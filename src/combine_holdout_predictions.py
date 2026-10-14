"""Combine frozen rules, abstentions, and LLM results into one prediction file."""

from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HYBRID = ROOT / "results" / "validation" / "holdout_v1" / "hybrid_stage"
LLM = ROOT / "data" / "interim" / "holdout_llm_v1_results.csv"
OUTPUT = ROOT / "data" / "interim" / "holdout_pipeline_v1_predictions.csv"
MANIFEST = ROOT / "data" / "interim" / "holdout_pipeline_v1_predictions_manifest.json"
SCREENING = ROOT / "data" / "interim" / "holdout_screening_v1_240.csv"
FREEZE = ROOT / "results" / "validation" / "holdout_v1" / "FROZEN_CONFIG.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> None:
    with SCREENING.open(newline="", encoding="utf-8-sig") as handle:
        ordered_ids = [row["review_id"] for row in csv.DictReader(handle)]
    rows: dict[str, dict[str, object]] = {}
    for record in jsonl(HYBRID / "rule_decisions.jsonl"):
        rows[str(record["review_id"])] = {
            "review_id": record["review_id"], "pipeline_stage": "deterministic_rule",
            "pipeline_decision": "classify", "pipeline_classification": record["classification"],
            "confidence": "", "evidence_quote": "", "rationale": record["rationale"],
            "rule_id": record["rule_id"], "missing_evidence": json.dumps(record["missing_evidence"]),
        }
    for record in jsonl(HYBRID / "abstentions.jsonl"):
        rows[str(record["review_id"])] = {
            "review_id": record["review_id"], "pipeline_stage": "deterministic_abstention",
            "pipeline_decision": "abstain", "pipeline_classification": record["classification"],
            "confidence": "", "evidence_quote": "", "rationale": record["rationale"],
            "rule_id": record["rule_id"], "missing_evidence": json.dumps(record["missing_evidence"]),
        }
    with LLM.open(newline="", encoding="utf-8-sig") as handle:
        for record in csv.DictReader(handle):
            if record["valid_response"].lower() != "true":
                raise ValueError(f"Invalid LLM response: {record['review_id']}")
            rows[record["review_id"]] = {
                "review_id": record["review_id"], "pipeline_stage": "llm_semantic_review",
                "pipeline_decision": record["decision"], "pipeline_classification": record["classification"],
                "confidence": record["confidence"], "evidence_quote": record["evidence_quote"],
                "rationale": record["rationale"], "rule_id": "",
                "missing_evidence": record["missing_evidence"],
            }
    if set(rows) != set(ordered_ids):
        raise ValueError(f"Prediction IDs differ from screening IDs: missing={set(ordered_ids)-set(rows)}, extra={set(rows)-set(ordered_ids)}")
    ordered = [rows[review_id] for review_id in ordered_ids]
    with OUTPUT.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(ordered[0]))
        writer.writeheader()
        writer.writerows(ordered)
    counts: dict[str, int] = {}
    labels: dict[str, int] = {}
    for row in ordered:
        stage = str(row["pipeline_stage"])
        label = str(row["pipeline_classification"])
        counts[stage] = counts.get(stage, 0) + 1
        labels[label] = labels.get(label, 0) + 1
    manifest = {
        "purpose": "Frozen held-out v1 pipeline predictions before human sampling",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "human_labels_observed": False,
        "records": len(ordered),
        "stage_counts": counts,
        "classification_counts": labels,
        "screening_sha256": sha256(SCREENING),
        "hybrid_manifest_sha256": sha256(HYBRID / "manifest.json"),
        "llm_results_sha256": sha256(LLM),
        "frozen_config_sha256": sha256(FREEZE),
        "output_sha256": sha256(OUTPUT),
    }
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"stage_counts": counts, "classification_counts": labels}, indent=2))
    print(f"Predictions: {OUTPUT}")


if __name__ == "__main__":
    main()
