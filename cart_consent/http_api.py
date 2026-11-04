import hmac
import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from .domain import ConfigurationError, ConsentError, Conflict, Forbidden, ProviderError, catalog_view, keys


def make_server(address, store, provider, planner, tokens):
    keys(tokens, {'agent_token', 'human_token'})
    if any(not isinstance(value, str) or len(value) < 32 for value in tokens.values()) or tokens['agent_token'] == tokens['human_token']:
        raise ConfigurationError('Two distinct private role tokens of at least 32 characters are required.')

    class Handler(BaseHTTPRequestHandler):
        server_version = 'CartConsent/1.0'

        def setup(self):
            super().setup()
            self.connection.settimeout(10)

        def log_message(self, *_args):
            pass  # No tokens, URLs, model prompts, payment responses, or addresses in request logs.

        def send_json(self, status, data):
            raw = json.dumps(data, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(raw)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            self.wfile.write(raw)

        def role(self):
            authorization = self.headers.get('Authorization', '')
            if not authorization.startswith('Bearer '):
                raise Forbidden('A Bearer role token is required.')
            value = authorization.removeprefix('Bearer ')
            for role in ('agent', 'human'):
                if hmac.compare_digest(value, tokens[role + '_token']):
                    return role
            raise Forbidden('A valid role token is required.')

        def body(self):
            if self.headers.get('Transfer-Encoding') or len(self.headers.get_all('Content-Length', [])) != 1 or self.headers.get_content_type() != 'application/json':
                raise ConsentError('Send a bounded JSON body with one Content-Length header.')
            try:
                length = int(self.headers['Content-Length'])
                if not 1 <= length <= 65536:
                    raise ValueError()
                value = json.loads(self.rfile.read(length))
                if not isinstance(value, dict):
                    raise ValueError()
                return value
            except (ValueError, UnicodeError):
                raise ConsentError('Invalid or oversized JSON object.') from None

        def dispatch(self):
            path = urlsplit(self.path).path
            if self.command == 'GET' and path == '/health':
                return self.send_json(200, {'status': 'ok', 'payment_mode': provider.mode, 'agent_mode': planner.mode, 'capture_implemented': False})
            role = self.role()
            if self.command == 'GET' and path == '/v1/catalog':
                return self.send_json(200, catalog_view(store.catalog))
            if self.command == 'POST' and path == '/v1/proposals':
                data = self.body()
                keys(data, {'goal', 'context'})
                proposal = planner.propose(data['goal'], data['context'])
                cart = store.create(proposal['draft'], self.headers.get('Idempotency-Key'), role)
                return self.send_json(201, {'cart': cart, 'proposal': {key: value for key, value in proposal.items() if key != 'draft'}})
            if self.command == 'POST' and path == '/v1/carts':
                data = self.body()
                keys(data, {'draft'})
                return self.send_json(201, {'cart': store.create(data['draft'], self.headers.get('Idempotency-Key'), role)})
            match = re.fullmatch(r'/v1/carts/(cart_[a-f0-9]{24})(?:/(approve|checkout-link|revoke|audit))?', path)
            if not match:
                return self.send_json(404, {'code': 'NOT_FOUND'})
            cart_id, operation = match.groups()
            if self.command == 'GET' and operation is None:
                return self.send_json(200, {'cart': store.get(cart_id, role)})
            if self.command == 'GET' and operation == 'audit':
                return self.send_json(200, {'events': store.audit(cart_id, role)})
            if self.command == 'PATCH' and operation is None:
                data = self.body()
                keys(data, {'draft', 'expected_revision'})
                return self.send_json(200, {'cart': store.update(cart_id, data['draft'], data['expected_revision'], role)})
            if self.command == 'POST' and operation in ('approve', 'checkout-link'):
                data = self.body()
                keys(data, {'expected_fingerprint'})
                if operation == 'approve':
                    return self.send_json(200, {'cart': store.approve(cart_id, data['expected_fingerprint'], role)})
                return self.send_json(200, store.checkout(cart_id, data['expected_fingerprint'], provider, role))
            if self.command == 'POST' and operation == 'revoke':
                if self.body() != {}:
                    raise ConsentError('Revoke expects an empty JSON object.')
                return self.send_json(200, {'cart': store.revoke(cart_id, role)})
            return self.send_json(404, {'code': 'NOT_FOUND'})

        def handle_request(self):
            try:
                self.dispatch()
            except Forbidden as exc:
                self.send_json(403, {'code': 'FORBIDDEN', 'message': str(exc)})
            except Conflict as exc:
                self.send_json(409, {'code': 'REVIEW_REQUIRED', 'message': str(exc)})
            except ConsentError as exc:
                self.send_json(400, {'code': 'INVALID_INPUT', 'message': str(exc)})
            except ProviderError as exc:
                self.send_json(502, {'code': 'PROVIDER_UNAVAILABLE', 'message': str(exc)})
            except Exception:
                self.send_json(503, {'code': 'UNAVAILABLE', 'message': 'No checkout link was delivered. Review the current cart and retry safely.'})

        do_GET = handle_request
        do_POST = handle_request
        do_PATCH = handle_request

    return ThreadingHTTPServer(address, Handler)
