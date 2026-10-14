# Human test-retest analysis

## Scope

The same reviewer classified the same 90 cases twice. Round 2 used a new order and new identifiers. This is an intra-rater test-retest analysis, not an inter-rater study.

## Main results

- Exact eight-class agreement: **56.7%** (51/90)
- Eight-class Cohen's kappa: **0.486**
- Eight-class Gwet's AC1: **0.509**
- Three-state agreement: **63.3%** (57/90)
- Three-state Cohen's kappa: **0.422**
- Three-state Gwet's AC1: **0.474**
- Stable decisive cases for primary binary evaluation: **42**
- Stable problematic cases: **6**
- Stable nonproblematic cases: **36**
- Stable unknown cases: **15**
- Unstable three-state cases: **33**

## Access sensitivity

Round 2 contains **13** access-issue records, including **11** described as temporary GitHub failures. Excluding those temporary failures, three-state agreement is **67.1%** across 79 cases. This is a sensitivity analysis, not a replacement for the prespecified full-sample result.

## Three-state transition matrix

| Round 1 | problematic | nonproblematic | unknown |
| --- | --- | --- | --- |
| problematic | 6 | 2 | 13 |
| nonproblematic | 2 | 36 | 14 |
| unknown | 0 | 2 | 15 |

## Exact-label transition matrix

| Round 1 | confirmed_exists | confirmed_missing_problematic | expected_absence_create | expected_absence_move_or_delete | external_repository_reference | non_file_reference | ambiguous_reference | inaccessible_or_invalid |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| confirmed_exists | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| confirmed_missing_problematic | 0 | 6 | 1 | 1 | 0 | 0 | 10 | 3 |
| expected_absence_create | 0 | 0 | 16 | 0 | 3 | 0 | 10 | 2 |
| expected_absence_move_or_delete | 0 | 2 | 0 | 8 | 0 | 0 | 0 | 1 |
| external_repository_reference | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 1 |
| non_file_reference | 0 | 0 | 0 | 0 | 0 | 8 | 0 | 0 |
| ambiguous_reference | 0 | 0 | 0 | 0 | 0 | 0 | 8 | 1 |
| inaccessible_or_invalid | 0 | 0 | 1 | 0 | 0 | 1 | 1 | 5 |

## Interpretation rule for system evaluation

Primary binary performance uses only stable decisive cases. Stable unknown cases contribute to coverage and abstention reporting but not binary diagnostic metrics. Three-state disagreements are retained as human-reference instability and are not adjudicated after seeing system predictions. Round-1-only and round-2-only analyses are secondary sensitivity checks.
