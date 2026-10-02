# Proposed integration

Status: implementation pending. This describes the intended contract, not current plugin behavior.

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
