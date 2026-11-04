"""Synthetic role-switch demonstration against an explicitly local mock server."""
from copy import deepcopy
import json
from pathlib import Path
import uuid
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
BASE = 'http://127.0.0.1:8768'


def main():
    tokens = json.loads((ROOT / 'var' / 'roles.json').read_text())

    def call(path, role='agent', data=None, method=None, headers=None):
        request = Request(BASE + path, data=None if data is None else json.dumps(data).encode(), method=method,
                          headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + tokens[role + '_token']} | (headers or {}))
        try:
            response = urlopen(request, timeout=10)
        except HTTPError as exc:
            response = exc
        with response:
            return response.status, json.loads(response.read())

    _, health = call('/health')
    if health['payment_mode'] != 'mock' or health['agent_mode'] != 'mock':
        raise SystemExit('This synthetic demonstration only runs with both modes set to mock.')
    draft = json.loads((ROOT / 'examples' / 'cart.json').read_text())
    status, body = call('/v1/carts', data={'draft': draft}, headers={'Idempotency-Key': 'api_demo_' + uuid.uuid4().hex})
    assert status == 201
    cart = body['cart']
    path = '/v1/carts/' + cart['id']
    expected = {'expected_fingerprint': cart['fingerprint']}
    assert call(path + '/approve', data=expected)[0] == 403
    assert call(path + '/checkout-link', 'human', expected)[0] == 409
    assert call(path + '/approve', 'human', expected)[0] == 200
    assert call(path + '/checkout-link', 'human', expected)[0] == 200
    changed = deepcopy(draft)
    changed['shipping']['method'] = 'express'
    assert call(path, data={'draft': changed, 'expected_revision': 1}, method='PATCH')[0] == 200
    assert call(path + '/checkout-link', 'human', expected)[0] == 409
    print(json.dumps({'mode': 'mock', 'synthetic_role_switch': True, 'agent_approval_blocked': True,
                      'unapproved_link_blocked': True, 'shipping_change_revoked_approval': True,
                      'real_money': False, 'capture_implemented': False}, indent=2))


if __name__ == '__main__':
    main()
