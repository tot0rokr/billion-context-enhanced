import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from prepare_instrumented import ROOT, prepare
from recompute import request_cost


class CostRules(unittest.TestCase):
    def setUp(self):
        self.pricing = json.loads((ROOT / "results/cost-estimate.json").read_text())

    def row(self, **changes):
        return dict(input_tokens=272000, cached_input_tokens=100000,
                    cache_write_input_tokens=0, output_tokens=100,
                    reasoning_output_tokens=10) | changes

    def test_long_rates_apply_to_the_whole_request_above_the_boundary(self):
        self.assertEqual(sum(request_cost(self.row(), self.pricing).values()), Decimal("1.825"))
        self.assertEqual(sum(request_cost(self.row(input_tokens=272001), self.pricing).values()), Decimal("3.64752"))

    def test_cache_writes_are_not_charged_again_as_uncached_input(self):
        row = self.row(input_tokens=2000, cached_input_tokens=500,
                       cache_write_input_tokens=300, output_tokens=2,
                       reasoning_output_tokens=1)
        self.assertEqual(sum(request_cost(row, self.pricing).values()), Decimal("0.01635"))

    def test_reasoning_is_already_in_output(self):
        self.assertEqual(request_cost(self.row(reasoning_output_tokens=0), self.pricing),
                         request_cost(self.row(reasoning_output_tokens=100), self.pricing))

    def test_invalid_token_categories_are_rejected(self):
        with self.assertRaises(ValueError):
            request_cost(self.row(cached_input_tokens=300000), self.pricing)


class InstrumentedCopies(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="bili-publication-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.sources = [self.root / "baseline", self.root / "enhanced"]
        self.original = (ROOT.parent / "src/fetch-util.ts").read_bytes()
        for source in self.sources:
            (source / "src").mkdir(parents=True)
            (source / "src/fetch-util.ts").write_bytes(self.original)
            (source / "node_modules").mkdir()
            (source / "node_modules/not-a-source").write_text("omit")

    def test_new_copies_match_the_historical_observer_and_preserve_inputs(self):
        output = self.root / "instrumented"
        prepare(*self.sources, output)
        for arm in "BC":
            for name in ("audit-usage.ts", "fetch-util.ts"):
                self.assertEqual((output / arm / "src" / name).read_bytes(),
                                 (ROOT / "instrumentation" / name).read_bytes())
            self.assertFalse((output / arm / "node_modules").exists())
            self.assertTrue((output / arm / ".audit/audit-meter.test.ts").is_file())
        for source in self.sources:
            self.assertEqual((source / "src/fetch-util.ts").read_bytes(), self.original)

    def test_existing_output_is_preserved(self):
        output = self.root / "existing"
        output.mkdir()
        marker = output / "keep"
        marker.write_text("preserve")
        with self.assertRaises(FileExistsError):
            prepare(*self.sources, output)
        self.assertEqual(marker.read_text(), "preserve")

    def test_source_drift_is_rejected_before_output_creation(self):
        (self.sources[0] / "src/fetch-util.ts").write_text("changed")
        output = self.root / "new"
        with self.assertRaises(ValueError):
            prepare(*self.sources, output)
        self.assertFalse(output.exists())

    def test_nested_output_cannot_recursively_copy_itself(self):
        with self.assertRaises(ValueError):
            prepare(*self.sources, self.sources[1] / "nested")


if __name__ == "__main__":
    unittest.main()
