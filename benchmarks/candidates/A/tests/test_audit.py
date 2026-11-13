"""Audit evidence must explain R3 execution without changing its output."""

import copy
import json
import random
import unittest
from pathlib import Path

from reconcile import reconcile, reconcile_with_audit
from report import build_audit


def event(event_id, action, sequence, *, time=None, success=True, **overrides):
    row = {
        "schema": 1, "event_id": event_id, "board": "board", "epoch": 0,
        "sequence": sequence, "action": action, "tx": "tx", "slot": 1,
        "digest": "new", "success": success,
        "time": sequence if time is None else time,
    }
    row.update(overrides)
    return row


def baseline(**overrides):
    return event("baseline", "BASELINE", 0, tx=None, slot=0, digest="old", **overrides)


class AuditContract(unittest.TestCase):
    def test_transport_and_action_counts_distinguish_replays_conflicts_and_acceptance(self):
        stage = event("stage", "STAGE", 1)
        verify = event("verify", "VERIFY", 2)
        rows = [baseline(), stage, dict(stage), dict(stage), verify,
                dict(verify, digest="conflict"), event("commit", "COMMIT", 3)]
        report, audit = reconcile_with_audit(rows)
        self.assertEqual(report, reconcile(rows))
        self.assertEqual(set(report), {"boards", "incidents", "totals"})
        self.assertEqual(set(audit), {
            "contract", "summary", "transport", "transitions", "per_action", "reason_catalog",
        })
        self.assertEqual(audit["contract"], "R3")
        self.assertEqual(audit["summary"], {
            **report["totals"], "input_rows": 7, "retained_events": 3, "conflicted_rows": 2,
        })
        self.assertEqual(audit["summary"]["duplicate_replays"], 2)
        self.assertEqual(audit["summary"]["conflicted_ids"], 1)
        transport = {row["event_id"]: row for row in audit["transport"]}
        self.assertEqual(transport["stage"]["transport_rows"], 3)
        self.assertEqual(transport["stage"]["duplicate_replays"], 2)
        self.assertEqual(transport["verify"]["status"], "conflict")
        self.assertEqual(transport["verify"]["duplicate_replays"], 0)
        self.assertEqual(audit["per_action"]["VERIFY"]["attempted"], 0)
        self.assertEqual(audit["per_action"]["STAGE"]["attempted"], 1)
        self.assertEqual(audit["per_action"]["COMMIT"], {
            "attempted": 1, "reported_success": 1, "accepted": 0, "rejected": 1, "ignored": 0,
        })
        self.assertEqual(audit["summary"]["rejected_events"], 2)
        self.assertEqual(sum(row["rejected"] for row in audit["per_action"].values()), 1)

    def test_trace_follows_sequence_execution_despite_clock_skew(self):
        report, audit = reconcile_with_audit([
            event("commit", "COMMIT", 30, time=1), baseline(time=99),
            event("verify", "VERIFY", 20, time=2), event("stage", "STAGE", 10, time=3),
        ])
        trace = audit["transitions"]
        self.assertEqual([row["event_id"] for row in trace], ["baseline", "stage", "verify", "commit"])
        self.assertEqual(trace[0]["active_before"], {"slot": None, "digest": None})
        self.assertEqual(trace[0]["active_after"], {"slot": "A", "digest": "old"})
        self.assertTrue(trace[0]["verified_image_added"])
        self.assertEqual(trace[1]["pending_before"], [])
        self.assertEqual(trace[1]["pending_after"], [
            {"tx": "tx", "slot": "B", "digest": "new", "verified": False},
        ])
        self.assertTrue(trace[2]["pending_after"][0]["verified"])
        self.assertTrue(trace[2]["verified_image_added"])
        self.assertEqual(trace[3]["active_after"], {"slot": "B", "digest": "new"})
        self.assertEqual(trace[3]["pending_after"], [])
        self.assertEqual(audit["per_action"]["COMMIT"]["accepted"], report["totals"]["applied_commits"])

    def test_trace_explains_failed_verify_revocation_and_history_retention(self):
        _, audit = reconcile_with_audit([
            baseline(), event("stage", "STAGE", 1), event("verify", "VERIFY", 2),
            event("failed-verify", "VERIFY", 3, success=False),
            event("early-commit", "COMMIT", 4),
            event("reverify", "VERIFY", 5),
            event("mismatch", "VERIFY", 6, digest="different"),
            event("commit", "COMMIT", 7),
            event("rollback", "ROLLBACK", 8, epoch=1),
        ])
        trace = {row["event_id"]: row for row in audit["transitions"]}
        self.assertEqual(trace["failed-verify"]["reason"], "verify_failed")
        self.assertFalse(trace["failed-verify"]["reported_success"])
        self.assertTrue(trace["failed-verify"]["pending_before"][0]["verified"])
        self.assertFalse(trace["failed-verify"]["pending_after"][0]["verified"])
        self.assertEqual(trace["early-commit"]["reason"], "commit_unverified")
        self.assertTrue(trace["reverify"]["pending_after"][0]["verified"])
        self.assertEqual(trace["mismatch"]["reason"], "verify_mismatch")
        self.assertTrue(trace["mismatch"]["reported_success"])
        self.assertFalse(trace["mismatch"]["pending_after"][0]["verified"])
        self.assertEqual(trace["commit"]["reason"], "commit_unverified")
        self.assertEqual(trace["rollback"]["outcome"], "accepted")
        self.assertFalse(trace["rollback"]["verified_image_added"])
        self.assertTrue(trace["rollback"]["epoch_advanced"])
        self.assertEqual(trace["rollback"]["pending_after_epoch"], [])
        self.assertEqual(trace["rollback"]["pending_after"], [])

    def test_epoch_clear_is_distinct_from_failed_first_event_effects(self):
        report, audit = reconcile_with_audit([
            baseline(), event("stage-a", "STAGE", 1, tx="a"),
            event("verify-a", "VERIFY", 2, tx="a"),
            event("stage-b", "STAGE", 3, tx="b"),
            event("failed-reset", "RESET", 0, epoch=1, success=False),
            event("commit-a", "COMMIT", 1, epoch=1, tx="a"),
            event("stage-new", "STAGE", 2, epoch=1, tx="new"),
            event("wrong-slot", "ROLLBACK", 0, epoch=2, slot=0),
            event("rollback", "ROLLBACK", 1, epoch=2),
        ])
        trace = {row["event_id"]: row for row in audit["transitions"]}
        failed = trace["failed-reset"]
        self.assertEqual(failed["epoch_before"], 0)
        self.assertEqual(failed["epoch"], 1)
        self.assertTrue(failed["epoch_advanced"])
        self.assertEqual([row["tx"] for row in failed["pending_before"]], ["a", "b"])
        self.assertEqual(failed["pending_after_epoch"], [])
        self.assertEqual(failed["pending_after"], [])
        self.assertEqual(failed["active_before"], failed["active_after"])
        self.assertEqual(failed["reason"], "reset_failed")
        self.assertEqual(trace["commit-a"]["reason"], "commit_without_stage")
        self.assertFalse(trace["stage-new"]["epoch_advanced"])
        self.assertEqual(trace["stage-new"]["epoch_before"], 1)
        wrong_slot = trace["wrong-slot"]
        self.assertTrue(wrong_slot["epoch_advanced"])
        self.assertEqual(wrong_slot["pending_before"][0]["tx"], "new")
        self.assertEqual(wrong_slot["pending_after_epoch"], [])
        self.assertEqual(wrong_slot["pending_after"], [])
        self.assertEqual(wrong_slot["reason"], "rollback_unverified")
        self.assertEqual(trace["rollback"]["outcome"], "accepted")
        self.assertEqual(report["totals"]["accepted_rollbacks"], 1)

    def test_new_epoch_failed_verify_reports_missing_stage_after_clearing(self):
        _, audit = reconcile_with_audit([
            baseline(), event("stage", "STAGE", 1), event("verify", "VERIFY", 2),
            event("failed-verify", "VERIFY", 0, epoch=1, success=False),
        ])
        row = audit["transitions"][-1]
        self.assertTrue(row["pending_before"][0]["verified"])
        self.assertTrue(row["epoch_advanced"])
        self.assertEqual(row["pending_after_epoch"], [])
        self.assertEqual(row["pending_after"], [])
        self.assertEqual(row["reason"], "verify_without_stage")

    def test_audit_is_deterministic_does_not_mutate_inputs_and_excludes_runtime_fields(self):
        rows = [baseline(), event("stage", "STAGE", 1), event("verify", "VERIFY", 2),
                event("commit", "COMMIT", 3), event("commit", "COMMIT", 3, time=50)]
        before = copy.deepcopy(rows)
        expected = reconcile_with_audit(rows)
        self.assertEqual(rows, before)
        random.Random(17).shuffle(rows)
        self.assertEqual(reconcile_with_audit(iter(rows)), expected)
        for index, row in enumerate(rows):
            row["time"] = -index * 100000
        self.assertEqual(reconcile_with_audit(rows), expected)

        def assert_no_runtime_keys(value):
            if isinstance(value, dict):
                self.assertFalse({"time", "timestamp", "path", "input_path", "output_path"} & value.keys())
                for child in value.values():
                    assert_no_runtime_keys(child)
            elif isinstance(value, list):
                for child in value:
                    assert_no_runtime_keys(child)

        assert_no_runtime_keys(expected[1])

    def test_projection_copies_nested_trace_and_discards_internal_fields(self):
        report, audit = reconcile_with_audit([
            baseline(), event("stage", "STAGE", 1), event("verify", "VERIFY", 2),
        ])
        transport = copy.deepcopy(audit["transport"])
        trace = copy.deepcopy(audit["transitions"])
        transport[0]["timestamp"] = 10
        trace[0]["timestamp"] = 10
        trace[0]["active_after"]["internal"] = True
        trace[1]["pending_after"][0]["internal"] = True
        trace[2]["pending_after_epoch"][0]["internal"] = True
        projected = build_audit(reversed(transport), trace, report)
        self.assertEqual(projected, audit)
        trace[0]["active_after"]["digest"] = "changed"
        trace[1]["pending_after"][0]["verified"] = True
        trace[2]["pending_after_epoch"][0]["digest"] = "changed"
        self.assertEqual(projected, audit)

    def test_reason_catalog_covers_prescribed_incidents(self):
        _, audit = reconcile_with_audit([])
        self.assertEqual(set(audit["reason_catalog"]), {
            "duplicate_conflict", "reset_failed", "stage_failed", "verify_without_stage",
            "verify_failed", "verify_mismatch", "commit_failed", "commit_without_stage",
            "commit_mismatch", "commit_unverified", "rollback_failed", "rollback_unverified",
        })
        self.assertEqual(audit["summary"]["input_rows"], 0)
        self.assertEqual(audit["transitions"], [])
        self.assertEqual(audit["transport"], [])
        for counts in audit["per_action"].values():
            self.assertEqual(set(counts.values()), {0})


