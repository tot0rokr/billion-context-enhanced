# State reconstruction: R2 and evidence batch 2

The explicit R2 revision applies to every batch, including previously
processed evidence. Retained events now execute by
`(board, epoch, sequence, event_id)`; wall-clock values never order state
transitions. A failed VERIFY for an existing pending transaction emits
`verify_failed` and clears that transaction's earlier verified flag. All
other R1 rules remain unchanged, including pending state across epochs,
exact image history, baseline initialization, and rejection precedence.

The earlier `audit/state-batch-1.md` records historical R1 results. It has
not been rewritten. This audit records current R2 results for batches 1 and
2 and the complete visible corpus. Event IDs are reconciled globally before
selecting case ranges; no excluded conflict row reaches the state machine.

## Current counts

| Scope | Boards | Retained events | Applied COMMIT | Accepted ROLLBACK | Transition incidents | Conflict incidents | All rejected events |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| INC-00001..INC-00064 | 64 | 510 | 54 | 5 | 149 | 12 | 161 |
| INC-00065..INC-00128 | 64 | 510 | 54 | 5 | 152 | 13 | 165 |
| Full visible corpus | 192 | 1,530 | 163 | 16 | 451 | 38 | 489 |

The complete corpus still has 384 duplicate replays and 38 conflicted IDs.
Final active slots are A/B on 22/42 boards in batch 1, 23/41 boards in batch
2, and 68/124 boards in the full corpus. These are contract reconstruction
results, not independent confirmation of physical device state.

The former R1 batch 1 had 13 applied commits and 258 total rejected events;
R2 has 54 and 161. The former full-corpus R1 totals were 30 applied commits
and 786 total rejected events; R2 has 163 and 489. Both revisions affect
these comparisons, so their deltas do not isolate either rule's effect.
Accepted rollback totals remain 5 for batch 1 and 16 for the full corpus.

| Action | Batch 1 accepted / attempts | Batch 2 accepted / attempts | Full accepted / attempts |
| --- | ---: | ---: | ---: |
| BASELINE | 64 / 64 | 64 / 64 | 192 / 192 |
| STAGE | 116 / 121 | 115 / 120 | 346 / 362 |
| VERIFY | 100 / 139 | 99 / 139 | 298 / 416 |
| COMMIT | 54 / 144 | 54 / 144 | 163 / 432 |
| RESET | 22 / 27 | 21 / 27 | 64 / 80 |
| ROLLBACK | 5 / 15 | 5 / 16 | 16 / 48 |

Reported successful COMMIT counts are 139, 138, and 416 for these scopes;
reported successful ROLLBACK counts are 10, 11, and 32. Reported success is
distinct from rule acceptance. Replays do not multiply attempts, and an
accepted operation need not change the active image.

| Transition rejection | Batch 1 | Batch 2 | Full |
| --- | ---: | ---: | ---: |
| commit_failed | 5 | 6 | 16 |
| commit_mismatch | 21 | 20 | 61 |
| commit_unverified | 25 | 25 | 74 |
| commit_without_stage | 39 | 39 | 118 |
| reset_failed | 5 | 6 | 16 |
| rollback_failed | 5 | 5 | 16 |
| rollback_unverified | 5 | 6 | 16 |
| stage_failed | 5 | 5 | 16 |
| verify_failed | 21 | 20 | 61 |
| verify_mismatch | 4 | 5 | 13 |
| verify_without_stage | 14 | 15 | 44 |

## Failed verification examples

`INC-00073`, epoch 0, executes these events in sequence order despite their
skewed timestamps:

| Event ID | Sequence | Diagnostic timestamp | Action | Accepted / reason |
| --- | ---: | ---: | --- | --- |
| board-00073-e001 | 7 | 1700448140 | STAGE | accepted |
| board-00073-e002 | 14 | 1700588623 | successful VERIFY | accepted |
| board-00073-e003 | 21 | 1700166156 | failed VERIFY | verify_failed |
| board-00073-e004 | 28 | 1700123774 | successful COMMIT | commit_unverified |

