# Evidence batch 1 audit findings

Cases `INC-00001` through `INC-00064` correspond to `board-00001` through
`board-00064` in `data/visible.jsonl`. This batch provides evidence and
operational reporting notes, with no explicit revision to provisional R1.

## Reconciliation

The batch contains 662 transport rows. Global ID reconciliation retains
510 executable events, counts 128 equivalent replay rows, and excludes
24 rows belonging to 12 conflicting IDs. Each conflicting ID produces one
incident. Thus transport volume is not an action-attempt count.

| R1 result | Count |
| --- | ---: |
| Boards | 64 |
| Applied commits | 13 |
| Accepted rollbacks | 5 |
| Transition rejections | 246 |
| Duplicate-conflict incidents | 12 |
| Total rejected events/incidents | 258 |

The 144 retained COMMIT attempts include 139 events reporting success,
but only 13 commits satisfy R1's pending-image and verification checks.
The other commit classifications are 72 `commit_without_stage`,
28 `commit_mismatch`, 26 `commit_unverified`, and 5 `commit_failed`.

Reported timestamps remain the provisional execution order. In
`INC-00001`, the COMMIT with diagnostic sequence 28 executes before the
STAGE with sequence 7 and is rejected as `commit_without_stage`. The
audit preserves this actual execution order, including baseline initialization,
so sequence-sorted incident presentation is not mistaken for execution order.

Pending state still survives epoch advancement, and failed VERIFY still
preserves an existing verified flag. These are R1 decisions, not corrections
inferred from the new evidence. Exact `(slot, digest)` history remains the
sole rollback authorization rule.

## Audit artifact

`--audit-output` writes a separate artifact with `contract`, `summary`,
`transport`, `transitions`, `per_action`, and `reason_catalog`. The ordinary
report retains exactly `boards`, `incidents`, and `totals`.

`summary` includes the ordinary report totals plus `input_rows`,
`retained_events`, and `conflicted_rows`. Transport rows identify each global
ID's canonical location, disposition, raw row count, and replay count.
Transitions record actual execution order, reported success, accepted/rejected/
ignored disposition, rejection reason, active image and pending state before
and after execution, and whether verified history gained an image.

Per-action counters describe retained executed events. They distinguish
`reported_success` from `accepted`; neither equivalent transport copies nor
conflicting IDs count as action attempts. Rejection reasons are explained in
the reason catalog. Audit output contains no timestamps, paths, or runtime
metadata; event IDs and state snapshots support inspection without changing
the contract report.

## Operational notes and carry-forward

`operations-notes.json` preserves F01–F16 with their exact operation IDs,
case IDs, field names, and string values, including numeric-looking values.
They are reporting data only. No note changes state-machine behavior, and
an approved-rollback digest note cannot authorize an unverified image.

Eight additional audit tests cover transport/action accounting, execution
order, state effects, deterministic output, field projection, reason coverage,
exact note preservation, and the independence of rollback authorization from
operational notes. All eight pass with the integrated implementation.

No report/audit implementation work remains for this batch. The provisional
timestamp ordering, epoch retention, and failed-VERIFY flag behavior remain
available for a later explicit contract revision; none is assumed here.
