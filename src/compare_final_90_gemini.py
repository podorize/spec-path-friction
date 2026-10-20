"""Compare frozen human labels vs Gemini LLM judge on the final 90 cases."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
INTERIM = ROOT / "data" / "interim"
SHARDS_DIR = INTERIM / "gemini_shards"
HUMAN_CSV = INTERIM / "validation_human_final_90_R1_initial.csv"
KEY_CSV = INTERIM / "validation_final_90_en_key.csv"
RESULTS_DIR = ROOT / "results" / "validation" / "final_90_gemini"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

TAXONOMY = [
    "confirmed_exists",
    "confirmed_missing_problematic",
    "expected_absence_create",
    "expected_absence_move_or_delete",
    "external_repository_reference",
    "non_file_reference",
    "ambiguous_reference",
    "inaccessible_or_invalid",
]


def cohen_kappa(y_true: list[str], y_pred: list[str], labels: list[str]) -> float:
    label_to_idx = {l: i for i, l in enumerate(labels)}
    k = len(labels)
    cm = np.zeros((k, k), dtype=float)
    for t, p in zip(y_true, y_pred):
        if t in label_to_idx and p in label_to_idx:
            cm[label_to_idx[t], label_to_idx[p]] += 1
    n = cm.sum()
    if n == 0:
        return 0.0
    po = np.trace(cm) / n
    pe = sum(cm[i, :].sum() * cm[:, i].sum() for i in range(k)) / (n * n)
    if pe == 1.0:
        return 1.0
    return float((po - pe) / (1.0 - pe))


def gwet_ac1(y_true: list[str], y_pred: list[str], labels: list[str]) -> float:
    label_to_idx = {l: i for i, l in enumerate(labels)}
    k = len(labels)
    cm = np.zeros((k, k), dtype=float)
    for t, p in zip(y_true, y_pred):
        if t in label_to_idx and p in label_to_idx:
            cm[label_to_idx[t], label_to_idx[p]] += 1
    n = cm.sum()
    if n == 0 or k <= 1:
        return 0.0
    po = np.trace(cm) / n
    pi = [(cm[i, :].sum() + cm[:, i].sum()) / (2 * n) for i in range(k)]
    pe = sum(p * (1 - p) for p in pi) / (k - 1)
    if pe == 1.0:
        return 1.0
    return float((po - pe) / (1.0 - pe))


def collapse_3state(label: str) -> str:
    if label == "confirmed_missing_problematic":
        return "problematic"
    if label in {
        "confirmed_exists",
        "expected_absence_create",
        "expected_absence_move_or_delete",
        "external_repository_reference",
        "non_file_reference",
    }:
        return "nonproblematic"
    return "unknown"


def main() -> None:
    # 1. Collect all shard outputs
    records = []
    for i in range(1, 7):
        shard_out = SHARDS_DIR / f"output_{i}.json"
        if not shard_out.exists():
            raise FileNotFoundError(f"Missing shard output: {shard_out}")
        with shard_out.open(encoding="utf-8") as f:
            data = json.load(f)
            records.extend(data)

    print(f"Loaded {len(records)} Gemini predictions across 6 shards.")
    assert len(records) == 90, f"Expected 90 records, got {len(records)}"

    gemini_df = pd.DataFrame(records)
    gemini_csv = INTERIM / "llm_final_90_gemini_results.csv"
    gemini_df.to_csv(gemini_csv, index=False)

    # 2. Load human and key
    human_df = pd.read_csv(HUMAN_CSV)
    key_df = pd.read_csv(KEY_CSV)

    merged = human_df[["review_id", "manual_classification", "evidence_note"]].merge(
        gemini_df[["review_id", "classification", "confidence", "evidence_quote", "rationale"]],
        on="review_id",
        suffixes=("_human", "_gemini"),
    ).merge(
        key_df[["review_id", "validation_group", "exists_at_anchor", "task_done"]],
        on="review_id",
    )

    y_human = merged["manual_classification"].tolist()
    y_gemini = merged["classification"].tolist()

    # 3. Eight-class metrics
    exact_matches = sum(1 for h, g in zip(y_human, y_gemini) if h == g)
    exact_acc = exact_matches / len(merged)
    kappa = cohen_kappa(y_human, y_gemini, TAXONOMY)
    ac1 = gwet_ac1(y_human, y_gemini, TAXONOMY)

    # Confusion matrix
    cm_df = pd.crosstab(
        merged["manual_classification"],
        merged["classification"],
        rownames=["Human"],
        colnames=["Gemini"],
    ).reindex(index=TAXONOMY, columns=TAXONOMY, fill_value=0)
    cm_df.to_csv(RESULTS_DIR / "confusion_matrix.csv")

    # Per-class precision, recall, f1
    per_class = []
    for cat in TAXONOMY:
        tp = ((merged["manual_classification"] == cat) & (merged["classification"] == cat)).sum()
        fp = ((merged["manual_classification"] != cat) & (merged["classification"] == cat)).sum()
        fn = ((merged["manual_classification"] == cat) & (merged["classification"] != cat)).sum()
        prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0
        support = (merged["manual_classification"] == cat).sum()
        per_class.append({
            "category": cat,
            "support": int(support),
            "precision": round(prec, 4),
            "recall": round(rec, 4),
            "f1": round(f1, 4),
        })
    per_class_df = pd.DataFrame(per_class)
    per_class_df.to_csv(RESULTS_DIR / "per_class_metrics.csv", index=False)
    macro_f1 = per_class_df["f1"].mean()

    # 4. Three-state evaluation
    merged["3state_human"] = merged["manual_classification"].apply(collapse_3state)
    merged["3state_gemini"] = merged["classification"].apply(collapse_3state)
    three_state_matches = (merged["3state_human"] == merged["3state_gemini"]).sum()
    three_state_acc = three_state_matches / len(merged)
    kappa_3state = cohen_kappa(merged["3state_human"].tolist(), merged["3state_gemini"].tolist(), ["problematic", "nonproblematic", "unknown"])

    # 5. Binary metrics on confirmed_missing_problematic
    tp_prob = ((merged["manual_classification"] == "confirmed_missing_problematic") & (merged["classification"] == "confirmed_missing_problematic")).sum()
    fp_prob = ((merged["manual_classification"] != "confirmed_missing_problematic") & (merged["classification"] == "confirmed_missing_problematic")).sum()
    fn_prob = ((merged["manual_classification"] == "confirmed_missing_problematic") & (merged["classification"] != "confirmed_missing_problematic")).sum()
    tn_prob = ((merged["manual_classification"] != "confirmed_missing_problematic") & (merged["classification"] != "confirmed_missing_problematic")).sum()

    prec_prob = tp_prob / (tp_prob + fp_prob) if (tp_prob + fp_prob) > 0 else 0.0
    rec_prob = tp_prob / (tp_prob + fn_prob) if (tp_prob + fn_prob) > 0 else 0.0
    f1_prob = 2 * prec_prob * rec_prob / (prec_prob + rec_prob) if (prec_prob + rec_prob) > 0 else 0.0

    # 6. Disagreements list
    disagreements = merged.loc[merged["manual_classification"] != merged["classification"]].copy()
    disagreements_file = RESULTS_DIR / "disagreements.csv"
    disagreements.to_csv(disagreements_file, index=False)

    summary = {
        "sample_size": len(merged),
        "exact_agreement_count": int(exact_matches),
        "exact_agreement_rate": round(exact_acc, 4),
        "cohen_kappa_8class": round(kappa, 4),
        "gwet_ac1_8class": round(ac1, 4),
        "macro_f1_8class": round(macro_f1, 4),
        "three_state_agreement_rate": round(three_state_acc, 4),
        "three_state_kappa": round(kappa_3state, 4),
        "binary_problematic": {
            "true_positives": int(tp_prob),
            "false_positives": int(fp_prob),
            "false_negatives": int(fn_prob),
            "true_negatives": int(tn_prob),
            "precision": round(prec_prob, 4),
            "recall": round(rec_prob, 4),
            "f1": round(f1_prob, 4),
        },
        "disagreements_count": len(disagreements),
    }

    with (RESULTS_DIR / "summary.json").open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print("\n" + "=" * 50)
    print("FINAL 90 EVALUATION: HUMAN vs. GEMINI JUDGE")
    print("=" * 50)
    print(f"Exact Agreement: {exact_matches}/90 ({exact_acc*100:.1f}%)")
    print(f"Cohen's Kappa (8 classes): {kappa:.4f}")
    print(f"Gwet's AC1 (8 classes): {ac1:.4f}")
    print(f"Macro-F1 (8 classes): {macro_f1:.4f}")
    print(f"Three-State Agreement: {three_state_matches}/90 ({three_state_acc*100:.1f}%)")
    print(f"Three-State Kappa: {kappa_3state:.4f}")
    print("-" * 50)
    print("Binary Detection of 'confirmed_missing_problematic':")
    print(f"  True Positives: {tp_prob} | False Positives: {fp_prob}")
    print(f"  False Negatives: {fn_prob} | True Negatives: {tn_prob}")
    print(f"  Precision: {prec_prob*100:.1f}% | Recall: {rec_prob*100:.1f}% | F1: {f1_prob:.4f}")
    print(f"Total Disagreements: {len(disagreements)}")
    print("=" * 50)


if __name__ == "__main__":
    main()
