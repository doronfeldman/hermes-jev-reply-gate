# Hermes Jev Reply Gate

An experimental design for a Hermes Agent plugin that uses [TypeSafe AI's Jev](https://docs.typesafe.ai/introduction) to decide whether Hermes should participate in an ordinary Telegram group conversation.

**Status: design and benchmark stage. The plugin is not implemented or installable yet.** The scripts here benchmark classification; they do not modify Hermes or Telegram behavior.

## Intended behavior

When group participation without mentions is enabled, a small classifier can distinguish a request for Hermes from conversation between people. Jev chooses `ANSWER`, `IGNORE`, or `UNCERTAIN`; Hermes's main model still produces every actual response.

```text
Incoming Telegram message
  → Check configured group, profile, and sender permissions
  → Pass commands, mentions, bot replies, and clarification answers through
  → Classify ordinary text with Jev and short attributed context
      ANSWER / UNCERTAIN / timeout / error → Normal Hermes processing
      Confident IGNORE                    → Preserve context, stay silent
```

The proposed default is **shadow mode**: record decisions without suppressing messages. Enabling suppression would follow validation on representative conversations, especially follow-ups and Hebrew messages.

## Initial latency measurements

Measured on October 2, 2026 from the same deployment machine, using six synthetic English/Hebrew examples twice per condition. Each request classifies one message; warm-ups are excluded.

| Model | Reasoning effort | Samples | Mean | Median | Range |
| --- | --- | ---: | ---: | ---: | ---: |
| Jev 1.13.0 | N/A | 12 | **0.279 s** | 0.272 s | 0.248–0.333 s |
| GPT-6 Luna | none | 12 | 2.167 s | 1.189 s | 0.905–11.002 s |
| GPT-6 Luna | low | 12 | 1.528 s | 1.277 s | 0.917–4.240 s |
| GPT-6.1 Sol | low | 12 | 2.864 s | 2.895 s | 1.947–3.773 s |
| GPT-6.1 Sol | medium | 12 | 3.461 s | 3.044 s | 2.436–5.893 s |

All conditions returned the expected labels in these 12 samples. These are six easy examples repeated, not a production accuracy evaluation. Jev ran in a separate batch through TypeSafe's direct API; GPT ran through Hermes's Codex OAuth route. Prompts and token counts differ across protocols. These observations are not a general model latency guarantee.

Jev's mean was about 5.5× faster than Luna at low effort and 10.3× faster than Sol at low effort in this run. Its 6,184 measured sample input tokens imply approximately $0.00026 at the documented $0.042 per million input tokens; this is an estimate, not a billing record. See [methodology and reproduction](benchmarks/README.md) and [sanitized results](benchmarks/results/).

## Does this make responses faster?

A sequential gate adds its own latency to messages Hermes answers. Its main benefit is avoiding expensive agent turns for messages Hermes should ignore, and avoiding interruptions from unrelated chatter. Under this run's measurements, an answered message would add roughly 0.28 seconds before the main model begins, assuming similar conditions.

For a simplified cost comparison, let `C_gate` be the classification cost, `C_agent` the average agent-turn cost, and `p_ignore` the fraction suppressed. Filtering saves money when `C_gate < p_ignore × C_agent`. Real-world usefulness also depends on missed requests, context handling, and busy-session behavior.

## Integration design

Hermes exposes native Telegram handler registration and a `pre_gateway_dispatch` hook. A dispatch hook alone does not cover every busy-session path, so the proposed gate runs through an early native Telegram handler. The [design](docs/design.md) covers permissions, ignored-message context, timeouts, and implementation acceptance criteria.

No API keys, private chat messages, group IDs, server addresses, or production configuration are included. Jev receives message content when classification is enabled; configure the scope accordingly.

## Roadmap

- Implement the scoped native Telegram handler and async Jev client.
- Preserve ignored messages as attributed context without launching an agent turn.
- Add shadow-mode decision logging and configurable thresholds/timeouts.
- Test idle and busy sessions, permissions, follow-ups, errors, and profile isolation.
- Validate on representative conversations before enabling suppression.
- Document installation and publish a versioned plugin release after those checks pass.

## Sources

- [Hermes plugins](https://hermes-agent.nousresearch.com/docs/user-guide/features/plugins)
- [Native platform handlers](https://hermes-agent.nousresearch.com/docs/developer-guide/plugins#register-native-platform-handlers-any-platform)
- [Pre-dispatch hook](https://hermes-agent.nousresearch.com/docs/user-guide/features/hooks#pre_gateway_dispatch)
- [Jev API](https://docs.typesafe.ai/api), [models and pricing](https://docs.typesafe.ai/models), and [confidence](https://docs.typesafe.ai/confidence)

MIT licensed. This is an independent experiment, not an official Hermes or TypeSafe integration.
