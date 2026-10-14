"""Evaluate the frozen holdout-v1 hybrid pipeline against blinded human labels."""

from __future__ import annotations

import csv
import json
import math
import random
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
INTERIM = ROOT / "data" / "interim"
RESULTS = ROOT / "results" / "validation" / "holdout_v1" / "final_evaluation"
HUMAN = INTERIM / "holdout_human_v1_90_labels.csv"
KEY = INTERIM / "holdout_human_v1_90_key.csv"
PREDICTIONS = INTERIM / "holdout_pipeline_v1_predictions.csv"
SCREENING = INTERIM / "holdout_screening_v1_240.csv"
BOOTSTRAP_SEED = 20261014
BOOTSTRAP_REPLICATES = 20_000
PROBLEMATIC = "confirmed_missing_problematic"
PREDICTION_STRATA = ["predicted_problematic", "pipeline_abstention", "predicted_non_problematic"]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def ratio(numerator: float, denominator: float) -> float | None:
    return numerator / denominator if denominator else None


def wilson(successes: int, total: int) -> tuple[float, float]:
    if total == 0:
        return (math.nan, math.nan)
    z = 1.959963984540054
    p = successes / total
    denominator = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denominator
    half = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    return (center - half, center + half)


def percentile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    position = probability * (len(ordered) - 1)
    low = math.floor(position)
    high = math.ceil(position)
    if low == high:
        return ordered[low]
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def interval(values: list[float]) -> list[float]:
    return [percentile(values, 0.025), percentile(values, 0.975)]


def weighted_cells(rows: Iterable[dict[str, object]], weight_field: str) -> dict[str, float]:
    cells = defaultdict(float)
    for row in rows:
        stratum = str(row["prediction_stratum"])
        human_positive = bool(row["human_problematic"])
        cells[f"{stratum}:{'problematic' if human_positive else 'non_problematic'}"] += float(row[weight_field])
    return dict(cells)


def metrics_from_cells(cells: dict[str, float]) -> dict[str, float | None]:
    tp = cells.get("predicted_problematic:problematic", 0.0)
    fp = cells.get("predicted_problematic:non_problematic", 0.0)
    fn = cells.get("predicted_non_problematic:problematic", 0.0)
    tn = cells.get("predicted_non_problematic:non_problematic", 0.0)
    abstain_positive = cells.get("pipeline_abstention:problematic", 0.0)
    abstain_negative = cells.get("pipeline_abstention:non_problematic", 0.0)
    return {
        "true_positive": tp,
        "false_positive": fp,
        "false_negative": fn,
        "true_negative": tn,
        "abstained_problematic": abstain_positive,
        "abstained_non_problematic": abstain_negative,
        "precision": ratio(tp, tp + fp),
        "end_to_end_recall": ratio(tp, tp + fn + abstain_positive),
        "covered_case_recall": ratio(tp, tp + fn),
        "negative_predictive_value": ratio(tn, tn + fn),
        "covered_case_accuracy": ratio(tp + tn, tp + fp + fn + tn),
        "problematic_prevalence": ratio(tp + fn + abstain_positive, sum(cells.values())),
    }


def bootstrap(rows: list[dict[str, object]]) -> dict[str, list[float]]:
    by_stratum = {
        stratum: [row for row in rows if row["prediction_stratum"] == stratum]
        for stratum in PREDICTION_STRATA
    }
    rng = random.Random(BOOTSTRAP_SEED)
    screening_metrics = defaultdict(list)
    population_metrics = defaultdict(list)
    for _ in range(BOOTSTRAP_REPLICATES):
        draw: list[dict[str, object]] = []
        for stratum, members in by_stratum.items():
            if stratum == "predicted_problematic":
                draw.extend(members)  # All five predicted positives were reviewed.
            else:
                draw.extend(members[rng.randrange(len(members))] for _ in members)
        for name, bundle in [
            ("screening", metrics_from_cells(weighted_cells(draw, "phase2_weight"))),
            ("population", metrics_from_cells(weighted_cells(draw, "final_sampling_weight"))),
        ]:
            target = screening_metrics if name == "screening" else population_metrics
            for metric in ["end_to_end_recall", "covered_case_recall", "negative_predictive_value", "problematic_prevalence"]:
                value = bundle[metric]
                if value is not None:
                    target[metric].append(float(value))
    return {
        f"screening_{metric}": interval(values)
        for metric, values in screening_metrics.items()
    } | {
        f"eligible_population_{metric}": interval(values)
        for metric, values in population_metrics.items()
    }


