# Evidence batch 1 audit

R1 is the only contract revision in force for these artifacts. The evidence
contains INC-00001 through INC-00064; data/visible.jsonl contains all 192 boards.

- `batch-1-report.json`: required R1 report for these 64 cases.
- `batch-1-trace.json`: retained event outcomes in execution order, exact
  requested image, active image before/after, acceptance, rejection reason,
  reason explanations, conflict incidents and operation counters.
- `operations-batch-1.json`: all sixteen operational note values, preserved
  as strings. They are audit data and do not authorize or influence operations.
- `visible-r1-report.json`: required R1 report for the complete visible corpus.
- `batch-1-validation.json`: counts, scope, checks and SHA-256 provenance.
- The three `*-batch-1.md` files record ingestion, state and reporting findings.

An event's `success` is its device-reported result. `accepted` records whether
it passes the reconciliation rules. Only accepted COMMITs and ROLLBACKs count
as applied operations. An accepted rollback may target the current image.
`attempted` counts retained normalized events; transport replays and conflicted
IDs are excluded. Conflicts appear separately, one incident per ID. The main
report's `rejected_events` includes those conflict incidents. Trace entries
omit timestamps but preserve actual execution order; sequence order is not
execution order under R1. Pending state is interpreted from the R1 transitions
and event decisions; the before/after image fields describe active state only.

Run the CLI on any corpus with an optional audit sidecar:

```sh
python3 reconcile.py --input data/visible.jsonl --output audit/visible-r1-report.json --audit-output audit/visible-r1-trace.json
```

The main report's schema and behavior are unchanged when the optional flag is
used. The input is read and reconciled before output files are opened. Separate
output paths are required. Writes to the two files are not an atomic pair.

Reproduce the batch artifacts from the repository root:

```python
import json
from pathlib import Path
from reconcile import reconcile
from report import build_audit_report

rows = [json.loads(line) for line in Path("data/visible.jsonl").read_text().splitlines()
        if line.strip()]
boards = {f"board-{i:05d}" for i in range(1, 65)}
batch = [row for row in rows if row.get("board", row.get("device")) in boards]
trace = []
report = reconcile(batch, trace=trace)
for name, value in (("batch-1-report.json", report),
                    ("batch-1-trace.json", build_audit_report(report, trace))):
    Path("audit", name).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
```

The batch projection was verified against global reconciliation. In this
corpus, IDs never cross board boundaries. For new evidence with cross-board
IDs, reconcile globally before selecting board results.

Validate using `python3 -m unittest discover -s tests -v`. Artifact totals
are observations under R1, not an independent correctness oracle. An explicit
future revision requires updating transitions, explanations, tests and saved
artifacts together; the sidecar's revision label alone does not change rules.
