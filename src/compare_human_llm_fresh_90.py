"""Compare R1 first-pass labels with the isolated H001-H090 LLM run."""

from __future__ import annotations

import csv
import json
import math
import random
from collections import Counter
from pathlib import Path
from typing import Callable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
INTERIM = PROJECT_ROOT / "data" / "interim"
RESULTS = PROJECT_ROOT / "results" / "validation" / "human_90"

HUMAN_PATH = INTERIM / "validation_human_fresh_90_R1_initial.csv"
LLM_PATH = INTERIM / "llm_human_90_results.csv"
KEY_PATH = INTERIM / "validation_human_fresh_90_en_key.csv"
SOURCE_PATH = INTERIM / "validation_human_fresh_90_en.csv"

CASES_OUTPUT = RESULTS / "comparison_cases.csv"
DISAGREEMENTS_OUTPUT = RESULTS / "disagreements_for_adjudication.csv"
PER_CLASS_OUTPUT = RESULTS / "per_class_metrics.csv"
CONFUSION_OUTPUT = RESULTS / "confusion_matrix.csv"
COLLAPSED_CONFUSION_OUTPUT = RESULTS / "collapsed_confusion_matrix.csv"
METRICS_OUTPUT = RESULTS / "summary.json"
REPORT_OUTPUT = RESULTS / "REPORT.md"

LABELS = [
    "confirmed_exists",
    "confirmed_missing_problematic",
    "expected_absence_create",
    "expected_absence_move_or_delete",
    "non_file_reference",
    "ambiguous_reference",
    "inaccessible_or_invalid",
]

COLLAPSED_LABELS = [
    "exists",
    "problematic_missing",
    "expected_absence",
    "non_file_or_ambiguous",
    "inaccessible",
]

COLLAPSE = {
    "confirmed_exists": "exists",
    "confirmed_missing_problematic": "problematic_missing",
    "expected_absence_create": "expected_absence",
    "expected_absence_move_or_delete": "expected_absence",
    "non_file_reference": "non_file_or_ambiguous",
    "ambiguous_reference": "non_file_or_ambiguous",
    "inaccessible_or_invalid": "inaccessible",
}

