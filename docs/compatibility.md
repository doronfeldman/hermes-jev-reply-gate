# Compatibility and ownership

The standalone plugin is implemented against the unreleased generic Hermes ingress
extension developed from Hermes **0.21.5, `34f8ec3b407e50bad3ae27e4cd79d65212061356`**.
That base commit alone is unsupported. The required capability is
`PluginContext.register_ingress_policy(async_callback)` plus `on_unload` and scoped
`get_config`. There is no fallback to Telegram native handlers or a downstream hook.
The matching host change must be reviewed and installed before live use; these tests do
not establish compatibility with arbitrary future Hermes releases.

The host invokes `callback(request)` for authorized ordinary group text with complete,
bounded prior context. Its immutable request exposes:

| Field | Meaning |
| --- | --- |
| `platform` | Normalized string; initial plugin scope is `telegram` |
| `chat_id` | Scope filter only; never included in classifier state |
| `session_key` | Canonical profile/session routing key; local coordination only |
| `message_id` | Current event identity; host idempotency only |
| `text` | Complete current text with canonical `[name\|id]` attribution |
| `history` | Chronological tuple of immutable `role`, `content` entries; excludes current event |
| `reply_expected` | Exactly `False` for ordinary text; `True` or unknown bypasses |

The plugin returns only `{"action": "allow"}` or `{"action": "observe"}`. The host
validates the intent and atomically owns observation/continuation, redelivery, generation
changes, cancellation, authorization, pending controls, busy routing and scheduling.
The plugin never writes a transcript, acknowledges a transport event, or owns a second
conversation history. Request-local speaker labels remove valid attribution names and
IDs before classification. Ambiguous attribution fails open. Message bodies themselves
are not anonymized: names or sensitive content naturally written in a message can still
be disclosed to TypeSafe within the configured scope.

Each request owns an async HTTP client and closes it on return or cancellation. This
replaces the plan's pooled client to avoid profile/loop/unload resource reuse. It may cost
connection setup latency; the historical persistent-client benchmark does not measure
this implementation. Pooling should only follow measured need and explicit lifecycle tests.
Requests use the direct pinned API endpoint, no redirects, retries or ambient proxy
configuration. Bodies are bounded to 16 KiB. Only a recognized maximum-probability
`IGNORE` meeting the configured threshold can produce `observe`, and only in suppression
mode. Errors, missing keys and malformed responses allow normal handling.

Offline verification covers strict settings and API schema, bounded complete context,
English/Hebrew policy plumbing, attribution, A→B→A scoped keys, shadows, runtime disable,
unload, timeouts and cancellation. The opt-in integration suite loads the directory
plugin through the real amended PluginManager and runs the real ingress evaluator into
temporary SQLite, including idempotent replay, restored actual-author authorization,
command/media/addressing bypasses, real clarification/approval/update/slash-confirm state
before and during HTTP, and unpersisted active input. A→B→A tests switch actual homes,
settings, secret files, plugin managers and databases. A synthetic policy exercises a
second normalized platform while the Jev plugin itself remains Telegram-scoped.
Wheel entrypoint imports are tested
outside the checkout. Transport-control and transcript race proofs belong to the host suite.
Actual Telegram delivery, real Jev latency, accuracy and live profile deployment remain
unverified. No Discord/Slack support is claimed.

Run the standalone suite:

```sh
python -m pip install '.[test]'
python -m pytest -q
python benchmarks/verify_results.py
```

Include amended-host integration (otherwise those tests skip explicitly):

```sh
HERMES_TEST_HOST=/path/to/amended-hermes python -m pytest -q
```

Use that host's Python environment with its dependencies installed. Tests isolate a
synthetic profile, replace only external HTTP with `httpx.MockTransport`, and do not
require credentials or a Telegram connection.
