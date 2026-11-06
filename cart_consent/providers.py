"""Only mock checkout links or PayPal sandbox order creation; never capture."""
import base64
import json
import os
import re
import time
from urllib.parse import urlsplit, parse_qs
from urllib.request import Request, build_opener, HTTPRedirectHandler, ProxyHandler

from .domain import ConfigurationError, ProviderError, fingerprint, minor_value


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        return None


class JsonTransport:
    def __init__(self, *, use_environment_proxy=True, timeout=15):
        handlers = [NoRedirect()]
        if not use_environment_proxy:
            # Local model requests must stay on loopback even when a proxy is configured.
            handlers.append(ProxyHandler({}))
        self.opener = build_opener(*handlers)
        self.timeout = timeout

    def post(self, url, body, headers):
        try:
            with self.opener.open(Request(url, data=body, headers=headers, method='POST'), timeout=self.timeout) as response:
                raw = response.read(1048577)
                if len(raw) > 1048576:
                    raise ValueError('response too large')
                value = json.loads(raw)
                if not isinstance(value, dict):
                    raise ValueError('invalid response')
                return value
        except Exception as exc:
            # Do not return upstream bodies: they can contain tokens or PII.
            raise ProviderError('Upstream request failed; no checkout or capture was performed by this application.') from exc


class MockPayPal:
    mode = 'mock'
    merchant_id = 'mock-merchant'

    def create_order(self, cart, cart_id, snapshot_hash, request_id):
        order_id = 'MOCK-' + fingerprint({'request_id': request_id})[:20]
        return {'order_id': order_id, 'approval_url': 'mock-checkout://' + order_id,
                'mode': 'mock', 'real_money': False, 'snapshot_hash': snapshot_hash,
                'notice': 'Synthetic link. No PayPal order, buyer checkout, authorization, or capture exists.'}


def order_body(cart, cart_id, snapshot_hash, return_url, cancel_url):
    currency = cart['currency']

    def money(value):
        return {'currency_code': currency, 'value': minor_value(value)}

    address = dict(cart['shipping']['address'])
    name = address.pop('full_name')
    unit = {'reference_id': cart_id, 'custom_id': snapshot_hash,
            'amount': money(cart['totals']['total_minor']) | {'breakdown': {
                'item_total': money(cart['totals']['items_minor']),
                'shipping': money(cart['totals']['shipping_minor'])}},
            'items': [{'name': item['name'], 'sku': item['sku'], 'quantity': str(item['quantity']),
                       'unit_amount': money(item['unit_minor']), 'category': 'PHYSICAL_GOODS'} for item in cart['items']],
            'shipping': {'name': {'full_name': name}, 'address': address}}
    if cart['checkout_mode'] == 'paypal-sandbox':
        unit['payee'] = {'merchant_id': cart['merchant']['id']}
    return {'intent': 'CAPTURE', 'purchase_units': [unit],
            'payment_source': {'paypal': {'experience_context': {
                'brand_name': 'Cart Consent Sandbox', 'shipping_preference': 'SET_PROVIDED_ADDRESS',
                'user_action': 'CONTINUE', 'return_url': return_url, 'cancel_url': cancel_url}}}}


