import unittest
from unittest.mock import patch

from state_machine import reconstruct


def event(sequence, action, **changes):
    row = {
        "event_id": "event-%02d" % sequence,
        "board": "board",
        "epoch": 0,
        "sequence": sequence,
        "action": action,
        "tx": "transaction",
        "slot": "B",
        "digest": "new",
        "success": True,
    }
    row.update(changes)
    return row


def baseline(**changes):
    return event(0, "BASELINE", slot="A", digest="old", **changes)


class StateMachineContract(unittest.TestCase):
    def test_r2_sequence_order_ignores_deliberately_reversed_timestamps(self):
        boards, incidents, counts = reconstruct([
            event(3, "COMMIT", timestamp=1),
            baseline(timestamp=100),
            event(1, "STAGE", timestamp=3),
            event(2, "VERIFY", timestamp=2),
        ])
        self.assertEqual(incidents, [])
        self.assertEqual(counts["applied_commits"], 1)
        self.assertEqual(boards[0]["active_digest"], "new")

    def test_same_epoch_pending_failure_revokes_and_later_verify_restores(self):
        trace = []
        boards, incidents, counts = reconstruct([
            baseline(),
            event(1, "STAGE"),
            event(2, "VERIFY"),
            event(3, "VERIFY", success=False),
            event(4, "COMMIT"),
            event(5, "VERIFY"),
            event(6, "COMMIT"),
            event(7, "COMMIT"),
        ], audit=trace)
        self.assertEqual([i["reason"] for i in incidents], [
            "verify_failed", "commit_unverified", "commit_without_stage",
        ])
        self.assertEqual(counts["applied_commits"], 1)
        self.assertEqual(boards[0]["epoch"], 0)
        self.assertTrue(trace[3]["pending_before"][0]["verified"])
        self.assertFalse(trace[3]["pending_after"][0]["verified"])
        self.assertTrue(trace[5]["pending_after"][0]["verified"])
        self.assertFalse(trace[5]["verified_image_added"])

    def test_epoch_precedes_sequence_and_requires_restage_and_reverify(self):
        boards, incidents, counts = reconstruct([
            event(1, "COMMIT", epoch=1),
            event(101, "VERIFY"),
            baseline(),
            event(100, "STAGE"),
            event(2, "VERIFY", epoch=1),
            event(3, "STAGE", epoch=1),
            event(4, "COMMIT", epoch=1),
            event(5, "VERIFY", epoch=1),
            event(6, "COMMIT", epoch=1),
        ])
        self.assertEqual([row["reason"] for row in incidents], [
            "commit_without_stage", "verify_without_stage", "commit_unverified",
        ])
        self.assertEqual(counts["applied_commits"], 1)
        self.assertEqual(boards[0]["active_digest"], "new")
        self.assertEqual(boards[0]["epoch"], 1)

    def test_epoch_gap_clears_all_transactions_before_every_failing_action(self):
        reasons = {
            "STAGE": "stage_failed",
            "VERIFY": "verify_without_stage",
            "RESET": "reset_failed",
            "COMMIT": "commit_failed",
            "ROLLBACK": "rollback_failed",
        }
        for action, reason in reasons.items():
            with self.subTest(action=action):
                trace = []
                boards, incidents, counts = reconstruct([
                    baseline(epoch=2),
                    event(1, "STAGE", tx=None, epoch=2),
                    event(2, "VERIFY", tx=None, epoch=2),
                    event(3, "STAGE", tx="other", epoch=2),
                    event(4, "VERIFY", tx="other", epoch=2),
                    event(0, action, event_id="boundary", tx=None,
                          success=False, epoch=7),
                    event(1, "COMMIT", event_id="stale-other", tx="other", epoch=7),
                    event(0, "ROLLBACK", event_id="history", epoch=8),
                ], audit=trace)
                self.assertEqual([row["reason"] for row in incidents],
                                 [reason, "commit_without_stage"])
                self.assertEqual(counts,
                                 {"applied_commits": 0, "accepted_rollbacks": 1})
                self.assertEqual(boards[0]["epoch"], 8)
                self.assertEqual(boards[0]["active_digest"], "new")
                self.assertEqual(trace[0]["epoch_before"], 2)
                self.assertFalse(trace[0]["epoch_advanced"])
                boundary = trace[5]
                self.assertEqual(boundary["epoch_before"], 2)
                self.assertTrue(boundary["epoch_advanced"])
                self.assertEqual([row["tx"] for row in boundary["pending_before"]],
                                 [None, "other"])
                self.assertTrue(all(row["verified"] for row in boundary["pending_before"]))
                self.assertEqual(boundary["pending_after_epoch"], [])
                self.assertEqual(boundary["pending_after"], [])
                self.assertEqual(boundary["active_before"], boundary["active_after"])
                self.assertFalse(trace[6]["epoch_advanced"])
                self.assertTrue(trace[7]["epoch_advanced"])

    def test_epoch_boundary_snapshots_separate_clear_from_new_stage(self):
        trace = []
        reconstruct([
            baseline(),
            event(1, "STAGE"),
            event(2, "VERIFY"),
            event(0, "STAGE", event_id="new-stage", epoch=4, digest="replacement"),
            event(1, "VERIFY", event_id="new-verify", epoch=4, digest="replacement"),
        ], audit=trace)
        boundary = trace[3]
        self.assertTrue(boundary["pending_before"][0]["verified"])
        self.assertEqual(boundary["pending_before"][0]["digest"], "new")
        self.assertEqual(boundary["pending_after_epoch"], [])
        self.assertEqual(boundary["pending_after"], [{
            "tx": "transaction", "slot": "B", "digest": "replacement", "verified": False,
        }])
        boundary["pending_after_epoch"].append({"changed": "snapshot"})
        boundary["pending_before"][0]["digest"] = "changed snapshot"
        self.assertEqual(trace[2]["pending_after"][0]["digest"], "new")
        self.assertEqual(trace[4]["pending_before"][0]["digest"], "replacement")
        trace[4]["pending_after_epoch"][0]["verified"] = "changed snapshot"
        self.assertFalse(trace[4]["pending_before"][0]["verified"])
        self.assertTrue(trace[4]["pending_after"][0]["verified"])

    def test_failed_verify_only_revokes_target_pending_and_preserves_history(self):
        trace = []
        boards, incidents, counts = reconstruct([
            baseline(),
            event(1, "STAGE"),
            event(2, "VERIFY"),
            event(3, "STAGE", tx="other", slot="A", digest="other"),
            event(4, "VERIFY", tx="other", slot="A", digest="other"),
            event(5, "VERIFY", success=False, slot="A", digest="different"),
            event(6, "COMMIT", tx="other", slot="A", digest="other"),
            event(7, "COMMIT"),
            event(8, "ROLLBACK"),
        ], audit=trace)
        self.assertEqual([row["reason"] for row in incidents],
                         ["verify_failed", "commit_unverified"])
        self.assertEqual(counts, {"applied_commits": 1, "accepted_rollbacks": 1})
        self.assertEqual(boards[0]["active_digest"], "new")
        pending = {row["tx"]: row for row in trace[5]["pending_after"]}
        self.assertTrue(pending["other"]["verified"])
        self.assertEqual(pending["transaction"], {
            "tx": "transaction", "slot": "B", "digest": "new", "verified": False,
        })
        self.assertEqual(trace[5]["active_before"], trace[5]["active_after"])
        self.assertFalse(trace[5]["verified_image_added"])

    def test_verification_mismatch_and_restage_clear_flag(self):
        boards, incidents, counts = reconstruct([
            baseline(),
            event(1, "STAGE"),
            event(2, "VERIFY"),
            event(3, "VERIFY", digest="different"),
            event(4, "COMMIT"),
            event(5, "VERIFY"),
            event(6, "STAGE"),
            event(7, "COMMIT"),
            event(8, "VERIFY"),
            event(9, "COMMIT"),
        ])
        self.assertEqual([i["reason"] for i in incidents], [
            "verify_mismatch", "commit_unverified", "commit_unverified",
        ])
        self.assertEqual(counts["applied_commits"], 1)
        self.assertEqual(boards[0]["active_slot"], "B")

    def test_failures_and_commit_mismatch_do_not_mutate_pending(self):
        _, incidents, counts = reconstruct([
            baseline(),
            event(1, "STAGE"),
            event(2, "VERIFY"),
            event(3, "STAGE", success=False, digest="different"),
            event(4, "RESET", success=False),
            event(5, "COMMIT", success=False),
            event(6, "COMMIT", digest="different"),
            event(7, "ROLLBACK", success=False, slot="A", digest="old"),
            event(8, "ROLLBACK", slot="B", digest="old"),
            event(9, "COMMIT"),
        ])
        self.assertEqual([i["reason"] for i in incidents], [
            "stage_failed", "reset_failed", "commit_failed",
            "commit_mismatch", "rollback_failed", "rollback_unverified",
        ])
        self.assertEqual(counts, {"applied_commits": 1, "accepted_rollbacks": 0})

    def test_rollback_history_is_exact_and_clears_all_pending(self):
        boards, incidents, counts = reconstruct([
            baseline(),
            event(1, "STAGE"),
            event(2, "VERIFY"),
            event(3, "STAGE", tx="other"),
            event(4, "VERIFY", tx="other"),
            event(5, "ROLLBACK", slot="A", digest="new", epoch=1),
            event(6, "STAGE", epoch=1),
            event(7, "VERIFY", epoch=1),
            event(8, "STAGE", tx="other", epoch=1),
            event(9, "VERIFY", tx="other", epoch=1),
            event(10, "ROLLBACK", epoch=1),
            event(11, "COMMIT", epoch=1),
            event(12, "COMMIT", tx="other", epoch=1),
            event(13, "ROLLBACK", slot="A", digest="old", epoch=2),
        ])
        self.assertEqual([i["reason"] for i in incidents], [
            "rollback_unverified", "commit_without_stage", "commit_without_stage",
        ])
        self.assertEqual(counts, {"applied_commits": 0, "accepted_rollbacks": 2})
        self.assertEqual(boards[0]["active_digest"], "old")

    def test_rollback_history_survives_epochs_but_is_slot_exact_and_board_local(self):
        rows = [
            baseline(board="alpha"),
            event(1, "STAGE", board="alpha"),
            event(2, "VERIFY", board="alpha"),
            event(3, "ROLLBACK", board="alpha", epoch=5, slot="A"),
            event(4, "ROLLBACK", board="alpha", epoch=5),
            baseline(board="beta", event_id="beta-baseline"),
            event(1, "ROLLBACK", board="beta", epoch=5, event_id="beta-rollback"),
        ]
        boards, incidents, counts = reconstruct(reversed(rows))
        self.assertEqual([(row["board"], row["reason"]) for row in incidents], [
            ("alpha", "rollback_unverified"), ("beta", "rollback_unverified"),
        ])
        self.assertEqual(counts, {"applied_commits": 0, "accepted_rollbacks": 1})
        self.assertEqual([(row["board"], row["active_slot"], row["active_digest"])
                          for row in boards], [("alpha", "B", "new"), ("beta", "A", "old")])

    def test_reset_clears_pending_but_keeps_history_and_active_image(self):
        boards, incidents, counts = reconstruct([
            baseline(),
            event(1, "STAGE"),
            event(2, "VERIFY"),
            event(3, "RESET"),
            event(4, "VERIFY"),
            event(5, "COMMIT"),
            event(6, "ROLLBACK"),
        ])
        self.assertEqual([i["reason"] for i in incidents], [
            "verify_without_stage", "commit_without_stage",
        ])
        self.assertEqual(counts["accepted_rollbacks"], 1)
        self.assertEqual(boards[0]["active_digest"], "new")

    def test_missing_baseline_does_not_authorize_a_rollback(self):
        boards, incidents, counts = reconstruct([
            event(1, "ROLLBACK", slot=None, digest=None),
            event(2, "VERIFY", success=False),
            event(3, "COMMIT", success=False),
        ])
        self.assertIsNone(boards[0]["active_slot"])
        self.assertIsNone(boards[0]["active_digest"])
        self.assertEqual([i["reason"] for i in incidents], [
            "rollback_unverified", "verify_without_stage", "commit_failed",
        ])
        self.assertEqual(counts, {"applied_commits": 0, "accepted_rollbacks": 0})

    def test_audit_is_optional_and_does_not_change_reconstruction(self):
        events = [
            baseline(),
            event(1, "STAGE"),
            event(2, "VERIFY"),
            event(3, "VERIFY", digest="wrong"),
            event(4, "COMMIT"),
            event(5, "VERIFY"),
            event(6, "COMMIT"),
            event(7, "ROLLBACK", slot="A", digest="old"),
        ]
        with patch("state_machine._pending_snapshot", side_effect=AssertionError):
            expected = reconstruct(events)
        trace = [{"existing": "caller entry"}]
        self.assertEqual(reconstruct(events, audit=trace), expected)
        self.assertEqual(trace[0], {"existing": "caller entry"})
        self.assertEqual(len(trace), len(events) + 1)
        self.assertEqual(set(trace[1]), {
            "board", "epoch", "sequence", "event_id", "action", "tx", "slot",
            "digest", "reported_success", "outcome", "reason", "active_before",
            "active_after", "pending_before", "pending_after", "verified_image_added",
            "epoch_before", "epoch_advanced", "pending_after_epoch",
        })
        mismatch = trace[4]
        self.assertEqual((mismatch["outcome"], mismatch["reason"]),
                         ("rejected", "verify_mismatch"))
        self.assertTrue(mismatch["pending_before"][0]["verified"])
        self.assertFalse(mismatch["pending_after"][0]["verified"])

    def test_trace_follows_epoch_sequence_and_event_id_order(self):
        trace = []
        reconstruct([
            event(7, "COMMIT", event_id="tie-c", timestamp=10),
            baseline(timestamp=100),
            event(7, "STAGE", event_id="tie-a", timestamp=30),
            event(7, "VERIFY", event_id="tie-b", timestamp=20),
        ], audit=trace)
        self.assertEqual([row["event_id"] for row in trace],
                         ["event-00", "tie-a", "tie-b", "tie-c"])
        self.assertEqual(trace[0]["active_before"], {"slot": None, "digest": None})
        self.assertEqual(trace[0]["active_after"], {"slot": "A", "digest": "old"})
        self.assertTrue(trace[0]["verified_image_added"])
        self.assertEqual([row["outcome"] for row in trace], ["accepted"] * 4)

    def test_trace_snapshots_are_independent_and_pending_order_handles_null(self):
        trace = []
        boards, _, _ = reconstruct([
            baseline(),
            event(1, "STAGE", tx="z"),
            event(2, "STAGE", tx=None),
            event(3, "STAGE", tx="a"),
            event(4, "VERIFY", tx=None),
        ], audit=trace)
        self.assertEqual([row["tx"] for row in trace[3]["pending_after"]],
                         [None, "a", "z"])
        self.assertFalse(trace[3]["pending_after"][0]["verified"])
        self.assertFalse(trace[4]["pending_before"][0]["verified"])
        self.assertTrue(trace[4]["pending_after"][0]["verified"])
        trace[4]["pending_before"][0]["digest"] = "changed snapshot"
        self.assertEqual(trace[3]["pending_after"][0]["digest"], "new")
        self.assertEqual(trace[4]["pending_after"][0]["digest"], "new")
        trace[0]["active_after"]["digest"] = "changed snapshot"
        self.assertEqual(trace[1]["active_before"]["digest"], "old")
        self.assertEqual(boards[0]["active_digest"], "old")

    def test_trace_distinguishes_reported_commit_success_from_applied_commit(self):
        trace = []
        _, _, counters = reconstruct([
            baseline(),
            event(1, "COMMIT"),
            event(2, "STAGE"),
            event(3, "COMMIT"),
            event(4, "VERIFY"),
            event(5, "COMMIT", digest="wrong"),
            event(6, "COMMIT", success=False),
            event(7, "COMMIT"),
            event(8, "STAGE"),
            event(9, "VERIFY"),
            event(10, "COMMIT"),
        ], audit=trace)
        commits = [row for row in trace if row["action"] == "COMMIT"]
        self.assertEqual([row["reported_success"] for row in commits],
                         [True, True, True, False, True, True])
        self.assertEqual([row["outcome"] for row in commits],
                         ["rejected"] * 4 + ["accepted"] * 2)
        self.assertEqual([row["reason"] for row in commits], [
            "commit_without_stage", "commit_unverified", "commit_mismatch",
            "commit_failed", None, None,
        ])
        self.assertEqual(commits[-1]["active_before"], commits[-1]["active_after"])
        self.assertEqual(counters["applied_commits"], 2)
        self.assertEqual([row["verified_image_added"] for row in trace
                          if row["action"] == "VERIFY"], [True, False])

    def test_trace_marks_out_of_contract_ignored_rows(self):
        trace = []
        _, incidents, counters = reconstruct([
            baseline(),
            event(1, "BASELINE", success=False),
            event(2, "UNKNOWN"),
        ], audit=trace)
        self.assertEqual([row["outcome"] for row in trace],
                         ["accepted", "ignored", "ignored"])
        self.assertTrue(all(row["reason"] is None for row in trace))
        self.assertEqual(incidents, [])
        self.assertEqual(counters, {"applied_commits": 0, "accepted_rollbacks": 0})


if __name__ == "__main__":
    unittest.main()
