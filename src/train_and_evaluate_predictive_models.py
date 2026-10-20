"""Train supervised predictive models on Silver data and evaluate on Gold Human ground truth."""

from __future__ import annotations

import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd
from sklearn.ensemble import (
    GradientBoostingClassifier,
    HistGradientBoostingClassifier,
    RandomForestClassifier,
)
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    classification_report,
    cohen_kappa_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import StratifiedKFold

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

INTERIM = PROJECT_ROOT / "data" / "interim"
RESULTS_DIR = PROJECT_ROOT / "results" / "supervised_models"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

SILVER_PARQUET = INTERIM / "silver_labeled_dataset_450.parquet"
GOLD_CSV = INTERIM / "validation_human_final_90_R1_initial.csv"
GOLD_KEY_CSV = INTERIM / "validation_final_90_en_key.csv"

from src.extract_reference_ml_features import extract_features_from_context, map_targets


FEATURE_COLS = [
    "verb_create",
    "verb_update",
    "verb_delete",
    "verb_test",
    "verb_balance",
    "header_has_create",
    "header_has_delete",
    "header_has_test",
    "task_checkbox_done",
    "task_checkbox_open",
    "task_pos_ratio",
    "task_line_word_count",
    "path_depth",
    "path_length",
    "path_basename_length",
    "is_test_file",
    "is_config_file",
    "is_doc_file",
    "is_source_file",
    "has_glob_pattern",
    "has_traversal",
    "has_backslash",
    "is_monorepo",
    "task_done",
    "artifact_completion_ratio",
    "artifact_code_ref_density",
]


def prepare_gold_test_set() -> pd.DataFrame:
    df_human = pd.read_csv(GOLD_CSV)
    df_key = pd.read_csv(GOLD_KEY_CSV)
    df = df_human.merge(df_key[["review_id", "exists_at_anchor", "task_done"]], on="review_id")

    rows = []
    for _, r in df.iterrows():
        f = extract_features_from_context(str(r["code_path"]), str(r["task_context"]))
        t = map_targets(r["manual_classification"])
        f.update(t)
        f["review_id"] = r["review_id"]
        f["task_done"] = int(r["task_done"])
        f["exists_at_anchor"] = int(r["exists_at_anchor"])
        f["manual_classification"] = r["manual_classification"]
        f["artifact_completion_ratio"] = 0.5
        f["artifact_code_ref_density"] = 1.0
        rows.append(f)
    return pd.DataFrame(rows)


