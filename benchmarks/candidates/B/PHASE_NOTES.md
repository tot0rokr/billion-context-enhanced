# Reconciliation phase record

Current authority: R3, supplied with evidence batch 3 and effective for all
batches. Advancing epoch clears all pending transactions before the new event,
even if that event fails, while retaining active image and verified history.
Rollback authorization requires the exact board-local `(slot, digest)` pair.
R2 ordering `(board, epoch, sequence, event_id)` and failed-VERIFY invalidation
remain in force; timestamps never affect execution.
Phases 1 and 2 below are historical records of the then-current R1 contract;
their timestamp and failed-VERIFY decisions are superseded. Phase 3 records R2;
its pending-state retention across epochs is superseded by phase 4. F01..F08
were corrected in phase 4; former values are invalid. `audit/operations-current.json`
is the resolved register of all 48 current operational values.

## Phase 1: initial R1 implementation

The current authority is the provisional R1 contract in README.md. No later
contract revision has arrived. Future explicit user revisions take precedence;
update this record and the affected implementation/tests when they arrive.

Responsibilities (all agents inherit the parent's configured model):

- `/root/ingest_schema`: schema normalization and global ID reconciliation in
  `ingest.py`, with ingestion tests.
- `/root/state_machine`: board state transitions in `state_machine.py`, with
  state-machine tests.
- `/root/report_audit`: exact report projection, sorting and totals in
  `report.py`, with report tests and contract audit.
- Parent `/root`: CLI integration in `reconcile.py`, integration tests, final
  review, validation and this phase record.

### Current contract decisions

- Preserve R1 timestamp ordering, pending transactions across epoch changes,
  and an earlier verified flag after a failed VERIFY. These are provisional
  rules explicitly stated in README.md, even if later evidence suggests changes.
- Initialize a board from its successful BASELINE before other events, even if
  its reported timestamp is later. Then process epochs in ascending order and
  events within an epoch by `(timestamp, sequence, event_id)`. Sequence and ID
  only break timestamp ties for deterministic behavior.
- Ignore timestamp and schema spelling for replay identity. Use the minimum
  timestamp among identical replay payloads as their representative timestamp.
  R1 does not specify this choice; minimum makes input permutations equivalent.
- VERIFY without pending state emits `verify_without_stage` before considering
  success or image mismatch. Failed COMMIT always emits `commit_failed` first.
- Successful RESET and accepted ROLLBACK clear all pending transactions for the
  board. A committed transaction is removed individually.
- Verified image history is per board and contains exact `(slot, digest)` pairs.
  Epoch transitions, RESET, failed verification and mismatches never erase history.
- If conflict exclusion removes a board's baseline, remaining events start with
  a null active image and empty history. Boards with no retained events do not
  receive a state row. These cases are outside R1's baseline guarantee.
- Input field types and actions follow the declared schemas; malformed records
  and mixed timestamp representations have no specified report contract.
- Output remains exactly `boards`, `incidents`, `totals`, with no timestamps or
  diagnostic metadata added. CLI computes the result before opening its output.

### Validation and handoff

Phase 1 implementation and parent integration review are complete.

- `python3 -m unittest discover -s tests -v`: 26 tests passed, including the
  unchanged public CLI test. Tests cover normalization, global conflicts,
  transition failures and recovery, transaction isolation, rollback history,
  deterministic reporting, mixed-schema integration and blank CLI input.
- Ran the CLI on all 1,990 rows of `data/visible.jsonl`; its JSON matched direct
  reconciliation after shuffling those rows with seed `20261106`.
- Visible R1 smoke totals: 192 boards, 30 applied commits, 16 accepted rollbacks,
  384 duplicate replays, 38 conflicted IDs, 786 rejected events. These are
  observed provisional results, not an independent correctness oracle.
- Runtime: Python 3.11.2 via `python3`; the `python` alias and `rg` are absent.
  The task directory has no Git metadata. No commit, external network access
  or new dependencies were used.

No unfinished implementation work remains for this phase. Open work for later
phases: consume the promised incident evidence and explicit contract revisions
when supplied. Do not infer a revision from fixture timestamps.

## Phase 2: evidence batch 1

Completed the audit of INC-00001 through INC-00064 and checked the complete
visible corpus. The same three agents resumed their original responsibilities.
No explicit contract revision arrived: R1 remains in force, including timestamp
ordering, pending state across epochs, and earlier verification after a failed
VERIFY. The operational notes are reporting data, not reconciliation rules.

### Implementation and durable audit records

- Added optional `reconcile_states(events, *, trace=None)` and
  `reconcile(events, *, trace=None)` tracing from the actual transition loop.
  Each retained event records reported success separately from acceptance,
  its rejection reason, and its active image before and after processing.
- Added `build_audit_report(report, trace, *, contract_revision="R1")` and CLI
  `--audit-output`. The sidecar explains rejection reasons and counts retained
  COMMIT/ROLLBACK attempts, reported successes, acceptances and rejections.
  Replay and conflicted rows do not count as executable attempts. Accepted
  same-image rollbacks still count even when the active image does not change.
- The main report still has exactly the R1 fields. Audit events retain actual
  execution order; incidents retain the contract's diagnostic sorting. Neither
  report contains timestamps or runtime metadata. Separate output paths are
  required so the sidecar cannot overwrite the main report at the same path.
- Preserved all sixteen F01..F16 / OPS-001..OPS-016 values exactly as strings in
  `audit/operations-batch-1.json`, including the original digest spelling and
  numeric values. No operational action or external communication was performed.
- Saved `audit/batch-1-report.json`, `audit/batch-1-trace.json`, and
  `audit/visible-r1-report.json`. `audit/batch-1-validation.json` records source,
  code and artifact SHA-256 hashes, scope, totals, rejection counts and checks.
  These files snapshot R1; regenerate or version them after an explicit revision.
- Detailed evidence and decisions are in `audit/ingest-batch-1.md`,
  `audit/state-batch-1.md`, and `audit/report-batch-1.md`. `audit/README.md`
  describes artifact interpretation and reproduction.

### Results and checks

- All 40 tests passed with `python3 -m unittest discover -s tests -v`, including
  the unchanged public test. Added corpus ingestion regressions, trace/report
  consistency, same-image rollback acceptance, CLI sidecar behavior and output
  collision protection. Full-corpus report and trace are invariant under
  shuffles with seeds 17 and 20261106; ingest additionally checked reversal.
- Batch 1: 662 transport rows, 522 IDs, 510 retained events, 64 boards,
  128 duplicate replays and 12 conflicted IDs. Main report has 258 rejected
  events: 246 transition incidents plus 12 duplicate-conflict incidents.
- Retained COMMIT attempts: 144, with 139 reporting success and 13 accepted.
  Retained ROLLBACK attempts: 15, with 10 reporting success and 5 accepted.
- Full corpus: 1,990 rows, 192 boards, 30 applied commits, 16 accepted
  rollbacks, 384 duplicate replays, 38 conflicted IDs, 786 rejected events.
  Default R1 results agree with phase 1. Batch report and event trace were
  also checked against the first64-board projection of global reconciliation.
- No R1 transition or ingest defect was found. Improvements add inspectable
  outcomes and regression coverage; they do not reinterpret evidence as a
  contract revision. No dependencies, network access or commits were used.

### Unresolved contractual choices

Timestamp order can run COMMIT before STAGE (board-00001-e004 before e001);
R1 explicitly requires that order. Epoch retention accepts board-00002-e003
using epoch 0 pending verification. Failed VERIFY still preserves an earlier
flag; batch evidence alone does not revoke this rule. These remain provisional
pending an explicit revision. Minimum replay timestamp and timestamp ties use
the recorded deterministic choices. Malformed inputs and missing/conflicted
baseline guarantees remain outside the defined contract. Future revisions
must update audit reason explanations as well as transitions and tests.

No unfinished work remains for batch 1. Later evidence/revisions are anticipated.

## Phase 3: evidence batch 2 and R2 revision

Completed INC-00065 through INC-00128 and re-evaluated all earlier evidence.
The original three subagents resumed ingest/schema, state-machine, and
report/audit ownership. R2 explicitly supersedes two R1 rules for every batch:

- Execute retained events by `(board, epoch, sequence, event_id)`, never clocks.
- Failed VERIFY of an existing pending transaction clears its verified flag.

No other transition rule changed. In particular, epoch changes preserve pending
state, active image, and verified image history. An absent transaction still
makes VERIFY emit `verify_without_stage` before failure; an existing failed
VERIFY emits `verify_failed` even if its requested image mismatches. Failure
only clears its transaction's flag. A later matching VERIFY can restore it;
earlier exact image history remains eligible for rollback. Operational notes
such as `reuse-old-epoch-verification` remain reporting values, not contract
revisions.

State logic, integration tests, live README, sidecar explanations and default
revision label now use R2. The current sidecar builder rejects non-R2 labels.
Ingest still chooses the minimum replay timestamp as inert metadata, excluded
from identity, execution order and all report fields. Primary report schema
and trace fields are unchanged. R1 batch report/trace/validation/documentation
were archived under `audit/r1/`; historical agent notes and the explicitly named
`audit/visible-r1-report.json` are retained. Current batch-1 artifacts were
regenerated under R2; batch-2 and full-corpus R2 report/trace artifacts were
added. See `audit/README.md` for the complete mapping.

All F17..F32 / OPS-017..OPS-032 values are preserved exactly as strings in
`audit/operations-batch-2.json`, associated with INC-00065..INC-00080. The prior
sixteen values remain untouched. No operational action, external network,
dependency installation, or commit was performed.

Validation: `python3 -m unittest discover -s tests -v` passed all 50 tests,
including the unchanged public test. Full-corpus report/trace stay identical
after shuffling and independently rewriting every timestamp. Sequence ties
use event ID. Tests cover flag clearing for matching/mismatching failed VERIFY,
transaction isolation, fresh verification recovery, retained exact history,
and unchanged epoch retention. Both batch report/trace outputs equal their
projections from full global reconciliation. SHA-256 provenance is recorded
in the updated per-batch validation files.

R2 observed results:

| Scope | Input rows | Retained | Commits | Rollbacks | Replays | Conflicted IDs | Rejected events |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Batch 1 | 662 | 510 | 54 | 5 | 128 | 12 | 161 |
| Batch 2 | 664 | 510 | 54 | 5 | 128 | 13 | 165 |
| Full 192 boards | 1990 | 1530 | 163 | 16 | 384 | 38 | 489 |

Batch 2 COMMIT attempts/report-success/accepted are 144/138/54; ROLLBACK
16/11/5. Both R2 changes affect the R1-to-R2 differences, so total deltas do
not isolate either rule. Concrete evidence: INC-00073 e003 clears verification
before e004 rejects `commit_unverified`; earlier INC-00001 e004 now has that
same rejection instead of R1 `commit_without_stage`; INC-00074 e003 still
accepts epoch-0 verification, while e007 rejects after the epoch-2 RESET.

No unfinished batch-2 work or known implementation issue remains. Malformed
input and missing/conflicted baselines remain outside the declared guarantees.
Further explicit revisions must update transitions, explanations, tests, live
documentation and artifacts together. Later evidence is anticipated.


## Phase 4: evidence batch 3 and R3 revision

Completed INC-00129 through INC-00192 and re-evaluated all earlier evidence.
The original three agents retained ingest/schema, state-machine and report/audit
ownership. R3 requires clearing all pending state on boot epoch advancement
before evaluating the new event, even if it fails. Active image and verified
history survive. Exact board-local `(slot, digest)` rollback authorization was
already implemented and is explicitly reaffirmed. R2 canonical sequence order
and failed-VERIFY invalidation remain in force.

The state loop now clears `pending` when `event["epoch"] > epoch`, then updates
`epoch` and evaluates the event. It leaves active image and history untouched.
The same trace API and exact public schemas remain. Sidecars now require R3
labels; explanations distinguish boot-boundary clearing from action rejection.
All historical state and ingest audit notes are retained as historical records.
No ingestion semantics changed.

All 56 tests passed with `python3 -m unittest discover -s tests -v`, including
the unchanged public test. New coverage checks multiple pending transactions,
epoch jumps before all five failing action types, active-image retention,
exact history across epochs, fresh-stage recovery, and R3 on every batch.
Full report/trace remain invariant under shuffling and independent clock
rewrites. Batch report/trace match global projections. Current validation
manifests record artifact/source hashes and operation counts.

| Scope | Rows | Retained | Commits | Rollbacks | Replays | Conflicts | Incidents |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Batch 1 | 662 | 510 | 49 | 5 | 128 | 12 | 166 |
| Batch 2 | 664 | 510 | 50 | 5 | 128 | 13 | 169 |
| Batch 3 | 664 | 510 | 51 | 6 | 128 | 13 | 167 |
| Full 192 boards | 1990 | 1530 | 150 | 16 | 384 | 38 | 502 |

Batch 3 COMMIT attempted/reported-success/accepted counts are 144/139/51;
ROLLBACK counts are 17/11/6. R2-to-R3 changes exactly 13 acceptance decisions:
old-epoch pending COMMITs now reject `commit_without_stage`. Boards are
2,14,26,38,62,74,86,98,122,134,146,158,182, all event e003. Rollback decisions
remain unchanged. Every batch finishes with 27 active A images and 37 B images.
INC-00134 shows cleared epoch-0 verification; INC-00140 rejects a baseline
digest on the wrong slot. All corpus rollbacks occur epoch 0, so cross-epoch
history retention is exercised by focused tests rather than corpus evidence.

R2 reports, traces, validation and documentation were archived byte-for-byte
under `audit/r2/` before current artifacts were regenerated. Explicitly named
full-corpus R1/R2 outputs remain historical. All three current batch outputs
and full-corpus R3 outputs are available through `audit/README.md`.

Applied the exact F01..F08 / OPS-001..OPS-008 corrections to current batch-1
notes. The old values are invalid; the correction history labels them
`invalid_previous_value`. Added exact F33..F48 / OPS-033..OPS-048 values for
INC-00129..INC-00144. `audit/operations-current.json` resolves all 48 current
notes; F09..F32 remain unchanged. Archived R2 operations are explicitly marked
historical/invalid for the corrected fields. These values never control
reconciliation and no named operational action was executed.

No unfinished batch-3 work or known implementation issue remains. Malformed
inputs and missing/conflicted baselines remain outside the declared guarantees.
No external network, dependency installation or commit was used. More evidence
and explicit revisions are anticipated; update live rules, explanations,
tests and artifacts together when supplied.

## Final CLI integration

Reviewed `reconcile.py`, ingestion, state transitions and report projection under
R3; runtime code is generic and needs no board, event-ID, digest or outcome
special cases. The CLI and exact main JSON shape remain unchanged.

Added a CLI regression using three generated sets of unseen board/transaction/
event identities, digests, epochs and mixed schema spellings. It checks failed
VERIFY invalidation and recovery, a failed RESET on an epoch boundary, rejection
of old pending commits, exact-slot and board-local rollback authorization,
retained history, fresh staging, replay counting and clock-independent ordering.
All 57 public and regression tests passed. Test temporary files stayed inside
the repository; no hidden evaluator files or external paths were inspected.

Generated `analysis.json` with the requested command
`python reconcile.py --input data/visible.jsonl --output analysis.json`.
Because the environment has no `python` executable, a temporary shell function
forwarded `python` to the installed `python3`; no interpreter wrapper was added
to the project or system. Output matches `audit/visible-r3-report.json` and has
the exact public fields: 192 boards, 150 applied commits, 16 accepted rollbacks,
384 duplicate replays, 38 conflicted IDs and 502 incidents. Current validation
manifests include the final output and refreshed source/test/document hashes.
