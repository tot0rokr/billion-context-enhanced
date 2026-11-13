# Evidence batch 1: ingestion

Scope: the first 64 lexically sorted board IDs in `data/visible.jsonl`,
`board-00001` through `board-00064`. No event ID in this batch also occurs on a
board outside the batch, so filtering this batch does not truncate global ID
groups. README R1 and the existing phase decisions remain authoritative.

## Changes and checks

`ingest_events(raw_events, *, audit=None)` preserves its existing return value.
It now keeps one representative per ID and discards payload storage once an ID
conflicts. Repeated identical rows no longer accumulate in memory. The optional
caller list receives one record per ID in canonical location order, containing
only location, retained/conflict status, total transport rows, and replay count.
Conflicted IDs still contribute zero replay rows, regardless of repeated copies.

Nine ingestion tests pass, including cross-schema normalization, optional nulls,
minimum replay timestamp, global conflicts, transport audit ordering/counts,
generator input, and conflicts followed by further identical replays. No
ingestion classification bug was found. A `tracemalloc` check using a generated
single-ID replay stream reported the same peak tracked allocation (370,874
bytes) for 10,000 and 100,000 rows; these observations are environment-specific,
not a test threshold.

## Observations

| Measure | Count |
| --- | ---: |
| Boards | 64 |
| Transport rows | 662 |
| Schema 1 / schema 2 rows | 334 / 328 |
| Global event IDs | 522 |
| Retained IDs | 510 |
| Duplicate replay rows | 128 |
| Conflicted IDs | 12 |
| Transport rows belonging to conflicted IDs | 24 |
| ID groups with one / two / three rows | 446 / 12 / 64 |
| IDs represented in both schemas | 74 |
| Mixed-schema IDs with identical normalized payloads | 64 |
| Mixed-schema conflicted IDs | 10 |
| Retained replay groups whose timestamps disagree | 64 |

The audit transport-row sum is exactly 662, and its replay sum is exactly 128.
Original input, reversed input, and 20 seeded shuffles produce identical
accepted events, canonical conflict incidents, counters, and transport audits.

Timestamp diagnostics use retained representatives and exclude baselines when
comparing event order. Timestamp order differs from sequence order in 115
board/epoch groups, affecting all 64 boards. Sequence-sorted events contain 159
adjacent timestamp regressions. No nonbaseline board/epoch group has timestamp
ties. On 50 boards the retained baseline timestamp is later than another retained
event in its epoch; existing baseline-first initialization remains in force.

## Carry forward

Timestamp disagreements and sequence inversions are evidence, not an explicit
revision of R1. Timestamp ordering and the minimum-timestamp replay
representative remain unchanged until an explicit revision arrives. No new
ingestion issues remain open; parent integration and state/report findings are
tracked separately.