class PayPalSandbox:
    mode = 'paypal-sandbox'
    BASE = 'https://api-m.sandbox.paypal.com'

    def __init__(self, environ=None, transport=None):
        env = os.environ if environ is None else environ
        self.client_id, self.secret = env.get('PAYPAL_CLIENT_ID', ''), env.get('PAYPAL_CLIENT_SECRET', '')
        self.return_url, self.cancel_url = env.get('PAYPAL_RETURN_URL', ''), env.get('PAYPAL_CANCEL_URL', '')
        self.merchant_id = env.get('PAYPAL_MERCHANT_ID', '')
        if not all((self.client_id, self.secret, self.return_url, self.cancel_url, self.merchant_id)):
            raise ConfigurationError('Sandbox mode requires PAYPAL_CLIENT_ID, PAYPAL_CLIENT_SECRET, PAYPAL_MERCHANT_ID, PAYPAL_RETURN_URL and PAYPAL_CANCEL_URL; no fallback to mock.')
        if not re.fullmatch(r'[A-Z0-9]{13}', self.merchant_id):
            raise ConfigurationError('Configure the sandbox business merchant ID, not a buyer email or client ID.')
        for value in (self.return_url, self.cancel_url):
            parsed = urlsplit(value)
            if parsed.scheme != 'https' or not parsed.netloc or parsed.username or parsed.password:
                raise ConfigurationError('Return and cancel URLs must be explicit HTTPS URLs without credentials.')
        self.transport = transport or JsonTransport()
        self._token, self._expires = None, 0

    def _access_token(self):
        if self._token and time.monotonic() < self._expires:
            return self._token
        basic = base64.b64encode(f'{self.client_id}:{self.secret}'.encode()).decode()
        result = self.transport.post(self.BASE + '/v1/oauth2/token', b'grant_type=client_credentials',
                                     {'Authorization': 'Basic ' + basic, 'Content-Type': 'application/x-www-form-urlencoded'})
        token, expires = result.get('access_token'), result.get('expires_in')
        if not isinstance(token, str) or not token or type(expires) not in (int, float) or not 0 < expires <= 86400:
            raise ProviderError('Sandbox OAuth response is missing a valid token or lifetime.')
        self._token, self._expires = token, time.monotonic() + max(0, expires - 30)
        return token

    def create_order(self, cart, cart_id, snapshot_hash, request_id):
        if cart.get('checkout_mode') != self.mode or cart.get('merchant', {}).get('id') != self.merchant_id:
            raise ProviderError('Merchant or payment mode differs from the approved snapshot.')
        body = order_body(cart, cart_id, snapshot_hash, self.return_url, self.cancel_url)
        result = self.transport.post(self.BASE + '/v2/checkout/orders', json.dumps(body).encode(),
            {'Authorization': 'Bearer ' + self._access_token(), 'Content-Type': 'application/json',
             'PayPal-Request-Id': request_id, 'Prefer': 'return=representation'})
        order_id = result.get('id')
        if not isinstance(order_id, str) or not re.fullmatch(r'[A-Z0-9]{8,32}', order_id) or result.get('status') not in ('CREATED', 'PAYER_ACTION_REQUIRED'):
            raise ProviderError('Sandbox did not return a new, uncompleted order.')
        units = result.get('purchase_units')
        if not isinstance(units, list) or len(units) != 1:
            raise ProviderError('Sandbox order representation is missing its purchase unit; fail closed.')
        expected, actual = body['purchase_units'][0], units[0]
        if (actual.get('custom_id') != snapshot_hash or actual.get('reference_id') != cart_id
                or actual.get('amount') != expected['amount'] or actual.get('shipping') != expected['shipping']
                or actual.get('items') != expected['items'] or actual.get('payee', {}).get('merchant_id') != self.merchant_id):
            raise ProviderError('Sandbox order representation does not exactly match the approved snapshot.')
        links = result.get('links', [])
        for link in links if isinstance(links, list) else []:
            if not isinstance(link, dict) or link.get('rel') not in ('approve', 'payer-action') or link.get('method') != 'GET':
                continue
            url = link.get('href', '')
            try:
                parsed = urlsplit(url)
                port = parsed.port
            except (TypeError, ValueError):
                continue
            if (parsed.scheme == 'https' and parsed.hostname in ('www.sandbox.paypal.com', 'sandbox.paypal.com')
                    and port in (None, 443) and not parsed.username and not parsed.password
                    and parsed.path in ('/checkoutnow', '/webapps/hermes')
                    and parse_qs(parsed.query).get('token') == [order_id]):
                return {'order_id': order_id, 'approval_url': url, 'mode': self.mode, 'real_money': False,
                        'snapshot_hash': snapshot_hash, 'notice': 'Sandbox order creation only. No browser opened and no capture endpoint exists.'}
        raise ProviderError('Sandbox did not return an allowed, matching approval URL.')


def payment_provider(environ=None):
    env = os.environ if environ is None else environ
    mode = env.get('CART_PAYMENT_MODE', 'mock')
    if mode == 'mock':
        return MockPayPal()
    if mode == 'paypal-sandbox':
        return PayPalSandbox(env)
    raise ConfigurationError('Only mock and paypal-sandbox are implemented; production is deliberately unavailable.')
