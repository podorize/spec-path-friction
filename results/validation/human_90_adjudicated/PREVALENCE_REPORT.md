# Stratified semantic prevalence estimate

The 90-case validation sample was balanced at 30 cases per stratum. Therefore, the raw proportion of `confirmed_missing_problematic` labels is not a corpus estimate. This analysis reweights the two unresolved strata by their population sizes in `openspec_code_refs.parquet`.

| Stratum | Population references | Sample | Problematic | Conservative rate | Known-only rate |
|---|---:|---:|---:|---:|---:|
| completed + missing | 34,227 | 30 | 3 | 10.0% | 10.0% |
| open + missing | 17,752 | 30 | 2 | 6.7% | 7.4% |

## Weighted estimate

- Conservative treatment, counting inaccessible cases as non-problematic: **8.9%** (bootstrap 95% interval 2.2%–17.6%).
- Known-only sensitivity, excluding inaccessible cases from the stratum denominator: **9.1%** (bootstrap 95% interval 2.2%–17.8%).

This estimate is exploratory. It is based on one human reviewer, 30 sampled cases per stratum, and an English-only validation sample. It should be presented as calibrated evidence about the meaning of literal non-resolution, not as a definitive gold-standard prevalence for the entire SpecMine corpus.
