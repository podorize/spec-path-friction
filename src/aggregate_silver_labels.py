"""Aggregate labeled shards from Gemini Judge and merge with ML feature matrix."""

from __future__ import annotations

import json
from pathlib import Path
import sys

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

INTERIM = PROJECT_ROOT / "data" / "interim"
SHARDS_DIR = INTERIM / "silver_shards"
KEY_CSV = INTERIM / "silver_sample_450_key.csv"
FEATURES_PARQUET = INTERIM / "silver_ml_features_450.parquet"
OUTPUT_PARQUET = INTERIM / "silver_labeled_dataset_450.parquet"
OUTPUT_CSV = INTERIM / "silver_labeled_dataset_450.csv"

from src.extract_reference_ml_features import map_targets


def main() -> None:
    print("=" * 60)
    print("AGGREGATING SILVER LABELS (GEMINI JUDGE)")
    print("=" * 60)

    # 1. Check all 18 output shards
    records: list[dict] = []
    missing_shards = []
    for i in range(1, 19):
        p = SHARDS_DIR / f"output_{i:02d}.json"
        if not p.exists():
            missing_shards.append(f"output_{i:02d}.json")
            continue
        try:
            with p.open("r", encoding="utf-8") as f:
                data = json.load(f)
            assert isinstance(data, list), f"{p} is not a JSON list"
            records.extend(data)
            print(f"Loaded {len(data)} records from output_{i:02d}.json")
        except Exception as e:
            print(f"Error loading {p}: {e}")
            missing_shards.append(f"output_{i:02d}.json (corrupted)")

    if missing_shards:
        print(f"WARNING: {len(missing_shards)} shards missing or incomplete: {missing_shards}")
        print(f"Total records loaded so far: {len(records)} / 450")
        if not records:
            return
    else:
        print(f"All 18 shards successfully loaded! Total records: {len(records)}")
        assert len(records) == 450, f"Expected 450 records, got {len(records)}"

    preds_df = pd.DataFrame(records)

    # 2. Map targets
    target_mappings = [map_targets(c) for c in preds_df["classification"]]
    preds_df["target_problematic_binary"] = [m["target_problematic_binary"] for m in target_mappings]
    preds_df["target_lifecycle_multiclass"] = [m["target_lifecycle_multiclass"] for m in target_mappings]

    # 3. Load ML features
    feat_df = pd.read_parquet(FEATURES_PARQUET)
    print(f"Loaded {len(feat_df)} ML feature rows.")

    # 4. Merge on review_id
    merged = feat_df.merge(
        preds_df[[
            "review_id",
            "decision",
            "classification",
            "confidence",
            "evidence_quote",
            "rationale",
            "target_problematic_binary",
            "target_lifecycle_multiclass",
        ]],
        on="review_id",
        how="inner",
    )
    print(f"Merged dataset shape: {merged.shape}")

    # 5. Save final Silver dataset
    merged.to_parquet(OUTPUT_PARQUET, compression="zstd", index=False)
    merged.to_csv(OUTPUT_CSV, index=False)
    print(f"Saved silver labeled dataset: {OUTPUT_PARQUET} and {OUTPUT_CSV}")

    # 6. Print distribution summary
    print("\n--- CLASSIFICATION DISTRIBUTION ---")
    print(merged["classification"].value_counts())
    print("\n--- MULTICLASS TARGET DISTRIBUTION ---")
    print(merged["target_lifecycle_multiclass"].value_counts())
    print("\n--- BINARY PROBLEMATIC TARGET ---")
    print(merged["target_problematic_binary"].value_counts())
    print("\n--- BREAKDOWN BY STRATA ---")
    print(pd.crosstab(merged["strata_group"], merged["target_lifecycle_multiclass"]))
    print("=" * 60)


if __name__ == "__main__":
    main()
