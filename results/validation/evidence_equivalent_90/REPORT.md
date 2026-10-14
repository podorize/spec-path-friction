# Evidence-equivalent evaluation: GPT-6 Sol on H001–H090

The same 90 cases were evaluated with the same human reference labels, but the model received a richer evidence packet: task context, pinned raw-file observations, candidate-path content where available, and repository-tree basename searches. Human labels, adjudication notes, private strata, and the numeric `exists_at_anchor` field were excluded.

## Semantic comparison

| Scope | Exact agreement | Cohen's kappa | Macro-F1 | Disagreements |
|---|---:|---:|---:|---:|
| Primary semantic subset (n=86) | 69/86 (80.2%) | 0.738 | 0.678 | 17 |
| Full set (n=90) | 70/90 (77.8%) | 0.711 | 0.631 | 20 |
| Collapsed full taxonomy (n=90) | 72/90 (80.0%) | 0.709 | 0.688 | 18 |

Compared with the previous record-only Sol condition (76.7% and κ=0.691 on the primary semantic subset), the evidence-equivalent condition improves exact agreement by 3.5 percentage points and κ by 0.047.

## Binary target: problematic missing

Among 57 accessible cases in the two unresolved strata, the human reference contains five `confirmed_missing_problematic` cases. The evidence-equivalent Sol condition produced:

- accuracy: **89.5%**;
- precision: **0.455**;
- recall: **1.000**;
- F1: **0.625**;
- confusion matrix `(non-problematic, problematic)`: `[[46, 6], [0, 5]]`.

The model found all five human-positive cases in this small sample, at the cost of six false positives. This makes it more appropriate as a high-recall screening instrument than as an automatic source of definitive labels.

## Interpretation

The increase after adding repository evidence supports the hypothesis that the earlier disagreement was partly caused by unequal information access. The result does not establish population-level accuracy: the problematic class is rare, there is one human evaluator, and the sample remains small.

## Artifacts

- Evidence packet: `data/interim/evidence_equivalent_90_augmented.jsonl`
- LLM inputs: `data/interim/llm_judge_inputs_evidence_equivalent_90.jsonl`
- Raw outputs: `data/interim/llm_evidence_equivalent_90_raw/`
- Results: `data/interim/llm_evidence_equivalent_90_results.csv`
- Run manifest: `data/interim/llm_evidence_equivalent_90_run_manifest.json`
- Detailed comparison: `results/validation/human_90_evidence_equivalent/`
