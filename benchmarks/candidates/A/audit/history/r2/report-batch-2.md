# Evidence batch 2 audit findings — R2

Cases `INC-00065` through `INC-00128` correspond to `board-00065` through
`board-00128` in `data/visible.jsonl`. The explicit R2 revision applies to
every batch, including previously processed evidence:

- Retained events execute by `(board, epoch, sequence, event_id)`; deliberately
  skewed wall-clock timestamps never determine execution order.
- Failed VERIFY of an existing pending transaction clears its verified flag.
  Verified image history remains intact.

Other rules remain unchanged. In particular, epoch advancement preserves
pending transactions, active images, and verification history. Operational
notes do not override the reconciliation contract.

## Reconciliation

This batch contains 664 transport rows: 510 retained events, 128 equivalent
replay rows, and 26 excluded rows belonging to 13 conflicting IDs. R2 applies
54 commits and accepts 5 rollbacks across 64 boards. There are 152 transition
rejections plus 13 duplicate-conflict incidents, for 165 total incidents.

| Action | Retained attempts | Reported success | Accepted | Rejected |
| --- | ---: | ---: | ---: | ---: |
| BASELINE | 64 | 64 | 64 | 0 |
| COMMIT | 144 | 138 | 54 | 90 |
| RESET | 27 | 21 | 21 | 6 |
| ROLLBACK | 16 | 11 | 5 | 11 |
| STAGE | 120 | 115 | 115 | 5 |
| VERIFY | 139 | 118 | 99 | 40 |

Reported success does not guarantee acceptance. The 90 rejected COMMIT
attempts comprise 39 `commit_without_stage`, 25 `commit_unverified`,
20 `commit_mismatch`, and 6 `commit_failed` incidents. Replays and globally
conflicted IDs do not count as retained action attempts.

Four failed VERIFY events in this batch clear a previously true pending
verified flag. For example, `INC-00073` successfully stages and verifies at
sequences 7 and 14, then fails verification at sequence 21. Its sequence-28
COMMIT is rejected as `commit_unverified`. The audit records the flag changing
from true to false at the failed verification, while image history is retained.

## Audit and note preservation

The separate audit artifact is tagged `R2`. Its reason catalog explains failed
verification revocation, and its transition list preserves actual sequence-based
execution. The ordinary report still has exactly `boards`, `incidents`, and
`totals`. Audit records contain no timestamps, paths, or runtime metadata.

`operations-notes.json` preserves all F01–F16 values and appends exact F17–F32
values as strings. The new notes map OPS-017/F17 to `INC-00065` through
OPS-032/F32 to `INC-00080`; operation ordinals do not equal those case numbers.
The notes remain reporting data and cannot authorize rollback or other actions.

Eight audit tests pass under R2. They check sequence ordering despite clock
skew, invariance under changed timestamps, failed-verification flag clearing
without history loss, report and audit accounting, deterministic projection,
reason coverage, exact known note values and unique IDs, and note-independent
rollback authorization. Note-preservation checks allow future appended notes.

No report/audit implementation tasks remain for this batch. Historical R1
results describe superseded behavior; current conclusions must use R2 across
all batches. No further semantic revisions are inferred from this evidence.
