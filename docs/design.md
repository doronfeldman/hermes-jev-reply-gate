# Architecture

The plugin supplies a participation decision before Hermes routes ordinary group
chatter into an agent turn. Hermes retains its existing Telegram connection and
canonical conversation transcript.

```text
Existing Telegram intake
  → Hermes authorization and profile/session resolution
  → Host ingress scheduling and bounded context snapshot
  → Plugin scope check and Jev classification
  → Allow: normal Hermes dispatch
    Observe: host atomically persists context without an agent turn
```

## Why a Hermes patch is required

In the pinned Hermes version, `pre_gateway_dispatch` runs after busy-session routing
can queue or steer a message. Filtering there cannot prevent irrelevant chatter from
interrupting an active turn. Waiting inside a native Telegram handler can delay later
updates and commands; the existing observation helper also lacks the atomic
observe-or-continue contract needed to prevent duplicate handling after errors.

The [generic host patch](../compat/README.md) adds
`PluginContext.register_ingress_policy`. It owns pre-busy scheduling, bounded
read-only context, admission receipts, atomic observations, cancellation, and recovery.
The patch contains no Jev logic. Upstream adoption of that contract would remove the
need to carry a compatibility patch. Upgrades require verification against the actual
host capabilities, not a version-string assumption.

## Plugin responsibilities

`config.py` validates settings; `jev.py` implements the bounded HTTP/schema contract;
`engine.py` projects attributed context and selects an action; `hermes_bridge.py`
connects those pieces to scoped Hermes configuration, credentials, and lifecycle.

Only authorized ordinary text in enabled Telegram groups is eligible. Commands,
explicit addressing, pending controls, media, unknown state, and incomplete context
pass through. The model returns `ANSWER`, `IGNORE`, or `UNCERTAIN`. Only a valid,
maximum-probability `IGNORE` at or above the configured threshold can suppress, and
only in `suppress` mode. Errors and uncertainty permit normal processing.

Shadow mode records the proposed decision and allows normal dispatch. Classification
is disabled until explicitly scoped and enabled. The default threshold is a starting
value, not a measured accuracy guarantee; see [evaluation](evaluation.md).

## Context, concurrency, and lifecycle

Hermes supplies complete recent entries from its canonical transcript, capped at 12
entries and 6000 content characters. The plugin uses request-local speaker aliases
and never sends routing identifiers. Message bodies can still contain personal data.
There is no separate plugin transcript or injected duplicate observation history.

The host preserves per-session arrival order before busy routing while control
messages bypass classification. The default one-second arrival budget includes queue
waits. Once an observation write starts, ownership must settle before continuation:
a possibly committed observation cannot also become a normal agent input.

Settings and scoped credentials are resolved per request. A synchronous guard rechecks
settings and callback generation inside the host's final observation boundary, after
awaits. Disable, unload, and profile switches must not leave active stale decisions.
The client is request-local, cancellation-safe, and bounded; it performs no retries,
redirects, or ambient proxy discovery. Pooling would require explicit lifecycle tests
and measured benefit.

See [compatibility](compatibility.md) for the exact request/response contract and
[installation](install.md) for configuration. Telegram is the only supported plugin
transport; the generic host contract does not imply verified Discord or Slack support.
