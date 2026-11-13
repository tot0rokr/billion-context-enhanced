# Evidence batch 2: ingestion under R2

Scope: cases INC-00065 through INC-00128, corresponding to `board-00065`
through `board-00128`. The explicit R2 revision applies retroactively to every
batch, including batch 1. Historical R1 findings remain in the earlier note.

## Explicit decisions

- Retained events use `(board, epoch, sequence, event_id)` ordering. Reported
  clocks are deliberately skewed and never determine identity, representative
  selection, or execution order.
- Normalization now returns exactly nine payload fields: `event_id`, `board`,
  `epoch`, `sequence`, `action`, `tx`, `slot`, `digest`, and `success`. It does
  not read `time` or `timestamp`; missing or incomparable clock values therefore
  have no effect. The earlier minimum-timestamp representative policy is
  superseded.
- Global conflict exclusion, minimum conflict location, replay counts, optional
  null fields, streaming memory behavior, and the transport audit are unchanged.
- R2 also requires failed VERIFY with an existing pending transaction to clear
  its previous verified flag. The state-machine role implements that revision;
  ingestion does not interpret transaction state. Other rules remain unchanged.

## Accounting

| Measure | Batch 1 | Batch 2 | Boards 129–192 | Full corpus |
| --- | ---: | ---: | ---: | ---: |
| Boards | 64 | 64 | 64 | 192 |
| Transport rows | 662 | 664 | 664 | 1,990 |
| Global event IDs | 522 | 523 | 523 | 1,568 |
| Retained IDs | 510 | 510 | 510 | 1,530 |
| Duplicate replay rows | 128 | 128 | 128 | 384 |
| Conflicted IDs | 12 | 13 | 13 | 38 |
| Transport rows excluded by conflicts | 24 | 26 | 26 | 76 |

Boards 129–192 are included only to check whole-corpus transport accounting.
No state-machine conclusions about that later evidence batch are implied.

Batch 2 contains 335 schema-1 and 329 schema-2 rows. Its ID groups consist of
446 singletons, 64 three-row replay groups, and 13 two-row conflict groups.
Of 75 mixed-schema ID groups, 64 have equivalent normalized payloads and 11
conflict. None of the corpus's global event IDs cross the 64-board batch
boundaries, so batch selection does not truncate any replay or conflict group.

For every batch and the full corpus, an independent raw-field payload grouping
agrees with the implementation's replay and conflict counts. Each transport
audit has one record per global ID, transport-row sums match input row counts,
and `retained IDs + replay rows + conflicted transport rows = input rows`.
Batch totals sum exactly to full-corpus totals. R2 does not change these counts.

## Validation and carry forward

Ten ingestion tests pass. They cover the exact normalized schema, missing and
incomparable clocks, canonical location ordering including event-ID tie breaks,
generator replay input, global conflict persistence, and deterministic audit
counts. For batch 2, original input, reversed input, and 20 seeded shuffles
produce identical accepted events, incidents, counters, and transport audits.
Removing all clock fields or replacing them with arbitrary JSON objects and
arrays also produces identical results.

No ingestion work remains unfinished. Parent integration regenerates earlier
batch reports and audits using R2 and records the combined verification results.
