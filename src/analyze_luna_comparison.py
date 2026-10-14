"""Compare deterministic-plus-Luna and Luna-only against the human retest reference."""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "results" / "validation" / "holdout_v1"
RETEST = BASE / "human_retest" / "human_retest_cases.csv"
RUN = BASE / "luna_comparison"
OUTPUT = RUN / "analysis"

LABELS = [
    "confirmed_exists", "confirmed_missing_problematic", "expected_absence_create",
    "expected_absence_move_or_delete", "external_repository_reference",
    "non_file_reference", "ambiguous_reference", "inaccessible_or_invalid",
]
UNKNOWN = {"ambiguous_reference", "inaccessible_or_invalid"}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def predicted_state(decision: str, label: str) -> str:
    if decision == "abstain" or label in UNKNOWN:
        return "unknown"
    if label == "confirmed_missing_problematic":
        return "problematic"
    return "nonproblematic"


def combine_hybrid() -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for row in read_jsonl(RUN / "rule_decisions.jsonl"):
        rows.append({
            "review_id": row["review_id"], "hybrid_stage": "deterministic_rule",
            "hybrid_decision": "classify", "hybrid_classification": row["classification"],
            "hybrid_confidence": "", "hybrid_rationale": row["rationale"],
        })
    for row in read_jsonl(RUN / "deterministic_abstentions.jsonl"):
        rows.append({
            "review_id": row["review_id"], "hybrid_stage": "deterministic_abstention",
            "hybrid_decision": "abstain", "hybrid_classification": row["classification"],
            "hybrid_confidence": "", "hybrid_rationale": row["rationale"],
        })
    llm = pd.read_csv(RUN / "hybrid_luna_results.csv", dtype=str, keep_default_na=False)
    if len(llm) != 18 or not (llm["valid_response"].str.lower() == "true").all():
        raise ValueError("Hybrid Luna stage must contain 18 valid responses")
    for row in llm.to_dict("records"):
        rows.append({
            "review_id": row["review_id"], "hybrid_stage": "luna_semantic_review",
            "hybrid_decision": row["decision"], "hybrid_classification": row["classification"],
            "hybrid_confidence": row["confidence"], "hybrid_rationale": row["rationale"],
        })
    result = pd.DataFrame(rows)
    if len(result) != 90 or result["review_id"].duplicated().any():
        raise ValueError("Hybrid predictions must contain 90 unique cases")
    result["hybrid_state"] = result.apply(
        lambda row: predicted_state(row["hybrid_decision"], row["hybrid_classification"]), axis=1
    )
    return result


def combine_luna_only() -> pd.DataFrame:
    initial = pd.read_csv(RUN / "luna_only_results.csv", dtype=str, keep_default_na=False)
    retry = pd.read_csv(RUN / "luna_only_retry_results.csv", dtype=str, keep_default_na=False)
    retry_ids = set(retry["review_id"])
    final = pd.concat([initial.loc[~initial["review_id"].isin(retry_ids)], retry], ignore_index=True)
    if len(final) != 90 or final["review_id"].duplicated().any():
        raise ValueError("Luna-only predictions must contain 90 unique cases after retries")
    if not (final["valid_response"].str.lower() == "true").all():
        raise ValueError("Luna-only contains invalid final responses")
    final = final.rename(columns={
        "decision": "luna_only_decision", "classification": "luna_only_classification",
        "confidence": "luna_only_confidence", "rationale": "luna_only_rationale",
    })
    final["luna_only_state"] = final.apply(
        lambda row: predicted_state(row["luna_only_decision"], row["luna_only_classification"]), axis=1
    )
    return final[[
        "review_id", "luna_only_decision", "luna_only_classification",
        "luna_only_confidence", "luna_only_rationale", "luna_only_state",
    ]]


