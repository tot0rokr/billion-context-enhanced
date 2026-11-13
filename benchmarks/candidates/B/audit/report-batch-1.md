# Batch 1 report and audit decisions

The authority remains README.md contract R1. INC-00001 through INC-00064 and
operational notes are evidence for review, not contract revisions. The primary
report still contains exactly `boards`, `incidents`, and `totals`.

The optional audit sidecar records the state machine's actual execution order,
including baseline initialization before other board events. It must not be
sorted by diagnostic sequence: R1 uses reported timestamps within an epoch.
It projects the agreed event, decision, and before/after active-image fields;
timestamps, paths, runtime metadata, and pending internals do not appear.

Operation counters cover retained COMMIT and ROLLBACK trace rows only.
`attempted` counts those rows, `reported_success` counts their input success
flags, `accepted` counts state-machine acceptance, and `rejected` is attempted
minus accepted. An accepted operation can target an already active image;
acceptance must come from the decision, not an image inequality. Excluded ID
conflicts and discarded replay rows contribute no attempts. Conflicts appear
separately as projected `duplicate_conflict` incidents. Consequently operation
rejections need not equal the primary report's `rejected_events`, which counts
all incident reasons, including conflicts and non-operation failures.

The explanation map contains precisely the incident reasons present in the
primary report. Current explanations follow all twelve R1 rejection reasons.
Future explicit revisions that alter reason semantics must also update these
explanations; changing only the sidecar's revision label does not change rules.
In particular, failed VERIFY preserves an earlier verified flag under R1,
whereas successful mismatching VERIFY clears it; rollback history contains
exact board-local slot/digest pairs.

Current limitations remain those recorded in PHASE_NOTES.md: minimum replay
timestamp and sequence/ID timestamp ties are implementation decisions; missing
baseline handling is outside the promised input shape. The trace excludes
conflicted payload details, so use the original evidence when investigating a
conflict. The parent preserves the sixteen operational notes separately with
their exact text as audit-only evidence; they do not authorize state changes.
