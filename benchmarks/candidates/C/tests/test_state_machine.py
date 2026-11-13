import unittest

from state_machine import apply_events


def event(sequence, action, *, epoch=0, timestamp=None, tx="tx", slot="B",
          digest="new", success=True, board="board", event_id=None):
    return {
        "event_id": event_id or "{}-{}".format(board, sequence),
        "board": board,
        "epoch": epoch,
        "sequence": sequence,
        "action": action,
        "timestamp": sequence if timestamp is None else timestamp,
        "tx": tx,
        "slot": slot,
        "digest": digest,
        "success": success,
    }


def baseline(**kwargs):
    return event(0, "BASELINE", tx=None, slot="A", digest="old", **kwargs)


class StateMachineContract(unittest.TestCase):
    def test_audit_records_accepted_commit_in_execution_order(self):
        events = [
            baseline(timestamp=1000),
            event(10, "STAGE", timestamp=3),
            event(20, "VERIFY", timestamp=2),
            event(30, "COMMIT", timestamp=1),
        ]
        audit = []
        result = apply_events(reversed(events), audit=audit)
        self.assertEqual(result, apply_events(events))
        self.assertEqual([item["action"] for item in audit],
                         ["BASELINE", "STAGE", "VERIFY", "COMMIT"])
        self.assertEqual([item["active_digest"] for item in audit],
                         ["old", "old", "old", "new"])
        self.assertEqual(audit[-1], {
            "board": "board", "epoch": 0, "sequence": 30,
            "event_id": "board-30", "action": "COMMIT", "tx": "tx",
            "slot": "B", "digest": "new", "success": True,
            "outcome": "accepted", "reason": None,
            "active_slot": "B", "active_digest": "new",
        })
        for item in audit:
            self.assertEqual(set(item), set(audit[-1]))
            self.assertEqual(item["outcome"], "accepted")
            self.assertIsNone(item["reason"])

    def test_audit_rejected_attempt_preserves_active_image(self):
        marker = {"existing": True}
        audit = [marker]
        boards, incidents, counts = apply_events([
            baseline(), event(1, "STAGE"), event(2, "COMMIT"),
        ], audit=audit)
        self.assertIs(audit[0], marker)
        self.assertEqual(len(audit), 4)
        self.assertEqual(audit[-1]["outcome"], "rejected")
        self.assertEqual(audit[-1]["reason"], "commit_unverified")
        self.assertEqual(audit[-1]["active_slot"], "A")
        self.assertEqual(audit[-1]["active_digest"], "old")
        self.assertEqual(boards[0]["active_digest"], "old")
        self.assertEqual(incidents[0]["reason"], audit[-1]["reason"])
        self.assertEqual(counts["applied_commits"], 0)

    def test_failed_verify_without_pending_reports_missing_stage_first(self):
        audit = []
        _, incidents, _ = apply_events([
            baseline(), event(1, "VERIFY", success=False),
        ], audit=audit)
        self.assertEqual(incidents[0]["reason"], "verify_without_stage")
        self.assertFalse(audit[-1]["success"])
        self.assertEqual(audit[-1]["reason"], "verify_without_stage")
        self.assertEqual(audit[-1]["outcome"], "rejected")

    def test_baseline_initializes_before_sequence_ordered_events(self):
        events = [
            baseline(timestamp=1000),
            event(10, "STAGE", timestamp=3),
            event(20, "VERIFY", timestamp=2),
            event(30, "COMMIT", timestamp=1),
        ]
        boards, incidents, counts = apply_events(reversed(events))
        self.assertEqual(boards[0]["active_digest"], "new")
        self.assertEqual(incidents, [])
        self.assertEqual(counts["applied_commits"], 1)

    def test_event_id_breaks_sequence_ties_without_timestamp_input(self):
        events = [
            baseline(),
            event(1, "STAGE", event_id="a-stage"),
            event(1, "VERIFY", event_id="b-verify"),
            event(1, "COMMIT", event_id="c-commit"),
        ]
        for item in events:
            del item["timestamp"]
        audit = []
        _, incidents, counts = apply_events(reversed(events), audit=audit)
        self.assertEqual([item["event_id"] for item in audit],
                         ["board-0", "a-stage", "b-verify", "c-commit"])
        self.assertEqual(incidents, [])
        self.assertEqual(counts["applied_commits"], 1)

    def test_epoch_advance_clears_pending_verification(self):
        boards, incidents, counts = apply_events([
            baseline(), event(1, "STAGE"), event(2, "VERIFY"),
            event(4, "COMMIT", epoch=1, timestamp=-4),
            event(5, "COMMIT", epoch=1, timestamp=-3),
        ])
        self.assertEqual(boards[0]["epoch"], 1)
        self.assertEqual(boards[0]["active_digest"], "old")
        self.assertEqual([item["reason"] for item in incidents],
                         ["commit_without_stage", "commit_without_stage"])
        self.assertEqual(counts["applied_commits"], 0)

    def test_epoch_jump_clears_all_transactions_even_when_first_event_fails(self):
        audit = []
        boards, incidents, counts = apply_events([
            baseline(), event(10, "STAGE"), event(20, "VERIFY"),
            event(30, "STAGE", tx="other", digest="other"),
            event(40, "VERIFY", tx="other", digest="other"),
            event(0, "RESET", epoch=4, success=False, event_id="epoch-4-reset"),
            event(1, "VERIFY", epoch=4),
            event(2, "COMMIT", epoch=4, tx="other", digest="other"),
        ], audit=audit)
        self.assertEqual(boards[0]["epoch"], 4)
        self.assertEqual(boards[0]["active_digest"], "old")
        self.assertEqual([item["reason"] for item in incidents],
                         ["reset_failed", "verify_without_stage", "commit_without_stage"])
        self.assertEqual(audit[5]["event_id"], "epoch-4-reset")
        self.assertEqual(audit[5]["active_digest"], "old")
        self.assertEqual(counts["applied_commits"], 0)

    def test_first_new_epoch_stage_survives_transition_and_can_be_committed(self):
        boards, incidents, counts = apply_events([
            baseline(), event(10, "STAGE", digest="obsolete"),
            event(20, "VERIFY", digest="obsolete"),
            event(0, "STAGE", epoch=3, event_id="epoch-3-stage"),
            event(1, "VERIFY", epoch=3), event(2, "COMMIT", epoch=3),
        ])
        self.assertEqual(boards[0]["epoch"], 3)
        self.assertEqual(boards[0]["active_digest"], "new")
        self.assertEqual(incidents, [])
        self.assertEqual(counts["applied_commits"], 1)

    def test_epoch_keeps_active_image_and_exact_rollback_history(self):
        audit = []
        boards, incidents, counts = apply_events([
            baseline(), event(10, "STAGE"), event(20, "VERIFY"),
            event(30, "COMMIT"),
            event(0, "RESET", epoch=2, success=False, event_id="epoch-2-reset"),
            event(1, "ROLLBACK", epoch=2, slot="A", digest="new"),
            event(2, "ROLLBACK", epoch=2),
            event(3, "ROLLBACK", epoch=2, slot="A", digest="old"),
        ], audit=audit)
        self.assertEqual([item["reason"] for item in incidents],
                         ["reset_failed", "rollback_unverified"])
        self.assertEqual(audit[4]["active_digest"], "new")
        self.assertEqual(audit[5]["active_slot"], "B")
        self.assertEqual(audit[5]["active_digest"], "new")
        self.assertEqual(audit[6]["outcome"], "accepted")
        self.assertEqual(boards[0]["active_digest"], "old")
        self.assertEqual(counts, {"applied_commits": 1, "accepted_rollbacks": 2})

    def test_failed_verify_invalidates_only_its_tx_and_allows_reverification(self):
        audit = []
        boards, incidents, counts = apply_events([
            baseline(), event(1, "STAGE"), event(2, "VERIFY"),
            event(3, "STAGE", tx="other", digest="other"),
            event(4, "VERIFY", tx="other", digest="other"),
            event(5, "VERIFY", success=False), event(6, "COMMIT"),
            event(7, "COMMIT", tx="other", digest="other"),
            event(8, "VERIFY"), event(9, "COMMIT"),
        ], audit=audit)
        self.assertEqual([item["reason"] for item in incidents],
                         ["verify_failed", "commit_unverified"])
        self.assertEqual(audit[6]["active_digest"], "old")
        self.assertEqual(audit[7]["active_digest"], "other")
        self.assertEqual(audit[9]["active_digest"], "new")
        self.assertEqual(boards[0]["active_digest"], "new")
        self.assertEqual(counts["applied_commits"], 2)

    def test_failed_verify_keeps_image_in_rollback_history(self):
        boards, incidents, counts = apply_events([
            baseline(), event(1, "STAGE"), event(2, "VERIFY"),
            event(3, "VERIFY", success=False), event(4, "ROLLBACK", epoch=1),
        ])
        self.assertEqual([item["reason"] for item in incidents], ["verify_failed"])
        self.assertEqual(boards[0]["active_digest"], "new")
        self.assertEqual(counts, {"applied_commits": 0, "accepted_rollbacks": 1})

    def test_successful_verify_mismatch_clears_pending_verification(self):
        boards, incidents, counts = apply_events([
            baseline(), event(1, "STAGE"), event(2, "VERIFY"),
            event(3, "VERIFY", digest="other"), event(4, "COMMIT"),
            event(5, "ROLLBACK"),
        ])
        self.assertEqual([item["reason"] for item in incidents],
                         ["verify_mismatch", "commit_unverified"])
        self.assertEqual(counts, {"applied_commits": 0, "accepted_rollbacks": 1})
        self.assertEqual(boards[0]["active_digest"], "new")

    def test_failed_stage_preserves_pending_and_restage_clears_verification(self):
        boards, incidents, counts = apply_events([
            baseline(), event(1, "STAGE"), event(2, "VERIFY"),
            event(3, "STAGE", digest="other", success=False),
            event(4, "COMMIT"), event(5, "STAGE"), event(6, "VERIFY"),
            event(7, "STAGE"), event(8, "COMMIT"),
        ])
        self.assertEqual([item["reason"] for item in incidents],
                         ["stage_failed", "commit_unverified"])
        self.assertEqual(counts["applied_commits"], 1)
        self.assertEqual(boards[0]["active_digest"], "new")

    def test_commit_rejections_preserve_pending_and_failed_commit_has_priority(self):
        _, incidents, counts = apply_events([
            baseline(), event(1, "COMMIT", success=False),
            event(2, "STAGE"), event(3, "COMMIT", digest="other"),
            event(4, "COMMIT"), event(5, "VERIFY"),
            event(6, "COMMIT", success=False), event(7, "COMMIT"),
        ])
        self.assertEqual([item["reason"] for item in incidents], [
            "commit_failed", "commit_mismatch", "commit_unverified", "commit_failed"
        ])
        self.assertEqual(counts["applied_commits"], 1)

    def test_successful_reset_clears_all_pending_but_keeps_history(self):
        boards, incidents, counts = apply_events([
            baseline(), event(1, "STAGE"), event(2, "VERIFY"),
            event(3, "STAGE", tx="other", digest="other"),
            event(4, "RESET", success=False), event(5, "COMMIT"),
            event(6, "STAGE"), event(7, "RESET"), event(8, "VERIFY"),
            event(9, "VERIFY", tx="other", digest="other"),
            event(10, "ROLLBACK", slot="A", digest="old"),
        ])
        self.assertEqual([item["reason"] for item in incidents], [
            "reset_failed", "verify_without_stage", "verify_without_stage"
        ])
        self.assertEqual(boards[0]["active_digest"], "old")
        self.assertEqual(counts, {"applied_commits": 1, "accepted_rollbacks": 1})

    def test_rollback_requires_exact_image_and_clears_pending_only_when_accepted(self):
        boards, incidents, counts = apply_events([
            baseline(), event(1, "STAGE"), event(2, "VERIFY"),
            event(3, "ROLLBACK", slot="B", digest="old"),
            event(4, "ROLLBACK", slot="A", digest="old", success=False),
            event(5, "COMMIT"), event(6, "STAGE", tx="other"),
            event(7, "ROLLBACK", slot="A", digest="old"),
            event(8, "VERIFY", tx="other"),
        ])
        self.assertEqual([item["reason"] for item in incidents], [
            "rollback_unverified", "rollback_failed", "verify_without_stage"
        ])
        self.assertEqual(boards[0]["active_digest"], "old")
        self.assertEqual(counts, {"applied_commits": 1, "accepted_rollbacks": 1})

    def test_verification_history_is_board_local(self):
        boards, incidents, counts = apply_events([
            baseline(board="first"), event(1, "STAGE", board="first"),
            event(2, "VERIFY", board="first"), baseline(board="second"),
            event(1, "ROLLBACK", board="second"),
        ])
        self.assertEqual(len(boards), 2)
        self.assertEqual(incidents[0]["board"], "second")
        self.assertEqual(incidents[0]["reason"], "rollback_unverified")
        self.assertEqual(counts["accepted_rollbacks"], 0)

    def test_missing_baseline_after_conflict_removal_has_null_active_image(self):
        boards, incidents, counts = apply_events([event(1, "COMMIT", epoch=3)])
        self.assertEqual(boards, [{
            "board": "board", "epoch": 3, "active_slot": None, "active_digest": None
        }])
        self.assertEqual(incidents[0]["reason"], "commit_without_stage")
        self.assertEqual(counts["applied_commits"], 0)


if __name__ == "__main__":
    unittest.main()