BOOTSTRAP_SEED = 20261010
BOOTSTRAP_REPLICATES = 5_000


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def safe_div(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0


def metric_bundle(
    pairs: list[tuple[str, str]], labels: list[str]
) -> dict[str, object]:
    n = len(pairs)
    matches = sum(human == llm for human, llm in pairs)
    accuracy = safe_div(matches, n)
    human_counts = Counter(human for human, _ in pairs)
    llm_counts = Counter(llm for _, llm in pairs)
    expected = safe_div(
        sum(human_counts[label] * llm_counts[label] for label in labels), n * n
    )
    kappa = safe_div(accuracy - expected, 1 - expected)

    per_class: list[dict[str, object]] = []
    for label in labels:
        tp = sum(human == label and llm == label for human, llm in pairs)
        fp = sum(human != label and llm == label for human, llm in pairs)
        fn = sum(human == label and llm != label for human, llm in pairs)
        precision = safe_div(tp, tp + fp)
        recall = safe_div(tp, tp + fn)
        f1 = safe_div(2 * precision * recall, precision + recall)
        per_class.append(
            {
                "label": label,
                "human_support": human_counts[label],
                "llm_support": llm_counts[label],
                "true_positive": tp,
                "false_positive": fp,
                "false_negative": fn,
                "precision": precision,
                "recall": recall,
                "f1": f1,
            }
        )
    macro_f1 = safe_div(sum(float(row["f1"]) for row in per_class), len(labels))
    return {
        "n": n,
        "matches": matches,
        "accuracy": accuracy,
        "expected_agreement": expected,
        "cohen_kappa": kappa,
        "macro_f1": macro_f1,
        "per_class": per_class,
    }


def percentile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    position = probability * (len(ordered) - 1)
    low = math.floor(position)
    high = math.ceil(position)
    if low == high:
        return ordered[low]
    weight = position - low
    return ordered[low] * (1 - weight) + ordered[high] * weight


def bootstrap_intervals(
    pairs: list[tuple[str, str]], labels: list[str], seed_offset: int
) -> dict[str, list[float]]:
    rng = random.Random(BOOTSTRAP_SEED + seed_offset)
    buckets: dict[str, list[float]] = {
        "accuracy": [],
        "cohen_kappa": [],
        "macro_f1": [],
    }
    for _ in range(BOOTSTRAP_REPLICATES):
        sample = [pairs[rng.randrange(len(pairs))] for _ in pairs]
        metrics = metric_bundle(sample, labels)
        for metric in buckets:
            buckets[metric].append(float(metrics[metric]))
    return {
        f"{metric}_95_percentile": [
            percentile(values, 0.025),
            percentile(values, 0.975),
        ]
        for metric, values in buckets.items()
    }


def with_intervals(
    pairs: list[tuple[str, str]], labels: list[str], seed_offset: int
) -> dict[str, object]:
    result = metric_bundle(pairs, labels)
    result["bootstrap"] = {
        "seed": BOOTSTRAP_SEED + seed_offset,
        "replicates": BOOTSTRAP_REPLICATES,
        **bootstrap_intervals(pairs, labels, seed_offset),
    }
    return result


def binary_problematic(pairs: list[tuple[str, str]]) -> dict[str, object]:
    positive = "confirmed_missing_problematic"
    tp = sum(h == positive and m == positive for h, m in pairs)
    tn = sum(h != positive and m != positive for h, m in pairs)
    fp = sum(h != positive and m == positive for h, m in pairs)
    fn = sum(h == positive and m != positive for h, m in pairs)
    precision = safe_div(tp, tp + fp)
    recall = safe_div(tp, tp + fn)
    return {
        "positive_label": positive,
        "true_positive": tp,
        "true_negative": tn,
        "false_positive": fp,
        "false_negative": fn,
        "accuracy": safe_div(tp + tn, len(pairs)),
        "precision": precision,
        "recall": recall,
        "f1": safe_div(2 * precision * recall, precision + recall),
    }


def write_confusion(
    path: Path, pairs: list[tuple[str, str]], labels: list[str]
) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["human_label", *labels])
        writer.writeheader()
        for human_label in labels:
            writer.writerow(
                {
                    "human_label": human_label,
                    **{
                        llm_label: sum(
                            human == human_label and model == llm_label
                            for human, model in pairs
                        )
                        for llm_label in labels
                    },
                }
            )


def fmt_pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def fmt_ci(values: list[float]) -> str:
    return f"{values[0]:.3f}–{values[1]:.3f}"


