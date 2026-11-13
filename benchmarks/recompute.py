"""Recompute published measurements without a model request."""

import argparse
import collections
import hashlib
import json
from decimal import Decimal
from pathlib import Path

from grade import grade_code, grade_memory

ROOT = Path(__file__).resolve().parent
TOKEN_KEYS = (
    "input_tokens", "cached_input_tokens", "cache_write_input_tokens",
    "output_tokens", "reasoning_output_tokens",
)


def load(path):
    return json.loads(path.read_text())


def request_cost(row, pricing):
    cached = row["cached_input_tokens"]
    writes = row["cache_write_input_tokens"]
    uncached = row["input_tokens"] - cached - writes
    if uncached < 0 or not 0 <= row["reasoning_output_tokens"] <= row["output_tokens"]:
        raise ValueError("Invalid overlapping token categories")
    rates = pricing["rates_per_million"]
    long = pricing["long_context"]
    over = row["input_tokens"] > long["input_token_threshold_exclusive"]
    input_factor = Decimal(str(long["input_and_cache_multiplier"])) if over else Decimal(1)
    output_factor = Decimal(str(long["output_multiplier"])) if over else Decimal(1)
    million = Decimal(1_000_000)
    return {
        "uncached_input": Decimal(uncached) * Decimal(rates["uncached_input"]) * input_factor / million,
        "cached_input": Decimal(cached) * Decimal(rates["cached_input"]) * input_factor / million,
        "cache_write": Decimal(writes) * Decimal(rates["cache_write"]) * input_factor / million,
        "output": Decimal(row["output_tokens"]) * Decimal(rates["output"]) * output_factor / million,
    }


def verify_hashes(root):
    manifest = load(root / "artifact-manifest.json")
    for entry in manifest["files"]:
        actual = hashlib.sha256((root.parent / entry["path"]).read_bytes()).hexdigest()
        if actual != entry["published_sha256"]:
            raise ValueError(f"Artifact hash mismatch: {entry['path']}")
    fixture = load(root / "dataset-v2/manifest.json")
    for name, expected in fixture["hashes"].items():
        actual = hashlib.sha256((root / "dataset-v2" / name).read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError(f"Fixture hash mismatch: {name}")
    return {"artifact_files": len(manifest["files"]), "fixture_files": len(fixture["hashes"])}


def verify(root, run_code=False, image="python:3.12-slim"):
    hashes = verify_hashes(root)
    comparison = load(root / "results/comparison-ABC.json")
    pricing = load(root / "results/cost-estimate.json")
    process = load(root / "results/process-metrics.json")
    output = {"hashes": hashes, "arms": {}}
    for arm in "ABC":
        directory = root / "results" / arm
        rows = [json.loads(line) for line in (directory / "usage.jsonl").read_text().splitlines()]
        metrics = load(directory / "metrics.json")
        if arm == "A":
            source_rows = [{key: row[key] for key in TOKEN_KEYS} | {"context_management": False}
                           for row in metrics["otel_samples"]]
        else:
            records = [json.loads(line) for line in (directory / "audit/provider-usage.jsonl").read_text().splitlines()]
            context_ids = {row["id"] for row in records if row.get("kind") == "tool_call"
                           and row.get("name") in ("compress", "decompress", "acp_status", "search_context")}
            usages = {row["id"]: row for row in records if row.get("kind") == "usage"}
            source_rows = []
            for key, row in usages.items():
                usage = row["usage"]
                source_rows.append({
                    "input_tokens": usage["input_tokens"],
                    "cached_input_tokens": usage.get("input_tokens_details", {}).get("cached_tokens", 0),
                    "cache_write_input_tokens": usage.get("input_tokens_details", {}).get("cache_write_tokens", 0),
                    "output_tokens": usage["output_tokens"],
                    "reasoning_output_tokens": usage.get("output_tokens_details", {}).get("reasoning_tokens", 0),
                    "context_management": key in context_ids,
                })
        source_rows = [{"index": index + 1, **row} for index, row in enumerate(source_rows)]
        if rows != source_rows:
            raise ValueError(f"{arm}: normalized usage differs from original measurements")
        observed = {key: sum(row[key] for row in rows) for key in TOKEN_KEYS}
        expected = comparison["arms"][arm]
        for key, value in observed.items():
            if value != expected["reported_tokens"][key]:
                raise ValueError(f"{arm}: token mismatch for {key}")
        costs = collections.defaultdict(Decimal)
        for row in rows:
            for key, value in request_cost(row, pricing).items():
                costs[key] += value
        costs["total"] = sum(costs.values())
        for key, value in costs.items():
            if value != Decimal(pricing["arms"][arm]["standard_api_equivalent_usd"][key]):
                raise ValueError(f"{arm}: cost mismatch for {key}")
        commands = load(directory / "audit/root-commands.json")
        command_failures = sum(row["exit_code"] not in (0, None) for row in commands)
        if command_failures != process["arms"][arm]["root_shell_failures"]:
            raise ValueError(f"{arm}: root command failure count mismatch")
        unique = {(row["thread_id"], row["call_id"]): row for row in metrics["otel_tool_calls"]}
        names = collections.Counter(row["name"] for row in unique.values())
        for tool in ("exec_command", "apply_patch", "send_message"):
            if names[tool] != process["arms"][arm][f"all_threads_{tool}_calls"]:
                raise ValueError(f"{arm}: tool count mismatch for {tool}")
        memory = {}
        for name, final in load(directory / "audit/exact-final-text.json").items():
            if hashlib.sha256(final["text"].encode()).hexdigest() != final["sha256"]:
                raise ValueError(f"{arm}: original final text hash mismatch: {name}")
            if (directory / "audit" / name).read_text().rstrip("\n") != final["text"].rstrip("\n"):
                raise ValueError(f"{arm}: published final text differs: {name}")
        for phase in (6, 7, 8):
            grade = grade_memory(root / "dataset-v2", directory / "audit" / f"final-{phase:02d}.txt")
            memory[str(phase)] = {key: grade[key] for key in ("correct", "total", "revised_correct", "revised_total", "stale_values")}
            if grade["correct"] != 48 or grade["revised_correct"] != 8:
                raise ValueError(f"{arm}: memory score mismatch in phase {phase}")
        candidate = root / "candidates" / arm
        lines = sum(len(path.read_text().splitlines()) for path in candidate.glob("*.py"))
        if lines != process["arms"][arm]["production_python_lines"]:
            raise ValueError(f"{arm}: implementation line count mismatch")
        result = {
            "measured_responses": len(rows), "reported_tokens": observed,
            "standard_api_equivalent_usd": str(costs["total"]),
            "memory": memory, "root_shell_failures": command_failures,
            "production_python_lines": lines,
        }
        if run_code:
            code = grade_code(root / "dataset-v2", candidate, image, 30)
            result["code"] = code
            if code["hidden_pass"] != 13 or not code["visible_report"]["exact"]:
                raise ValueError(f"{arm}: independent functional regrade failed")
        output["arms"][arm] = result
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--grade-code", action="store_true", help="Also execute saved candidates in network-disabled Docker containers")
    parser.add_argument("--docker-image", default="python:3.12-slim")
    args = parser.parse_args()
    print(json.dumps(verify(args.root.resolve(), args.grade_code, args.docker_image), indent=2))


if __name__ == "__main__":
    main()
