# Astra implementation-plan review

Historical design review. The user subsequently approved the shared host extension; see the [implementation verification](verification.md) for the completed review and tests.

Reviewed October 2, 2026 against Hermes 0.21.5, commit `34f8ec3b407e50bad3ae27e4cd79d65212061356`. This was a source/plan review, not a live integration test. No deployed configuration or credentials were changed.

## Recommendation

Build a generic Hermes ingress extension first, then connect the transport-independent Jev plugin. The proposed native Telegram handler cannot meet the approved shadow, control responsiveness, and observation guarantees on the inspected host. This changes the implementation approach, not the user's single-stream/single-transcript requirement. The extension is a prerequisite requiring design approval; it is not an existing Hermes API or a trivial promised patch.

## Findings

1. **P1 — A native plugin handler changes admission semantics, even in shadow mode.** Telegram's `update_admission.py::_admit_callbacks` marks native plugin callbacks accepted before executing them. Returning normally does not preserve the core handler's retry behavior after a preparation failure. Block live native shadow integration as well as suppression.
2. **P1 — A blocking classifier delays controls at the transport queue.** The pinned adapter does not enable PTB concurrent updates. Later `/stop` and unrelated-group updates wait before reaching bypass checks. Per-session classifier locks cannot solve transport scheduling. Hermes must own the scheduling change.
3. **P1 — Persistence readback alone does not make suppression safe.** The observation helper swallows errors, and `append_to_transcript` queues failed writes for recovery. Falling through to normal dispatch after a failed readback can later produce both an observation and a normal-message occurrence. Separate generation validation also races with reset/compression. Hermes needs an atomic idempotent observe-or-continue operation with defined cancellation/failure ownership.
4. **P2 — Existing transcript loading is neither bounded nor strictly read-only.** `load_transcript` loads the whole conversation and asks for alternation repair. A classifier needs a bounded read-only snapshot with route/generation and pending-control state. An asyncio deadline cannot preempt synchronous lock/SQLite work; offloading writes can leave side effects after a timeout.
5. **P2 — Context projection must remove raw identities and avoid a second inbound history.** Existing observed text may embed `[name|user_id]`. Project it to request-local speaker labels before sending it to Jev. If prior unpersisted input makes context/order uncertain, allow normally; do not invent a second authoritative history in the plugin.

## Required host contract

- Canonical authorization and profile resolution before classification or external disclosure.
- An early gate before queueing/steering, with host-owned scheduling that allows controls to progress during an ordinary classification wait.
- Bounded read-only context, pending-interaction state and canonical message/session generation snapshots.
- A host-owned idempotent observe-or-continue operation. A `continue` result must not leave a queued observation that can persist later; stale/cancelled decisions must not commit into a different generation.
- Existing admission/retry, busy-turn persistence, profile isolation and transcript replay contracts remain intact.
- Plugin supplies only configuration, classifier and policy; Hermes owns transport, lifecycle and durable state. No TypeSafe-specific core code.

## Regression evidence to produce

Use actual pinned Hermes/PTB imports, temporary profiles/SQLite and a fake transport/classifier. Check shadow retry parity, stalled classification followed by controls/other groups, write failure then normal dispatch and later recovery, cancellation during observation commit, reset/compression between snapshot and commit, busy-turn flush preserving observations once, and profile A→B→A isolation.

## Alternative

The shared Jev client/engine and offline labeled evaluator can be developed independently. A downstream hook could provide limited shadow evaluation, but it would miss some busy arrivals and would not fulfill the approved live-gate contract. Do not advertise that as a working replacement.

## Source locations

All paths are relative to the pinned Hermes source:

- `hermes_cli/plugins.py::PluginContext.register_platform_handler` — adapter read-only extension contract.
- `plugins/platforms/telegram/update_admission.py::_admit_callbacks` — plugin update admission.
- `plugins/platforms/telegram/adapter.py` — application construction and `_observe_unmentioned_group_message`.
- `gateway/platforms/base.py::handle_message`, `_handle_message_while_active` — busy routing before normal runner admission.
- `gateway/session_transcript.py::append_to_transcript`, `load_transcript` — queued writes, rerouting and repairing reads.
- `gateway/run_inbound.py::_hm_pending_reply_intercepts`, `_hm_estop_turn_allowed` — pending-control bypasses.
- `agent/secret_scope.py::get_secret` — standard scoped credentials.
