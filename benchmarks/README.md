# Reply-classification benchmark

## Recorded run

The JSONL files in `results/` contain the measurements recorded on October 2, 2026. Both providers were called from the same deployment machine. The client measured elapsed wall-clock time until a complete classification response, including network and provider processing time. It did not measure Hermes's full agent turn, time to first token, Telegram delivery, or plugin overhead.

The six cases are synthetic English/Hebrew conversations, each repeated twice. One warm-up per condition is excluded from summaries. There were no errors in the recorded samples. GPT conditions were interleaved with deterministic random ordering; Jev was measured later in a separate sequential batch using a persistent HTTP client.

GPT used Hermes's existing `openai-codex` route with the exact model and reasoning-effort values recorded in the data. Jev used the direct TypeSafe API and a structured choice question. Both requested the same three semantic labels, but API formats, instruction shapes, and token counts differ. Twelve samples per condition cannot establish a reliable tail-latency distribution or general accuracy.

The recorded deployment hostname was removed. Published speaker names were replaced with pseudonyms after measurement; the scenarios and labels are unchanged. These substitutions may change token counts in a reproduction. No real group messages or production agent timings are included.

Jev's estimated sample cost is `sample_input_tokens × 0.042 / 1_000_000`, using [documented pricing](https://docs.typesafe.ai/models) at the time of the run, with outputs free. Warm-up usage is excluded. The API response did not return an actual billed cost.

## Reproduce Jev measurements

Use the repository uv environment. This makes authenticated, potentially billable API requests. Set `TYPESAFE_API_KEY` securely in your environment; the script never prints the key.

```sh
uv sync --locked
mkdir -p benchmarks/local-results
uv run --locked python benchmarks/benchmark_jev.py > benchmarks/local-results/jev.jsonl
```

The model is pinned to `jev-1.13.0`. Historical model availability and prices may change. Errors log their class, without response bodies or request credentials.

## Reproduce the Hermes Codex measurements

Use the interpreter/environment of an existing Hermes installation, with an already authenticated profile. Supply your own paths explicitly:

```sh
mkdir -p benchmarks/local-results
python benchmarks/benchmark_codex.py \
  --hermes-source /path/to/hermes-agent \
  --hermes-home /path/to/hermes-profile \
  > benchmarks/local-results/codex.jsonl
```

This depends on Hermes's `hermes_bootstrap` and `agent.auxiliary_client` APIs. It does not install Hermes, authenticate an account, change Telegram settings, run an agent, or send chat messages. Provider authentication may perform its normal token refresh. Model access depends on your account and provider support.

The public runners adapt the original scripts to read pseudonymized cases from files and accept configuration without private deployment paths. Their request loops match the measured approach, but no new live benchmark was run as part of publication.

## Check the published evidence locally

```sh
uv run --locked python benchmarks/verify_results.py
```

The checker recomputes every summary from sample rows, verifies the case/label roster and Jev cost calculation, and validates the published files against deployment details that should be absent. It makes no network requests.
