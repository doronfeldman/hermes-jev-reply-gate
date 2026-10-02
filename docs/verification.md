# Verification record — October 2, 2026

The host extension is based on Hermes `34f8ec3b407e50bad3ae27e4cd79d65212061356`;
its reviewed commit is `abf9fb5427991bc7123ae7597c34a4f4b0f55bba`, distributed as
[`compat/hermes-0.21.5-ingress.patch`](../compat/hermes-0.21.5-ingress.patch).

- **125 plugin tests passed**, including actual PluginManager loading, temporary SQLite,
  genuine profile A→B→A switching and settings/secrets isolation, native control registries,
  a second normalized host transport, and disable/unload changes after the policy returns.
- **395 affected Hermes tests passed, 17 skipped**, across 33 files in an independent clean
  checkout. Coverage includes busy routing, canonical identity, profile handling, ordinary
  transcript persistence, shutdown recovery, plugin registration and native Telegram intake.
- Native PTB tests confirmed ordinary group targeting and preservation of the actual author
  in shared sessions, and command delivery while the generic classifier waits.
- Astra reviewed the design, then the implementation independently. Reported races were
  corrected with regressions: FIFO admission before authorization awaits, bounded and
  ordered overload handling, shutdown/uncertain-write recovery, complete context, and
  generation/settings invalidation inside the final write boundary. Final recheck found
  no remaining verified blocking issue.
- Historical benchmark data passed its verifier: five conditions and sixty records.
  Eight additional synthetic API calls used the actual request-local plugin client from
  the deployment host: mean **0.321 s**, median **0.282 s**, range **0.267–0.571 s**;
  all eight labels matched expectations. The first request is included. See the
  [sanitized smoke report](../benchmarks/results/2026-10-02-plugin-client-smoke.json).

One existing test outside that green affected suite,
`test_only_pre_handoff_failure_reopens_admission[error_before_entry-cancel]`, failed
identically with the original baseline Telegram adapter restored. Its cancellation
claim remains in flight in the local Python 3.14/PTB environment. This pre-existing
failure is recorded rather than attributed to or changed by this plugin.

The full Hermes suite was not run. Seventeen affected-suite skips include platform-
specific coverage. Mocked classifications establish policy behavior, not model quality;
eight synthetic live cases do not calibrate the suppression threshold. Production
suppression must follow representative shadow evaluation, especially ambiguous Hebrew
follow-ups and responses during active work.
