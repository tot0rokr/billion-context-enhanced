# Rollout reconciliation phase notes

**Current authority: R3, effective for all batches.** Retained events execute by
`(board, epoch, sequence, event_id)` with clocks ignored. Failed VERIFY of an
existing pending transaction clears its verified flag. Epoch advancement clears
all pending transactions while retaining the active image and exact-image
verification history. Rollback requires the exact `(slot,digest)` pair.
F01–F08 have corrected current values; their old values are invalid for those
operations and retained as superseded correction history. See phases 4–5 below
for current results and final integration checks.
Earlier phase sections are historical; their artifacts and detailed findings
reside under `audit/history/r1/` and `audit/history/r2/`.

## Phase 1: initial implementation (2026-11-06)

The current authority is the provisional R1 contract in README.md. Later
explicit user revisions take precedence; update these notes when applying them.
Do not infer revisions from the visible fixture's timestamps or sequences.

Exactly three implementation subagents use the parent's configured model:

- `/root/ingest_schema`: schema normalization and global ID reconciliation;
  owns `ingest.py` and focused ingestion tests.
- `/root/state_machine`: board state, execution ordering, and transition
  incidents; owns `state_machine.py` and focused transition tests.
- `/root/report_audit`: deterministic report shape, sorting, and integrated
  contract tests; owns `report.py` and `tests/test_contract.py`.

The parent integrates the CLI in `reconcile.py`, reviews the combined work,
runs the public tests and broader checks, and maintains this note. No new
dependencies, external network access, or commits are part of this phase.

### Current decisions

- Normalize schema spelling and slots before deduplication or state changes.
  Missing transaction, slot, and digest values become null.
- Timestamps are excluded from payload identity. Equivalent replay copies use
  their minimum reported timestamp so shuffling input cannot change ordering.
  This timestamp representative policy fills a gap in R1; it is revisable.
- Conflicting IDs are removed globally before any board state is reconstructed.
  Their rows contribute no replay count and produce one canonical incident.
- A successful baseline initializes each board before its remaining events,
  even if its reported timestamp is later. This interprets R1's baseline-before-
  other-events guarantee as initialization rather than relying on clock order.
- Process remaining events by ascending epoch, then reported timestamp, with
  sequence and event ID breaking ties deterministically. Sequence is not the
  primary execution order under R1.
- Epoch advancement retains pending transactions, the active image, and exact
  `(slot, digest)` verification history, as explicitly required by R1.
- Failed verification preserves an earlier verified flag under R1. Verification
  without a pending transaction reports `verify_without_stage` first, including
  failed verification attempts. Successful mismatched verification clears the
  pending transaction's verified flag without erasing historical verification.
- Accepted commits consume only their own pending transaction; successful resets
  and accepted rollbacks clear all pending transactions on that board.
- If global conflict removal eliminates a board's baseline but other events
  survive, reconstruction starts with null active slot/digest and empty history.
  A board represented only by discarded rows has no reconstructed board row.
  General malformed-input semantics remain outside the supplied contract.

### Validation and carry-forward work

Phase 1 implementation is complete. The parent integrated and reviewed all
three components. The CLI uses UTF-8 JSONL, ignores blank lines, and writes
sorted, indented JSON with a final newline. Reconciliation finishes before the
output file is opened. No phase 1 implementation work remains unfinished.

Validation completed by the parent:

- `python3 -m unittest discover -s tests -p test_public.py -v`: supplied public
  CLI test passes against `data/public-expected.json`.
- `python3 -m unittest discover -s tests -v`: all 25 tests pass (1 public,
  5 ingestion, 7 state-machine, and 12 report/integration tests).
- The 1,990-row visible fixture reconciles for 192 boards. Ten seeded shuffles
  produce identical reports. Reconciliation does not mutate raw input rows.
  CLI output for original versus shuffled input is byte-identical; the shuffled
  CLI input also includes blank lines. Temporary check files were removed.

Observed visible-fixture R1 totals (diagnostic, not an independent oracle):

| Counter | Value |
| --- | ---: |
| board_count | 192 |
| applied_commits | 30 |
| accepted_rollbacks | 16 |
| duplicate_replays | 384 |
| conflicted_ids | 38 |
| rejected_events | 786 |

CLI output SHA-256 for this R1 visible-fixture report:
`b1141eff3ad38ad03719bbc3260ce0c5c8bc2f24a0422ff951f7237575676ebf`.
The visible fixture has no supplied expected report, so its checks establish
determinism and successful execution rather than independently proving all
incident classifications.

