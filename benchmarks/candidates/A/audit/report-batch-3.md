# Evidence batch 3 audit findings — R3

Cases `INC-00129` through `INC-00192` correspond to `board-00129` through
`board-00192` in `data/visible.jsonl`. The explicit R3 contract applies to all
batches. Advancing to a new epoch clears every pending transaction before its
first retained event executes, regardless of that event's reported success.
The active image and exact `(slot, digest)` verification history survive.

R2's sequence ordering and failed-VERIFY flag clearing remain in force.
Wall-clock timestamps never affect execution. Rollback requires an exact
verified slot/digest pair; a digest known only in another slot is insufficient.

## Reconciliation

The batch contains 664 transport rows: 510 retained events, 128 equivalent
replay rows, and 26 excluded rows belonging to 13 conflicting IDs. R3 applies
51 commits and accepts 6 rollbacks across 64 boards. There are 154 transition
rejections plus 13 duplicate-conflict incidents, for 167 total incidents.

| Action | Retained attempts | Reported success | Accepted | Rejected |
| --- | ---: | ---: | ---: | ---: |
| BASELINE | 64 | 64 | 64 | 0 |
| COMMIT | 144 | 139 | 51 | 93 |
| RESET | 26 | 21 | 21 | 5 |
| ROLLBACK | 17 | 11 | 6 | 11 |
| STAGE | 121 | 115 | 115 | 6 |
| VERIFY | 138 | 117 | 99 | 39 |

Reported success remains distinct from acceptance. The 93 rejected COMMIT
attempts comprise 44 `commit_without_stage`, 24 `commit_unverified`,
20 `commit_mismatch`, and 5 `commit_failed` incidents. Replayed and conflicted
transport rows do not count as retained action attempts.

The execution trace contains 69 epoch advances, including 12 that clear
nonempty pending state. For example, `board-00133-e005` clears a pending
transaction on entering epoch 1 and then stages a replacement image. Its audit
shows the old pending state, the empty state after epoch clearing, and the new
stage separately. No first event that clears nonempty pending state in this
batch reports failure; dedicated regression tests cover that required case.

`board-00140-e004` is rejected as `rollback_unverified`: its digest is present
in verified history for another slot, so it does not authorize the requested
slot. Epoch advancement never broadens rollback authorization.

## Audit and corrected reporting notes

The separate audit is tagged `R3`. Every transition now includes
`epoch_before`, `epoch_advanced`, and `pending_after_epoch`. `pending_before`
captures state before automatic epoch clearing; `pending_after_epoch` captures
state after clearing but before the action; `pending_after` captures the result
of the action. Statements that a failed action leaves state unchanged refer to
the state after epoch processing. The reason catalog makes this distinction
explicit. Ordinary reports retain exactly `boards`, `incidents`, and `totals`.

`operations-notes.json` holds exactly one current record for each known note.
F01–F08 now use the user's corrected values; their old values are invalid.
`operations-corrections.json` preserves those eight replacements as historical
records with invalidated and current values and `status: superseded`.
F09–F32 remain unchanged. New F33–F48 values map OPS-033/F33 to `INC-00129`
through OPS-048/F48 to `INC-00144`. All values remain exact strings and are
reporting data only; neither current nor invalidated notes authorize actions.

Eleven audit tests pass under R3. Coverage includes automatic clearing before
a failed first event, the precedence of missing stage for failed VERIFY after
epoch clearing, independent snapshots for the three pending-state stages,
history retention with exact-slot rollback checks, clock invariance,
transport/action accounting, exact current 48 notes, and the correction ledger.
Known-note checks permit future appended records while enforcing unique active
note and operation IDs.

No report/audit implementation tasks remain for this batch. Current findings
must use R3 for every batch; archived R1 and R2 findings describe superseded
contracts. No further semantic changes are inferred from the evidence or notes.
