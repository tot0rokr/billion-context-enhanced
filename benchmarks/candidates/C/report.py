"""Project reconciliation results into the deterministic public report."""


BOARD_FIELDS = ("board", "epoch", "active_slot", "active_digest")
INCIDENT_FIELDS = ("board", "epoch", "sequence", "event_id", "reason")
OUTCOME_FIELDS = (
    "board", "epoch", "sequence", "event_id", "action", "tx", "slot",
    "digest", "success", "outcome", "reason", "active_slot", "active_digest",
)
OPERATIONS_NOTE_FIELDS = ("note_id", "operation_id", "field", "value")


def build_report(boards, incidents, transition_counts, ingestion_counts):
    """Return only public fields, with stable ordering and derived counts.

    ``boards`` and ``incidents`` are iterables of mappings. Projection also
    prevents internal state, timestamps, or source metadata from leaking into
    the output and leaves the supplied mappings untouched.
    """
    board_rows = [{field: board[field] for field in BOARD_FIELDS}
                  for board in boards]
    board_rows.sort(key=lambda board: board["board"])
    incident_rows = [{field: incident[field] for field in INCIDENT_FIELDS}
                     for incident in incidents]
    incident_rows.sort(
        key=lambda incident: tuple(incident[field] for field in INCIDENT_FIELDS)
    )
    return {
        "boards": board_rows,
        "incidents": incident_rows,
        "totals": {
            "board_count": len(board_rows),
            "applied_commits": transition_counts["applied_commits"],
            "accepted_rollbacks": transition_counts["accepted_rollbacks"],
            "duplicate_replays": ingestion_counts["duplicate_replays"],
            "conflicted_ids": ingestion_counts["conflicted_ids"],
            "rejected_events": len(incident_rows),
        },
    }


def build_audit_report(report, outcomes, operations_notes):
    """Build a separate R3 audit without changing the public report schema.

    Outcomes contain one row per retained normalized event in execution order
    under R3's (board, epoch, sequence, event_id) ordering, never by timestamp.
    The state machine clears pending transactions on epoch advances while
    preserving the active image and exact (slot, digest) verification history.
    Attempts count retained COMMIT/ROLLBACK events, including rejected events;
    transport replays and all rows with conflicted IDs have already been
    removed. Accepted identifiers require both the corresponding action and
    an accepted outcome, so successful staging or verification is not a commit.

    Operations notes are inert records. Their values are copied without being
    interpreted as event data or transition instructions. Cases cover the
    public report's boards and incident locations, with null final state for
    a board represented only by an incident.
    """
    final_states = {
        row["board"]: {field: row[field] for field in BOARD_FIELDS}
        for row in report["boards"]
    }
    board_names = set(final_states)
    board_names.update(row["board"] for row in report["incidents"])
    cases = {
        board: {
            "board": board,
            "final_state": final_states.get(board),
            "accepted_commit_ids": [],
            "accepted_rollback_ids": [],
            "attempts": {"COMMIT": 0, "ROLLBACK": 0},
            "incidents": [],
            "events": [],
        }
        for board in sorted(board_names)
    }
    for incident in report["incidents"]:
        cases[incident["board"]]["incidents"].append({
            field: incident[field] for field in INCIDENT_FIELDS
        })
    for case in cases.values():
        case["incidents"].sort(
            key=lambda incident: tuple(incident[field] for field in INCIDENT_FIELDS)
        )

    for outcome in outcomes:
        case = cases.get(outcome["board"])
        if case is None:
            continue
        case["events"].append({field: outcome[field] for field in OUTCOME_FIELDS})
        action = outcome["action"]
        if action in case["attempts"]:
            case["attempts"][action] += 1
            if outcome["outcome"] == "accepted":
                identifiers = ("accepted_commit_ids" if action == "COMMIT"
                               else "accepted_rollback_ids")
                case[identifiers].append(outcome["event_id"])

    notes = [{field: note[field] for field in OPERATIONS_NOTE_FIELDS}
             for note in operations_notes]
    notes.sort(key=lambda note: note["note_id"])
    return {"contract": "R3", "operations_notes": notes, "cases": list(cases.values())}
