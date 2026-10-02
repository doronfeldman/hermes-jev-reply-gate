# Hermes Jev Reply Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Astra reviews this plan; no implementation is included in this document.

**Goal:** Build a reusable Jev reply gate and a working Hermes Telegram integration that preserves normal requests and prevents confident ignored chatter from starting or steering agent turns.

**Architecture:** A transport-independent classifier/policy engine connects to a proposed generic Hermes ingress extension. Hermes owns the existing connection, scheduling, update admission, profile secrets, session identity, and authoritative transcript. The host extension is a prerequisite for live shadow and suppression integration; it is not available on the pinned version. See the [Astra review](../../astra-review.md).

**Tech Stack:** Python 3.11+, asyncio, httpx, pytest/pytest-asyncio; Telegram SDK supplied by Hermes. The initial compatibility target is Hermes 0.21.5, commit `34f8ec3b407e50bad3ae27e4cd79d65212061356`, not the developer machine's newer checkout.

**Spec:** [Approved behavioral design](../../design.md), with the implementation amendment recommended in the [Astra review](../../astra-review.md). The shared-host extension and this plan await user review; this amendment proposes replacing the native Telegram binding, subject to user approval.

## Global Constraints

- Default disabled, mode `shadow`, pinned model `jev-1.13.0`, one-second classification budget, ignore probability 0.95; threshold is provisional.
- Context limits: 12 complete messages, 6000 characters, 128 tracked sessions. Empty group allowlist classifies nothing. No plugin-owned inbound conversation buffer; uncertain/unpersisted preceding input means allow.
- Secrets: `agent.secret_scope.get_secret("TYPESAFE_API_KEY")` under the owning Hermes runtime scope; settings: `ctx.get_config` under that same scope. No direct process-environment secret lookup.
- No second Telegram connection, no second durable conversation store, no vendor code in Hermes core, no monkey-patching core adapters.
- Existing sender and group/topic policy is authoritative. Out-of-scope, unauthorized, anonymous, service, and bot-echo content must not reach Jev through this plugin.
- Commands, mentions, bot replies, media, pending clarification/approval/control answers bypass classification.
- Suppress only validated `IGNORE` at or above threshold; errors, uncertainty, unavailable context, oversized latest messages, and exhausted budgets pass normally.
- Shadow mode must preserve existing dispatch, transcript, admission/retry, and acknowledgment semantics, apart from documented classification latency.
- Suppression must preserve a message through Hermes before stopping its normal dispatch; use message identity, not content, for deduplication.
- No message bodies, participant/group IDs, secrets, or raw HTTP bodies in plugin logs. Diagnostics use Hermes's scoped logging and rotation.
- Telegram is the first end-to-end transport test, not a plugin-specific integration module. No platform is advertised as supported until its real ingress path passes the host-contract suite.
- Deployment remains scoped to the requested profile/group and shadow mode. No real Telegram messages, model calls, or key handling during offline tests.

## Review Focus

1. Observation APIs swallow errors or buffer writes: suppression must not turn an uncertain save into message loss or duplicate persistence.
2. PTB processes updates sequentially by default: per-session locks alone do not keep later controls or other groups responsive.
3. A plugin native handler can alter Hermes update-admission receipts even when it returns without suppressing.
4. Reset/compression/active-turn flush can change or overwrite transcript context while a decision is in flight.
5. Factory callbacks run before the main turn scope: credentials, permissions, settings, and teardown must stay with their owning profile across A→B→A execution.

Each focus item has an integration test in Task 1 or Task 4; an unresolved item blocks live shadow and suppression, not merely documentation.

## Files and interfaces

Standalone plugin layout:

| File | Responsibility |
| --- | --- |
| `plugin.yaml`, `__init__.py` | Manifest and `register(ctx)` entry point for the proposed host ingress extension; no classifier/tool surface in the main agent |
| `reply_gate/config.py` | Validated immutable `Settings.from_mapping(mapping)` |
| `reply_gate/types.py` | `GateInput`, `ContextEntry`, `Classification`, `GateDecision` immutable value types |
| `reply_gate/jev.py` | Persistent async `JevClient.classify(state, *, api_key, model, deadline)` and `aclose()` |
| `reply_gate/engine.py` | `ReplyGate.evaluate(event, context, settings, *, api_key, deadline)`; no Hermes/Telegram imports |
| `reply_gate/hermes_bridge.py` | Owning runtime scope, settings/secrets, ingress callback and context projection; requires the approved new host API |
| `tests/test_config.py`, `tests/test_jev.py`, `tests/test_engine.py` | Pure config/API/policy behavior |
| `tests/integration/test_hermes_gate.py`, `tests/integration/test_profiles.py` | Actual pinned Hermes/PTB pipeline and profile-scoping tests |
| `tests/integration/conftest.py` | Temporary profiles/SQLite, fake transport/model endpoint, real Hermes imports |
| `pyproject.toml`, `docs/install.md`, `docs/evaluation.md` | Test/package setup, installation, shadow evaluation and rollback |

