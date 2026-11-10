# PayPal AI Hackathon — build and entry status

Rules checked 2026-11-04 against the [official rules](https://paypalaihackathon.devpost.com/rules), [FAQ](https://paypalaihackathon.devpost.com/details/faqs), [schedule](https://paypalaihackathon.devpost.com/details/dates), and [PayPal announcement](https://developer.paypal.com/community/blog/PayPal_AI_Hackathon/). Actual registration and integration status below is updated to November 10.

| Question | Verified finding |
| --- | --- |
| Deadline | **2026-11-12 at 12:00 PST = 20:00 UTC = 2026-11-13 at 04:00 China Standard Time**. |
| Format | Online. A runnable repository with complete instructions can satisfy demo access; hosting is optional. |
| Mainland-China individual | Adults may enter individually. Mainland China is not explicitly named in the rules' excluded locations; legal/prize restrictions still apply. This is not a personal eligibility determination. The FAQ separates account availability from eligibility. |
| Required technologies | Meaningful use of PayPal's free sandbox plus an AI tool/model/platform. A mock-only recording does not establish this integration. |
| New work | New projects, or pre-existing projects significantly advanced during the submission window, are allowed. This independent project was created during that window. |
| Reuse | Licensed open source may be used when the entry adds functionality; third-party rights and licenses must be respected. |
| Deliverables | English description/instructions, functional demo access, a public repository with a visible open-source license, and a public YouTube demonstration under three minutes. |

Read the full rules for exclusions, ownership, conflicts, and organizer discretion. Event registration was actually verified on **2026-11-09**. The [public demonstration](https://youtu.be/icz2WX1DXZ4) was published November 10 and lasts 138.8 seconds. The technical Devpost draft is saved, including the overview, Story, technology tags, public repository/video and original gallery/cover. Personal feedback has been supplied; final review, the required agreement and Submit remain pending, with no final project receipt. PayPal's [REST guide](https://developer.paypal.com/api/rest/) requires a Business account for testing outside the US. Authorized sandbox access was used for the November 10 run, without implying account availability for every entrant.

## Differentiated build

Cart Consent focuses on consent drift: a model proposes goods, but a human approves the exact basket. Budget, currency, items/prices, shipping, address, merchant and payment mode are bound to one reviewed fingerprint. Every critical change revokes local approval; stale or over-budget baskets cannot receive a link. This is separate from paid-content generation or generic payment-tool wrappers. Approval-bound checkout is established work; this project does not invent a payment protocol.

## Evidence and remaining work

- Implemented: runnable Python CLI/API, offline mock demo, separate agent/human HTTP capabilities, persistent approval/checkout-attempt ledger, change and race invalidation, sandbox Orders adapter, constrained Ollama planner, MIT license and local tests.
- Historical local-model run, **November 6**: a CPU-only `qwen2.5:0.5b` proposal selected one pen set in 21.350 seconds, totaling 1,398 minor units including shipping against a 5,000 budget. It remained unapproved `DRAFT`; no provider call was made. Earlier timeouts and a budget rejection remain in [the evidence](evidence/local-model-20261106.json). This is not a model-quality benchmark.
- Actual combined run, **November 10**: a fresh proposal took **5.899 seconds**, then the developer reviewed the exact fictional snapshot and explicitly approved its fingerprint through the local CLI. Real sandbox OAuth and one Orders request succeeded, returning **`PAYER_ACTION_REQUIRED`**. The existing strict adapter validated the returned representation without code changes. The first attempt stopped at OAuth HTTP 401; correcting duplicated private configuration retained the same cart, fingerprint, approval nonce and persisted request ID. [Sanitized run evidence](evidence/sandbox-model-20261110.json) records the limits; raw success HTTP status was not recorded. A guarded subsequent CLI call returned the cached existing order with zero network calls; this is local replay evidence, not a remote idempotency retest.
- Consent boundary: the actual run was a **developer-operated synthetic demonstration**, not authenticated real-buyer consent. The HTTP role-separation tests are separate mock demonstrations. The returned approval URL was not opened; no buyer login, checkout, authorization, capture, completed purchase or production payment occurred.
- Published video: [Cart Consent | Exact Basket Approval + PayPal Sandbox](https://youtu.be/icz2WX1DXZ4), November 10, **138.8 seconds**. It is an edited walkthrough of sanitized evidence cards and an actual mock-mode terminal shot, with generic synthetic Aria narration and 25 English captions, not a continuous recording. Full audio/video decoding passed; no full manual listening claim. [Metadata](evidence/video-20261110.json).
- Remaining: complete final review and the required agreement, click Submit, then verify a final project receipt. The entrant has supplied the actual personal feedback; no additional experience is inferred. Registration, a repository and a successful local integration run do not themselves submit an entry.

Codex assisted implementation, tests and documentation. Runtime AI is the separately configured local Ollama model; default mocks explicitly report no AI. No AP2 certification, remote order cancellation, real-world tax/address/shipping validation, model-quality benchmark, prize guarantee or commercial security certification is claimed.
