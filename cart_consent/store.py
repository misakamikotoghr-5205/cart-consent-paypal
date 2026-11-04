"""Atomic approval state, immutable attempts and PII-free event history."""
from contextlib import contextmanager
from copy import deepcopy
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import time

from .domain import (CATALOG, Conflict, ConsentError, ProviderError, canonical, diff_paths,
                     fingerprint, normalize_cart, require_role)


class Store:
    def __init__(self, path, *, mode='mock', merchant_id='mock-merchant', catalog=None, clock=time.time):
        if str(path) == ':memory:':
            raise ConsentError('A persistent SQLite file is required.')
        self.path, self.mode, self.merchant_id, self.clock = str(path), mode, merchant_id, clock
        self.catalog = deepcopy(CATALOG if catalog is None else catalog)
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        os.close(os.open(target, os.O_CREAT | os.O_RDWR, 0o600))
        os.chmod(target, 0o600)
        with self.transaction() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS carts (
                    id TEXT PRIMARY KEY, idempotency_key TEXT UNIQUE NOT NULL,
                    input_json TEXT NOT NULL, snapshot_json TEXT NOT NULL, fingerprint TEXT NOT NULL,
                    revision INTEGER NOT NULL, status TEXT NOT NULL,
                    approved_hash TEXT, approval_nonce TEXT, approved_at REAL, approval_expires REAL,
                    mode TEXT NOT NULL, merchant_id TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS attempts (
                    request_id TEXT PRIMARY KEY, cart_id TEXT NOT NULL, revision INTEGER NOT NULL,
                    snapshot_hash TEXT NOT NULL, approval_nonce TEXT NOT NULL,
                    state TEXT NOT NULL, result_json TEXT
                );
                CREATE TABLE IF NOT EXISTS audit (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT, cart_id TEXT NOT NULL,
                    event TEXT NOT NULL, actor TEXT NOT NULL, data_json TEXT NOT NULL, at REAL NOT NULL
                );
            ''')

    @contextmanager
    def transaction(self):
        db = sqlite3.connect(self.path, isolation_level=None, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            db.execute('BEGIN IMMEDIATE')
            yield db
            if db.in_transaction:
                db.execute('COMMIT')
        except Exception:
            if db.in_transaction:
                db.execute('ROLLBACK')
            raise
        finally:
            db.close()

    def _normalize(self, data):
        snapshot = normalize_cart(data, self.catalog)
        snapshot['checkout_mode'] = self.mode
        snapshot['merchant']['id'] = self.merchant_id
        return snapshot

    def _event(self, db, cart_id, event, role, data):
        db.execute('INSERT INTO audit(cart_id,event,actor,data_json,at) VALUES(?,?,?,?,?)',
                   (cart_id, event, role, canonical(data), self.clock()))

    def _row(self, db, cart_id):
        row = db.execute('SELECT * FROM carts WHERE id=?', (cart_id,)).fetchone()
        if row is None:
            raise ConsentError('Unknown cart.')
        return dict(row)

    def _same_context(self, row):
        if row['mode'] != self.mode or row['merchant_id'] != self.merchant_id:
            raise Conflict('Cart belongs to a different merchant or payment mode. Create a new draft.')

    def _approval_valid(self, row):
        return (row['approved_hash'] == row['fingerprint'] and row['approval_nonce'] is not None
                and row['approval_expires'] is not None and self.clock() < row['approval_expires']
                and fingerprint(self._normalize(json.loads(row['input_json']))) == row['fingerprint'])

    def _view(self, row, role):
        snapshot = json.loads(row['snapshot_json'])
        if role == 'agent':
            snapshot['shipping']['address'] = {'redacted': True}
        return {'id': row['id'], 'revision': row['revision'], 'fingerprint': row['fingerprint'],
                'status': row['status'], 'snapshot': snapshot,
                'approval_valid': self._approval_valid(row), 'approval_expires': row['approval_expires'],
                'over_budget': snapshot['totals']['total_minor'] > snapshot['budget_minor'],
                'mode': row['mode'], 'real_money': False}

    def create(self, data, idempotency_key, role='agent'):
        require_role(role, {'agent', 'human'})
        if not isinstance(idempotency_key, str) or not re.fullmatch(r'[A-Za-z0-9_-]{12,128}', idempotency_key):
            raise ConsentError('Idempotency-Key must contain 12–128 letters, digits, underscores or hyphens.')
        snapshot = self._normalize(data)
        digest = fingerprint(snapshot)
        with self.transaction() as db:
            existing = db.execute('SELECT * FROM carts WHERE idempotency_key=?', (idempotency_key,)).fetchone()
            if existing:
                if existing['fingerprint'] != digest:
                    raise Conflict('Idempotency key already belongs to a different snapshot.')
                return self._view(dict(existing), role)
            cart_id = 'cart_' + secrets.token_hex(12)
            db.execute('INSERT INTO carts(id,idempotency_key,input_json,snapshot_json,fingerprint,revision,status,mode,merchant_id) VALUES(?,?,?,?,?,?,?,?,?)',
                       (cart_id, idempotency_key, canonical(data), canonical(snapshot), digest, 1, 'DRAFT', self.mode, self.merchant_id))
            self._event(db, cart_id, 'DRAFT_CREATED', role, {'fingerprint': digest, 'revision': 1})
            return self._view(self._row(db, cart_id), role)

    def get(self, cart_id, role='human'):
        require_role(role, {'agent', 'human'})
        with self.transaction() as db:
            return self._view(self._row(db, cart_id), role)

    def update(self, cart_id, data, expected_revision, role='agent'):
        require_role(role, {'agent', 'human'})
        snapshot = self._normalize(data)
        with self.transaction() as db:
            row = self._row(db, cart_id)
            self._same_context(row)
            if type(expected_revision) is not int or expected_revision != row['revision']:
                raise Conflict('Cart revision changed. Review the current snapshot before updating.')
            digest = fingerprint(snapshot)
            if digest != row['fingerprint']:
                changed = diff_paths(json.loads(row['snapshot_json']), snapshot)
                db.execute("UPDATE carts SET input_json=?,snapshot_json=?,fingerprint=?,revision=revision+1,status='DRAFT',approved_hash=NULL,approval_nonce=NULL,approved_at=NULL,approval_expires=NULL WHERE id=?",
                           (canonical(data), canonical(snapshot), digest, cart_id))
                self._event(db, cart_id, 'SNAPSHOT_CHANGED_APPROVAL_REVOKED', role,
                            {'previous_hash': row['fingerprint'], 'fingerprint': digest, 'changed_fields': changed, 'revision': row['revision'] + 1})
            return self._view(self._row(db, cart_id), role)

    def approve(self, cart_id, expected_fingerprint, role='human'):
        require_role(role, {'human'})
        with self.transaction() as db:
            row = self._row(db, cart_id)
            self._same_context(row)
            if expected_fingerprint != row['fingerprint']:
                raise Conflict('Approval fingerprint is stale. Review the current full basket first.')
            if fingerprint(self._normalize(json.loads(row['input_json']))) != row['fingerprint']:
                raise Conflict('Catalog pricing changed. Update and review the basket again before approving.')
            snapshot = json.loads(row['snapshot_json'])
            if snapshot['totals']['total_minor'] > snapshot['budget_minor']:
                raise Conflict('Basket exceeds the approved budget including shipping.')
            if not self._approval_valid(row):
                now = self.clock()
                db.execute("UPDATE carts SET status='APPROVED',approved_hash=fingerprint,approval_nonce=?,approved_at=?,approval_expires=? WHERE id=?",
                           (secrets.token_hex(12), now, now + 900, cart_id))
                self._event(db, cart_id, 'HUMAN_APPROVED_EXACT_SNAPSHOT', role,
                            {'fingerprint': row['fingerprint'], 'revision': row['revision'], 'expires': now + 900})
            return self._view(self._row(db, cart_id), role)

    def revoke(self, cart_id, role='human'):
        require_role(role, {'human'})
        with self.transaction() as db:
            self._row(db, cart_id)
            db.execute("UPDATE carts SET status='DRAFT',approved_hash=NULL,approval_nonce=NULL,approval_expires=NULL WHERE id=?", (cart_id,))
            self._event(db, cart_id, 'HUMAN_REVOKED', role, {})
            return self._view(self._row(db, cart_id), role)

    def checkout(self, cart_id, expected_fingerprint, provider, role='human'):
        require_role(role, {'human'})
        # Persist the attempt before the network. A stable request ID survives timeouts.
        with self.transaction() as db:
            row = self._row(db, cart_id)
            self._same_context(row)
            snapshot = json.loads(row['snapshot_json'])
            current = self._normalize(json.loads(row['input_json']))
            if fingerprint(current) != row['fingerprint']:
                raise Conflict('Catalog pricing changed. Update and review the basket again before checkout.')
            if expected_fingerprint != row['fingerprint'] or not self._approval_valid(row):
                raise Conflict('A current, unexpired human approval of this exact snapshot is required.')
            if provider.mode != self.mode or provider.merchant_id != self.merchant_id:
                raise Conflict('Checkout provider differs from the approved merchant or mode.')
            request_id = 'cc-' + fingerprint({'cart': cart_id, 'revision': row['revision'], 'nonce': row['approval_nonce']})[:32]
            attempt = db.execute('SELECT * FROM attempts WHERE request_id=?', (request_id,)).fetchone()
            if attempt and attempt['state'] == 'READY':
                return json.loads(attempt['result_json']) | {'replayed': True}
            if attempt is None:
                db.execute('INSERT INTO attempts VALUES(?,?,?,?,?,?,?)',
                           (request_id, cart_id, row['revision'], row['fingerprint'], row['approval_nonce'], 'PENDING', None))
                self._event(db, cart_id, 'CHECKOUT_LINK_REQUESTED', role, {'fingerprint': row['fingerprint'], 'request_id': request_id})
        try:
            result = provider.create_order(deepcopy(snapshot), cart_id, row['fingerprint'], request_id)
            if result.get('snapshot_hash') != row['fingerprint'] or result.get('mode') != self.mode or result.get('real_money') is not False:
                raise ProviderError('Checkout result is not bound to the current approved snapshot.')
        except Exception as exc:
            with self.transaction() as db:
                db.execute("UPDATE attempts SET state='RETRYABLE' WHERE request_id=? AND state!='READY'", (request_id,))
            raise ProviderError('Checkout link creation failed. Retry safely with the same approved snapshot; no capture is available.') from exc
        stale = False
        with self.transaction() as db:
            latest = self._row(db, cart_id)
            if (latest['revision'] != row['revision'] or latest['fingerprint'] != row['fingerprint']
                    or latest['approval_nonce'] != row['approval_nonce'] or not self._approval_valid(latest)
                    or fingerprint(self._normalize(json.loads(latest['input_json']))) != row['fingerprint']):
                db.execute("UPDATE attempts SET state='STALE',result_json=NULL WHERE request_id=?", (request_id,))
                self._event(db, cart_id, 'STALE_CHECKOUT_LINK_WITHHELD', role, {'approved_hash': row['fingerprint']})
                stale = True
            else:
                db.execute("UPDATE attempts SET state='READY',result_json=? WHERE request_id=?", (canonical(result), request_id))
                db.execute("UPDATE carts SET status='LINK_READY' WHERE id=?", (cart_id,))
                self._event(db, cart_id, 'CHECKOUT_LINK_READY', role, {'fingerprint': row['fingerprint'], 'provider': provider.mode})
        if stale:
            raise Conflict('Basket, catalog, approval or expiry changed during checkout. The resulting link was withheld; review again.')
        return result | {'replayed': False}

    def audit(self, cart_id, role='human'):
        require_role(role, {'human'})
        with self.transaction() as db:
            self._row(db, cart_id)
            return [{'seq': row['seq'], 'event': row['event'], 'actor': row['actor'], 'data': json.loads(row['data_json']), 'at': row['at']}
                    for row in db.execute('SELECT * FROM audit WHERE cart_id=? ORDER BY seq', (cart_id,))]
