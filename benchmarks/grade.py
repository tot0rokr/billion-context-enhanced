#!/usr/bin/env python3
"""Grade code and memory answers without exposing expected outputs to candidates."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tempfile
import time
import uuid
from pathlib import Path


def load_json(path: Path):
    return json.loads(path.read_text())


def json_equal(actual, expected):
    if type(actual) is not type(expected):
        return False
    if isinstance(expected, dict):
        return actual.keys() == expected.keys() and all(json_equal(actual[key], value) for key, value in expected.items())
    if isinstance(expected, list):
        return len(actual) == len(expected) and all(json_equal(left, right) for left, right in zip(actual, expected))
    return actual == expected


def answer_object(path: Path):
    raw = path.read_text().strip()
    if raw.startswith("```"):
        raw = "\n".join(raw.splitlines()[1:-1])
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("answers must be a JSON object")
    return value


def grade_memory(root: Path, answers: Path) -> dict:
    facts = load_json(root / "oracle/facts.json")
    try:
        submitted = answer_object(answers)
    except (OSError, ValueError) as error:
        return {"correct": 0, "total": len(facts), "valid_json": False, "error": str(error)}
    outcomes = []
    for key, fact in facts.items():
        actual = submitted.get(key)
        outcomes.append({"id": key, "correct": json_equal(actual, fact["answer"]),
                         "missing": actual is None,
                         "stale_value": "superseded" in fact and actual == fact["superseded"],
                         "actual": actual, "expected": fact["answer"]})
    revised = [row for row in outcomes if "superseded" in facts[row["id"]]]
    return {"correct": sum(row["correct"] for row in outcomes), "total": len(facts),
            "valid_json": True, "missing": sum(row["missing"] for row in outcomes),
            "plain_json_format": not answers.read_text().lstrip().startswith("```"),
            "extra_keys": sorted(set(submitted) - set(facts)),
            "stale_values": sum(row["stale_value"] for row in outcomes),
            "revised_correct": sum(row["correct"] for row in revised),
            "revised_total": len(revised), "outcomes": outcomes,
            "tool_free_adherence": "runner must verify from trace"}


def compare_report(actual, expected: dict) -> dict:
    if not isinstance(actual, dict):
        return {"exact": False, "error": "report must be an object"}
    actual_boards = actual.get("boards", [])
    actual_incidents = actual.get("incidents", [])
    boards_by_id = {row.get("board"): row for row in actual_boards if isinstance(row, dict)} if isinstance(actual_boards, list) else {}
    def encoded_rows(rows):
        return {json.dumps(row, sort_keys=True) for row in rows} if isinstance(rows, list) else set()
    found, wanted = encoded_rows(actual_incidents), encoded_rows(expected["incidents"])
    return {"exact": json_equal(actual, expected),
            "boards_correct": sum(json_equal(boards_by_id.get(row["board"]), row) for row in expected["boards"]),
            "boards_total": len(expected["boards"]),
            "incident_true_positive": len(found & wanted),
            "incident_false_positive": len(found - wanted),
            "incident_false_negative": len(wanted - found),
            "totals_correct": json_equal(actual.get("totals"), expected["totals"])}


def run_case(candidate: Path, source: Path, expected: dict, image: str, timeout: int) -> dict:
    # This directory is the only evaluator data mounted into candidate execution.
    directory = Path(tempfile.mkdtemp(prefix="bili-grade-case-"))
    shutil.copyfile(source, directory / "input.jsonl")
    output = directory / "result.json"
    container_name = "bili-grade-" + uuid.uuid4().hex[:12]
    command = ["docker", "run", "--rm", "--name", container_name, "--network", "none", "--user", f"{os.getuid()}:{os.getgid()}",
               "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--memory", "512m",
               "--cpus", "1", "--pids-limit", "64", "--env", "HOME=/tmp",
               "--volume", f"{candidate.resolve()}:/candidate:ro",
               "--volume", f"{directory}:/case", "--workdir", "/candidate", image,
               "python3", "/candidate/reconcile.py", "--input", "/case/input.jsonl", "--output", "/case/result.json"]
    started = time.monotonic()
    try:
        result = subprocess.run(command, text=True, capture_output=True, timeout=timeout)
        detail = {"exit_code": result.returncode, "stderr_tail": result.stderr[-3000:],
                  "seconds": round(time.monotonic() - started, 3), "case_artifacts": str(directory)}
        if result.returncode != 0:
            return detail | {"exact": False}
        try:
            return detail | compare_report(load_json(output), expected)
        except (OSError, ValueError) as error:
            return detail | {"exact": False, "error": str(error)}
    except subprocess.TimeoutExpired:
        subprocess.run(["docker", "stop", "--time", "1", container_name], capture_output=True, timeout=10)
        return {"exact": False, "timeout": True, "seconds": timeout, "case_artifacts": str(directory)}


def grade_code(root: Path, candidate: Path, image: str, timeout: int) -> dict:
    oracle = root / "oracle"
    manifest = load_json(root / "manifest.json")
    cases = {"unseen_mixed": run_case(candidate, oracle / "hidden-input.jsonl", load_json(oracle / "expected.json"), image, timeout)}
    for name in manifest["semantic_cases"]:
        cases[name] = run_case(candidate, oracle / f"{name}.jsonl", load_json(oracle / f"{name}.expected.json"), image, timeout)
    try:
        visible = compare_report(load_json(candidate / "analysis.json"), load_json(oracle / "visible-expected.json"))
    except (OSError, ValueError) as error:
        visible = {"exact": False, "error": str(error)}
    return {"hidden_pass": sum(item.get("exact") is True for item in cases.values()),
            "hidden_total": len(cases), "cases": cases, "visible_report": visible}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--candidate", type=Path)
    parser.add_argument("--phase", choices=["final", "memory", "retrieval"], required=True)
    parser.add_argument("--answers", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--docker-image", default="python:3.12-slim")
    parser.add_argument("--case-timeout", type=int, default=30)
    args = parser.parse_args()
    if args.phase == "final":
        if args.candidate is None:
            parser.error("--candidate is required for final")
        result = grade_code(args.root, args.candidate, args.docker_image, args.case_timeout)
    else:
        if args.answers is None:
            parser.error("--answers is required for memory/retrieval")
        result = grade_memory(args.root, args.answers)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"phase": args.phase, **result}, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({key: value for key, value in result.items() if key not in ("cases", "outcomes")}, indent=2))


if __name__ == "__main__":
    main()
