"""Benchmark reply classification through an existing Hermes Codex OAuth route."""
import argparse
import json
import os
import random
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--hermes-source", type=Path, required=True, help="Existing Hermes source checkout")
parser.add_argument("--hermes-home", type=Path, required=True, help="Existing authenticated Hermes profile home")
args = parser.parse_args()
os.environ["HERMES_HOME"] = str(args.hermes_home.expanduser().resolve())
sys.path.insert(0, str(args.hermes_source.expanduser().resolve()))
import hermes_bootstrap  # noqa: E402,F401
from agent.auxiliary_client import resolve_provider_client  # noqa: E402

HERE = Path(__file__).resolve().parent
SYSTEM = (HERE / "policy.txt").read_text().strip()
CASES = [(c["id"], c["expected"], c["conversation"]) for c in json.loads((HERE / "cases.json").read_text())]
CONDITIONS = [
    ("gpt-6-luna", "none"),
    ("gpt-6-luna", "low"),
    ("gpt-6.1-sol", "low"),
    ("gpt-6.1-sol", "medium"),
]
clients = {}
for model, _ in CONDITIONS:
    if model not in clients:
        client, resolved = resolve_provider_client("openai-codex", model=model)
        if client is None or resolved != model:
            raise RuntimeError("Requested route could not be resolved exactly")
        clients[model] = client

def request(model, effort, case, phase, repeat):
    case_id, expected, conversation = case
    start = time.perf_counter()
    row = {"phase": phase, "repeat": repeat, "case": case_id,
           "model": model, "reasoning_effort": effort, "expected": expected}
    try:
        result = clients[model].chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": SYSTEM},
                      {"role": "user", "content": conversation}],
            extra_body={"reasoning": {"effort": effort}}, timeout=30,
        )
        decision = (result.choices[0].message.content or "").strip()
        row.update(seconds=round(time.perf_counter() - start, 4),
                   response_model=getattr(result, "model", None),
                   decision=decision, correct=decision == expected)
        usage = getattr(result, "usage", None)
        if usage is not None:
            row["usage"] = usage.model_dump() if hasattr(usage, "model_dump") else str(usage)
    except Exception as exc:
        row.update(seconds=round(time.perf_counter() - start, 4),
                   error_type=type(exc).__name__, status=getattr(exc, "status_code", None))
    print(json.dumps(row, ensure_ascii=False), flush=True)
    return row

print(json.dumps({"phase": "metadata", "started_utc": datetime.now(timezone.utc).isoformat(),
                  "provider": "openai-codex",
                  "metric": "client-side wall clock until complete classification",
                  "synthetic_cases": len(CASES), "repetitions": 2,
                  "interleaved": True, "tools": False, "warmup_excluded": True}), flush=True)
for model, effort in CONDITIONS:
    request(model, effort, CASES[1], "warmup", 0)

rows = []
for repeat in range(1, 3):
    for i, case in enumerate(CASES):
        conditions = list(CONDITIONS)
        random.Random(100 * repeat + i).shuffle(conditions)
        for model, effort in conditions:
            rows.append(request(model, effort, case, "sample", repeat))

for model, effort in CONDITIONS:
    selected = [r for r in rows if r["model"] == model and r["reasoning_effort"] == effort]
    ok = [r for r in selected if "error_type" not in r]
    values = [r["seconds"] for r in ok]
    print(json.dumps({"phase": "summary", "model": model, "reasoning_effort": effort,
                      "n": len(ok), "errors": len(selected) - len(ok),
                      "mean_s": round(statistics.mean(values), 4) if values else None,
                      "median_s": round(statistics.median(values), 4) if values else None,
                      "min_s": min(values) if values else None,
                      "max_s": max(values) if values else None,
                      "correct": sum(r["correct"] for r in ok)}), flush=True)