def run_training_pipeline() -> None:
    print("=" * 60)
    print("TRAINING SUPERVISED PREDICTIVE MODELS ON SILVER DATASET (N=450)")
    print("=" * 60)

    if not SILVER_PARQUET.exists():
        print(f"ERROR: Silver dataset not found at {SILVER_PARQUET}.")
        return

    silver_df = pd.read_parquet(SILVER_PARQUET)
    print(f"Loaded {len(silver_df)} Silver training instances.")

    gold_df = prepare_gold_test_set()
    print(f"Loaded {len(gold_df)} Gold human test instances (completely independent).")

    # Feature matrices
    X_train = silver_df[FEATURE_COLS].copy()
    y_train_bin = silver_df["target_problematic_binary"].astype(int)
    y_train_multi = silver_df["target_lifecycle_multiclass"].astype(str)
    sample_weights = silver_df["sampling_weight"].values

    X_test = gold_df[FEATURE_COLS].copy()
    y_test_bin = gold_df["target_problematic_binary"].astype(int)
    y_test_multi = gold_df["target_lifecycle_multiclass"].astype(str)

    # -------------------------------------------------------------
    # 1. Binary Model: Friction Detection (problematic vs nonproblematic)
    # -------------------------------------------------------------
    print("\n" + "=" * 50)
    print("TASK 1: BINARY FRICTION DETECTOR (confirmed_missing_problematic)")
    print("=" * 50)
    print(f"Silver Train Class Distribution: {dict(y_train_bin.value_counts())}")
    print(f"Gold Test Class Distribution:   {dict(y_test_bin.value_counts())}")

    models = {
        "LogisticRegression": LogisticRegression(class_weight="balanced", max_iter=1000, random_state=42),
        "RandomForest": RandomForestClassifier(n_estimators=100, class_weight="balanced", random_state=42),
        "HistGradientBoosting": HistGradientBoostingClassifier(class_weight="balanced", random_state=42),
        "GradientBoosting": GradientBoostingClassifier(n_estimators=100, random_state=42),
    }

    binary_results = {}
    for name, clf in models.items():
        if name in {"LogisticRegression", "RandomForest", "HistGradientBoosting"}:
            clf.fit(X_train, y_train_bin, sample_weight=sample_weights)
        else:
            clf.fit(X_train, y_train_bin)

        y_pred = clf.predict(X_test)
        y_prob = clf.predict_proba(X_test)[:, 1] if hasattr(clf, "predict_proba") else y_pred

        tp = int(sum((y_test_bin == 1) & (y_pred == 1)))
        fp = int(sum((y_test_bin == 0) & (y_pred == 1)))
        fn = int(sum((y_test_bin == 1) & (y_pred == 0)))
        tn = int(sum((y_test_bin == 0) & (y_pred == 0)))

        prec = precision_score(y_test_bin, y_pred, zero_division=0)
        rec = recall_score(y_test_bin, y_pred, zero_division=0)
        f1 = f1_score(y_test_bin, y_pred, zero_division=0)
        try:
            auc = roc_auc_score(y_test_bin, y_prob)
        except Exception:
            auc = 0.5
        kappa = cohen_kappa_score(y_test_bin, y_pred)

        print(f"\n--- {name} (Evaluated on 90 Gold Cases) ---")
        print(f"  TP: {tp} | FP: {fp} | FN: {fn} | TN: {tn}")
        print(f"  Precision: {prec:.4f} | Recall: {rec:.4f} | F1: {f1:.4f} | ROC-AUC: {auc:.4f} | Kappa: {kappa:.4f}")

        binary_results[name] = {
            "TP": tp, "FP": fp, "FN": fn, "TN": tn,
            "precision": round(prec, 4),
            "recall": round(rec, 4),
            "f1": round(f1, 4),
            "roc_auc": round(auc, 4),
            "cohen_kappa": round(kappa, 4),
        }

    # -------------------------------------------------------------
    # 2. Multiclass Model: Lifecycle Stage Classifier
    # -------------------------------------------------------------
    print("\n" + "=" * 50)
    print("TASK 2: MULTICLASS LIFECYCLE CLASSIFIER")
    print("=" * 50)

    rf_multi = RandomForestClassifier(n_estimators=150, class_weight="balanced", random_state=42)
    rf_multi.fit(X_train, y_train_multi, sample_weight=sample_weights)

    y_pred_multi = rf_multi.predict(X_test)
    exact_acc = (y_test_multi == y_pred_multi).mean()
    macro_f1 = f1_score(y_test_multi, y_pred_multi, average="macro", zero_division=0)
    multi_kappa = cohen_kappa_score(y_test_multi, y_pred_multi)

    print(f"\nExact Accuracy on 90 Gold cases: {exact_acc:.4f} ({sum(y_test_multi == y_pred_multi)}/90)")
    print(f"Macro-F1 on 90 Gold cases:        {macro_f1:.4f}")
    print(f"Cohen's Kappa on 90 Gold cases:   {multi_kappa:.4f}")

    print("\nPer-class Classification Report (Gold Test Set):")
    print(classification_report(y_test_multi, y_pred_multi, zero_division=0))

    # Feature Importance
    importances = pd.Series(rf_multi.feature_importances_, index=FEATURE_COLS).sort_values(ascending=False)
    print("\nTop 10 Most Informative Features (Random Forest):")
    print(importances.head(10))

    # Save summary
    summary = {
        "silver_train_n": len(silver_df),
        "gold_test_n": len(gold_df),
        "binary_models": binary_results,
        "multiclass_rf": {
            "exact_accuracy": round(exact_acc, 4),
            "macro_f1": round(macro_f1, 4),
            "cohen_kappa": round(multi_kappa, 4),
        },
        "top_features": importances.head(10).to_dict(),
    }
    with (RESULTS_DIR / "evaluation_summary.json").open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    importances.to_frame("importance").to_csv(RESULTS_DIR / "feature_importance.csv")
    print(f"\nAll results saved to {RESULTS_DIR}")
    print("=" * 60)


if __name__ == "__main__":
    run_training_pipeline()
