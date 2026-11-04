import argparse
from copy import deepcopy
import json
import os
from pathlib import Path
import secrets
import sys

from .domain import ConfigurationError, ConsentError, ProviderError, catalog_view
from .http_api import make_server
from .planner import Planner
from .providers import payment_provider
from .store import Store


def runtime(db, environ=None):
    provider = payment_provider(environ)
    planner = Planner(environ)
    store = Store(db, mode=provider.mode, merchant_id=provider.merchant_id)
    planner.catalog = store.catalog
    return store, provider, planner


def main(argv=None):
    parser = argparse.ArgumentParser(description='Cart Consent — exact shopping-basket approval before sandbox order links')
    parser.add_argument('--db', default='var/cart-consent.sqlite3')
    sub = parser.add_subparsers(dest='command', required=True)
    init = sub.add_parser('init-tokens', help='create a private role-token file without printing tokens')
    init.add_argument('--out', default='var/roles.json')
    serve = sub.add_parser('serve', help='local JSON API, bound only to 127.0.0.1')
    serve.add_argument('--tokens', default='var/roles.json')
    serve.add_argument('--port', type=int, default=8768)
    demo = sub.add_parser('demo', help='synthetic local consent demonstration; mock only')
    demo.add_argument('--input', default='examples/cart.json')
    create = sub.add_parser('draft')
    create.add_argument('--input', required=True)
    create.add_argument('--key', required=True)
    propose = sub.add_parser('propose')
    propose.add_argument('--goal', required=True)
    propose.add_argument('--context', required=True)
    propose.add_argument('--key', required=True)
    edit = sub.add_parser('edit')
    edit.add_argument('--cart', required=True)
    edit.add_argument('--input', required=True)
    edit.add_argument('--revision', required=True, type=int)
    for name in ('review', 'approve', 'checkout-link', 'revoke', 'audit'):
        command = sub.add_parser(name)
        command.add_argument('--cart', required=True)
        if name in ('approve', 'checkout-link'):
            command.add_argument('--fingerprint', required=True, help='the exact fingerprint shown during human review')
    args = parser.parse_args(argv)
    try:
        if args.command == 'init-tokens':
            path = Path(args.out)
            path.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'w') as target:
                json.dump({'agent_token': secrets.token_urlsafe(32), 'human_token': secrets.token_urlsafe(32)}, target)
            print(json.dumps({'created': str(path), 'notice': 'Keep the human token out of the agent runtime. Existing files are never overwritten.'}))
            return 0
        store, provider, planner = runtime(args.db)
        if args.command == 'serve':
            tokens = json.loads(Path(args.tokens).read_text())
            server = make_server(('127.0.0.1', args.port), store, provider, planner, tokens)
            print(json.dumps({'listening': f'http://127.0.0.1:{server.server_port}', 'payment_mode': provider.mode, 'agent_mode': planner.mode, 'capture_implemented': False}), flush=True)
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass
            finally:
                server.server_close()
            return 0
        if args.command == 'demo':
            if provider.mode != 'mock' or planner.mode != 'mock':
                raise ConfigurationError('The demo is synthetic and only runs with both modes set to mock.')
            draft = json.loads(Path(args.input).read_text())
            cart = store.create(draft, 'demo_' + secrets.token_hex(12))
            blocked = False
            try:
                store.checkout(cart['id'], cart['fingerprint'], provider)
            except ConsentError:
                blocked = True
            store.approve(cart['id'], cart['fingerprint'])
            first = store.checkout(cart['id'], cart['fingerprint'], provider)
            changed = deepcopy(draft)
            changed['shipping']['address']['postal_code'] += '-changed'
            updated = store.update(cart['id'], changed, cart['revision'])
            stale_blocked = False
            try:
                store.checkout(cart['id'], cart['fingerprint'], provider)
            except ConsentError:
                stale_blocked = True
            store.approve(cart['id'], updated['fingerprint'])
            second = store.checkout(cart['id'], updated['fingerprint'], provider)
            assert blocked and stale_blocked and first['order_id'] != second['order_id']
            output = {'mode': 'mock', 'ai_used': False, 'synthetic_human_for_demo': True,
                      'unapproved_blocked': blocked, 'address_change_revoked_approval': stale_blocked,
                      'new_approval_new_order': first['order_id'] != second['order_id'],
                      'capture_implemented': False, 'events': store.audit(cart['id'])}
        elif args.command == 'draft':
            output = store.create(json.loads(Path(args.input).read_text()), args.key)
        elif args.command == 'propose':
            proposal = planner.propose(args.goal, json.loads(Path(args.context).read_text()))
            output = {'cart': store.create(proposal['draft'], args.key),
                      'proposal': {key: value for key, value in proposal.items() if key != 'draft'}}
        elif args.command == 'edit':
            output = store.update(args.cart, json.loads(Path(args.input).read_text()), args.revision)
        elif args.command == 'review':
            output = store.get(args.cart)
        elif args.command == 'approve':
            output = store.approve(args.cart, args.fingerprint)
        elif args.command == 'checkout-link':
            output = store.checkout(args.cart, args.fingerprint, provider)
        elif args.command == 'revoke':
            output = store.revoke(args.cart)
        else:
            output = {'events': store.audit(args.cart)}
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0
    except (ConfigurationError, ConsentError, ProviderError, OSError, ValueError) as exc:
        print(json.dumps({'error': type(exc).__name__, 'message': str(exc)}), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