Await later user turns for additional incident evidence or explicit contract
revisions. Revisit the documented timestamp representative and baseline ordering
choices if those revisions specify different behavior.

Environment notes: invoke Python as `python3`; `python` and `rg` are unavailable.
The supplied `/task` directory has no Git metadata. No commits were made.

## Phase 2: evidence batch 1 (2026-11-06)

Scope: cases INC-00001 through INC-00064, corresponding to board-00001 through
board-00064 in `data/visible.jsonl`. This batch contains evidence and reporting
values, with **no explicit contract revision**. All R1 state rules and phase 1
interpretation decisions remain in force. In particular, timestamp ordering,
pending-state retention across epochs, and preservation of an earlier verified
flag on failed VERIFY have not changed.

The original three subagents were reactivated with their original roles and
configured model: `/root/ingest_schema`, `/root/state_machine`, and
`/root/report_audit`. The parent integrated and reviewed their implementation,
added CLI checks, generated the artifacts, and ran final validation.

### Implementation and preserved evidence

- Ingestion now aggregates each global event ID while reading rather than
  storing every replay row. A conflicted ID remains excluded even when more
  matching copies arrive later. Memory scales with distinct IDs rather than
  replay volume; classification and minimum-location rules are unchanged.
- Optional `--audit-output` produces a separate explanatory JSON file.
  `reconcile_with_audit(events)` returns `(primary_report, audit_report)`.
  The primary report still has exactly `boards`, `incidents`, and `totals`.
  The two output paths must differ so the audit cannot overwrite the report.
- The audit captures per-ID transport accounting and every retained event in
  execution order, with reported success, accepted/rejected outcome, rejection
  reason, before/after active and pending state, and verification-history
  additions. It uses the same state engine as ordinary reconciliation.
- Per-action attempt counts describe retained logical events. Replays and
  conflicted IDs do not count as executed attempts. `reported_success` does not
  imply an accepted COMMIT; the exact rejection explanation is in
  `reason_catalog`. Rejected VERIFY mismatch can change its verified flag, and
  that effect is shown in the snapshots.
- `audit/operations-notes.json` preserves all exact F01–F16 values as strings,
  with their operation IDs and case IDs. These notes never affect execution.
  In particular, F04/F12's forbidden-action text is not an epoch-state revision;
  F02/F10's approved digests do not add images to verified history. No party was
  contacted and no action named by a note was executed.

Machine-readable artifacts:

- `audit/batch-1-report.json`: primary R1 report for the 64 supplied cases.
- `audit/batch-1-audit.json`: transport, transitions, outcomes, and explanations
  for those cases.
- `audit/visible-report-r1.json`: primary R1 report for all 192 visible boards.
- `audit/operations-notes.json`: exact operational reporting values.

Supporting findings are in `audit/ingest-batch-1.md`,
`audit/state-batch-1.md`, and `audit/report-batch-1.md`.

### Batch results and validation

The 662 batch rows comprise 510 retained events, 128 extra replay rows, and 24
rows excluded under 12 conflicted IDs. No event ID crosses the batch boundary,
so selecting these boards does not truncate any global conflict/replay group.
There are 258 incidents: 246 transition rejections plus 12 duplicate conflicts.

| Operation | Retained attempts | Reported success | Accepted |
| --- | ---: | ---: | ---: |
| COMMIT | 144 | 139 | 13 |
| ROLLBACK | 15 | 10 | 5 |
| STAGE | 121 | 116 | 116 |
| VERIFY | 139 | 117 | 44 |
| RESET | 27 | 22 | 22 |
| BASELINE | 64 | 64 | 64 |

Final parent validation:

- `python3 -m unittest discover -s tests -v`: all 44 tests pass, including the
  supplied public test, 8 audit tests, and 2 CLI audit tests.
- Batch primary report and audit are identical for original input and ten
  seeded permutations. Original and shuffled/blank-line CLI input produce
  byte-identical primary and audit files. Audit collection does not mutate raw
  input and does not alter the primary result.
- Every rejected transition and every excluded ID projects back to exactly the
  primary incident list. Transport accounting, action counters, applied commits,
  and accepted rollbacks agree. Audit fields exclude timestamps and paths.
- The full visible primary report is byte-identical to phase 1's report;
  its SHA-256 remains
  `b1141eff3ad38ad03719bbc3260ce0c5c8bc2f24a0422ff951f7237575676ebf`.
