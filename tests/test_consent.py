from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from cart_consent.domain import CATALOG, Conflict, ConsentError, Forbidden, fingerprint, normalize_cart
from cart_consent.providers import MockPayPal
from cart_consent.store import Store

ROOT = Path(__file__).resolve().parents[1]
DRAFT = json.loads((ROOT / 'examples' / 'cart.json').read_text())


class SpyMock(MockPayPal):
    def __init__(self):
        self.calls = []
        self.before_return = None
        self.fail_once = False

    def create_order(self, cart, cart_id, snapshot_hash, request_id):
        self.calls.append(request_id)
        if self.fail_once:
            self.fail_once = False
            raise RuntimeError('simulated timeout with private upstream details')
        result = super().create_order(cart, cart_id, snapshot_hash, request_id)
        if self.before_return:
            self.before_return()
        return result


class ConsentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / 'private.sqlite3'
        self.now = [1800000000]
        self.store = Store(self.db, clock=lambda: self.now[0])
        self.provider = SpyMock()
        self.cart = self.store.create(DRAFT, 'initial_cart_key_001')

    def tearDown(self):
        self.tmp.cleanup()

    def approve(self, cart=None):
        cart = cart or self.cart
        return self.store.approve(cart['id'], cart['fingerprint'])

    def test_no_link_before_exact_human_approval_and_agent_cannot_approve_or_checkout(self):
        for operation in (lambda: self.store.approve(self.cart['id'], self.cart['fingerprint'], 'agent'),
                          lambda: self.store.checkout(self.cart['id'], self.cart['fingerprint'], self.provider, 'agent'),
                          lambda: self.store.revoke(self.cart['id'], 'agent')):
            with self.assertRaises(Forbidden):
                operation()
        with self.assertRaises(Conflict):
            self.store.checkout(self.cart['id'], self.cart['fingerprint'], self.provider)
        with self.assertRaises(Conflict):
            self.store.approve(self.cart['id'], 'wrong-fingerprint')
        self.assertEqual(self.provider.calls, [])
        self.approve()
        link = self.store.checkout(self.cart['id'], self.cart['fingerprint'], self.provider)
        self.assertTrue(link['approval_url'].startswith('mock-checkout://'))
        self.assertFalse(link['real_money'])

    def test_every_critical_field_change_revokes_the_old_approval(self):
        mutations = [
            lambda d: d.update(budget_minor=d['budget_minor'] + 1),
            lambda d: d.update(currency='EUR'),
            lambda d: d['selections'][0].update(quantity=1),
            lambda d: d['selections'][0].update(sku='desk-pouch'),
            lambda d: d['shipping'].update(method='express'),
        ]
        for field in DRAFT['shipping']['address']:
            mutations.append(lambda d, field=field: d['shipping']['address'].update({field: 'GB' if field == 'country_code' else d['shipping']['address'][field] + ' new'}))
        mutations.append(lambda d: d['shipping']['address'].update(address_line_2='Suite 2'))
        for index, mutate in enumerate(mutations):
            original = self.store.create(DRAFT, f'mutation_case_{index:04d}')
            self.approve(original)
            draft = deepcopy(DRAFT)
            mutate(draft)
            updated = self.store.update(original['id'], draft, 1)
            self.assertNotEqual(updated['fingerprint'], original['fingerprint'])
            self.assertFalse(updated['approval_valid'])
            self.assertEqual(updated['revision'], 2)
            with self.assertRaises(Conflict):
                self.store.checkout(original['id'], original['fingerprint'], self.provider)
        self.assertEqual(self.provider.calls, [])

    def test_shipping_and_item_prices_are_server_owned_and_catalog_repricing_requires_review(self):
        self.approve()
        self.store.catalog['notebook']['prices']['USD'] += 1
        self.assertFalse(self.store.get(self.cart['id'])['approval_valid'])
        with self.assertRaises(Conflict):
            self.store.checkout(self.cart['id'], self.cart['fingerprint'], self.provider)
        with self.assertRaises(Conflict):
            self.approve()
        updated = self.store.update(self.cart['id'], DRAFT, 1)
        self.assertIn('items[0].unit_minor', self.store.audit(self.cart['id'])[-1]['data']['changed_fields'])
        self.approve(updated)
        self.assertIn('approval_url', self.store.checkout(updated['id'], updated['fingerprint'], self.provider))
        bad = deepcopy(DRAFT)
        bad['selections'][0]['unit_minor'] = 1
        with self.assertRaises(ConsentError):
            normalize_cart(bad)
        bad = deepcopy(DRAFT)
        bad['shipping']['amount_minor'] = 0
        with self.assertRaises(ConsentError):
            normalize_cart(bad)

    def test_budget_is_integer_and_includes_shipping(self):
        for bad in (True, 5000.0, -1, '5000'):
            with self.assertRaises(ConsentError):
                normalize_cart(DRAFT | {'budget_minor': bad})
        over_budget = self.store.create(DRAFT | {'budget_minor': 3497}, 'over_budget_cart_001')
        self.assertTrue(over_budget['over_budget'])
        with self.assertRaises(Conflict):
            self.approve(over_budget)

    def test_unchanged_normalized_snapshot_is_idempotent_and_does_not_extend_approval(self):
        approved = self.approve()
        self.now[0] += 30
        repeated = self.approve()
        self.assertEqual(approved['approval_expires'], repeated['approval_expires'])
        whitespace = deepcopy(DRAFT)
        whitespace['shipping']['address']['full_name'] = '  Example Buyer  '
        same = self.store.update(self.cart['id'], whitespace, 1)
        self.assertTrue(same['approval_valid'])
        self.assertEqual(same['revision'], 1)

    def test_timeout_retry_uses_same_idempotency_key_and_persistent_cached_link(self):
        self.approve()
        self.provider.fail_once = True
        from cart_consent.domain import ProviderError
        with self.assertRaises(ProviderError):
            self.store.checkout(self.cart['id'], self.cart['fingerprint'], self.provider)
        first = self.store.checkout(self.cart['id'], self.cart['fingerprint'], self.provider)
        self.assertEqual(self.provider.calls[0], self.provider.calls[1])
        restored = Store(self.db, clock=lambda: self.now[0])
        another_provider = SpyMock()
        second = restored.checkout(self.cart['id'], self.cart['fingerprint'], another_provider)
        self.assertEqual(first['order_id'], second['order_id'])
        self.assertTrue(second['replayed'])
        self.assertEqual(another_provider.calls, [])

    def test_stale_approval_expiry_and_manual_revocation_reject_cached_links(self):
        self.approve()
        self.store.checkout(self.cart['id'], self.cart['fingerprint'], self.provider)
        self.now[0] += 900
        with self.assertRaises(Conflict):
            self.store.checkout(self.cart['id'], self.cart['fingerprint'], self.provider)
        renewed = self.approve()
        self.assertTrue(renewed['approval_valid'])
        self.store.revoke(self.cart['id'])
        with self.assertRaises(Conflict):
            self.store.checkout(self.cart['id'], self.cart['fingerprint'], self.provider)

    def test_change_during_upstream_call_withholds_link_and_persists_stale_attempt(self):
        self.approve()
        changed = deepcopy(DRAFT)
        changed['shipping']['method'] = 'express'
        self.provider.before_return = lambda: self.store.update(self.cart['id'], changed, 1)
        with self.assertRaisesRegex(Conflict, 'withheld'):
            self.store.checkout(self.cart['id'], self.cart['fingerprint'], self.provider)
        with self.store.transaction() as db:
            row = db.execute('SELECT state,result_json FROM attempts').fetchone()
            self.assertEqual(row['state'], 'STALE')
            self.assertIsNone(row['result_json'])
        self.assertEqual(self.store.audit(self.cart['id'])[-1]['event'], 'STALE_CHECKOUT_LINK_WITHHELD')

    def test_expiry_during_upstream_call_also_withholds_link(self):
        self.approve()
        self.provider.before_return = lambda: self.now.__setitem__(0, self.now[0] + 900)
        with self.assertRaisesRegex(Conflict, 'withheld'):
            self.store.checkout(self.cart['id'], self.cart['fingerprint'], self.provider)

    def test_idempotency_revision_and_mode_boundaries(self):
        self.assertEqual(self.store.create(DRAFT, 'initial_cart_key_001')['id'], self.cart['id'])
        with self.assertRaises(Conflict):
            self.store.create(DRAFT | {'budget_minor': 6000}, 'initial_cart_key_001')
        with self.assertRaises(Conflict):
            self.store.update(self.cart['id'], DRAFT, 0)
        other = Store(self.db, mode='paypal-sandbox', merchant_id='ABCDEFGHIJKLM')
        with self.assertRaises(Conflict):
            other.approve(self.cart['id'], self.cart['fingerprint'])

    def test_agent_view_and_audit_do_not_disclose_address_or_checkout_url(self):
        self.approve()
        self.store.checkout(self.cart['id'], self.cart['fingerprint'], self.provider)
        agent_json = json.dumps(self.store.get(self.cart['id'], 'agent'))
        audit_json = json.dumps(self.store.audit(self.cart['id']))
        for private in ('Example Buyer', '123 Fictional Demo Street', '95131', 'mock-checkout://'):
            self.assertNotIn(private, agent_json)
            self.assertNotIn(private, audit_json)
        self.assertIn('Example Buyer', json.dumps(self.store.get(self.cart['id'], 'human')))