The failed VERIFY clears the earlier flag. The COMMIT still matches the
pending slot B and digest
`9f34b688a34586dba1bf3496755e91ae7ac51d0d875e6db37b29785b5bd4b2d8`,
but it cannot use that stale verification. Its reported `success=true` is
preserved in the trace alongside `accepted=false`. Epoch 1 also has a failed
VERIFY followed by `commit_unverified`; the board ends on its baseline A
image with zero accepted commits.

R2 also revises the earlier `INC-00001` reconstruction. Epoch 0 now executes
`board-00001-e001` STAGE, `board-00001-e002` successful VERIFY,
`board-00001-e003` failed VERIFY, then `board-00001-e004` COMMIT. The last
event now emits `commit_unverified`; under historical R1 timestamp ordering
it ran before STAGE and emitted `commit_without_stage`. This is a changed
explanation even though both reconstructions reject that COMMIT.

Failure takes precedence over image mismatch when a pending transaction
exists. Tests cover failed VERIFY with a different slot or digest: it clears
the flag and emits `verify_failed`. A subsequent matching successful VERIFY
can restore the flag. Earlier exact `(slot, digest)` history survives the
failure and still authorizes a matching rollback; it does not authorize the
same digest in another slot. Failure affects only its named transaction.

## Sequence ordering and unchanged epoch retention

`INC-00066` demonstrates skewed timestamps without a failed VERIFY. Epoch 0
STAGE `board-00066-e001` has timestamp `1700784678`, successful VERIFY
`board-00066-e002` has `1700346398`, and mismatching VERIFY
`board-00066-e003` has `1700197354`. R2 executes them by sequences 7, 14,
21. The successful verification is therefore followed by the mismatch that
clears its flag, and COMMIT `board-00066-e004` is `commit_unverified`.
In epoch 1, RESET `board-00066-e007` at sequence 49 clears pending state
before COMMIT `board-00066-e008` at sequence 56, even though the COMMIT's
timestamp `1700116331` is earlier than RESET's `1700861493`. That COMMIT is
`commit_without_stage`.

`INC-00074` demonstrates the unchanged epoch rule. Epoch 0 STAGE
`board-00074-e001` and VERIFY `board-00074-e002` authorize epoch 1 COMMIT
`board-00074-e003` without an intervening stage or verification. It applies
slot B and digest
`4a4f90bcd3c95e2f2208050a66de1b8b9446360fe7724b95fe04fa17e206a6f3`.
In epoch 2, STAGE `board-00074-e004` and VERIFY `board-00074-e005` precede
RESET `board-00074-e006`; COMMIT `board-00074-e007` then emits
`commit_without_stage`. The board keeps its epoch 1 image, and its accepted
commit count is one. R2 does not clear pending state merely because epoch
increases.

Earlier `INC-00002` has the same retained-epoch pattern. Its epoch 1 COMMIT
`board-00002-e003` remains accepted, while its epoch 2 RESET now executes
after STAGE and VERIFY and before COMMIT. Thus `board-00002-e007` changes
from an accepted R1 COMMIT to R2 `commit_without_stage`.

## Implementation and validation

`reconcile_states(events, *, trace=None)` and its return tuple are unchanged.
Trace records still come from the actual transitions, include both reported
success and acceptance, and omit timestamps. Baseline initialization remains
first per board. Only the ordering key and failed-VERIFY flag mutation changed
in transition logic; no second simulation or compatibility mode was added.

`python3 -m unittest discover -s tests -p test_state_machine.py -v` passes
21 tests. Revised tests cover sequence ordering despite clock skew and
failed-VERIFY invalidation. Added coverage includes event-ID ties with
opposing timestamps, matching/mismatching failed verification, later recovery,
exact image-history preservation, and transaction isolation. Existing epoch
retention, commit consumption, reset/rollback clearing, rejection precedence,
and trace contract tests still pass.

For all 1,530 retained events, negating every timestamp and shuffling input
with seed `20261106` produced exactly the same result and execution trace.
This checks that current state reconstruction is independent of wall-clock
values and input row order.
