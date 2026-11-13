"""Stable reports and optional audit explanations for rollout reconciliation."""


_REASON_CATALOG = {
    "duplicate_conflict": (
        "One global event ID has different normalized payloads. All rows for "
        "that ID are excluded, and none counts as a replay."
    ),
    "reset_failed": (
        "RESET reported failure; it makes no further state changes after any "
        "epoch-advance clearing of pending transactions."
    ),
    "stage_failed": (
        "STAGE reported failure; it makes no further state changes after any "
        "epoch-advance clearing of pending transactions."
    ),
    "verify_without_stage": (
        "VERIFY has no pending transaction after any epoch-advance clearing. "
        "This takes precedence over reported failure."
    ),
    "verify_failed": (
        "VERIFY reported failure for a pending transaction. R3 clears its "
        "verified flag; verified image history remains unchanged."
    ),
    "verify_mismatch": (
        "Successful VERIFY names a different slot or digest than its pending "
        "transaction. The pending verified flag is cleared; image history remains."
    ),
    "commit_failed": (
        "COMMIT reported failure. This takes precedence over pending-state "
        "validation; it makes no further state changes after any epoch-advance "
        "clearing of pending transactions."
    ),
    "commit_without_stage": (
        "Successful COMMIT has no pending transaction after any epoch-advance clearing."
    ),
    "commit_mismatch": (
        "Successful COMMIT names a different slot or digest than its pending transaction."
    ),
    "commit_unverified": (
        "Successful COMMIT matches its pending image, but that transaction's "
        "verified flag is false."
    ),
    "rollback_failed": (
        "ROLLBACK reported failure; it makes no further state changes after "
        "any epoch-advance clearing of pending transactions."
    ),
    "rollback_unverified": (
        "Successful ROLLBACK names an exact (slot, digest) absent from this "
        "board's verified image history. Digest alone and operational approval "
        "notes do not authorize rollback."
    ),
}

_ACTIONS = ("BASELINE", "COMMIT", "RESET", "ROLLBACK", "STAGE", "VERIFY")
_LOCATION_KEYS = ("board", "epoch", "sequence", "event_id")


def build_report(board_rows, incidents, counters):
    """Project internal records onto the contract's public shape and order."""
    boards = [
        {key: row[key] for key in ("board", "epoch", "active_slot", "active_digest")}
        for row in board_rows
    ]
    boards.sort(key=lambda row: row["board"])
    incident_keys = ("board", "epoch", "sequence", "event_id", "reason")
    rejected = [
        {key: incident[key] for key in incident_keys}
        for incident in incidents
    ]
    rejected.sort(key=lambda incident: tuple(incident[key] for key in incident_keys))
    return {
        "boards": boards,
        "incidents": rejected,
        "totals": {
            "board_count": len(boards),
            "applied_commits": counters["applied_commits"],
            "accepted_rollbacks": counters["accepted_rollbacks"],
            "duplicate_replays": counters["duplicate_replays"],
            "conflicted_ids": counters["conflicted_ids"],
            "rejected_events": len(rejected),
        },
    }


def build_audit(transport, transitions, report):
    """Explain transport disposition and executed transitions separately from R3.

    Action counts describe retained events only: transport replays and globally
    conflicted IDs never execute. Trace order is the supplied state-machine
    execution order, including baseline initialization. R3 orders retained
    events by board, epoch, sequence, and event ID, never wall-clock time.
    pending_before precedes epoch advancement; pending_after_epoch follows its
    mandatory clearing and precedes the action; pending_after follows the action.
    Only the documented audit fields are copied into the artifact.
    """
    transport_keys = _LOCATION_KEYS + ("status", "transport_rows", "duplicate_replays")
    transport_rows = [
        {key: record[key] for key in transport_keys}
        for record in transport
    ]
    transport_rows.sort(key=lambda row: tuple(row[key] for key in _LOCATION_KEYS))
    transition_keys = _LOCATION_KEYS + (
        "action", "tx", "slot", "digest", "reported_success", "outcome", "reason",
        "verified_image_added", "epoch_before", "epoch_advanced",
    )
    trace = []
    per_action = {
        action: {key: 0 for key in ("attempted", "reported_success", "accepted", "rejected", "ignored")}
        for action in _ACTIONS
    }
    for transition in transitions:
        row = {key: transition[key] for key in transition_keys}
        for key in ("active_before", "active_after"):
            row[key] = {field: transition[key][field] for field in ("slot", "digest")}
        for key in ("pending_before", "pending_after_epoch", "pending_after"):
            row[key] = [
                {field: pending[field] for field in ("tx", "slot", "digest", "verified")}
                for pending in transition[key]
            ]
        trace.append(row)
        counts = per_action.setdefault(row["action"], {
            key: 0 for key in ("attempted", "reported_success", "accepted", "rejected", "ignored")
        })
        counts["attempted"] += 1
        counts["reported_success"] += int(row["reported_success"])
        counts[row["outcome"]] += 1

    summary = dict(report["totals"])
    summary.update({
        "input_rows": sum(row["transport_rows"] for row in transport_rows),
        "retained_events": sum(row["status"] == "retained" for row in transport_rows),
        "conflicted_rows": sum(
            row["transport_rows"] for row in transport_rows if row["status"] == "conflict"
        ),
    })
    return {
        "contract": "R3",
        "summary": summary,
        "transport": transport_rows,
        "transitions": trace,
        "per_action": {action: per_action[action] for action in sorted(per_action)},
        "reason_catalog": dict(sorted(_REASON_CATALOG.items())),
    }
