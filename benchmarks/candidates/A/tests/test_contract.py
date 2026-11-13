"""Regression coverage for the current R3 reconciliation rules."""

import unittest

from reconcile import reconcile
from report import build_report


def event(event_id, action, sequence, *, board="board", epoch=0, tx="tx",
          slot=1, digest="new", success=True, time=None):
    return {
        "schema": 1, "event_id": event_id, "board": board,
        "epoch": epoch, "sequence": sequence, "action": action,
        "tx": tx, "slot": slot, "digest": digest, "success": success,
        "time": sequence if time is None else time,
    }


def baseline(board="board", **kwargs):
    return event("baseline-" + board, "BASELINE", 0, board=board,
                 tx=None, slot=0, digest="old", **kwargs)


def schema_two(row):
    return {
        "schema": 2, "id": row["event_id"], "device": row["board"],
        "boot": row["epoch"], "seq": row["sequence"],
        "kind": row["action"].lower(), "transaction": row.get("tx"),
        "slot": {0: "A", 1: "B", None: None}[row.get("slot")],
        "sha256": row.get("digest"), "ok": row["success"],
        "timestamp": row["time"],
    }


class ReconciliationContract(unittest.TestCase):
    def reasons(self, result):
        return [(row["event_id"], row["reason"]) for row in result["incidents"]]

    def test_schema_equivalent_replays_ignore_timestamp_and_missing_null_fields(self):
        stage = event("stage", "STAGE", 1, time=10)
        replay = schema_two(stage)
        replay["timestamp"] = 40
        reset = event("reset", "RESET", 4, tx=None, slot=None, digest=None, time=50)
        omitted = dict(reset)
        for key in ("tx", "slot", "digest"):
            del omitted[key]
        rows = [baseline(), stage, replay,
                event("verify", "VERIFY", 2, time=20),
                event("commit", "COMMIT", 3, time=30),
                schema_two(reset), omitted]
        result = reconcile(rows)
        self.assertEqual(result, reconcile(list(reversed(rows))))
        self.assertEqual(result["incidents"], [])
        self.assertEqual(result["totals"]["duplicate_replays"], 2)
        self.assertEqual(result["totals"]["applied_commits"], 1)
        self.assertEqual(result["boards"][0]["active_digest"], "new")

    def test_conflicting_id_is_global_and_excludes_every_copy(self):
        conflict_a = event("collision", "STAGE", 9, board="alpha")
        conflict_z = event("collision", "STAGE", 1, board="zulu")
        rows = [baseline("zulu"), baseline("alpha"), conflict_z,
                conflict_a, dict(conflict_a),
                event("verify-a", "VERIFY", 10, board="alpha"),
                event("verify-z", "VERIFY", 2, board="zulu")]
        result = reconcile(rows)
        self.assertEqual(result, reconcile(list(reversed(rows))))
        self.assertEqual(result["totals"]["duplicate_replays"], 0)
        self.assertEqual(result["totals"]["conflicted_ids"], 1)
        self.assertEqual(result["totals"]["rejected_events"], 3)
        self.assertEqual(result["incidents"][0], {
            "board": "alpha", "epoch": 0, "sequence": 9,
            "event_id": "collision", "reason": "duplicate_conflict",
        })
        self.assertEqual(self.reasons(result)[1:], [
            ("verify-a", "verify_without_stage"),
            ("verify-z", "verify_without_stage"),
        ])

    def test_sequence_orders_events_despite_reversed_clocks(self):
        result = reconcile([
            event("commit", "COMMIT", 10, time=3), baseline(time=99),
            event("verify", "VERIFY", 20, time=2),
            event("stage", "STAGE", 30, time=1),
        ])
        self.assertEqual(self.reasons(result), [
            ("commit", "commit_without_stage"), ("verify", "verify_without_stage"),
        ])
        self.assertEqual(result["totals"]["applied_commits"], 0)
        self.assertEqual(result["boards"][0]["active_digest"], "old")

    def test_epoch_clears_pending_before_a_failed_verify(self):
        result = reconcile([
            baseline(), event("stage", "STAGE", 1, time=100),
            event("verify", "VERIFY", 2, time=101),
            event("failed-verify", "VERIFY", 0, epoch=1, success=False),
            event("commit", "COMMIT", 1, epoch=1),
        ])
        self.assertEqual(self.reasons(result), [
            ("failed-verify", "verify_without_stage"), ("commit", "commit_without_stage"),
        ])
        self.assertEqual(result["totals"]["applied_commits"], 0)
        self.assertEqual(result["boards"], [{
            "board": "board", "epoch": 1, "active_slot": "A", "active_digest": "old",
        }])

    def test_epoch_alone_clears_pending_verification(self):
        result = reconcile([
            baseline(), event("stage", "STAGE", 1, time=100),
            event("verify", "VERIFY", 2, time=101),
            event("commit", "COMMIT", 0, epoch=1, time=-100),
        ])
        self.assertEqual(self.reasons(result), [("commit", "commit_without_stage")])
        self.assertEqual(result["totals"]["applied_commits"], 0)
        self.assertEqual(result["boards"], [{
            "board": "board", "epoch": 1, "active_slot": "A", "active_digest": "old",
        }])

    def test_stage_failure_preserves_pending_and_replacement_clears_verified(self):
        result = reconcile([
            baseline(), event("stage", "STAGE", 1), event("verify", "VERIFY", 2),
            event("failed-stage", "STAGE", 3, digest="other", success=False),
            event("commit", "COMMIT", 4),
            event("stage-again", "STAGE", 5), event("verify-again", "VERIFY", 6),
            event("replace", "STAGE", 7, digest="replacement"),
            event("wrong-commit", "COMMIT", 8),
            event("unverified-commit", "COMMIT", 9, digest="replacement"),
            event("verify-replacement", "VERIFY", 10, digest="replacement"),
            event("commit-replacement", "COMMIT", 11, digest="replacement"),
            event("recommit", "COMMIT", 12, digest="replacement"),
        ])
        self.assertEqual(self.reasons(result), [
            ("failed-stage", "stage_failed"), ("wrong-commit", "commit_mismatch"),
            ("unverified-commit", "commit_unverified"),
            ("recommit", "commit_without_stage"),
        ])
        self.assertEqual(result["totals"]["applied_commits"], 2)
        self.assertEqual(result["boards"][0]["active_digest"], "replacement")

    def test_successful_verify_mismatch_revokes_verification(self):
        result = reconcile([
            baseline(), event("stage", "STAGE", 1), event("verify", "VERIFY", 2),
            event("mismatch", "VERIFY", 3, slot=0),
            event("unverified-commit", "COMMIT", 4),
            event("verify-again", "VERIFY", 5), event("commit", "COMMIT", 6),
        ])
        self.assertEqual(self.reasons(result), [
            ("mismatch", "verify_mismatch"), ("unverified-commit", "commit_unverified"),
        ])
        self.assertEqual(result["totals"]["applied_commits"], 1)

    def test_commit_failure_precedes_validation_and_keeps_pending(self):
        result = reconcile([
            baseline(), event("failed-no-stage", "COMMIT", 1, success=False),
            event("stage", "STAGE", 2), event("verify", "VERIFY", 3),
            event("failed-mismatch", "COMMIT", 4, digest="wrong", success=False),
            event("mismatch", "COMMIT", 5, digest="wrong"),
            event("commit", "COMMIT", 6),
        ])
        self.assertEqual(self.reasons(result), [
            ("failed-no-stage", "commit_failed"), ("failed-mismatch", "commit_failed"),
            ("mismatch", "commit_mismatch"),
        ])
        self.assertEqual(result["totals"]["applied_commits"], 1)

    def test_reset_success_clears_all_pending_and_failure_preserves_it(self):
        result = reconcile([
            baseline(), event("stage", "STAGE", 1), event("verify", "VERIFY", 2),
            event("failed-reset", "RESET", 3, success=False),
            event("commit", "COMMIT", 4),
            event("stage-a", "STAGE", 5, tx="a"),
            event("stage-b", "STAGE", 6, tx="b"),
            event("reset", "RESET", 7),
            event("commit-a", "COMMIT", 8, tx="a"),
            event("verify-b", "VERIFY", 9, tx="b"),
        ])
        self.assertEqual(self.reasons(result), [
            ("failed-reset", "reset_failed"), ("commit-a", "commit_without_stage"),
            ("verify-b", "verify_without_stage"),
        ])
        self.assertEqual(result["boards"][0]["active_digest"], "new")

    def test_rollback_requires_exact_history_and_retains_history_across_epochs(self):
        result = reconcile([
            baseline(), event("stage", "STAGE", 1), event("verify", "VERIFY", 2),
            event("wrong-slot", "ROLLBACK", 3, slot=1, digest="old"),
            event("failed-rollback", "ROLLBACK", 4, slot=0, digest="old", success=False),
            event("commit", "COMMIT", 5),
            event("stage-a", "STAGE", 6, tx="a"),
            event("stage-b", "STAGE", 7, tx="b"),
            event("rollback-old", "ROLLBACK", 8, slot=0, digest="old"),
            event("commit-a", "COMMIT", 9, tx="a"),
            event("verify-b", "VERIFY", 10, tx="b"),
            event("rollback-new", "ROLLBACK", 1, epoch=1),
        ])
        self.assertEqual(self.reasons(result), [
            ("wrong-slot", "rollback_unverified"), ("failed-rollback", "rollback_failed"),
            ("commit-a", "commit_without_stage"), ("verify-b", "verify_without_stage"),
        ])
        self.assertEqual(result["totals"]["accepted_rollbacks"], 2)
        self.assertEqual(result["totals"]["applied_commits"], 1)
        self.assertEqual(result["boards"][0]["active_digest"], "new")
        self.assertEqual(result["boards"][0]["epoch"], 1)

    def test_verification_authorizes_rollback_before_commit(self):
        result = reconcile([
            baseline(), event("stage", "STAGE", 1), event("verify", "VERIFY", 2),
            event("rollback", "ROLLBACK", 3), event("commit", "COMMIT", 4),
        ])
        self.assertEqual(self.reasons(result), [("commit", "commit_without_stage")])
        self.assertEqual(result["totals"]["accepted_rollbacks"], 1)
        self.assertEqual(result["totals"]["applied_commits"], 0)
        self.assertEqual(result["boards"][0]["active_digest"], "new")

    def test_empty_input_has_exact_zero_report(self):
        self.assertEqual(reconcile([]), {
            "boards": [], "incidents": [], "totals": {
                "board_count": 0, "applied_commits": 0, "accepted_rollbacks": 0,
                "duplicate_replays": 0, "conflicted_ids": 0, "rejected_events": 0,
            },
        })


