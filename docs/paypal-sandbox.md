# Sandbox and AI adapter contracts

Verified against official documentation on 2026-11-04. No credential, OAuth exchange, remote order, buyer checkout, authorization, capture, or model inference was performed while building this repository.

## Configuration, before using the sandbox adapter

PayPal's [REST setup guide](https://developer.paypal.com/api/rest/) describes sandbox app client credentials. It also states that testing integrations outside the US requires a PayPal Business account. Account availability is not established by this repository. Use your authorized account; do not bypass country or onboarding controls.

Use the Developer Dashboard's sandbox app and business seller information. [Sandbox accounts](https://developer.paypal.com/sandbox-testing/accounts) distinguish a business seller from a personal buyer. This app only needs the seller's sandbox client credentials and merchant ID to create an order link; it does not log into a buyer or complete checkout.

Set these privately through your environment/configuration system; `.env.example` is a reference, not automatically loaded:

```text
CART_PAYMENT_MODE=paypal-sandbox
PAYPAL_CLIENT_ID=<sandbox app client ID>
PAYPAL_CLIENT_SECRET=<sandbox app secret>
PAYPAL_MERCHANT_ID=<13-character sandbox business merchant ID>
PAYPAL_RETURN_URL=<your HTTPS return URL>
PAYPAL_CANCEL_URL=<your HTTPS cancel URL>
```

There is no live/production mode and no configurable PayPal gateway. A real-mode cart belongs to the configured sandbox merchant and cannot reuse an approval created in mock mode. Callback pages are supplied by the operator; this prototype does not treat a return URL as proof of payment or implement a capture callback.

## Exact outbound surface

1. [OAuth](https://developer.paypal.com/api/rest/authentication/): `POST https://api-m.sandbox.paypal.com/v1/oauth2/token`, HTTP Basic client authentication, form body `grant_type=client_credentials`. Access tokens stay in process memory and are not logged or persisted.
2. [Create order](https://developer.paypal.com/api/orders/v2/orders-create): `POST https://api-m.sandbox.paypal.com/v2/checkout/orders`, bearer token, persisted `PayPal-Request-Id`, `Prefer: return=representation`. One purchase unit carries the reviewed `reference_id`, fingerprint in `custom_id`, explicit payee, item/shipping amount breakdown, quantities, and supplied shipping address. `payment_source.paypal.experience_context` uses `SET_PROVIDED_ADDRESS` and `CONTINUE`.

`intent=CAPTURE` describes the order type; this program has **no** capture request or endpoint. It does not set an auto-complete processing instruction. Nothing automatically opens the returned URL. Redirects are not followed by the HTTP transport, and TLS verification stays enabled.

The response must represent an uncompleted order and exactly match the approved amount, item list, address, fingerprint, and merchant. Only matching `approve`/`payer-action` links to an allowed sandbox hostname/path and order token are accepted. This deliberately strict representation check can reject responses with additional normalized fields; inspect and contract-test actual account behavior before changing it. Never relax the bindings merely to make a demo pass.

Before returning a link, the ledger rechecks revision, catalog, approval nonce, fingerprint, and expiry. A change during the network call withholds the URL and records a stale attempt. The remote sandbox order may still exist; local rejection does not claim remote cancellation. Retries retain the same request ID; the provider's own idempotency retention is external to this local ledger.

## Local Ollama AI

The optional planner follows the official [chat API](https://docs.ollama.com/api/chat) and [structured-output guidance](https://docs.ollama.com/capabilities/structured-outputs). It sends `model`, `messages`, `stream=false`, a JSON schema in `format`, and a low-temperature option. It does not supply tools. Only loopback `/api/chat` endpoints are accepted, and that transport disables environment proxies. The sandbox payment transport retains environment proxy support. Structured shipping-address fields are omitted from model messages, but the free-text goal is sent unchanged; do not include addresses, personal information, tokens, or other secrets in it. No arbitrary-text privacy filter or redaction is promised. Model name and model licensing are the operator's explicit configuration, not an implicit download.

The [2026-11-06 real local-model record](evidence/local-model-20261106.json)
includes a valid unapproved pen-set draft, two observed timeouts and a prior
budget rejection. The installed model was `qwen2.5:0.5b`; all inputs were shipped
fictional examples. This provides local proposal evidence only. The PayPal
sandbox OAuth/order path has not been called with real account credentials.

## Verification boundary

`python3 scripts/verify.py` runs domain, race, persistence, role-authentication, CLI, and adapter contract tests. Transport doubles check the official OAuth/Orders request fields and reject wrong amount, item, merchant, address, fingerprint, URL, or completed status. Model doubles check constrained output and omission of structured shipping-address fields; intercepted transport tests verify that environment proxies cannot reroute local-model requests while remaining available for sandbox requests. These are offline contract tests, not a successful PayPal sandbox integration or a real model quality evaluation.
