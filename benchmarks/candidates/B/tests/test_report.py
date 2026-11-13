import copy
import unittest

from report import build_audit_report, build_report


class ReportContract(unittest.TestCase):
    def test_canonical_sort_and_exact_projection(self):
        boards = [
            {
                "board": "z",
                "epoch": 2,
                "active_slot": "B",
                "active_digest": "new",
                "timestamp": 123,
                "path": "/private/input.jsonl",
            },
            {
                "board": "a",
                "epoch": 10,
                "active_slot": "A",
                "active_digest": "old",
                "pending": {"t1": "internal"},
            },
        ]
        expected_locations = [
            ("a", 2, 2, "a", "commit_failed"),
            ("a", 2, 2, "a", "duplicate_conflict"),
            ("a", 2, 2, "b", "stage_failed"),
            ("a", 2, 10, "a", "verify_failed"),
            ("a", 10, 0, "a", "reset_failed"),
            ("z", 0, 0, "a", "rollback_failed"),
        ]
        incident_fields = ("board", "epoch", "sequence", "event_id", "reason")
        incidents = [
            dict(zip(incident_fields, location), time=999, path="input.jsonl")
            for location in reversed(expected_locations)
        ]
        original_boards = copy.deepcopy(boards)
        original_incidents = copy.deepcopy(incidents)

        report = build_report(boards, incidents, 3, 4, 5, 1)

        self.assertEqual(set(report), {"boards", "incidents", "totals"})
        self.assertEqual(
            report["boards"],
            [
                {"board": "a", "epoch": 10, "active_slot": "A", "active_digest": "old"},
                {"board": "z", "epoch": 2, "active_slot": "B", "active_digest": "new"},
            ],
        )
        self.assertEqual(
            report["incidents"],
            [dict(zip(incident_fields, location)) for location in expected_locations],
        )
        self.assertEqual(
            report["totals"],
            {
                "board_count": 2,
                "applied_commits": 3,
                "accepted_rollbacks": 4,
                "duplicate_replays": 5,
                "conflicted_ids": 1,
                "rejected_events": 6,
            },
        )
        self.assertEqual(boards, original_boards)
        self.assertEqual(incidents, original_incidents)
        report["boards"][0]["epoch"] = 99
        report["incidents"][0]["reason"] = "changed"
        self.assertEqual(boards, original_boards)
        self.assertEqual(incidents, original_incidents)

    def test_empty_report(self):
        self.assertEqual(
            build_report(iter(()), iter(()), 0, 0, 0, 0),
            {
                "boards": [],
                "incidents": [],
                "totals": {
                    "board_count": 0,
                    "applied_commits": 0,
                    "accepted_rollbacks": 0,
                    "duplicate_replays": 0,
                    "conflicted_ids": 0,
                    "rejected_events": 0,
                },
            },
        )


