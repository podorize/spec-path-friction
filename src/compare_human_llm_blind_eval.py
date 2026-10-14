"""Compare independent human and LLM labels for the B001-B030 sample."""

from __future__ import annotations

import csv
import json
import math
import random
from collections import Counter
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
INTERIM = PROJECT_ROOT / "data" / "interim"
RESULTS = PROJECT_ROOT / "results" / "validation"

HUMAN_PATH = INTERIM / "validation_blind_eval_30_human_canonical.csv"
LLM_PATH = INTERIM / "llm_blind_eval_30_results.csv"
KEY_PATH = INTERIM / "validation_blind_eval_30_en_key.csv"

CASES_OUTPUT = RESULTS / "human_llm_blind_eval_30_cases.csv"
PER_CLASS_OUTPUT = RESULTS / "human_llm_blind_eval_30_per_class.csv"
CONFUSION_OUTPUT = RESULTS / "human_llm_blind_eval_30_confusion.csv"
METRICS_OUTPUT = RESULTS / "human_llm_blind_eval_30_metrics.json"

LABELS = [
    "confirmed_exists",
    "confirmed_missing_problematic",
    "expected_absence_create",
    "expected_absence_move_or_delete",
    "non_file_reference",
    "ambiguous_reference",
    "inaccessible_or_invalid",
]
BOOTSTRAP_SEED = 20261001
BOOTSTRAP_REPLICATES = 10_000


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def safe_div(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0


def metric_bundle(
    pairs: list[tuple[str, str]],
) -> dict[str, float | int | list[dict[str, float | int | str]]]:
    n = len(pairs)
    matches = sum(human == llm for human, llm in pairs)
    accuracy = safe_div(matches, n)
    human_counts = Counter(human for human, _ in pairs)
    llm_counts = Counter(llm for _, llm in pairs)
    expected = safe_div(
        sum(human_counts[label] * llm_counts[label] for label in LABELS),
        n * n,
    )
    kappa = safe_div(accuracy - expected, 1 - expected)

    per_class: list[dict[str, float | int | str]] = []
    for label in LABELS:
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
    macro_f1 = sum(float(row["f1"]) for row in per_class) / len(LABELS)
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
    pairs: list[tuple[str, str]],
) -> dict[str, list[float]]:
    rng = random.Random(BOOTSTRAP_SEED)
    accuracy: list[float] = []
    kappa: list[float] = []
    macro_f1: list[float] = []
    for _ in range(BOOTSTRAP_REPLICATES):
        sample = [pairs[rng.randrange(len(pairs))] for _ in pairs]
        metrics = metric_bundle(sample)
        accuracy.append(float(metrics["accuracy"]))
        kappa.append(float(metrics["cohen_kappa"]))
        macro_f1.append(float(metrics["macro_f1"]))
    return {
        "accuracy_95_percentile": [
            percentile(accuracy, 0.025),
            percentile(accuracy, 0.975),
        ],
        "cohen_kappa_95_percentile": [
            percentile(kappa, 0.025),
            percentile(kappa, 0.975),
        ],
        "macro_f1_95_percentile": [
            percentile(macro_f1, 0.025),
            percentile(macro_f1, 0.975),
        ],
    }


def wilson_interval(successes: int, total: int) -> list[float]:
    if total == 0:
        return [0.0, 0.0]
    z = 1.959963984540054
    proportion = successes / total
    denominator = 1 + z * z / total
    center = (proportion + z * z / (2 * total)) / denominator
    half = (
        z
        * math.sqrt(
            proportion * (1 - proportion) / total
            + z * z / (4 * total * total)
        )
        / denominator
    )
    return [center - half, center + half]


