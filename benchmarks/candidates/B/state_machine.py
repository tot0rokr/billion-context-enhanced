"""Apply the current R3 rollout transition rules to canonical events.

Ingestion has already normalized and deduplicated these events. Wall-clock
timestamps never participate in state ordering. If conflict exclusion
removes a board's baseline, its active image starts as null and the remaining
events still participate in reconciliation.
"""

from collections import defaultdict
from dataclasses import dataclass


@dataclass
class PendingImage:
    slot: str | None
    digest: str | None
    verified: bool = False


def _event_order(event):
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


def _trace_record(event, before, after, reason):
    record = {
        field: event[field]
        for field in (
            "board", "epoch", "sequence", "event_id", "action", "tx",
            "slot", "digest", "success",
        )
    }
    record.update({
        "accepted": reason is None,
        "reason": reason,
        "active_slot_before": before[0],
        "active_digest_before": before[1],
        "active_slot_after": after[0],
        "active_digest_after": after[1],
    })
    return record


def reconcile_states(events, *, trace=None):
    """Return (boards, incidents, applied_commits, accepted_rollbacks).

    A successful baseline initializes each board before its other events.
    Subsequent processing follows epoch, sequence, and event ID. Advancing
    epochs clears all pending transactions while retaining the active image
    and verified history. Failed VERIFY clears its transaction's verified
    flag without erasing verified history.
    If trace is a list, append a fresh audit record for every processed event
    in execution order. An event's reported success and its acceptance by
    these rules are separate fields. The ordinary return value is unchanged.
    """
    by_board = defaultdict(list)
    for event in events:
        by_board[event["board"]].append(event)

    boards = []
    incidents = []
    applied_commits = 0
    accepted_rollbacks = 0

    for board, board_events in sorted(by_board.items()):
        ordered = sorted(board_events, key=_event_order)
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
        history = set()
        pending = {}

        if baseline is not None:
            active_slot = baseline["slot"]
            active_digest = baseline["digest"]
            epoch = baseline["epoch"]
            history.add((active_slot, active_digest))
            if trace is not None:
                trace.append(_trace_record(
                    baseline, (None, None), (active_slot, active_digest), None,
                ))

        for event in ordered:
            if event is baseline:
                continue
            # R3: a boot boundary clears pending before evaluating its event,
            # regardless of that event's reported success or acceptance.
            if event["epoch"] > epoch:
                pending.clear()
                epoch = event["epoch"]
            action = event["action"]
            success = event["success"]
            tx = event["tx"]
            image = (event["slot"], event["digest"])
            staged = pending.get(tx)
            reason = None
            before = (active_slot, active_digest)

            if action == "RESET":
                if success:
                    pending.clear()
                else:
                    reason = "reset_failed"
            elif action == "STAGE":
                if success:
                    pending[tx] = PendingImage(*image)
                else:
                    reason = "stage_failed"
            elif action == "VERIFY":
                if staged is None:
                    reason = "verify_without_stage"
                elif not success:
                    # R2: failure clears this transaction's earlier verification.
                    staged.verified = False
                    reason = "verify_failed"
                elif image != (staged.slot, staged.digest):
                    staged.verified = False
                    reason = "verify_mismatch"
                else:
                    staged.verified = True
                    history.add(image)
            elif action == "COMMIT":
                if not success:
                    reason = "commit_failed"
                elif staged is None:
                    reason = "commit_without_stage"
                elif image != (staged.slot, staged.digest):
                    reason = "commit_mismatch"
                elif not staged.verified:
                    reason = "commit_unverified"
                else:
                    active_slot, active_digest = image
                    applied_commits += 1
                    del pending[tx]
            elif action == "ROLLBACK":
                if not success:
                    reason = "rollback_failed"
                elif image not in history:
                    reason = "rollback_unverified"
                else:
                    active_slot, active_digest = image
                    accepted_rollbacks += 1
                    pending.clear()
            else:
                # The input contract provides exactly one successful
                # BASELINE and otherwise only the actions handled above.
                raise ValueError(f"Unexpected action {action!r} for {event['event_id']!r}")

            if reason is not None:
                incidents.append(_incident(event, reason))
            if trace is not None:
                trace.append(_trace_record(
                    event, before, (active_slot, active_digest), reason,
                ))

        boards.append(
            {
                "board": board,
                "epoch": epoch,
                "active_slot": active_slot,
                "active_digest": active_digest,
            }
        )

    return boards, incidents, applied_commits, accepted_rollbacks
