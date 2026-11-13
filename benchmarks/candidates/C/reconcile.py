#!/usr/bin/env python3
import argparse
import json
from pathlib import Path

from ingest import ingest_events
from report import build_audit_report, build_report
from state_machine import apply_events


def reconcile(events, *, audit=None):
    """Reconstruct a deterministic incident report under the current contract."""
    normalized, duplicate_incidents, ingestion_counts = ingest_events(events)
    boards, transition_incidents, transition_counts = apply_events(normalized, audit=audit)
    return build_report(
        boards,
        duplicate_incidents + transition_incidents,
        transition_counts,
        ingestion_counts,
    )


def _write_json(path, value):
    with open(path, "w", encoding="utf-8") as target:
        json.dump(value, target, sort_keys=True, indent=2)
        target.write("\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--audit-output", help="write a separate event outcome audit as JSON")
    parser.add_argument("--operations-notes", help="JSON array of inert audit note values")
    args = parser.parse_args()
    if args.operations_notes and not args.audit_output:
        parser.error("--operations-notes requires --audit-output")
    if args.audit_output and Path(args.audit_output).resolve() == Path(args.output).resolve():
        parser.error("--audit-output and --output must be different files")
    operations_notes = []
    if args.operations_notes:
        with open(args.operations_notes, encoding="utf-8") as source:
            operations_notes = json.load(source)
    audit = [] if args.audit_output else None
    with open(args.input, encoding="utf-8") as source:
        events = (json.loads(line) for line in source if line.strip())
        result = reconcile(events, audit=audit)
    audit_report = build_audit_report(result, audit, operations_notes) if audit is not None else None
    _write_json(args.output, result)
    if audit_report is not None:
        _write_json(args.audit_output, audit_report)


if __name__ == "__main__":
    main()
