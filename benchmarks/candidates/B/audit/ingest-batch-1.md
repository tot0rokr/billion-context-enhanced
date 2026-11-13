# Evidence batch 1: ingest/schema audit

R1 remains the governing contract. INC-00001 through INC-00064 map to
`board-00001` through `board-00064` in `data/visible.jsonl`. No ingest bug or
contract revision was found; `ingest.py` is unchanged in this phase.

| Metric | First 64 boards | Full visible corpus |
| --- | ---: | ---: |
| Boards | 64 | 192 |
| Input rows | 662 | 1,990 |
| Schema 1 rows | 334 | 1,004 |
| Schema 2 rows | 328 | 986 |
| Distinct event IDs | 522 | 1,568 |
| Retained events | 510 | 1,530 |
| Identical-payload replay groups | 64 | 192 |
| Counted duplicate replays | 128 | 384 |
| Conflicted IDs / duplicate-conflict incidents | 12 | 38 |
| Excluded rows belonging to conflicted IDs | 24 | 76 |

Every board has one three-row replay group: both schema spellings occur,
the normalized payload is identical, and there are two distinct reported
timestamps. Each group contributes two duplicate replays. For example,
`board-00001-e006` is the same failed VERIFY for epoch 1, sequence 42,
transaction `tx-01`, slot B in all three rows. Its timestamps are
`1700702820`, `1700702820`, and `1900000000`. The retained timestamp is
`1700702820`, following the existing provisional minimum-timestamp policy.
Schema spelling and timestamp variation do not create conflicts.

All conflicts have exactly two rows and differ only in digest among the
normalized payload fields. They occur at the e001 STAGE event of every
fifth board: `board-00005-e001` through `board-00060-e001` in batch 1,
and through `board-00190-e001` in the full corpus. Both rows of each ID
are discarded, one duplicate-conflict incident is placed at epoch 0,
sequence 7, and neither row contributes to duplicate replay counts.
For `board-00005-e001`, the conflicting digests are
`a99ec0760b09abfa699322c94319d4cc9d2d7d2451ca26f377196c09cea60cd6`
and `6edc28a52b77f51377b9c64a53ca57bdc121c8d262d5a5d9f0994a0174877eeb`.

No event ID spans multiple boards in the supplied corpus. The pre-existing
synthetic regression continues to cover global cross-board conflict
resolution and minimum-location selection. No supplied row omits tx,
slot, or digest (or their schema 2 equivalents); existing synthetic tests
cover their normalization to null when absent.

Both scopes yield exactly identical ingestion results after reversal and
after a shuffle with random seed 17. Corpus regressions cover the counts,
the concrete timestamp/schema replay above, discarded conflicting stages,
and full-corpus input-order invariance. All 11 ingest tests pass with
`python3 -m unittest discover -s tests -p test_ingest.py -v`.

Carry forward: minimum reported timestamp remains a provisional replay
selection policy. Future explicit contract revisions may change it;
working incident evidence alone does not. Execution ordering and rollout
state transitions remain outside this ingest audit's scope.
