# Hybrid longitudinal classifier: implementation status

## Purpose

This iteration implements the recommendation derived from the evidence-equivalent
error analysis. The target is not to infer a defect from `exists_at_anchor = 0`.
It is to classify the semantic explanation for a reference using temporal,
repository-boundary, and task evidence, while allowing abstention.

The original H001–H090 records are development data for this iteration. They
must not be reported as a held-out evaluation of the revised pipeline.

## Implemented components

1. `src/build_longitudinal_evidence.py`
   - retrieves the task artifact at the anchor SHA;
   - checks literal and resolved paths;
   - scans the full anchor tree for same-basename candidates;
   - retrieves the anchor commit message and exact-path history;
   - relates path-history commits to the anchor;
   - records repository languages, explicit repository mentions, and evidence gaps;
   - caches stable GitHub responses and retries transient failures;
   - excludes human labels, LLM labels, `task_done`, and `exists_at_anchor` from the packet.

2. `src/classify_reference_rules.py`
   - resolves only high-confidence structural cases;
   - distinguishes existence, patterns, explicit external repositories,
     lifecycle retirement, and creation followed by post-anchor history;
   - abstains on inaccessible evidence and bare ambiguous filenames;
   - routes all other cases to semantic LLM review.

3. `src/prepare_hybrid_judge_batch.py`
   - creates three disjoint outputs: deterministic decisions, abstentions, and
     a frozen LLM queue;
   - records hashes of the evidence, prompt, and JSON schema;
   - reports rule coverage, pre-LLM abstention, and LLM queue rates;
   - does not call a model.

4. `validation/LLM_JUDGE_PROMPT_LONGITUDINAL_V2.md` and
   `validation/llm_judge_output_schema_v2.json`
   - define the semantic stage, revised taxonomy, evidence requirements, and
     explicit abstention.

5. `validation/PROTOCOL_V2_LONGITUDINAL.md`
   - freezes the construct, evidence contract, evaluation plan, and decision gates.

## H025 audit correction and pilot

Historical evidence at anchor `24a5afc6` shows that the same squashed commit
contains the explicit change `remove-gmg-stokes-solver` and states that GMG
tests and fixtures were deleted. Its archived task 2.1 explicitly deletes
`TESTS/DisabledBenchmarks/*Gmg*` sources and fixtures.

Therefore H025 is `expected_absence_move_or_delete`, not
`expected_absence_create` and not `confirmed_missing_problematic`.

The implemented longitudinal pilot routes H025 as:

- decision: `classified`;
- classification: `expected_absence_move_or_delete`;
- rule: `R5_LIFECYCLE_RETIRE`;
- LLM call required: no.

This semantic correction does not change the binary confusion matrix because
H025 remains non-problematic. The accessible binary matrix remains
`[[46, 6], [0, 5]]`, so positive precision remains `5/11 = 45.5%`.

## Verification completed

- Eight automated unit tests pass.
- All new Python modules compile.
- The H025 evidence retrieval succeeded against the pinned public GitHub commit.
- The H025 hybrid batch contains one deterministic decision, zero abstentions,
  and zero LLM-queue records.
- The corrected human-label file is written as a new version; the source file is preserved.
- The false-positive audit workbook was regenerated and inspected without spreadsheet errors.

## Next confirmatory step

Freeze this implementation before drawing a new held-out sample. Then:

1. sample new `exists_at_anchor = 0` references with documented inclusion probabilities;
2. produce label-free longitudinal evidence packets;
3. route cases through rules, abstention, and the frozen LLM prompt;
4. obtain human labels independently and blind to pipeline decisions;
5. report precision, recall, uncertainty intervals, coverage, abstention, and
   human-review workload reduction;
6. allow automatic final classification only if both precision and recall meet
   the pre-registered 0.80 threshold.

Until that held-out evaluation is complete, the revised pipeline is a validated
implementation and development result, not evidence that population-scale LLM
classification is reliable.
