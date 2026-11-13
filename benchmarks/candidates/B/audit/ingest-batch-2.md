# Evidence batch 2: ingest/schema audit under R2

R2 applies to all batches: retained events execute in
`(board, epoch, sequence, event_id)` order, never wall-clock order, and a
failed VERIFY clears an existing pending transaction's verified flag.
The VERIFY change belongs to the state machine. The historical batch 1
audit remains unchanged; R2 supersedes its timing-related interpretation.

Ingest identity and global conflict semantics remain unchanged. The minimum
reported replay timestamp is retained only as inert metadata; it must never
affect event ordering or state. `ingest.py` already sorts retained events by
the R2 key, and its documentation now states these rules explicitly.

| Metric | Cases 65–128 | Full visible corpus |
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

All 64 replay groups in batch 2 have three rows with two reported timestamps
and equivalent normalized payloads. For example, `board-00128-e006` is a
successful VERIFY at epoch 1, sequence 42, transaction `tx-11`, slot B.
Its timestamps are `1700076085`, `1700076085`, and `1900000000`; the first
value survives solely as metadata. The group contributes two replays and
no conflict.

Batch 2's 13 conflicts occur at e001 on every fifth board, from
`board-00065-e001` through `board-00125-e001`. Each pair differs only in
digest among normalized payload fields. `board-00065-e001`, epoch 0,
sequence 7, is a successful STAGE for transaction `tx-00`, slot B with
conflicting digests
`e98bfba975875302e49f00d858b88d90efb43abbbc83c43518d0c5f3c2e16eed`
and `d992d8de03bd9009a0dd0b1ff21bec3d1e43124e9517c39499137bcc09c3cbb7`.
Both rows are excluded, exactly one duplicate-conflict incident is emitted,
and the pair contributes no duplicate replay count. Full-corpus replay and
conflict totals remain the same as the batch 1 audit.

Both scopes retain canonical R2 ordering and identical results after input
reversal or a shuffle with seed 17. A new full-corpus regression rewrites
every reported timestamp and confirms that all retained payloads, their
order, conflict incidents, and counters stay identical; only inert timestamp
metadata can differ. A synthetic regression covers every part of the R2
ordering key, including equal-sequence event-ID ties, against contradictory
timestamps. Batch 2 count, conflict-removal, and concrete replay checks were
also added. All 14 ingest tests pass with
`python3 -m unittest discover -s tests -p test_ingest.py -v`.

Carry forward: no unresolved ingest defect or requested identity change.
Timestamp metadata must remain excluded from identity, execution ordering,
state transitions, and final report fields in future phases.
