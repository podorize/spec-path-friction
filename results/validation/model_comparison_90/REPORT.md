# GPT-6 Sol versus GPT-6 Luna: paired comparison on H001–H090

Both models received the same 90 leakage-free records, frozen prompt, output schema, reasoning setting (`low`), and isolated read-only execution protocol. The reference labels are the final human decisions after adjudication.

## Exact semantic classification

| Model | Accessible cases | Exact agreement | Cohen's kappa | Macro-F1 |
|---|---:|---:|---:|---:|
| GPT-6 Sol | 86 | 66/86 (76.7%) | 0.691 | 0.673 |
| GPT-6 Luna | 86 | 61/86 (70.9%) | 0.626 | 0.573 |
| GPT-6 Astra | 86 | 64/86 (74.4%) | 0.664 | 0.692 |

For the full 90 cases, including inaccessible records, Sol achieved 66/90 (73.3%) and Luna 61/90 (67.8%). The collapsed full-taxonomy results were 71/90 (78.9%) for Sol and 68/90 (75.6%) for Luna.

## Target binary decision: problematic missing versus other missing cases

The primary operational target is whether an unresolved literal path remains `confirmed_missing_problematic`. Restricting the comparison to the 57 accessible cases in the two missing strata:

| Model | Accuracy | Precision | Recall | F1 | Confusion matrix (non-problematic, problematic) |
|---|---:|---:|---:|---:|---|
| GPT-6 Sol | 92.98% | 0.60 | 0.60 | 0.60 | `[[50, 2], [2, 3]]` |
| GPT-6 Luna | 85.96% | 0.286 | 0.40 | 0.333 | `[[47, 5], [3, 2]]` |
| GPT-6 Astra | 92.98% | 0.60 | 0.60 | 0.60 | `[[50, 2], [2, 3]]` |

The human reference contains only five problematic cases in this subset, so these estimates are imprecise. Nevertheless, Luna produced more false positives and missed more problematic cases than Sol in this target decision.

## Paired outcome

Across all 90 final labels:

- both models agreed with the human reference on 54 cases;
- Sol was correct and Luna incorrect on 12 cases;
- Luna was correct and Sol incorrect on 7 cases;
- neither was correct on 17 cases.

For Astra versus Sol, both were correct on 62 cases; Sol was correct alone on 4 cases; Astra was correct alone on 2 cases; and neither was correct on 22 cases.

The models produced the same fine-grained label on 66/90 cases.

## Decision

GPT-6 Luna is substantially cheaper, but it should not replace GPT-6 Sol for the primary large-scale classification under the current protocol. Sol performed better on the exact semantic task and, more importantly, on the binary decision that the study intends to extrapolate. GPT-6 Astra did not improve over Sol on this sample: it was slightly worse on exact agreement and tied Sol on the binary target. Luna remains useful as a cost-sensitive secondary condition or as a first-pass screen followed by Sol review of low-confidence cases.

The comparison is an evaluation result, not a claim that either model is an absolute gold standard. The sample is small, the problematic class is rare, and the reference is based on one human adjudicator.

## Artifacts

- Luna raw outputs: `data/interim/llm_human_90_luna_raw/`
- Luna results: `data/interim/llm_human_90_luna_results.csv`
- Luna run manifest: `data/interim/llm_human_90_luna_run_manifest.json`
- Luna adjudicated comparison: `results/validation/human_90_luna_adjudicated/`
- Astra raw outputs: `data/interim/llm_human_90_astra_raw/`
- Astra results: `data/interim/llm_human_90_astra_results.csv`
- Astra run manifest: `data/interim/llm_human_90_astra_run_manifest.json`
- Astra adjudicated comparison: `results/validation/human_90_astra_adjudicated/`
