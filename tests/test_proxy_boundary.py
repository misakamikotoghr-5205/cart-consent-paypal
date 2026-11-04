"""No sockets: intercept requests after proxy handling and before HTTP transport."""
import io
import json
from email.message import Message
from unittest.mock import patch
import unittest
from urllib.request import BaseHandler
from urllib.response import addinfourl

from cart_consent.planner import Planner
from cart_consent.providers import PayPalSandbox


class CaptureAfterProxy(BaseHandler):
    handler_order = 200  # ProxyHandler=100; actual HTTP/HTTPS handlers=500.

    def __init__(self, response):
        self.response = response
        self.calls = []

    def intercept(self, request):
        self.calls.append({'host': request.host, 'url': request.full_url,
                           'body': request.data})
        reply = addinfourl(io.BytesIO(json.dumps(self.response).encode()),
                          Message(), request.full_url, 200)
        reply.msg = 'OK'
        return reply

    http_open = intercept
    https_open = intercept


class ProxyBoundaryTests(unittest.TestCase):
    def test_ollama_loopback_transport_ignores_environment_proxy_without_socket_access(self):
        environment = {'http_proxy': 'http://off-host-proxy.invalid:8080',
                       'https_proxy': 'http://off-host-proxy.invalid:8080',
                       'no_proxy': ''}
        with patch.dict('os.environ', environment, clear=True):
            planner = Planner({'CART_AGENT_MODE': 'ollama', 'OLLAMA_MODEL': 'test-double'})
            capture = CaptureAfterProxy({'message': {'content': json.dumps({
                'selections': [{'sku': 'pen-set', 'quantity': 1}],
                'reason': 'Synthetic transport contract test.'})}})
            planner.transport.opener.add_handler(capture)
            from test_adapters import DRAFT
            context = {key: value for key, value in DRAFT.items() if key != 'selections'}
            planner.propose('Choose stationery', context)
        self.assertEqual(len(capture.calls), 1)
        self.assertEqual(capture.calls[0]['host'], '127.0.0.1:11434')
        self.assertEqual(capture.calls[0]['url'], 'http://127.0.0.1:11434/api/chat')

    def test_sandbox_transport_keeps_environment_proxy_support_without_socket_access(self):
        environment = {'https_proxy': 'http://sandbox-proxy.invalid:8080', 'no_proxy': ''}
        with patch.dict('os.environ', environment, clear=True):
            from test_adapters import CONFIG
            provider = PayPalSandbox(CONFIG)
            capture = CaptureAfterProxy({'access_token': 'synthetic-access-token',
                                         'expires_in': 3600})
            provider.transport.opener.add_handler(capture)
            self.assertEqual(provider._access_token(), 'synthetic-access-token')
        self.assertEqual(len(capture.calls), 1)
        self.assertEqual(capture.calls[0]['host'], 'sandbox-proxy.invalid:8080')
        self.assertEqual(capture.calls[0]['url'],
                         'https://api-m.sandbox.paypal.com/v1/oauth2/token')


if __name__ == '__main__':
    unittest.main()
