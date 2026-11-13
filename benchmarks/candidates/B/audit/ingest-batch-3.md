# Evidence batch 3: ingest/schema audit under R3

R3 clears pending transactions on epoch advance while retaining active image
and verified image history. Rollback authorization requires the exact
`(slot, digest)` pair. R2 canonical ordering and failed-VERIFY invalidation
remain in force. These state rules do not change normalization, global ID
identity, replay counting, or conflict exclusion. No ingest defect was found;
`ingest.py` required no changes in this phase.

| Metric | Cases 129–192 | Full visible corpus |
| --- | ---: | ---: |
| Boards | 64 | 192 |
| Input rows | 664 | 1,990 |
| Schema 1 rows | 335 | 1,004 |
| Schema 2 rows | 329 | 986 |
| Distinct event IDs | 523 | 1,568 |
| Retained events | 510 | 1,530 |
| Identical-payload replay groups | 64 | 192 |
| Counted duplicate replays | 128 | 384 |
| Conflicted IDs / duplicate-conflict incidents | 13 | 38 |
| Excluded rows belonging to conflicted IDs | 26 | 76 |

Every batch 3 replay group contains three rows spanning both schemas and
two reported timestamps, with one normalized payload. For example,
`board-00129-e006` is a failed VERIFY at epoch 1, sequence 42, slot B.
Its timestamps are `1700239406`, `1900000000`, and `1700239406`. Ingest
retains one event and counts two duplicate replays. The retained minimum
timestamp, `1700239406`, remains inert metadata and cannot affect ordering
or state.

All 13 batch 3 conflicts consist of two rows differing only in digest among
the normalized payload fields. They occur at e001 on every fifth board
from `board-00130-e001` through `board-00190-e001`. For example,
`board-00130-e001` at epoch 0, sequence 7 contains digests
`10976353912d09dbfd40adafc2c5882f5b652a0db5b2d19f91a69eb58b6945d9`
and `037931928ae223de21d14cc4d996cd1398f99eadba125015c818bb2c6dc6dad7`.
Both rows are excluded, one duplicate-conflict incident is emitted, and
neither row increases duplicate replay counts. The corpus has no event ID
spanning multiple boards; synthetic tests continue to cover that global
identity case and minimum-location selection.

Batch 3 and full-corpus ingestion are unchanged by input reversal and a
shuffle with seed 17. Existing corpus tests now explicitly check all three
batches' counts, conflicting-ID removal, and permutation invariance. The
concrete batch 3 replay above is covered alongside the batch 2 example.
All 14 ingest tests pass with
`python3 -m unittest discover -s tests -p test_ingest.py -v`; the suite also
retains full-corpus timestamp-rewrite invariance and canonical-order checks.

Carry forward: normalization and global duplicate semantics remain stable
under R3. No ingest task remains unfinished. Historical batch 1 and batch 2
audit notes are preserved; current state-transition authority is R3.
