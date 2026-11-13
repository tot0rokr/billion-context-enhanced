# State-machine audit: evidence batch 3 and R3

The explicit R3 revision applies to all evidence batches. Advancing a board's
epoch clears every pending transaction before processing the first retained
event in the new epoch. The active image and exact `(slot, digest)` verification
history survive. R2's sequence/event-ID ordering, ignored clocks, and failed-
VERIFY flag revocation remain in force. Exact-slot rollback authorization was
already implemented and is now explicitly reaffirmed.

Historical R2 outcomes and the superseded pending-preservation decision are in
`history/r2/state-batch-2.md`. Operational notes remain reporting data; the
explicit R3 instruction supplies the new epoch rule.

## Implementation and audit semantics

The existing engine applies automatic epoch clearing before every action,
including failed actions, and across gaps between retained epochs. No excluded
conflict row reaches the engine or advances its epoch. Reusing a transaction ID
after a boundary requires a fresh stage and matching successful verification.
Remaining in the same epoch does not itself clear pending state.

One trace record remains associated with each retained event. It now includes:

- `epoch_before`: the board's epoch before this event; the first event starts
  with its own epoch.
- `epoch_advanced`: whether this event starts a strictly higher epoch; false
  for the first retained event on each board.
- `pending_before`: the pending transactions before any automatic clearing.
- `pending_after_epoch`: the state after epoch clearing and before the action.
- `pending_after`: the state after the action.

The three pending lists are independent snapshots, collected only when audit
is requested. A new-epoch STAGE can show old pending state, an empty intermediate
list, and a fresh unverified transaction after the action. A new-epoch failure
can show pending cleared even though the action is rejected. Failed VERIFY
after such a clear reports `verify_without_stage`, preserving the established
missing-stage precedence. Active-image snapshots retain their prior semantics.

## R3 results and comparison with R2

Computed after globally reconciling all IDs in `data/visible.jsonl`, then
selecting each board range. These are contract-derived results, not independently
supplied expected reports. All batches retain 510 events on 64 boards each.

| Scope | R2 commits | R3 commits | Rollbacks under both | R2 incidents | R3 incidents |
| --- | ---: | ---: | ---: | ---: | ---: |
| Cases 1–64 | 54 | 49 | 5 | 161 | 166 |
| Cases 65–128 | 54 | 50 | 5 | 165 | 169 |
| Cases 129–192 | 55 | 51 | 6 | 163 | 167 |
| All 192 cases | 163 | 150 | 16 | 489 | 502 |

The full R3 report has 464 transition incidents plus 38 duplicate conflicts.
The 13 formerly accepted cross-epoch commits now reject with
`commit_without_stage`; 13 final active images change accordingly. Replay and
conflict accounting are unchanged.

| Scope | Epoch advances | Advances clearing nonempty pending | Pending transactions cleared |
| --- | ---: | ---: | ---: |
| Cases 1–64 | 70 | 14 | 14 |
| Cases 65–128 | 69 | 13 | 13 |
| Cases 129–192 | 69 | 12 | 12 |
| All 192 cases | 208 | 39 | 39 |

The supplied fixture has one pending transaction at each nonempty boundary;
focused tests separately exercise simultaneous named and null transaction IDs.

## Cases 129–192

| Action | Retained attempts | Reported success | Accepted |
| --- | ---: | ---: | ---: |
| BASELINE | 64 | 64 | 64 |
| STAGE | 121 | 115 | 115 |
| VERIFY | 138 | 117 | 99 |
| COMMIT | 144 | 139 | 51 |
| RESET | 26 | 21 | 21 |
| ROLLBACK | 17 | 11 | 6 |

The 93 rejected commits comprise 44 without stage, 24 unverified, 20 mismatched,
and 5 reported failures. The batch has 154 transition incidents and 13 global
duplicate-conflict incidents.

Commits `e003` on boards 00134, 00146, 00158, and 00182 now reject after clearing
their verified epoch-0 pending transaction on entry to epoch 1. Their traces
show `epoch_before=0`, `epoch=1`, `epoch_advanced=true`, a previously verified
transaction in `pending_before`, and empty `pending_after_epoch`/`pending_after`.
The equivalent earlier cases are boards 00002, 00014, 00026, 00038, 00062,
00074, 00086, 00098, and 00122.

Rollbacks `e004` on boards 00129, 00141, 00153, 00165, 00177, and 00189 remain
accepted. Five other rollback attempts reject as `rollback_unverified`, and six
report `rollback_failed`. Authorization uses exact slot and digest in that
board's history; another slot or another board cannot supply it.

## Validation and remaining work

All 17 focused state-machine tests pass. New and revised tests cover multiple
pending transactions including a null ID, skipped epochs, every failing action
as the first new-epoch event, fresh stage/verification requirements, same-epoch
retention, distinct boundary snapshots, unchanged active image on clearing,
and exact rollback history across epochs with board isolation. Existing clock
independence, event-ID ordering, verification revocation, and audit-equivalence
tests continue to pass.

Across all 1,530 fixture transition records, every epoch advance has empty
`pending_after_epoch`, every non-advance has matching before/intermediate state,
and reconstruction with and without trace collection returns identical results.

No state-machine implementation task remains for this phase. The parent owns
integrated validation and artifact regeneration. Unchanged interpretation points
are missing-baseline fallback after conflict removal and failed-VERIFY
missing-stage precedence.
