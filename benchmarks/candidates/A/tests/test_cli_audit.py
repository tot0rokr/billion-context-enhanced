"""Check the optional audit CLI without changing the public report contract."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class AuditCLI(unittest.TestCase):
    def test_audit_and_primary_report_are_stable_across_transport_order(self):
        rows = (ROOT / "data/public.jsonl").read_text(encoding="utf-8").splitlines()
        expected = json.loads((ROOT / "data/public-expected.json").read_text())
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            directory = Path(directory)
            outputs = []
            for index, ordered in enumerate((rows, list(reversed(rows)))):
                source = directory / f"input-{index}.jsonl"
                report_path = directory / f"report-{index}.json"
                audit_path = directory / f"audit-{index}.json"
                source.write_text("\n" + "\n\n".join(ordered) + "\n", encoding="utf-8")
                subprocess.run([
                    sys.executable, str(ROOT / "reconcile.py"),
                    "--input", str(source), "--output", str(report_path),
                    "--audit-output", str(audit_path),
                ], check=True, capture_output=True, text=True)
                self.assertEqual(json.loads(report_path.read_text()), expected)
                audit = json.loads(audit_path.read_text())
                self.assertEqual(audit["per_action"]["COMMIT"]["attempted"], 1)
                self.assertEqual(audit["per_action"]["COMMIT"]["accepted"], 1)
                self.assertEqual(audit["summary"]["input_rows"], 5)
                self.assertEqual(audit["summary"]["duplicate_replays"], 1)
                outputs.append((report_path.read_bytes(), audit_path.read_bytes()))
            self.assertEqual(outputs[0], outputs[1])

    def test_audit_cannot_overwrite_the_primary_report(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            output = Path(directory) / "report.json"
            output.write_text("existing result\n", encoding="utf-8")
            process = subprocess.run([
                sys.executable, str(ROOT / "reconcile.py"),
                "--input", str(ROOT / "data/public.jsonl"),
                "--output", str(output), "--audit-output", str(output),
            ], capture_output=True, text=True)
            self.assertEqual(process.returncode, 2)
            self.assertIn("--audit-output must differ from --output", process.stderr)
            self.assertEqual(output.read_text(), "existing result\n")


if __name__ == "__main__":
    unittest.main()
