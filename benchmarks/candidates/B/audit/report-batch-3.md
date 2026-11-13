# Batch 3 report and audit decisions

R3 applies to all evidence batches. A board's boot epoch advance clears every
pending transaction before processing the first event of the new epoch. The
active image and board-local verified image history survive. Retained event
ordering remains `(board, epoch, sequence, event_id)` without timestamp input;
failed VERIFY still clears the existing pending transaction's verified flag.

New sidecars identify `contract_revision: R3`; the builder rejects other labels.
Historical batch 1 and batch 2 audit notes and archived reports retain their
original meanings. Current sidecar reason explanations explicitly describe
epoch clearing for `verify_without_stage` and `commit_without_stage`, without
claiming that epoch clearing caused every occurrence of those reasons. A failed
RESET does not itself clear pending transactions, but any epoch advance has
already cleared them before that action executes.

Rollback authorization requires the exact `(slot, digest)` pair in that board's
verified image history. A digest previously verified on slot A does not authorize
slot B. The history survives reboot and failed verification; neither retaining
the history nor retaining the active image retains pending transactions.
`rollback_unverified` now explains both the exact pair requirement and persistent
history. The same twelve reason names remain in use.

The primary report and sidecar event schemas are unchanged. Audit events follow
actual execution order and contain no timestamps, paths, or runtime metadata.
COMMIT/ROLLBACK attempted and reported-success counts cover retained events only;
accepted counts come directly from state decisions. Excluded ID conflicts and
discarded replay rows contribute no attempts. Acceptance is independent of
whether the selected image differs from the active image. Operational notes
remain audit evidence and do not revise the transition rules.

Validation against the visible corpus after the R3 state changes produced the
following observed counts. Operation cells list attempted / reported successful
/ accepted; these observations are not an independent correctness oracle.

| Scope | Retained trace rows | COMMIT | ROLLBACK | Rejected events |
| --- | ---: | ---: | ---: | ---: |
| Batch 1, boards 1–64 | 510 | 144 / 139 / 49 | 15 / 10 / 5 | 166 |
| Batch 2, boards 65–128 | 510 | 144 / 138 / 50 | 16 / 11 / 5 | 169 |
| Batch 3, boards 129–192 | 510 | 144 / 139 / 51 | 17 / 11 / 6 | 167 |
| All 192 boards | 1530 | 432 / 416 / 150 | 48 / 32 / 16 | 502 |

For every scope, accepted COMMIT and ROLLBACK counts match the primary totals;
rejected trace rows plus conflict incidents match `rejected_events`; explanation
keys match exactly the report's incident reasons; and the trace follows the
retained-event ordering. Across all 192 boards, R3 has 150 accepted commits
compared with R2's 163, and 502 incidents compared with 489. Accepted rollbacks
remain 16. All 384 duplicate replays and 38 conflicted IDs remain excluded from
operation attempts under the unchanged ingestion rules.
