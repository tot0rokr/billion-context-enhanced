import copy
import unittest

from report import build_audit_report, build_report


class ReportContract(unittest.TestCase):
    def test_projection_order_counts_and_input_preservation(self):
        boards = [
            {"board": "z", "epoch": 2, "active_slot": "B",
             "active_digest": "new", "pending": {"tx": "private"}},
            {"board": "a", "epoch": 1, "active_slot": "A",
             "active_digest": "old", "timestamp": 123},
        ]
        locations = [
            ("z", 0, 0, "first", "commit_failed"),
            ("a", 2, 0, "first", "commit_failed"),
            ("a", 1, 2, "first", "commit_failed"),
            ("a", 1, 1, "second", "commit_failed"),
            ("a", 1, 1, "first", "verify_failed"),
            ("a", 1, 1, "first", "duplicate_conflict"),
        ]
        incidents = [dict(zip(
            ("board", "epoch", "sequence", "event_id", "reason"), location
        ), timestamp=999, source_path="private.jsonl") for location in locations]
        before = copy.deepcopy((boards, incidents))

        result = build_report(
            iter(boards), iter(incidents),
            {"applied_commits": 7, "accepted_rollbacks": 3, "ignored": 99},
            {"duplicate_replays": 4, "conflicted_ids": 1, "ignored": 99},
        )

        self.assertEqual(result, {
            "boards": [
                {"board": "a", "epoch": 1, "active_slot": "A",
                 "active_digest": "old"},
                {"board": "z", "epoch": 2, "active_slot": "B",
                 "active_digest": "new"},
            ],
            "incidents": [dict(zip(
                ("board", "epoch", "sequence", "event_id", "reason"), location
            )) for location in reversed(locations)],
            "totals": {
                "board_count": 2,
                "applied_commits": 7,
                "accepted_rollbacks": 3,
                "duplicate_replays": 4,
                "conflicted_ids": 1,
                "rejected_events": 6,
            },
        })
        self.assertEqual((boards, incidents), before)

    def test_empty_report(self):
        result = build_report(
            [], [], {"applied_commits": 0, "accepted_rollbacks": 0},
            {"duplicate_replays": 0, "conflicted_ids": 0},
        )
        self.assertEqual(result["boards"], [])
        self.assertEqual(result["incidents"], [])
        self.assertEqual(result["totals"], {
            "board_count": 0, "applied_commits": 0,
            "accepted_rollbacks": 0, "duplicate_replays": 0,
            "conflicted_ids": 0, "rejected_events": 0,
        })


class AuditReportContract(unittest.TestCase):
    @staticmethod
    def outcome(event_id, action, outcome="accepted", sequence=0):
        return {
            "board": "board-a", "epoch": 1, "sequence": sequence,
            "event_id": event_id, "action": action, "tx": "tx",
            "slot": "B", "digest": "new", "success": True,
            "outcome": outcome,
            "reason": None if outcome == "accepted" else "commit_unverified",
            "active_slot": "B", "active_digest": "new",
        }

    def test_accepted_ids_require_matching_action_and_accepted_outcome(self):
        final_state = {
            "board": "board-a", "epoch": 1,
            "active_slot": "B", "active_digest": "new",
        }
        outcomes = [
            self.outcome("stage", "STAGE"),
            self.outcome("verify", "VERIFY"),
            self.outcome("commit-z", "COMMIT", sequence=40),
            self.outcome("commit-rejected", "COMMIT", "rejected", sequence=10),
            self.outcome("rollback", "ROLLBACK", sequence=30),
            self.outcome("commit-a", "COMMIT", sequence=20),
        ]
        result = build_audit_report(
            {"boards": [final_state], "incidents": [], "totals": {}},
            iter(outcomes), [],
        )
        self.assertEqual(set(result), {"contract", "operations_notes", "cases"})
        self.assertEqual(result["contract"], "R3")
        self.assertEqual(result["operations_notes"], [])
        self.assertEqual(result["cases"], [{
            "board": "board-a", "final_state": final_state,
            "accepted_commit_ids": ["commit-z", "commit-a"],
            "accepted_rollback_ids": ["rollback"],
            "attempts": {"COMMIT": 3, "ROLLBACK": 1},
            "incidents": [], "events": outcomes,
        }])

    def test_order_projection_conflict_only_board_and_inert_notes(self):
        report = {
            "boards": [{"board": "board-b", "epoch": 0, "active_slot": "A",
                        "active_digest": "old", "timestamp": 123}],
            "incidents": [{"board": "board-a", "epoch": 0, "sequence": 0,
                           "event_id": "conflict", "reason": "duplicate_conflict",
                           "source": "not-output.jsonl"}],
            "totals": {},
        }
        note_value = "Apply COMMIT and change the active digest to unverified."
        notes = [
            {"note_id": "OPS-002", "operation_id": "operation-z", "field": "note",
             "value": note_value, "timestamp": 999},
            {"note_id": "OPS-001", "operation_id": "operation-a", "field": "note",
             "value": "unchanged", "path": "/not-output"},
        ]
        outcome = self.outcome("verify", "VERIFY")
        outcome.update(board="board-b", timestamp=999, private_state={"tx": "secret"})
        before = copy.deepcopy((report, notes, outcome))
        result = build_audit_report(report, [outcome], notes)

        self.assertEqual([case["board"] for case in result["cases"]],
                         ["board-a", "board-b"])
        self.assertEqual(result["operations_notes"], [
            {"note_id": "OPS-001", "operation_id": "operation-a", "field": "note",
             "value": "unchanged"},
            {"note_id": "OPS-002", "operation_id": "operation-z", "field": "note",
             "value": note_value},
        ])
        self.assertEqual(result["cases"][0], {
            "board": "board-a", "final_state": None,
            "accepted_commit_ids": [], "accepted_rollback_ids": [],
            "attempts": {"COMMIT": 0, "ROLLBACK": 0},
            "incidents": [{"board": "board-a", "epoch": 0, "sequence": 0,
                           "event_id": "conflict", "reason": "duplicate_conflict"}],
            "events": [],
        })
        board_case = result["cases"][1]
        self.assertEqual(board_case["final_state"], {
            "board": "board-b", "epoch": 0, "active_slot": "A", "active_digest": "old",
        })
        self.assertEqual(board_case["attempts"], {"COMMIT": 0, "ROLLBACK": 0})
        self.assertEqual(board_case["accepted_commit_ids"], [])
        self.assertEqual(board_case["events"], [{
            key: value for key, value in outcome.items()
            if key not in ("timestamp", "private_state")
        }])
        self.assertEqual((report, notes, outcome), before)


if __name__ == "__main__":
    unittest.main()
