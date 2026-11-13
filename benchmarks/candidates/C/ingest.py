"""Normalize rollout event schemas and resolve globally duplicated event IDs."""

from dataclasses import dataclass


_PAYLOAD_FIELDS = (
    "event_id", "board", "epoch", "sequence", "action", "tx", "slot",
    "digest", "success",
)
_LOCATION_FIELDS = ("board", "epoch", "sequence", "event_id")


@dataclass
class _EventGroup:
    event: dict
    location: tuple
    row_count: int = 1
    conflicted: bool = False


def normalize_event(row):
    """Return the common event representation for one schema 1 or 2 row."""
    schema = row["schema"]
    if schema == 1:
        slot = row.get("slot")
        if slot not in (None, 0, 1):
            raise ValueError("schema 1 slot must be 0, 1, or null")
        return {
            "event_id": row["event_id"],
            "board": row["board"],
            "epoch": row["epoch"],
            "sequence": row["sequence"],
            "action": row["action"].upper(),
            "tx": row.get("tx"),
            "slot": {0: "A", 1: "B", None: None}[slot],
            "digest": row.get("digest"),
            "success": row["success"],
            "timestamp": row["time"],
        }
    if schema == 2:
        slot = row.get("slot")
        if slot not in (None, "A", "B"):
            raise ValueError("schema 2 slot must be A, B, or null")
        return {
            "event_id": row["id"],
            "board": row["device"],
            "epoch": row["boot"],
            "sequence": row["seq"],
            "action": row["kind"].upper(),
            "tx": row.get("transaction"),
            "slot": slot,
            "digest": row.get("sha256"),
            "success": row["ok"],
            "timestamp": row["timestamp"],
        }
    raise ValueError("unsupported event schema: {!r}".format(schema))


def _location(event):
    return tuple(event[field] for field in _LOCATION_FIELDS)


def ingest_events(rows):
    """Return (normalized events, duplicate incidents, duplicate counts).

    R2 orders events by (board, epoch, sequence, event_id). Timestamp is
    excluded from both ordering and replay equivalence. The earliest reported
    timestamp remains inert metadata for a replay group, making the returned
    representation independent of input order. Each ID retains one aggregate,
    so repeated transport rows do not grow ingestion memory.
    """
    groups = {}
    for row in rows:
        event = normalize_event(row)
        event_id = event["event_id"]
        location = _location(event)
        if event_id not in groups:
            groups[event_id] = _EventGroup(event, location)
            continue

        group = groups[event_id]
        group.row_count += 1
        group.location = min(group.location, location)
        # A later replay cannot revive an ID after any conflicting payload.
        if not group.conflicted:
            group.conflicted = any(
                event[field] != group.event[field] for field in _PAYLOAD_FIELDS
            )
            if not group.conflicted and event["timestamp"] < group.event["timestamp"]:
                group.event = event

    events = []
    incidents = []
    counts = {"duplicate_replays": 0, "conflicted_ids": 0}
    for group in groups.values():
        if group.conflicted:
            counts["conflicted_ids"] += 1
            incident = dict(zip(_LOCATION_FIELDS, group.location))
            incident["reason"] = "duplicate_conflict"
            incidents.append(incident)
        else:
            counts["duplicate_replays"] += group.row_count - 1
            events.append(group.event)

    events.sort(key=_location)
    incidents.sort(key=lambda incident: _location(incident) + (incident["reason"],))
    return events, incidents, counts
