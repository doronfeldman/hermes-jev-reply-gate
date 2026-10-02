# Proposed integration

Status: implementation pending. This describes the intended contract, not current plugin behavior.

## First release and Hermes abstractions

Hermes already normalizes inbound traffic into `MessageEvent` with a `SessionSource`, and its platforms share `BasePlatformAdapter`. Its `pre_gateway_dispatch` hook is also platform-independent. However, the hook runs in the runner's normal admission path, after the adapter can already route a busy-session message to queueing or steering. It is not a complete cross-platform early gate.

Release 0.1 will therefore have a transport-independent engine and a Telegram binding. The engine owns bounded attributed context, Jev classification, decision validation, timeouts, and shadow/suppress policy. The binding owns Telegram trigger detection, authorization, session identity, native dispatch stopping, and Hermes observation persistence. It converts Hermes's normalized event into the engine's input; the engine does not import the Telegram SDK or Hermes internals.

This deliberately does not claim working Discord/Slack support. Adding those bindings should reuse the engine. A future generic Hermes hook before busy routing could replace the native bindings, but this release makes no core edits and does not monkey-patch adapters.

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

For suppression, require Hermes's existing group-observation support to be enabled and the target group to appear in its observation allowlist. Use the same shared observation source as later triggered turns. If observation persistence fails, continue normal dispatch rather than lose the message. Settings are re-read under the owning profile at message time, so disabling the gate makes any still-registered native handler inert. Restart the gateway after code or secret changes.

Context and session limits must be positive integers; timeout must be finite and positive; ignore probability must be finite in `(0.5, 1]`. Long latest messages that cannot fit the configured context budget pass normally without classification; do not classify truncated instructions. Retain recent complete attributed context entries within the message/character limits and evict idle sessions at `max_sessions`.

Classification is bounded by a one-second overall operation by default, including lock waits. A waiting message passes normally if that budget is exhausted. Each session is serialized for context consistency; other sessions proceed independently. Explicit control messages bypass classification and never wait on its lock.

Only ordinary eligible text is classified. Human bot replies and pending clarification responses bypass it. A native handler runs in an earlier handler group than the core handler, with blocking execution for that update. In shadow mode it simply returns; in suppression mode it stops propagation only after an eligible confident ignore has been successfully recorded as an observation.

The binding checks Hermes's existing sender, group/topic, own-bot, and bot-to-bot gates before any external request. It must resolve the owning profile and canonical session identity before accessing settings, credentials, pending prompts, or context. A resolved source user ID is required for classification; ambiguous anonymous/service messages follow normal Hermes handling.

Read classifier context from the owning Hermes session's recent transcript plus bounded unpersisted inbound context, with message IDs used to avoid duplicates. This lets accepted turns and Hermes replies inform later follow-up decisions without inventing a second conversation history. Suppressed observations remain in Hermes's existing transcript path. Shadow decisions create no extra transcript entries.

TypeSafe responses must contain the expected pinned model, a recognized choice, finite probabilities in `[0, 1]` for exactly the three labels, and a probability total consistent with rounded API values. Unexpected or inconsistent responses pass normally. Require `IGNORE` to be the maximum-probability choice as well as to meet the configured threshold.

Log one structured decision record through Hermes logging with mode, model, selected action, probabilities, elapsed milliseconds, and reason. Do not log content, sender IDs, group IDs, credentials, or API response bodies. Use Hermes's log rotation and profile routing. Emit a startup warning when a suppression group cannot preserve observed context; leave that group ungated.

## Scope

Enable the gate explicitly per Hermes profile and Telegram group. Honor the profile's sender authorization before sending content to Jev or adding it to conversational context. Unconfigured profiles, groups, private chats, and unauthorized senders must not be classified.

Use verified Telegram sender identity for permission checks and attribution. Observed-message representations may omit a normal user ID; do not infer authorization from display names. Existing Hermes authorization remains authoritative downstream.

## Placement

Register an early handler through `ctx.register_telegram_handler(factory)` (or the platform-handler equivalent). Gate eligible ordinary text before Hermes can queue, steer, or interrupt an active session. Handle suppression using the native handler's supported stop-propagation mechanism.

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

Read `TYPESAFE_API_KEY` from the profile's environment or documented secret mechanism. Never store it in configuration examples, transcripts, or decision logs.

Proposed configurable settings: enabled state, shadow/suppress mode, group allowlist, model version, ignore-probability threshold, overall timeout, and context limits. Configuration syntax and defaults will be chosen during implementation; there is no working config format yet.

Shadow mode records the proposed action and continues normal message handling. Logs should include model, decision, probabilities, elapsed time, and failure category. Omit message bodies by default. Retention and sampling should be bounded.

Native handlers may remain registered until gateway restart when a plugin is disabled. Check runtime enablement in the callback and document restart requirements verified during implementation.

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
