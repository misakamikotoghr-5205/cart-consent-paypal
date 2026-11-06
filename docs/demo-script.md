# Demo recording outline — under three minutes

Use English narration and fictional data. Do not reveal role tokens, sandbox secrets, access tokens, or real addresses. No video has been recorded or uploaded by this repository.

1. **0:00–0:20:** “A basket changed after approval. Should an AI shopper still be allowed to check out?” Show the purpose and the fact that no capture operation exists.
2. **0:20–0:50:** Run the configured Ollama proposal command. Show the selected catalog items, `ai_used=true`, and that status remains `DRAFT`. If no model was actually run, label this portion as a mock and do not claim AI integration is demonstrated.
3. **0:50–1:20:** Use the human review command to see the complete basket and address. Show that the agent role gets 403 for approval. Approve the exact reviewed fingerprint.
4. **1:20–1:55:** Change shipping or the postcode. Attempt the old fingerprint and show 409. Review the changed field names in the audit without exposing address values.
5. **1:55–2:30:** Reapprove the new snapshot and, only with authorized sandbox configuration, create its sandbox order link. Do not capture or open the buyer checkout automatically. Clearly distinguish real sandbox creation from the mock link demo.
6. **2:30–2:50:** Show passing local tests and state the boundaries: local consent gate, no AP2 certification, no capture, no remote cancellation claim.

For offline evaluation use `python3 -m cart_consent demo` or `scripts/api_demo.py`; both disclose synthetic consent and no actual AI/payment. A competition video should separately evidence the actual configured AI and sandbox integrations before claiming the required technology usage.

## Actual local-model evidence, 2026-11-06

`docs/evidence/local-model-20261106.json` now preserves real production-adapter
requests to local `qwen2.5:0.5b`, not test doubles. A short one-pen-set request
returned in 21.350 seconds, passed the known-SKU/quantity/budget checks, and was
persisted as unapproved `DRAFT` in a temporary database. Its total was 1,398 minor
units including shipping. The earlier timeout, rejected over-budget proposal,
and later 90-second timeout remain disclosed. The accepted response is narrow
evidence, not a general quality benchmark.

This JSON is not a video or a PayPal sandbox record. Reproduce the actual model
segment when recording; retain the distinction between the model proposal and
human consent, and complete authorized sandbox setup before narrating a real
order link. Nothing in this run contacted PayPal, checked out or captured funds.
