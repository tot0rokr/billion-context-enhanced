# Evidence batch 3: ingestion under R3

Scope: cases INC-00129 through INC-00192, corresponding to `board-00129`
through `board-00192`, plus a final whole-corpus ingestion audit.

## Contract and implementation decisions

R3 applies to every batch. Advancing the boot epoch clears all pending
transactions while retaining the active image and exact verified-image history.
Rollback authorization requires the exact `(slot, digest)` pair. R2 location
ordering, complete clock independence, and failed-VERIFY flag revocation remain
in force. The state-machine role implements epoch clearing; ingestion must
exclude every conflicted global ID before any event can affect board state.

No ingestion production change was needed. The existing nine-field normalized
payload includes both slot and digest, and its global conflict classification
already precedes state reconstruction. Thirteen ingestion tests now pass, with
three additional regressions checking:

- An ID repeated across epochs is a global conflict, all its rows contribute
  zero replays, and its incident uses the minimum board/epoch/sequence/ID even
  when a smaller location arrives after the conflict was discovered.
- A discarded future-epoch copy cannot advance the reconstructed board epoch;
  discarded STAGE copies cannot supply pending state to a later VERIFY/COMMIT.
- Changing only the slot with the same digest, or only the digest with the same
  slot, makes the normalized payload different across schema spellings.

## Transport findings

| Measure | Batch 3 | Full corpus |
| --- | ---: | ---: |
| Boards | 64 | 192 |
| Transport rows | 664 | 1,990 |
| Schema 1 rows | 335 | 1,004 |
| Schema 2 rows | 329 | 986 |
| Global event IDs | 523 | 1,568 |
| Retained IDs | 510 | 1,530 |
| Duplicate replay rows | 128 | 384 |
| Conflicted IDs | 13 | 38 |
| Rows excluded by conflicts | 26 | 76 |
| Singleton ID groups | 446 | 1,338 |
| Three-row replay groups | 64 | 192 |
| Two-row conflict groups | 13 | 38 |
| Mixed-schema equivalent ID groups | 64 | 192 |
| Mixed-schema conflicted ID groups | 10 | 31 |

No global ID crosses a 64-board batch boundary. In the supplied corpus, all 38
conflicts differ only in digest; none crosses boards or epochs. The new
cross-epoch and slot-distinction tests therefore cover contract requirements
not exercised by those concrete conflict rows.

An independent raw-field payload grouping agrees with normalization, all
conflict classifications, canonical conflict locations, and replay counts for
batch 3 and the full corpus. Every ID has exactly one transport-audit record,
conflicted IDs are absent from retained events, and all retained events have
exactly the nine clock-free payload fields in canonical location order. Input
rows remain unchanged. Accounting balances:

- Batch 3: `510 retained + 128 replay rows + 26 excluded rows = 664 rows`.
- Full corpus: `1,530 retained + 384 replay rows + 76 excluded rows = 1,990 rows`.

For both scopes, original input, reversed input, and 20 seeded shuffles produce
identical ingestion results and transport audits. Removing clocks or replacing
them with arbitrary JSON arrays/objects also leaves all results unchanged.

## Carry forward

No ingestion defects, failing ingestion tests, or unfinished ingestion tasks
remain. Contract-derived corpus accounting is supported by independent grouping;
it is not an external oracle for state transitions. Parent integration owns
the regenerated R3 primary/audit artifacts and complete public-test results.
