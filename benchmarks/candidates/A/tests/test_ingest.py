import itertools
import unittest

from ingest import ingest_events, normalize_event


def schema_one(**changes):
    event = {
        "schema": 1,
        "event_id": "event-1",
        "board": "board-a",
        "epoch": 2,
        "sequence": 3,
        "action": "STAGE",
        "tx": "transaction-1",
        "slot": 1,
        "digest": "image-1",
        "success": True,
        "time": 8,
    }
    event.update(changes)
    return event


def schema_two(**changes):
    event = {
        "schema": 2,
        "id": "event-1",
        "device": "board-a",
        "boot": 2,
        "seq": 3,
        "kind": "stage",
        "transaction": "transaction-1",
        "slot": "B",
        "sha256": "image-1",
        "ok": True,
        "timestamp": 8,
    }
    event.update(changes)
    return event


class IngestContract(unittest.TestCase):
    def test_schemas_share_a_normalized_representation(self):
        expected = {
            "event_id": "event-1", "board": "board-a", "epoch": 2,
            "sequence": 3, "action": "STAGE", "tx": "transaction-1",
            "slot": "B", "digest": "image-1", "success": True,
        }
        self.assertEqual(normalize_event(schema_one()), expected)
        self.assertEqual(normalize_event(schema_two()), expected)
        self.assertEqual(normalize_event(schema_one(slot=0))["slot"], "A")

    def test_omitted_optional_fields_match_explicit_nulls(self):
        first = schema_one(tx=None, slot=None, digest=None)
        second = schema_two(transaction=None, slot=None, sha256=None)
        for key in ("tx", "slot", "digest"):
            del first[key]
        accepted, incidents, counters = ingest_events([first, second])
        self.assertEqual(len(accepted), 1)
        self.assertEqual([accepted[0][key] for key in ("tx", "slot", "digest")],
                         [None, None, None])
        self.assertEqual(incidents, [])
        self.assertEqual(counters, {"duplicate_replays": 1, "conflicted_ids": 0})

    def test_replays_ignore_schema_and_noncomparable_clocks(self):
        events = [schema_one(time=12), schema_two(timestamp={"skewed": True}),
                  schema_one(time=None), schema_two(timestamp=["ignored"])]
        expected = ingest_events(events)
        self.assertEqual(expected[0], [normalize_event(schema_one())])
        self.assertEqual(expected[1], [])
        self.assertEqual(expected[2], {"duplicate_replays": 3, "conflicted_ids": 0})
        for permutation in itertools.permutations(events):
            self.assertEqual(ingest_events(permutation), expected)

    def test_clocks_can_be_absent_without_affecting_normalization_or_audit(self):
        first = schema_one()
        second = schema_two()
        del first["time"]
        del second["timestamp"]
        expected_audit = []
        expected = ingest_events([schema_one(), schema_two()], audit=expected_audit)
        actual_audit = []
        self.assertEqual(ingest_events(iter([first, second]), audit=actual_audit), expected)
        self.assertEqual(actual_audit, expected_audit)

    def test_conflict_is_global_excludes_every_row_and_counts_no_replays(self):
        events = [schema_one(board="board-z"), schema_one(board="board-z"),
                  schema_two(device="board-a", seq=9)]
        expected = (
            [],
            [{"board": "board-a", "epoch": 2, "sequence": 9,
              "event_id": "event-1", "reason": "duplicate_conflict"}],
            {"duplicate_replays": 0, "conflicted_ids": 1},
        )
        for permutation in itertools.permutations(events):
            self.assertEqual(ingest_events(permutation), expected)

    def test_accepted_events_are_sorted_by_location(self):
        accepted, incidents, counters = ingest_events([
            schema_one(event_id="last-board", board="board-z", epoch=0,
                       sequence=0, time=-100),
            schema_one(event_id="next-epoch", epoch=3, sequence=0, time=-20),
            schema_one(event_id="later-sequence", sequence=8, time=0),
            schema_one(event_id="tie-z", sequence=1, time=1),
            schema_one(event_id="tie-a", sequence=1, time=20),
        ])
        self.assertEqual([event["event_id"] for event in accepted],
                         ["tie-a", "tie-z", "later-sequence", "next-epoch", "last-board"])
        self.assertEqual(incidents, [])
        self.assertEqual(counters, {"duplicate_replays": 0, "conflicted_ids": 0})

    def test_transport_audit_counts_rows_without_exposing_payloads(self):
        events = [
            schema_one(event_id="retained", sequence=8, time=12),
            schema_two(id="retained", seq=8, timestamp=2),
            schema_one(event_id="conflicted", board="board-z", time=9),
            schema_one(event_id="conflicted", board="board-z", time=8),
            schema_two(id="conflicted", device="board-b", timestamp=5),
            schema_one(event_id="conflicted", board="board-a", sequence=1),
        ]
        expected_audit = [
            {"board": "board-a", "epoch": 2, "sequence": 1,
             "event_id": "conflicted", "status": "conflict",
             "transport_rows": 4, "duplicate_replays": 0},
            {"board": "board-a", "epoch": 2, "sequence": 8,
             "event_id": "retained", "status": "retained",
             "transport_rows": 2, "duplicate_replays": 1},
        ]
        expected_result = ingest_events(events)
        for order in (events, list(reversed(events)), events[2:] + events[:2]):
            audit = []
            self.assertEqual(ingest_events(order, audit=audit), expected_result)
            self.assertEqual(audit, expected_audit)
            self.assertEqual(sum(record["transport_rows"] for record in audit), len(events))
            self.assertEqual(sum(record["duplicate_replays"] for record in audit),
                             expected_result[2]["duplicate_replays"])

    def test_generator_input_with_many_replays(self):
        audit = []
        accepted, incidents, counters = ingest_events(
            (schema_one(time=clock) for clock in itertools.islice(
                itertools.cycle([None, {"skewed": True}, 100, ["ignored"]]), 10000)),
            audit=audit,
        )
        self.assertEqual(accepted, [normalize_event(schema_one())])
        self.assertEqual(incidents, [])
        self.assertEqual(counters, {"duplicate_replays": 9999, "conflicted_ids": 0})
        self.assertEqual(audit[0]["transport_rows"], 10000)
        self.assertEqual(audit[0]["duplicate_replays"], 9999)

    def test_audit_appends_to_caller_list_and_empty_input_adds_nothing(self):
        sentinel = {"caller": "existing record"}
        audit = [sentinel]
        self.assertEqual(ingest_events(iter(()), audit=audit),
                         ([], [], {"duplicate_replays": 0, "conflicted_ids": 0}))
        self.assertEqual(audit, [sentinel])
        ingest_events([schema_one()], audit=audit)
        self.assertIs(audit[0], sentinel)
        self.assertEqual(len(audit), 2)
        self.assertEqual(audit[1]["status"], "retained")

    def test_conflict_stays_excluded_after_later_matching_replays(self):
        audit = []
        accepted, incidents, counters = ingest_events([
            schema_one(), schema_two(sha256="different-image"),
            schema_one(time=1), schema_two(timestamp=0),
        ], audit=audit)
        self.assertEqual(accepted, [])
        self.assertEqual(len(incidents), 1)
        self.assertEqual(counters, {"duplicate_replays": 0, "conflicted_ids": 1})
        self.assertEqual(audit[0]["transport_rows"], 4)
        self.assertEqual(audit[0]["duplicate_replays"], 0)

    def test_cross_epoch_conflicts_use_global_minimum_location_and_no_replays(self):
        conflicted = [schema_one(epoch=5, sequence=0),
                      schema_two(boot=1, seq=9),
                      schema_one(epoch=1, sequence=9),
                      schema_two(boot=1, seq=3)]
        retained = schema_one(event_id="retained", epoch=2, sequence=1)
        expected_incident = {
            "board": "board-a", "epoch": 1, "sequence": 3,
            "event_id": "event-1", "reason": "duplicate_conflict",
        }
        for order in itertools.permutations(conflicted):
            audit = []
            accepted, incidents, counters = ingest_events(
                iter([retained, *order, dict(retained, time=None)]), audit=audit)
            self.assertEqual(accepted, [normalize_event(retained)])
            self.assertEqual(incidents, [expected_incident])
            self.assertEqual(counters, {"duplicate_replays": 1, "conflicted_ids": 1})
            self.assertEqual(audit[0], {
                "board": "board-a", "epoch": 1, "sequence": 3,
                "event_id": "event-1", "status": "conflict",
                "transport_rows": 4, "duplicate_replays": 0,
            })
            self.assertEqual(audit[1]["transport_rows"], 2)
            self.assertEqual(audit[1]["duplicate_replays"], 1)

    def test_cross_epoch_conflict_cannot_advance_state_or_supply_pending_stage(self):
        from reconcile import reconcile

        events = [
            schema_one(event_id="baseline", epoch=0, sequence=0, action="BASELINE",
                       tx=None, slot=0, digest="old-image"),
            schema_one(epoch=0, sequence=1),
            schema_two(boot=7, seq=1),
            schema_one(epoch=0, sequence=1, time=None),
            schema_one(event_id="verify", epoch=0, sequence=2, action="VERIFY"),
            schema_one(event_id="commit", epoch=0, sequence=3, action="COMMIT"),
        ]
        for order in (events, list(reversed(events)), events[2:] + events[:2]):
            report = reconcile(iter(order))
            self.assertEqual(report["boards"], [{
                "board": "board-a", "epoch": 0,
                "active_slot": "A", "active_digest": "old-image",
            }])
            self.assertEqual([(incident["event_id"], incident["reason"])
                              for incident in report["incidents"]], [
                ("event-1", "duplicate_conflict"),
                ("verify", "verify_without_stage"),
                ("commit", "commit_without_stage"),
            ])
            self.assertEqual(report["totals"]["duplicate_replays"], 0)
            self.assertEqual(report["totals"]["conflicted_ids"], 1)
            self.assertEqual(report["totals"]["applied_commits"], 0)

    def test_slot_and_digest_independently_distinguish_payloads(self):
        first = schema_one(slot=0)
        equivalent = schema_two(slot="A")
        for differing in (schema_two(slot="B"),
                          schema_two(slot="A", sha256="different-image")):
            with self.subTest(slot=differing["slot"], digest=differing["sha256"]):
                audit = []
                accepted, incidents, counters = ingest_events(
                    [first, equivalent, differing], audit=audit)
                self.assertEqual(accepted, [])
                self.assertEqual(len(incidents), 1)
                self.assertEqual(incidents[0]["reason"], "duplicate_conflict")
                self.assertEqual(counters, {"duplicate_replays": 0, "conflicted_ids": 1})
                self.assertEqual(audit[0]["transport_rows"], 3)
                self.assertEqual(audit[0]["duplicate_replays"], 0)


if __name__ == "__main__":
    unittest.main()
