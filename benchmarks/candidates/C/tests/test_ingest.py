import itertools
import unittest

from ingest import ingest_events, normalize_event


def event(event_id="event-1", **changes):
    row = {
        "schema": 1, "event_id": event_id, "board": "board-a", "epoch": 0,
        "sequence": 1, "action": "STAGE", "tx": "tx", "slot": 1,
        "digest": "image", "success": True, "time": 20,
    }
    row.update(changes)
    return row


class IngestContract(unittest.TestCase):
    def test_cross_schema_replay_ignores_timestamp_and_uses_earliest(self):
        schema_two = {
            "schema": 2, "id": "event-1", "device": "board-a", "boot": 0,
            "seq": 1, "kind": "stage", "transaction": "tx", "slot": "B",
            "sha256": "image", "ok": True, "timestamp": 10,
        }
        events, incidents, counts = ingest_events([event(), schema_two, event()])
        self.assertEqual(events, [dict(normalize_event(event()), timestamp=10)])
        self.assertEqual(incidents, [])
        self.assertEqual(counts, {"duplicate_replays": 2, "conflicted_ids": 0})

    def test_missing_optional_fields_normalize_to_null(self):
        first = event()
        for field in ("tx", "slot", "digest"):
            del first[field]
        second = {
            "schema": 2, "id": "event-1", "device": "board-a", "boot": 0,
            "seq": 1, "kind": "stage", "ok": True, "timestamp": 20,
        }
        events, incidents, counts = ingest_events([first, second])
        self.assertEqual(len(events), 1)
        self.assertEqual([events[0][field] for field in ("tx", "slot", "digest")],
                         [None, None, None])
        self.assertEqual(incidents, [])
        self.assertEqual(counts["duplicate_replays"], 1)

    def test_global_conflict_discards_replays_and_uses_minimum_location(self):
        first = event(board="board-z", sequence=0)
        second = event(board="board-a", epoch=2, sequence=5)
        third = event(board="board-a", epoch=1, sequence=10)
        events, incidents, counts = ingest_events([first, first, second, third])
        self.assertEqual(events, [])
        self.assertEqual(incidents, [{
            "board": "board-a", "epoch": 1, "sequence": 10,
            "event_id": "event-1", "reason": "duplicate_conflict",
        }])
        self.assertEqual(counts, {"duplicate_replays": 0, "conflicted_ids": 1})

    def test_payload_differences_conflict(self):
        changes = {
            "board": "board-b", "epoch": 1, "sequence": 2, "action": "VERIFY",
            "tx": "other", "slot": 0, "digest": "other", "success": False,
        }
        for field, value in changes.items():
            with self.subTest(field=field):
                events, incidents, counts = ingest_events([event(), event(**{field: value})])
                self.assertEqual(events, [])
                self.assertEqual(len(incidents), 1)
                self.assertEqual(counts["conflicted_ids"], 1)

    def test_late_conflict_discards_prior_replays_and_tracks_later_minimum(self):
        repeated = event(board="board-z")
        rows = itertools.chain(
            itertools.repeat(repeated, 64),
            [event(board="board-z", digest="conflict"), repeated,
             event(board="board-a", epoch=2), event(board="board-a", epoch=1),
             event("survivor"), event("survivor", time=10)],
        )
        events, incidents, counts = ingest_events(rows)
        self.assertEqual(events, [normalize_event(event("survivor", time=10))])
        self.assertEqual(incidents, [{
            "board": "board-a", "epoch": 1, "sequence": 1,
            "event_id": "event-1", "reason": "duplicate_conflict",
        }])
        self.assertEqual(counts, {"duplicate_replays": 1, "conflicted_ids": 1})

    def test_input_order_does_not_affect_results(self):
        rows = [event(), event(time=10), event("event-2", time=15),
                event("conflict", digest="one"), event("conflict", digest="two")]
        expected = ingest_events(rows)
        for permutation in itertools.permutations(rows):
            self.assertEqual(ingest_events(permutation), expected)

    def test_sequence_order_ignores_clock_skew(self):
        rows = [
            event("other-board", board="board-b", sequence=0, time=-100),
            event("later-epoch", epoch=1, sequence=0, time=-1000),
            event("later-sequence", sequence=2, time=-1),
            event("earlier-sequence", sequence=1, time=9999),
        ]
        events, incidents, counts = ingest_events(rows)
        self.assertEqual([item["event_id"] for item in events], [
            "earlier-sequence", "later-sequence", "later-epoch", "other-board",
        ])
        self.assertEqual(incidents, [])
        self.assertEqual(counts, {"duplicate_replays": 0, "conflicted_ids": 0})

    def test_sequence_ties_use_event_id_with_skewed_or_equal_timestamps(self):
        for first_time, second_time in ((9999, -1), (20, 20)):
            with self.subTest(first_time=first_time, second_time=second_time):
                rows = [event("event-b", time=second_time),
                        event("event-a", time=first_time)]
                events, _, _ = ingest_events(rows)
                self.assertEqual([item["event_id"] for item in events],
                                 ["event-a", "event-b"])
                self.assertEqual(ingest_events(reversed(rows)), ingest_events(rows))

    def test_empty_input(self):
        self.assertEqual(ingest_events([]), (
            [], [], {"duplicate_replays": 0, "conflicted_ids": 0},
        ))


if __name__ == "__main__":
    unittest.main()
