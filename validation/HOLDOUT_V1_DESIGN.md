# Held-out validation v1: two-phase design

## Objective

Estimate whether the frozen hybrid longitudinal pipeline can identify genuinely
problematic missing references among OpenSpec references with
`exists_at_anchor = 0`, while controlling human-review cost.

The H001–H090 development cases and every earlier pilot or confirmation case
are excluded before sampling.

## Phase 1: pipeline screening

Draw 240 previously unused references:

- 120 with `task_done = 1`;
- 120 with `task_done = 0`.

Within each task-status stratum, eligible references are ordered by a seeded
hash and sampled without replacement. Eligibility requires English task
context with `langdetect` probability at least 0.90 and no detected foreign
script. The private key records the eligible frame size, sampling probability,
and inverse-probability weight for every selected reference.

Generate longitudinal evidence and apply the frozen pipeline without human
labels. Preserve deterministic decisions, LLM decisions, and abstentions.

## Phase 2: independent human reference

After all pipeline outputs are frozen, sample 90 of the 240 cases for human
review. Stratify by the pipeline result:

1. predicted `confirmed_missing_problematic`;
2. predicted non-problematic;
3. pipeline abstention or inaccessible evidence.

Take all members of a stratum when it has fewer cases than its target and
redistribute remaining review slots using a documented deterministic rule.
Record the realized phase-2 probability within every prediction stratum.
The final analysis weight is the inverse of the product of phase-1 and phase-2
inclusion probabilities.

The human workbook must hide task status, path-resolution state, sampling
stratum, pipeline output, confidence, and model rationale. Human labels and
evidence notes must be completed before opening the private prediction key.

## Primary outcomes

- precision and recall for `confirmed_missing_problematic`;
- Wilson or bootstrap uncertainty intervals;
- classification coverage and abstention rate;
- proportion of cases requiring LLM review;
- estimated reduction in human workload;
- inverse-probability-weighted estimates for the eligible population.

## Interpretation gates

Automatic final classification is supported only if both precision and recall
are at least 0.80, with uncertainty intervals reported. If this gate fails but
recall remains high, the pipeline may be evaluated as a triage instrument. The
development-set results are not combined with this held-out estimate.
