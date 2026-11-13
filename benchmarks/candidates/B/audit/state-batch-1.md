# State reconstruction: evidence batch 1

Scope: `INC-00001` through `INC-00064`, corresponding to `board-00001`
through `board-00064` in `data/visible.jsonl`. Ingestion first reconciles
event IDs globally across the complete corpus; this audit then selects the
first 64 boards' retained events. R1 remains the authority. Evidence does
not revise ordering, epoch boundaries, or failed verification behavior.

## Accepted operations versus reported attempts

The 64 boards have 510 retained normalized events. Their transitions produce
246 rejection incidents, 13 applied commits, and 5 accepted rollbacks.
Conflict incidents belong to ingestion and are not included in these 246
transition incidents. Replayed rows and excluded conflict rows do not create
state-machine trace entries.

| Action | Retained attempts | Reported success | Accepted | Rejected |
| --- | ---: | ---: | ---: | ---: |
| BASELINE | 64 | 64 | 64 | 0 |
| STAGE | 121 | 116 | 116 | 5 |
| VERIFY | 139 | 117 | 44 | 95 |
| COMMIT | 144 | 139 | 13 | 131 |
| RESET | 27 | 22 | 22 | 5 |
| ROLLBACK | 15 | 10 | 5 | 10 |

A device's `success=true` is insufficient evidence that a COMMIT or ROLLBACK
was accepted. For example, 139 COMMIT attempts report success, but only 13
satisfy the staged image and verification checks. The final active slots are
A on 52 boards and B on 12 boards. These are R1 reconstruction results, not
independent assertions about physical device state.

Accepted COMMIT event IDs:

- `board-00002-e003`, `board-00002-e007`, `board-00013-e004`
- `board-00018-e008`, `board-00022-e008`, `board-00024-e004`
- `board-00026-e007`, `board-00032-e003`, `board-00036-e007`
- `board-00042-e004`, `board-00044-e003`, `board-00046-e004`
- `board-00064-e007`

Accepted ROLLBACK event IDs: `board-00009-e004`, `board-00021-e004`,
`board-00033-e004`, `board-00045-e004`, and `board-00057-e004`. All target
their board's verified baseline image in slot A. An accepted rollback can
leave the active image unchanged while still clearing pending transactions.

## Timestamp ordering observations

R1 initializes BASELINE first, then processes ascending epochs and ascending
timestamps within each epoch. Sequence is only a deterministic timestamp
tie-breaker. These examples therefore retain their surprising order:

- `INC-00001`: `board-00001-e004` is a successful COMMIT at sequence 28 and
  timestamp `1700134097`. It runs before `board-00001-e001`, the STAGE at
  sequence 7 and timestamp `1700258383`, so it emits `commit_without_stage`.
  BASELINE `board-00001-e000` initializes the image first even though its
  timestamp is `1700386160`. The later successful VERIFY cannot retroactively
  accept the earlier COMMIT.
- `INC-00013`: epoch 0 executes STAGE `board-00013-e001`, successful VERIFY
  `board-00013-e002`, COMMIT `board-00013-e004`, then failed VERIFY
  `board-00013-e003`. Their timestamps are respectively `1700033928`,
  `1700488530`, `1700659807`, and `1700866094`. The COMMIT is accepted and
  consumes its pending transaction; the later failed VERIFY emits
  `verify_without_stage`, which takes precedence over `verify_failed`.
- `INC-00002`: epoch 2 executes RESET `board-00002-e006` at `1700097406`
  before STAGE `board-00002-e004` at `1700330052`, despite sequences 42 and
  28. VERIFY `board-00002-e005` and COMMIT `board-00002-e007` then succeed.
  RESET did not erase that later STAGE.

## Pending state across epochs

`INC-00002` directly exercises R1 epoch retention. STAGE `board-00002-e001`
and successful VERIFY `board-00002-e002` establish `tx-02` in epoch 0 with
slot B and digest
`425d9a017781a7368369d5be02c6d0ff6d867bec5d9bcdb5fec75ae4d9a0e9c2`.
COMMIT `board-00002-e003` in epoch 1 is accepted without a new stage or
verification. Its timestamp `1700101898` is earlier than those epoch 0
events, but epoch ordering takes precedence. The accepted commit changes the
active image and removes only `tx-02`.

`INC-00001` also retains epoch 0 pending state into epoch 1. COMMIT
`board-00001-e007` requests digest
`4a002371431aa448c8fa9733ccb295f6901ffd4af4f4d808f58b65297ee8d142`
before the epoch 1 STAGE executes. The retained pending digest is instead
`161429e139929f2241c9ef22d79a33dcb9f2b1d41bd4d2108c0b4cb12fb0a1c9`,
so the rejection is `commit_mismatch`, not `commit_without_stage`.

## Failed verification preserves an earlier flag

In `INC-00001`, successful VERIFY `board-00001-e002` runs at `1700547933`
after its STAGE. Failed VERIFY `board-00001-e003` follows at `1700996892`
and emits `verify_failed`; R1 leaves that transaction's earlier verified
flag set. In epoch 1, failed VERIFY `board-00001-e006` again leaves the flag
unchanged even though its requested digest differs from pending state:
failure is checked before mismatch. Finally STAGE `board-00001-e005`
replaces the pending image and clears the flag.

No later matching COMMIT in this example exercises the preserved flag, so
the evidence does not demonstrate an accepted commit caused by that flag.
The focused state test separately verifies R1's specified consequence:
STAGE, successful VERIFY, failed VERIFY, matching COMMIT applies the commit.
No change to this provisional rule has been inferred from the evidence.

## Trace API and verification

`reconcile_states(events, *, trace=None)` preserves its existing return
value. Passing a list appends fresh records for every retained event in
actual execution order, with BASELINE first per board. Records include the
canonical event identity and request, reported `success`, rule-derived
`accepted`, rejection `reason`, and active slot/digest before and after.
Accepted events have `reason=null`. Timestamps are absent. Trace generation
uses the same transitions and rejection decisions as normal reconciliation;
there is no independent replay engine.

`python3 -m unittest discover -s tests -p test_state_machine.py -v` passes
17 tests, including all 14 existing R1 tests. Added coverage checks reported
success versus acceptance, rejected commits leaving the active image intact,
accepted commit/rollback counters, baseline-first trace ordering, exact trace
fields, append-only behavior, independent records, failed VERIFY flag
preservation, missing baseline behavior, empty input, and unchanged results
with or without tracing.
