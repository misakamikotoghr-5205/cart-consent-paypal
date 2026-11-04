import hashlib
import json
import re
from copy import deepcopy

CURRENCIES = {'USD', 'EUR', 'GBP'}  # Every supported example currency has two decimal places.
CATALOG = {
    'notebook': {'name': 'Recycled-paper notebook', 'prices': {'USD': 1299, 'EUR': 1199, 'GBP': 1099}},
    'pen-set': {'name': 'Three refillable pens', 'prices': {'USD': 899, 'EUR': 799, 'GBP': 699}},
    'desk-pouch': {'name': 'Canvas desk pouch', 'prices': {'USD': 1599, 'EUR': 1499, 'GBP': 1299}},
}
SHIPPING = {'standard': {'USD': 499, 'EUR': 499, 'GBP': 399},
            'express': {'USD': 1299, 'EUR': 1199, 'GBP': 999}}


class ConsentError(ValueError):
    pass


class Conflict(ConsentError):
    pass


class Forbidden(ConsentError):
    pass


class ConfigurationError(RuntimeError):
    pass


class ProviderError(RuntimeError):
    pass


def require_role(role, allowed):
    if role not in allowed:
        raise Forbidden('This operation is not available to the authenticated role.')


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def fingerprint(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def keys(value, required, optional=frozenset()):
    if not isinstance(value, dict) or set(value) - set(required) - set(optional) or set(required) - set(value):
        raise ConsentError('Input contains missing or unexpected fields.')


def integer(value, low, high, name):
    if type(value) is not int or not low <= value <= high:
        raise ConsentError(f'{name} must be an integer in {low}..{high}.')
    return value


def normalize_cart(value, catalog=None):
    catalog = CATALOG if catalog is None else catalog
    keys(value, {'currency', 'budget_minor', 'selections', 'shipping'})
    currency = value['currency']
    if not isinstance(currency, str) or currency not in CURRENCIES:
        raise ConsentError('Supported currencies are USD, EUR and GBP; no implicit conversion is performed.')
    budget = integer(value['budget_minor'], 1, 100000000, 'budget_minor')
    selections = value['selections']
    if not isinstance(selections, list) or not 1 <= len(selections) <= 20:
        raise ConsentError('Provide 1–20 catalog selections.')
    items, seen = [], set()
    for selection in selections:
        keys(selection, {'sku', 'quantity'})
        sku = selection['sku']
        if not isinstance(sku, str) or sku not in catalog or sku in seen:
            raise ConsentError('Every selection must have a unique known catalog SKU.')
        quantity = integer(selection['quantity'], 1, 20, 'quantity')
        product = catalog[sku]
        price = integer(product['prices'][currency], 1, 100000000, 'catalog price')
        items.append({'sku': sku, 'name': product['name'], 'quantity': quantity, 'unit_minor': price})
        seen.add(sku)
    shipping = value['shipping']
    keys(shipping, {'method', 'address'})
    method = shipping['method']
    if not isinstance(method, str) or method not in SHIPPING:
        raise ConsentError('Unknown shipping method.')
    required_address = {'full_name', 'address_line_1', 'admin_area_2', 'admin_area_1', 'postal_code', 'country_code'}
    keys(shipping['address'], required_address, {'address_line_2'})
    address = {}
    for key, text in shipping['address'].items():
        if not isinstance(text, str) or not 1 <= len(text.strip()) <= (60 if key == 'postal_code' else 120):
            raise ConsentError('Address fields must contain bounded nonblank text.')
        address[key] = text.strip()
    if not re.fullmatch(r'(?:[A-Z]{2}|C2)', address['country_code']):
        raise ConsentError('country_code must be a two-letter uppercase country code.')
    item_total = sum(item['unit_minor'] * item['quantity'] for item in items)
    shipping_total = SHIPPING[method][currency]
    return {'currency': currency, 'budget_minor': budget, 'items': items,
            'shipping': {'method': method, 'amount_minor': shipping_total, 'address': address},
            'totals': {'items_minor': item_total, 'shipping_minor': shipping_total,
                       'tax_minor': 0, 'total_minor': item_total + shipping_total},
            'merchant': {'name': 'Cart Consent Example Merchant', 'catalog': 'fictional-stationery-v1'}}


def diff_paths(before, after, path=''):
    """Return changed field names, never the address or other sensitive values."""
    if isinstance(before, dict) and isinstance(after, dict):
        result = []
        for key in sorted(set(before) | set(after)):
            child = f'{path}.{key}' if path else key
            result.extend(diff_paths(before.get(key), after.get(key), child))
        return result
    if isinstance(before, list) and isinstance(after, list):
        result = []
        for index in range(max(len(before), len(after))):
            result.extend(diff_paths(before[index] if index < len(before) else None,
                                     after[index] if index < len(after) else None, f'{path}[{index}]'))
        return result
    return [path] if before != after else []


def minor_value(value):
    integer(value, 0, 100000000000, 'amount')
    return f'{value // 100}.{value % 100:02d}'


def catalog_view(catalog=None):
    return {'products': deepcopy(CATALOG if catalog is None else catalog), 'shipping': deepcopy(SHIPPING),
            'currencies': sorted(CURRENCIES), 'notice': 'Fictional catalog prices, not live exchange rates. Taxes are zero in this prototype.'}
