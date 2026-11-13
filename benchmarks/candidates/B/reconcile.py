#!/usr/bin/env python3
import argparse
import json
from pathlib import Path

from ingest import ingest_events
from report import build_audit_report, build_report
from state_machine import reconcile_states


def reconcile(events, *, trace=None):
    """Reconcile raw event records using R3, including all earlier batches."""
    retained, conflicts, duplicate_replays, conflicted_ids = ingest_events(events)
    boards, incidents, applied_commits, accepted_rollbacks = reconcile_states(
        retained, trace=trace
    )
    return build_report(
        boards,
        conflicts + incidents,
        applied_commits,
        accepted_rollbacks,
        duplicate_replays,
        conflicted_ids,
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--audit-output",
        help="Optional JSON file with event outcomes and rejection explanations",
    )
    args = parser.parse_args()
    if args.audit_output and Path(args.output).resolve() == Path(args.audit_output).resolve():
        parser.error("--output and --audit-output must name different files")
    with open(args.input, encoding="utf-8") as source:
        events = [json.loads(line) for line in source if line.strip()]
    trace = [] if args.audit_output else None
    result = reconcile(events, trace=trace)
    audit = build_audit_report(result, trace) if trace is not None else None
    with open(args.output, "w", encoding="utf-8") as target:
        json.dump(result, target, sort_keys=True, indent=2)
        target.write("\n")
    if audit is not None:
        with open(args.audit_output, "w", encoding="utf-8") as target:
            json.dump(audit, target, sort_keys=True, indent=2)
            target.write("\n")


if __name__ == "__main__":
    main()
