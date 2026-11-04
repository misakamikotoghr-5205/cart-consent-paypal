from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from cart_consent.domain import ConfigurationError
from cart_consent.http_api import make_server
from cart_consent.planner import Planner
from cart_consent.providers import MockPayPal
from cart_consent.store import Store

ROOT = Path(__file__).resolve().parents[1]
DRAFT = json.loads((ROOT / 'examples' / 'cart.json').read_text())
TOKENS = {'agent_token': 'agent-test-' + 'a' * 32, 'human_token': 'human-test-' + 'h' * 32}


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / 'http.sqlite3')
        self.provider = MockPayPal()
        self.server = make_server(('127.0.0.1', 0), self.store, self.provider, Planner({}), TOKENS)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.tmp.cleanup()

    def request(self, path, data=None, role='agent', method=None, extra_headers=None):
        headers = {'Authorization': 'Bearer ' + TOKENS[role + '_token'], 'Content-Type': 'application/json'} | (extra_headers or {})
        request = Request(self.base + path, data=None if data is None else json.dumps(data).encode(),
                          headers=headers, method=method)
        try:
            response = urlopen(request)
        except HTTPError as exc:
            response = exc
        with response:
            return response.status, json.loads(response.read())

    def create(self):
        status, body = self.request('/v1/carts', {'draft': DRAFT}, extra_headers={'Idempotency-Key': 'http_cart_key_001'})
        self.assertEqual(status, 201)
        return body['cart']

    def test_agent_draft_human_review_approval_checkout_and_change_reapproval_flow(self):
        cart = self.create()
        route = '/v1/carts/' + cart['id']
        self.assertEqual(cart['snapshot']['shipping']['address'], {'redacted': True})
        expected = {'expected_fingerprint': cart['fingerprint']}
        self.assertEqual(self.request(route + '/approve', expected)[0], 403)
        self.assertEqual(self.request(route + '/checkout-link', expected)[0], 403)
        self.assertEqual(self.request(route + '/checkout-link', expected, 'human')[0], 409)
        _, reviewed = self.request(route, role='human')
        self.assertEqual(reviewed['cart']['snapshot']['shipping']['address'], DRAFT['shipping']['address'])
        self.assertEqual(self.request(route + '/approve', expected, 'human')[0], 200)
        status, first = self.request(route + '/checkout-link', expected, 'human')
        self.assertEqual(status, 200)
        changed = deepcopy(DRAFT)
        changed['shipping']['address']['postal_code'] = '00000'
        status, updated = self.request(route, {'draft': changed, 'expected_revision': 1}, method='PATCH')
        self.assertEqual(status, 200)
        self.assertFalse(updated['cart']['approval_valid'])
        self.assertEqual(self.request(route + '/checkout-link', expected, 'human')[0], 409)
        fresh = {'expected_fingerprint': updated['cart']['fingerprint']}
        self.assertEqual(self.request(route + '/approve', fresh, 'human')[0], 200)
        status, second = self.request(route + '/checkout-link', fresh, 'human')
        self.assertEqual(status, 200)
        self.assertNotEqual(first['order_id'], second['order_id'])
        _, audit = self.request(route + '/audit', role='human')
        serialized = json.dumps(audit)
        for private in (TOKENS['agent_token'], TOKENS['human_token'], 'Example Buyer', '123 Fictional Demo Street', 'mock-checkout://'):
            self.assertNotIn(private, serialized)
        self.assertEqual(self.request(route + '/capture', {}, 'human')[0], 404)

    def test_proposal_endpoint_returns_only_a_draft_and_no_approval(self):
        context = {key: value for key, value in DRAFT.items() if key != 'selections'}
        status, body = self.request('/v1/proposals', {'goal': 'A notebook', 'context': context},
                                    extra_headers={'Idempotency-Key': 'http_proposal_001'})
        self.assertEqual(status, 201)
        self.assertEqual(body['cart']['status'], 'DRAFT')
        self.assertFalse(body['cart']['approval_valid'])
        self.assertFalse(body['proposal']['ai_used'])
        self.assertFalse(body['proposal']['approval_granted'])

    def test_missing_wrong_or_body_spoofed_role_never_confers_human_authority(self):
        cart = self.create()
        route = '/v1/carts/' + cart['id'] + '/approve'
        self.assertEqual(self.request(route, {'expected_fingerprint': cart['fingerprint'], 'role': 'human'})[0], 400)
        self.assertEqual(self.request('/v1/catalog', extra_headers={'Authorization': 'Bearer invalid'})[0], 403)
        self.assertEqual(self.request('/v1/catalog', extra_headers={'Authorization': TOKENS['human_token']})[0], 403)
        with self.assertRaises(ConfigurationError):
            make_server(('127.0.0.1', 0), self.store, self.provider, Planner({}), {'agent_token': 'same' * 10, 'human_token': 'same' * 10})


class CliTests(unittest.TestCase):
    def test_demo_proves_revocation_without_network_or_capture(self):
        with tempfile.TemporaryDirectory() as temp:
            env = os.environ | {'CART_PAYMENT_MODE': 'mock', 'CART_AGENT_MODE': 'mock'}
            result = subprocess.run([sys.executable, '-m', 'cart_consent', '--db', str(Path(temp) / 'demo.sqlite3'), 'demo'],
                                    cwd=ROOT, capture_output=True, text=True, env=env, check=True)
            data = json.loads(result.stdout)
            self.assertTrue(data['unapproved_blocked'])
            self.assertTrue(data['address_change_revoked_approval'])
            self.assertTrue(data['new_approval_new_order'])
            self.assertFalse(data['capture_implemented'])
            self.assertFalse(data['ai_used'])

    def test_role_file_is_private_does_not_print_tokens_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'roles.json'
            command = [sys.executable, '-m', 'cart_consent', 'init-tokens', '--out', str(path)]
            result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=True)
            tokens = json.loads(path.read_text())
            self.assertNotEqual(tokens['agent_token'], tokens['human_token'])
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertNotIn(tokens['human_token'], result.stdout)
            self.assertNotIn(tokens['agent_token'], result.stdout)
            repeated = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(repeated.returncode, 2)
            self.assertEqual(json.loads(path.read_text()), tokens)
