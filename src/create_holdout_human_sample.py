"""Draw phase-2 blinded human cases after holdout pipeline predictions freeze."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
INTERIM = ROOT / "data" / "interim"
DEFAULT_SCREENING = INTERIM / "holdout_screening_v1_240.csv"
DEFAULT_KEY = INTERIM / "holdout_screening_v1_240_key.csv"
DEFAULT_OUTPUT = INTERIM / "holdout_human_v1_90_blinded.csv"
DEFAULT_OUTPUT_KEY = INTERIM / "holdout_human_v1_90_key.csv"
DEFAULT_MANIFEST = INTERIM / "holdout_human_v1_90_manifest.json"
SEED = 20261013
TOTAL_HUMAN_CASES = 90
BASE_TARGET = 30
STRATUM_ORDER = ["predicted_problematic", "pipeline_abstention", "predicted_non_problematic"]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prediction_stratum(row: pd.Series) -> str:
    decision = str(row["pipeline_decision"])
    classification = str(row["pipeline_classification"])
    if decision == "abstain":
        return "pipeline_abstention"
    if classification == "confirmed_missing_problematic":
        return "predicted_problematic"
    return "predicted_non_problematic"


def allocate_counts(counts: dict[str, int], total: int = TOTAL_HUMAN_CASES) -> dict[str, int]:
    allocation = {name: min(BASE_TARGET, counts.get(name, 0)) for name in STRATUM_ORDER}
    remaining = total - sum(allocation.values())
    while remaining > 0:
        available = {name: counts.get(name, 0) - allocation[name] for name in STRATUM_ORDER}
        choices = [name for name in STRATUM_ORDER if available[name] > 0]
        if not choices:
            raise ValueError(f"Only {sum(allocation.values())} cases available for a {total}-case human sample")
        chosen = max(choices, key=lambda name: (available[name], -STRATUM_ORDER.index(name)))
        allocation[chosen] += 1
        remaining -= 1
    return allocation


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("predictions", type=Path, help="Frozen CSV with review_id, pipeline_decision, pipeline_classification")
    parser.add_argument("--screening", type=Path, default=DEFAULT_SCREENING)
    parser.add_argument("--screening-key", type=Path, default=DEFAULT_KEY)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--output-key", type=Path, default=DEFAULT_OUTPUT_KEY)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args()

    screening = pd.read_csv(args.screening, dtype=str, keep_default_na=False)
    screening_key = pd.read_csv(args.screening_key)
    predictions = pd.read_csv(args.predictions, dtype=str, keep_default_na=False)
    required = {"review_id", "pipeline_decision", "pipeline_classification"}
    if not required.issubset(predictions.columns):
        raise ValueError(f"Prediction file is missing: {sorted(required - set(predictions.columns))}")
    if len(predictions) != len(screening) or set(predictions["review_id"]) != set(screening["review_id"]):
        raise ValueError("Predictions must contain exactly the 240 frozen screening IDs")
    if predictions["review_id"].duplicated().any():
        raise ValueError("Prediction IDs must be unique")

    merged = screening.merge(predictions, on="review_id", validate="one_to_one").merge(screening_key, on="review_id", validate="one_to_one")
    merged["prediction_stratum"] = merged.apply(prediction_stratum, axis=1)
    counts = merged["prediction_stratum"].value_counts().reindex(STRATUM_ORDER, fill_value=0).astype(int).to_dict()
    allocation = allocate_counts(counts)
    selected_parts: list[pd.DataFrame] = []
    for stratum in STRATUM_ORDER:
        rows = merged.loc[merged["prediction_stratum"] == stratum].copy()
        rows["phase2_hash"] = rows["id"].map(lambda value: int(hashlib.sha256(f"{SEED}:{int(value)}".encode()).hexdigest()[:16], 16))
        rows = rows.sort_values("phase2_hash")
        take = allocation[stratum]
        chosen = rows.head(take).copy()
        chosen["phase2_stratum_size"] = len(rows)
        chosen["phase2_sample_size"] = take
        chosen["phase2_inclusion_probability"] = take / len(rows) if len(rows) else 0
        chosen["final_inclusion_probability"] = chosen["phase1_inclusion_probability"] * chosen["phase2_inclusion_probability"]
        chosen["final_sampling_weight"] = 1 / chosen["final_inclusion_probability"]
        selected_parts.append(chosen)
    selected = pd.concat(selected_parts, ignore_index=True)
    selected["display_hash"] = selected["id"].map(lambda value: int(hashlib.sha256(f"{SEED + 1}:{int(value)}".encode()).hexdigest()[:16], 16))
    selected = selected.sort_values("display_hash").reset_index(drop=True)
    selected["human_review_id"] = [f"V{number:03d}" for number in range(1, len(selected) + 1)]

    public_columns = [
        "human_review_id", "repo_name", "anchor_sha", "artifact_path", "code_path",
        "resolved_path", "task_url", "literal_path_url", "candidate_path_url", "task_context",
    ]
    blinded = selected[public_columns].copy()
    blinded["reviewer_id"] = ""
    blinded["manual_classification"] = ""
    blinded["evidence_note"] = ""
    blinded["access_issue"] = ""
    blinded.to_csv(args.output, index=False)
    key_columns = [
        "human_review_id", "review_id", "id", "sampling_stratum", "prediction_stratum",
        "pipeline_decision", "pipeline_classification", "phase1_inclusion_probability",
        "phase2_stratum_size", "phase2_sample_size", "phase2_inclusion_probability",
        "final_inclusion_probability", "final_sampling_weight",
    ]
    selected[key_columns].to_csv(args.output_key, index=False)
    manifest = {
        "purpose": "Independent blinded phase-2 human reference sample",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "seed": SEED,
        "n_human_cases": len(selected),
        "prediction_stratum_counts_in_screening_sample": counts,
        "human_sample_allocation": allocation,
        "prediction_file": str(args.predictions),
        "prediction_file_sha256": sha256(args.predictions),
        "screening_file_sha256": sha256(args.screening),
        "blinded_file_sha256": sha256(args.output),
        "private_key_sha256": sha256(args.output_key),
        "blinding": ["task_done", "exists_at_anchor", "sampling strata", "pipeline decision", "pipeline label", "confidence", "rationale"],
    }
    args.manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"screening_counts": counts, "human_allocation": allocation}, indent=2))
    print(f"Blinded human cases: {args.output}")


if __name__ == "__main__":
    main()
