# Reconciliation audit artifacts

Current contract: **R3 for all batches**. Events execute by
`(board, epoch, sequence, event_id)` and clocks are ignored. Failed VERIFY of an
existing pending transaction clears its verified flag. Epoch advancement clears
all pending transactions, retaining the active image and verified-image history.
Rollback authorization requires the exact `(slot,digest)` pair.

| Current artifact | Scope |
| --- | --- |
| `batch-1-report.json` / `batch-1-audit.json` | Cases INC-00001–INC-00064, recomputed under R3 |
| `batch-2-report.json` / `batch-2-audit.json` | Cases INC-00065–INC-00128, recomputed under R3 |
| `batch-3-report.json` / `batch-3-audit.json` | Cases INC-00129–INC-00192 under R3 |
| `visible-report.json` / `visible-audit.json` | All 192 boards in the complete visible corpus under R3 |
| `operations-notes.json` | Exact current reporting values F01–F48, including corrected F01–F08 |
| `operations-corrections.json` | Historical invalidated/current value pairs for F01–F08; old values are invalid |

Primary reports preserve the required `boards`, `incidents`, and `totals` shape.
Separate audit files identify the revision and explain transport disposition,
accepted and rejected attempts, state changes, and incident reasons. Counts of
attempts exclude transport replays and globally conflicted IDs. Audit records
separate pending state before epoch advancement, after automatic clearing, and
after the event action. Current operational values come from the current-note
file only; the correction ledger does not supply alternate valid values.

`ingest-batch-3.md`, `state-batch-3.md`, and `report-batch-3.md` explain the R3
findings. `../PHASE_NOTES.md` contains the full decision and validation history,
artifact fingerprints, reproduction steps, and carry-forward decisions.

Superseded reports and findings are preserved unchanged in `history/r1/` and
`history/r2/`. They are historical evidence, not current reconciliation results.
