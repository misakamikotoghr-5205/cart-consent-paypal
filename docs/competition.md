# PayPal AI Hackathon — candidate assessment

Checked 2026-11-04 against the [official rules](https://paypalaihackathon.devpost.com/rules), [FAQ](https://paypalaihackathon.devpost.com/details/faqs), [schedule](https://paypalaihackathon.devpost.com/details/dates), and [PayPal announcement](https://developer.paypal.com/community/blog/PayPal_AI_Hackathon/).

| Question | Verified finding |
| --- | --- |
| Still open? | Submission closes **2026-11-12 at 12:00 PST = 20:00 UTC = 2026-11-13 at 04:00 China Standard Time**. |
| Format | Online. A runnable repository with complete instructions can satisfy demo access; hosting is optional. |
| Mainland-China individual | Adults may enter individually. Mainland China is not explicitly named in the rules' excluded locations; legal/prize restrictions still apply. This is not a personal eligibility determination. The FAQ separates account availability from eligibility. |
| Required technologies | Meaningful use of PayPal's free sandbox plus an AI tool/model/platform. A mock-only recording does not establish this integration. |
| New work | New projects, or pre-existing projects significantly advanced during the submission window, are allowed. This independent project was created during that window. |
| Reuse | Licensed open source may be used when the entry adds functionality; third-party rights and licenses must be respected. |
| Deliverables | English description/instructions, functional demo access, a public repository with a visible open-source license, and a public YouTube demonstration under three minutes. |

Read the full rules for exclusions, ownership, conflicts, and organizer discretion. We have not registered, accepted terms for the user, submitted a project, or uploaded a video. PayPal's [REST guide](https://developer.paypal.com/api/rest/) additionally requires a Business account for testing outside the US; actual authorized sandbox access remains an operator dependency.

## Differentiated build

Cart Consent focuses on consent drift: a model proposes goods, but a human approves the exact basket. Budget, currency, items/prices, shipping, address, merchant, and payment mode are bound to one reviewed fingerprint. Every critical change revokes local approval; stale or over-budget baskets cannot receive a link. This is separate from paid-content generation or generic payment-tool wrappers.

## Submission readiness

- Implemented: runnable CLI/API, offline mock demo, separate agent/human capabilities, persistent approval/checkout attempt ledger, change and race invalidation, sandbox Orders adapter, optional constrained Ollama planner, MIT license, and tests.
- Not yet evidenced: an authorized remote PayPal sandbox order creation and a real Ollama inference reviewed by the entrant. No live or sandbox checkout/capture was executed here.
- Still needed before claiming an entry satisfies the theme: configure and demonstrate both real adapters, review model output and actual sandbox responses, record the English demo, and complete the user's own registration/submission. Do not claim that local mocks are remote integration evidence.
