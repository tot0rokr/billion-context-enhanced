import argparse
import collections
import datetime
import hashlib
import json
from pathlib import Path


TOKEN_FIELDS = ("input_tokens", "cached_input_tokens", "cache_write_input_tokens", "output_tokens", "reasoning_output_tokens")


def rows(path):
    if not path.exists():
        return
    for line in path.read_text(errors="replace").splitlines():
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            continue


def values(attributes):
    return {entry["key"]: next(iter(entry.get("value", {}).values()), None) for entry in attributes}


def number(value):
    try:
        return int(value)
    except (ValueError, TypeError):
        return 0


def summarize(run):
    phases = [json.loads(path.read_text()) for path in sorted((run / "audit").glob("phase-*.json"))]
    root_ids = {phase["thread_id"] for phase in phases if phase.get("thread_id")}
    otel_samples = []
    seen_otel = set()
    names = collections.Counter()
    otel_tools = {}
    for batch in rows(run / "audit/otel.jsonl"):
        for resource in batch.get("payload", {}).get("resourceLogs", []):
            for scope in resource.get("scopeLogs", []):
                for record in scope.get("logRecords", []):
                    attrs = values(record.get("attributes", []))
                    event = attrs.get("event.name", "unknown")
                    names[event] += 1
                    if event in ("codex.tool_decision", "codex.tool_result") and attrs.get("call_id"):
                        stamp = attrs.get("event.timestamp")
                        tool_seconds = datetime.datetime.fromisoformat(stamp.replace("Z", "+00:00")).timestamp() if stamp else None
                        tool_phase = next((p["phase"] for p in phases if tool_seconds is not None and p["started"] <= tool_seconds <= p["finished"]), None)
                        tool_key = (attrs.get("conversation.id"), attrs["call_id"])
                        otel_tools[tool_key] = {"thread_id": tool_key[0], "call_id": tool_key[1], "name": attrs.get("tool_name"), "namespace": attrs.get("tool_namespace"), "timestamp": stamp, "phase": tool_phase}
                    if event != "codex.sse_event" or "input_token_count" not in attrs:
                        continue
                    signature = (record.get("observedTimeUnixNano"), attrs.get("conversation.id"), attrs.get("event.timestamp"), attrs.get("event.kind"), attrs.get("input_token_count"), attrs.get("output_token_count"), attrs.get("cached_token_count"), attrs.get("cache_write_token_count"), attrs.get("reasoning_token_count"))
                    if signature in seen_otel:
                        continue
                    seen_otel.add(signature)
                    at = attrs.get("event.timestamp")
                    seconds = datetime.datetime.fromisoformat(at.replace("Z", "+00:00")).timestamp() if at else None
                    phase = next((p["phase"] for p in phases if seconds is not None and p["started"] <= seconds <= p["finished"]), None)
                    otel_samples.append({
                        "thread_id": attrs.get("conversation.id"), "model": attrs.get("model"),
                        "event_kind": attrs.get("event.kind"), "timestamp": at, "phase": phase,
                        "input_tokens": number(attrs.get("input_token_count")),
                        "cached_input_tokens": number(attrs.get("cached_token_count")),
                        "cache_write_input_tokens": number(attrs.get("cache_write_token_count")),
                        "output_tokens": number(attrs.get("output_token_count")),
                        "reasoning_output_tokens": number(attrs.get("reasoning_token_count")),
                    })
    otel_totals = {key: sum(row[key] for row in otel_samples) for key in TOKEN_FIELDS}
    otel_totals["uncached_input_tokens"] = otel_totals["input_tokens"] - otel_totals["cached_input_tokens"]
    by_thread = {}
    for row in otel_samples:
        current = by_thread.setdefault(row["thread_id"], {key: 0 for key in TOKEN_FIELDS} | {"calls": 0, "model": row["model"], "root": row["thread_id"] in root_ids})
        current["calls"] += 1
        for key in TOKEN_FIELDS:
            current[key] += row[key]
    rollouts = {}
    all_tools = []
    for path in (run / "home").rglob("rollout-*.jsonl"):
        thread_id = None
        meta = None
        totals = {}
        windows = set()
        for event in rows(path):
            payload = event.get("payload", {})
            if event.get("type") == "session_meta":
                thread_id = payload.get("id")
                meta = {key: payload.get(key) for key in ("id", "source", "model_provider", "agent_path")}
            if event.get("type") == "event_msg" and payload.get("type") == "token_count" and payload.get("info"):
                info = payload["info"]
                for key, value in info.get("total_token_usage", {}).items():
                    totals[key] = max(totals.get(key, 0), number(value))
                if info.get("model_context_window"):
                    windows.add(info["model_context_window"])
            if event.get("type") == "response_item" and payload.get("type") in ("function_call", "custom_tool_call", "local_shell_call"):
                at = event.get("timestamp")
                seconds = datetime.datetime.fromisoformat(at.replace("Z", "+00:00")).timestamp() if at else None
                phase = next((p["phase"] for p in phases if seconds is not None and p["started"] <= seconds <= p["finished"]), None)
                all_tools.append({"thread_id": thread_id, "phase": phase, "name": payload.get("name", payload.get("type")), "timestamp": at, "call_id": payload.get("call_id")})
        if thread_id:
            previous = rollouts.get(thread_id)
            if previous is None or totals.get("input_tokens", 0) >= previous["totals"].get("input_tokens", 0):
                rollouts[thread_id] = {"metadata": meta, "totals": totals, "effective_windows": sorted(windows), "file": str(path.relative_to(run))}
    provider_rows = list(rows(run / "audit/provider-usage.jsonl"))
    request_ids = {row["id"] for row in provider_rows if row.get("kind") == "request"}
    provider_usage = {}
    for row in provider_rows:
        if row.get("kind") == "usage":
            provider_usage[row["id"]] = row
    provider_totals = collections.Counter()
    for row in provider_usage.values():
        usage = row["usage"]
        provider_totals["input_tokens"] += number(usage.get("input_tokens"))
        provider_totals["output_tokens"] += number(usage.get("output_tokens"))
        provider_totals["cached_input_tokens"] += number(usage.get("input_tokens_details", {}).get("cached_tokens"))
        provider_totals["cache_write_input_tokens"] += number(usage.get("input_tokens_details", {}).get("cache_write_tokens"))
        provider_totals["reasoning_output_tokens"] += number(usage.get("output_tokens_details", {}).get("reasoning_tokens"))
    provider_totals["uncached_input_tokens"] = provider_totals["input_tokens"] - provider_totals["cached_input_tokens"]
    phase_six = next((phase for phase in phases if phase["phase"] == 6), None)
    hidden_tools = [row for row in provider_rows if row.get("kind") == "tool_call" and phase_six and phase_six["started"] * 1000 <= row["at"] <= phase_six["finished"] * 1000]
    code_hashes = {str(path.relative_to(run / "candidate")): hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted((run / "candidate").rglob("*.py"))}
    return {
        "arm": run.name, "phases": phases, "otel_totals": otel_totals,
        "otel_measured_responses": len(otel_samples), "otel_zero_output_responses": sum(row["output_tokens"] == 0 for row in otel_samples),
        "otel_by_thread": by_thread, "otel_samples": otel_samples, "otel_event_counts": dict(names),
        "rollouts": rollouts, "subagent_threads": len((set(rollouts) | set(by_thread)) - root_ids),
        "rollout_total_sum": {key: sum(row["totals"].get(key, 0) for row in rollouts.values()) for key in TOKEN_FIELDS},
        "tool_calls": all_tools,
        "otel_tool_calls": list(otel_tools.values()),
        "phase6_tools": [row for row in all_tools if row["phase"] == 6],
        "phase6_otel_tools": [row for row in otel_tools.values() if row["phase"] == 6], "phase6_proxy_tools": hidden_tools,
        "provider_totals": dict(provider_totals), "provider_requests": len(request_ids),
        "provider_measured_requests": len(provider_usage), "provider_missing_usage_requests": sorted(request_ids - set(provider_usage)),
        "code_hashes": code_hashes,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("run", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    summary = summarize(args.run)
    if args.output:
        args.output.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({key: value for key, value in summary.items() if key not in ("otel_samples", "tool_calls", "otel_tool_calls", "rollouts", "code_hashes", "phases")}, ensure_ascii=False, indent=2))
