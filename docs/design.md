# Proposed integration

Status: behavioral design approved; implementation pending. The host-extension amendment below awaits approval. This describes the intended contract, not current plugin behavior.

## Astra implementation amendment — pending approval

Astra's review of the pinned Hermes source found that the proposed native Telegram handler cannot preserve shadow admission/retry behavior and would block later controls at the transport queue. Existing observation helpers also do not provide an atomic success/continue contract. See the [review](astra-review.md) and [revised implementation plan](superpowers/plans/2026-10-02-reply-gate.md).

The recommendation is a generic Hermes ingress extension: authorize and resolve profile/session identity, take bounded read-only context and pending-control snapshots, invoke the plugin before busy routing under host-owned scheduling, then atomically preserve an ignored event or continue normal processing. A continued event must not leave a queued observation that can persist later. Hermes retains one event stream and one authoritative transcript; Jev remains in the standalone plugin.

This proposes replacing the native Telegram binding and allowing generic host changes, subject to user approval. No live shadow or suppression integration should be built/deployed on the unmodified pinned host. The sections below preserve the originally discussed binding as design history where noted; the approved behavior, scoped credentials and single-transcript requirement remain unchanged.

## First release and Hermes abstractions

Hermes already normalizes inbound traffic into `MessageEvent` with a `SessionSource`, and its platforms share `BasePlatformAdapter`. Its `pre_gateway_dispatch` hook is also platform-independent. However, the hook runs in the runner's normal admission path, after the adapter can already route a busy-session message to queueing or steering. It is not a complete cross-platform early gate.

The original proposal paired a transport-independent engine with a Telegram native binding. The proposed amendment instead connects the engine to the generic host extension above. The engine owns Jev classification, validation, bounded context projection and shadow/suppress policy; Hermes owns authorization, identity, pending controls, scheduling, admission and observation persistence. The engine does not import the Telegram SDK or Hermes internals.

This does not claim working Discord/Slack support: test each actual transport's ingress contract before advertising support. The proposed host extension is vendor-independent; no TypeSafe-specific core code or adapter monkey-patching is permitted.

## Release 0.1 settings and defaults

Use `plugins.entries.hermes-jev-reply-gate.settings` in the owning profile's `config.yaml`:

```yaml
plugins:
  entries:
    hermes-jev-reply-gate:
      enabled: true
      settings:
        enabled: false
        mode: shadow
        model: jev-1.13.0
        timeout_seconds: 1.0
        ignore_probability: 0.95
        context_messages: 12
        context_characters: 6000
        max_sessions: 128
        telegram:
          group_ids: []
```

Plugin loading and reply-gate enablement are separate. Empty groups means no classification. Accept only `shadow` and `suppress` modes; reject invalid settings before registering a handler. The 0.95 threshold is a conservative starting setting, not a measured guarantee. Shadow mode remains the deployment default until representative labeled conversations support suppression.

The amended host must preserve observations in the same canonical session as later triggered turns. A persistence failure may continue normal dispatch only when the host guarantees no queued observation can commit later. Settings are re-read under the owning profile at message time, so disabling the gate makes retained callbacks inert. Restart the gateway after code or secret changes.

Context and session limits must be positive integers; timeout must be finite and positive; ignore probability must be finite in `(0.5, 1]`. Long latest messages that cannot fit the configured context budget pass normally without classification; do not classify truncated instructions. Retain recent complete attributed context entries within the message/character limits and evict idle sessions at `max_sessions`.

Classification is bounded by a one-second overall operation by default, including lock waits. A waiting message passes normally if that budget is exhausted. Each session is serialized for context consistency; other sessions proceed independently. Explicit control messages bypass classification and never wait on its lock.

Only ordinary eligible text is classified. Human bot replies and any pending control interactions bypass it; unknown pending state allows normally. The proposed shared host service runs before busy routing. Shadow mode preserves existing admission/dispatch semantics. In suppression mode Hermes atomically records an eligible confident ignore as an observation and owns the decision to stop normal routing.

Hermes checks its full sender authorization, group/topic, own-bot and bot-to-bot gates before any external request. It resolves the owning profile and canonical session identity before exposing settings, credentials, pending controls or context to the callback. A resolved sender identity is required for classification; ambiguous anonymous/service messages follow normal Hermes handling.

The amended context policy reads a bounded read-only snapshot from the owning Hermes session and projects attribution into request-local speaker labels, removing raw identifiers embedded in observation text. If preceding unpersisted inbound context makes the snapshot insufficient, allow normally instead of creating a second plugin-owned history. Suppressed observations remain in Hermes's transcript path. Shadow decisions create no extra transcript entries.

TypeSafe responses must contain the expected pinned model, a recognized choice, finite probabilities in `[0, 1]` for exactly the three labels, and a probability total consistent with rounded API values. Unexpected or inconsistent responses pass normally. Require `IGNORE` to be the maximum-probability choice as well as to meet the configured threshold.

Log one structured decision record through Hermes logging with mode, model, selected action, probabilities, elapsed milliseconds, and reason. Do not log content, sender IDs, group IDs, credentials, or API response bodies. Use Hermes's log rotation and profile routing. Emit a startup warning when a suppression group cannot preserve observed context; leave that group ungated.

