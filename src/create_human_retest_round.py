"""Create a blinded, re-randomized human test-retest round from fixed cases."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
INTERIM = ROOT / "data" / "interim"
DEFAULT_INPUT = INTERIM / "holdout_human_v1_90_workbook.csv"
DEFAULT_OUTPUT = INTERIM / "holdout_human_v1_90_r2_blinded.csv"
DEFAULT_KEY = INTERIM / "holdout_human_v1_90_r2_key.csv"
DEFAULT_MANIFEST = INTERIM / "holdout_human_v1_90_r2_manifest.json"
SEED = 2026101302


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--key", type=Path, default=DEFAULT_KEY)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args()

    source = pd.read_csv(args.input, dtype=str, keep_default_na=False)
    if len(source) != 90:
        raise ValueError(f"Expected 90 fixed human-review cases, found {len(source)}")
    id_column = "human_review_id" if "human_review_id" in source.columns else "review_id"
    if source[id_column].duplicated().any():
        raise ValueError("Round-1 human review IDs must be unique")

    source = source.rename(columns={id_column: "round1_review_id"})
    source["random_order"] = source["round1_review_id"].map(
        lambda value: hashlib.sha256(f"{SEED}:{value}".encode()).hexdigest()
    )
    shuffled = source.sort_values("random_order").reset_index(drop=True)
    shuffled["round2_review_id"] = [f"R2-{i:03d}" for i in range(1, len(shuffled) + 1)]

    key = shuffled[["round2_review_id", "round1_review_id"]].copy()
    key.to_csv(args.key, index=False)

    public = shuffled.drop(columns=["round1_review_id", "random_order"]).rename(
        columns={"round2_review_id": "review_id"}
    )
    public["reviewer_id"] = ""
    public["manual_classification"] = ""
    public["evidence_note"] = ""
    public["access_issue"] = ""

    ordered_columns = [
        "review_id",
        "repo_name",
        "anchor_sha",
        "artifact_path",
        "code_path",
        "resolved_path",
        "task_url",
        "literal_path_url",
        "anchor_path",
        "anchor_path_url",
        "task_context",
        "reviewer_id",
        "manual_classification",
        "evidence_note",
        "access_issue",
    ]
    public = public[ordered_columns]
    public.to_csv(args.output, index=False)

    manifest = {
        "purpose": "Blinded same-reviewer test-retest round on the fixed 90-case human sample",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "seed": SEED,
        "n_cases": len(public),
        "source_file": str(args.input),
        "source_sha256": sha256(args.input),
        "blinded_file": str(args.output),
        "blinded_file_sha256": sha256(args.output),
        "private_key": str(args.key),
        "private_key_sha256": sha256(args.key),
        "blinding": [
            "round-1 review ID",
            "round-1 human classification",
            "all pipeline outputs",
            "deterministic routing stage",
            "LLM classification",
        ],
        "interpretation": "Measures intra-rater stability; it is not an independent second-reviewer assessment.",
    }
    args.manifest.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    print(
        json.dumps(
            {
                "cases": len(public),
                "first_ids": public["review_id"].head(3).tolist(),
                "output": str(args.output),
                "key": str(args.key),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
