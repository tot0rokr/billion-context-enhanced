# State-machine audit: evidence batch 1

Authority remains README.md provisional R1. The INC-00001 through INC-00064
evidence and OPS-004/OPS-012 `forbidden_operator_action` text do not explicitly
revise execution rules. Operational metadata is evidence for reporting only.

## Implementation

`state_machine.reconstruct(events, *, audit=None)` keeps its existing return
value. A supplied list receives per-event transition records in actual board
execution order, including the successful baseline first regardless of clock
order. The default call does not capture state snapshots. Both paths use the
same transition engine.

Each record distinguishes `reported_success` from the reconciler's `outcome`
(`accepted`, `rejected`, or `ignored`), includes the prescribed rejection reason,
and provides independent active-image and sorted pending-transaction snapshots.
Null transaction IDs sort before string IDs. `verified_image_added` reports a
new exact `(slot, digest)` history entry; repeated verification is accepted but
does not add another history entry. Successful baseline adds the initial image.
An accepted COMMIT increments the counter and consumes the transaction even
when it leaves the active image unchanged. A rejected VERIFY mismatch can clear
the pending verified flag, and that mutation appears in its snapshots.

## Observed first-64 outcomes

Computed from the whole fixture's global ID reconciliation, then scoped to
`board-00001` through `board-00064`. These are R1 reconstruction results, not an
independent ground-truth oracle.

| Observation | Count |
| --- | ---: |
| Retained normalized events | 510 |
| Applied commits | 13 |
| Accepted rollbacks | 5 |
| Transition incidents | 246 |
| Canonical duplicate-conflict incidents in scope | 12 |
| COMMIT attempts | 144 |
| COMMIT attempts reporting success | 139 |
| COMMIT attempts accepted | 13 |
| COMMIT rejected: without stage | 72 |
| COMMIT rejected: mismatch | 28 |
| COMMIT rejected: unverified | 26 |
| COMMIT rejected: reported failure | 5 |

All 64 boards have at least one epoch where timestamp execution order differs
from ascending sequence order. R1 still requires timestamp order. In particular,
`board-00001-e004` executes before its stage and rejects with
`commit_without_stage`, despite its later sequence number.

`board-00002-e003` applies in epoch 1 using stage `e001` and verification `e002`
from epoch 0. This follows R1's explicit pending-state preservation across epoch
changes. Old-epoch verification reuse cannot be prohibited by interpretation of
an operational metadata value; that would require an explicit contract revision.

Failed VERIFY preserves a true pending flag at `board-00001-e003`,
`board-00001-e006`, and `board-00033-e006`. Successful mismatched VERIFY clears a
true flag at `board-00004-e006`, `board-00008-e006`, `board-00012-e006`,
`board-00034-e006`, and `board-00047-e006`. Historical verification remains
available for exact-image rollback in both cases, as R1 specifies.

The accepted rollbacks are `e004` on boards 00009, 00021, 00033, 00045, and 00057.
The 13 accepted commits are: 00002/e003, 00002/e007, 00013/e004, 00018/e008,
00022/e008, 00024/e004, 00026/e007, 00032/e003, 00036/e007, 00042/e004,
00044/e003, 00046/e004, and 00064/e007.

## Validation and open interpretation points

All 12 focused state-machine tests pass. New checks establish unchanged return
values with audit enabled, no snapshot collection without audit, independent
snapshots, null-ID ordering, baseline-first trace order, accepted-versus-reported
success distinctions, and verification-history addition semantics.

No state-machine implementation task remains open for this batch. The earlier
R1 interpretation points remain revisable: minimum replay timestamp chosen by
ingestion, baseline initialization before clocks, missing-baseline fallback, and
failed-VERIFY-without-stage precedence. No explicit revision was applied.