- Batch primary report SHA-256:
  `5c8d63980666a573e7451a6867329603c34e418bf3174dd03f20e6473d80b4bb`.
- Batch audit SHA-256:
  `ef513bc52e96febb430d521ff3a580e847cecf489f47953d7e0b559e8240062c`.

To regenerate the batch artifacts from the repository root:

```python
import json
from pathlib import Path
from reconcile import reconcile_with_audit

boards = {f"board-{number:05d}" for number in range(1, 65)}
rows = [json.loads(line) for line in Path("data/visible.jsonl").read_text().splitlines() if line.strip()]
batch = [row for row in rows if row.get("board", row.get("device")) in boards]
report, audit = reconcile_with_audit(batch)
for path, value in [("audit/batch-1-report.json", report), ("audit/batch-1-audit.json", audit)]:
    Path(path).write_text(json.dumps(value, sort_keys=True, indent=2) + "\n", encoding="utf-8")
```

### Carry forward

No batch 1 implementation tasks or failing tests remain. Evidence questions
remain for later explicit contract review: all 64 boards have timestamp order
that differs from sequence order, and all 64 replay groups contain different
timestamps. R1's epoch-retention and failed-VERIFY behavior can preserve earlier
verification; examples are documented in the state audit. These observations
do not themselves revise R1. The visible corpus has no independent expected
report beyond the supplied small public fixture, so generated totals are
current-contract reconstruction results rather than an external oracle.

Future explicit revisions must update the relevant rules, explanatory audit
text, affected tests, and generated artifacts together, while retaining these
historical decisions and the exact operational notes. No network access, new
dependencies, or commits were used in this phase.

## Phase 3: evidence batch 2 and contract revision R2 (2026-11-06)

Scope: cases INC-00065 through INC-00128, corresponding to board-00065 through
board-00128. The user's explicit revision applies retroactively to every batch:

> order retained events by (board, epoch, sequence, event_id), NEVER wall-clock
> time; clocks are deliberately skewed. A failed VERIFY of an existing pending
> transaction MUST clear its prior verified flag.

All other rules remain unchanged. The current README has been updated to the
combined R2 contract. The original three agents resumed their original roles
and configured model: `/root/ingest_schema`, `/root/state_machine`, and
`/root/report_audit`. The parent integrated the revision, updated the integrated
contract tests, added evidence regressions, regenerated all relevant reports,
and ran the final tests.

### Revised decisions and implementation

- Clocks are ignored entirely. Normalization returns only the nine payload
  fields and never reads `time` or `timestamp`. The earlier minimum-timestamp
  replay representative policy is superseded; equivalent normalized payloads
  are interchangeable. Missing or incomparable ignored clocks cannot affect
  ingestion, execution, reports, or audits.
- Board execution and audit transitions follow the exact R2 location order.
  There is no separate baseline reordering; the input guarantee places a valid
  board's baseline before its other events in that same order. Equal sequence
  values are resolved by event ID, not transport arrival or clock values.
- Failed VERIFY on an existing pending transaction now sets only that
  transaction's verified flag to false. Pending slot/digest, other transactions,
  the active image, and the board's exact-image verification history remain.
  A later matching successful verification can restore the flag.
- Epoch advancement still preserves pending transactions, active image, and
  verified history. R2 does not introduce epoch clearing. Missing-stage VERIFY
  precedence and the unknown-image fallback after a conflicted baseline remain
  the earlier documented interpretations.
- Default report keys are unchanged. Audit artifacts identify `contract: R2`
  and explain failed-VERIFY flag clearing. All exact F01–F16 reporting values
  remain preserved; F17–F32 were appended as strings in
  `audit/operations-notes.json`. New note/operation ordinals 17–32 map to cases
  65–80 (offset 48). Values never authorize actions or modify reconciliation.

### Regenerated results

R1 report/audit files and batch-1 findings were moved unchanged to
`audit/history/r1/`. Their original SHA-256 values were rechecked. Active
`audit/batch-1-report.json` and `audit/batch-1-audit.json` now contain R2 results;
batch-2 equivalents and `audit/visible-report.json` were generated under R2.
`audit/README.md` indexes current and historical files.

| Scope | Input rows | Retained events | Applied commits | Accepted rollbacks | Replay rows | Conflicted IDs | Incidents |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Batch 1, cases 1–64 | 662 | 510 | 54 | 5 | 128 | 12 | 161 |
| Batch 2, cases 65–128 | 664 | 510 | 54 | 5 | 128 | 13 | 165 |
| Full visible corpus | 1990 | 1530 | 163 | 16 | 384 | 38 | 489 |

