"""Run corpus-wide supervised inference on all 51,979 missing OpenSpec references."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import time

import duckdb
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

INTERIM = PROJECT_ROOT / "data" / "interim"
PROCESSED = PROJECT_ROOT / "data" / "processed"
PROCESSED.mkdir(parents=True, exist_ok=True)

RESULTS_DIR = PROJECT_ROOT / "results" / "corpus_inference"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

SILVER_PARQUET = INTERIM / "silver_labeled_dataset_450.parquet"
FEATURES_MISSING = INTERIM / "reference_ml_features_missing.parquet"
OUTPUT_PREDICTIONS = PROCESSED / "specmine_missing_refs_classified.parquet"

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


def main() -> None:
    print("=" * 60)
    print("RUNNING CORPUS-WIDE INFERENCE ON ALL MISSING REFERENCES")
    print("=" * 60)

    # 1. Load Silver Training Data
    print(f"Loading silver training data from {SILVER_PARQUET}...")
    silver_df = pd.read_parquet(SILVER_PARQUET)
    print(f"Loaded {len(silver_df)} instances from Silver dataset.")

    X_train = silver_df[FEATURE_COLS].copy()
    y_train_bin = silver_df["target_problematic_binary"].astype(int)
    y_train_multi = silver_df["target_lifecycle_multiclass"].astype(str)
    sample_weights = silver_df["sampling_weight"].values

    # 2. Train Production Classifiers
    print("Fitting production Random Forest models with sample weights...")
    t0 = time.time()
    rf_binary = RandomForestClassifier(n_estimators=150, class_weight="balanced", random_state=42)
    rf_binary.fit(X_train, y_train_bin, sample_weight=sample_weights)

    rf_multi = RandomForestClassifier(n_estimators=150, class_weight="balanced", random_state=42)
    rf_multi.fit(X_train, y_train_multi, sample_weight=sample_weights)
    print(f"Models fitted in {time.time() - t0:.2f}s.")

    # 3. Load All Missing References Features (51,979 rows)
    print(f"Loading feature matrix for all missing references ({FEATURES_MISSING})...")
    t1 = time.time()
    missing_df = pd.read_parquet(FEATURES_MISSING)
    print(f"Loaded {len(missing_df):,} missing reference rows in {time.time() - t1:.2f}s.")

    X_missing = missing_df[FEATURE_COLS].copy()

    # 4. Predict
    print("Predicting friction probabilities and lifecycle stages...")
    t2 = time.time()
    prob_problematic = rf_binary.predict_proba(X_missing)[:, 1]
    pred_lifecycle = rf_multi.predict(X_missing)
    print(f"Inference completed in {time.time() - t2:.2f}s ({len(missing_df)/(time.time() - t2):.0f} rows/s).")

    # Add predictions
    missing_df["prob_problematic"] = np.round(prob_problematic, 4)
    # Calibrated threshold = 0.20 (which achieved 100% recall on the Gold Standard)
    missing_df["pred_is_problematic_calibrated"] = (prob_problematic >= 0.20).astype(int)
    # Standard threshold = 0.50 (high precision)
    missing_df["pred_is_problematic_conservative"] = (prob_problematic >= 0.50).astype(int)
    missing_df["pred_lifecycle_stage"] = pred_lifecycle

    # 5. Save Processed Predictions Parquet
    cols_to_save = [
        "id",
        "repo_name",
        "artifact_path",
        "code_path",
        "task_done",
        "exists_at_anchor",
        "is_test_file",
        "is_source_file",
        "is_config_file",
        "is_doc_file",
        "has_glob_pattern",
        "is_monorepo",
        "verb_create",
        "verb_update",
        "verb_delete",
        "prob_problematic",
        "pred_is_problematic_calibrated",
        "pred_is_problematic_conservative",
        "pred_lifecycle_stage",
    ]
    missing_df[cols_to_save].to_parquet(OUTPUT_PREDICTIONS, compression="zstd", index=False)
    print(f"Saved classified corpus predictions to {OUTPUT_PREDICTIONS} (size: {OUTPUT_PREDICTIONS.stat().st_size / 1024 / 1024:.2f} MB).")

    # -------------------------------------------------------------
    # 6. Aggregate Corpus Statistics (RQ1 & RQ2)
    # -------------------------------------------------------------
    total_missing = len(missing_df)
    n_done_missing = int((missing_df["task_done"] == 1).sum())
    n_open_missing = int((missing_df["task_done"] == 0).sum())

    # Lifecycle breakdown
    lifecycle_counts = missing_df["pred_lifecycle_stage"].value_counts()
    lifecycle_pcts = (lifecycle_counts / total_missing * 100).round(2)
    lifecycle_summary = pd.DataFrame({"count": lifecycle_counts, "percentage": lifecycle_pcts})

    # Breakdown by task_done
    by_task_done = pd.crosstab(
        missing_df["task_done"],
        missing_df["pred_lifecycle_stage"],
        margins=True,
    )
    by_task_done.to_csv(RESULTS_DIR / "lifecycle_distribution_by_task_done.csv")

    # Friction counts
    calibrated_friction = int(missing_df["pred_is_problematic_calibrated"].sum())
    calibrated_friction_pct = round(calibrated_friction / total_missing * 100, 2)

    conservative_friction = int(missing_df["pred_is_problematic_conservative"].sum())
    conservative_friction_pct = round(conservative_friction / total_missing * 100, 2)

    # In completed tasks specifically
    done_mask = missing_df["task_done"] == 1
    done_calibrated = int(missing_df.loc[done_mask, "pred_is_problematic_calibrated"].sum())
    done_calibrated_pct = round(done_calibrated / n_done_missing * 100, 2)

    done_conservative = int(missing_df.loc[done_mask, "pred_is_problematic_conservative"].sum())
    done_conservative_pct = round(done_conservative / n_done_missing * 100, 2)

    # Breakdown by extension
    missing_df["file_extension"] = missing_df["code_path"].apply(lambda p: Path(p.replace("\\", "/")).suffix.lower())
    ext_counts = missing_df["file_extension"].value_counts().head(15)
    ext_records = []
    for ext, cnt in ext_counts.items():
        if not ext:
            continue
        sub = missing_df[missing_df["file_extension"] == ext]
        ext_records.append({
            "extension": ext,
            "total_references": cnt,
            "pct_of_missing": round(cnt / total_missing * 100, 2),
            "calibrated_friction_count": int(sub["pred_is_problematic_calibrated"].sum()),
            "friction_rate_pct": round(sub["pred_is_problematic_calibrated"].mean() * 100, 2),
            "top_lifecycle_stage": sub["pred_lifecycle_stage"].mode().iloc[0],
        })
    ext_df = pd.DataFrame(ext_records).sort_values(by="total_references", ascending=False)
    ext_df.to_csv(RESULTS_DIR / "extension_friction_breakdown.csv", index=False)

    # Test vs Non-test friction
    test_friction_rate = round(missing_df.loc[missing_df["is_test_file"] == 1, "pred_is_problematic_calibrated"].mean() * 100, 2)
    source_friction_rate = round(missing_df.loc[missing_df["is_source_file"] == 1, "pred_is_problematic_calibrated"].mean() * 100, 2)

    # Repository level aggregation
    repo_stats = missing_df.groupby("repo_name").agg(
        total_missing=("id", "count"),
        completed_missing=("task_done", "sum"),
        friction_refs=("pred_is_problematic_calibrated", "sum"),
        avg_friction_prob=("prob_problematic", "mean"),
    ).reset_index()
    repo_stats["friction_rate_pct"] = (repo_stats["friction_refs"] / repo_stats["total_missing"] * 100).round(2)
    top_friction_repos = repo_stats.sort_values(by=["friction_refs", "total_missing"], ascending=False).head(30)
    top_friction_repos.to_csv(RESULTS_DIR / "top_friction_repositories.csv", index=False)

    # 7. Print Console Summary
    print("\n" + "=" * 60)
    print("CORPUS-WIDE PREDICTION SUMMARY (51,979 MISSING REFERENCES)")
    print("=" * 60)
    print(f"Total Missing References Analyzed: {total_missing:,}")
    print(f"  Completed Tasks (task_done = 1):  {n_done_missing:,} ({n_done_missing/total_missing*100:.1f}%)")
    print(f"  Open Tasks (task_done = 0):       {n_open_missing:,} ({n_open_missing/total_missing*100:.1f}%)")
    print(f"Unique Repositories Covered:        {missing_df['repo_name'].nunique():,}")

    print("\n--- PREDICTED LIFECYCLE DISTRIBUTION (CORPUS-WIDE) ---")
    for stage, row in lifecycle_summary.iterrows():
        print(f"  {stage:<15}: {row['count']:>7,} ({row['percentage']:>5.2f}%)")

    print("\n--- ESTIMATED SPECIFICATION FRICTION RATE ---")
    print(f"  Calibrated Threshold (>= 0.20):   {calibrated_friction:,} ({calibrated_friction_pct}%)")
    print(f"    - In Completed Tasks (done=1):  {done_calibrated:,} ({done_calibrated_pct}%)")
    print(f"  Conservative Threshold (>= 0.50): {conservative_friction:,} ({conservative_friction_pct}%)")
    print(f"    - In Completed Tasks (done=1):  {done_conservative:,} ({done_conservative_pct}%)")

    print(f"\nTest vs Source Friction Rate:")
    print(f"  Test files (is_test=1):   {test_friction_rate}% friction rate")
    print(f"  Source code (is_source=1): {source_friction_rate}% friction rate")

    # 8. Save JSON summary for paper
    corpus_summary = {
        "total_missing_references": total_missing,
        "completed_missing": n_done_missing,
        "open_missing": n_open_missing,
        "unique_repositories": int(missing_df["repo_name"].nunique()),
        "predicted_lifecycle_breakdown": lifecycle_summary.to_dict(),
        "friction_metrics": {
            "calibrated_threshold": 0.20,
            "calibrated_friction_total": calibrated_friction,
            "calibrated_friction_pct": calibrated_friction_pct,
            "completed_calibrated_friction": done_calibrated,
            "completed_calibrated_friction_pct": done_calibrated_pct,
            "conservative_threshold": 0.50,
            "conservative_friction_total": conservative_friction,
            "conservative_friction_pct": conservative_friction_pct,
            "completed_conservative_friction": done_conservative,
            "completed_conservative_friction_pct": done_conservative_pct,
        },
        "domain_friction_rates": {
            "test_files_friction_rate_pct": test_friction_rate,
            "source_files_friction_rate_pct": source_friction_rate,
        },
    }
    with (RESULTS_DIR / "corpus_predictions_summary.json").open("w", encoding="utf-8") as f:
        json.dump(corpus_summary, f, indent=2)

    print(f"\nAll corpus-wide results successfully saved to {RESULTS_DIR}")
    print("=" * 60)


if __name__ == "__main__":
    main()