def main() -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    human = {row["review_id"]: row for row in read_csv(HUMAN_PATH)}
    llm = {row["review_id"]: row for row in read_csv(LLM_PATH)}
    key = {row["review_id"]: row for row in read_csv(KEY_PATH)}
    source = {row["review_id"]: row for row in read_csv(SOURCE_PATH)}
    if not (set(human) == set(llm) == set(key) == set(source)):
        raise ValueError("Human, LLM, key, and source review IDs differ")
    if len(human) != 90:
        raise ValueError(f"Expected 90 cases; found {len(human)}")
    if not all(row["valid_response"].lower() == "true" for row in llm.values()):
        raise ValueError("At least one LLM response is invalid")

    cases: list[dict[str, object]] = []
    for review_id in sorted(human):
        human_label = human[review_id]["manual_classification"]
        llm_label = llm[review_id]["classification"]
        if human_label not in LABELS or llm_label not in LABELS:
            raise ValueError(f"Invalid label in {review_id}")
        cases.append(
            {
                "review_id": review_id,
                "reference_id": int(key[review_id]["id"]),
                "repo_name": source[review_id]["repo_name"],
                "artifact_path": source[review_id]["artifact_path"],
                "code_path": source[review_id]["code_path"],
                "resolved_path": source[review_id]["resolved_path"],
                "task_url": source[review_id]["task_url"],
                "anchor_path_url": source[review_id]["anchor_path_url"],
                "task_context": source[review_id]["task_context"],
                "validation_group": key[review_id]["validation_group"],
                "task_done": int(key[review_id]["task_done"]),
                "exists_at_anchor": int(key[review_id]["exists_at_anchor"]),
                "human_classification": human_label,
                "human_evidence_note": human[review_id]["evidence_note"],
                "human_access_issue": human[review_id]["access_issue"],
                "llm_classification": llm_label,
                "llm_confidence": float(llm[review_id]["confidence"]),
                "llm_evidence_quote": llm[review_id]["evidence_quote"],
                "llm_rationale": llm[review_id]["rationale"],
                "agreement": human_label == llm_label,
                "collapsed_human": COLLAPSE[human_label],
                "collapsed_llm": COLLAPSE[llm_label],
                "collapsed_agreement": COLLAPSE[human_label] == COLLAPSE[llm_label],
            }
        )

    all_pairs = [
        (str(row["human_classification"]), str(row["llm_classification"]))
        for row in cases
    ]
    semantic_cases = [
        row
        for row in cases
        if row["human_classification"] != "inaccessible_or_invalid"
    ]
    semantic_pairs = [
        (str(row["human_classification"]), str(row["llm_classification"]))
        for row in semantic_cases
    ]
    collapsed_pairs = [
        (str(row["collapsed_human"]), str(row["collapsed_llm"])) for row in cases
    ]
    collapsed_semantic_pairs = [
        (str(row["collapsed_human"]), str(row["collapsed_llm"]))
        for row in semantic_cases
    ]

    full = with_intervals(all_pairs, LABELS, 0)
    semantic = with_intervals(semantic_pairs, LABELS[:-1], 1)
    collapsed = with_intervals(collapsed_pairs, COLLAPSED_LABELS, 2)
    collapsed_semantic = with_intervals(
        collapsed_semantic_pairs, COLLAPSED_LABELS[:-1], 3
    )

    metrics: dict[str, object] = {
        "design": {
            "human_labels": "R1 first-pass labels, preserved unchanged",
            "llm_labels": "one fresh isolated process per case",
            "full_set": "all 90 cases",
            "primary_semantic_subset": (
                "86 cases excluding the four human inaccessible_or_invalid cases, "
                "because the LLM received only the frozen record and no live URLs"
            ),
        },
        "full_90": full,
        "primary_semantic_86": semantic,
        "collapsed_full_90": collapsed,
        "collapsed_primary_semantic_86": collapsed_semantic,
        "problematic_binary_full_90": binary_problematic(all_pairs),
        "problematic_binary_primary_semantic_86": binary_problematic(semantic_pairs),
        "disagreements_full_90": sum(not bool(row["agreement"]) for row in cases),
        "disagreements_primary_semantic_86": sum(
            not bool(row["agreement"]) for row in semantic_cases
        ),
        "collapsed_disagreements_full_90": sum(
            not bool(row["collapsed_agreement"]) for row in cases
        ),
    }

    with CASES_OUTPUT.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(cases[0]))
        writer.writeheader()
        writer.writerows(cases)

    disagreements = [row for row in cases if not bool(row["agreement"])]
    with DISAGREEMENTS_OUTPUT.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(cases[0]))
        writer.writeheader()
        writer.writerows(disagreements)

    per_class_rows: list[dict[str, object]] = []
    for scope, bundle in [
        ("full_90", full),
        ("primary_semantic_86", semantic),
        ("collapsed_full_90", collapsed),
        ("collapsed_primary_semantic_86", collapsed_semantic),
    ]:
        for row in bundle["per_class"]:  # type: ignore[index]
            per_class_rows.append({"scope": scope, **row})
    with PER_CLASS_OUTPUT.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(per_class_rows[0]))
        writer.writeheader()
        writer.writerows(per_class_rows)

    write_confusion(CONFUSION_OUTPUT, all_pairs, LABELS)
    write_confusion(COLLAPSED_CONFUSION_OUTPUT, collapsed_pairs, COLLAPSED_LABELS)
    METRICS_OUTPUT.write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    full_bootstrap = full["bootstrap"]
    semantic_bootstrap = semantic["bootstrap"]
    assert isinstance(full_bootstrap, dict)
    assert isinstance(semantic_bootstrap, dict)
    report = f"""# Human–LLM comparison: H001–H090

## Design

- Human reference: R1 first-pass labels, frozen before the LLM run.
- LLM condition: one fresh ephemeral process per case, frozen prompt, structured JSON output, no human labels or sampling strata.
- Model: `gpt-6-sol`, reasoning effort `low`.
- Valid outputs: 90/90.
- Primary analysis: 86 semantically assessable cases. Four human `inaccessible_or_invalid` cases are reported only in the full-set sensitivity analysis because R1 had live URLs while the LLM received only the frozen record.

## Main results

| Scope | Exact agreement | Cohen's kappa | Macro-F1 | Disagreements |
|---|---:|---:|---:|---:|
| Primary semantic subset (n=86) | {int(semantic['matches'])}/86 ({fmt_pct(float(semantic['accuracy']))}) | {float(semantic['cohen_kappa']):.3f} | {float(semantic['macro_f1']):.3f} | {int(metrics['disagreements_primary_semantic_86'])} |
| Full set (n=90) | {int(full['matches'])}/90 ({fmt_pct(float(full['accuracy']))}) | {float(full['cohen_kappa']):.3f} | {float(full['macro_f1']):.3f} | {int(metrics['disagreements_full_90'])} |
| Collapsed full taxonomy (n=90) | {int(collapsed['matches'])}/90 ({fmt_pct(float(collapsed['accuracy']))}) | {float(collapsed['cohen_kappa']):.3f} | {float(collapsed['macro_f1']):.3f} | {int(collapsed['n']) - int(collapsed['matches'])} |

Bootstrap 95% percentile intervals (5,000 case-level resamples):

- Primary agreement: {fmt_ci(semantic_bootstrap['accuracy_95_percentile'])}; kappa: {fmt_ci(semantic_bootstrap['cohen_kappa_95_percentile'])}; macro-F1: {fmt_ci(semantic_bootstrap['macro_f1_95_percentile'])}.
- Full-set agreement: {fmt_ci(full_bootstrap['accuracy_95_percentile'])}; kappa: {fmt_ci(full_bootstrap['cohen_kappa_95_percentile'])}; macro-F1: {fmt_ci(full_bootstrap['macro_f1_95_percentile'])}.

## Interpretation boundary

These are pre-adjudication measurements. The human labels are not assumed to be error-free, and the LLM is not used as the automatic gold standard. Every exact disagreement is exported for R1 adjudication while preserving both original labels. Final performance should be recomputed against the adjudicated labels.
"""
    REPORT_OUTPUT.write_text(report, encoding="utf-8")

    print(f"Cases: {CASES_OUTPUT}")
    print(f"Disagreements: {DISAGREEMENTS_OUTPUT}")
    print(f"Metrics: {METRICS_OUTPUT}")
    print(f"Report: {REPORT_OUTPUT}")
    print(
        f"Primary semantic agreement: {semantic['matches']}/{semantic['n']} "
        f"({float(semantic['accuracy']):.1%}); kappa={float(semantic['cohen_kappa']):.3f}; "
        f"macro-F1={float(semantic['macro_f1']):.3f}"
    )
    print(
        f"Full-set agreement: {full['matches']}/{full['n']} "
        f"({float(full['accuracy']):.1%}); kappa={float(full['cohen_kappa']):.3f}; "
        f"macro-F1={float(full['macro_f1']):.3f}"
    )
    print(f"Exact disagreements: {len(disagreements)}")


if __name__ == "__main__":
    main()