def safe_div(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else float("nan")


def wilson_interval(successes: float, total: float, z: float = 1.959963984540054) -> dict[str, float]:
    """Return a Wilson score interval for an unweighted binomial proportion."""
    if total <= 0:
        return {"estimate": float("nan"), "ci_low": float("nan"), "ci_high": float("nan")}
    proportion = successes / total
    denominator = 1 + z**2 / total
    centre = (proportion + z**2 / (2 * total)) / denominator
    margin = z * math.sqrt(proportion * (1 - proportion) / total + z**2 / (4 * total**2)) / denominator
    return {
        "estimate": proportion,
        "ci_low": max(0.0, centre - margin),
        "ci_high": min(1.0, centre + margin),
    }


def binary_metrics(frame: pd.DataFrame, ref_col: str, pred_col: str, weight_col: str | None = None) -> dict[str, float | int]:
    weights = frame[weight_col].astype(float) if weight_col else pd.Series(1.0, index=frame.index)
    ref = frame[ref_col]
    pred = frame[pred_col]
    tp = float(weights[(ref == "problematic") & (pred == "problematic")].sum())
    fp = float(weights[(ref == "nonproblematic") & (pred == "problematic")].sum())
    tn = float(weights[(ref == "nonproblematic") & (pred == "nonproblematic")].sum())
    fn = float(weights[(ref == "problematic") & (pred == "nonproblematic")].sum())
    abstain_pos = float(weights[(ref == "problematic") & (pred == "unknown")].sum())
    abstain_neg = float(weights[(ref == "nonproblematic") & (pred == "unknown")].sum())
    total = float(weights.sum())
    classified = tp + fp + tn + fn
    precision = safe_div(tp, tp + fp)
    recall = safe_div(tp, tp + fn + abstain_pos)
    specificity = safe_div(tn, tn + fp + abstain_neg)
    npv = safe_div(tn, tn + fn)
    return {
        "n": len(frame), "weighted_n": total,
        "tp": tp, "fp": fp, "tn": tn, "fn": fn,
        "abstain_positive": abstain_pos, "abstain_negative": abstain_neg,
        "coverage": safe_div(classified, total),
        "precision": precision,
        "recall_end_to_end": recall,
        "specificity_end_to_end": specificity,
        "npv": npv,
        "f1_end_to_end": safe_div(2 * precision * recall, precision + recall),
        "accuracy_end_to_end": safe_div(tp + tn, total),
        "balanced_accuracy_end_to_end": (recall + specificity) / 2,
        "selective_accuracy": safe_div(tp + tn, classified),
    }


def exact_macro_f1(reference: pd.Series, prediction: pd.Series) -> dict[str, float | int]:
    f1s = []
    per_class: dict[str, float] = {}
    for label in LABELS:
        tp = int(((reference == label) & (prediction == label)).sum())
        fp = int(((reference != label) & (prediction == label)).sum())
        fn = int(((reference == label) & (prediction != label)).sum())
        precision = safe_div(tp, tp + fp)
        recall = safe_div(tp, tp + fn)
        f1 = safe_div(2 * precision * recall, precision + recall)
        if not math.isnan(f1):
            f1s.append(f1)
            per_class[label] = f1
    return {
        "n": len(reference),
        "exact_accuracy": float((reference == prediction).mean()),
        "macro_f1_observed_classes": float(np.mean(f1s)) if f1s else float("nan"),
        "per_class_f1": per_class,
    }


def hybrid_stage_breakdown(frame: pd.DataFrame) -> dict[str, dict[str, float | int | None]]:
    """Describe routing and correctness within each hybrid stage."""
    result: dict[str, dict[str, float | int | None]] = {}
    for stage, group in frame.groupby("hybrid_stage", sort=True):
        classified = group["hybrid_state"] != "unknown"
        correct = group["hybrid_state"] == group["round1_state"]
        result[stage] = {
            "n": len(group),
            "problematic_n": int((group["round1_state"] == "problematic").sum()),
            "nonproblematic_n": int((group["round1_state"] == "nonproblematic").sum()),
            "classified_n": int(classified.sum()),
            "unknown_n": int((~classified).sum()),
            "correct_n": int(correct.sum()),
            "end_to_end_accuracy": float(correct.mean()),
            "selective_accuracy": float(correct[classified].mean()) if classified.any() else None,
            "true_positive_n": int(((group["round1_state"] == "problematic") & (group["hybrid_state"] == "problematic")).sum()),
            "false_negative_n": int(((group["round1_state"] == "problematic") & (group["hybrid_state"] == "nonproblematic")).sum()),
            "positive_abstention_n": int(((group["round1_state"] == "problematic") & (group["hybrid_state"] == "unknown")).sum()),
        }
    return result


def mcnemar_exact(hybrid_correct: pd.Series, luna_correct: pd.Series) -> dict[str, float | int]:
    hybrid_only = int((hybrid_correct & ~luna_correct).sum())
    luna_only = int((~hybrid_correct & luna_correct).sum())
    discordant = hybrid_only + luna_only
    if discordant == 0:
        p_value = 1.0
    else:
        tail = sum(math.comb(discordant, i) for i in range(0, min(hybrid_only, luna_only) + 1)) / (2 ** discordant)
        p_value = min(1.0, 2 * tail)
    return {"hybrid_only_correct": hybrid_only, "luna_only_correct": luna_only, "discordant": discordant, "exact_two_sided_p": p_value}


def bootstrap_difference(frame: pd.DataFrame, metric: str, iterations: int = 10000, seed: int = 20261013) -> dict[str, float]:
    rng = np.random.default_rng(seed)
    indices = rng.integers(0, len(frame), size=(iterations, len(frame)))
    reference_positive = (frame["round1_state"].to_numpy() == "problematic")
    hybrid_state = frame["hybrid_state"].to_numpy()
    luna_state = frame["luna_only_state"].to_numpy()
    if metric == "accuracy_end_to_end":
        hybrid_value = (hybrid_state == frame["round1_state"].to_numpy()).astype(float)
        luna_value = (luna_state == frame["round1_state"].to_numpy()).astype(float)
        array = hybrid_value[indices].mean(axis=1) - luna_value[indices].mean(axis=1)
    elif metric == "recall_end_to_end":
        positive = reference_positive[indices]
        denominators = positive.sum(axis=1)
        valid = denominators > 0
        hybrid_tp = ((hybrid_state[indices] == "problematic") & positive).sum(axis=1)
        luna_tp = ((luna_state[indices] == "problematic") & positive).sum(axis=1)
        array = (hybrid_tp[valid] - luna_tp[valid]) / denominators[valid]
    else:
        raise ValueError(f"Unsupported bootstrap metric: {metric}")
    return {
        "hybrid_minus_luna_point": float(
            binary_metrics(frame, "round1_state", "hybrid_state")[metric]
            - binary_metrics(frame, "round1_state", "luna_only_state")[metric]
        ),
        "ci_low": float(np.quantile(array, 0.025)),
        "ci_high": float(np.quantile(array, 0.975)),
    }


def usage_cost(manifest_paths: list[Path]) -> dict[str, float | int]:
    attempts = 0
    totals = {key: 0 for key in ["input_tokens", "cached_input_tokens", "output_tokens", "reasoning_output_tokens"]}
    for path in manifest_paths:
        manifest = json.loads(path.read_text(encoding="utf-8"))
        attempts += int(manifest["records_requested"])
        for key in totals:
            totals[key] += int(manifest["token_usage"].get(key, 0))
    uncached = totals["input_tokens"] - totals["cached_input_tokens"]
    cost = uncached / 1_000_000 * 0.10 + totals["cached_input_tokens"] / 1_000_000 * 0.01 + totals["output_tokens"] / 1_000_000 * 0.50
    return {"attempts": attempts, **totals, "estimated_usd": cost}


def fmt(value: float) -> str:
    return "n.a." if math.isnan(value) else f"{value:.1%}"


def main() -> None:
    human = pd.read_csv(RETEST, dtype=str, keep_default_na=False)
    human["final_sampling_weight"] = human["final_sampling_weight"].astype(float)
    merged = human.merge(combine_hybrid(), on="review_id", validate="one_to_one").merge(combine_luna_only(), on="review_id", validate="one_to_one")

    stable_decisive = merged.loc[merged["stable_decisive_reference"].str.lower() == "true"].copy()
    exact_stable = merged.loc[merged["exact_label_agreement"].str.lower() == "true"].copy()
    stable_three = merged.loc[merged["three_state_agreement"].str.lower() == "true"].copy()
    r1_decisive = merged.loc[merged["round1_state"] != "unknown"].copy()
    r2_decisive = merged.loc[merged["round2_state"] != "unknown"].copy()

    primary = {
        "hybrid_unweighted": binary_metrics(stable_decisive, "round1_state", "hybrid_state"),
        "luna_only_unweighted": binary_metrics(stable_decisive, "round1_state", "luna_only_state"),
        "hybrid_design_weighted": binary_metrics(stable_decisive, "round1_state", "hybrid_state", "final_sampling_weight"),
        "luna_only_design_weighted": binary_metrics(stable_decisive, "round1_state", "luna_only_state", "final_sampling_weight"),
    }
    sensitivities = {
        "round1": {
            "hybrid": binary_metrics(r1_decisive, "round1_state", "hybrid_state"),
            "luna_only": binary_metrics(r1_decisive, "round1_state", "luna_only_state"),
        },
        "round2": {
            "hybrid": binary_metrics(r2_decisive, "round2_state", "hybrid_state"),
            "luna_only": binary_metrics(r2_decisive, "round2_state", "luna_only_state"),
        },
    }
    exact_semantic = {
        "hybrid": exact_macro_f1(exact_stable["round1_classification"], exact_stable["hybrid_classification"]),
        "luna_only": exact_macro_f1(exact_stable["round1_classification"], exact_stable["luna_only_classification"]),
    }
    three_state = {
        "hybrid_accuracy": float((stable_three["round1_state"] == stable_three["hybrid_state"]).mean()),
        "luna_only_accuracy": float((stable_three["round1_state"] == stable_three["luna_only_state"]).mean()),
        "n": len(stable_three),
    }
    hybrid_correct = stable_decisive["hybrid_state"] == stable_decisive["round1_state"]
    luna_correct = stable_decisive["luna_only_state"] == stable_decisive["round1_state"]
    paired = {
        "both_correct": int((hybrid_correct & luna_correct).sum()),
        "both_incorrect": int((~hybrid_correct & ~luna_correct).sum()),
        **mcnemar_exact(hybrid_correct, luna_correct),
        "bootstrap_accuracy_difference": bootstrap_difference(stable_decisive, "accuracy_end_to_end"),
        "bootstrap_recall_difference": bootstrap_difference(stable_decisive, "recall_end_to_end"),
    }
    resources = {
        "hybrid": usage_cost([RUN / "hybrid_luna_manifest.json"]),
        "luna_only": usage_cost([RUN / "luna_only_manifest.json", RUN / "luna_only_retry_manifest.json"]),
    }
    stage_breakdown = hybrid_stage_breakdown(stable_decisive)
    h = primary["hybrid_unweighted"]
    l = primary["luna_only_unweighted"]
    uncertainty = {
        "hybrid": {
            "coverage_wilson_95": wilson_interval(h["tp"] + h["fp"] + h["tn"] + h["fn"], h["weighted_n"]),
            "precision_wilson_95": wilson_interval(h["tp"], h["tp"] + h["fp"]),
            "recall_wilson_95": wilson_interval(h["tp"], h["tp"] + h["fn"] + h["abstain_positive"]),
            "accuracy_wilson_95": wilson_interval(h["tp"] + h["tn"], h["weighted_n"]),
        },
        "luna_only": {
            "coverage_wilson_95": wilson_interval(l["tp"] + l["fp"] + l["tn"] + l["fn"], l["weighted_n"]),
            "precision_wilson_95": wilson_interval(l["tp"], l["tp"] + l["fp"]),
            "recall_wilson_95": wilson_interval(l["tp"], l["tp"] + l["fn"] + l["abstain_positive"]),
            "accuracy_wilson_95": wilson_interval(l["tp"] + l["tn"], l["weighted_n"]),
        },
    }
    summary = {
        "reference": {
            "stable_decisive_n": len(stable_decisive),
            "stable_problematic_n": int((stable_decisive["round1_state"] == "problematic").sum()),
            "stable_nonproblematic_n": int((stable_decisive["round1_state"] == "nonproblematic").sum()),
            "exact_stable_n": len(exact_stable),
            "three_state_stable_n": len(stable_three),
        },
        "primary": primary,
        "sensitivities": sensitivities,
        "exact_semantic": exact_semantic,
        "stable_three_state": three_state,
        "paired_comparison": paired,
        "hybrid_stage_breakdown": stage_breakdown,
        "uncertainty": uncertainty,
        "resources": resources,
        "prediction_counts": {
            "hybrid_state": merged["hybrid_state"].value_counts().to_dict(),
            "luna_only_state": merged["luna_only_state"].value_counts().to_dict(),
            "hybrid_stage": merged["hybrid_stage"].value_counts().to_dict(),
        },
    }

    OUTPUT.mkdir(parents=True, exist_ok=True)
    merged.to_csv(OUTPUT / "paired_case_results.csv", index=False)
    (OUTPUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    hu = uncertainty["hybrid"]
    lu = uncertainty["luna_only"]
    report = f"""# GPT-6 Luna architecture comparison

## Reference set

The primary binary analysis uses **{len(stable_decisive)} stable decisive human cases**: {summary['reference']['stable_problematic_n']} problematic and {summary['reference']['stable_nonproblematic_n']} nonproblematic. The small positive count makes recall and F1 estimates highly uncertain.

## Primary unweighted results

| Metric | Deterministic + Luna | Luna only |
| --- | ---: | ---: |
| Coverage | {fmt(h['coverage'])} | {fmt(l['coverage'])} |
| Precision | {fmt(h['precision'])} | {fmt(l['precision'])} |
| End-to-end recall | {fmt(h['recall_end_to_end'])} | {fmt(l['recall_end_to_end'])} |
| End-to-end specificity | {fmt(h['specificity_end_to_end'])} | {fmt(l['specificity_end_to_end'])} |
| End-to-end F1 | {fmt(h['f1_end_to_end'])} | {fmt(l['f1_end_to_end'])} |
| End-to-end accuracy | {fmt(h['accuracy_end_to_end'])} | {fmt(l['accuracy_end_to_end'])} |
| Selective accuracy | {fmt(h['selective_accuracy'])} | {fmt(l['selective_accuracy'])} |

Wilson 95% confidence intervals for the most consequential proportions:

| Metric | Deterministic + Luna | Luna only |
| --- | ---: | ---: |
| Coverage | [{fmt(hu['coverage_wilson_95']['ci_low'])}, {fmt(hu['coverage_wilson_95']['ci_high'])}] | [{fmt(lu['coverage_wilson_95']['ci_low'])}, {fmt(lu['coverage_wilson_95']['ci_high'])}] |
| Precision | [{fmt(hu['precision_wilson_95']['ci_low'])}, {fmt(hu['precision_wilson_95']['ci_high'])}] | [{fmt(lu['precision_wilson_95']['ci_low'])}, {fmt(lu['precision_wilson_95']['ci_high'])}] |
| End-to-end recall | [{fmt(hu['recall_wilson_95']['ci_low'])}, {fmt(hu['recall_wilson_95']['ci_high'])}] | [{fmt(lu['recall_wilson_95']['ci_low'])}, {fmt(lu['recall_wilson_95']['ci_high'])}] |
| End-to-end accuracy | [{fmt(hu['accuracy_wilson_95']['ci_low'])}, {fmt(hu['accuracy_wilson_95']['ci_high'])}] | [{fmt(lu['accuracy_wilson_95']['ci_low'])}, {fmt(lu['accuracy_wilson_95']['ci_high'])}] |

The apparent 100% precision is based on only **one** stable true-positive prediction and zero stable false positives for each architecture. Its interval is therefore very wide and must not be read as evidence of near-perfect precision.

Confusion and abstention counts:

- Hybrid: TP={h['tp']:.0f}, FP={h['fp']:.0f}, TN={h['tn']:.0f}, FN={h['fn']:.0f}, positive abstentions={h['abstain_positive']:.0f}, negative abstentions={h['abstain_negative']:.0f}.
- Luna only: TP={l['tp']:.0f}, FP={l['fp']:.0f}, TN={l['tn']:.0f}, FN={l['fn']:.0f}, positive abstentions={l['abstain_positive']:.0f}, negative abstentions={l['abstain_negative']:.0f}.

## Hybrid-stage diagnosis

- **Deterministic classifications:** {stage_breakdown['deterministic_rule']['n']} stable decisive cases ({stage_breakdown['deterministic_rule']['problematic_n']} positive, {stage_breakdown['deterministic_rule']['nonproblematic_n']} negative). The rules correctly classified {stage_breakdown['deterministic_rule']['correct_n']} cases, but all {stage_breakdown['deterministic_rule']['problematic_n']} stable positives routed here were labeled nonproblematic.
- **Deterministic abstentions:** {stage_breakdown['deterministic_abstention']['n']} stable decisive cases, all human-stable nonproblematic. These safe abstentions explain much of the hybrid coverage loss.
- **Luna semantic-review stage:** {stage_breakdown['luna_semantic_review']['n']} stable decisive cases. It classified {stage_breakdown['luna_semantic_review']['classified_n']} and abstained on {stage_breakdown['luna_semantic_review']['unknown_n']}; all classified cases were correct, including the single detected stable positive.

The hybrid's main positive-class failure is therefore not merely LLM uncertainty. Three of the six stable positives were intercepted by deterministic lifecycle rules and labeled nonproblematic before Luna could inspect them.

## Paired comparison

- Both correct: {paired['both_correct']}
- Hybrid only correct: {paired['hybrid_only_correct']}
- Luna only correct: {paired['luna_only_correct']}
- Both incorrect: {paired['both_incorrect']}
- Exact McNemar p-value: {paired['exact_two_sided_p']:.4f}
- Hybrid minus Luna end-to-end accuracy: {paired['bootstrap_accuracy_difference']['hybrid_minus_luna_point']:.1%}, bootstrap 95% CI [{paired['bootstrap_accuracy_difference']['ci_low']:.1%}, {paired['bootstrap_accuracy_difference']['ci_high']:.1%}]
- Hybrid minus Luna end-to-end recall: {paired['bootstrap_recall_difference']['hybrid_minus_luna_point']:.1%}, bootstrap 95% CI [{paired['bootstrap_recall_difference']['ci_low']:.1%}, {paired['bootstrap_recall_difference']['ci_high']:.1%}]

## Resource use

- Hybrid: {resources['hybrid']['attempts']} Luna calls, estimated API token cost **US${resources['hybrid']['estimated_usd']:.4f}**.
- Luna only: {resources['luna_only']['attempts']} attempts for 90 final cases, estimated API token cost **US${resources['luna_only']['estimated_usd']:.4f}**.

The estimate applies GPT-6 Luna standard text-token prices of US$0.10 per million uncached input tokens, US$0.01 per million cached input tokens, and US$0.50 per million output tokens. It excludes subscription accounting and any platform-specific overhead.

## Interpretation limits

The same human performed both rounds, so stable agreement measures repeatability rather than independent validity. Human and model evidence were not perfectly equivalent: the model used frozen repository evidence, while the human experienced live GitHub availability, including temporary failures. The primary reference contains only six stable positive cases. Results therefore support architecture triage and cost comparison, not a definitive claim of superiority.
"""
    (OUTPUT / "LUNA_COMPARISON.md").write_text(report, encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
