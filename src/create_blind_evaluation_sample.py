"""Create a fresh balanced blind evaluation set from unreviewed confirmation cases.

The source confirmation sample is fixed. Cases already adjudicated in the supplied
human-answer CSV are excluded, then ten references from each validation stratum
are selected deterministically. The workbook-facing CSV deliberately omits
automatic labels and strata; those remain in the private key.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
INTERIM = PROJECT_ROOT / "data" / "interim"
MASTER_PATH = INTERIM / "validation_workbook_confirmatory_en.csv"
ORIGINAL_KEY_PATH = INTERIM / "validation_blinding_key_confirmatory_en.csv"
DEFAULT_ANSWERED_PATH = (
    Path("/Users/pedroodorize/Downloads")
    / "validation_human_blinded_confirmatory_en_30_answered - Review.csv"
)
OUTPUT_CSV = INTERIM / "validation_blind_eval_30_en.csv"
OUTPUT_KEY = INTERIM / "validation_blind_eval_30_en_key.csv"
OUTPUT_MANIFEST = INTERIM / "validation_blind_eval_30_en_manifest.json"
SEED = 20261001
N_PER_GROUP = 10


def nonblank(series: pd.Series) -> pd.Series:
    return series.fillna("").astype(str).str.strip().ne("")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--answered", type=Path, default=DEFAULT_ANSWERED_PATH)
    args = parser.parse_args()

    answered = pd.read_csv(args.answered)
    required_answer_columns = {"Review ID", "Classificação", "Nota de evidência"}
    missing = required_answer_columns.difference(answered.columns)
    if missing:
        raise ValueError(f"Answered CSV is missing columns: {sorted(missing)}")

    reviewed = answered.loc[nonblank(answered["Classificação"]), "Review ID"].astype(str)
    if len(reviewed) != 30:
        raise ValueError(f"Expected 30 answered review IDs; found {len(reviewed)}")
    if not nonblank(answered.loc[answered["Review ID"].isin(reviewed), "Nota de evidência"]).all():
        raise ValueError("Every answered review must include an evidence note")

    master = pd.read_csv(MASTER_PATH)
    original_key = pd.read_csv(ORIGINAL_KEY_PATH)
    reviewed_ids = set(
        original_key.loc[original_key["review_id"].astype(str).isin(set(reviewed)), "id"]
    )
    if len(reviewed_ids) != 30:
        raise ValueError("Could not map all answered review IDs to source references")

    remaining = master.loc[~master["id"].isin(reviewed_ids)].copy()
    sampled_parts: list[pd.DataFrame] = []
    for group, group_rows in remaining.groupby("validation_group", sort=True):
        if len(group_rows) < N_PER_GROUP:
            raise ValueError(f"Only {len(group_rows)} remaining rows in {group}")
        sampled_parts.append(group_rows.sample(n=N_PER_GROUP, random_state=SEED))
    sampled = pd.concat(sampled_parts, ignore_index=True)
    sampled = sampled.sample(frac=1, random_state=SEED).reset_index(drop=True)
    sampled.insert(0, "review_id", [f"B{n:03d}" for n in range(1, len(sampled) + 1)])

    review_columns = [
        "review_id",
        "repo_name",
        "anchor_sha",
        "artifact_path",
        "code_path",
        "resolved_path",
        "artifact_url",
        "literal_code_url",
        "anchor_code_path",
        "anchor_code_url",
        "reference_excerpt",
    ]
    blind = sampled[review_columns].copy()
    blind["reviewer_id"] = ""
    blind["manual_classification"] = ""
    blind["evidence_note"] = ""
    blind["access_issue"] = ""
    blind.to_csv(OUTPUT_CSV, index=False)

    private_key = sampled[
        ["review_id", "id", "validation_group", "task_done", "exists_at_anchor"]
    ].copy()
    private_key.to_csv(OUTPUT_KEY, index=False)

    group_counts = private_key["validation_group"].value_counts().sort_index().to_dict()
    OUTPUT_MANIFEST.write_text(
        json.dumps(
            {
                "purpose": "Fresh blind human evaluation for LLM comparison",
                "dataset": "SpecMine July 2026 release",
                "source_sample": MASTER_PATH.name,
                "excluded_answered_file": args.answered.name,
                "excluded_answered_reviews": sorted(reviewed.tolist()),
                "seed": SEED,
                "n_per_group": N_PER_GROUP,
                "group_counts": group_counts,
                "n_references": len(blind),
                "review_csv": OUTPUT_CSV.name,
                "private_key": OUTPUT_KEY.name,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    print(f"Created {len(blind)} blind reviews")
    print(f"Group counts: {group_counts}")
    print(f"Review CSV: {OUTPUT_CSV}")
    print(f"Private key: {OUTPUT_KEY}")


if __name__ == "__main__":
    main()
