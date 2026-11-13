# State reconstruction: R3 and evidence batch 3

R3 explicitly clears every pending transaction when a board's boot epoch
advances. The boundary is applied before evaluating the first retained event
of the new epoch, even if that event reports failure or is rejected. The
active image and exact verified `(slot, digest)` history survive. Sequence
ordering and failed-VERIFY invalidation from R2 remain in force.

This revision applies to all evidence, including previously processed cases.
The earlier state batch notes remain historical records of R1 and R2.
The counts below use global ingestion before selecting a batch; excluded
conflicts never enter state transition processing.

## Current results and revision impact

| Scope | Boards | Retained events | Applied COMMIT | Accepted ROLLBACK | Transition incidents | Conflict incidents | Total rejected |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| INC-00001..INC-00064 | 64 | 510 | 49 | 5 | 154 | 12 | 166 |
| INC-00065..INC-00128 | 64 | 510 | 50 | 5 | 156 | 13 | 169 |
| INC-00129..INC-00192 | 64 | 510 | 51 | 6 | 154 | 13 | 167 |
| Full visible corpus | 192 | 1,530 | 150 | 16 | 464 | 38 | 502 |

Every batch has 27 final active images in slot A and 37 in slot B; the full
corpus has 81 in A and 111 in B. Duplicate replays remain 384 and conflicted
IDs remain 38. These are contract reconstruction results.

| Scope | R2 applied COMMIT | R3 applied COMMIT | R2 total rejected | R3 total rejected |
| --- | ---: | ---: | ---: | ---: |
| Batch 1 | 54 | 49 | 161 | 166 |
| Batch 2 | 54 | 50 | 165 | 169 |
| Batch 3 | 55 | 51 | 163 | 167 |
| Full corpus | 163 | 150 | 489 | 502 |

Comparing actual event traces against the archived R2 full-corpus trace
finds exactly 13 changes to event acceptance or rejection reason. Each is
an epoch 1 COMMIT previously accepted from epoch 0 pending state; each now
emits `commit_without_stage`. Their event IDs are:

- `board-00002-e003`, `board-00014-e003`, `board-00026-e003`,
  `board-00038-e003`, `board-00062-e003`
- `board-00074-e003`, `board-00086-e003`, `board-00098-e003`,
  `board-00122-e003`
- `board-00134-e003`, `board-00146-e003`, `board-00158-e003`,
  `board-00182-e003`

There are no rollback acceptance changes. The aggregate
`commit_without_stage` count increases from 118 to 131; all other rejection
reason counts remain unchanged from R2. Active-image trace fields also
reflect the removed commits, so unchanged acceptance does not imply every
other field in an event's trace is unchanged.

## Batch 3 accepted operations and attempts

| Action | Retained attempts | Accepted | Rejected |
| --- | ---: | ---: | ---: |
| BASELINE | 64 | 64 | 0 |
| STAGE | 121 | 115 | 6 |
| VERIFY | 138 | 99 | 39 |
| COMMIT | 144 | 51 | 93 |
| RESET | 26 | 21 | 5 |
| ROLLBACK | 17 | 6 | 11 |

The batch's 154 transition incidents comprise 5 `commit_failed`,
20 `commit_mismatch`, 24 `commit_unverified`, 44 `commit_without_stage`,
5 `reset_failed`, 6 `rollback_failed`, 5 `rollback_unverified`,
6 `stage_failed`, 20 `verify_failed`, 4 `verify_mismatch`, and
15 `verify_without_stage`. Ingestion contributes 13 separate conflict
incidents. Reported attempts do not automatically count as accepted actions.

## Concrete evidence and retained history

`INC-00134` demonstrates the R3 boot boundary. STAGE `board-00134-e001`
and successful VERIFY `board-00134-e002` occur in epoch 0, at sequences 7
and 14, for slot B and digest
`f1dba782a0594e12b7a81e66cd3e82c15f2c099cf62e25114bd62aedcb24bc50`.
COMMIT `board-00134-e003` is the first epoch 1 event at sequence 21.
Although it reports success and matches the former pending image, the
boundary has already cleared pending state; it emits `commit_without_stage`.
R2 accepted this event.

Epoch 2 of the same case stages and verifies another image, then RESET
`board-00134-e006` clears pending before COMMIT `board-00134-e007`.
That COMMIT is also `commit_without_stage`, for the unchanged RESET rule.
The board finishes at epoch 2 on baseline slot A, digest
`bf88fe7b79a136323a0bcdf5692a6d01401ce0611c112b19876607bde1c3efc0`,
with no accepted commits or rollbacks. The failed first commit does not
change its active image.

`INC-00140` demonstrates exact image history. Its baseline authorizes slot
A with digest
`f286d6c7c74807b1d8a6d4f1f1ed47d9bd65d623e83ed82ecbd37ddc2aca07c4`.
ROLLBACK `board-00140-e004` requests the same digest in slot B and emits
`rollback_unverified`. Digest equality alone is insufficient authorization.

`INC-00141` has an accepted epoch 0 COMMIT `board-00141-e003`, followed by
accepted ROLLBACK `board-00141-e004` to its baseline slot A image. The first
epoch 1 event is STAGE `board-00141-e005`; its before/after active image is
unchanged. Failed VERIFY and a rejected COMMIT leave that image active.
The board therefore records one accepted COMMIT and one accepted ROLLBACK
while ending on its baseline. Neither the epoch transition nor STAGE alone
switches the active image.

All 48 retained ROLLBACK attempts in this corpus occur in epoch 0. The corpus
does not directly exercise a rollback using history from an earlier epoch.
Focused tests cover that R3 requirement: verified images survive a jump to
a later epoch, pending commits are rejected, an exact historical pair can
be rolled back, and the same digest in the other slot remains unauthorized.
Tests also confirm that a committed active image survives the epoch change.

Previously processed cases are corrected by the same rule. For example,
`board-00002-e003` and `board-00074-e003` now emit `commit_without_stage`
instead of applying commits from the prior boot's pending verification.
Their historical R2 notes remain available as records of the superseded
contract, not descriptions of current behavior.

## Implementation and validation

`reconcile_states(events, *, trace=None)` keeps its return tuple and exact
trace schema. It clears pending state when `event["epoch"] > epoch`, then
evaluates that event using the normal action rules. The change creates no
synthetic event, does not erase verified history, and does not touch the
active slot or digest. A later STAGE, VERIFY, and COMMIT within the new epoch
can still succeed.

`python3 -m unittest discover -s tests -p test_state_machine.py -v` passes
25 tests. Focused R3 coverage includes clearing multiple transactions on an
epoch jump, applying the boundary before failed RESET/STAGE/VERIFY/COMMIT/
ROLLBACK events, preserving committed active state, retaining baseline and
verified candidate history, enforcing exact slot/digest pairs, and accepting
a fresh transaction in the new boot. R2 clock-ordering and verification
failure tests, rejection precedence, transaction isolation, and optional
trace tests also continue to pass.
