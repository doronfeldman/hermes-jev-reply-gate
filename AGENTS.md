# Working on Hermes Jev Reply Gate

Read `README.md`, `CONTRIBUTING.md`, and the relevant architecture/compatibility docs
before changing behavior. Use uv for Python installation, dependency management,
commands, and builds. The committed `uv.lock` is authoritative for this project;
update it alongside `pyproject.toml`. Python 3.14 is the development default and
standalone CI also covers the minimum supported Python 3.11.

## Commands

- `uv sync --locked` installs the package and development tools.
- `uv run --locked pytest -q` runs offline tests; network sockets are disabled.
- `uv run --locked ruff check .` checks Python errors.
- `uv run --locked python benchmarks/verify_results.py` checks published evidence.
- `uv build --no-sources` builds the wheel and source distribution.
- Follow `CONTRIBUTING.md` for real Hermes integration; do not call skipped host
  tests a passing integration run.

## Ownership and behavior

- Hermes owns transport intake, authorization, profile/session identity, ordering,
  the canonical transcript, observation commits, and shutdown recovery. Keep one
  event stream and one durable conversation history. Do not add a second listener,
  transcript store, monkeypatch, or Telegram-native interception fallback.
- Keep Jev-specific code in this plugin. The compatibility patch must stay generic.
  Changes to its contract require corresponding host regressions and integration tests.
- Read runtime secrets only through Hermes `agent.secret_scope.get_secret` in the
  owning profile's scope. Never introduce process-global runtime secret reads.
  The standalone, explicitly invoked CI smoke script accepts an environment secret.
- Scope and authorize before disclosure. Preserve command, addressed-message,
  pending-control, unknown-state, and media bypasses. Fail open on missing context,
  keys, timeouts, invalid responses, or uncertainty.
- Suppress only in explicitly enabled suppression mode for a validated confident
  `IGNORE`. Keep shadow mode the default. Recheck settings/lifecycle at the commit
  boundary; never trade away idempotency, FIFO ordering, or profile isolation.
- Keep contexts, requests, response sizes, timeouts, concurrency, and state bounded.
  Do not add request retries to the ingress path or loosen strict API validation.

## Tests and secrets

Use synthetic data, temporary profiles/SQLite, and `httpx.MockTransport` for normal
coverage. Add focused regressions for behavioral changes, particularly cancellation,
ordering, configuration changes during awaits, and profile isolation. No real user
messages, identifiers, credentials, private deployment paths, or server addresses
belong in code, fixtures, logs, commits, or PR descriptions.

Never run paid benchmarks or live API probes as part of ordinary tests. Local live
checks need explicit authorization and `scripts/jev_smoke.py --live`. Never print a
key, put one on a command line, or save one in this repo. Do not deploy or change a
live Hermes profile as a side effect of repository maintenance.

## CI boundary

Ordinary PR CI has no secrets. The live workflow is trusted default-branch code and
must keep all job-level owner/actor/same-repository checks. The `jev-live` environment
must allow only `main`; its key must never become a repository-wide secret. Do not
execute outside contributors' code in a secret-bearing job, including via artifacts,
caches, changed dependency manifests, or a privileged trigger. Do not broaden this
boundary without the owner's explicit authorization.

Pin GitHub Actions to commit SHAs. Keep `GITHUB_TOKEN` read-only, checkout credential
persistence off, and caches disabled in privileged tests. Offline socket blocking is
an accidental-network guard, not a security sandbox.

## Documentation and completion

Keep user-facing docs about current behavior, installation, compatibility, and
reproduction. Put one-time plans, model reviews, test-run transcripts, and deployment
journals in the PR or ignored local notes, not new permanent docs. Update the README
when setup or supported behavior changes. Separate API smoke success from model
accuracy and from production chat verification. Report exact checks and any skips;
never claim hosted CI or deployment succeeded from local test results alone.
