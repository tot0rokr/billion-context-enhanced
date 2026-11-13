"""End-to-end contract checks with identifiers generated independently of fixtures."""

import hashlib
import json
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest
import uuid

from reconcile import reconcile


ROOT = Path(__file__).resolve().parents[1]


def image_digest():
    return hashlib.sha256(uuid.uuid4().bytes).hexdigest()


def encode(event, schema):
    if schema == 1:
        return {"schema": 1, **event,
                "slot": {"A": 0, "B": 1, None: None}[event["slot"]],
                "time": 100000 - event["sequence"]}
    return {
        "schema": 2, "id": event["event_id"], "device": event["board"],
        "boot": event["epoch"], "seq": event["sequence"],
        "kind": event["action"].lower(), "transaction": event["tx"],
        "slot": event["slot"], "sha256": event["digest"],
        "ok": event["success"], "timestamp": -100000 + event["sequence"],
    }


class UnseenEvents(unittest.TestCase):
    def test_cli_reconciles_fresh_mixed_schema_transactions(self):
        board = "fresh-device-" + uuid.uuid4().hex
        tx_a, tx_b = uuid.uuid4().hex, uuid.uuid4().hex
        original, candidate, other = image_digest(), image_digest(), image_digest()
        events, incidents = [], []

        def add(action, epoch, sequence, tx=tx_a, slot="B", digest=candidate,
                success=True, reason=None):
            event = {
                "event_id": uuid.uuid4().hex, "board": board, "epoch": epoch,
                "sequence": sequence, "action": action, "tx": tx, "slot": slot,
                "digest": digest, "success": success,
            }
            events.append(event)
            if reason is not None:
                incidents.append({**{key: event[key] for key in (
                    "board", "epoch", "sequence", "event_id")}, "reason": reason})
            return event

        add("BASELINE", 7, 0, tx=None, slot="A", digest=original)
        add("STAGE", 7, 10)
        add("VERIFY", 7, 20)
        add("VERIFY", 7, 30, success=False, reason="verify_failed")
        add("COMMIT", 7, 40, reason="commit_unverified")
        add("VERIFY", 7, 50)
        committed = add("COMMIT", 7, 60)
        add("COMMIT", 7, 70, reason="commit_without_stage")
        add("STAGE", 7, 80)
        add("VERIFY", 7, 90)
        add("STAGE", 7, 100, tx=tx_b, slot="A", digest=other)
        add("VERIFY", 7, 110, tx=tx_b, slot="A", digest=other)
        add("COMMIT", 9, 0, reason="commit_without_stage")
        add("VERIFY", 9, 10, tx=tx_b, slot="A", digest=other,
            reason="verify_without_stage")
        add("ROLLBACK", 9, 20, slot="A", reason="rollback_unverified")
        add("ROLLBACK", 9, 30)
        add("STAGE", 9, 40, tx=None, slot="A", digest=other)
        add("COMMIT", 9, 50, tx=None, slot="A", digest=other,
            reason="commit_unverified")
        add("VERIFY", 9, 60, tx=None, slot="A", digest=other)
        add("COMMIT", 9, 70, tx=None, slot="A", digest=other)
        add("RESET", 9, 80, tx=None, slot=None, digest=None, success=False,
            reason="reset_failed")
        add("ROLLBACK", 9, 90, slot="A", digest=original)

        rows = [encode(event, 1 + index % 2) for index, event in enumerate(events)]
        rows.append(encode(committed, 2))
        random.Random(735).shuffle(rows)
        expected = {
            "boards": [{"board": board, "epoch": 9,
                        "active_slot": "A", "active_digest": original}],
            "incidents": incidents,
            "totals": {"board_count": 1, "applied_commits": 2,
                       "accepted_rollbacks": 2, "duplicate_replays": 1,
                       "conflicted_ids": 0, "rejected_events": 8},
        }
        self.assertEqual(reconcile(iter(rows)), expected)
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            source, output = Path(directory) / "fresh.jsonl", Path(directory) / "report.json"
            source.write_text("\n\n".join(json.dumps(row) for row in rows), encoding="utf-8")
            subprocess.run([
                sys.executable, str(ROOT / "reconcile.py"),
                "--input", str(source), "--output", str(output),
            ], cwd=directory, check=True, capture_output=True, text=True)
            self.assertEqual(json.loads(output.read_text()), expected)

    def test_fresh_global_conflict_and_board_local_rollback_history(self):
        first, second = sorted([uuid.uuid4().hex, uuid.uuid4().hex])
        first_image, second_image, target_image = image_digest(), image_digest(), image_digest()
        collision, transaction = uuid.uuid4().hex, uuid.uuid4().hex

        def event(board, sequence, action, digest, event_id=None, tx=None, slot="A"):
            return {"event_id": event_id or uuid.uuid4().hex, "board": board,
                    "epoch": 4, "sequence": sequence, "action": action, "tx": tx,
                    "slot": slot, "digest": digest, "success": True}

        baseline_a = event(first, 0, "BASELINE", first_image)
        baseline_b = event(second, 0, "BASELINE", second_image)
        conflict_a = event(first, 7, "STAGE", target_image, collision, transaction, "B")
        conflict_b = event(second, 7, "STAGE", target_image, collision, transaction, "B")
        verify_a = event(first, 14, "VERIFY", target_image, tx=transaction, slot="B")
        verify_b = event(second, 14, "VERIFY", target_image, tx=transaction, slot="B")
        rollback = event(second, 21, "ROLLBACK", first_image)
        events = [baseline_b, conflict_b, baseline_a, conflict_a, conflict_b,
                  rollback, verify_b, verify_a]
        rows = [encode(row, 1 + index % 2) for index, row in enumerate(events)]
        result = reconcile(rows)
        self.assertEqual(result["totals"], {
            "board_count": 2, "applied_commits": 0, "accepted_rollbacks": 0,
            "duplicate_replays": 0, "conflicted_ids": 1, "rejected_events": 4,
        })
        self.assertEqual(result["incidents"], [
            {**{key: row[key] for key in ("board", "epoch", "sequence", "event_id")},
             "reason": reason}
            for row, reason in ((conflict_a, "duplicate_conflict"),
                                (verify_a, "verify_without_stage"),
                                (verify_b, "verify_without_stage"),
                                (rollback, "rollback_unverified"))
        ])
        self.assertEqual([row["active_digest"] for row in result["boards"]],
                         [first_image, second_image])
        self.assertEqual(reconcile(reversed(rows)), result)


if __name__ == "__main__":
    unittest.main()
