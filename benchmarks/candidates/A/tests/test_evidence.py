"""Behavioral regressions from all evidence batches under revision R3."""

import json
from pathlib import Path
import random
import unittest

from reconcile import reconcile, reconcile_with_audit


class EvidenceContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path(__file__).resolve().parents[1] / "data" / "visible.jsonl"
        cls.rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]

    def board_rows(self, number):
        board = f"board-{number:05d}"
        return [row for row in self.rows if row.get("board", row.get("device")) == board]

    def test_failed_verify_revokes_prior_verification_in_all_batches(self):
        for number in (1, 73, 133):
            with self.subTest(case=number):
                report, audit = reconcile_with_audit(self.board_rows(number))
                self.assertEqual(report["totals"]["applied_commits"], 0)
                self.assertEqual(report["boards"][0]["active_slot"], "A")
                self.assertEqual([(row["sequence"], row["reason"]) for row in report["incidents"]], [
                    (21, "verify_failed"), (28, "commit_unverified"),
                    (42, "verify_failed"), (49, "commit_unverified"),
                ])
                failed = next(row for row in audit["transitions"] if row["sequence"] == 21)
                self.assertTrue(failed["pending_before"][0]["verified"])
                self.assertFalse(failed["pending_after"][0]["verified"])

    def test_epoch_and_reset_each_prevent_later_commit_in_all_batches(self):
        for number in (2, 74, 134):
            with self.subTest(case=number):
                report, audit = reconcile_with_audit(self.board_rows(number))
                self.assertEqual(report["totals"]["applied_commits"], 0)
                self.assertEqual([(row["sequence"], row["reason"]) for row in report["incidents"]], [
                    (21, "commit_without_stage"), (49, "commit_without_stage"),
                ])
                commit = next(row for row in audit["transitions"] if row["sequence"] == 21)
                self.assertEqual(commit["epoch"], 1)
                self.assertTrue(commit["epoch_advanced"])
                self.assertTrue(commit["pending_before"][0]["verified"])
                self.assertEqual(commit["pending_after_epoch"], [])
                self.assertEqual(commit["outcome"], "rejected")
                self.assertEqual(report["boards"][0]["active_slot"], "A")
                self.assertEqual(report["boards"][0]["active_digest"], commit["active_before"]["digest"])

    def test_conflicting_stage_never_authorizes_a_commit(self):
        report = reconcile(self.board_rows(65))
        self.assertEqual(report["totals"]["applied_commits"], 0)
        self.assertEqual(report["totals"]["conflicted_ids"], 1)
        self.assertEqual(report["totals"]["duplicate_replays"], 2)
        self.assertEqual([(row["sequence"], row["reason"]) for row in report["incidents"]], [
            (7, "duplicate_conflict"), (14, "verify_without_stage"),
            (21, "reset_failed"), (28, "commit_without_stage"),
            (42, "verify_failed"), (49, "commit_unverified"),
        ])

    def test_mismatch_revocation_and_reset_are_ordered_by_sequence(self):
        report = reconcile(self.board_rows(66))
        self.assertEqual(report["totals"]["applied_commits"], 0)
        self.assertEqual([(row["sequence"], row["reason"]) for row in report["incidents"]], [
            (21, "verify_mismatch"), (28, "commit_unverified"),
            (56, "commit_without_stage"),
        ])

    def test_consumed_commit_does_not_reapply_without_a_new_stage(self):
        report = reconcile(self.board_rows(72))
        self.assertEqual(report["totals"]["applied_commits"], 2)
        self.assertEqual([(row["sequence"], row["reason"]) for row in report["incidents"]], [
            (28, "commit_without_stage"),
        ])

    def test_rollback_digest_alone_does_not_authorize_another_slot_in_all_batches(self):
        for number in (8, 68, 152):
            with self.subTest(case=number):
                report, audit = reconcile_with_audit(self.board_rows(number))
                self.assertEqual(report["totals"]["applied_commits"], 2)
                self.assertEqual(report["totals"]["accepted_rollbacks"], 0)
                self.assertEqual([(row["sequence"], row["reason"]) for row in report["incidents"]], [
                    (28, "rollback_unverified"),
                ])
                baseline = audit["transitions"][0]
                rollback = next(row for row in audit["transitions"] if row["action"] == "ROLLBACK")
                self.assertEqual(rollback["digest"], baseline["digest"])
                self.assertNotEqual(rollback["slot"], baseline["slot"])
                self.assertEqual(rollback["active_before"], rollback["active_after"])

    def test_batch_three_conflict_and_reset_prevent_attempted_commits(self):
        report = reconcile(self.board_rows(130))
        self.assertEqual(report["totals"]["applied_commits"], 0)
        self.assertEqual(report["totals"]["conflicted_ids"], 1)
        self.assertEqual(report["totals"]["duplicate_replays"], 2)
        self.assertEqual([(row["sequence"], row["reason"]) for row in report["incidents"]], [
            (7, "duplicate_conflict"), (14, "verify_without_stage"),
            (21, "stage_failed"), (28, "commit_without_stage"),
            (56, "commit_without_stage"),
        ])

    def test_full_corpus_epoch_clear_preserves_active_image_and_trace_continuity(self):
        _, audit = reconcile_with_audit(self.rows)
        previous = {}
        for row in audit["transitions"]:
            prior = previous.get(row["board"])
            if prior is not None:
                self.assertEqual(row["pending_before"], prior["pending_after"])
                self.assertEqual(row["active_before"], prior["active_after"])
                self.assertEqual(row["epoch_before"], prior["epoch"])
                self.assertEqual(row["epoch_advanced"], row["epoch"] > prior["epoch"])
            if row["epoch_advanced"]:
                self.assertEqual(row["pending_after_epoch"], [])
            else:
                self.assertEqual(row["pending_after_epoch"], row["pending_before"])
            previous[row["board"]] = row

    def test_full_corpus_reports_ignore_clock_values_and_transport_order(self):
        expected = reconcile_with_audit(self.rows)
        changed = []
        for index, row in enumerate(self.rows):
            changed.append({**row, "time": 10**15 - index, "timestamp": -10**15 + index})
        random.Random(2026).shuffle(changed)
        self.assertEqual(reconcile_with_audit(iter(changed)), expected)
        locations = [tuple(row[key] for key in ("board", "epoch", "sequence", "event_id"))
                     for row in expected[1]["transitions"]]
        self.assertEqual(locations, sorted(locations))


if __name__ == "__main__":
    unittest.main()