## Scope

Enable the gate explicitly per Hermes profile and Telegram group. Honor the profile's sender authorization before sending content to Jev or adding it to conversational context. Unconfigured profiles, groups, private chats, and unauthorized senders must not be classified.

Use verified Telegram sender identity for permission checks and attribution. Observed-message representations may omit a normal user ID; do not infer authorization from display names. Existing Hermes authorization remains authoritative downstream.

## Placement

The original approach registered an early handler through `ctx.register_telegram_handler(factory)`. Astra's review identified admission and scheduling blockers for that route. The amendment requires a new generic host service before Hermes can queue, steer or interrupt an active session; the host owns observation and suppression rather than the plugin stopping native propagation.

The `pre_gateway_dispatch` hook can skip normal dispatch, but some busy-session paths process incoming messages before reaching that hook. Using it as the only gate could still allow ignored chatter to interrupt an active turn.

Both extension points were inspected against Hermes 0.21.5, commit `34f8ec3b407e50bad3ae27e4cd79d65212061356`. This is a design reference, not a tested compatibility claim. Verify the installed version's APIs before implementation and release.

## Decision policy

1. Apply runtime enablement, profile/group scope, and sender permissions.
2. Pass slash commands, explicit mentions, direct replies to Hermes, and answers to pending clarification prompts to normal Hermes processing.
3. Initially pass media, attachments, and voice messages through unchanged. Jev is text-only.
4. Classify ordinary text using a short chronological conversation with speaker attribution and the latest message clearly identified.
5. Suppress only when the returned choice is `IGNORE` and its probability meets a calibrated threshold. Pass `ANSWER`, `UNCERTAIN`, malformed responses, network failures, and timeouts through normally.

Jev's `confidence` describes concentration in the choice distribution; it is not a calibrated probability that the choice is correct. Choose a suppression threshold from labeled representative examples, with missed assistant requests as the primary failure to minimize. Do not infer a production threshold from six synthetic cases.

## State and context

Preserve ignored messages as attributed observations in the appropriate Hermes session, without starting a main-model turn. Prefer Hermes's supported observation/transcript path and confirm the next normal turn sees each observation once. Do not duplicate observations into a second injected prompt.

Keep context and decision state isolated by profile and Telegram chat/topic/session identifiers. Bound context length, retention, and concurrent work. Maintain message ordering when classification requests overlap. A per-session serialization mechanism must not block unrelated sessions.

Pending clarification and control-message detection must use Hermes's actual session state rather than a text heuristic alone. Preserve cancel/stop and other gateway controls even while an agent is busy.

## Network and operations

Use a persistent async HTTP client. Pin `jev-1.13.0` for initial evaluation rather than a moving alias. Bound the whole classification operation, not just an individual socket read, with no long retry queue in the inbound path.

Read `TYPESAFE_API_KEY` using Hermes's standard `agent.secret_scope.get_secret("TYPESAFE_API_KEY")`, inside the owning profile's runtime scope. Hermes loads the profile's `.env` and its supported credential sources; the plugin does not parse a separate secret file or directly read the process-global environment. This preserves profile isolation when one gateway serves multiple profiles. Never store the key in configuration examples, transcripts, or decision logs.

The settings schema and initial defaults are specified above; code implementing that schema is still pending. Settings cover enabled state, mode, group allowlist, model version, threshold, classification timeout and context limits.

Shadow mode records the proposed action and continues normal message handling. Logs should include model, decision, probabilities, elapsed time, and failure category. Omit message bodies by default. Retention and sampling should be bounded.

The host extension must own callback lifecycle and make stale generations inert on disable/unload/force-reload. Check runtime enablement before classification and before host commit; document restart requirements verified during implementation.

## Acceptance criteria before a release

- Scoped authorized ordinary chatter can be suppressed in idle and busy sessions.
- Ignored chatter cannot interrupt, steer, or queue an agent turn.
- The next authorized assistant request sees prior ignored observations once, with attribution.
- Commands, mentions, bot replies, pending clarification answers, and media preserve normal behavior.
- Errors, unexpected schemas, unavailable credentials, and timeouts continue normal processing.
- Out-of-scope or unauthorized content never reaches Jev or a transcript through this plugin.
- Concurrent arrivals preserve ordering without leaking state across profiles or sessions.
- Shadow mode does not suppress messages or alter transcript semantics.
- Disable/restart behavior is verified against the supported Hermes version.
- Representative English/Hebrew conversations are evaluated for false suppression; synthetic label agreement alone is insufficient.

## References

- [Hermes native platform handlers](https://hermes-agent.nousresearch.com/docs/developer-guide/plugins#register-native-platform-handlers-any-platform)
- [Hermes pre-dispatch hook](https://hermes-agent.nousresearch.com/docs/user-guide/features/hooks#pre_gateway_dispatch)
- [TypeSafe API](https://docs.typesafe.ai/api)
- [Jev confidence](https://docs.typesafe.ai/confidence)
- [Jev model limitations](https://docs.typesafe.ai/model-jaggedness/jev-1.13)
