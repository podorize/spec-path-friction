"""Extract an untouched review batch from the frozen 90-case human sample."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = PROJECT_ROOT / "data" / "interim" / "validation_human_fresh_90_en.csv"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--start", type=int, required=True)
    parser.add_argument("--end", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    if args.start < 1 or args.end < args.start or args.end > 90:
        raise ValueError("The requested range must be within H001-H090")

    frame = pd.read_csv(args.source, dtype=str, keep_default_na=False)
    expected_ids = [f"H{number:03d}" for number in range(args.start, args.end + 1)]
    batch = frame.loc[frame["review_id"].isin(expected_ids)].copy()
    batch["_order"] = pd.Categorical(batch["review_id"], expected_ids, ordered=True)
    batch = batch.sort_values("_order").drop(columns="_order")

    if batch["review_id"].tolist() != expected_ids:
        raise ValueError("Could not recover every requested review ID from the frozen sample")
    response_columns = [
        "reviewer_id",
        "manual_classification",
        "evidence_note",
        "access_issue",
    ]
    if any(batch[column].astype(str).str.strip().ne("").any() for column in response_columns):
        raise ValueError("The requested batch already contains review responses")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    batch.to_csv(args.output, index=False)
    print(f"Created {len(batch)} untouched reviews: {expected_ids[0]}-{expected_ids[-1]}")
    print(f"Output: {args.output}")


if __name__ == "__main__":
    main()
