# Batch 2 report and audit decisions

R2 is effective for every batch, including re-evaluation of INC-00001 through
INC-00064. Retained events follow `(board, epoch, sequence, event_id)`; timestamps
never determine execution order. A failed VERIFY with an existing pending
transaction clears that transaction's prior verified flag. All other rules
remain unchanged, including pending state, active image, and verified history
surviving an epoch advance. Operational notes remain audit-only evidence.

New sidecars default to `contract_revision: R2`. The builder rejects other
revision labels so current decisions cannot be presented as historical R1.
Historical batch 1 notes and archived R1 outputs remain evidence of that earlier
phase; they do not describe the current contract. Regenerated batch 1 sidecars
use R2 and explicitly explain failed verification as clearing the pending flag
while retaining verified image history.

The primary report schema, sidecar trace fields, and operation count definitions
are unchanged. The trace preserves actual state-machine order and does not
expose timestamps or paths. Attempt and reported-success counters use retained
COMMIT and ROLLBACK rows; acceptance comes from the state machine's decisions.
Excluded conflict and replay rows contribute no attempts. Successful COMMIT
after a failed verification is now rejected as `commit_unverified` unless an
intervening matching verification restores eligibility. Its reported success
flag remains true even though the accepted count does not increase.

The explanation map still covers exactly the reasons present in the primary
report, using the same twelve reason names. Failed verification clears only the
pending flag, so the exact image previously added to verified history remains
eligible for a later rollback. No report count is inferred from active-image
inequality; accepting an already active image is still an accepted operation.

Validation against the visible corpus after the R2 state changes produced the
following observed counts. Each operation cell lists attempted / reported
successful / accepted; these observations are not an independent oracle.

| Scope | Retained trace rows | COMMIT | ROLLBACK | Rejected events |
| --- | ---: | ---: | ---: | ---: |
| Batch 1, boards 1–64 | 510 | 144 / 139 / 54 | 15 / 10 / 5 | 161 |
| Batch 2, boards 65–128 | 510 | 144 / 138 / 54 | 16 / 11 / 5 | 165 |
| All 192 boards | 1530 | 432 / 416 / 163 | 48 / 32 / 16 | 489 |

For each scope, accepted operation counts matched primary totals, rejected
trace rows plus conflict incidents matched `rejected_events`, explanations
covered exactly the report's reason set, and the trace followed the R2 order.
