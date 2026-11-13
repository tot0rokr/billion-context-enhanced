# Rollout evidence audit

R2 is effective for **all batches**. Retained events execute by
`(board, epoch, sequence, event_id)`, never wall-clock time. Failed VERIFY
clears the existing pending transaction's verified flag. All other R1 rules
remain unchanged, including pending transactions and exact verified image
history surviving epoch changes. Operational notes do not revise these rules.

## Current machine-readable artifacts

- `batch-1-report.json` and `batch-1-trace.json`: INC-00001..INC-00064, regenerated under R2.
- `batch-2-report.json` and `batch-2-trace.json`: INC-00065..INC-00128 under R2.
- `visible-r2-report.json` and `visible-r2-trace.json`: all 192 boards under R2.
- `batch-1-validation.json` and `batch-2-validation.json`: scope, counts, tests and SHA-256 provenance for R2 artifacts.
- `operations-batch-1.json`: exact F01..F16 / OPS-001..OPS-016 values.
- `operations-batch-2.json`: exact F17..F32 / OPS-017..OPS-032 values.
- The three `*-batch-2.md` files explain R2 decisions and concrete evidence.

The primary report has exactly `boards`, `incidents`, and `totals`. Its
`rejected_events` includes one incident per conflicted ID. The audit sidecar
records every retained event in execution order with requested image, reported
`success`, rule `accepted`, rejection `reason`, and active image before/after.
Its explanation map defines every reason present in the primary report.
Operation counters separate attempted, reported successful, accepted, and
rejected COMMITs/ROLLBACKs. Replay and conflicted rows are excluded from attempts.
Accepted same-image operations still count. Before/after fields show active
images; pending verification changes follow the recorded action and reason.

## Historical R1 records

`r1/batch-1-report.json`, `r1/batch-1-trace.json`, and
`r1/batch-1-validation.json` preserve the earlier R1 artifacts byte for byte.
`r1/README.md` preserves their original documentation. `visible-r1-report.json`
and the three `*-batch-1.md` notes are also historical R1 records. They are
superseded for current reconciliation. Historical validation hashes describe
files at the original paths and code as it existed in phase 2; those code
hashes are not assertions about the current R2 implementation. The archived
batch report and trace now live under `r1/` instead of their former paths.

## Reproduction

From the repository root, reproduce the full corpus with:

```sh
python3 reconcile.py --input data/visible.jsonl --output audit/visible-r2-report.json --audit-output audit/visible-r2-trace.json
python3 -m unittest discover -s tests -v
```

For a batch, load `data/visible.jsonl`, select raw records using `board` or
`device` for the inclusive board range above, call `reconcile(rows, trace=trace)`
with a fresh list, and serialize the result plus `build_audit_report(result,
trace)` with sorted keys, indent 2, and a trailing newline. Batch results and
traces were verified against global reconciliation. This corpus has no IDs
shared across boards; new evidence with shared IDs must be reconciled globally
before selecting results. Revision labels do not select older semantics: the
current sidecar builder accepts only R2.

Output files are written after reading and reconciling the input. Main and
audit output paths must differ; the two writes are not an atomic pair. All
50 tests pass, including input permutation invariance, full-corpus timestamp
rewriting, both R2 changes applied to earlier cases, and unchanged public tests.
The counts are reconstruction results under R2, not independent confirmation
of physical device state. No unresolved implementation defect was found.
Malformed input and missing/conflicted baselines remain outside the stated
input guarantees; the implementation retains its documented fallback behavior.
