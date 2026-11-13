import unittest

from state_machine import reconcile_states


def event(sequence, action, *, epoch=0, timestamp=None, success=True,
          tx="tx", slot="B", digest="new", board="board", event_id=None):
    return {
        "event_id": event_id or f"event-{sequence}",
        "board": board,
        "epoch": epoch,
        "sequence": sequence,
        "action": action,
        "tx": tx,
        "slot": slot,
        "digest": digest,
        "success": success,
        "timestamp": sequence if timestamp is None else timestamp,
    }


def baseline(**kwargs):
    return event(0, "BASELINE", tx=None, slot="A", digest="old", **kwargs)


class StateMachineContract(unittest.TestCase):
    def reasons(self, result):
        return [incident["reason"] for incident in result[1]]

    def test_baseline_initializes_first_despite_timestamp(self):
        result = reconcile_states([
            event(3, "COMMIT"), baseline(timestamp=100),
            event(2, "VERIFY"), event(1, "STAGE"),
        ])
        self.assertEqual(result[0], [{
            "board": "board", "epoch": 0,
            "active_slot": "B", "active_digest": "new",
        }])
        self.assertEqual(result[1:], ([], 1, 0))

    def test_sequence_precedes_skewed_timestamps(self):
        events = [baseline(), event(1, "STAGE", timestamp=30),
                  event(2, "VERIFY", timestamp=20),
                  event(3, "COMMIT", timestamp=10)]
        trace = []
        result = reconcile_states(list(reversed(events)), trace=trace)
        self.assertEqual(result[2], 1)
        self.assertEqual([row["sequence"] for row in trace], [0, 1, 2, 3])

    def test_sequence_ties_use_event_id_despite_skewed_timestamps(self):
        events = [baseline(), event(1, "STAGE", timestamp=50),
                  event(2, "VERIFY", timestamp=100, event_id="a"),
                  event(2, "COMMIT", timestamp=-100, event_id="b")]
        trace = []
        result = reconcile_states(list(reversed(events)), trace=trace)
        self.assertEqual(result[2], 1)
        self.assertEqual([row["event_id"] for row in trace],
                         ["event-0", "event-1", "a", "b"])

    def test_epoch_advancement_clears_pending_but_retains_history(self):
        trace = []
        result = reconcile_states([
            baseline(), event(1, "STAGE"), event(2, "VERIFY"),
            event(0, "COMMIT", epoch=1, timestamp=-100, event_id="next-boot"),
            event(1, "ROLLBACK", epoch=2, event_id="history-rollback"),
        ], trace=trace)
        self.assertEqual(result[0][0]["epoch"], 2)
        self.assertEqual(result[0][0]["active_digest"], "new")
        self.assertEqual(self.reasons(result), ["commit_without_stage"])
        self.assertEqual(result[2:], (0, 1))
        self.assertEqual(trace[3]["active_digest_before"], "old")
        self.assertEqual(trace[3]["active_digest_after"], "old")

    def test_epoch_jump_clears_all_pending_transactions(self):
        result = reconcile_states([
            baseline(epoch=2), event(1, "STAGE", epoch=2),
            event(2, "VERIFY", epoch=2),
            event(3, "STAGE", epoch=2, tx="other", digest="other"),
            event(4, "VERIFY", epoch=2, tx="other", digest="other"),
            event(0, "COMMIT", epoch=8, event_id="new-boot-tx"),
            event(1, "COMMIT", epoch=8, tx="other", digest="other",
                  event_id="new-boot-other"),
        ])
        self.assertEqual(result[0][0]["epoch"], 8)
        self.assertEqual(result[0][0]["active_digest"], "old")
        self.assertEqual(self.reasons(result),
                         ["commit_without_stage", "commit_without_stage"])
        self.assertEqual(result[2], 0)

    def test_failed_first_event_of_epoch_still_clears_pending(self):
        for action, reason in (
            ("RESET", "reset_failed"), ("STAGE", "stage_failed"),
            ("VERIFY", "verify_without_stage"), ("COMMIT", "commit_failed"),
            ("ROLLBACK", "rollback_failed"),
        ):
            with self.subTest(action=action):
                result = reconcile_states([
                    baseline(), event(1, "STAGE"), event(2, "VERIFY"),
                    event(0, action, epoch=1, success=False,
                          event_id="new-boot-failure"),
                    event(1, "COMMIT", epoch=1, event_id="new-boot-commit"),
                ])
                self.assertEqual(self.reasons(result), [reason, "commit_without_stage"])
                self.assertEqual(result[0][0]["epoch"], 1)
                self.assertEqual(result[0][0]["active_digest"], "old")
                self.assertEqual(result[2], 0)

    def test_epoch_change_retains_active_image_and_exact_verified_pairs(self):
        trace = []
        result = reconcile_states([
            baseline(), event(1, "STAGE"), event(2, "VERIFY"), event(3, "COMMIT"),
            event(4, "STAGE", slot="A", digest="candidate"),
            event(5, "VERIFY", slot="A", digest="candidate"),
            event(0, "COMMIT", epoch=3, slot="A", digest="candidate",
                  event_id="after-jump-commit"),
            event(1, "ROLLBACK", epoch=3, slot="B", digest="candidate",
                  event_id="wrong-slot-rollback"),
            event(2, "ROLLBACK", epoch=3, slot="A", digest="candidate",
                  event_id="exact-pair-rollback"),
            event(3, "ROLLBACK", epoch=3, slot="A", digest="old",
                  event_id="baseline-rollback"),
        ], trace=trace)
        self.assertEqual(self.reasons(result), ["commit_without_stage", "rollback_unverified"])
        self.assertEqual(result[2:], (1, 2))
        self.assertEqual(result[0][0]["epoch"], 3)
        self.assertEqual(result[0][0]["active_digest"], "old")
        self.assertEqual(trace[6]["active_digest_before"], "new")
        self.assertEqual(trace[6]["active_digest_after"], "new")
        self.assertEqual(trace[7]["active_digest_after"], "new")
        self.assertEqual(trace[8]["active_digest_after"], "candidate")

    def test_new_epoch_can_stage_verify_and_commit_again(self):
        result = reconcile_states([
            baseline(), event(1, "STAGE"), event(2, "VERIFY"),
            event(0, "STAGE", epoch=1, digest="fresh", event_id="fresh-stage"),
            event(1, "VERIFY", epoch=1, digest="fresh", event_id="fresh-verify"),
            event(2, "COMMIT", epoch=1, digest="fresh", event_id="fresh-commit"),
        ])
        self.assertEqual(result[1:], ([], 1, 0))
        self.assertEqual(result[0][0]["active_digest"], "fresh")

    def test_failed_verify_clears_flag_even_for_mismatched_image(self):
        for changes in ({}, {"slot": "A"}, {"digest": "different"}):
            with self.subTest(changes=changes):
                result = reconcile_states([
                    baseline(), event(1, "STAGE"), event(2, "VERIFY"),
                    event(3, "VERIFY", success=False, **changes),
                    event(4, "COMMIT"),
                ])
                self.assertEqual(self.reasons(result),
                                 ["verify_failed", "commit_unverified"])
                self.assertEqual(result[2], 0)
                self.assertEqual(result[0][0]["active_digest"], "old")

    def test_fresh_verification_recovers_after_failure(self):
        result = reconcile_states([
            baseline(), event(1, "STAGE"), event(2, "VERIFY"),
            event(3, "VERIFY", success=False), event(4, "COMMIT"),
            event(5, "VERIFY"), event(6, "COMMIT"),
        ])
        self.assertEqual(self.reasons(result), ["verify_failed", "commit_unverified"])
        self.assertEqual(result[2], 1)
        self.assertEqual(result[0][0]["active_digest"], "new")

    def test_failed_verify_retains_exact_image_history(self):
        result = reconcile_states([
            baseline(), event(1, "STAGE"), event(2, "VERIFY"),
            event(3, "VERIFY", success=False), event(4, "ROLLBACK", slot="A"),
            event(5, "ROLLBACK"), event(6, "COMMIT"),
        ])
        self.assertEqual(self.reasons(result),
                         ["verify_failed", "rollback_unverified", "commit_without_stage"])
        self.assertEqual(result[2:], (0, 1))
        self.assertEqual(result[0][0]["active_slot"], "B")
        self.assertEqual(result[0][0]["active_digest"], "new")

    def test_failed_verify_clears_only_its_transaction_flag(self):
        result = reconcile_states([
            baseline(), event(1, "STAGE"), event(2, "VERIFY"),
            event(3, "STAGE", tx="other", digest="other"),
            event(4, "VERIFY", tx="other", digest="other"),
            event(5, "VERIFY", success=False),
            event(6, "COMMIT", tx="other", digest="other"), event(7, "COMMIT"),
        ])
        self.assertEqual(self.reasons(result), ["verify_failed", "commit_unverified"])
        self.assertEqual(result[2], 1)
        self.assertEqual(result[0][0]["active_digest"], "other")

    def test_verify_without_stage_precedes_failure(self):
        result = reconcile_states([
            baseline(), event(1, "VERIFY", success=False),
        ])
        self.assertEqual(self.reasons(result), ["verify_without_stage"])

    def test_verify_mismatch_clears_flag_but_retains_history(self):
        result = reconcile_states([
            baseline(), event(1, "STAGE"), event(2, "VERIFY"),
            event(3, "VERIFY", slot="A"), event(4, "COMMIT"),
            event(5, "ROLLBACK"),
        ])
        self.assertEqual(self.reasons(result), ["verify_mismatch", "commit_unverified"])
        self.assertEqual(result[2:], (0, 1))

    def test_rejected_operations_preserve_pending(self):
        for action, changes, reason in [
            ("STAGE", {"success": False, "digest": "other"}, "stage_failed"),
            ("RESET", {"success": False}, "reset_failed"),
            ("COMMIT", {"success": False}, "commit_failed"),
            ("COMMIT", {"digest": "other"}, "commit_mismatch"),
            ("ROLLBACK", {"success": False}, "rollback_failed"),
            ("ROLLBACK", {"digest": "other"}, "rollback_unverified"),
        ]:
            with self.subTest(action=action, reason=reason):
                result = reconcile_states([
                    baseline(), event(1, "STAGE"), event(2, "VERIFY"),
                    event(3, action, **changes), event(4, "COMMIT"),
                ])
                self.assertEqual(self.reasons(result), [reason])
                self.assertEqual(result[2], 1)

    def test_restage_clears_verification(self):
        result = reconcile_states([
            baseline(), event(1, "STAGE"), event(2, "VERIFY"),
            event(3, "STAGE"), event(4, "COMMIT"),
            event(5, "VERIFY"), event(6, "COMMIT"), event(7, "COMMIT"),
        ])
        self.assertEqual(self.reasons(result), ["commit_unverified", "commit_without_stage"])
        self.assertEqual(result[2], 1)

    def test_failed_commit_precedes_missing_stage(self):
        result = reconcile_states([baseline(), event(1, "COMMIT", success=False)])
        self.assertEqual(self.reasons(result), ["commit_failed"])

    def test_reset_and_rollback_clear_all_pending_transactions(self):
        for action in ("RESET", "ROLLBACK"):
            with self.subTest(action=action):
                result = reconcile_states([
                    baseline(), event(1, "STAGE"), event(2, "VERIFY"),
                    event(3, "STAGE", tx="other"), event(4, "VERIFY", tx="other"),
                    event(5, action, slot="A", digest="old"),
                    event(6, "COMMIT"), event(7, "COMMIT", tx="other"),
                    event(8, "ROLLBACK"),
                ])
                self.assertEqual(self.reasons(result), ["commit_without_stage", "commit_without_stage"])
                self.assertEqual(result[2], 0)
                self.assertEqual(result[3], 1 if action == "RESET" else 2)

    def test_history_requires_exact_slot_and_board(self):
        result = reconcile_states([
            baseline(), event(1, "ROLLBACK", slot="B", digest="old"),
            event(2, "STAGE"), event(3, "VERIFY"),
            baseline(board="other", event_id="other-baseline"),
            event(1, "ROLLBACK", board="other", event_id="other-rollback"),
        ])
        self.assertEqual(self.reasons(result), ["rollback_unverified", "rollback_unverified"])
        self.assertEqual(result[3], 0)

    def test_successful_commit_removes_only_its_own_transaction(self):
        result = reconcile_states([
            baseline(), event(1, "STAGE"), event(2, "VERIFY"),
            event(3, "STAGE", tx="other", digest="newer"),
            event(4, "VERIFY", tx="other", digest="newer"),
            event(5, "COMMIT"),
            event(6, "COMMIT", tx="other", digest="newer"),
        ])
        self.assertEqual(result[0][0]["active_digest"], "newer")
        self.assertEqual(result[1:], ([], 2, 0))

    def test_missing_baseline_retains_board_with_null_initial_image(self):
        result = reconcile_states([event(1, "COMMIT", epoch=4)])
        self.assertEqual(result[0], [{
            "board": "board", "epoch": 4,
            "active_slot": None, "active_digest": None,
        }])
        self.assertEqual(self.reasons(result), ["commit_without_stage"])

    def test_empty_input(self):
        self.assertEqual(reconcile_states([]), ([], [], 0, 0))

    def test_trace_records_reported_success_separately_from_acceptance(self):
        events = [
            baseline(timestamp=100), event(1, "COMMIT"),
            event(2, "STAGE"), event(3, "COMMIT"),
            event(4, "VERIFY"), event(5, "COMMIT"),
            event(6, "ROLLBACK", slot="A", digest="old"),
        ]
        trace = []
        result = reconcile_states(list(reversed(events)), trace=trace)
        self.assertEqual(result, reconcile_states(events))
        self.assertEqual([row["sequence"] for row in trace], list(range(7)))
        self.assertEqual([row["accepted"] for row in trace],
                         [True, False, True, False, True, True, True])
        self.assertEqual([row["reason"] for row in trace],
                         [None, "commit_without_stage", None,
                          "commit_unverified", None, None, None])
        self.assertTrue(trace[1]["success"])
        self.assertFalse(trace[1]["accepted"])
        self.assertEqual(trace[0], {
            "board": "board", "epoch": 0, "sequence": 0,
            "event_id": "event-0", "action": "BASELINE", "tx": None,
            "slot": "A", "digest": "old", "success": True,
            "accepted": True, "reason": None,
            "active_slot_before": None, "active_digest_before": None,
            "active_slot_after": "A", "active_digest_after": "old",
        })
        self.assertEqual(
            [(row["active_digest_before"], row["active_digest_after"])
             for row in trace],
            [(None, "old"), ("old", "old"), ("old", "old"),
             ("old", "old"), ("old", "old"), ("old", "new"),
             ("new", "old")],
        )
        self.assertEqual(sum(row["accepted"] and row["action"] == "COMMIT"
                             for row in trace), result[2])
        self.assertEqual(sum(row["accepted"] and row["action"] == "ROLLBACK"
                             for row in trace), result[3])
        self.assertTrue(all(set(row) == set(trace[0]) for row in trace))

    def test_trace_appends_independent_records_and_records_failed_events(self):
        events = [baseline(), event(1, "STAGE"), event(2, "VERIFY"),
                  event(3, "VERIFY", success=False), event(4, "COMMIT")]
        sentinel = {"existing": True}
        trace = [sentinel]
        result = reconcile_states(events, trace=trace)
        self.assertIs(trace[0], sentinel)
        self.assertEqual(len(trace), len(events) + 1)
        self.assertEqual(len({id(row) for row in trace}), len(trace))
        self.assertEqual(trace[4]["reason"], "verify_failed")
        self.assertFalse(trace[4]["accepted"])
        self.assertFalse(trace[4]["success"])
        self.assertFalse(trace[5]["accepted"])
        self.assertEqual(trace[5]["reason"], "commit_unverified")
        self.assertEqual(result[2], 0)
        events[1]["digest"] = "input changed"
        self.assertEqual(trace[2]["digest"], "new")
        trace[2]["digest"] = "trace changed"
        self.assertEqual(trace[3]["digest"], "new")
        self.assertEqual(result[0][0]["active_digest"], "old")

    def test_trace_missing_baseline_and_empty_input(self):
        trace = []
        reconcile_states([event(1, "COMMIT")], trace=trace)
        self.assertIsNone(trace[0]["active_digest_before"])
        self.assertIsNone(trace[0]["active_digest_after"])
        self.assertFalse(trace[0]["accepted"])
        snapshot = list(trace)
        self.assertEqual(reconcile_states([], trace=trace), ([], [], 0, 0))
        self.assertEqual(trace, snapshot)


if __name__ == "__main__":
    unittest.main()
