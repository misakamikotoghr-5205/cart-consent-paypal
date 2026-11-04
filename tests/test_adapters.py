from copy import deepcopy
import json
from pathlib import Path
import unittest

from cart_consent.domain import CATALOG, ConfigurationError, ConsentError, ProviderError, fingerprint, normalize_cart
from cart_consent.planner import Planner
from cart_consent.providers import PayPalSandbox, payment_provider

DRAFT = json.loads((Path(__file__).resolve().parents[1] / 'examples' / 'cart.json').read_text())
CONFIG = {'PAYPAL_CLIENT_ID': 'test-client', 'PAYPAL_CLIENT_SECRET': 'test-secret',
          'PAYPAL_MERCHANT_ID': 'ABCDEFGHIJKLM', 'PAYPAL_RETURN_URL': 'https://example.org/return',
          'PAYPAL_CANCEL_URL': 'https://example.org/cancel'}


class PayPalTransport:
    def __init__(self, mutate=None):
        self.calls, self.mutate = [], mutate

    def post(self, url, body, headers):
        self.calls.append((url, body, headers))
        if url.endswith('/v1/oauth2/token'):
            return {'access_token': 'test-access-token', 'expires_in': 3600}
        data = json.loads(body)
        result = {'id': '5O190127TN364715T', 'status': 'PAYER_ACTION_REQUIRED',
                  'purchase_units': deepcopy(data['purchase_units']),
                  'links': [{'rel': 'payer-action', 'method': 'GET',
                             'href': 'https://www.sandbox.paypal.com/checkoutnow?token=5O190127TN364715T'}]}
        if self.mutate:
            self.mutate(result)
        return result


