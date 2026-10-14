# Development protocol v2: longitudinal reference classification

## Scope and status

This protocol was created after inspecting errors in H001–H090. Those records
are development data for this protocol, not a held-out evaluation set. A new
sample must be drawn only after the rules, prompt, evidence schema, model, and
metrics are frozen.

## Construct

The target construct is an implementation or traceability problem associated
with a code reference in an SDD task. Literal path absence at one commit is an
input signal, not the construct itself.

## Required evidence

Each record should contain, when available:

1. the task artifact as stored at the anchor commit;
2. the extracted task context and whether it matches the anchor snapshot;
3. literal and resolved-path observations at the anchor commit;
4. basename matches in the complete anchor tree;
5. commits touching the exact path and their relation to the anchor;
6. the anchor commit message, including explicit retirement or deletion text;
7. repository languages and explicit references to another repository;
8. retrieval status and missing-evidence fields.

## Revised taxonomy

| Label | Definition |
|---|---|
| `confirmed_exists` | The referenced local implementation exists at the anchor commit. |
| `confirmed_missing_problematic` | A pre-existing local file is required but absent without a supported lifecycle or repository-boundary explanation. |
| `expected_absence_create` | A new local file is planned or appears after the anchor. |
| `expected_absence_move_or_delete` | The path was moved, renamed, replaced, deleted, or retired. |
| `external_repository_reference` | The reference denotes a file affirmatively located in another repository. |
| `non_file_reference` | The reference denotes something other than one unique file. |
| `ambiguous_reference` | Available evidence does not support a safe decision. |
| `inaccessible_or_invalid` | Required evidence cannot be retrieved or validated. |

## Pipeline

1. Apply deterministic rules only when their prerequisites are present.
2. Send unresolved cases to the frozen LLM prompt.
3. Permit explicit abstention.
4. Human reviewers remain blind to model output in the held-out evaluation.
5. Report classification coverage in addition to agreement and class metrics.

## Evaluation

The held-out evaluation uses the two-phase design frozen in
`validation/HOLDOUT_V1_DESIGN.md`. Phase 1 draws a stratified probability
sample before any new human labels are observed. After the pipeline outputs are
frozen, Phase 2 samples the human-review subset by pipeline prediction, with
the realized conditional probability recorded for every case. Report precision
among predicted positives, error rates among predicted negatives, coverage,
abstention, and inverse-probability-weighted population estimates. Do not
present development-set performance as confirmatory evidence.

## Pre-registered interpretation gates

- Final automatic classification requires both precision and recall of at
  least 0.80 with uncertainty intervals reported.
- Triage use additionally requires a meaningful reduction in human review
  workload and a sufficiently high lower confidence bound for recall.
- If these gates fail, the study reports the pipeline as an error-analysis or
  prioritization instrument rather than a source of final labels.
