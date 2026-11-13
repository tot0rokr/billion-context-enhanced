import copy
import json
import random
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from reconcile import reconcile
from report import build_audit_report


ROOT = Path(__file__).resolve().parents[1]


def event(event_id, board, epoch, sequence, action, timestamp, *,
          tx=None, slot=0, digest="old", success=True):
    return {
        "schema": 1, "event_id": event_id, "board": board,
        "epoch": epoch, "sequence": sequence, "action": action,
        "time": timestamp, "tx": tx, "slot": slot,
        "digest": digest, "success": success,
    }


class ReconciliationIntegration(unittest.TestCase):
    def test_cli_handles_generated_unseen_events_under_r3(self):
        for seed in (317, 809, 2027):
            with self.subTest(seed=seed):
                rng = random.Random(seed)

                def identifier():
                    return f"{rng.getrandbits(256):064x}"

                board, other_board = sorted([identifier(), identifier()])
                tx, other_tx = identifier(), identifier()
                original, candidate, other_image = identifier(), identifier(), identifier()
                epoch = rng.randrange(3, 30)
                next_epoch = epoch + rng.randrange(2, 10)
                initial_slot = rng.randrange(2)
                target_slot = 1 - initial_slot
                # Expected reasons describe the contract, independently of the
                # reconciler. Random identities never occur in the visible corpus.
                steps = [
                    (epoch, "BASELINE", None, initial_slot, original, True, None),
                    (epoch, "STAGE", tx, target_slot, candidate, True, None),
                    (epoch, "VERIFY", tx, target_slot, candidate, True, None),
                    (epoch, "VERIFY", tx, target_slot, candidate, False, "verify_failed"),
                    (epoch, "COMMIT", tx, target_slot, candidate, True, "commit_unverified"),
                    (epoch, "VERIFY", tx, target_slot, candidate, True, None),
                    (epoch, "COMMIT", tx, target_slot, candidate, True, None),
                    (epoch, "STAGE", other_tx, initial_slot, original, True, None),
                    (epoch, "VERIFY", other_tx, initial_slot, original, True, None),
                    (next_epoch, "RESET", None, None, None, False, "reset_failed"),
                    (next_epoch, "COMMIT", other_tx, initial_slot, original,
                     True, "commit_without_stage"),
                    (next_epoch, "ROLLBACK", None, target_slot, original,
                     True, "rollback_unverified"),
                    (next_epoch, "ROLLBACK", None, target_slot, candidate, True, None),
                    (next_epoch, "STAGE", tx, target_slot, candidate, True, None),
                    (next_epoch, "COMMIT", tx, target_slot, candidate,
                     True, "commit_unverified"),
                    (next_epoch, "VERIFY", tx, target_slot, candidate, True, None),
                    (next_epoch, "COMMIT", tx, target_slot, candidate, True, None),
                    (next_epoch, "ROLLBACK", None, initial_slot, original, True, None),
                ]
                rows, incidents = [], []
                for sequence, (boot, action, transaction, slot, digest, success, reason) in enumerate(steps):
                    row = event(identifier(), board, boot, sequence, action,
                                1000 - sequence, tx=transaction, slot=slot,
                                digest=digest, success=success)
                    rows.append(row)
                    if reason:
                        incidents.append({key: row[key] for key in
                                          ("board", "epoch", "sequence", "event_id")} |
                                         {"reason": reason})
                rows.append(event(identifier(), other_board, epoch, 0, "BASELINE", 50,
                                  slot=initial_slot, digest=other_image))
                row = event(identifier(), other_board, next_epoch, 1, "ROLLBACK", 0,
                            slot=target_slot, digest=candidate)
                rows.append(row)
                incidents.append({key: row[key] for key in
                                  ("board", "epoch", "sequence", "event_id")} |
                                 {"reason": "rollback_unverified"})
                replay = dict(rows[6], time=-999)
                rows.append(replay)

                def schema2(row):
                    return {
                        "schema": 2, "id": row["event_id"], "device": row["board"],
                        "boot": row["epoch"], "seq": row["sequence"],
                        "kind": row["action"].lower(), "transaction": row["tx"],
                        "slot": {0: "A", 1: "B", None: None}[row["slot"]],
                        "sha256": row["digest"], "ok": row["success"],
                        "timestamp": row["time"],
                    }

                rows = [schema2(row) if index % 2 == 0 else row
                        for index, row in enumerate(rows)]
                # Ensure the replay also uses the opposite schema spelling.
                rows[-1] = replay
                rng.shuffle(rows)
                expected = {
                    "boards": [
                        {"board": name, "epoch": next_epoch,
                         "active_slot": "AB"[initial_slot], "active_digest": digest}
                        for name, digest in ((board, original), (other_board, other_image))
                    ],
                    "incidents": incidents,
                    "totals": {"board_count": 2, "applied_commits": 2,
                               "accepted_rollbacks": 2, "duplicate_replays": 1,
                               "conflicted_ids": 0, "rejected_events": 7},
                }
                with tempfile.TemporaryDirectory(dir=ROOT) as directory:
                    source = Path(directory) / "unseen.jsonl"
                    output = Path(directory) / "result.json"
                    source.write_text("\n".join(map(json.dumps, rows)) + "\n",
                                      encoding="utf-8")
                    subprocess.run(
                        [sys.executable, str(ROOT / "reconcile.py"),
                         "--input", str(source), "--output", str(output)],
                        check=True, capture_output=True, text=True,
                    )
                    self.assertEqual(json.loads(output.read_text(encoding="utf-8")), expected)

    def test_cli_audit_distinguishes_reported_success_from_acceptance(self):
        rows = [
            event("base", "a", 0, 0, "BASELINE", 100),
            event("stage", "a", 0, 1, "STAGE", 10, tx="t", slot=1, digest="new"),
            event("verify", "a", 0, 2, "VERIFY", 20, tx="t", slot=1, digest="new"),
            event("early-commit", "a", 0, 3, "COMMIT", 5,
                  tx="t", slot=1, digest="new"),
            event("commit", "a", 0, 4, "COMMIT", 30,
                  tx="t", slot=1, digest="new"),
            event("commit", "a", 0, 4, "COMMIT", 999,
                  tx="t", slot=1, digest="new"),
            event("conflict", "a", 0, 5, "STAGE", 35, tx="other", digest="x"),
            event("conflict", "a", 0, 5, "STAGE", 35, tx="other", digest="y"),
            event("same-image-rollback", "a", 0, 6, "ROLLBACK", 40,
                  slot=1, digest="new"),
        ]
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            source = Path(directory) / "events.jsonl"
            target = Path(directory) / "result.json"
            audit_target = Path(directory) / "audit.json"
            source.write_text("\n".join(map(json.dumps, reversed(rows))), encoding="utf-8")
            subprocess.run(
                [sys.executable, str(ROOT / "reconcile.py"),
                 "--input", str(source), "--output", str(target),
                 "--audit-output", str(audit_target)],
                check=True, capture_output=True, text=True,
            )
            result = json.loads(target.read_text(encoding="utf-8"))
            audit = json.loads(audit_target.read_text(encoding="utf-8"))
        self.assertEqual(result, reconcile(rows))
        self.assertEqual(set(result), {"boards", "incidents", "totals"})
        self.assertEqual(audit["contract_revision"], "R3")
        self.assertEqual(audit["operations"], {
            "COMMIT": {"attempted": 2, "reported_success": 2, "accepted": 1, "rejected": 1},
            "ROLLBACK": {"attempted": 1, "reported_success": 1, "accepted": 1, "rejected": 0},
        })
        self.assertEqual([row["event_id"] for row in audit["events"]],
                         ["base", "stage", "verify", "early-commit", "commit",
                          "same-image-rollback"])
        self.assertTrue(audit["events"][3]["accepted"])
        self.assertEqual(audit["events"][4]["reason"], "commit_without_stage")
        self.assertFalse(audit["events"][4]["accepted"])
        self.assertEqual(len(audit["conflicts"]), 1)
        self.assertEqual(set(audit["reason_explanations"]),
                         {row["reason"] for row in result["incidents"]})
        for row in audit["events"]:
            self.assertNotIn("timestamp", row)
            self.assertNotIn("time", row)

    def test_corpus_audit_matches_report_and_is_order_independent(self):
        rows = [json.loads(line) for line in
                (ROOT / "data" / "visible.jsonl").read_text().splitlines() if line.strip()]
        trace = []
        result = reconcile(rows, trace=trace)
        audit = build_audit_report(result, trace)
        locations = [(row["board"], row["epoch"], row["sequence"], row["event_id"])
                     for row in trace]
        self.assertEqual(locations, sorted(locations))
        trace_incidents = [
            {field: row[field] for field in ("board", "epoch", "sequence", "event_id", "reason")}
            for row in trace if not row["accepted"]
        ]
        self.assertCountEqual(trace_incidents + audit["conflicts"], result["incidents"])
        self.assertEqual(audit["operations"]["COMMIT"]["accepted"],
                         result["totals"]["applied_commits"])
        self.assertEqual(audit["operations"]["ROLLBACK"]["accepted"],
                         result["totals"]["accepted_rollbacks"])
        active = {}
        for row in trace:
            board = row["board"]
            self.assertEqual((row["active_slot_before"], row["active_digest_before"]),
                             active.get(board, (None, None)))
            active[board] = (row["active_slot_after"], row["active_digest_after"])
            if row["accepted"]:
                self.assertTrue(row["success"])
                self.assertIsNone(row["reason"])
        for board in result["boards"]:
            self.assertEqual(active[board["board"]],
                             (board["active_slot"], board["active_digest"]))
        for seed in (17, 20261106):
            random.Random(seed).shuffle(rows)
            shuffled_trace = []
            shuffled_report = reconcile(rows, trace=shuffled_trace)
            self.assertEqual(shuffled_report, result)
            self.assertEqual(build_audit_report(shuffled_report, shuffled_trace), audit)

    def test_all_batches_ignore_clock_rewrites_in_report_and_trace(self):
        rows = [json.loads(line) for line in
                (ROOT / "data" / "visible.jsonl").read_text().splitlines() if line.strip()]
        trace = []
        result = reconcile(rows, trace=trace)
        audit = build_audit_report(result, trace)
        clocks = random.Random(20261106)
        for row in rows:
            field = "time" if row["schema"] == 1 else "timestamp"
            row[field] = clocks.randrange(-10**12, 10**12)
        clocks.shuffle(rows)
        rewritten_trace = []
        rewritten_result = reconcile(rows, trace=rewritten_trace)
        self.assertEqual(rewritten_result, result)
        self.assertEqual(build_audit_report(rewritten_result, rewritten_trace), audit)

        # R2 failed-VERIFY invalidation remains in force under R3 for all batches.
        outcomes = {row["event_id"]: row for row in rewritten_trace}
        for board in ("board-00001", "board-00013", "board-00073", "board-00133"):
            self.assertEqual(outcomes[board + "-e003"]["reason"], "verify_failed")
            self.assertEqual(outcomes[board + "-e004"]["reason"], "commit_unverified")
        # R3 clears old-epoch pending state in earlier and current batches.
        for board in ("board-00002", "board-00074", "board-00134"):
            self.assertFalse(outcomes[board + "-e003"]["accepted"])
            self.assertEqual(outcomes[board + "-e003"]["reason"], "commit_without_stage")

    def test_all_batches_enforce_epoch_boundaries_and_exact_rollback_pairs(self):
        rows = [json.loads(line) for line in
                (ROOT / "data" / "visible.jsonl").read_text().splitlines() if line.strip()]
        trace = []
        reconcile(rows, trace=trace)
        outcomes = {row["event_id"]: row for row in trace}
        for number in (2, 74, 134):
            board = f"board-{number:05}"
            baseline = outcomes[board + "-e000"]
            verification = outcomes[board + "-e002"]
            commit = outcomes[board + "-e003"]
            with self.subTest(board=board):
                self.assertTrue(verification["accepted"])
                self.assertLess(verification["epoch"], commit["epoch"])
                self.assertTrue(commit["success"])
                self.assertEqual(commit["reason"], "commit_without_stage")
                self.assertEqual(commit["active_digest_after"], baseline["digest"])
        for number in (8, 68, 152):
            board = f"board-{number:05}"
            baseline = outcomes[board + "-e000"]
            rollback = outcomes[board + "-e004"]
            with self.subTest(board=board):
                self.assertEqual(rollback["digest"], baseline["digest"])
                self.assertNotEqual(rollback["slot"], baseline["slot"])
                self.assertTrue(rollback["success"])
                self.assertFalse(rollback["accepted"])
                self.assertEqual(rollback["reason"], "rollback_unverified")
                self.assertEqual(rollback["active_digest_before"], rollback["active_digest_after"])

    def test_cli_rejects_overlapping_output_files_before_writing(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            source = Path(directory) / "events.jsonl"
            target = Path(directory) / "report.json"
            source.write_text("", encoding="utf-8")
            target.write_text("existing report", encoding="utf-8")
            run = subprocess.run(
                [sys.executable, str(ROOT / "reconcile.py"),
                 "--input", str(source), "--output", str(target),
                 "--audit-output", str(target)],
                capture_output=True, text=True,
            )
            self.assertEqual(run.returncode, 2)
            self.assertIn("must name different files", run.stderr)
            self.assertEqual(target.read_text(), "existing report")

    def test_mixed_schema_conflicts_and_r3_transitions_are_order_independent(self):
        rows = [
            event("a-base", "a", 0, 0, "BASELINE", 100),
            event("b-base", "b", 0, 0, "BASELINE", 100, digest="b-old"),
            event("stage", "a", 0, 10, "STAGE", 1, tx="t", slot=1, digest="new"),
            event("verify", "a", 0, 20, "VERIFY", 2, tx="t", slot=1, digest="new"),
            event("failed-verify", "a", 0, 30, "VERIFY", 3,
                  tx="t", slot=1, digest="new", success=False),
            event("commit", "a", 1, 40, "COMMIT", 0, tx="t", slot=1, digest="new"),
            {"schema": 2, "id": "commit", "device": "a", "boot": 1,
             "seq": 40, "kind": "commit", "timestamp": 1000,
             "transaction": "t", "slot": "B", "sha256": "new", "ok": True},
            event("rollback", "a", 1, 41, "ROLLBACK", 1),
            event("repeat", "a", 1, 42, "COMMIT", 2, tx="t", slot=1, digest="new"),
            event("conflict", "a", 1, 43, "STAGE", 3, tx="bad"),
            event("conflict", "b", 0, 1, "STAGE", 0, tx="bad"),
            event("b-commit", "b", 0, 2, "COMMIT", 1, tx="bad"),
        ]
        original = copy.deepcopy(rows)
        expected = {
            "boards": [
                {"board": "a", "epoch": 1, "active_slot": "A", "active_digest": "old"},
                {"board": "b", "epoch": 0, "active_slot": "A", "active_digest": "b-old"},
            ],
            "incidents": [
                {"board": "a", "epoch": 0, "sequence": 30,
                 "event_id": "failed-verify", "reason": "verify_failed"},
                {"board": "a", "epoch": 1, "sequence": 40,
                 "event_id": "commit", "reason": "commit_without_stage"},
                {"board": "a", "epoch": 1, "sequence": 42,
                 "event_id": "repeat", "reason": "commit_without_stage"},
                {"board": "a", "epoch": 1, "sequence": 43,
                 "event_id": "conflict", "reason": "duplicate_conflict"},
                {"board": "b", "epoch": 0, "sequence": 2,
                 "event_id": "b-commit", "reason": "commit_without_stage"},
            ],
            "totals": {"board_count": 2, "applied_commits": 0,
                       "accepted_rollbacks": 1, "duplicate_replays": 1,
                       "conflicted_ids": 1, "rejected_events": 5},
        }
        self.assertEqual(reconcile(rows), expected)
        self.assertEqual(rows, original)
        for seed in range(5):
            with self.subTest(seed=seed):
                shuffled = list(rows)
                random.Random(seed).shuffle(shuffled)
                self.assertEqual(reconcile(shuffled), expected)

    def test_cli_accepts_blank_lines_and_empty_input(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "events.jsonl"
            target = Path(directory) / "result.json"
            source.write_text("\n  \n", encoding="utf-8")
            subprocess.run(
                [sys.executable, str(ROOT / "reconcile.py"),
                 "--input", str(source), "--output", str(target)],
                check=True, capture_output=True, text=True,
            )
            result = json.loads(target.read_text(encoding="utf-8"))
        self.assertEqual(result, {
            "boards": [], "incidents": [],
            "totals": {"board_count": 0, "applied_commits": 0,
                       "accepted_rollbacks": 0, "duplicate_replays": 0,
                       "conflicted_ids": 0, "rejected_events": 0},
        })


if __name__ == "__main__":
    unittest.main()
