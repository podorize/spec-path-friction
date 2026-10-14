# Holdout-v1 final evaluation

## Main result

The frozen hybrid pipeline does **not** pass the preregistered gate for automatic classification. All 5 predicted-positive cases were confirmed as problematic, for observed precision of **100.0%** (Wilson 95% CI 56.6%–100.0%). However, the design-weighted end-to-end recall in the 240-case screening sample is only **10.3%** (stratified-bootstrap 95% interval 7.1%–16.8%).

The pipeline therefore produces a small, high-yield shortlist, but it does not find most problematic references.

## Human labels by frozen prediction stratum

| Frozen outcome | Reviewed | Human problematic | Human non-problematic | Observed problematic rate |
|---|---:|---:|---:|---:|
| Predicted problematic | 5 | 5 | 0 | 100.0% |
| Predicted non-problematic | 55 | 10 | 45 | 18.2% |
| Pipeline abstention | 30 | 6 | 24 | 20.0% |

The human reviewer found problematic references in **10/55 (18.2%)** of sampled predicted negatives (Wilson 95% CI 10.2%–30.3%) and **6/30 (20.0%)** of sampled abstentions (Wilson 95% CI 9.5%–37.3%).

## Design-weighted screening estimate

Inverse-probability weighting estimates approximately 34.0 problematic cases among the 187 predicted negatives and 9.6 among the 48 abstentions. Together with the five detected cases, the estimated problematic prevalence in the 240-case screening sample is **20.2%** (bootstrap 95% interval 12.4%–29.2%).

- Classification coverage: **80.0%**.
- Abstention rate: **20.0%**.
- Cases routed to LLM review: **21.7%**.
- Covered-case recall, excluding abstentions from the denominator: **12.8%**.
- End-to-end recall, counting missed positives in both negative predictions and abstentions: **10.3%**.

## Error localization

Nine of the ten reviewed negative predictions that the human labeled problematic came from the deterministic `expected_absence_move_or_delete` rule. One came from an LLM `expected_absence_create` classification. Another six human-positive cases occurred among abstentions: four deterministic abstentions and two LLM abstentions. The broad lifecycle rule is therefore the largest single observed source of missed positives, but abstention also contributes materially to low end-to-end recall.

## Interpretation

The pipeline fails the frozen requirement that both precision and recall reach 0.80. It should not supply final labels for all `exists_at_anchor = 0` cases, and reviewing only its positive shortlist would miss most problematic references. The current result supports a narrower claim: longitudinal evidence can identify a small set of high-confidence problematic cases, while broad deterministic explanations of absence require revision and new held-out validation.

The eligible-population estimates in `summary.json` use the complete two-phase weights. Their bootstrap intervals are approximate because only the 90 phase-2 cases have human labels.