def main() -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    human = {row["review_id"]: row for row in read_csv(HUMAN_PATH)}
    llm = {row["review_id"]: row for row in read_csv(LLM_PATH)}
    key = {row["review_id"]: row for row in read_csv(KEY_PATH)}
    if not (set(human) == set(llm) == set(key)):
        raise ValueError("Human, LLM, and private-key review IDs differ")
    if not all(row["valid_response"].lower() == "true" for row in llm.values()):
        raise ValueError("At least one LLM response is invalid")

    cases: list[dict[str, str | int | float | bool]] = []
    pairs: list[tuple[str, str]] = []
    for review_id in sorted(human):
        human_label = human[review_id]["manual_classification"]
        llm_label = llm[review_id]["classification"]
        pairs.append((human_label, llm_label))
        cases.append(
            {
                "review_id": review_id,
                "reference_id": int(key[review_id]["id"]),
                "validation_group": key[review_id]["validation_group"],
                "task_done": int(key[review_id]["task_done"]),
                "exists_at_anchor": int(key[review_id]["exists_at_anchor"]),
                "human_classification": human_label,
                "llm_classification": llm_label,
                "agreement": human_label == llm_label,
                "llm_confidence": float(llm[review_id]["confidence"]),
                "human_evidence_note": human[review_id]["evidence_note"],
                "llm_evidence_quote": llm[review_id]["evidence_quote"],
                "llm_rationale": llm[review_id]["rationale"],
            }
        )

    metrics = metric_bundle(pairs)
    metrics["bootstrap"] = {
        "seed": BOOTSTRAP_SEED,
        "replicates": BOOTSTRAP_REPLICATES,
        **bootstrap_intervals(pairs),
    }
    metrics["accuracy_wilson_95"] = wilson_interval(
        int(metrics["matches"]), int(metrics["n"])
    )

    problematic_human = [
        human_label == "confirmed_missing_problematic"
        for human_label, _ in pairs
    ]
    problematic_llm = [
        llm_label == "confirmed_missing_problematic" for _, llm_label in pairs
    ]
    tp = sum(h and model for h, model in zip(problematic_human, problematic_llm))
    tn = sum(
        not h and not model for h, model in zip(problematic_human, problematic_llm)
    )
    fp = sum(not h and model for h, model in zip(problematic_human, problematic_llm))
    fn = sum(h and not model for h, model in zip(problematic_human, problematic_llm))
    binary_precision = safe_div(tp, tp + fp)
    binary_recall = safe_div(tp, tp + fn)
    metrics["problematic_binary"] = {
        "positive_label": "confirmed_missing_problematic",
        "true_positive": tp,
        "true_negative": tn,
        "false_positive": fp,
        "false_negative": fn,
        "accuracy": safe_div(tp + tn, len(pairs)),
        "precision": binary_precision,
        "recall": binary_recall,
        "f1": safe_div(
            2 * binary_precision * binary_recall,
            binary_precision + binary_recall,
        ),
        "warning": (
            "Only one human-positive case; binary performance is unstable "
            "and must not be generalized."
        ),
    }

    absent_cases = [row for row in cases if row["exists_at_anchor"] == 0]
    absent_problematic = sum(
        row["human_classification"] == "confirmed_missing_problematic"
        for row in absent_cases
    )
    metrics["human_semantic_audit"] = {
        "literal_absence_cases": len(absent_cases),
        "confirmed_problematic_among_literal_absence": absent_problematic,
        "confirmed_problematic_rate": safe_div(
            absent_problematic, len(absent_cases)
        ),
        "confirmed_problematic_rate_wilson_95": wilson_interval(
            absent_problematic, len(absent_cases)
        ),
    }

    case_fields = list(cases[0])
    with CASES_OUTPUT.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=case_fields)
        writer.writeheader()
        writer.writerows(cases)

    per_class = metrics["per_class"]
    assert isinstance(per_class, list)
    with PER_CLASS_OUTPUT.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(per_class[0]))
        writer.writeheader()
        writer.writerows(per_class)

    with CONFUSION_OUTPUT.open("w", newline="", encoding="utf-8") as handle:
        fieldnames = ["human_label", *LABELS]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for human_label in LABELS:
            writer.writerow(
                {
                    "human_label": human_label,
                    **{
                        llm_label: sum(
                            h == human_label and model == llm_label
                            for h, model in pairs
                        )
                        for llm_label in LABELS
                    },
                }
            )

    METRICS_OUTPUT.write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Cases: {CASES_OUTPUT}")
    print(f"Per class: {PER_CLASS_OUTPUT}")
    print(f"Confusion matrix: {CONFUSION_OUTPUT}")
    print(f"Metrics: {METRICS_OUTPUT}")
    print(
        "Agreement: "
        f"{metrics['matches']}/{metrics['n']} "
        f"({float(metrics['accuracy']):.1%})"
    )
    print(f"Cohen's kappa: {float(metrics['cohen_kappa']):.3f}")
    print(f"Macro-F1: {float(metrics['macro_f1']):.3f}")


if __name__ == "__main__":
    main()
