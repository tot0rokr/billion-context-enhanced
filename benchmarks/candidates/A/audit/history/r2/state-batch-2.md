# State-machine audit: evidence batch 2 and R2

The explicit R2 revision applies to every evidence batch, including cases
INC-00001 through INC-00064 previously reconstructed under R1. It replaces two
rules: execution follows `(board, epoch, sequence, event_id)` without consulting
wall-clock values, and a failed VERIFY of an existing pending transaction clears
that transaction's prior verified flag. All other rules remain unchanged.

The historical findings in `history/r1/state-batch-1.md` describe R1 and are superseded for
current reconstruction. There is no special baseline reordering in R2: a valid
board's successful baseline precedes its other events in the prescribed order.
The engine accepts clockless normalized events and the optional trace follows
exactly the same ordering as execution.

Failed verification retains the pending slot/digest and all exact-image
verification history. It changes only the addressed transaction's verified
flag. A later matching successful VERIFY restores the flag; it does not count
as a new history addition if that exact image is already known. Verification
without a stage retains its `verify_without_stage` precedence. Pending state,
active image, and verified history continue to survive epoch advancement.

## Current R2 outcomes

Computed after globally reconciling all IDs in `data/visible.jsonl`, then
selecting each board range. These are contract-derived reconstruction results,
not independently supplied expected reports.

| Scope | Retained events | Applied commits | Accepted rollbacks | Transition incidents | Conflicted IDs | Total incidents |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Cases 1–64 | 510 | 54 | 5 | 149 | 12 | 161 |
| Cases 65–128 | 510 | 54 | 5 | 152 | 13 | 165 |
| All 192 visible cases | 1530 | 163 | 16 | 451 | 38 | 489 |

Cases 65–128 have the following executed attempts. Global conflicts and replay
copies do not execute, and a transport-level success flag is not an acceptance.

| Action | Retained attempts | Reported success | Accepted |
| --- | ---: | ---: | ---: |
| BASELINE | 64 | 64 | 64 |
| STAGE | 120 | 115 | 115 |
| VERIFY | 139 | 118 | 99 |
| COMMIT | 144 | 138 | 54 |
| RESET | 27 | 21 | 21 |
| ROLLBACK | 16 | 11 | 5 |

The 90 rejected batch-2 commits comprise 39 without stage, 25 unverified,
20 mismatched, and 6 reported failures. Failed VERIFY revokes a previously true
flag at `board-00073-e003`, `board-00097-e003`, `board-00109-e003`, and
`board-00121-e003`. Commits `e003` on boards 00074, 00086, 00098, and 00122
remain accepted using verification from an earlier epoch; R2 does not change
the pending-state retention rule.

## Earlier evidence reinterpreted under R2

- `board-00001-e003` fails VERIFY after `e002` successfully verified its pending
  image. It now clears the flag. Commit `e004` therefore rejects with
  `commit_unverified`; later `e006` also fails and `e007` rejects with the same
  commit reason. No commit applies on this board.
- `board-00002-e003` still applies in epoch 1 using stage `e001` and verification
  `e002` from epoch 0. In epoch 2, `e006` RESET now executes after stage `e004`
  and verification `e005`, in sequence order, and clears pending state. Commit
  `e007` rejects with `commit_without_stage`. This board has one applied commit.
- `board-00065-e001` is excluded by a global conflict, so its early VERIFY and
  COMMIT cannot use that stage. Its later failed VERIFY also prevents the final
  commit. `board-00066-e003` mismatches verification and clears the flag; its
  later successful RESET clears the new pending transaction before commit.

Operational notes remain reporting data. The earlier forbidden-action values
do not introduce an epoch-state rule; only the explicit R2 revisions above have
changed reconstruction.

## Validation and remaining work

All 14 focused state-machine tests pass. Updated tests reject deliberately
reversed clock order, resolve equal sequences by event ID, and use clockless
normalized events by default. New checks cover failed-VERIFY revocation of only
the target transaction, unchanged staged data/history, recovery by later
matching verification, and pending verification surviving epoch advancement.
Existing trace invariance and independent-snapshot checks continue to pass.

The state-machine implementation is complete for this phase. The parent owns
integrated validation, regenerated primary/audit artifacts, and current-contract
documentation. Remaining non-revised interpretations are missing-baseline
fallback after conflict removal and missing-stage precedence for failed VERIFY.
