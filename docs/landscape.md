# Existing work, licenses and differentiation

Research date: 2026-11-04. Source README and LICENSE files were inspected at the commits below. No external repository was installed, executed, forked, or copied into this project.

| Reference | Already exists | Our narrower difference / gap |
| --- | --- | --- |
| [PayPal Agent Toolkit](https://github.com/paypal/agent-toolkit/blob/a3aa963960caf32912691a759879a8ce7a6018b2/README.md) | PayPal tools for popular agent frameworks/MCP, including order creation, payment and refund operations | We implement a policy gate around a reviewed basket, with separate human capabilities, changed-field invalidation and no payment/capture tools. We do not replace the toolkit's broader functionality or claim its tools are unsafe. |
| [Google AP2](https://github.com/google-agentic-commerce/AP2/blob/e1ea56db72a6385bce3e5c1112b3a56ce60acb43/README.md), [Checkout Mandate](https://github.com/google-agentic-commerce/AP2/blob/e1ea56db72a6385bce3e5c1112b3a56ce60acb43/docs/ap2/checkout_mandate.md) | Agent-commerce consent and cryptographic checkout/payment mandates, with direct and delegated flows | Exact consent binding is established work. Our hash and role-token ledger are a small local implementation of that design concern, **not AP2-compatible signed mandates**. We lack AP2 credentials, signatures, trust surfaces and interoperable merchant verification. |
| [Ollama](https://github.com/ollama/ollama/blob/e9fde36d75fea66579d84099956ce1430792737a/README.md) | Local model serving and structured JSON output | We consume the documented local API only to propose SKU/quantity selections. No model weights/runtime are bundled, no AI quality claim is based on mock selection, and no payment authority is passed to the model. |

## Pinned source and licenses

| Repository | Commit | Inspected license | Use |
| --- | --- | --- | --- |
| `paypal/agent-toolkit` | `a3aa963960caf32912691a759879a8ce7a6018b2` | [Apache-2.0](https://github.com/paypal/agent-toolkit/blob/a3aa963960caf32912691a759879a8ce7a6018b2/LICENSE) | Design/API comparison, no copied code or MCP package dependency |
| `google-agentic-commerce/AP2` | `e1ea56db72a6385bce3e5c1112b3a56ce60acb43` | [Apache-2.0](https://github.com/google-agentic-commerce/AP2/blob/e1ea56db72a6385bce3e5c1112b3a56ce60acb43/LICENSE) | Design reference for exact informed consent; no protocol code, schemas or artwork copied |
| `ollama/ollama` | `e9fde36d75fea66579d84099956ce1430792737a` | [MIT](https://github.com/ollama/ollama/blob/e9fde36d75fea66579d84099956ce1430792737a/LICENSE) | Optional external API/runtime; model licenses remain separate |

This project's implementation is independent and MIT licensed. Since no third-party code was incorporated, no upstream license text has been relabeled as ours. Reuse later would require preserving applicable license/notice obligations.

## Concrete value and validation

The useful change is the testable boundary between a suggestion and a reviewed transaction: merchant prices and shipping are server-owned; every critical field enters the snapshot; an agent token cannot approve or retrieve a link; expiry, edits, catalog repricing and changes during an upstream request fail closed. An exact retry returns the saved link with a stable request ID.

Tests cover every critical-field edit, stale/expired/revoked approvals, over-budget totals, catalog repricing, in-flight mutation, persistence, retry identity, role spoofing, address/audit redaction, structured model proposal validation, and the official OAuth/Orders request contract. The demo proves local invariants without any real PayPal operation. It does not prove remote order cancellation, model quality, cryptographic human identity, production security or a completed purchase.
