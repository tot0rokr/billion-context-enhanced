"""Create new benchmark-only source copies with the historical usage observer."""

import argparse
import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
EXCLUDED = {".git", "node_modules", "dist", "benchmarks", "artifacts", "benchmark-runs", "__pycache__"}
UPSTREAM_FETCH_SHA256 = "d75748b5f8c293e2561358234e951a3c8f59ed225419830f87d657a08a1ff1f7"


def prepare(baseline, enhanced, output):
    baseline, enhanced, output = baseline.resolve(), enhanced.resolve(), output.resolve()
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite {output}")
    for source in (baseline, enhanced):
        actual = hashlib.sha256((source / "src/fetch-util.ts").read_bytes()).hexdigest()
        if actual != UPSTREAM_FETCH_SHA256:
            raise ValueError(f"fetch-util.ts differs from the audited uninstrumented source: {source}")
        if source == output or source in output.parents:
            raise ValueError("Output must be outside both source checkouts")
    output.mkdir(parents=True, mode=0o700)
    provenance = {}
    for arm, source in (("B", baseline), ("C", enhanced)):
        destination = output / arm
        shutil.copytree(source, destination, symlinks=True, ignore=shutil.ignore_patterns(*EXCLUDED))
        for filename in ("audit-usage.ts", "fetch-util.ts"):
            shutil.copyfile(ROOT / "instrumentation" / filename, destination / "src" / filename)
        (destination / ".audit").mkdir(exist_ok=True)
        shutil.copyfile(ROOT / "instrumentation/audit-meter.test.ts", destination / ".audit/audit-meter.test.ts")
        provenance[arm] = {
            "source": str(source), "destination": str(destination),
            "instrumentation": {
                name: hashlib.sha256((destination / "src" / name).read_bytes()).hexdigest()
                for name in ("audit-usage.ts", "fetch-util.ts")
            },
        }
    (output / "instrumentation-manifest.json").write_text(json.dumps(provenance, indent=2) + "\n")
    return provenance


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-source", type=Path, required=True)
    parser.add_argument("--enhanced-source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.baseline_source, args.enhanced_source, args.output), indent=2))


if __name__ == "__main__":
    main()
