"""Validate published benchmark records without network calls."""
import json
import statistics
import subprocess
from pathlib import Path


def main():
    here = Path(__file__).resolve().parent
    cases = json.loads((here / "cases.json").read_text())
    expected = {case["id"]: case["expected"] for case in cases}
    assert len(expected) == 6
    conditions = 0
    for path in sorted((here / "results").glob("*.jsonl")):
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        assert len([r for r in rows if r["phase"] == "metadata"]) == 1
        summaries = [r for r in rows if r["phase"] == "summary"]
        samples = [r for r in rows if r["phase"] == "sample"]
        for summary in summaries:
            selected = [r for r in samples if r["model"] == summary["model"]
                        and r.get("reasoning_effort") == summary.get("reasoning_effort")]
            assert len(selected) == 12
            assert {(r["case"], r["repeat"]) for r in selected} == {
                (case_id, repeat) for case_id in expected for repeat in (1, 2)
            }
            ok = [r for r in selected if "error_type" not in r]
            assert summary["n"] == len(ok)
            assert summary["errors"] == len(selected) - len(ok)
            for row in ok:
                assert row["expected"] == expected[row["case"]]
                assert row["correct"] == (row["decision"] == row["expected"])
                assert row["seconds"] > 0
            values = [r["seconds"] for r in ok]
            assert summary["mean_s"] == round(statistics.mean(values), 4)
            assert summary["median_s"] == round(statistics.median(values), 4)
            assert summary["min_s"] == min(values)
            assert summary["max_s"] == max(values)
            assert summary["correct"] == sum(r["correct"] for r in ok)
            if summary["model"].startswith("jev"):
                tokens = sum(r["usage"]["input_tokens"] for r in ok)
                assert summary["sample_input_tokens"] == tokens
                assert summary["estimated_sample_cost_usd"] == round(tokens * 0.042 / 1e6, 8)
                for row in ok:
                    assert row["response_model"] == summary["model"]
                    probabilities = row["probabilities"]
                    assert set(probabilities) == {"ANSWER", "IGNORE", "UNCERTAIN"}
                    assert abs(sum(probabilities.values()) - 1) <= 0.011
            conditions += 1
        assert len(samples) == sum(s["n"] + s["errors"] for s in summaries)
        assert all("host" not in row for row in rows)
    assert conditions == 5
    root = here.parent
    try:
        names = subprocess.check_output(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
            cwd=root, stderr=subprocess.DEVNULL).decode().split("\0")
        paths = [root / name for name in names if name]
    except (subprocess.CalledProcessError, FileNotFoundError):
        ignored = {".git", ".superpowers", ".pytest_cache", ".venv", "__pycache__", "build", "dist"}
        paths = [p for p in root.rglob("*") if not ignored.intersection(p.relative_to(root).parts)]
    for path in paths:
        if (not path.is_file() or ".git" in path.parts or "__pycache__" in path.parts
                or path == Path(__file__).resolve()):
            continue
        contents = path.read_text()
        for forbidden in ("/srv/", "/opt/", "hermes@", "/Users/", "hermes-server"):
            assert forbidden not in contents, f"Private deployment marker in {path}"
    print("Verified: 5 conditions, 60 sample records, summaries, case labels, cost, and sanitized metadata.")


if __name__ == "__main__":
    main()
