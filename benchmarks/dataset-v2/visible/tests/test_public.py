import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class PublicContract(unittest.TestCase):
    def test_successful_commit_and_replay(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "result.json"
            subprocess.run([sys.executable, str(root / "reconcile.py"),
                            "--input", str(root / "data/public.jsonl"),
                            "--output", str(output)], check=True)
            expected = json.loads((root / "data/public-expected.json").read_text())
            self.assertEqual(json.loads(output.read_text()), expected)


if __name__ == "__main__":
    unittest.main()