class OperationsNotes(unittest.TestCase):
    def read_notes(self):
        path = Path(__file__).resolve().parents[1] / "audit" / "operations-notes.json"
        return json.loads(path.read_text(encoding="utf-8"))["notes"]

    def test_known_notes_preserve_exact_values_mapping_and_unique_identifiers(self):
        expected = [
            ("change_ticket", "revised-CHG-1106-001"),
            ("approved_rollback_digest", "a2cf9430662e6ca5754d20895242bd2d53075964c1fa40b527700fe2541dd02e"),
            ("settle_window_ms", "17524"),
            ("forbidden_operator_action", "revised-reuse-old-epoch-verification"),
            ("escalation_scope", "revised-deployment-batch"),
            ("accepted_boot_status", "revised-ready-epoch-13"),
            ("audit_correlation_nonce", "revised-118a27ca65904294cb9e"),
            ("evidence_retention_days", "151"),
            ("change_ticket", "CHG-1106-009"),
            ("approved_rollback_digest", "15badb0ea0073ed85e764b678efaf57c144c3874e4ade5da228aee360d52bcc8"),
            ("settle_window_ms", "18507"),
            ("forbidden_operator_action", "reuse-old-epoch-verification"),
            ("escalation_scope", "rack"),
            ("accepted_boot_status", "ready-epoch-21"),
            ("audit_correlation_nonce", "726907cf0954db14e4ea"),
            ("evidence_retention_days", "46"),
            ("change_ticket", "CHG-1106-017"),
            ("approved_rollback_digest", "23139fbf491de2f1e9ca759d4c114e07865ec257b89a0d099364781c8ff43277"),
            ("settle_window_ms", "19603"),
            ("forbidden_operator_action", "reuse-old-epoch-verification"),
            ("escalation_scope", "single-board"),
            ("accepted_boot_status", "ready-epoch-29"),
            ("audit_correlation_nonce", "4f69c385ab1772576a87"),
            ("evidence_retention_days", "54"),
            ("change_ticket", "CHG-1106-025"),
            ("approved_rollback_digest", "fb5d8083ced8cce6722d586553d79b311687a5d17cde952304a1abca4bfc713f"),
            ("settle_window_ms", "20699"),
            ("forbidden_operator_action", "reuse-old-epoch-verification"),
            ("escalation_scope", "deployment-batch"),
            ("accepted_boot_status", "ready-epoch-37"),
            ("audit_correlation_nonce", "c3a8bceb370890311a34"),
            ("evidence_retention_days", "62"),
            ("change_ticket", "CHG-1106-033"),
            ("approved_rollback_digest", "0de61026d961f4719491da66d8c746c0698dcabb20d33379b66284e370b17a79"),
            ("settle_window_ms", "21795"),
            ("forbidden_operator_action", "reuse-old-epoch-verification"),
            ("escalation_scope", "rack"),
            ("accepted_boot_status", "ready-epoch-45"),
            ("audit_correlation_nonce", "f88754d0b542d90447a5"),
            ("evidence_retention_days", "70"),
            ("change_ticket", "CHG-1106-041"),
            ("approved_rollback_digest", "12a71789f81882694a6c56866042a33ed147438ec27adcfde8583a6afcabda09"),
            ("settle_window_ms", "22891"),
            ("forbidden_operator_action", "reuse-old-epoch-verification"),
            ("escalation_scope", "single-board"),
            ("accepted_boot_status", "ready-epoch-53"),
            ("audit_correlation_nonce", "8e22fa7c84b9d3a89b8d"),
            ("evidence_retention_days", "78"),
        ]
        notes = self.read_notes()
        self.assertGreaterEqual(len(notes), len(expected))
        by_id = {note["note_id"]: note for note in notes}
        self.assertEqual(len(by_id), len(notes))
        self.assertEqual(len({note["operation_id"] for note in notes}), len(notes))
        for index, (field, value) in enumerate(expected, 1):
            case_number = index + 48 * ((index - 1) // 16)
            self.assertEqual(by_id["F{:02d}".format(index)], {
                "note_id": "F{:02d}".format(index), "operation_id": "OPS-{:03d}".format(index),
                "case_id": "INC-{:05d}".format(case_number), "field": field, "value": value,
            })

    def test_correction_ledger_marks_old_values_superseded_and_matches_current_notes(self):
        path = Path(__file__).resolve().parents[1] / "audit" / "operations-corrections.json"
        corrections = json.loads(path.read_text(encoding="utf-8"))["corrections"]
        invalidated = [
            "CHG-1106-001",
            "db7b802fead1fd7c5ec12451e8329b5ac82509f404b6d2cd5bc3a9b139e5f48e",
            "17411", "reuse-old-epoch-verification", "deployment-batch",
            "ready-epoch-13", "118a27ca65904294cb9e", "38",
        ]
        by_key = {(row["note_id"], row["invalidated_value"]): row for row in corrections}
        self.assertEqual(len(by_key), len(corrections))
        self.assertGreaterEqual(len(corrections), len(invalidated))
        current = {note["note_id"]: note for note in self.read_notes()}
        for ordinal, old_value in enumerate(invalidated, 1):
            note_id = "F{:02d}".format(ordinal)
            note = current[note_id]
            self.assertEqual(by_key[(note_id, old_value)], {
                **{key: note[key] for key in ("note_id", "operation_id", "case_id", "field")},
                "invalidated_value": old_value, "current_value": note["value"],
                "status": "superseded",
            })
            self.assertNotEqual(note["value"], old_value)

    def test_approved_digest_note_does_not_authorize_rollback(self):
        approved = self.read_notes()[1]["value"]
        report, audit = reconcile_with_audit([
            baseline(board="board-00002"),
            event("rollback", "ROLLBACK", 1, board="board-00002", digest=approved),
        ])
        self.assertEqual(report["totals"]["accepted_rollbacks"], 0)
        self.assertEqual(report["incidents"][0]["reason"], "rollback_unverified")
        self.assertEqual(audit["transitions"][-1]["outcome"], "rejected")


if __name__ == "__main__":
    unittest.main()
