# Same-reviewer retest and GPT-6 Luna comparison

## Purpose

This phase measures two distinct questions:

1. How stable is the human classification when the same reviewer evaluates the same 90 cases again without seeing the first-round labels?
2. On the same cases and evidence, how does a deterministic-plus-LLM pipeline compare with an LLM-only pipeline?

The second human round is a test-retest assessment. It does not estimate inter-rater reliability and must not be described as an independent second-reviewer reference.

## Human round 2

- Population: the same 90 cases used in human round 1.
- Presentation: newly randomized order and new `R2-xxx` identifiers.
- Blinding: round-1 identifiers, round-1 answers, deterministic decisions, LLM decisions, routing stages, and model rationales are hidden.
- Taxonomy: unchanged eight-class taxonomy from round 1.
- Required fields: reviewer, classification, factual evidence note, and access issue when applicable.
- The reviewer must classify each case anew and must not consult the first workbook or an LLM.

## Human stability analysis

The eight classes are also collapsed into three states:

- `problematic`: `confirmed_missing_problematic`
- `nonproblematic`: `confirmed_exists`, `expected_absence_create`, `expected_absence_move_or_delete`, `external_repository_reference`, and `non_file_reference`
- `unknown`: `ambiguous_reference` and `inaccessible_or_invalid`

Report:

- exact eight-class agreement;
- three-state agreement;
- Cohen's kappa;
- Gwet's AC1 as a robustness measure for class imbalance;
- a transition table from round 1 to round 2;
- the number and proportion of cases that remain unknown.

For binary problem detection, the primary reference set contains cases whose three-state human label is identical in both rounds. Stable `unknown` cases are retained for coverage reporting but excluded from precision, recall, specificity, NPV, accuracy, and F1. Cases whose three-state label changes between rounds are reported as unstable and excluded from the primary diagnostic-performance analysis.

For exact semantic classification, the primary reference set contains only cases with the same eight-class label in both human rounds.

Sensitivity analyses compute system metrics against round 1 and round 2 separately. No disagreement is resolved after inspecting model predictions.

## GPT-6 Luna arms

Both arms use:

- model: `gpt-6-luna`;
- reasoning effort: `high`;
- one independent response per case;
- the same frozen evidence bundle;
- the same classification taxonomy, prompt instructions, and structured-output schema;
- no access to human labels or to the other arm's output.

### Arm A: deterministic plus Luna

Apply the frozen deterministic rules first. Preserve a deterministic decision when a rule returns a terminal classification. Send only routed or unresolved cases to GPT-6 Luna. Preserve explicit abstentions.

### Arm B: Luna only

Send all 90 cases directly to GPT-6 Luna. Do not expose deterministic features, rule decisions, routing labels, or Arm A outputs.

## Comparison

The architecture comparison is paired because both arms evaluate the same cases.

Primary binary outcomes on the stable human reference set:

- precision, recall, F1, specificity, NPV, and balanced accuracy for `problematic`;
- coverage and abstention rate;
- selective accuracy among classified cases.

Semantic outcomes on the exact-stable reference set:

- exact eight-class agreement;
- macro-F1;
- per-class recall and confusion matrix.

Report both design-weighted estimates, using the frozen phase-2 sampling weights, and unweighted sample results. Use paired bootstrap confidence intervals. Use McNemar's test only on decisive cases classified by both arms and interpret it cautiously when discordant counts are small.

## Resource comparison

For each arm record:

- number of LLM calls;
- input, cached-input, reasoning, and output tokens when available;
- wall-clock time;
- estimated API cost under the price in effect on the execution date.

## Freeze requirements

Before reading round-2 answers, preserve hashes for:

- the round-2 blinded workbook source and private ID key;
- the evidence bundle;
- deterministic rule code and configuration;
- prompt and output schema;
- model ID, reasoning effort, and execution parameters.

Record the execution timestamp and the model identifier returned by the API. Do not revise prompts, rules, or thresholds after inspecting round-2 labels.
