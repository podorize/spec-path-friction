# Evidence-equivalent pilot: GPT-6 Sol on 10 cases

The pilot reused ten cases from the original human-first sample: three `completed + exists`, three `completed + missing`, and four `open + missing`. The model received the task context plus pinned commit evidence: literal-path status, candidate-path content when available, and repository-tree basename search. Human labels, strata, adjudication notes, and `exists_at_anchor` were excluded.

## Result

| Metric | Result |
|---|---:|
| Valid JSON responses | 10/10 |
| Exact agreement | 10/10 (100%) |
| Cohen's kappa | 1.000 |
| Macro-F1 | 1.000 |

The first version of the evidence packet omitted repository-wide tree evidence and produced 9/10 agreement. The only disagreement was H004: the model returned `ambiguous_reference` because a 404 alone did not establish that no file with the same basename existed elsewhere. After adding the complete anchor-tree basename search, the model correctly returned `confirmed_missing_problematic`, matching the human adjudicated label.

## Interpretation

This is encouraging but not conclusive. Ten cases are too few for a reliable performance estimate, and the pilot cases were not selected to estimate corpus-wide prevalence. The result supports running the same evidence-equivalent protocol on all 90 cases.

## Artifacts

- Evidence packet: `data/interim/evidence_equivalent_pilot_10.jsonl`
- Input manifest: `data/interim/evidence_equivalent_pilot_10_manifest.json`
- LLM inputs: `data/interim/llm_judge_inputs_evidence_equivalent_pilot_10.jsonl`
- Raw outputs: `data/interim/llm_evidence_equivalent_pilot_10_raw/`
- Results: `data/interim/llm_evidence_equivalent_pilot_10_results.csv`
- Run manifest: `data/interim/llm_evidence_equivalent_pilot_10_run_manifest.json`
