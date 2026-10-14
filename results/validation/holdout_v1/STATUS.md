# Held-out validation v1: current status

## Design and screening

- The hybrid pipeline and evaluation protocol were frozen before observing new human labels.
- All 330 references used in prior pilots and validation rounds were excluded.
- A new 240-reference screening sample was drawn from `exists_at_anchor = 0`:
  - 120 completed-task references;
  - 120 open-task references.
- The sample contains 240 unique SpecMine reference IDs and has zero overlap with prior samples.
- The eligible English-language frames contain 25,323 completed-task references and 13,510 open-task references.
- Phase-1 inclusion probabilities and inverse-probability weights are stored in the private key.

## Evidence and pipeline predictions

- Authenticated GitHub evidence collection completed for all 240 cases.
- Evidence gaps were recorded, rather than silently interpreted:
  - path history unavailable: 11 cases;
  - anchor commit unavailable: 3 cases;
  - repository tree unavailable: 3 cases.
- Frozen hybrid routing produced:
  - 148 deterministic rule decisions (61.67%);
  - 40 deterministic abstentions (16.67%);
  - 52 cases sent to semantic LLM review (21.67%).
- The LLM judge (`gpt-6-sol`, low reasoning) returned 52 valid structured responses out of 52 requests.
- The combined pipeline produced:
  - 5 predicted problematic cases;
  - 48 pipeline abstentions;
  - 187 predicted non-problematic cases.

## Independent human validation sample

- The frozen phase-2 sampler selected 90 cases:
  - all 5 predicted problematic cases;
  - 30 of 48 pipeline abstentions;
  - 55 of 187 predicted non-problematic cases.
- Phase-2 and combined inclusion probabilities and inverse-probability weights are stored only in the private key.
- The reviewer-facing workbook is blinded: it contains no pipeline prediction, routing stage, model output, sampling stratum, or weight.
- The completed workbook was imported with 90 unique IDs, no immutable-field changes, no blank required fields, and no invalid classifications.
- The human reference contains 21 `confirmed_missing_problematic` cases among the 90 reviewed records.

## Confirmatory result

- All 5 predicted-positive cases were confirmed as problematic: observed precision 100.0%, Wilson 95% CI 56.6%–100.0%.
- The reviewer also found 10 problematic cases among 55 sampled predicted negatives and 6 among 30 sampled abstentions.
- Phase-2 inverse-probability weighting estimates 34.0 problematic cases among the 187 predicted negatives and 9.6 among the 48 abstentions.
- Design-weighted end-to-end recall in the 240-case screening sample is 10.3%, with a stratified-bootstrap 95% interval of 7.1%–16.8%.
- The preregistered automatic-classification gate fails because recall is far below 0.80.
- Nine of the 10 reviewed negative predictions that the human labeled problematic came from the deterministic `expected_absence_move_or_delete` rule; one came from an LLM `expected_absence_create` classification.
- Six additional human-positive cases occurred among abstentions: four deterministic abstentions and two LLM abstentions.
- The full analysis is stored under `results/validation/holdout_v1/final_evaluation/`.

## Next step

Treat holdout v1 as the final evaluation of the frozen pipeline. Do not tune and
re-report performance on these 90 labels. Use the error analysis to define a
revised lifecycle rule, then evaluate that revised pipeline on a newly drawn
holdout if automatic classification remains the objective. The current pipeline
may be reported as producing a small high-yield shortlist, but not as a reliable
classifier or high-recall triage system.

## Frozen-design cautions

- The pipeline classified a large number of cases as
  `expected_absence_move_or_delete`; the human sample intentionally includes
  predicted-negative cases so false negatives from this rule can be measured.
- Only five cases were predicted problematic. All five are included in the
  human sample, but performance estimates for the positive prediction stratum
  will necessarily have wide uncertainty.
