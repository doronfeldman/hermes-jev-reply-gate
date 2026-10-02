# Development

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) **0.12.3 or newer**.
It manages the Python interpreter and `.venv`; no manual activation is needed.

```sh
git clone https://github.com/doronfeldman/hermes-jev-reply-gate.git
cd hermes-jev-reply-gate
uv sync --locked
uv run --locked ruff check .
uv run --locked pytest -q
uv run --locked python benchmarks/verify_results.py
uv build --no-sources
```

Python 3.14 is pinned in `.python-version`. Standalone CI tests 3.11 and 3.14.
Use `uv add package` for runtime dependencies and `uv add --dev package` for tools;
commit both `pyproject.toml` and `uv.lock`. Upgrade deliberately with
`uv lock --upgrade-package package`, then rerun checks. `--locked` fails if metadata
and lockfile disagree. The runtime wheel keeps ordinary dependency bounds so it can
be installed into Hermes's own environment.

The default tests disable network sockets with pytest-socket (local Unix sockets
remain available for asyncio). API calls use `httpx.MockTransport`. Tests never
need an API key. Host integration tests explicitly skip without `HERMES_TEST_HOST`.

## Hermes integration

The host must match the pinned base and [bundled patch](compat/README.md). Use a
separate checkout, never the source directory of a running gateway:

```sh
git clone https://github.com/NousResearch/hermes-agent.git .hermes-test-host
git -C .hermes-test-host checkout 34f8ec3b407e50bad3ae27e4cd79d65212061356
git -C .hermes-test-host apply ../compat/hermes-0.21.5-ingress.patch
export HERMES_TEST_HOST="$PWD/.hermes-test-host"
export HERMES_HOME="$(mktemp -d)"
uv run --project "$HERMES_TEST_HOST" --frozen --group dev --extra telegram \
  --with pytest-socket==0.7.0 --with-editable "$PWD" \
  python -m pytest "$PWD/tests" -q --disable-socket --allow-unix-socket
```

The host has its own committed lockfile and requires Python 3.14 for its runtime.
This command uses that environment plus the editable plugin and socket guard.
CI repeats this setup and applies the published patch from scratch. These are plugin
integration tests through real host APIs, not the entire upstream Hermes suite.
When editing the patch, also run the affected host tests with its isolated
`scripts/run_tests.sh` harness. Keep host source changes and patch contents in sync.

## CI and paid API checks

| Workflow | Trigger | What runs | Jev key |
| --- | --- | --- | --- |
| CI | Every PR; pushes to `main` | Python matrix, lint, packaging, benchmark verification, patched-host integration | None |
| Jev live smoke | Relevant updates to eligible owner PRs targeting `main` | Three synthetic requests using the real client | `jev-live` environment only |

The live job requires **all** of these: repository
`doronfeldman/hermes-jev-reply-gate`, PR author `doronfeldman`, a head branch in that
same repository, base `main`, and both original actor and rerun actor
`doronfeldman`. Fork PRs, other authors, bots, and other actors cannot run it.
These are job-level conditions in a `pull_request_target` workflow, loaded from
the default branch. The exact eligible PR head is checked out only after the guard;
the smoke harness comes from the trusted default-branch commit. Owner PR code and
its dependencies are trusted in this job; step-local secret injection is not a
sandbox against that code.

GitHub setup:

1. Create environment **`jev-live`** with **Selected branches and tags**, allowing
   only the branch **`main`**. Do not add tags or `refs/pull/*/merge` patterns.
2. Add **`TYPESAFE_API_KEY` as an environment secret** there. Do not add the key as
   an Actions repository or organization secret. To enter it without a command-line
   value, run `gh secret set TYPESAFE_API_KEY --env jev-live` from this repository
   and use its hidden prompt.
3. Keep write/admin access limited to trusted maintainers. Treat changes to the
   privileged workflow and environment policy as security-sensitive.
4. Merge the setup PR before expecting live tests: `pull_request_target` needs the
   trusted workflow and smoke harness on `main`. A subsequent eligible code PR
   runs it automatically, including drafts. Documentation-only PRs do not spend API
   credits. Missing credentials fail the live job instead of silently skipping.

The `main` restriction is enforced by GitHub outside PR-controlled YAML. Ordinary
PR workflows use `refs/pull/N/merge`, so a PR cannot unlock the environment by
editing its workflow. See [GitHub environment rules](https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments)
and [privileged PR event behavior](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#pull_request_target).
Approving an outside contributor's ordinary CI does not grant the Jev key.

The committed probe has at most three sequential calls, no retries, and a five-second
per-call timeout. It validates API connectivity and response schema, not calibrated
classification accuracy. Rerunning it spends credits again. For an explicitly
authorized local smoke run, provide the key through your shell's secret mechanism,
then run `uv run --locked python scripts/jev_smoke.py --live`. Never paste a key into
an issue, command-line argument, test output, or committed `.env`.

## Contributions

Read [AGENTS.md](AGENTS.md) for development invariants. Keep changes focused; include
regressions for behavior changes and update the relevant docs. PR descriptions should
explain the resulting behavior and actual checks performed. Review notes and one-time
execution plans belong in the PR, not permanent documentation. Production suppression
requires representative evaluation and an explicit rollout decision.
