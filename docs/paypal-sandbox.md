# Sandbox and AI adapter contracts

The contracts were checked against official documentation on 2026-11-04. Real local-model evidence was recorded on November 6, followed by a fresh model proposal and authorized sandbox OAuth/order creation on **2026-11-10**. The latter was a developer-operated synthetic demonstration, with no buyer checkout, authorization, capture or production payment.

## Configuration, before using the sandbox adapter

PayPal's [REST setup guide](https://developer.paypal.com/api/rest/) describes sandbox app client credentials. It also states that testing integrations outside the US requires a PayPal Business account. Authorized sandbox access was available for the November 10 run; this does not establish account availability for every reader. Use your authorized account; do not bypass country or onboarding controls.

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
fictional examples. This historical run provides local proposal evidence only;
it did not contact the payment provider.

## Actual combined run, 2026-11-10

The [sanitized run record](evidence/sandbox-model-20261110.json) records a fresh
Ollama 0.40.15 / `qwen2.5:0.5b` proposal in 5.899 seconds. It selected one pen set
and initially persisted an unapproved `DRAFT`: USD 8.99 item + USD 4.99 shipping =
USD 13.98, below the USD 50.00 budget. The developer inspected the complete
fictional snapshot and explicitly supplied its exact fingerprint to the local
approval command. This CLI operator controls the local ledger; the run does not
authenticate a real buyer or demonstrate the HTTP role boundary.

The first checkout attempt failed at OAuth with HTTP 401, before any Orders
request. After duplicated private configuration was corrected, the same cart,
fingerprint, approval nonce and saved request ID were retained. The real sandbox
Orders response was `PAYER_ACTION_REQUIRED`. The original strict adapter accepted
the amount, items, shipping, merchant, `custom_id`, `reference_id`, order ID and
approved snapshot hash without code changes. One remote Orders request was made;
the successful checkout CLI invocation took 1.369 seconds. Its raw success HTTP
status was not recorded, so none is asserted here. Credentials, merchant/order
identifiers and approval URLs remain private.

The approval link was returned but not opened. `intent=CAPTURE` was an order
field, not an executed capture. No buyer login, checkout, authorization, capture,
completed purchase, remote cancellation or production payment was demonstrated.
A post-success checkout CLI probe, with network access guarded, returned the
cached existing order and `replayed=true` with zero network calls. This verifies
local cached replay, not another remote order or a remote idempotency test.
This is sanitized operator-held run evidence, not independent certification.

## Published demonstration

[Cart Consent | Exact Basket Approval + PayPal Sandbox](https://youtu.be/icz2WX1DXZ4) was published on November 10, 2026. The 138.8-second video combines edited sanitized run-evidence cards with an actual mock-mode native terminal shot. It is not continuous footage. It uses generic synthetic Aria narration and 25 burned-in English captions. Full audio/video decoding passed; full manual audio listening is not claimed. [Public video metadata](evidence/video-20261110.json) records the local upload source size and hash. This publication does not submit the project: Start project / CAPTCHA still awaits the current consent/action, with no formal project receipt.

## Verification boundary

`python3 scripts/verify.py` runs domain, race, persistence, role-authentication, CLI, and adapter contract tests. Transport doubles check the official OAuth/Orders request fields and reject wrong amount, item, merchant, address, fingerprint, URL, or completed status. Model doubles check constrained output and omission of structured shipping-address fields; intercepted transport tests verify that environment proxies cannot reroute local-model requests while remaining available for sandbox requests. These remain offline contract tests. The separate dated November 10 record supplies narrow real integration evidence; neither the tests nor that single run establish model quality, real-buyer consent or production payment readiness.
