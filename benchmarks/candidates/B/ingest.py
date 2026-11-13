"""Normalize incident evidence and eliminate event-ID replays/conflicts.

R2 ignores timestamps for payload identity, execution ordering, and state.
When identical payloads report different timestamps, retain the minimum one
only as inert metadata so ingestion remains independent of input row order.
Retained events are ordered by (board, epoch, sequence, event_id).
"""

from collections import defaultdict


_PAYLOAD_FIELDS = (
    "event_id", "board", "epoch", "sequence", "action", "tx", "slot",
    "digest", "success",
)


def normalize_event(raw: dict) -> dict:
    """Return one canonical event from a schema 1 or schema 2 input row."""
    schema = raw.get("schema", 2 if "id" in raw else 1)
    if schema == 1:
        names = {
            "event_id": "event_id", "board": "board", "epoch": "epoch",
            "sequence": "sequence", "action": "action", "tx": "tx",
            "digest": "digest", "success": "success", "timestamp": "time",
        }
        slots = {0: "A", 1: "B", None: None}
    elif schema == 2:
        names = {
            "event_id": "id", "board": "device", "epoch": "boot",
            "sequence": "seq", "action": "kind", "tx": "transaction",
            "digest": "sha256", "success": "ok", "timestamp": "timestamp",
        }
        slots = {"A": "A", "B": "B", None: None}
    else:
        raise ValueError(f"Unsupported schema: {schema!r}")

    event = {
        key: raw.get(source) if key in ("tx", "digest") else raw[source]
        for key, source in names.items()
    }
    event["action"] = event["action"].upper()
    slot = raw.get("slot")
    if slot not in slots:
        raise ValueError(f"Invalid slot for schema {schema}: {slot!r}")
    event["slot"] = slots[slot]
    return event


def _location(event: dict) -> tuple:
    return event["board"], event["epoch"], event["sequence"], event["event_id"]


def ingest_events(events) -> tuple:
    """Return (retained events, conflict incidents, replay count, conflict count).

    IDs are global across boards and epochs. A conflicting ID contributes one
    incident at its minimum location and no replay count, regardless of how
    many copies of its distinct payloads were present.
    """
    groups = defaultdict(list)
    for raw in events:
        event = normalize_event(raw)
        groups[event["event_id"]].append(event)

    retained = []
    conflicts = []
    duplicate_replays = 0
    for rows in groups.values():
        payloads = {tuple(row[field] for field in _PAYLOAD_FIELDS) for row in rows}
        if len(payloads) > 1:
            location = min(rows, key=_location)
            conflicts.append({
                "board": location["board"],
                "epoch": location["epoch"],
                "sequence": location["sequence"],
                "event_id": location["event_id"],
                "reason": "duplicate_conflict",
            })
        else:
            retained.append(min(rows, key=lambda row: row["timestamp"]))
            duplicate_replays += len(rows) - 1

    # R2 canonical order never consults the retained timestamp metadata.
    retained.sort(key=_location)
    conflicts.sort(key=_location)
    return retained, conflicts, duplicate_replays, len(conflicts)
