# Rollout evidence audit

R3 is effective for **all batches**. Boot epoch advancement clears all pending
transactions before evaluating the new epoch's event, even when it fails.
The active image and verified-image history survive. Rollback authorization
requires an exact board-local `(slot, digest)` pair. R2 ordering by
`(board, epoch, sequence, event_id)` and failed-VERIFY invalidation remain in
force; timestamps never determine execution. Operational notes are reporting
values and do not revise these rules or authorize actions.

## Current machine-readable artifacts

- `batch-1-report.json` / `batch-1-trace.json`: INC-00001..INC-00064 under R3.
- `batch-2-report.json` / `batch-2-trace.json`: INC-00065..INC-00128 under R3.
- `batch-3-report.json` / `batch-3-trace.json`: INC-00129..INC-00192 under R3.
- `visible-r3-report.json` / `visible-r3-trace.json`: all 192 boards under R3.
- `batch-1-validation.json`, `batch-2-validation.json`, `batch-3-validation.json`:
  current scope, counts, tests and SHA-256 provenance.
- `r2-to-r3-changes.json`: the 13 changed acceptance/reason decisions and final
  board states. Other trace fields can change as a consequence of these decisions.
- The three `*-batch-3.md` files explain R3 decisions and concrete evidence.

The primary report has exactly `boards`, `incidents`, and `totals`.
`rejected_events` counts transition incidents plus one incident per conflicted
ID. The sidecar records each retained event in execution order: requested
image, reported `success`, rule `accepted`, rejection `reason`, and active
image before/after. Its explanation map covers every reported reason.
COMMIT/ROLLBACK counters distinguish attempted, reported successful, accepted,
and rejected operations. Replays and conflicted rows are excluded from attempts;
accepted same-image operations still count. Epoch clearing is implicit before
the first retained event of each higher epoch, without a synthetic trace row.

## Current operational values and corrections

`operations-current.json` is the resolved register of all 48 notes as of batch 3.
It contains only current values. `operations-batch-1.json` includes the corrected
F01..F08 / OPS-001..OPS-008 values and unchanged F09..F16; batch 2's F17..F32
remain unchanged; `operations-batch-3.json` contains exact F33..F48 strings.
`operations-corrections-batch-3.json` records each `current_value` alongside
its explicitly invalid `invalid_previous_value` for audit history. The former
F01..F08 values must not be used as current values. All numbers and digests
remain exactly supplied strings. No operational action was performed.

## Historical records

`r1/` preserves the R1 batch-1 report, trace, validation and documentation.
`visible-r1-report.json` and the three `*-batch-1.md` notes are also historical.
`r2/` preserves the R2 batch-1 and batch-2 reports, traces, validation and
original documentation. `visible-r2-report.json`, `visible-r2-trace.json`, and
the three `*-batch-2.md` notes remain historical R2 results. Archived
`r2/operations-batch-1.json` contains superseded F01..F08 values; `r2/STATUS.md`
marks those invalid and directs readers to the current register.

Historical hashes describe original paths and code at that phase, not current
files. Reports now under `r1/` or `r2/` must be resolved within their archive
when checking artifact hashes. The archived code hashes are provenance only;
old code snapshots were not saved. Historical rules and operational values
are superseded where the current contract or corrections say so.

## Reproduction and validation

From the repository root:

```sh
python3 reconcile.py --input data/visible.jsonl --output audit/visible-r3-report.json --audit-output audit/visible-r3-trace.json
python3 -m unittest discover -s tests -v
```

For each batch, select raw rows by `board` or `device` for the inclusive range,
call `reconcile(rows, trace=trace)` with a fresh list, then serialize the report
and `build_audit_report(report, trace)` with sorted keys, indent 2, and a trailing
newline. Each batch's report and trace were checked against global reconstruction.
This corpus has no event IDs crossing boards. New evidence with shared IDs must
be reconciled globally before selecting results. Revision labels do not choose
historical semantics: the current sidecar builder accepts only R3.

All 57 tests pass, including the unchanged public test, full-corpus permutation
and timestamp invariance, epoch clearing before failed actions, all-transaction
clearing, active/history retention, exact slot/digest rollback checks, fresh-boot
recovery, earlier-batch R3 corrections, and CLI runs on generated unseen boards,
event IDs, transaction IDs, digests and boot epochs in both schemas.
`../analysis.json` is the final requested CLI output and matches the full R3 report.
The environment provides `python3`; the requested `python` command was run with
a temporary shell function forwarding to `python3`, without changing the CLI.
All corpus rollback attempts occur
in epoch 0; focused tests exercise rollback history across epoch boundaries.
Current full totals are 150 accepted commits, 16 accepted rollbacks, and 502
incidents. These are reconstruction results, not independent physical-state
confirmation.

Malformed inputs and missing/conflicted baselines remain outside the input
guarantees. The fallback retains surviving events with a null initial active
image if baseline exclusion occurs. Output and audit paths must differ; their
writes are not an atomic pair. No known implementation defect remains.