`GateInput` carries owning profile/session generation, platform/chat/topic identity, platform message ID, attributed text, and trusted bypass flags. Identity values never enter the Jev state string. `ContextEntry` carries role, attributed content, platform message ID, and generation. `Classification` carries model, label and the three probabilities. `GateDecision` carries `allow`/`would_ignore`/`ignore`, reason, latency, and optional classification.

The bridge exposes `snapshot(event) -> ContextSnapshot`, `is_current(snapshot) -> bool`, and `preserve_observation(event, snapshot) -> ObservationReceipt`. A snapshot identifies the canonical session/generation and bounded transcript content. A receipt must distinguish saved/already-saved from failure without relying on a helper's `None` return. These are proposed host-interface responsibilities, not available methods on the current core. `observe_or_continue(event_identity, generation, decision)` must validate and commit atomically; separate `is_current` then append is insufficient. Context acquisition must be bounded, read-only and must not create/repair sessions. The host converts attribution metadata, including IDs embedded in observed text, to request-local speaker labels before exposing classifier content.

## Task 1: Reproduce host gaps and specify the generic ingress contract

**Files:** Plugin repo `tests/integration/conftest.py`, `tests/integration/test_host_gaps.py`, `docs/compatibility.md`, `docs/host-ingress-contract.md`. Proposed host code families: `gateway/platforms/base.py`, `gateway/run_inbound.py`, `gateway/session_transcript.py`, plugin registration and Telegram update-admission/scheduling modules. Exact new host file placement is set by the approved host contract, not by speculative code in this plugin.

**Consumes:** Approved behavior, Astra's source findings, and pinned Hermes source.

**Produces:** Minimal regression counterexamples and a separately reviewable host contract/design. Live integration remains blocked until the host implementation passes these regressions.

- [ ] Add an offline test bootstrap selecting an existing pinned checkout through `--hermes-source`, setting temporary profile/runtime paths before actual imports. Reject the wrong SHA for gap reproductions; later contract tests also record the amended host SHA.
- [ ] Reproduce `test_native_shadow_changes_retry_receipt` using the real PTB Application/adapter and a downstream core preparation failure. Assert the difference and document it as a gap, not a passing compatibility check.
- [ ] Reproduce `test_sequential_native_gate_delays_controls` through the real application queue with a held classifier, then `/stop` and another group. Do not assume per-session locks alter PTB scheduling.
- [ ] Reproduce `test_failed_observe_then_continue_duplicates_after_recovery`: fail the SQLite append after queue ownership, continue normal dispatch, restore the DB and drain pending observations. This pins the unsafe readback/fallback class.
- [ ] Define the generic host API in `docs/host-ingress-contract.md`: immutable canonical authorized input; bounded read-only snapshot with generation and pending controls; early async decision before busy routing; atomic idempotent observe-or-continue ownership; classification deadline, transport scheduling, cancellation and admission semantics; scoped lifecycle cleanup. No TypeSafe vendor logic in core.
- [ ] Explicitly distinguish cancellable classification/read work from observation commit. Define a safe commit point after which cancellation cannot fall through to dispatch, and before which `continue` leaves no deferred observation. No timed-out worker thread may write later.
- [ ] Specify host tests: control progress while classification is held, shadow admission parity, redelivery once, missing store/SQLite lock/failure, recovery after failed observation, cancel during commit, reset between validation/commit, compression reroute, busy flush preserving observations, bounded read-only snapshots, full canonical auth, and profile A→B→A.
- [ ] Run `pytest tests/integration/test_host_gaps.py -q --hermes-source /path/to/pinned-hermes` and record what was reproduced versus only source-reviewed in `docs/compatibility.md`.
- [ ] Commit gap fixtures and proposed contract; review the host extension before changing Hermes. This prerequisite touches scheduling and persistence ownership and must not be described as a trivial hook patch. If the host extension is declined, only Tasks 2–3/offline evaluation remain deliverable; Tasks 4–5 stay blocked.

## Task 2: Implement configuration and Jev validation

**Files:** `reply_gate/types.py`, `reply_gate/config.py`, `reply_gate/jev.py`, `tests/test_config.py`, `tests/test_jev.py`, `pyproject.toml`.