def main() -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    human = {row["human_review_id"]: row for row in read_csv(HUMAN)}
    key = read_csv(KEY)
    predictions = {row["review_id"]: row for row in read_csv(PREDICTIONS)}
    screening = read_csv(SCREENING)
    if len(human) != 90 or len(key) != 90 or set(human) != {row["human_review_id"] for row in key}:
        raise ValueError("Human labels and private key must contain the same 90 unique cases")
    if len(screening) != 240 or len(predictions) != 240:
        raise ValueError("Frozen screening and prediction files must each contain 240 cases")

    rows: list[dict[str, object]] = []
    for private in key:
        label = human[private["human_review_id"]]
        prediction = predictions[private["review_id"]]
        if private["pipeline_decision"] != prediction["pipeline_decision"]:
            raise ValueError(f"Prediction mismatch for {private['review_id']}")
        phase2_probability = float(private["phase2_inclusion_probability"])
        rows.append(
            {
                **private,
                "pipeline_stage": prediction["pipeline_stage"],
                "human_classification": label["manual_classification"],
                "human_problematic": label["manual_classification"] == PROBLEMATIC,
                "reviewer_id": label["reviewer_id"],
                "evidence_note": label["evidence_note"],
                "access_issue": label["access_issue"],
                "phase2_weight": 1 / phase2_probability,
                "final_sampling_weight": float(private["final_sampling_weight"]),
            }
        )

    observed_labels = Counter(str(row["human_classification"]) for row in rows)
    observed_binary = Counter(
        (str(row["prediction_stratum"]), bool(row["human_problematic"])) for row in rows
    )
    screening_cells = weighted_cells(rows, "phase2_weight")
    population_cells = weighted_cells(rows, "final_sampling_weight")
    screening_metrics = metrics_from_cells(screening_cells)
    population_metrics = metrics_from_cells(population_cells)
    uncertainty = bootstrap(rows)

    positive_successes = observed_binary[("predicted_problematic", True)]
    positive_total = sum(count for (stratum, _), count in observed_binary.items() if stratum == "predicted_problematic")
    negative_problematic = observed_binary[("predicted_non_problematic", True)]
    negative_total = sum(count for (stratum, _), count in observed_binary.items() if stratum == "predicted_non_problematic")
    abstain_problematic = observed_binary[("pipeline_abstention", True)]
    abstain_total = sum(count for (stratum, _), count in observed_binary.items() if stratum == "pipeline_abstention")
    precision_wilson = wilson(positive_successes, positive_total)
    negative_problematic_wilson = wilson(negative_problematic, negative_total)
    abstain_problematic_wilson = wilson(abstain_problematic, abstain_total)

    stage_diagnostics = []
    for stage in sorted({str(row["pipeline_stage"]) for row in rows}):
        members = [row for row in rows if row["pipeline_stage"] == stage]
        stage_diagnostics.append(
            {
                "pipeline_stage": stage,
                "reviewed_n": len(members),
                "reviewed_problematic_n": sum(bool(row["human_problematic"]) for row in members),
                "reviewed_problematic_rate": sum(bool(row["human_problematic"]) for row in members) / len(members),
                "phase2_weighted_problematic_total_in_240": sum(
                    float(row["phase2_weight"]) for row in members if row["human_problematic"]
                ),
            }
        )

    false_negative_origins = Counter(
        (str(row["pipeline_stage"]), str(row["pipeline_classification"]))
        for row in rows
        if row["prediction_stratum"] == "predicted_non_problematic" and row["human_problematic"]
    )
    full_prediction_counts = Counter(
        "abstain" if row["pipeline_decision"] == "abstain" else "classified"
        for row in predictions.values()
    )
    full_stage_counts = Counter(row["pipeline_stage"] for row in predictions.values())
    coverage = full_prediction_counts["classified"] / len(predictions)
    abstention_rate = full_prediction_counts["abstain"] / len(predictions)
    llm_review_rate = full_stage_counts["llm_semantic_review"] / len(predictions)

    summary = {
        "reference_standard": "independent single-reviewer blinded human labels",
        "reviewed_cases": len(rows),
        "human_label_counts": dict(sorted(observed_labels.items())),
        "observed_by_prediction_stratum": {
            stratum: {
                "reviewed": sum(count for (name, _), count in observed_binary.items() if name == stratum),
                "human_problematic": observed_binary[(stratum, True)],
                "human_non_problematic": observed_binary[(stratum, False)],
            }
            for stratum in PREDICTION_STRATA
        },
        "known_pipeline_operating_characteristics": {
            "screening_cases": len(predictions),
            "classification_coverage": coverage,
            "abstention_rate": abstention_rate,
            "llm_review_rate": llm_review_rate,
            "maximum_human_workload_reduction_if_only_abstentions_are_reviewed": coverage,
        },
        "screening_sample_240_design_weighted": {
            "estimated_cells": screening_cells,
            "metrics": screening_metrics,
            "bootstrap_95_percentile": {
                metric.removeprefix("screening_"): value
                for metric, value in uncertainty.items()
                if metric.startswith("screening_")
            },
        },
        "eligible_population_design_weighted_exploratory": {
            "estimated_cells": population_cells,
            "estimated_total_from_weights": sum(population_cells.values()),
            "known_eligible_frame_total": 38_833,
            "metrics": population_metrics,
            "bootstrap_95_percentile": {
                metric.removeprefix("eligible_population_"): value
                for metric, value in uncertainty.items()
                if metric.startswith("eligible_population_")
            },
        },
        "direct_stratum_intervals": {
            "predicted_positive_precision_wilson_95": list(precision_wilson),
            "predicted_negative_problematic_rate_wilson_95": list(negative_problematic_wilson),
            "abstention_problematic_rate_wilson_95": list(abstain_problematic_wilson),
        },
        "false_negative_origins_in_reviewed_cases": [
            {"pipeline_stage": stage, "pipeline_classification": label, "count": count}
            for (stage, label), count in sorted(false_negative_origins.items())
        ],
        "stage_diagnostics": stage_diagnostics,
        "bootstrap": {
            "method": "stratified nonparametric bootstrap within phase-2 prediction strata; predicted-positive census held fixed",
            "seed": BOOTSTRAP_SEED,
            "replicates": BOOTSTRAP_REPLICATES,
            "population_intervals_are_approximate": True,
        },
        "preregistered_gate": {
            "precision_threshold": 0.80,
            "recall_threshold": 0.80,
            "point_estimate_gate_passed": bool(
                screening_metrics["precision"] is not None
                and screening_metrics["precision"] >= 0.80
                and screening_metrics["end_to_end_recall"] is not None
                and screening_metrics["end_to_end_recall"] >= 0.80
            ),
        },
    }

    cases_path = RESULTS / "reviewed_cases_with_predictions.csv"
    case_fields = [
        "human_review_id", "review_id", "id", "sampling_stratum", "prediction_stratum",
        "pipeline_stage", "pipeline_decision", "pipeline_classification",
        "human_classification", "human_problematic", "phase1_inclusion_probability",
        "phase2_inclusion_probability", "phase2_weight", "final_sampling_weight",
        "reviewer_id", "evidence_note", "access_issue",
    ]
    with cases_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=case_fields)
        writer.writeheader()
        writer.writerows({field: row[field] for field in case_fields} for row in rows)

    confusion_path = RESULTS / "estimated_screening_binary_outcomes.csv"
    with confusion_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["pipeline_outcome", "human_problematic_estimated", "human_non_problematic_estimated"])
        writer.writeheader()
        for stratum in PREDICTION_STRATA:
            writer.writerow(
                {
                    "pipeline_outcome": stratum,
                    "human_problematic_estimated": screening_cells.get(f"{stratum}:problematic", 0.0),
                    "human_non_problematic_estimated": screening_cells.get(f"{stratum}:non_problematic", 0.0),
                }
            )

    diagnostics_path = RESULTS / "stage_diagnostics.csv"
    with diagnostics_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(stage_diagnostics[0]))
        writer.writeheader()
        writer.writerows(stage_diagnostics)

    (RESULTS / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    recall_ci = summary["screening_sample_240_design_weighted"]["bootstrap_95_percentile"]["end_to_end_recall"]
    prevalence_ci = summary["screening_sample_240_design_weighted"]["bootstrap_95_percentile"]["problematic_prevalence"]
    report = f"""# Holdout-v1 final evaluation

## Main result

The frozen hybrid pipeline does **not** pass the preregistered gate for automatic classification. All {positive_successes} predicted-positive cases were confirmed as problematic, for observed precision of **{screening_metrics['precision']:.1%}** (Wilson 95% CI {precision_wilson[0]:.1%}–{precision_wilson[1]:.1%}). However, the design-weighted end-to-end recall in the 240-case screening sample is only **{screening_metrics['end_to_end_recall']:.1%}** (stratified-bootstrap 95% interval {recall_ci[0]:.1%}–{recall_ci[1]:.1%}).

The pipeline therefore produces a small, high-yield shortlist, but it does not find most problematic references.

## Human labels by frozen prediction stratum

| Frozen outcome | Reviewed | Human problematic | Human non-problematic | Observed problematic rate |
|---|---:|---:|---:|---:|
| Predicted problematic | {positive_total} | {positive_successes} | {positive_total-positive_successes} | {positive_successes/positive_total:.1%} |
| Predicted non-problematic | {negative_total} | {negative_problematic} | {negative_total-negative_problematic} | {negative_problematic/negative_total:.1%} |
| Pipeline abstention | {abstain_total} | {abstain_problematic} | {abstain_total-abstain_problematic} | {abstain_problematic/abstain_total:.1%} |

The human reviewer found problematic references in **{negative_problematic}/{negative_total} ({negative_problematic/negative_total:.1%})** of sampled predicted negatives (Wilson 95% CI {negative_problematic_wilson[0]:.1%}–{negative_problematic_wilson[1]:.1%}) and **{abstain_problematic}/{abstain_total} ({abstain_problematic/abstain_total:.1%})** of sampled abstentions (Wilson 95% CI {abstain_problematic_wilson[0]:.1%}–{abstain_problematic_wilson[1]:.1%}).

## Design-weighted screening estimate

Inverse-probability weighting estimates approximately {screening_cells['predicted_non_problematic:problematic']:.1f} problematic cases among the 187 predicted negatives and {screening_cells['pipeline_abstention:problematic']:.1f} among the 48 abstentions. Together with the five detected cases, the estimated problematic prevalence in the 240-case screening sample is **{screening_metrics['problematic_prevalence']:.1%}** (bootstrap 95% interval {prevalence_ci[0]:.1%}–{prevalence_ci[1]:.1%}).

- Classification coverage: **{coverage:.1%}**.
- Abstention rate: **{abstention_rate:.1%}**.
- Cases routed to LLM review: **{llm_review_rate:.1%}**.
- Covered-case recall, excluding abstentions from the denominator: **{screening_metrics['covered_case_recall']:.1%}**.
- End-to-end recall, counting missed positives in both negative predictions and abstentions: **{screening_metrics['end_to_end_recall']:.1%}**.

## Error localization

Nine of the ten reviewed negative predictions that the human labeled problematic came from the deterministic `expected_absence_move_or_delete` rule. One came from an LLM `expected_absence_create` classification. Another six human-positive cases occurred among abstentions: four deterministic abstentions and two LLM abstentions. The broad lifecycle rule is therefore the largest single observed source of missed positives, but abstention also contributes materially to low end-to-end recall.

## Interpretation

The pipeline fails the frozen requirement that both precision and recall reach 0.80. It should not supply final labels for all `exists_at_anchor = 0` cases, and reviewing only its positive shortlist would miss most problematic references. The current result supports a narrower claim: longitudinal evidence can identify a small set of high-confidence problematic cases, while broad deterministic explanations of absence require revision and new held-out validation.

The eligible-population estimates in `summary.json` use the complete two-phase weights. Their bootstrap intervals are approximate because only the 90 phase-2 cases have human labels.
"""
    (RESULTS / "FINAL_EVALUATION.md").write_text(report, encoding="utf-8")
    print(report)
    print(f"Summary: {RESULTS / 'summary.json'}")


if __name__ == "__main__":
    main()
