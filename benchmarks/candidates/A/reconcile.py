#!/usr/bin/env python3
"""Reconstruct rollout incidents from schema 1 and schema 2 JSONL events."""

import argparse
import json
from pathlib import Path

from ingest import ingest_events
from report import build_audit, build_report
from state_machine import reconstruct


def reconcile(events):
    """Return a deterministic report under the current README contract."""
    return _reconcile(events, audit_enabled=False)[0]


def reconcile_with_audit(events):
    """Return the contract report and a separate explanatory audit record."""
    return _reconcile(events, audit_enabled=True)


def _reconcile(events, *, audit_enabled):
    transport = [] if audit_enabled else None
    transitions = [] if audit_enabled else None
    accepted, conflicts, ingest_counts = ingest_events(events, audit=transport)
    boards, incidents, state_counts = reconstruct(accepted, audit=transitions)
    report = build_report(
        boards,
        conflicts + incidents,
        {**ingest_counts, **state_counts},
    )
    audit = build_audit(transport, transitions, report) if audit_enabled else None
    return report, audit


def _write_json(path, value):
    with open(path, "w", encoding="utf-8") as target:
        json.dump(value, target, sort_keys=True, indent=2)
        target.write("\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--audit-output",
        help="optional separate JSON report of transport evidence and transitions",
    )
    args = parser.parse_args()
    if args.audit_output and Path(args.audit_output).resolve() == Path(args.output).resolve():
        parser.error("--audit-output must differ from --output")
    with open(args.input, encoding="utf-8") as source:
        events = (json.loads(line) for line in source if line.strip())
        result, audit = _reconcile(events, audit_enabled=bool(args.audit_output))
    _write_json(args.output, result)
    if args.audit_output:
        _write_json(args.audit_output, audit)


if __name__ == "__main__":
    main()