**Consumes:** Values/types defined in Global Constraints and Files and interfaces.

**Produces:** `Settings.from_mapping`, `JevClient.classify`, `JevClient.aclose`, strict `Classification` validation.

- [ ] Write config tests covering safe defaults, empty groups, malformed modes, bools masquerading as integers, non-finite floats, non-positive limits, and threshold outside `(0.5, 1]`. Run them and confirm missing implementation fails.
- [ ] Implement immutable settings with behavior in YAML only; secret values are not settings fields. Use `settings.telegram.group_ids` as the only initially supported transport allowlist.
- [ ] Write API tests with a fake HTTP endpoint/transport: valid ignore, mismatched model, unknown choice, missing/extra labels, invalid/out-of-range/NaN probabilities, wrong top choice, non-success HTTP, malformed JSON, stalled response, request cancellation. Test round-off tolerance of 0.02 for a three-label probability sum.
- [ ] Implement one persistent `httpx.AsyncClient`; send the direct `/v1/systemone` structured choice request with no retries. Wrap the operation in the caller's remaining overall deadline. Exceptions produce safe failure categories, not raw response/key strings in logs.
- [ ] Verify persistent-client reuse, `aclose()` releasing the transport, and key isolation per request; never mutate shared client's authorization headers across profiles.
- [ ] Run `pytest tests/test_config.py tests/test_jev.py -q`, then commit.

## Task 3: Implement the shared gate engine without a second history

**Files:** `reply_gate/engine.py`, `tests/test_engine.py`.

**Consumes:** Task 2 types/client and an immutable authoritative-context snapshot from the bridge.

**Produces:** `ReplyGate.evaluate(...) -> GateDecision`.

- [ ] Write tests: confident ignore suppresses only in suppress mode; shadow reports `would_ignore`; answer/uncertain/invalid/error allow. Test exactly-at-threshold behavior, latest message already in context, oversized latest message, and no truncation of the latest message.
- [ ] Run tests to establish failure, then implement the policy and bounded chronological attributed context. Exclude tool payloads and keys; retain complete relevant user/assistant entries.
- [ ] Use Hermes transcript snapshots as the sole conversation history. Do not maintain a second accepted-message history. If a preceding unpersisted inbound message could change intent or ordering, conservatively allow rather than invent authoritative context from a plugin queue.
- [ ] Test Hebrew clarification-follow-up examples and human-to-human chatter using a deterministic fake classifier; separately evaluate actual Jev labels later. Unit tests cannot establish model accuracy.
- [ ] Test that engine imports require neither Hermes nor Telegram, demonstrating reuse by a future platform binding.
- [ ] Run `pytest tests/test_engine.py -q`, then commit.

## Task 4: Implement the approved host contract and bind the engine

**Files:** Separate Hermes implementation/tests named by Task 1's approved `docs/host-ingress-contract.md`; plugin `plugin.yaml`, `__init__.py`, `reply_gate/hermes_bridge.py`, integration fixtures/tests. Keep host and vendor-plugin changes in separate commits/repos.

**Consumes:** User-approved Task 1 host contract, Task 2 settings/client, Task 3 engine. A native handler on unmodified Hermes is not an acceptable implementation of this task.

**Produces:** A host ingress extension and real `register(ctx)` ingress-policy callback with proved shadow/suppression semantics; no native Telegram gate handler.

