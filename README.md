# Hermes Jev Reply Gate

An experimental Hermes Agent plugin that uses [TypeSafe AI's Jev](https://docs.typesafe.ai/introduction) to decide whether Hermes should participate in an ordinary Telegram group conversation.

**Status: implemented, reviewed, and deployed in scoped shadow mode; requires the [bundled generic Hermes ingress patch](compat/README.md).** Unmodified Hermes 0.21.5 is unsupported. The actual client passed eight synthetic live API checks; suppression remains off pending representative evaluation. See [installation](docs/install.md), [compatibility](docs/compatibility.md), and [evaluation](docs/evaluation.md).

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

The default is **shadow mode**, with classification disabled until explicitly scoped and enabled: record decisions without suppressing messages. Enabling suppression would follow validation on representative conversations, especially follow-ups and Hebrew messages.

## Installation

Apply the [matching Hermes patch](compat/README.md), install the plugin into the
Hermes Python environment with uv, and configure the owning profile's standard
`TYPESAFE_API_KEY` secret plus an explicit group allowlist. Follow the
[installation guide](docs/install.md) for the complete configuration and rollback.
A stock Hermes installation cannot load this plugin yet.

## Development

Use [uv](https://docs.astral.sh/uv/) 0.12.3 or newer. The repo commits its lockfile
and defaults to Python 3.14; CI also checks standalone support on Python 3.11.

```sh
uv sync --locked
uv run --locked ruff check .
uv run --locked pytest -q
uv run --locked python benchmarks/verify_results.py
uv build --no-sources
```

Normal tests are offline and require no API key. Real Hermes integration is a
separate CI job using the pinned host plus the bundled patch. See
[CONTRIBUTING.md](CONTRIBUTING.md) for that setup and [AGENTS.md](AGENTS.md) for
ownership, privacy, testing, and maintenance rules.

Every PR gets offline CI. Paid Jev smoke checks run only for `doronfeldman`-authored,
same-repository PRs triggered by `doronfeldman`; fork and other-author PRs never
receive the key. The key belongs only in the `jev-live` GitHub environment, restricted
to `main`. Each eligible run uses three synthetic requests with no retries. The
trusted live workflow becomes active after this setup reaches `main`.
[CI policy and secret setup](CONTRIBUTING.md#ci-and-paid-api-checks).

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

The plugin registers one policy through `ctx.register_ingress_policy`. Hermes owns authorization, transport scheduling, session identity and atomic observation writes; the plugin supplies the scoped Jev decision. Ignored messages remain in the one authoritative Hermes transcript. The [architecture](docs/design.md) explains the current design and why the host patch is needed; [compatibility](docs/compatibility.md) describes the implemented contract.

No API keys, private chat messages, group IDs, server addresses, or production configuration are included. Jev receives message content when classification is enabled; configure the scope accordingly.

## Roadmap

- Seek upstream support for the generic Hermes host extension.
- Monitor actual gateway latency; eight request-local client smoke calls averaged 0.321 seconds, while historical numbers used a pooled HTTP client.
- Validate representative conversations in scoped shadow mode before suppression.
- Publish a supported release after host and live-rollout checks pass.

## Sources

- [Hermes plugins](https://hermes-agent.nousresearch.com/docs/user-guide/features/plugins)
- [Native platform handlers](https://hermes-agent.nousresearch.com/docs/developer-guide/plugins#register-native-platform-handlers-any-platform)
- [Pre-dispatch hook](https://hermes-agent.nousresearch.com/docs/user-guide/features/hooks#pre_gateway_dispatch)
- [Jev API](https://docs.typesafe.ai/api), [models and pricing](https://docs.typesafe.ai/models), and [confidence](https://docs.typesafe.ai/confidence)

MIT licensed. This is an independent experiment, not an official Hermes or TypeSafe integration.