Batch 2's 144 retained COMMIT attempts include 138 reported successes, 54 actual
applied commits, and 90 rejections: 39 without stage, 25 unverified, 20 mismatch,
and 6 reported failures. Its 165 incidents consist of 152 transition rejections
plus 13 conflict incidents; 26 raw rows belong to those conflicted IDs.
Across the whole visible corpus, 13 failed verifications clear a previously
true flag. In batch 2, these are `e003` on boards 00073, 00097, 00109, and 00121.

Earlier cases were explicitly revisited. On board-00001, failure `e003` now
clears the flag before `e004`, so the commit is unverified. Board-00002 still
accepts `e003` across epochs, but its later reset precedes `e007` by sequence
and causes `commit_without_stage`. Batch-2 equivalents, conflict exclusion,
verification mismatch, reset clearing, and consumed commits are covered by
`tests/test_r2_evidence.py`.

### Final validation and artifact fingerprints

- `python3 -m unittest discover -s tests -v`: all 54 tests pass, including the
  supplied public CLI test and six new evidence regressions spanning both
  batches. Superseded R1 test assertions were updated to the explicit R2 rules.
- All 1,530 full-corpus transition locations exactly follow R2 order. Audit
  counts and rejected transitions/conflicts project back to the primary totals
  and incident list. Every accepted rollback has a preceding exact historical
  verification; every failed VERIFY clears only its addressed pending flag.
- Both batch reports and audits are unchanged across ten seeded permutations
  with independently perturbed clocks. Original versus shuffled, clock-altered,
  blank-line CLI inputs produce byte-identical primary and audit output.
- Ingestion independently verified all-batch transport accounting and no global
  event ID crosses a 64-board boundary in the current fixture.
- F01–F32 values, case mappings, and unique note/operation IDs are tested.
  Note-preservation tests allow additional records in later phases.

Current artifact SHA-256 values:

| Artifact | SHA-256 |
| --- | --- |
| batch-1-report.json | `fb4e1aa12bd9c004640ea9d6e51b5bcf3f3f43cb1236410805a7432bd0763354` |
| batch-1-audit.json | `a89482346219a53e7c06b868683cbd9201384e429114b0079b7683b65acc4e59` |
| batch-2-report.json | `9e17167eb9ca83de4dfe7aac879d40c986cdd622288805cc1693e2642371d1a7` |
| batch-2-audit.json | `65cdad598a617422c0168cc97fa6f252bcdbd6faf48b099ca0a4597b2186b54a` |
| visible-report.json | `6cef8713e8e9232723f998c11e5b90bd295170832ee29150df9b5dd09424ef87` |

The phase-2 regeneration snippet now generates current R2 results, not archived
R1 results. Use `range(65, 129)` and `batch-2` filenames for this batch. The full
report is reproducible with
`python3 reconcile.py --input data/visible.jsonl --output audit/visible-report.json`.

### Carry forward

No implementation tasks or failing tests remain for batch 2. The earlier
timestamp-authority and failed-VERIFY questions are resolved by explicit R2.
Epoch retention remains in force; forbidden-action reporting values do not
revise it. Malformed-input behavior beyond the documented baseline fallback
remains outside the supplied contract. Corpus totals are contract-derived,
with no independent expected fixture beyond the small public test. Preserve
this history and all exact notes when later evidence or revisions arrive.
No network access, new dependencies, contacts, or commits were used.

## Phase 4: evidence batch 3, R3, and operations corrections (2026-11-06)

Scope: cases INC-00129 through INC-00192, corresponding to board-00129 through
board-00192, plus retroactive reconstruction of the two earlier batches. The
explicit R3 revision applies to every batch:

> advancing boot epoch MUST clear all pending transaction state, while
> retaining active image and verified-image history. Rollback authorization
> matches the exact (slot,digest) pair, never digest alone.

This supersedes R1/R2's pending-state preservation across epochs. Exact-pair
rollback was already implemented and is reaffirmed by R3. R2's location ordering
and failed-VERIFY flag clearing remain in force. The same three agents resumed
the same roles/model: `/root/ingest_schema`, `/root/state_machine`, and
`/root/report_audit`; the parent integrated and reviewed the combined work.

### Implementation and audit decisions