- [ ] Write failing host-contract tests from Task 1, then implement canonical authorization/profile resolution and early decision scheduling before busy routing. Preserve update admission and cancellation. Host-level tests must prove controls and unrelated sessions progress while an ordinary classifier is held.
- [ ] Implement a bounded read-only snapshot API without calling `load_transcript()`, which requests alternation repair internally, or using private plugin SQL, session creation or unbounded full-history reads. Snapshot route/generation and pending-control state.
- [ ] Implement atomic idempotent observe-or-continue in Hermes, preserving busy-turn guards, compression/reset ownership and admission/ACK semantics. Returned `continue` leaves no eventual observation side effect. Run the failure/recovery/cancellation/race suite before wiring a plugin.
- [ ] Write plugin registration tests and register the shared policy callback through the newly approved host API. Refuse unsupported hosts with an actionable compatibility message; never silently fall back to native handlers or the downstream dispatch hook.
- [ ] Implement plugin scope eligibility only after host-provided full canonical authorization and profile ownership. Preserve existing group/topic, sender and bot policy; no copied environment allowlists or display-name authorization. Unknown authority means no Jev disclosure.
- [ ] Bind the owning runtime scope before calling `ctx.get_config`, `get_secret`, transcript APIs or pending-prompt APIs. Settings and handler enablement are checked per message. Use only the new host API for ingress state and lifecycle; do not bridge around it using private adapter/runner methods on older hosts.
- [ ] Use host-provided bypass state for commands/plaintext controls, bot mentions/wake words, direct bot replies, media, any pending clarify/choice, slash confirmation, update prompt or dangerous-command approval. Unknown pending state allows normally. Test canonical shared-group session keys.
- [ ] Project context to request-local speaker labels and test that `[name|user_id]`, raw IDs and sender metadata are absent from Jev payloads while attribution is preserved.
- [ ] Implement per-session coordination bounded by the one-second classification deadline, preserving transport order. Do not evict active coordination state. If all 128 slots are in use, allow immediately rather than create a second lock for one session. Controls do not acquire classifier locks.
- [ ] Recheck runtime enablement, authorization, pending prompts and canonical session generation after the network await, before acting. A reset/profile change/disable while classifying means allow. Handle cancellation without a delayed write or delayed suppression.
- [ ] Shadow returns a non-mutating policy decision to the host, which continues its original processing/admission path. Suppression returns an ignore intent; only Hermes commits the observation and stops normal routing. Do not call private adapter observation/ACK methods from the plugin.
- [ ] Implement unload/force-reload behavior: make retained callbacks inert, cancel owned work, and close HTTP resources on the owning event loop using Hermes lifecycle APIs. Test no active callback survives a disabled generation and no client/task leaks across A→B→A.
- [ ] Emit scoped structured decision diagnostics without content or identifying IDs. Assert serialized logs contain neither test secrets nor conversation text/IDs.
- [ ] Run the full offline host/plugin suite: real idle/busy integration, redelivery, observation failure/recovery, reset/compression races, cancellation and retry/admission parity. Include a second normalized test transport to prove the callback is platform-independent, without claiming an untested actual transport supported. Commit only after the required host contract passes.

## Task 5: Package, document and validate a usable shadow deployment

**Files:** `README.md`, `docs/install.md`, `docs/evaluation.md`, `docs/compatibility.md`, `pyproject.toml`, plugin manifest and packaging tests.

**Consumes:** Passing implementation and compatibility evidence from Tasks 1–4.

**Produces:** Installable standalone plugin, documented compatibility, reversible scoped shadow rollout, evaluation record.

- [ ] Add installation/load tests using Hermes's real plugin manager and temporary profile, including missing dependencies/config, disable/re-enable and gateway restart. The installed manifest/entry point must match the public repo layout.
- [ ] Document the exact required host version/commit/API contract, standard profile secret placement, settings example, initial shadow mode, one connection/transcript model, logs and rollback. Require the amended host; do not advertise compatibility with unmodified 0.21.5. Report measured end-to-end delay, but do not waive required control/persistence behavior through documentation.
- [ ] Update README status only after import/load and end-to-end tests pass. Preserve historical benchmarks as historical; rerun only when needed for the actual integration measurement.
- [ ] Verify `python benchmarks/verify_results.py`, package install/import and the full relevant suite in the supported interpreter. Inspect tracked files for private IDs, paths, keys and real chat content before publication.
- [ ] Publish the implementation branch/PR to the existing repo; attach any created PR to the task. Do not tag a production-ready release based only on fake endpoints or the six synthetic benchmark cases.
- [ ] Deploy scoped shadow mode to the requested profile/group after the key is present through Hermes's standard secret mechanism. Keep the key out of chat/tool arguments. Verify plugin loading and an authenticated synthetic Jev request without sending a Telegram message.
- [ ] Observe representative English/Hebrew group interactions in shadow mode with the user's knowledge. Evaluate requests, ambiguous follow-ups and ignore candidates; label outcome counts without publishing private content. Do not infer correctness from high Jev confidence.
- [ ] Enable suppression only after the compatibility tests pass and shadow false-suppression results support it. Check standard requests/bypasses and rollback. A short shadow evaluation remains explicitly experimental; do not claim a universal reliability guarantee.

## Execution recommendation

Implement in this session with focused task-level tests, then have Astra review the complete host/plugin change. The components share tight contracts, and the critical uncertainty is host integration. Task 1's host contract requires approval before host changes; no live gate is promised or deployed until Task 4 proves it.

## Plan review status

Astra reviewed the initial plan and recommended a prerequisite generic host extension. The five findings in `docs/astra-review.md` are incorporated: live shadow is blocked as well as suppression; host owns scheduling and atomic observation; snapshots are bounded/read-only; classifier context uses local speaker labels and conservative fallback. This revised implementation approach awaits user review. No product code, regression run, model request or deployment has been performed as part of this plan review.