class AuditReportContract(unittest.TestCase):
    @staticmethod
    def trace_event(sequence, action, success, accepted, reason=None):
        return {
            "board": "a",
            "epoch": 0,
            "sequence": sequence,
            "event_id": f"event-{sequence}",
            "action": action,
            "tx": "t",
            "slot": "B",
            "digest": "new",
            "success": success,
            "accepted": accepted,
            "reason": reason,
            "active_slot_before": "A",
            "active_digest_before": "old",
            "active_slot_after": "B" if accepted else "A",
            "active_digest_after": "new" if accepted else "old",
        }

    def test_operation_counts_distinguish_success_from_acceptance(self):
        trace = [
            self.trace_event(30, "COMMIT", True, False, "commit_without_stage"),
            self.trace_event(10, "COMMIT", True, True),
            self.trace_event(20, "COMMIT", False, False, "commit_failed"),
            self.trace_event(60, "ROLLBACK", True, False, "rollback_unverified"),
            self.trace_event(40, "ROLLBACK", True, True),
            self.trace_event(50, "ROLLBACK", False, False, "rollback_failed"),
            self.trace_event(70, "STAGE", True, True),
        ]
        conflicts = [
            {"board": "a", "epoch": 0, "sequence": 80, "event_id": "conflict", "reason": "duplicate_conflict"},
        ]
        report = build_report([], conflicts, 1, 1, 100, 1)
        result = build_audit_report(report, iter(trace))
        self.assertEqual(result["events"], trace)
        self.assertEqual(result["conflicts"], conflicts)
        self.assertEqual(result["operations"], {
            "COMMIT": {"attempted": 3, "reported_success": 2, "accepted": 1, "rejected": 2},
            "ROLLBACK": {"attempted": 3, "reported_success": 2, "accepted": 1, "rejected": 2},
        })
        self.assertEqual(set(result["reason_explanations"]), {"duplicate_conflict"})

    def test_projection_and_no_input_mutation(self):
        trace = [self.trace_event(9, "COMMIT", True, False, "commit_unverified")]
        expected_event = dict(trace[0])
        trace[0].update(timestamp=123, path="private.jsonl", pending={"t": "private"})
        conflict = {"board": "a", "epoch": 0, "sequence": 3, "event_id": "duplicate", "reason": "duplicate_conflict"}
        report = build_report([], [conflict], 0, 0, 2, 1)
        report["incidents"][0]["timestamp"] = 123
        report["incidents"][0]["path"] = "private.jsonl"
        original_trace = copy.deepcopy(trace)
        original_report = copy.deepcopy(report)

        result = build_audit_report(report, trace)

        self.assertEqual(set(result), {"contract_revision", "events", "conflicts", "operations", "reason_explanations"})
        self.assertEqual(result["contract_revision"], "R3")
        self.assertEqual(result["events"], [expected_event])
        self.assertEqual(result["conflicts"], [conflict])
        self.assertEqual(trace, original_trace)
        self.assertEqual(report, original_report)
        result["events"][0]["reason"] = "changed"
        result["conflicts"][0]["reason"] = "changed"
        self.assertEqual(trace, original_trace)
        self.assertEqual(report, original_report)

    def test_explanations_cover_all_current_rejection_reasons(self):
        reasons = (
            "duplicate_conflict", "reset_failed", "stage_failed",
            "verify_without_stage", "verify_failed", "verify_mismatch",
            "commit_failed", "commit_without_stage", "commit_mismatch",
            "commit_unverified", "rollback_failed", "rollback_unverified",
        )
        incidents = [
            {"board": "a", "epoch": 0, "sequence": index, "event_id": str(index), "reason": reason}
            for index, reason in enumerate(reasons)
        ]
        report = build_report([], incidents, 0, 0, 0, 1)
        explanations = build_audit_report(report, [])["reason_explanations"]
        self.assertEqual(set(explanations), set(reasons))
        self.assertTrue(all(explanations.values()))
        self.assertIn("cleared", explanations["verify_failed"])
        self.assertIn("cleared", explanations["verify_mismatch"])
        self.assertIn("exact slot and digest", explanations["rollback_unverified"])

    def test_empty_audit(self):
        report = build_report([], [], 0, 0, 0, 0)
        self.assertEqual(build_audit_report(report, []), {
            "contract_revision": "R3",
            "events": [],
            "conflicts": [],
            "operations": {
                "COMMIT": {"attempted": 0, "reported_success": 0, "accepted": 0, "rejected": 0},
                "ROLLBACK": {"attempted": 0, "reported_success": 0, "accepted": 0, "rejected": 0},
            },
            "reason_explanations": {},
        })

    def test_r3_failed_verify_explanation_and_revision_label(self):
        incidents = [
            {"board": "a", "epoch": 0, "sequence": 3, "event_id": "failed-verify", "reason": "verify_failed"},
            {"board": "a", "epoch": 0, "sequence": 4, "event_id": "commit", "reason": "commit_unverified"},
        ]
        report = build_report([], incidents, 0, 0, 0, 0)
        trace = [
            self.trace_event(3, "VERIFY", False, False, "verify_failed"),
            self.trace_event(4, "COMMIT", True, False, "commit_unverified"),
        ]
        audit = build_audit_report(report, trace)
        self.assertEqual(audit, build_audit_report(report, trace, contract_revision="R3"))
        self.assertEqual(audit["contract_revision"], "R3")
        explanation = audit["reason_explanations"]["verify_failed"]
        self.assertIn("R3", explanation)
        self.assertIn("pending transaction is cleared", explanation)
        self.assertIn("history is retained", explanation)
        self.assertNotIn("R1", explanation)
        self.assertNotIn("R2", explanation)
        self.assertEqual(audit["operations"]["COMMIT"], {
            "attempted": 1, "reported_success": 1, "accepted": 0, "rejected": 1,
        })

    def test_current_audit_cannot_be_mislabeled_with_another_revision(self):
        report = build_report([], [], 0, 0, 0, 0)
        for revision in ("R1", "R2", "R4"):
            with self.subTest(revision=revision):
                with self.assertRaisesRegex(ValueError, "expected 'R3'"):
                    build_audit_report(report, [], contract_revision=revision)

    def test_r3_epoch_clearing_and_slot_pair_explanations(self):
        reasons = ("verify_without_stage", "commit_without_stage", "rollback_unverified", "reset_failed")
        incidents = [
            {"board": "a", "epoch": 1, "sequence": index, "event_id": str(index), "reason": reason}
            for index, reason in enumerate(reasons)
        ]
        report = build_report([], incidents, 0, 0, 0, 0)
        explanations = build_audit_report(report, [])["reason_explanations"]
        for reason in ("verify_without_stage", "commit_without_stage"):
            self.assertIn("boot epoch advances clear all pending transactions", explanations[reason])
            self.assertIn("before processing the event", explanations[reason])
        rollback = explanations["rollback_unverified"]
        self.assertIn("exact slot and digest pair", rollback)
        self.assertIn("another slot does not authorize", rollback)
        self.assertIn("history survives boot epoch advances", rollback)
        self.assertIn("did not itself clear", explanations["reset_failed"])
        self.assertIn("before processing the action", explanations["reset_failed"])


if __name__ == "__main__":
    unittest.main()