- On the first retained event in a higher epoch, clear every pending transaction
  before evaluating the action, even if that action reports failure. This also
  applies across skipped epochs and to null transaction IDs. Events excluded
  by global conflict reconciliation cannot advance the reconstructed epoch.
- Retain active slot/digest and exact `(slot,digest)` image history across the
  boundary. A transaction reused in the new epoch needs a fresh successful stage
  and matching successful verification before a commit can apply. Historical
  verification remains sufficient for exact-image rollback only.
- One audit record still corresponds to each retained event; no synthetic
  events or extra incidents are introduced. `pending_before` is captured before
  automatic epoch clearing, `pending_after_epoch` after clearing/before the
  action, and `pending_after` after the action. `epoch_before` and
  `epoch_advanced` expose the boundary. The first event on a board initializes
  its epoch and has `epoch_advanced=false`. Snapshots are independent and only
  collected when requested.
- The reason catalog explains action failure relative to state after epoch
  clearing. Failed VERIFY at the boundary has no pending transaction and emits
  `verify_without_stage`, preserving the established missing-stage precedence.
- No ingestion production change was needed. New tests cover cross-epoch global
  conflicts, exclusion before state reasoning, and independent slot/digest
  identity. The three evidence batches are now covered by `tests/test_evidence.py`
  (renamed from `tests/test_r2_evidence.py` and updated for R3).

### Operational values now in force

`audit/operations-notes.json` contains one current record for each of F01–F48.
F01–F08 were replaced with the user's exact corrected values; their old values
are invalid for those operations. F09–F32 are unchanged. F33–F48 map to cases
129–144 (operation ordinal plus 96); all values, including numbers, are strings.

`audit/operations-corrections.json` records the eight invalidated/current value
pairs and labels the invalidated records `superseded`. It is historical evidence,
not an alternate active source. Corrections apply to the specified note/operation:
an unchanged identical string on another note remains that note's valid value.
The current-note and correction-ledger tests check exact values and mappings.
Neither notes nor corrections authorize actions or alter the state machine.
No party was contacted and no named operator action was executed.

### Results and revision impact

All active batch report/audit artifacts and the full visible report were
regenerated under R3. A full-corpus explanatory artifact is also now available
at `audit/visible-audit.json`. Superseded R2 artifacts/findings were moved intact
to `audit/history/r2/`; their previously recorded hashes were verified. R1
history remains intact. `audit/README.md` indexes current and historical files.

| Scope | Rows | Retained events | Applied commits | Accepted rollbacks | Replay rows | Conflicted IDs | Incidents |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Batch 1 | 662 | 510 | 49 | 5 | 128 | 12 | 166 |
| Batch 2 | 664 | 510 | 50 | 5 | 128 | 13 | 169 |
| Batch 3 | 664 | 510 | 51 | 6 | 128 | 13 | 167 |
| Full corpus | 1990 | 1530 | 150 | 16 | 384 | 38 | 502 |

Batch 3 has 144 retained COMMIT attempts, 139 reporting success, 51 applied, and
93 rejected. Its 167 incidents are 154 transition rejections plus 13 conflicts.
The 69 epoch advances include 12 that clear nonempty pending state. Across all
batches, there are 208 epoch advances and 39 nonempty pending clears.

Relative to R2, exactly 13 formerly accepted commits now emit
`commit_without_stage`; there are no removed or otherwise changed incident
records. Exactly 13 final board active images change. The affected events are
`e003` on boards 00002, 00014, 00026, 00038, 00062, 00074, 00086, 00098, 00122,
00134, 00146, 00158, and 00182. Applied commits drop from 163 to 150; incidents
increase from 489 to 502. Rollback acceptance and transport accounting remain
unchanged. Detailed findings are in the three `audit/*-batch-3.md` files.

### Final validation and fingerprints

- `python3 -m unittest discover -s tests`: all 66 tests pass, including the
  supplied public CLI test. Coverage includes epoch gaps, simultaneous/null
  transactions, every failing action as a first new-epoch event, exact-image
  rollback across epochs and board isolation, and corrected operational values.
- All 1,530 retained transitions follow location order. Every epoch advance
  has empty `pending_after_epoch`; non-advances preserve the intermediate state.
  Per-board snapshots are continuous between records. Every accepted COMMIT
  has a stage and verification in its own epoch. Every accepted rollback has
  an earlier exact verified image on that board.
- Batch reports and audits are invariant over ten seeded permutations each
  with altered clocks. Original and shuffled/clock-altered/blank-line CLI inputs
  produce byte-identical reports/audits. All batch rows and incident lists
  combine exactly into the full report, and every total sums correctly.
