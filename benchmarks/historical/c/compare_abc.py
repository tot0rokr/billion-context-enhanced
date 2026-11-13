import collections
import datetime
import hashlib
import json
import re
import sqlite3
from pathlib import Path

from analyze import summarize


ROOT = Path(__file__).resolve().parent
PREVIOUS = Path("/tmp/billion-context-benchmark-20261106")
FIXTURE = PREVIOUS / "dataset-v2"


def read_json(path):
    return json.loads(path.read_text()) if path.exists() else None


def build_c():
    run = ROOT / "runs/C"
    result = read_json(run / "result.json")
    metrics = summarize(run)
    (run / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n")
    raw = [json.loads(line) for line in (run / "audit/provider-usage.jsonl").read_text().splitlines()]
    usage = {row["id"]: row for row in raw if row.get("kind") == "usage"}
    context_ids = {row["id"] for row in raw if row.get("kind") == "tool_call" and row.get("name") in ("compress", "decompress", "acp_status", "search_context")}
    context_usage = [row["usage"] for key, row in usage.items() if key in context_ids]
    log = (run / "home/.local/state/billion-context/bili.log").read_text(errors="replace")
    phases = metrics["phases"]
    phase_times = {phase["phase"]: phase["elapsed_s"] for phase in phases}
    phase_six_exists = 6 in phase_times
    closed_tools = metrics["phase6_tools"] + metrics["phase6_otel_tools"] + metrics["phase6_proxy_tools"]
    watchdog = read_json(run / "watchdog.json")
    status_reports = []
    for event_file in sorted((run / "audit").glob("events-*.jsonl")):
        for line in event_file.read_text().splitlines():
            event = json.loads(line)
            text = event.get("item", {}).get("text", "")
            if "acp_status result:" in text and "UNCOMPRESSED" in text:
                status_reports.append({"phase_file": event_file.name, "message_view": "visible messages" not in text and " msgs" in text})
    return {
        "arm": "C", "completed": result["completed"] if result else False,
        "wall_s": result["wall_s"] if result else None,
        "implementation_wall_s": sum(duration for phase, duration in phase_times.items() if phase <= 5),
        "phase_seconds": phase_times, "reported_tokens": metrics["provider_totals"],
        "host_visible_tokens": metrics["otel_totals"],
        "token_source": "bili upstream response observer, same as B",
        "measured_upstream_responses": len(usage),
        "provider_requests": metrics["provider_requests"],
        "provider_missing_usage_requests": metrics["provider_missing_usage_requests"],
        "provider_request_errors": sum(row.get("kind") == "request_error" for row in raw),
        "duplicate_response_ids": len(usage) - len({row.get("response_id") for row in usage.values()}),
        "peak_upstream_reported_input": max((row["usage"]["input_tokens"] for row in usage.values()), default=0),
        "context_management_responses": len(context_usage),
        "context_management_response_input_tokens": sum(row["input_tokens"] for row in context_usage),
        "context_management_response_output_tokens": sum(row["output_tokens"] for row in context_usage),
        "subagent_threads": metrics["subagent_threads"],
        "models_seen": sorted({row["model"] for row in metrics["otel_samples"]}),
        "effective_windows": sorted({value for row in metrics["rollouts"].values() for value in row["effective_windows"]}),
        "compression_log_receipts": re.findall(r"\[Compressed ([^\]\n]+?) → (\d+) block\(s\), ~([\d,]+) tokens saved", log),
        "compression_noop_count": len(re.findall(r"compress no-op", log)),
        "compression_failure_count": len(re.findall(r"\[acp-proxy: compress FAILED", log)),
        "patch_observations": {
            "noop_receipt_rounds": len(re.findall(r"no-op-only compress round; continuing with the client-visible receipt", log)),
            "uncompressed_status_reports": len(status_reports),
            "message_view_status_reports": sum(report["message_view"] for report in status_reports),
            "status_reports": status_reports,
        },
        "phase6_tool_free": not closed_tools if phase_six_exists else None,
        "phase6_tool_events": closed_tools,
        "code": read_json(run / "code-grade.json"), "memory": read_json(run / "memory-grade.json"),
        "engine_recovery": read_json(run / "engine-recovery-grade.json"),
        "file_recovery": read_json(run / "file-recovery-grade.json"),
        "prompt_hashes": {phase["phase"]: phase["prompt_sha256"] for phase in phases},
        "watchdog": watchdog,
        "executed_runner": str(ROOT / "run_benchmark.py.bak.before-deadline-v1.20261113"),
        "date_utc": datetime.datetime.fromtimestamp(result["started"], datetime.timezone.utc).date().isoformat() if result else None,
    }


def verify_c():
    run = ROOT / "runs/C"
    result = read_json(run / "result.json")
    if not result or not result["completed"]:
        return {"completed": False}
    phases = result["phases"]
    hashes_match = all(hashlib.sha256((FIXTURE / "prompts" / f'{phase["phase"]:02d}.txt').read_bytes()).hexdigest() == phase["prompt_sha256"] for phase in phases)
    input_unchanged = (FIXTURE / "visible/data/visible.jsonl").read_bytes() == (run / "candidate/data/visible.jsonl").read_bytes()
    after_five = next(phase["finished"] for phase in phases if phase["phase"] == 5)
    changed_after_five = [str(path.relative_to(run / "candidate")) for path in (run / "candidate").rglob("*.py") if path.stat().st_mtime > after_five]
    malformed = []
    for path in (run / "audit").glob("*.jsonl"):
        for index, line in enumerate(path.read_text(errors="replace").splitlines(), 1):
            try:
                json.loads(line)
            except json.JSONDecodeError:
                malformed.append({"file": path.name, "line": index})
    session = phases[0]["thread_id"]
    database = run / "home/.local/share/billion-context/sessions/index.db"
    conn = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    conn.execute("PRAGMA query_only=ON")
    saved = []
    for ref, content in conn.execute("SELECT m.ref,c.bytes FROM messages m JOIN content c ON c.hash=m.content_hash WHERE m.session_id=?", (session,)):
        payload = json.loads(content)
        if isinstance(payload, dict) and isinstance(payload.get("text"), str):
            saved.append((ref, payload["text"]))
    originals = []
    for phase in (2, 3, 4):
        expected = (FIXTURE / "prompts" / f"{phase:02d}.txt").read_text()
        originals.append({"phase": phase, "sha256": hashlib.sha256(expected.encode()).hexdigest(), "matching_refs": [ref for ref, text in saved if text == expected]})
    block_counts = {str(tier): count for tier, count in conn.execute("SELECT tier,count(*) FROM blocks GROUP BY tier")}
    conn.close()
    return {"completed": True, "prompt_hashes_match": hashes_match, "visible_input_unchanged": input_unchanged,
            "python_files_modified_after_phase5": changed_after_five, "malformed_jsonl_records": malformed,
            "original_evidence": originals, "blocks_by_tier": block_counts}


if __name__ == "__main__":
    historical = read_json(PREVIOUS / "comparison.json")
    arms = {label: historical["arms"][label] for label in ("A", "B")}
    for label, row in arms.items():
        result = read_json(PREVIOUS / "runs" / label / "result.json")
        row["date_utc"] = datetime.datetime.fromtimestamp(result["started"], datetime.timezone.utc).date().isoformat()
    arms["C"] = build_c()
    output = {"design": "Historical A/B plus one later C run; not a contemporaneous randomized comparison.",
              "metric_scope": "Reported usage only; unreported cancelled requests are unknown. Cached input and reasoning are subsets.",
              "arms": arms, "C_verification": verify_c(),
              "matching_prompt_hashes": arms["A"]["prompt_hashes"] == {str(key): value for key, value in arms["C"]["prompt_hashes"].items()}}
    (ROOT / "comparison-ABC.json").write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n")
    for label, row in arms.items():
        print(json.dumps({"arm": label, "completed": row["completed"], "wall_s": row["wall_s"], "tokens": row["reported_tokens"],
                          "subagents": row["subagent_threads"], "compressions": len(row["compression_log_receipts"]),
                          "noops": row["compression_noop_count"], "phase6_tool_free": row["phase6_tool_free"]}))
