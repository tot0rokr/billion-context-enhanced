import itertools
import json
import random
import unittest
from pathlib import Path

from ingest import ingest_events, normalize_event


def schema_one(**updates):
    event = {
        "schema": 1, "event_id": "event-1", "board": "board-b", "epoch": 2,
        "sequence": 3, "action": "STAGE", "tx": "tx-1", "slot": 1,
        "digest": "image", "success": True, "time": 10,
    }
    event.update(updates)
    return event


def schema_two(**updates):
    event = {
        "schema": 2, "id": "event-1", "device": "board-b", "boot": 2,
        "seq": 3, "kind": "stage", "transaction": "tx-1", "slot": "B",
        "sha256": "image", "ok": True, "timestamp": 10,
    }
    event.update(updates)
    return event


class IngestContract(unittest.TestCase):
    def test_schema_equivalence_and_canonical_fields(self):
        expected = {
            "event_id": "event-1", "board": "board-b", "epoch": 2,
            "sequence": 3, "action": "STAGE", "tx": "tx-1", "slot": "B",
            "digest": "image", "success": True, "timestamp": 10,
        }
        self.assertEqual(normalize_event(schema_one()), expected)
        self.assertEqual(normalize_event(schema_two()), expected)
        self.assertEqual(normalize_event(schema_one(slot=0))["slot"], "A")
        self.assertEqual(normalize_event(schema_two(slot="A"))["slot"], "A")

    def test_missing_optional_fields_normalize_to_null(self):
        for event, optional in (
            (schema_one(), ("tx", "slot", "digest")),
            (schema_two(), ("transaction", "slot", "sha256")),
        ):
            for key in optional:
                del event[key]
            normalized = normalize_event(event)
            self.assertEqual(
                {key: normalized[key] for key in ("tx", "slot", "digest")},
                {"tx": None, "slot": None, "digest": None},
            )

    def test_timestamp_and_spelling_only_differences_are_replays(self):
        retained, incidents, replays, conflicts = ingest_events([
            schema_one(time=12), schema_two(timestamp=8), schema_one(time=10),
        ])
        self.assertEqual(retained, [normalize_event(schema_one(time=8))])
        self.assertEqual(incidents, [])
        self.assertEqual((replays, conflicts), (2, 0))

    def test_global_conflict_discards_all_rows_and_excludes_replays(self):
        retained, incidents, replays, conflicts = ingest_events([
            schema_one(), schema_one(),
            schema_two(device="board-a", boot=9, seq=7),
            schema_one(event_id="kept", time=20),
            schema_two(id="kept", timestamp=21),
        ])
        self.assertEqual(retained, [normalize_event(schema_one(event_id="kept", time=20))])
        self.assertEqual(incidents, [{
            "board": "board-a", "epoch": 9, "sequence": 7,
            "event_id": "event-1", "reason": "duplicate_conflict",
        }])
        self.assertEqual((replays, conflicts), (1, 1))

    def test_non_timestamp_payload_differences_conflict(self):
        changes = (
            {"board": "other"}, {"epoch": 3}, {"sequence": 4},
            {"action": "VERIFY"}, {"tx": "other"}, {"slot": 0},
            {"digest": "other"}, {"success": False},
        )
        for change in changes:
            with self.subTest(change=change):
                retained, incidents, replays, conflicts = ingest_events([
                    schema_one(), schema_one(**change),
                ])
                self.assertEqual(retained, [])
                self.assertEqual(len(incidents), 1)
                self.assertEqual((replays, conflicts), (0, 1))

    def test_input_permutations_have_identical_results(self):
        rows = [
            schema_one(time=12), schema_two(timestamp=8),
            schema_one(event_id="conflict", board="board-c"),
            schema_one(event_id="conflict", board="board-a"),
            schema_one(event_id="another", board="board-a"),
        ]
        expected = ingest_events(rows)
        for permutation in itertools.permutations(rows):
            self.assertEqual(ingest_events(iter(permutation)), expected)

    def test_empty_input(self):
        self.assertEqual(ingest_events([]), ([], [], 0, 0))

    def test_retained_order_uses_location_and_event_id_not_timestamp(self):
        retained, incidents, replays, conflicts = ingest_events([
            schema_one(event_id="last-board", board="board-z", epoch=0, sequence=0, time=-100),
            schema_one(event_id="later-epoch", board="board-a", epoch=1, sequence=0, time=-50),
            schema_one(event_id="later-sequence", board="board-a", epoch=0, sequence=2, time=0),
            schema_one(event_id="z", board="board-a", epoch=0, sequence=1, time=-10),
            schema_one(event_id="a", board="board-a", epoch=0, sequence=1, time=20),
        ])
        self.assertEqual(
            [event["event_id"] for event in retained],
            ["a", "z", "later-sequence", "later-epoch", "last-board"],
        )
        self.assertEqual((incidents, replays, conflicts), ([], 0, 0))


