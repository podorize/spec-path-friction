# Human–LLM comparison: H001–H090

## Design

- Human reference: R1 first-pass labels, frozen before the LLM run.
- LLM condition: one fresh ephemeral process per case, frozen prompt, structured JSON output, no human labels or sampling strata.
- Model: `gpt-6-sol`, reasoning effort `low`.
- Valid outputs: 90/90.
- Primary analysis: 86 semantically assessable cases. Four human `inaccessible_or_invalid` cases are reported only in the full-set sensitivity analysis because R1 had live URLs while the LLM received only the frozen record.

## Main results

| Scope | Exact agreement | Cohen's kappa | Macro-F1 | Disagreements |
|---|---:|---:|---:|---:|
| Primary semantic subset (n=86) | 66/86 (76.7%) | 0.691 | 0.674 | 20 |
| Full set (n=90) | 66/90 (73.3%) | 0.653 | 0.566 | 24 |
| Collapsed full taxonomy (n=90) | 68/90 (75.6%) | 0.640 | 0.539 | 22 |

Bootstrap 95% percentile intervals (5,000 case-level resamples):

- Primary agreement: 0.674–0.849; kappa: 0.571–0.800; macro-F1: 0.563–0.764.
- Full-set agreement: 0.644–0.822; kappa: 0.534–0.764; macro-F1: 0.474–0.643.

## Interpretation boundary

These are pre-adjudication measurements. The human labels are not assumed to be error-free, and the LLM is not used as the automatic gold standard. Every exact disagreement is exported for R1 adjudication while preserving both original labels. Final performance should be recomputed against the adjudicated labels.
