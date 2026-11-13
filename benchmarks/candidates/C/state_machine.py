"""Apply normalized rollout events under the R3 contract."""

from collections import defaultdict
from dataclasses import dataclass, field


@dataclass
class _BoardState:
    epoch: int
    active_slot: object = None
    active_digest: object = None
    pending: dict = field(default_factory=dict)
    verified_images: set = field(default_factory=set)


def _incident(event, reason):
    return {
        "board": event["board"],
        "epoch": event["epoch"],
        "sequence": event["sequence"],
        "event_id": event["event_id"],
        "reason": reason,
    }


def _audit_outcome(state, event, reason):
    return {
        "board": event["board"],
        "epoch": event["epoch"],
        "sequence": event["sequence"],
        "event_id": event["event_id"],
        "action": event["action"],
        "tx": event["tx"],
        "slot": event["slot"],
        "digest": event["digest"],
        "success": event["success"],
        "outcome": "accepted" if reason is None else "rejected",
        "reason": reason,
        "active_slot": state.active_slot,
        "active_digest": state.active_digest,
    }


def _apply_event(state, event, counts):
    """Apply one non-baseline event, returning its rejection reason if any."""
    action = event["action"]
    success = event["success"]
    tx = event["tx"]
    image = (event["slot"], event["digest"])

    if action == "RESET":
        if not success:
            return "reset_failed"
        state.pending.clear()
        return None

    if action == "STAGE":
        if not success:
            return "stage_failed"
        state.pending[tx] = {"image": image, "verified": False}
        return None

    if action == "VERIFY":
        pending = state.pending.get(tx)
        if pending is None:
            return "verify_without_stage"
        if not success:
            pending["verified"] = False
            return "verify_failed"
        if pending["image"] != image:
            pending["verified"] = False
            return "verify_mismatch"
        pending["verified"] = True
        state.verified_images.add(image)
        return None

    if action == "COMMIT":
        if not success:
            return "commit_failed"
        pending = state.pending.get(tx)
        if pending is None:
            return "commit_without_stage"
        if pending["image"] != image:
            return "commit_mismatch"
        if not pending["verified"]:
            return "commit_unverified"
        state.active_slot, state.active_digest = image
        counts["applied_commits"] += 1
        del state.pending[tx]
        return None

    if action == "ROLLBACK":
        if not success:
            return "rollback_failed"
        if image not in state.verified_images:
            return "rollback_unverified"
        state.active_slot, state.active_digest = image
        counts["accepted_rollbacks"] += 1
        state.pending.clear()
        return None

    raise ValueError("Unknown rollout action: {!r}".format(action))


def apply_events(events, *, audit=None):
    """Return (boards, incidents, counts) for normalized, deduplicated events.

    A baseline initializes the board before any ordinary events. R3 then
    orders epochs numerically and events within each epoch by sequence and
    event ID. Reported timestamps never affect execution. Epoch advances
    clear all pending state before the new epoch's first event, while the
    active image and verification history survive.

    A board whose baseline was excluded by ID conflict starts with a null
    active image and empty verification history.

    If audit is a supplied list, append one outcome per retained event in
    execution order, including the baseline and the active image after each
    event. This leaves the standard return value unchanged.
    """
    grouped = defaultdict(list)
    for event in events:
        grouped[event["board"]].append(event)

    boards = []
    incidents = []
    counts = {"applied_commits": 0, "accepted_rollbacks": 0}
    for board in sorted(grouped):
        board_events = grouped[board]
        baselines = [event for event in board_events if event["action"] == "BASELINE"]
        if len(baselines) > 1 or (baselines and not baselines[0]["success"]):
            raise ValueError("Board {!r} must have a single successful BASELINE".format(board))

        if baselines:
            baseline = baselines[0]
            state = _BoardState(
                epoch=baseline["epoch"],
                active_slot=baseline["slot"],
                active_digest=baseline["digest"],
            )
            state.verified_images.add((state.active_slot, state.active_digest))
            if audit is not None:
                audit.append(_audit_outcome(state, baseline, None))
        else:
            state = _BoardState(epoch=min(event["epoch"] for event in board_events))

        ordered = sorted(
            (event for event in board_events if event["action"] != "BASELINE"),
            key=lambda event: (
                event["epoch"], event["sequence"], event["event_id"]
            ),
        )
        for event in ordered:
            if event["epoch"] > state.epoch:
                state.pending.clear()
                state.epoch = event["epoch"]
            reason = _apply_event(state, event, counts)
            if reason is not None:
                incidents.append(_incident(event, reason))
            if audit is not None:
                audit.append(_audit_outcome(state, event, reason))

        boards.append({
            "board": board,
            "epoch": state.epoch,
            "active_slot": state.active_slot,
            "active_digest": state.active_digest,
        })

    return boards, incidents, counts
