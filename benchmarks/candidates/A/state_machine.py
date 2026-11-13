"""Reconstruct per-board rollout state under revised contract R3.

Execution follows board, epoch, sequence, and event ID; clocks are ignored.
Epoch advances clear all pending transactions before the next event, retaining
the active image and exact verified image history. A failed VERIFY clears the
affected transaction's verified flag but retains its staged image and history.
"""

from collections import defaultdict
from dataclasses import dataclass


@dataclass
class _Pending:
    slot: object
    digest: object
    verified: bool = False


def _order(event):
    return (
        event["epoch"],
        event["sequence"],
        event["event_id"],
    )


def _incident(event, reason):
    return {
        "board": event["board"],
        "epoch": event["epoch"],
        "sequence": event["sequence"],
        "event_id": event["event_id"],
        "reason": reason,
    }


def _pending_snapshot(pending):
    """Return independent transaction rows, with null transaction IDs first."""
    return [
        {
            "tx": tx,
            "slot": pending[tx].slot,
            "digest": pending[tx].digest,
            "verified": pending[tx].verified,
        }
        for tx in sorted(pending, key=lambda value: (value is not None, value or ""))
    ]


def reconstruct(events, *, audit=None):
    """Return board rows, incidents, and transition counters.

    Events must already be schema-normalized and globally deduplicated. A
    baseline excluded by a duplicate conflict leaves the active image unknown
    (null/null) and history empty; surviving events can still be reconciled.
    BASELINE is initialization only. The input contract otherwise guarantees
    exactly one successful baseline per board.

    If audit is a caller-supplied list, append transition snapshots in actual
    execution order: board, epoch, sequence, and event ID. A valid board's
    successful baseline precedes its other events in that same order.
    Audit collection does not change reconstruction or its return signature.
    pending_before precedes any epoch advance, pending_after_epoch follows the
    automatic clear, and pending_after follows the event's own transition.
    """
    grouped = defaultdict(list)
    for event in events:
        grouped[event["board"]].append(event)

    boards = []
    incidents = []
    counters = {"applied_commits": 0, "accepted_rollbacks": 0}

    for board, board_events in sorted(grouped.items()):
        ordered = sorted(board_events, key=_order)
        baseline = next(
            (
                event
                for event in ordered
                if event["action"] == "BASELINE" and event["success"]
            ),
            None,
        )
        active_slot = None
        active_digest = None
        epoch = ordered[0]["epoch"]
        verified_history = set()
        pending = {}

        for event in ordered:
            epoch_before = epoch
            epoch_advanced = event["epoch"] > epoch
            action = event["action"]
            successful = event["success"]
            tx = event["tx"]
            image = (event["slot"], event["digest"])
            reason = None
            outcome = "accepted"
            verified_image_added = False
            if audit is not None:
                active_before = {"slot": active_slot, "digest": active_digest}
                pending_before = _pending_snapshot(pending)

            if epoch_advanced:
                pending.clear()
                epoch = event["epoch"]
            if audit is not None:
                pending_after_epoch = _pending_snapshot(pending)

            if action == "BASELINE":
                if event is baseline:
                    active_slot, active_digest = image
                    verified_image_added = image not in verified_history
                    verified_history.add(image)
                else:
                    outcome = "ignored"

            elif action == "RESET":
                if successful:
                    pending.clear()
                else:
                    reason = "reset_failed"

            elif action == "STAGE":
                if successful:
                    pending[tx] = _Pending(*image)
                else:
                    reason = "stage_failed"

            elif action == "VERIFY":
                staged = pending.get(tx)
                # Missing stage takes precedence, including for failed VERIFY.
                if staged is None:
                    reason = "verify_without_stage"
                elif not successful:
                    staged.verified = False
                    reason = "verify_failed"
                elif image != (staged.slot, staged.digest):
                    staged.verified = False
                    reason = "verify_mismatch"
                else:
                    staged.verified = True
                    verified_image_added = image not in verified_history
                    verified_history.add(image)

            elif action == "COMMIT":
                staged = pending.get(tx)
                if not successful:
                    reason = "commit_failed"
                elif staged is None:
                    reason = "commit_without_stage"
                elif image != (staged.slot, staged.digest):
                    reason = "commit_mismatch"
                elif not staged.verified:
                    reason = "commit_unverified"
                else:
                    active_slot, active_digest = image
                    counters["applied_commits"] += 1
                    del pending[tx]

            elif action == "ROLLBACK":
                if not successful:
                    reason = "rollback_failed"
                elif image not in verified_history:
                    reason = "rollback_unverified"
                else:
                    active_slot, active_digest = image
                    counters["accepted_rollbacks"] += 1
                    pending.clear()
            else:
                outcome = "ignored"

            if reason is not None:
                outcome = "rejected"
                incidents.append(_incident(event, reason))

            if audit is not None:
                audit.append({
                    "board": board,
                    "epoch": event["epoch"],
                    "epoch_before": epoch_before,
                    "epoch_advanced": epoch_advanced,
                    "sequence": event["sequence"],
                    "event_id": event["event_id"],
                    "action": action,
                    "tx": tx,
                    "slot": event["slot"],
                    "digest": event["digest"],
                    "reported_success": successful,
                    "outcome": outcome,
                    "reason": reason,
                    "active_before": active_before,
                    "active_after": {"slot": active_slot, "digest": active_digest},
                    "pending_before": pending_before,
                    "pending_after_epoch": pending_after_epoch,
                    "pending_after": _pending_snapshot(pending),
                    "verified_image_added": verified_image_added,
                })

        boards.append(
            {
                "board": board,
                "epoch": epoch,
                "active_slot": active_slot,
                "active_digest": active_digest,
            }
        )

    incidents.sort(
        key=lambda incident: (
            incident["board"],
            incident["epoch"],
            incident["sequence"],
            incident["event_id"],
            incident["reason"],
        )
    )
    return boards, incidents, counters