- Transport accounting and incident projection match the primary report;
  conflict exclusion occurs before all epoch effects. The 13-event R2-to-R3
  incident delta was checked against the unchanged archived report.

Current artifact SHA-256 values:

| Artifact | SHA-256 |
| --- | --- |
| batch-1-report.json | `9129c654315a2330ef7a817ad7a803767c65b71105c945891d929b34b41d3d40` |
| batch-1-audit.json | `51ee421ddc006f3e86a418cd86d58fceb0180501afaab54fd989e65555518bac` |
| batch-2-report.json | `8cfab0da3b50a0f2ae0acc0a5ac25d76faa63ac6c4897f3f7df9be5335c1fa07` |
| batch-2-audit.json | `528cd9f65d03d1cde03d2510c0c3360550fee89d540b624eb114e176d7dfe2a1` |
| batch-3-report.json | `70b6638cd12163ffe439db336a60bde947e234a6b21a1b4b130abd8707f4e487` |
| batch-3-audit.json | `95d144a07924ecee5bd3d65b2ed6459026ca1330844e318e09cf53564d88e36d` |
| visible-report.json | `7f9833813e072dbcba508bc26d1144f2ad8480e8a309d0c57aad225341244383` |
| visible-audit.json | `b28d3f79034868197b1b49d6478dab1eb9ab9d4b66ff983855b84588939923e4` |
| operations-notes.json | `cd4c3b1aaa913d69029316485f610c00c3963d795e4a1fed5ea47063c383abae` |
| operations-corrections.json | `798cd712ada41a0d2f33f23667c35e22742bbe3ef9265c575348679e3a1095cd` |

The full artifacts are reproducible with
`python3 reconcile.py --input data/visible.jsonl --output audit/visible-report.json --audit-output audit/visible-audit.json`.
Earlier scoped regeneration snippets now use R3; batch 3 uses `range(129, 193)`
and `batch-3` filenames. Do not overwrite revision archives when regenerating.

### Carry forward

No batch 3 implementation tasks, failing tests, or unresolved revision conflicts
remain. R3 resolves the earlier epoch-state question; exact-pair rollback is
explicit. Missing-baseline fallback and missing-stage VERIFY precedence remain
as documented, and general malformed-input semantics remain outside the supplied
contract. The complete visible corpus is reconciled under current rules; its
totals are contract-derived, not an independent expected-results oracle.
Keep the current 48-note file authoritative, retain the invalidation ledger and
revision archives for later audit, and apply any subsequent explicit revisions
to every affected batch. No network access, new dependencies, or commits occurred.

## Phase 5: final integration and requested CLI output (2026-11-06)

Reviewed the integrated `reconcile.py` pipeline and its ingestion, state-machine,
and report modules against the final R3 contract. Production reconciliation
contains no board-, ID-, digest-, or fixture-specific outcomes and reads only
the input selected through the CLI. No further production changes were needed.

Added `tests/test_unseen.py` with two regressions using newly generated UUID
identifiers and image digests, independently of the public/visible fixtures.
The end-to-end CLI case exercises mixed schemas, clock skew, transport replay,
verification revocation, consumed commits, multiple pending transactions,
epoch gaps, null transaction IDs, and exact rollback history. A second case
checks global cross-board conflicts and board-local rollback authorization.
Both compare exact contract-derived output, including the JSON field sets.

Ran `TMPDIR="$PWD/.test-tmp" python3 -m unittest discover -s tests -v`:
all 68 tests pass, including the supplied public test and both new unseen-event
regressions. Temporary test files were kept inside the repository and removed.

Ran the requested command:
`python reconcile.py --input data/visible.jsonl --output analysis.json`.
This environment has no `python` executable, so the command used the temporary
shell function `python() { command python3 "$@"; }`; no interpreter installation
or persistent wrapper was created.

`analysis.json` has exactly the required primary report shape and sort order,
with 192 boards, 150 applied commits, 16 accepted rollbacks, 384 duplicate
replays, 38 conflicted IDs, and 502 incidents. It is byte-identical to the
current R3 `audit/visible-report.json`. SHA-256:
`7f9833813e072dbcba508bc26d1144f2ad8480e8a309d0c57aad225341244383`.

No unfinished integration tasks remain. R3 and the retained R2 rules are
unchanged; current operational values and their explicit correction history
remain preserved. No hidden evaluator files were inspected, and no network
access, dependencies, or commits were used.
