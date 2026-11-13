import json
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest

from reconcile import reconcile


def event(event_id, sequence, action, **changes):
    row = {
        "schema": 1,
        "event_id": event_id,
        "board": "board-a",
        "epoch": 0,
        "sequence": sequence,
        "action": action,
        "tx": "tx",
        "slot": 1,
        "digest": "new",
        "success": True,
        "time": sequence,
    }
    row.update(changes)
    return row


class ReconciliationIntegration(unittest.TestCase):
    def test_cli_handles_fresh_mixed_schema_events(self):
        root = Path(__file__).resolve().parents[1]
        randomizer = random.Random(87031)
        board = "device-" + format(randomizer.getrandbits(128), "032x")
        tx = format(randomizer.getrandbits(128), "032x")
        old, new = [format(randomizer.getrandbits(256), "064x") for _ in range(2)]
        ids = [format(randomizer.getrandbits(128), "032x") for _ in range(13)]
        steps = [
            (11, "BASELINE", {"slot": 0, "digest": old, "tx": None}),
            (11, "STAGE", {}),
            (11, "VERIFY", {}),
            (11, "VERIFY", {"success": False}),
            (11, "COMMIT", {}),
            (11, "VERIFY", {}),
            (29, "COMMIT", {}),
            (29, "ROLLBACK", {"slot": 0}),
            (29, "ROLLBACK", {}),
            (29, "STAGE", {}),
            (29, "VERIFY", {}),
            (29, "COMMIT", {}),
            (29, "COMMIT", {}),
        ]
        rows = []
        for index, (epoch, action, changes) in enumerate(steps):
            values = {"board": board, "tx": tx, "digest": new,
                      "epoch": epoch, "time": randomizer.randrange(-10**9, 10**9)}
            values.update(changes)
            row = event(ids[index], index * 17, action, **values)
            if index % 2:
                row = {
                    "schema": 2, "id": row["event_id"], "device": row["board"],
                    "boot": row["epoch"], "seq": row["sequence"],
                    "kind": row["action"].lower(), "transaction": row["tx"],
                    "slot": {0: "A", 1: "B", None: None}[row["slot"]],
                    "sha256": row["digest"], "ok": row["success"],
                    "timestamp": row["time"],
                }
            rows.append(row)
        # Cross-schema replay of the successful commit must execute only once.
        rows.append({"schema": 1, "event_id": ids[11], "board": board,
                     "epoch": 29, "sequence": 187, "action": "COMMIT",
                     "tx": tx, "slot": 1, "digest": new, "success": True,
                     "time": -10**20})
        randomizer.shuffle(rows)
        expected_rejections = [
            (3, "verify_failed"), (4, "commit_unverified"),
            (6, "commit_without_stage"), (7, "rollback_unverified"),
            (12, "commit_without_stage"),
        ]
        expected = {
            "boards": [{"board": board, "epoch": 29,
                        "active_slot": "B", "active_digest": new}],
            "incidents": [
                {"board": board, "epoch": steps[index][0],
                 "sequence": index * 17, "event_id": ids[index], "reason": reason}
                for index, reason in expected_rejections
            ],
            "totals": {"board_count": 1, "applied_commits": 1,
                       "accepted_rollbacks": 1, "duplicate_replays": 1,
                       "conflicted_ids": 0, "rejected_events": 5},
        }
        with tempfile.TemporaryDirectory(dir=root) as directory:
            source = Path(directory) / "unseen.jsonl"
            output = Path(directory) / "result.json"
            source.write_text("\n".join(json.dumps(row) for row in rows) + "\n",
                              encoding="utf-8")
            subprocess.run([sys.executable, str(root / "reconcile.py"),
                            "--input", str(source), "--output", str(output)], check=True)
            self.assertEqual(json.loads(output.read_text()), expected)

    def test_full_corpus_report_and_audit_ignore_clock_values(self):
        root = Path(__file__).resolve().parents[1]
        rows = [json.loads(line) for line in
                (root / "data/visible.jsonl").read_text().splitlines() if line.strip()]
        expected_audit = []
        expected = reconcile(rows, audit=expected_audit)
        randomizer = random.Random(2026)
        skewed = []
        for source in rows:
            row = dict(source)
            row["time" if row["schema"] == 1 else "timestamp"] = randomizer.randrange(
                -10**30, 10**30)
            skewed.append(row)
        randomizer.shuffle(skewed)
        actual_audit = []
        self.assertEqual(reconcile(skewed, audit=actual_audit), expected)
        self.assertEqual(actual_audit, expected_audit)
        locations = [(item["board"], item["epoch"], item["sequence"], item["event_id"])
                     for item in actual_audit]
        self.assertEqual(locations, sorted(locations))

    def test_r3_revises_all_batches_and_preserves_r2_verification_rules(self):
        root = Path(__file__).resolve().parents[1]
        verification_boards = {"board-00013", "board-00073", "board-00133"}
        epoch_boards = {"board-00002", "board-00074", "board-00134"}
        boards = verification_boards | epoch_boards | {"board-00152"}
        rows = [json.loads(line) for line in
                (root / "data/visible.jsonl").read_text().splitlines() if line.strip()]
        audit = []
        reconcile((row for row in rows if row.get("board", row.get("device")) in boards),
                  audit=audit)
        by_id = {item["event_id"]: item for item in audit}
        for board in sorted(verification_boards):
            with self.subTest(board=board):
                self.assertEqual(by_id[board + "-e002"]["outcome"], "accepted")
                self.assertEqual(by_id[board + "-e003"]["reason"], "verify_failed")
                self.assertEqual(by_id[board + "-e004"]["reason"], "commit_unverified")
                self.assertEqual(by_id[board + "-e004"]["active_digest"],
                                 by_id[board + "-e000"]["digest"])
        for board in sorted(epoch_boards):
            with self.subTest(board=board):
                self.assertEqual(by_id[board + "-e002"]["outcome"], "accepted")
                self.assertEqual(by_id[board + "-e003"]["reason"], "commit_without_stage")
                self.assertEqual(by_id[board + "-e003"]["active_digest"],
                                 by_id[board + "-e000"]["digest"])
                self.assertEqual(by_id[board + "-e007"]["reason"], "commit_without_stage")
        self.assertEqual(by_id["board-00152-e004"]["reason"], "rollback_unverified")
        self.assertEqual(by_id["board-00152-e004"]["digest"],
                         by_id["board-00152-e000"]["digest"])
        self.assertNotEqual(by_id["board-00152-e004"]["slot"],
                            by_id["board-00152-e000"]["slot"])
        self.assertEqual(by_id["board-00152-e007"]["outcome"], "accepted")

    def test_cli_audit_preserves_public_report_and_exact_inert_notes(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(dir=root) as directory:
            output = Path(directory) / "report.json"
            audit_output = Path(directory) / "audit.json"
            notes = root / "data/operations-notes.json"
            subprocess.run([
                sys.executable, str(root / "reconcile.py"),
                "--input", str(root / "data/public.jsonl"),
                "--output", str(output), "--audit-output", str(audit_output),
                "--operations-notes", str(notes),
            ], check=True)
            self.assertEqual(json.loads(output.read_text()),
                             json.loads((root / "data/public-expected.json").read_text()))
            audit = json.loads(audit_output.read_text())
            self.assertEqual(audit["contract"], "R3")
            self.assertEqual(audit["operations_notes"], json.loads(notes.read_text()))
            case = audit["cases"][0]
            self.assertEqual(case["accepted_commit_ids"], ["pub-3"])
            self.assertEqual(case["attempts"], {"COMMIT": 1, "ROLLBACK": 0})
            self.assertEqual([row["active_digest"] for row in case["events"]],
                             ["old", "old", "old", "new"])
            self.assertEqual(len(case["events"]), 4)

    def test_cli_rejects_audit_output_alias_before_writing(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(dir=root) as directory:
            output = Path(directory) / "report.json"
            output.write_text("existing report", encoding="utf-8")
            result = subprocess.run([
                sys.executable, str(root / "reconcile.py"),
                "--input", str(root / "data/public.jsonl"),
                "--output", str(output), "--audit-output", str(output),
            ], capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertIn("must be different files", result.stderr)
            self.assertEqual(output.read_text(), "existing report")

    def test_mixed_schema_replays_and_r3_transitions_are_order_independent(self):
        rows = [
            event("base", 0, "BASELINE", slot=0, digest="old", tx=None, time=100),
            event("stage", 1, "STAGE", time=500),
            {
                "schema": 2, "id": "stage", "device": "board-a", "boot": 0,
                "seq": 1, "kind": "stage", "transaction": "tx", "slot": "B",
                "sha256": "new", "ok": True, "timestamp": 99,
            },
            event("verify", 2, "VERIFY", time=-10),
            event("verify-failed", 3, "VERIFY", success=False, time=-100),
            event("commit", 4, "COMMIT", epoch=1, time=-10000),
            event("reverify", 5, "VERIFY", epoch=1, time=8000),
            event("restage", 6, "STAGE", epoch=1, time=12000),
            event("fresh-verify", 7, "VERIFY", epoch=1, time=-100),
            event("commit-accepted", 8, "COMMIT", epoch=1, time=-100),
            event("commit-repeat", 9, "COMMIT", epoch=1, time=-1000),
        ]
        expected = {
            "boards": [{"board": "board-a", "epoch": 1,
                        "active_slot": "B", "active_digest": "new"}],
            "incidents": [
                {"board": "board-a", "epoch": 0, "sequence": 3,
                 "event_id": "verify-failed", "reason": "verify_failed"},
                {"board": "board-a", "epoch": 1, "sequence": 4,
                 "event_id": "commit", "reason": "commit_without_stage"},
                {"board": "board-a", "epoch": 1, "sequence": 5,
                 "event_id": "reverify", "reason": "verify_without_stage"},
                {"board": "board-a", "epoch": 1, "sequence": 9,
                 "event_id": "commit-repeat", "reason": "commit_without_stage"},
            ],
            "totals": {
                "board_count": 1, "applied_commits": 1, "accepted_rollbacks": 0,
                "duplicate_replays": 1, "conflicted_ids": 0, "rejected_events": 4,
            },
        }
        for seed in range(10):
            shuffled = list(rows)
            random.Random(seed).shuffle(shuffled)
            with self.subTest(seed=seed):
                self.assertEqual(reconcile(iter(shuffled)), expected)

    def test_global_conflict_removes_all_copies_before_execution(self):
        stage = event("shared-id", 1, "STAGE")
        rows = [
            event("base-a", 0, "BASELINE", slot=0, digest="old", tx=None),
            event("base-b", 0, "BASELINE", board="board-b", slot=0,
                  digest="other-old", tx=None),
            stage, dict(stage),
            event("shared-id", 1, "STAGE", board="board-b"),
            event("verify", 2, "VERIFY"),
            event("commit", 3, "COMMIT"),
        ]
        result = reconcile(rows)
        self.assertEqual(result["totals"], {
            "board_count": 2, "applied_commits": 0, "accepted_rollbacks": 0,
            "duplicate_replays": 0, "conflicted_ids": 1, "rejected_events": 3,
        })
        self.assertEqual(result["incidents"], [
            {"board": "board-a", "epoch": 0, "sequence": 1,
             "event_id": "shared-id", "reason": "duplicate_conflict"},
            {"board": "board-a", "epoch": 0, "sequence": 2,
             "event_id": "verify", "reason": "verify_without_stage"},
            {"board": "board-a", "epoch": 0, "sequence": 3,
             "event_id": "commit", "reason": "commit_without_stage"},
        ])
        self.assertEqual([board["active_digest"] for board in result["boards"]],
                         ["old", "other-old"])


if __name__ == "__main__":
    unittest.main()
