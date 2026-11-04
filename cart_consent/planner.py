"""AI proposes catalog selections only; neither addresses nor payment tools reach it."""
import json
import os
from urllib.parse import urlsplit

from .domain import CATALOG, SHIPPING, ConsentError, ConfigurationError, keys, integer, normalize_cart
from .providers import JsonTransport


class Planner:
    def __init__(self, environ=None, transport=None, catalog=None):
        env = os.environ if environ is None else environ
        self.mode = env.get('CART_AGENT_MODE', 'mock')
        self.model = env.get('OLLAMA_MODEL', '')
        self.url = env.get('OLLAMA_URL', 'http://127.0.0.1:11434/api/chat')
        self.transport, self.catalog = transport or JsonTransport(), catalog or CATALOG
        if self.mode not in ('mock', 'ollama'):
            raise ConfigurationError('Unknown agent mode; no automatic fallback is allowed.')
        if self.mode == 'ollama':
            parsed = urlsplit(self.url)
            if not self.model or parsed.scheme != 'http' or parsed.hostname not in ('127.0.0.1', 'localhost') or parsed.path != '/api/chat' or parsed.username or parsed.password or parsed.query or parsed.fragment:
                raise ConfigurationError('Ollama requires an explicit model and a loopback /api/chat URL.')

    def propose(self, goal, context):
        if not isinstance(goal, str) or not 1 <= len(goal.strip()) <= 1000:
            raise ConsentError('Goal must contain 1–1,000 characters.')
        keys(context, {'currency', 'budget_minor', 'shipping'})
        # Validate context without passing the private address to the model.
        currency = context['currency']
        validation = normalize_cart(context | {'selections': [{'sku': next(iter(self.catalog)), 'quantity': 1}]}, self.catalog)
        products = [{'sku': sku, 'name': product['name'], 'unit_minor': product['prices'][currency]} for sku, product in self.catalog.items()]
        if self.mode == 'mock':
            sku = 'notebook' if 'notebook' in goal.lower() and 'notebook' in self.catalog else min(products, key=lambda p: (p['unit_minor'], p['sku']))['sku']
            proposal = {'selections': [{'sku': sku, 'quantity': 1}], 'reason': 'Deterministic demonstration selection; no LLM was called.'}
        else:
            schema = {'type': 'object', 'required': ['selections', 'reason'], 'additionalProperties': False,
                'properties': {'selections': {'type': 'array', 'minItems': 1, 'maxItems': 20, 'items': {
                    'type': 'object', 'required': ['sku', 'quantity'], 'additionalProperties': False,
                    'properties': {'sku': {'type': 'string', 'enum': list(self.catalog)}, 'quantity': {'type': 'integer', 'minimum': 1, 'maximum': 20}}}},
                    'reason': {'type': 'string'}}}
            payload = {'model': self.model, 'stream': False, 'format': schema, 'options': {'temperature': 0},
                'messages': [{'role': 'system', 'content': 'Propose a shopping basket using only the catalog SKUs and quantities. Stay within the stated budget including shipping. You have no approval, payment, checkout, or external tools. Return the requested JSON only.'},
                    {'role': 'user', 'content': json.dumps({'goal': goal, 'currency': currency, 'budget_minor': context['budget_minor'],
                        'shipping_minor': validation['totals']['shipping_minor'], 'catalog': products})}]}
            result = self.transport.post(self.url, json.dumps(payload).encode(), {'Content-Type': 'application/json'})
            try:
                proposal = json.loads(result['message']['content'])
            except (KeyError, TypeError, ValueError) as exc:
                raise ConsentError('The model did not return a structured shopping proposal; no draft was created.') from exc
        keys(proposal, {'selections', 'reason'})
        if not isinstance(proposal['reason'], str) or not 1 <= len(proposal['reason']) <= 2000:
            raise ConsentError('Invalid proposal reason.')
        draft = context | {'selections': proposal['selections']}
        normalized = normalize_cart(draft, self.catalog)
        if normalized['totals']['total_minor'] > normalized['budget_minor']:
            raise ConsentError('Proposed basket exceeds the budget including shipping; no draft was created.')
        return {'draft': draft, 'explanation': proposal['reason'], 'agent_mode': self.mode,
                'ai_used': self.mode == 'ollama', 'model': self.model if self.mode == 'ollama' else None,
                'approval_granted': False}
