"""Normalize rollout events and reconcile globally repeated event IDs."""


_PAYLOAD_FIELDS = (
    "event_id",
    "board",
    "epoch",
    "sequence",
    "action",
    "tx",
    "slot",
    "digest",
    "success",
)
_LOCATION_FIELDS = ("board", "epoch", "sequence", "event_id")


def normalize_event(raw):
    """Return the nine payload fields, excluding ignored transport clocks."""
    schema = raw["schema"]
    if schema == 1:
        return {
            "event_id": raw["event_id"],
            "board": raw["board"],
            "epoch": raw["epoch"],
            "sequence": raw["sequence"],
            "action": raw["action"].upper(),
            "tx": raw.get("tx"),
            "slot": {0: "A", 1: "B", None: None}[raw.get("slot")],
            "digest": raw.get("digest"),
            "success": raw["success"],
        }
    if schema == 2:
        return {
            "event_id": raw["id"],
            "board": raw["device"],
            "epoch": raw["boot"],
            "sequence": raw["seq"],
            "action": raw["kind"].upper(),
            "tx": raw.get("transaction"),
            "slot": raw.get("slot"),
            "digest": raw.get("sha256"),
            "success": raw["ok"],
        }
    raise ValueError("unsupported event schema: {!r}".format(schema))


def _location(event):
    return tuple(event[key] for key in _LOCATION_FIELDS)


def ingest_events(raw_events, *, audit=None):
    """Return accepted events, duplicate conflicts, and deduplication counts.

    Timestamps are ignored entirely under R2. Identical normalized payloads
    are interchangeable, and retained events are ordered by canonical location.
    Conflict classification happens before any replay rows are counted. Only
    one representative per ID is kept, so replay volume does not grow memory.
    If supplied, ``audit`` receives one transport-count record per global ID,
    sorted by canonical location, without event payloads or timestamps.
    """
    groups = {}
    for raw in raw_events:
        event = normalize_event(raw)
        location = _location(event)
        event_id = event["event_id"]
        if event_id not in groups:
            groups[event_id] = {
                "event": event,
                "payload": tuple(event[field] for field in _PAYLOAD_FIELDS),
                "location": location,
                "transport_rows": 1,
                "conflict": False,
            }
            continue

        group = groups[event_id]
        group["transport_rows"] += 1
        group["location"] = min(group["location"], location)
        if group["conflict"]:
            continue

        payload = tuple(event[field] for field in _PAYLOAD_FIELDS)
        if payload != group["payload"]:
            group["conflict"] = True
            # Conflicts are permanent; subsequent copies only affect counts
            # and the minimum incident location.
            group["event"] = None
            group["payload"] = None

    accepted = []
    incidents = []
    audit_records = []
    counters = {"duplicate_replays": 0, "conflicted_ids": 0}
    for group in groups.values():
        if group["conflict"]:
            counters["conflicted_ids"] += 1
            incident = dict(zip(_LOCATION_FIELDS, group["location"]))
            incident["reason"] = "duplicate_conflict"
            incidents.append(incident)
            duplicate_replays = 0
        else:
            duplicate_replays = group["transport_rows"] - 1
            counters["duplicate_replays"] += duplicate_replays
            accepted.append(group["event"])

        if audit is not None:
            record = dict(zip(_LOCATION_FIELDS, group["location"]))
            record.update({
                "status": "conflict" if group["conflict"] else "retained",
                "transport_rows": group["transport_rows"],
                "duplicate_replays": duplicate_replays,
            })
            audit_records.append(record)

    accepted.sort(key=_location)
    incidents.sort(key=_location)
    if audit is not None:
        audit.extend(sorted(audit_records, key=_location))
    return accepted, incidents, counters
