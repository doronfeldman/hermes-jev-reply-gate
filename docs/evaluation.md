# Evaluation status

The implementation has offline behavioral tests and synthetic host integration. Mocked
labels prove policy handling, not model accuracy. The six historical English/Hebrew
benchmark cases in `benchmarks/` are preserved as a small, easy synthetic sample. They
are not a basis for claiming a calibrated 0.95 suppression threshold.

The initial rollout must use shadow mode with the participants' knowledge. Evaluate
representative requests, human chatter, ambiguous short replies, Hebrew follow-ups,
multi-person attribution and busy-turn interactions. Label whether a response was
actually wanted, then compare each `would_ignore` outcome against that label. A missed
assistant request is the principal error to minimize. Report denominator and false-ignore
counts, not only aggregate accuracy or Jev's distribution concentration (`confidence`).

Do not publish private conversation text or IDs in evaluation artifacts. Decision logs
contain only mode, model, action, probabilities, reason and elapsed milliseconds through
Hermes logging. The classifier receives the scoped conversation content and request-local
speaker labels; it never receives routing IDs, API keys in state, or tool payloads.

Measure real end-to-end added delay on this implementation before making latency claims.
The historical benchmark used a persistent client, while this version uses request-local
clients for lifecycle correctness. Eight synthetic live requests through the actual client were checked: mean 0.321 seconds, median 0.282 seconds, and eight expected labels. See [verification](verification.md). These measure client calls, not full gateway latency or production accuracy. A representative shadow observation period and suppression rollout remain outstanding.

API contract checked against the [official TypeSafe API reference](https://docs.typesafe.ai/api)
on October 2, 2026: direct `/v1/systemone` choice request; returned pinned model, choice,
confidence and three-label probability distribution. The implementation rejects malformed
or inconsistent answers rather than interpreting their text as a decision.