class IngestCorpusRegression(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        evidence = Path(__file__).resolve().parents[1] / "data" / "visible.jsonl"
        cls.rows = [json.loads(line) for line in evidence.read_text().splitlines() if line.strip()]
        first_boards = {f"board-{number:05d}" for number in range(1, 65)}
        cls.batch_one = [
            row for row in cls.rows
            if row.get("board", row.get("device")) in first_boards
        ]
        second_boards = {f"board-{number:05d}" for number in range(65, 129)}
        cls.batch_two = [
            row for row in cls.rows
            if row.get("board", row.get("device")) in second_boards
        ]
        third_boards = {f"board-{number:05d}" for number in range(129, 193)}
        cls.batch_three = [
            row for row in cls.rows
            if row.get("board", row.get("device")) in third_boards
        ]

    def test_batch_counts_and_full_corpus_ingest_counts(self):
        for label, rows, expected in (
            ("batch_one", self.batch_one, (662, 510, 128, 12)),
            ("batch_two", self.batch_two, (664, 510, 128, 13)),
            ("batch_three", self.batch_three, (664, 510, 128, 13)),
            ("full_corpus", self.rows, (1990, 1530, 384, 38)),
        ):
            with self.subTest(scope=label):
                retained, incidents, replays, conflicts = ingest_events(rows)
                self.assertEqual((len(rows), len(retained), replays, conflicts), expected)
                self.assertEqual(len(incidents), conflicts)

    def test_batch_one_schema_timestamp_replay_uses_earliest_time(self):
        event_id = "board-00001-e006"
        replay_rows = [
            row for row in self.batch_one
            if row.get("event_id", row.get("id")) == event_id
        ]
        retained, incidents, replays, conflicts = ingest_events(replay_rows)
        self.assertEqual(len(replay_rows), 3)
        self.assertEqual({row["schema"] for row in replay_rows}, {1, 2})
        self.assertEqual(incidents, [])
        self.assertEqual((replays, conflicts), (2, 0))
        self.assertEqual(retained, [{
            "event_id": event_id, "board": "board-00001", "epoch": 1,
            "sequence": 42, "action": "VERIFY", "tx": "tx-01", "slot": "B",
            "digest": "4a002371431aa448c8fa9733ccb295f6901ffd4af4f4d808f58b65297ee8d142",
            "success": False, "timestamp": 1700702820,
        }])

    def test_batch_conflicting_stage_ids_are_all_removed(self):
        for label, rows, numbers in (
            ("batch_one", self.batch_one, range(5, 65, 5)),
            ("batch_two", self.batch_two, range(65, 129, 5)),
            ("batch_three", self.batch_three, range(130, 193, 5)),
        ):
            with self.subTest(scope=label):
                retained, incidents, _, _ = ingest_events(rows)
                expected_incidents = [
                    {
                        "board": f"board-{number:05d}", "epoch": 0, "sequence": 7,
                        "event_id": f"board-{number:05d}-e001", "reason": "duplicate_conflict",
                    }
                    for number in numbers
                ]
                self.assertEqual(incidents, expected_incidents)
                conflict_ids = {incident["event_id"] for incident in incidents}
                self.assertTrue(conflict_ids.isdisjoint(event["event_id"] for event in retained))

    def test_later_batch_schema_timestamp_replays_have_one_payload(self):
        for rows, event_id, timestamp, success in (
            (self.batch_two, "board-00128-e006", 1700076085, True),
            (self.batch_three, "board-00129-e006", 1700239406, False),
        ):
            with self.subTest(event_id=event_id):
                replay_rows = [
                    row for row in rows
                    if row.get("event_id", row.get("id")) == event_id
                ]
                retained, incidents, replays, conflicts = ingest_events(replay_rows)
                self.assertEqual(len(replay_rows), 3)
                self.assertEqual({row["schema"] for row in replay_rows}, {1, 2})
                self.assertEqual((incidents, replays, conflicts), ([], 2, 0))
                self.assertEqual(len(retained), 1)
                self.assertEqual(retained[0]["event_id"], event_id)
                self.assertEqual(retained[0]["timestamp"], timestamp)
                self.assertEqual(retained[0]["success"], success)

    def test_reported_time_does_not_change_identity_or_retained_order(self):
        rewritten = [
            dict(row, **{("time" if row["schema"] == 1 else "timestamp"): -index})
            for index, row in enumerate(self.rows)
        ]
        original_events, *original_counts = ingest_events(self.rows)
        rewritten_events, *rewritten_counts = ingest_events(rewritten)
        self.assertEqual(rewritten_counts, original_counts)
        self.assertEqual(
            [{key: value for key, value in row.items() if key != "timestamp"} for row in rewritten_events],
            [{key: value for key, value in row.items() if key != "timestamp"} for row in original_events],
        )

    def test_corpus_reversal_and_seeded_shuffle_are_invariant(self):
        for label, rows in (
            ("batch_one", self.batch_one),
            ("batch_two", self.batch_two),
            ("batch_three", self.batch_three),
            ("full_corpus", self.rows),
        ):
            with self.subTest(scope=label):
                expected = ingest_events(rows)
                shuffled = rows[:]
                random.Random(17).shuffle(shuffled)
                self.assertEqual(ingest_events(reversed(rows)), expected)
                self.assertEqual(ingest_events(shuffled), expected)


if __name__ == "__main__":
    unittest.main()
