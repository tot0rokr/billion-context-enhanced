"""Build the canonical, public reconciliation report."""

from collections.abc import Iterable, Mapping
from typing import Any


BOARD_FIELDS = ("board", "epoch", "active_slot", "active_digest")
INCIDENT_FIELDS = ("board", "epoch", "sequence", "event_id", "reason")
AUDIT_EVENT_FIELDS = (
    "board",
    "epoch",
    "sequence",
    "event_id",
    "action",
    "tx",
    "slot",
    "digest",
    "success",
    "accepted",
    "reason",
    "active_slot_before",
    "active_digest_before",
    "active_slot_after",
    "active_digest_after",
)
REASON_EXPLANATIONS = {
    "duplicate_conflict": (
        "The event ID has different normalized payloads. All rows for this ID "
        "are excluded from reconciliation; the incident uses its minimum location."
    ),
    "reset_failed": (
        "RESET reported failure and did not itself clear pending transactions. "
        "Any boot epoch advance clears pending state before processing the action."
    ),
    "stage_failed": (
        "STAGE reported failure and left pending transactions unchanged after "
        "any boot epoch advance."
    ),
    "verify_without_stage": (
        "VERIFY has no pending transaction to verify. Under R3, boot epoch "
        "advances clear all pending transactions before processing the event."
    ),
    "verify_failed": (
        "VERIFY reported failure. Under R3, an earlier verified flag on its "
        "pending transaction is cleared; verified image history is retained."
    ),
    "verify_mismatch": (
        "Successful VERIFY named a different slot or digest from its pending "
        "transaction and cleared that transaction's verified flag."
    ),
    "commit_failed": "COMMIT reported failure and did not change the active image.",
    "commit_without_stage": (
        "Successful COMMIT has no pending transaction. Under R3, boot epoch "
        "advances clear all pending transactions before processing the event."
    ),
    "commit_mismatch": (
        "Successful COMMIT named a different slot or digest from its pending "
        "transaction."
    ),
    "commit_unverified": (
        "Successful COMMIT matches its pending transaction, but that transaction "
        "does not have a verified flag."
    ),
    "rollback_failed": "ROLLBACK reported failure and did not change the active image.",
    "rollback_unverified": (
        "Successful ROLLBACK named an exact slot and digest pair absent from "
        "this board's verified image history. A matching digest previously "
        "verified on another slot does not authorize this rollback. Verified "
        "image history survives boot epoch advances."
    ),
}


def build_report(
    boards: Iterable[Mapping[str, Any]],
    incidents: Iterable[Mapping[str, Any]],
    applied_commits: int,
    accepted_rollbacks: int,
    duplicate_replays: int,
    conflicted_ids: int,
) -> dict[str, Any]:
    """Project and sort results without changing the supplied state records.

    Only public fields enter the report, even when callers pass richer internal
    records. An incident is the unit counted by ``rejected_events``.
    """
    board_records = [
        {field: board[field] for field in BOARD_FIELDS} for board in boards
    ]
    board_records.sort(key=lambda board: board["board"])
    incident_records = [
        {field: incident[field] for field in INCIDENT_FIELDS}
        for incident in incidents
    ]
    incident_records.sort(
        key=lambda incident: tuple(incident[field] for field in INCIDENT_FIELDS)
    )
    return {
        "boards": board_records,
        "incidents": incident_records,
        "totals": {
            "board_count": len(board_records),
            "applied_commits": applied_commits,
            "accepted_rollbacks": accepted_rollbacks,
            "duplicate_replays": duplicate_replays,
            "conflicted_ids": conflicted_ids,
            "rejected_events": len(incident_records),
        },
    }


def build_audit_report(
    report: Mapping[str, Any],
    trace: Iterable[Mapping[str, Any]],
    *,
    contract_revision: str = "R3",
) -> dict[str, Any]:
    """Explain actual reconciliation decisions without altering the main report.

    Trace order is execution order, including baseline initialization. R3 uses
    board, epoch, sequence, and event ID, never timestamp. Operation counts use
    retained trace rows only, so excluded conflicts and duplicate replay rows
    are not attempts. Reported success is the input flag; accepted COMMIT and
    ROLLBACK counts describe state-machine decisions, including same-image moves.
    """
    if contract_revision != "R3":
        raise ValueError(
            f"Unsupported audit contract revision: {contract_revision!r}; expected 'R3'."
        )
    events = [{field: event[field] for field in AUDIT_EVENT_FIELDS} for event in trace]
    conflicts = [
        {field: incident[field] for field in INCIDENT_FIELDS}
        for incident in report["incidents"]
        if incident["reason"] == "duplicate_conflict"
    ]
    operations = {}
    for action in ("COMMIT", "ROLLBACK"):
        operation_events = [event for event in events if event["action"] == action]
        accepted = sum(event["accepted"] for event in operation_events)
        operations[action] = {
            "attempted": len(operation_events),
            "reported_success": sum(event["success"] for event in operation_events),
            "accepted": accepted,
            "rejected": len(operation_events) - accepted,
        }
    reasons = sorted({incident["reason"] for incident in report["incidents"]})
    return {
        "contract_revision": contract_revision,
        "events": events,
        "conflicts": conflicts,
        "operations": operations,
        "reason_explanations": {reason: REASON_EXPLANATIONS[reason] for reason in reasons},
    }
