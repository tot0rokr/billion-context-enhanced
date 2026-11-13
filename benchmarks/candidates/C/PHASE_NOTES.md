# Reconciliation phase notes

## Current contract: R3

Evidence batch 3 explicitly revises ALL batches: advancing boot epoch clears
all pending transaction state before applying the first retained event in the
new epoch, including when that event fails. Active image and verified-image
history survive. Rollback authorization requires the exact board-local
(slot, digest) pair. R2 remains active for (board, epoch, sequence, event_id)
ordering and failed VERIFY invalidation. The current README describes R3.

Current notes are data/operations-notes.json (48 string values). F01-F08 have
been replaced by the batch 3 corrections; their old values are invalid.
Current reports are reports/*-r3-{report,audit}.json. Earlier sections and
R1/R2 outputs below preserve historical decisions and superseded values;
they must not be used as the current contract or operational-note source.

The phase 1 and batch 1 sections below record historical R1 decisions and
results. Their timestamp ordering and failed-VERIFY flag retention have been
superseded. Current R2 results are recorded in the batch 2 section. The saved
batch1-r1 files remain historical; batch1-r2 files replace them for current use.

## Phase 1 contract (historical R1)

The active contract at phase 1 was README.md's provisional R1. At that time,
event time ordered events within an epoch, advancing
epochs retains pending transactions, and failed verification preserves an
earlier verified flag. These decisions are deliberately provisional.

## Phase 1 implementation decisions (historical R1)

- Normalize schema 1 and schema 2 before duplicate detection and execution.
- Compare normalized payloads without timestamp or schema spelling. Equivalent
  replay rows use their minimum timestamp as the deterministic representative;
  input row order cannot select a different representative.
- Process each board's baseline first to honor the baseline initialization
  requirement even when its reported timestamp sorts after other events.
- Visit epochs in ascending order, then events by timestamp, sequence, and
  event ID. Sequence and ID break equal-time ties; sequence is otherwise only
  diagnostic under R1.
- Duplicate conflicts remove all payloads for the ID. Only retained events
  establish board state. A board with retained events but no retained baseline
  starts with null active slot/digest and empty verified history. No extra
  incident reason is invented for missing initialization.
- Keep normalization, transitions, and report projection in separate standard
  library modules. reconcile.py owns the CLI and connects their interfaces.
- Build the report before opening the output file so computation errors cannot
  truncate an existing output.

## Validation and remaining work

Phase 1 implementation and integration are complete. The parent integrated
exactly these three implementation subagents, all using the inherited model:

- `/root/ingest_schema`: normalization and global ID reconciliation.
- `/root/state_machine`: board state transitions and verified history.
- `/root/report_audit`: public report projection and contract audit.

`python3 -m unittest discover -s tests -v` passes all 20 tests, including the
unchanged public test. Coverage includes mixed-schema replay equivalence,
global conflicts, timestamp ordering, pending verification across epochs,
commit consumption, exact rollback authorization, reset behavior, and report
field projection. No new dependencies or network access were used; no commits
were made.

The CLI processed all 1,990 rows in data/visible.jsonl and produced identical
output bytes for five shuffled inputs (seeds 0 through 4). Current R1 totals:

| Counter | Value |
| --- | ---: |
| board_count | 192 |
| applied_commits | 30 |
| accepted_rollbacks | 16 |
| duplicate_replays | 384 |
| conflicted_ids | 38 |
| rejected_events | 786 |

Output SHA-256, including the CLI's final newline:
`b1141eff3ad38ad03719bbc3260ce0c5c8bc2f24a0422ff951f7237575676ebf`.
These totals are observations under R1, not independent expected truth.

No implementation task remains unfinished for phase 1. Contract questions to
revisit if later evidence or revisions address them:

- The README does not specify a timestamp representative for equivalent
  replays, equal-time tie breaks, or missing-baseline behavior after conflicts.
  Current deterministic choices are recorded above.
- Malformed input behavior is unspecified. Unsupported schemas, invalid slots,
  unknown actions, and failed or multiple baselines raise ValueError; missing
  required fields raise KeyError. Valid input is the current contract scope.
- The visible dataset has 192 nonconflicted IDs with differing timestamps and
  152 boards whose baseline timestamp follows another initial-epoch event.
  Do not infer sequence ordering or different state rules from that evidence.

Later incident evidence and explicit revisions are expected from the user.
Apply the latest explicit revision when it arrives and update these notes;
do not infer a new contract from the visible dataset's anomalies.

## Evidence batch 1: completed under historical R1

Scope: INC-00001 through INC-00064, corresponding to board-00001 through
board-00064 in data/visible.jsonl. The batch introduces evidence and inert
operations values, not an explicit contract revision. R1 was then in force:
reported timestamps order events within epochs, epoch advances preserve
pending state, and failed VERIFY preserves an earlier verified flag.
F04/F12's forbidden-action strings do not change those rules.

The same three subagents were resumed in their original roles. No additional
agents were created. No dependencies, network access, or commits were used.

Changes integrated by the parent:

- Ingestion now retains one aggregate per global ID: representative payload,
  minimum location, row count, and permanent conflict flag. Memory grows with
  unique IDs rather than repeated transport rows. CLI input parsing streams
  rows into this aggregator. Replay identity and minimum timestamp selection
  are unchanged.
- `apply_events(events, *, audit=None)` and
  `reconcile(events, *, audit=None)` optionally collect one outcome for each
  retained event, including baseline, in execution order. Each outcome records
  action, attempted image, reported success, accepted/rejected classification,
  reason, and active image after the event. Rejected VERIFY mismatches can
  clear verification while leaving the active image unchanged, as R1 requires.
- `build_audit_report(report, outcomes, operations_notes)` generates a separate
  audit. `--audit-output` exposes this through the CLI; `--operations-notes`
  adds inert records and requires audit output. Output and audit paths must
  differ. The ordinary report keeps its exact three-key R1 schema.
- Audit attempts count normalized retained COMMIT/ROLLBACK events, including
  rejected events. Replays and conflicted IDs never count as extra attempts.
  Accepted STAGE/VERIFY are distinguishable from accepted COMMIT/ROLLBACK.
  Conflicted IDs are explained by incidents and omitted from execution traces.

Exact operational values F01 through F16 / OPS-001 through OPS-016 are stored
as strings in data/operations-notes-batch1.json and copied into the audit.
They are reporting data only: no ticket is contacted, no digest grants
verification, no action is executed, and no note modifies state-machine rules.
The descriptive fields map as follows: change ticket -> change_ticket;
approved rollback digest -> approved_rollback_digest; settle window in
milliseconds -> settle_window_ms; forbidden operator action ->
forbidden_operator_action; escalation scope -> escalation_scope; accepted boot
status -> accepted_boot_status; audit correlation nonce ->
audit_correlation_nonce; evidence retention in days -> evidence_retention_days.

Batch audit facts:

| Measure | Value |
| --- | ---: |
| Transport rows | 662 |
| Boards | 64 |
| Global event IDs | 522 |
| Retained events | 510 |
| Duplicate replays | 128 |
| Conflicted IDs | 12 |
| Retained COMMIT attempts | 144 |
| Applied commits | 13 |
| Retained ROLLBACK attempts | 15 |
| Accepted rollbacks | 5 |
| State-machine incidents | 246 |
| All incidents / rejected_events | 258 |

No event ID crosses a board or the batch boundary in the complete corpus,
so selecting these boards before reconciliation preserves global-ID results
for this batch. All 12 batch conflicts are e001 on every fifth board, from
board-00005-e001 through board-00060-e001; their two payloads differ only in
digest. Each of the 64 boards has one three-row replay group, accounting for
128 duplicate replays; the other 446 IDs each have one row. Across the full
corpus these quantities are 38 two-row conflicts, 192 three-row replay groups,
and 1,338 single-row IDs.

Representative reviewed outcomes, all provisional R1 consequences:

- board-00002-e003 commits using pending verification retained from epoch 0;
  board-00002-e006 RESET sorts before e004/e005 and therefore does not prevent
  board-00002-e007 from committing.
- board-00005-e001's conflicting STAGE payloads are both excluded; subsequent
  operations cannot use either image as that transaction's pending stage.
- board-00008-e004 is rollback_unverified: slot A baseline history cannot
  authorize the same digest in slot B.
- board-00013-e004 commits before e003 under reported time; e003 is therefore
  verify_without_stage after the accepted commit consumes pending state.
- board-00018-e008 commits before e007 RESET under reported time; the later
  successful reset retains the newly active image.
- board-00024-e003 is commit_unverified; e002 subsequently verifies and e004
  commits. The failed attempt does not consume pending state.

Artifacts:

- reports/batch1-r1-report.json: canonical final states, rejection reasons, and
  counters for all 64 cases.
- reports/batch1-r1-audit.json: execution outcomes for all 510 retained events,
  all accepted commit/rollback IDs, case attempts and incidents, and all 16
  exact operational notes.

SHA-256 provenance:

- data/visible.jsonl:
  `403dc5ae6a3ad6da05ab37dffdc0fc0f76b36027e62ba8591a4c439f7d8bf87a`
- data/operations-notes-batch1.json:
  `b8fb9823210da3b1b5172e4f5cb4e6252f9470486871a4e686152e5b9767fe83`
- reports/batch1-r1-report.json:
  `5c8d63980666a573e7451a6867329603c34e418bf3174dd03f20e6473d80b4bb`
- reports/batch1-r1-audit.json:
  `54f926d6bc102f21b9cdcabe969b0636a3245c87014712bd5ed7f19b13c8ab88`

Validation: `python3 -m unittest discover -s tests -v` passes 28 tests,
including the unchanged public test. Batch report and audit are identical
under five input shuffles (seeds 0 through 4) and reversed note ordering.
All accepted-ID counts and rejected-outcome counts reconcile with totals.
The full-corpus CLI report with audit enabled retains phase 1's exact output
SHA-256 `b1141eff3ad38ad03719bbc3260ce0c5c8bc2f24a0422ff951f7237575676ebf`;
its audit contains 192 cases, 1,530 retained outcomes, and the exact notes.

No batch 1 implementation task remains unfinished. Open contract questions
remain those recorded in phase 1 (replay representative, equal-time ordering,
missing-baseline and malformed-input behavior). Future explicit revisions
must update implementation, tests, contract labels, and generated reports;
these saved R1 reports remain historical evidence, not later-contract truth.

## Evidence batch 2: completed under R2

Scope: INC-00065 through INC-00128, corresponding to board-00065 through
board-00128. The explicit R2 revision applies to ALL batches, including the
earlier 64 cases and the complete data/visible.jsonl corpus:

1. Retained event execution order is (board, epoch, sequence, event_id).
   Reported time/timestamp never orders execution or changes transitions.
2. Failed VERIFY of an existing pending transaction clears that transaction's
   previous verified flag and emits verify_failed. If no pending transaction
   exists, verify_without_stage retains precedence.

All other rules are unchanged. Epoch advances still retain pending state,
active image, and verified image history. A failed VERIFY does not erase
historical verification or affect another transaction. Successful matching
reverification can restore the pending flag. COMMIT still consumes pending
state only when accepted; accepted RESET/ROLLBACK still clear all pending
transactions. Historical rollback authorization remains an exact board-local
(slot, digest) match.

The same three original subagents handled ingestion/schema, state machine,
and report/audit. The parent integrated the changes, updated README and
integration regressions, recorded operational notes, and regenerated reports.
No new agents, dependencies, network access, or commits were used.

Ingestion and state-machine sorting now both use the R2 keys. Minimum replay
timestamps remain deterministic internal metadata only; timestamp selection
no longer presents an observable contract ambiguity. Equal-sequence events
use event_id as explicitly required, resolving the prior ordering question.
The optional audit contract label is R2. Its public outcome schema and the
ordinary report's exact public keys remain unchanged.

Exact F17 through F32 / OPS-017 through OPS-032 strings are saved in
data/operations-notes-batch2.json. The report/audit agent compared every
field/value and operation ID against the separately supplied user values,
including both rollback digests and both correlation nonces. All match.
data/operations-notes.json concatenates the unchanged batch 1 records with
batch 2 records, preserving all 32 values as strings. F20/F28's forbidden
operator-action text is inert and does not revise epoch state retention.

R2 audit counts:

| Measure | Batch 1 rerun | Batch 2 | Complete corpus |
| --- | ---: | ---: | ---: |
| Transport rows | 662 | 664 | 1,990 |
| Boards | 64 | 64 | 192 |
| Unique event IDs | 522 | 523 | 1,568 |
| Retained events | 510 | 510 | 1,530 |
| Duplicate replays | 128 | 128 | 384 |
| Conflicted IDs | 12 | 13 | 38 |
| COMMIT attempts | 144 | 144 | 432 |
| Applied commits | 54 | 54 | 163 |
| ROLLBACK attempts | 15 | 16 | 48 |
| Accepted rollbacks | 5 | 5 | 16 |
| State-machine incidents | 149 | 152 | 451 |
| All incidents / rejected_events | 161 | 165 | 489 |

Batch 2 has 446 single-row IDs, 13 two-row conflicting IDs, and 64 three-row
replay groups. Conflicts are e001 on every fifth board from board-00065 through
board-00125 and differ only in digest. There are no cross-board or cross-batch
IDs in the complete corpus, so batch selection preserves global-ID results.

Batch 2 incident reasons: commit_failed=6, commit_mismatch=20,
commit_unverified=25, commit_without_stage=39, duplicate_conflict=13,
reset_failed=6, rollback_failed=5, rollback_unverified=6, stage_failed=5,
verify_failed=20, verify_mismatch=5, verify_without_stage=15.

Representative reviewed traces:

- board-00073-e002 verifies, e003 fails and invalidates verification, and e004
  is commit_unverified. Its epoch-1 e006 fails and e007 is also unverified.
  Earlier batch 1 board-00013 now follows the same R2 failed-VERIFY rejection;
  its e004 had been accepted under R1.
- board-00066-e003 mismatches slot and clears verification; e004 is
  commit_unverified. In epoch 1, e007 RESET precedes e008, so e008 is
  commit_without_stage despite its earlier wall-clock time.
- board-00067-e003 is commit_failed; it preserves pending verification and
  permits e004 to commit. Its epoch-1 e007 is commit_mismatch.
- board-00068-e003 and e007 commit, while e004 is rollback_unverified because
  its slot-B target does not match the slot-A baseline history.
- board-00069-e003 commits, e004 rolls back to the verified baseline, and
  failed epoch-1 verification prevents e007 from committing.
- board-00072-e003 commits and consumes pending state; e004 is
  commit_without_stage. Its distinct epoch-1 staged image commits at e007.
- Cross-epoch e003 commits remain accepted on boards 00074, 00086, 00098,
  and 00122 because pending verification survives epochs under unchanged
  rules. Successful later RESET prevents their final COMMIT attempts.

Batch 1's R2 rerun changes 42 final board states from saved R1 output.
Applied commits change from 13 to 54; incidents change from 258 to 161;
rollbacks, replay counts, and conflict counts remain 5, 128, and 12.

Current artifacts and SHA-256 (CLI JSON bytes including final newline):

- reports/batch1-r2-report.json:
  `fb4e1aa12bd9c004640ea9d6e51b5bcf3f3f43cb1236410805a7432bd0763354`
- reports/batch1-r2-audit.json:
  `b7ebd5355aba7edbd59c76602830619377744aa7410b28cf0fb4e25c9ddcfab2`
- reports/batch2-r2-report.json:
  `9e17167eb9ca83de4dfe7aac879d40c986cdd622288805cc1693e2642371d1a7`
- reports/batch2-r2-audit.json:
  `371e4aa8dfb0de8d69780a6f7ef929736f03ef9f0d2b466775a76a7413343853`
- reports/visible-r2-report.json:
  `6cef8713e8e9232723f998c11e5b90bd295170832ee29150df9b5dd09424ef87`
- reports/visible-r2-audit.json:
  `777a1b414ee9ca32f966c07be099aae93e8948216b5fbc1a91f6a61657d6662e`
- data/operations-notes-batch2.json:
  `de7849fddd8f48bba0a03c0c7edcb563da19225fd92c76f14dc9be0e1b6f491b`
- data/operations-notes.json:
  `183da7be1287665b8e35766d0039ee65cd981320cbea32d55694249dba68aa56`

Batch audits contain their respective 16 notes; the complete corpus audit
contains all 32. Every case records attempted and accepted operations, every
retained event outcome, active state after each event, and all rejection
reasons. Transport conflicts appear once as incidents and never execute.

Validation: `python3 -m unittest discover -s tests -v` passes all 35 tests,
including the unchanged public fixture. Regressions cover clock skew,
event-ID ties, failed-VERIFY invalidation, isolation between transactions,
reverification, rollback-history preservation, unchanged epoch retention,
and both earlier and newly supplied real cases. Randomizing all 1,990 source
timestamps over [-10**30, 10**30) and shuffling the rows leaves the complete
report and all 1,530 audit outcomes unchanged. The independent report/audit
interpreter matches every batch 2 report row and all 510 outcome rows.
All three generated scopes were checked for ordered unique outcomes,
accepted-ID/count agreement, rejection/incident agreement, exact notes, and
final-state agreement. Source corpus and batch 1 notes retain their earlier
SHA-256 values.

This batch's implementation and audit are complete. Remaining contract gaps
are malformed-input behavior and missing-baseline behavior after conflicts;
the established fallbacks remain unchanged. No R2 implementation issue is
unresolved. Later explicit revisions supersede the corresponding R2 rules
and require fresh reports; these versioned artifacts preserve audit history.

## Evidence batch 3: completed under R3

Scope: INC-00129 through INC-00192, corresponding to board-00129 through
board-00192 in data/visible.jsonl. R3 applies to all three batches. The original
three subagents were resumed in their original ingestion/schema, state-machine,
and report/audit roles. No new agents, dependencies, network access, or commits
were used.

Epoch increases now clear the entire pending map before event execution.
This prevents prior-epoch stages or verified flags from authorizing a commit.
The first new-epoch STAGE remains available for that epoch's VERIFY/COMMIT.
Active image and exact verified history survive, including epoch jumps and
rejected first events. Exact (slot,digest) rollback authorization was already
implemented and is confirmed by R3; rollback acceptance did not change.
R2 sequence ordering and failed-VERIFY invalidation remain in force.

All corrected F01-F08 values replace their old values in
data/operations-notes-batch1.json. New exact F33-F48 values are in
data/operations-notes-batch3.json. The combined data/operations-notes.json has
exactly one current record for each F01-F48, with all values kept as strings.
The report/audit agent independently compared every corrected and new record
against separately supplied field/value/OPS IDs. Current R3 artifacts use
only corrected values. Historical R1/R2 sidecars still record earlier,
explicitly invalid F01-F08 values for provenance and are superseded.
Notes remain inert and do not authorize state transitions or external action.

R3 audit counts:

| Measure | Batch 1 rerun | Batch 2 rerun | Batch 3 | Complete corpus |
| --- | ---: | ---: | ---: | ---: |
| Transport rows | 662 | 664 | 664 | 1,990 |
| Boards | 64 | 64 | 64 | 192 |
| Unique event IDs | 522 | 523 | 523 | 1,568 |
| Retained events | 510 | 510 | 510 | 1,530 |
| Duplicate replays | 128 | 128 | 128 | 384 |
| Conflicted IDs | 12 | 13 | 13 | 38 |
| COMMIT attempts | 144 | 144 | 144 | 432 |
| Applied commits | 49 | 50 | 51 | 150 |
| ROLLBACK attempts | 15 | 16 | 17 | 48 |
| Accepted rollbacks | 5 | 5 | 6 | 16 |
| State-machine incidents | 154 | 156 | 154 | 464 |
| All incidents / rejected_events | 166 | 169 | 167 | 502 |

Batch 3's 13 conflicting IDs are e001 on every fifth board from board-00130
through board-00190; payloads differ only in digest. Its schema row counts
are 335 schema 1 / 329 schema 2. All source baselines occur at epoch 0,
sequence 0; no retained (board,epoch,sequence) ties occur in this corpus.
Every global ID belongs to one board, so independent batch ingestion exactly
matches the corresponding full-corpus projection. Replays and conflicted IDs
do not inflate operation attempts or execute more than once.

Compared with R2, exactly 13 e003 outcomes change from accepted COMMIT to
commit_without_stage: boards 00002, 00014, 00026, 00038, 00062, 00074, 00086,
00098, 00122, 00134, 00146, 00158, and 00182. These same boards' final active
images change to their baselines. Total commits decrease 163 to 150 and
incidents increase 489 to 502. Rollbacks, replay counts, and conflicts remain
16, 384, and 38. board-00170-e003 was already rejected after its STAGE conflict.

Representative batch 3 findings:

- board-00134, board-00146, board-00158, and board-00182 successfully verify
  at e002 in epoch 0, then reject e003 in epoch 1 because pending state was
  cleared. Their later epoch-2 RESET also prevents the final COMMIT.
- board-00133-e003 fails VERIFY, clears the flag, and e004 is
  commit_unverified; R2's invalidation still applies within an epoch.
- board-00152-e004 requests the baseline digest in slot B, although only
  the slot-A pair is in history, so rollback_unverified is correct. e007
  commits the freshly staged and verified epoch-1 image.
- board-00129 commits e003, accepts baseline rollback e004, then rejects
  e007 after failed epoch-1 VERIFY. board-00132 commits e003 and e007, but
  e004 is commit_without_stage because the first commit consumed its stage.

Batch 3 reasons: commit_failed=5, commit_mismatch=20, commit_unverified=24,
commit_without_stage=44, duplicate_conflict=13, reset_failed=5,
rollback_failed=6, rollback_unverified=5, stage_failed=6, verify_failed=20,
verify_mismatch=4, verify_without_stage=15.
Full-corpus reasons: commit_failed=16, commit_mismatch=61,
commit_unverified=74, commit_without_stage=131, duplicate_conflict=38,
reset_failed=16, rollback_failed=16, rollback_unverified=16, stage_failed=16,
verify_failed=61, verify_mismatch=13, verify_without_stage=44.

Generated current artifacts: reports/batch1-r3-{report,audit}.json,
reports/batch2-r3-{report,audit}.json, reports/batch3-r3-{report,audit}.json,
and reports/visible-r3-{report,audit}.json. Batch audits include their 16
current notes; the full audit includes all 48. The public schema is unchanged.
Each sidecar records every retained event, rejection reasons, attempted and
accepted operation counts/IDs, and active state after each event.

Selected SHA-256 values (JSON files include the CLI's final newline):

- reports/batch3-r3-report.json:
  `70b6638cd12163ffe439db336a60bde947e234a6b21a1b4b130abd8707f4e487`
- reports/batch3-r3-audit.json:
  `61004658bbc6a2ebc5eed11be88a391606af04150b26e6b46a08192d774c2375`
- reports/visible-r3-report.json:
  `7f9833813e072dbcba508bc26d1144f2ad8480e8a309d0c57aad225341244383`
- reports/visible-r3-audit.json:
  `cbc3a285c59739c60a3e45ead3264627cdf80fb75b5f7afa67ae6ba178d09bb8`
- data/operations-notes-batch1.json (corrected):
  `773c1564cac67c4b67b74d0ff1c65411b7609bdfd088c2561cdbfd13b0a5107b`
- data/operations-notes-batch3.json:
  `64410dbff3a7f47d47dd76e731d77d622bcd19e937f0d1c8df8dc2f917b81adf`
- data/operations-notes.json (48 current values):
  `7d743df5fdac957c3ecbc0854eef44db9bbad7be4083ace4e25ff6228b224303`

Validation: `python3 -m unittest discover -s tests -v` passes all 38 tests,
including the unchanged public fixture. New or updated regressions exercise
all-pending clearing, epoch jumps with sequence resets, failed first events,
fresh new-epoch staging, active/history retention, exact rollback matching,
and revised real cases from every batch. Existing clock randomization and
shuffle tests still pass. An independent interpreter matches all 1,530
retained outcomes and public results. Every generated scope passed checks
for ordered unique outcomes, accepted-ID/count agreement, attempt counts,
incident totals, exact current notes, and final-state agreement.
The corpus SHA-256 remains unchanged.

This batch is complete. Malformed-input and conflict-removed-baseline policy
remain unspecified; established error/null-state behavior is unchanged.
There are no unresolved R3 implementation issues. Later explicit revisions
must supersede these decisions and trigger regenerated current reports.

## Final CLI integration: completed

The integrated reconcile.py uses general schema normalization, global ID
reconciliation, R3 transitions, and exact public-field projection. Runtime
code does not depend on corpus board names, event IDs, digests, expected
outcomes, or report fixtures. A fresh CLI regression generates unrelated
identifiers and digests, mixes schemas and skewed timestamps, and checks
failed-VERIFY invalidation, epoch clearing, preserved exact rollback history,
commit consumption, and cross-schema replay handling against explicit
expected results.

`python3 -m unittest discover -s tests -v` passes all 39 tests, including the
public test and the fresh-input CLI regression. The requested invocation
`python reconcile.py --input data/visible.jsonl --output analysis.json` ran
successfully using a shell-local python function forwarding to python3,
because this environment has no python executable. No interpreter files or
configuration outside the repository were changed.

analysis.json preserves exactly boards/incidents/totals and their required
fields. It is byte-identical to reports/visible-r3-report.json, with SHA-256
`7f9833813e072dbcba508bc26d1144f2ad8480e8a309d0c57aad225341244383`.
Totals: 192 boards, 150 applied commits, 16 accepted rollbacks, 384 duplicate
replays, 38 conflicted IDs, and 502 rejected events. No hidden evaluator files
were inspected. All requested final integration work is complete.
