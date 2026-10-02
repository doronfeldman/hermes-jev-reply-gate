"""Benchmark Jev reply classification on synthetic data; makes paid API calls."""
import argparse
import json
import os
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.parse_args()
api_key = os.environ.get("TYPESAFE_API_KEY")
if not api_key:
    parser.error("Set TYPESAFE_API_KEY in the environment")
import httpx

HERE = Path(__file__).resolve().parent
payload = {
    "api_key": api_key,
    "policy": (HERE / "policy.txt").read_text().strip(),
    "cases": [(c["id"], c["expected"], c["conversation"]) for c in json.loads((HERE / "cases.json").read_text())],
}
MODEL = "jev-1.13.0"
questions = {
    "reply_action": {
        "type": "choice",
        "instructions": payload["policy"].split("Return exactly")[0]
        + "Choose whether Hermes should respond to the latest message.",
        "criteria": {
            "ANSWER": "The latest human message asks Hermes for help, requests assistant capabilities, or answers a question Hermes just asked.",
            "IGNORE": "The latest human message is ordinary conversation between the humans or a status update; Hermes should stay silent.",
            "UNCERTAIN": "The recent conversation does not establish whether the latest human message is addressed to Hermes.",
        },
    }
}

print(json.dumps({"phase": "metadata", "started_utc": datetime.now(timezone.utc).isoformat(),
                  "model": MODEL, "provider": "typesafe-direct",
                  "metric": "client-side wall clock until complete classification",
                  "synthetic_cases": len(payload["cases"]), "repetitions": 2,
                  "persistent_http_client": True, "warmup_excluded": True,
                  "synthetic_data_only": True, "tools": False}), flush=True)

with httpx.Client(base_url="https://api.typesafe.ai", timeout=30,
                  headers={"Authorization": "Bearer " + payload["api_key"]}) as client:
    check = client.get("/v1/models")
    print(json.dumps({"phase": "authentication", "http_status": check.status_code}), flush=True)
    check.raise_for_status()

    def request(case, phase, repeat):
        case_id, expected, conversation = case
        row = {"phase": phase, "repeat": repeat, "case": case_id,
               "model": MODEL, "provider": "typesafe-direct", "expected": expected}
        started = time.perf_counter()
        try:
            response = client.post("/v1/systemone", json={
                "model": MODEL, "state": conversation, "questions": questions})
            row["seconds"] = round(time.perf_counter() - started, 4)
            row["http_status"] = response.status_code
            response.raise_for_status()
            data = response.json()
            answer = data["answers"]["reply_action"]
            row.update(response_model=data["model"], decision=answer["choice"],
                       confidence=answer.get("confidence"),
                       probabilities=answer.get("probabilities"),
                       correct=answer["choice"] == expected, usage=data.get("usage"))
        except Exception as exc:
            row["seconds"] = round(time.perf_counter() - started, 4)
            row["error_type"] = type(exc).__name__
        print(json.dumps(row, ensure_ascii=False), flush=True)
        return row

    warmup = request(payload["cases"][1], "warmup", 0)
    if "error_type" in warmup:
        raise RuntimeError("Warmup failed; stopping without repeated failures")
    rows = [request(case, "sample", repeat)
            for repeat in range(1, 3) for case in payload["cases"]]

ok = [r for r in rows if "error_type" not in r]
values = [r["seconds"] for r in ok]
input_tokens = sum((r.get("usage") or {}).get("input_tokens", 0) for r in ok)
print(json.dumps({"phase": "summary", "model": MODEL, "n": len(ok),
                  "errors": len(rows) - len(ok),
                  "mean_s": round(statistics.mean(values), 4) if values else None,
                  "median_s": round(statistics.median(values), 4) if values else None,
                  "min_s": min(values) if values else None,
                  "max_s": max(values) if values else None,
                  "correct": sum(r["correct"] for r in ok),
                  "sample_input_tokens": input_tokens,
                  "estimated_sample_cost_usd": round(input_tokens * 0.042 / 1e6, 8)}), flush=True)