class ReportContract(unittest.TestCase):
    def test_report_projects_only_public_keys_and_sorts_full_incident_location(self):
        boards = [
            {"board": board, "epoch": 2, "active_slot": "A", "active_digest": "old",
             "timestamp": 100, "pending": {}}
            for board in ("zulu", "alpha")
        ]
        locations = [
            ("zulu", 0, 0, "a", "commit_failed"),
            ("alpha", 2, 0, "a", "commit_failed"),
            ("alpha", 1, 2, "b", "verify_failed"),
            ("alpha", 1, 2, "a", "verify_failed"),
            ("alpha", 1, 2, "a", "commit_failed"),
            ("alpha", 1, 1, "z", "commit_failed"),
        ]
        keys = ("board", "epoch", "sequence", "event_id", "reason")
        incidents = [dict(zip(keys, location), timestamp=100) for location in locations]
        result = build_report(boards, incidents, {
            "applied_commits": 3, "accepted_rollbacks": 4,
            "duplicate_replays": 5, "conflicted_ids": 6, "internal": 99,
        })
        self.assertEqual(set(result), {"boards", "incidents", "totals"})
        self.assertEqual([row["board"] for row in result["boards"]], ["alpha", "zulu"])
        self.assertEqual(set(result["boards"][0]), {
            "board", "epoch", "active_slot", "active_digest",
        })
        self.assertEqual(result["incidents"], [dict(zip(keys, row)) for row in sorted(locations)])
        self.assertEqual(result["totals"], {
            "board_count": 2, "applied_commits": 3, "accepted_rollbacks": 4,
            "duplicate_replays": 5, "conflicted_ids": 6, "rejected_events": 6,
        })


if __name__ == "__main__":
    unittest.main()