class AdapterTests(unittest.TestCase):
    def snapshot(self):
        snapshot = normalize_cart(DRAFT)
        snapshot['checkout_mode'] = 'paypal-sandbox'
        snapshot['merchant']['id'] = CONFIG['PAYPAL_MERCHANT_ID']
        return snapshot

    def test_official_oauth_and_orders_create_contract_has_no_capture_or_auto_complete(self):
        transport = PayPalTransport()
        provider = PayPalSandbox(CONFIG, transport)
        snapshot = self.snapshot()
        result = provider.create_order(snapshot, 'cart_test', fingerprint(snapshot), 'stable-request-123')
        self.assertEqual(len(transport.calls), 2)
        oauth, create = transport.calls
        self.assertEqual(oauth[0], 'https://api-m.sandbox.paypal.com/v1/oauth2/token')
        self.assertEqual(oauth[1], b'grant_type=client_credentials')
        self.assertTrue(oauth[2]['Authorization'].startswith('Basic '))
        self.assertEqual(create[0], 'https://api-m.sandbox.paypal.com/v2/checkout/orders')
        self.assertEqual(create[2]['PayPal-Request-Id'], 'stable-request-123')
        self.assertEqual(create[2]['Authorization'], 'Bearer test-access-token')
        body = json.loads(create[1])
        unit = body['purchase_units'][0]
        self.assertEqual(unit['amount']['value'], '39.96')
        self.assertEqual(unit['amount']['breakdown']['shipping']['value'], '4.99')
        self.assertEqual(unit['payee']['merchant_id'], CONFIG['PAYPAL_MERCHANT_ID'])
        self.assertEqual(unit['custom_id'], fingerprint(snapshot))
        context = body['payment_source']['paypal']['experience_context']
        self.assertEqual(context['shipping_preference'], 'SET_PROVIDED_ADDRESS')
        self.assertEqual(context['user_action'], 'CONTINUE')
        self.assertNotIn('processing_instruction', body)
        self.assertFalse(result['real_money'])
        self.assertFalse(hasattr(provider, 'capture'))

    def test_unbound_amount_payee_items_address_or_untrusted_approval_url_fail_closed(self):
        mutations = [
            lambda r: r['purchase_units'][0]['amount'].update(value='0.01'),
            lambda r: r['purchase_units'][0]['payee'].update(merchant_id='ZZZZZZZZZZZZZ'),
            lambda r: r['purchase_units'][0]['shipping']['address'].update(postal_code='00000'),
            lambda r: r['purchase_units'][0]['items'][0].update(quantity='20'),
            lambda r: r.update(purchase_units=[]),
            lambda r: r.update(status='COMPLETED'),
            lambda r: r['links'][0].update(href='https://paypal.com.attacker.example/checkoutnow?token=5O190127TN364715T'),
            lambda r: r['links'][0].update(href='https://www.sandbox.paypal.com/checkoutnow?token=DIFFERENT'),
        ]
        snapshot = self.snapshot()
        for mutate in mutations:
            with self.assertRaises(ProviderError):
                PayPalSandbox(CONFIG, PayPalTransport(mutate)).create_order(snapshot, 'cart_test', fingerprint(snapshot), 'request')

    def test_missing_sandbox_configuration_and_production_or_unknown_modes_never_fall_back(self):
        for env in ({'CART_PAYMENT_MODE': 'paypal-sandbox'}, {'CART_PAYMENT_MODE': 'production'}, {'CART_PAYMENT_MODE': 'typo'}):
            with self.assertRaises(ConfigurationError):
                payment_provider(env)
        with self.assertRaises(ConfigurationError):
            PayPalSandbox(CONFIG | {'PAYPAL_RETURN_URL': 'http://example.org/return'})

    def test_ollama_structured_proposal_excludes_address_and_has_no_approval_capability(self):
        class ModelTransport:
            payload = None

            def post(self, url, body, headers):
                self.payload = json.loads(body)
                self.url = url
                return {'message': {'content': json.dumps({'selections': [{'sku': 'pen-set', 'quantity': 2}], 'reason': 'Two pen sets fit the supplied budget.'})}}

        transport = ModelTransport()
        context = {key: value for key, value in DRAFT.items() if key != 'selections'}
        planner = Planner({'CART_AGENT_MODE': 'ollama', 'OLLAMA_MODEL': 'configured-model'}, transport=transport)
        proposal = planner.propose('Choose stationery for a workshop', context)
        self.assertTrue(proposal['ai_used'])
        self.assertFalse(proposal['approval_granted'])
        self.assertFalse(transport.payload['stream'])
        self.assertEqual(transport.payload['format']['additionalProperties'], False)
        self.assertNotIn('tools', transport.payload)
        for field in ('full_name', 'address_line_1', 'postal_code'):
            self.assertNotIn(DRAFT['shipping']['address'][field], json.dumps(transport.payload))
        user_context = json.loads(transport.payload['messages'][1]['content'])
        self.assertNotIn('shipping', user_context)
        self.assertNotIn('address', user_context)
        self.assertEqual(proposal['draft']['shipping'], DRAFT['shipping'])

    def test_model_cannot_supply_prices_approval_or_unknown_skus(self):
        class ModelTransport:
            def __init__(self, response):
                self.response = response

            def post(self, *_args):
                return {'message': {'content': json.dumps(self.response)}}

        context = {key: value for key, value in DRAFT.items() if key != 'selections'}
        for response in [
            {'selections': [{'sku': 'pen-set', 'quantity': 1}], 'reason': 'ok', 'approved': True},
            {'selections': [{'sku': 'pen-set', 'quantity': 1, 'unit_minor': 1}], 'reason': 'ok'},
            {'selections': [{'sku': 'invented-item', 'quantity': 1}], 'reason': 'ok'},
            {'selections': [{'sku': 'desk-pouch', 'quantity': 20}], 'reason': 'too much'},
        ]:
            with self.assertRaises(ConsentError):
                Planner({'CART_AGENT_MODE': 'ollama', 'OLLAMA_MODEL': 'configured-model'}, ModelTransport(response)).propose('Buy supplies', context)
        with self.assertRaises(ConfigurationError):
            Planner({'CART_AGENT_MODE': 'ollama', 'OLLAMA_MODEL': 'x', 'OLLAMA_URL': 'https://remote.example/api/chat'})
        self.assertFalse(Planner({}).propose('A notebook', context)['ai_used'])
