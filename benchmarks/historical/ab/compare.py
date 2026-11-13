import collections
import json
import re
from pathlib import Path

from analyze import TOKEN_FIELDS, summarize


ROOT = Path(__file__).resolve().parent


def load(path):
    return json.loads(path.read_text()) if path.exists() else None


def build_arm(label):
    run = ROOT / "runs" / label
    metrics = summarize(run)
    (run / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n")
    result = load(run / "result.json")
    phase_times = {item["phase"]: item["elapsed_s"] for item in metrics["phases"]}
    phase_tokens = collections.defaultdict(collections.Counter)
    for sample in metrics["otel_samples"]:
        for key in TOKEN_FIELDS:
            phase_tokens[sample["phase"]][key] += sample[key]
    provider_rows = []
    path = run / "audit/provider-usage.jsonl"
    if path.exists():
        provider_rows = [json.loads(line) for line in path.read_text().splitlines()]
    primary = metrics["provider_totals"] if label == "B" else metrics["otel_totals"]
    provider_usage = {row["id"]: row for row in provider_rows if row.get("kind") == "usage"}
    context_requests = {row["id"] for row in provider_rows if row.get("kind") == "tool_call" and row.get("name") in ("compress", "decompress", "acp_status", "search_context")}
    context_usage = [row["usage"] for key, row in provider_usage.items() if key in context_requests]
    proxy_log = run / "home/.local/state/billion-context/bili.log"
    log_text = proxy_log.read_text(errors="replace") if proxy_log.exists() else ""
    successes = re.findall(r"\[Compressed ([^\]\n]+?) → (\d+) block\(s\), ~([\d,]+) tokens saved", log_text)
    noops = re.findall(r"compress no-op", log_text)
    return {
        "arm": label, "completed": result["completed"] if result else False,
        "wall_s": result["wall_s"] if result else None,
        "implementation_wall_s": sum(value for phase, value in phase_times.items() if phase <= 5),
        "memory_probe_wall_s": sum(value for phase, value in phase_times.items() if phase >= 6),
        "phase_seconds": phase_times, "reported_tokens": primary,
        "token_source": "bili upstream response observer" if label == "B" else "Codex OTLP terminal usage events, all threads",
        "host_visible_tokens": metrics["otel_totals"],
        "phase_host_visible_tokens": dict(phase_tokens),
        "measured_upstream_responses": metrics["provider_measured_requests"] if label == "B" else metrics["otel_measured_responses"],
        "provider_request_errors": sum(row.get("kind") == "request_error" for row in provider_rows),
        "provider_missing_usage_requests": metrics["provider_missing_usage_requests"],
        "zero_output_reported_input": sum(row["input_tokens"] for row in metrics["otel_samples"] if row["output_tokens"] == 0),
        "peak_host_reported_input": max((row["input_tokens"] for row in metrics["otel_samples"]), default=0),
        "peak_upstream_reported_input": max((row["usage"]["input_tokens"] for row in provider_usage.values()), default=0) if label == "B" else max((row["input_tokens"] for row in metrics["otel_samples"]), default=0),
        "context_management_responses": len(context_usage),
        "context_management_response_input_tokens": sum(row["input_tokens"] for row in context_usage),
        "context_management_response_output_tokens": sum(row["output_tokens"] for row in context_usage),
        "subagent_threads": metrics["subagent_threads"],
        "models_seen": sorted({row["model"] for row in metrics["otel_samples"]}),
        "effective_windows": sorted({value for row in metrics["rollouts"].values() for value in row["effective_windows"]}),
        "compression_log_receipts": successes, "compression_noop_count": len(noops),
        "phase6_tool_free": not (metrics["phase6_tools"] or metrics["phase6_otel_tools"] or metrics["phase6_proxy_tools"]),
        "phase6_tool_events": metrics["phase6_tools"] + metrics["phase6_otel_tools"] + metrics["phase6_proxy_tools"],
        "code": load(run / "code-grade.json"), "memory": load(run / "memory-grade.json"),
        "engine_recovery": load(run / "engine-recovery-grade.json"), "file_recovery": load(run / "file-recovery-grade.json"),
        "prompt_hashes": {item["phase"]: item["prompt_sha256"] for item in metrics["phases"]},
    }


if __name__ == "__main__":
    arms = {label: build_arm(label) for label in ("A", "B")}
    output = {
        "design": "One sequential A then B controlled-long-context pilot; 60 minute maximum per arm.",
        "metric_scope": "Reported usage, including cache and reasoning subsets. Unreported aborted requests are unknown, not zero. Subscription dollars are not estimated.",
        "arms": arms,
        "matching_prompt_hashes": arms["A"]["prompt_hashes"] == arms["B"]["prompt_hashes"],
    }
    (ROOT / "comparison.json").write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n")
    for label, arm in arms.items():
        print(json.dumps({"arm": label, "completed": arm["completed"], "wall_s": arm["wall_s"],
                          "tokens": arm["reported_tokens"], "subagents": arm["subagent_threads"],
                          "compressions": len(arm["compression_log_receipts"]), "noops": arm["compression_noop_count"],
                          "phase6_tool_free": arm["phase6_tool_free"]}, ensure_ascii=False))
