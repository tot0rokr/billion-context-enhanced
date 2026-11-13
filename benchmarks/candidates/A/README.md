# Rollout incident reconstruction

Use Python standard library only. Implement the CLI in reconcile.py.
Later user messages may revise this contract. Latest explicit
revision wins; record the revised decisions while working.

## Current contract R3

R3 applies to every evidence batch. Advancing boot epoch clears all pending
transactions while retaining the active image and verified-image history.
Rollback authorization requires the exact (slot,digest) pair. R2's sequence
ordering and failed-VERIFY flag clearing remain in force. Historical decisions
and results are retained in `PHASE_NOTES.md` and `audit/history/`.

Normalize schema 1 and 2 before reasoning. Schema 1 keys: event_id, board,
epoch, sequence, action, tx, slot (0=A, 1=B), digest, success, time.
Schema 2 keys: id, device, boot, seq, kind (lowercase action), transaction,
slot (A or B), sha256, ok, timestamp. Ignore time/timestamp during normalization
and reconciliation; clocks are deliberately skewed.
Missing tx, slot, digest normalize to null. success/ok is always boolean.

Group by event ID globally. Identical normalized payloads are replays: keep
one and count the extra rows in duplicate_replays. If one ID has multiple
different normalized payloads, exclude ALL rows for that ID, count one
conflicted_id, and emit one duplicate_conflict incident using the minimum
(board, epoch, sequence, event_id) location among those payloads. Do not
count rows of a conflicted ID as duplicate_replays. Ignored timestamp and
schema spelling differences do not make normalized payloads different.

Order retained events by (board, epoch, sequence, event_id), never wall-clock time.
Each board has one successful BASELINE before its other events: set active
slot/digest and add that exact image to verified image history. Initial
epoch is the baseline epoch. Before processing the first retained event in a
higher epoch, clear all pending tx state, retaining the active image and verified
image history. This happens regardless of the event's action or success flag.
A successful RESET
also clears pending state without changing the active image. A failed
RESET emits reset_failed and does not clear pending state.

STAGE failure emits stage_failed and leaves pending state unchanged.
STAGE success replaces that tx's pending slot/digest and clears its verified
flag. VERIFY without a pending tx emits verify_without_stage. A failed VERIFY
of an existing pending transaction emits verify_failed and clears its prior
verified flag, retaining its slot/digest and the board's verified image history.
Successful VERIFY for a different slot or digest emits
verify_mismatch AND clears its verified flag. Matching successful VERIFY
sets verified=true and adds the exact (slot,digest) to verified history.

Failed COMMIT always emits commit_failed. Successful COMMIT without a
pending tx emits commit_without_stage. Successful COMMIT whose slot/digest
does not match pending emits commit_mismatch. A matching COMMIT without
the verified flag emits commit_unverified. Otherwise change active image,
increment applied_commits, and remove the pending tx. Thus a second commit
needs a new stage/verification. Incidents do not otherwise mutate state.

Failed ROLLBACK emits rollback_failed. Successful ROLLBACK is accepted only
when the exact (slot,digest) occurs in that board's verified history; then
change active image, increment accepted_rollbacks, and clear pending tx.
Otherwise emit rollback_unverified and leave state unchanged. Verification
history survives epoch changes, but a verification for slot A never
authorizes a rollback to slot B with the same digest.

Output exactly these keys: boards, incidents, totals. boards is sorted by
board and contains objects {board, epoch, active_slot, active_digest}.
incidents is sorted by (board, epoch, sequence, event_id, reason) and contains
objects {board, epoch, sequence, event_id, reason}. totals contains
board_count, applied_commits, accepted_rollbacks, duplicate_replays,
conflicted_ids, rejected_events; rejected_events equals len(incidents).
No timestamps, paths or runtime-dependent fields belong in the output.

## Running reconciliation and audits

```sh
python3 reconcile.py --input data/visible.jsonl --output result.json
python3 reconcile.py --input data/visible.jsonl --output result.json --audit-output audit.json
python3 -m unittest discover -s tests -v
```

The optional audit file records transport row accounting and each event's
reconciliation outcome, including state before and after the event. A reported
successful operation is still an attempt until it passes the state-machine
checks. The primary report retains the exact shape above; audit collection
uses the same state transitions and does not change the result.

Audit transitions appear in execution order, including baseline initialization,
while primary report incidents use the contract's location sort. Audit records
show pending state before epoch advancement, after advancement, and after the
event action, so automatic clearing is distinguishable from an action's effects.
Operational
notes in `audit/operations-notes.json` preserve reporting values from evidence
batches; corrected values replace invalidated values in that current file.
`audit/operations-corrections.json` records explicitly superseded values for
historical audit only. The reconciler does not treat notes as transition rules.
Contract decisions and outstanding evidence questions are in `PHASE_NOTES.md`.
