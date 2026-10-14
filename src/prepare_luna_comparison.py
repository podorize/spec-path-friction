"""Prepare paired hybrid-Luna and Luna-only inputs for the same 90 holdout cases."""

from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from classify_reference_rules import classify_record


ROOT = Path(__file__).resolve().parents[1]
INTERIM = ROOT / "data" / "interim"
OUTPUT = ROOT / "results" / "validation" / "holdout_v1" / "luna_comparison"
EVIDENCE = INTERIM / "holdout_longitudinal_evidence_v1_240.jsonl"
HUMAN_KEY = INTERIM / "holdout_human_v1_90_key.csv"
PROMPT = ROOT / "validation" / "LLM_JUDGE_PROMPT_LONGITUDINAL_V2.md"
SCHEMA = ROOT / "validation" / "llm_judge_output_schema_v2.json"
RULES = ROOT / "src" / "classify_reference_rules.py"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def main() -> None:
    with HUMAN_KEY.open(newline="", encoding="utf-8-sig") as handle:
        key_rows = list(csv.DictReader(handle))
    selected_ids = {row["review_id"] for row in key_rows}
    if len(selected_ids) != 90:
        raise ValueError("Human sample key must contain 90 unique screening IDs")

    evidence_by_id = {row["review_id"]: row for row in read_jsonl(EVIDENCE)}
    if not selected_ids.issubset(evidence_by_id):
        raise ValueError(f"Missing evidence: {sorted(selected_ids - set(evidence_by_id))}")
    ordered_ids = [row["review_id"] for row in key_rows]
    all_records = [evidence_by_id[review_id] for review_id in ordered_ids]

    rule_decisions: list[dict[str, Any]] = []
    deterministic_abstentions: list[dict[str, Any]] = []
    hybrid_luna_input: list[dict[str, Any]] = []
    for record in all_records:
        decision = classify_record(record)
        result = {"review_id": record["review_id"], **decision}
        if decision["decision"] == "classified":
            rule_decisions.append(result)
        elif decision["decision"] == "abstain":
            deterministic_abstentions.append(result)
        else:
            # The LLM receives exactly the same evidence object as Luna-only.
            # Routing metadata is intentionally excluded from the model input.
            hybrid_luna_input.append(record)

    OUTPUT.mkdir(parents=True, exist_ok=True)
    paths = {
        "all_luna_input": OUTPUT / "luna_only_input_90.jsonl",
        "hybrid_luna_input": OUTPUT / "hybrid_luna_input.jsonl",
        "rule_decisions": OUTPUT / "rule_decisions.jsonl",
        "deterministic_abstentions": OUTPUT / "deterministic_abstentions.jsonl",
    }
    write_jsonl(paths["all_luna_input"], all_records)
    write_jsonl(paths["hybrid_luna_input"], hybrid_luna_input)
    write_jsonl(paths["rule_decisions"], rule_decisions)
    write_jsonl(paths["deterministic_abstentions"], deterministic_abstentions)

    manifest = {
        "purpose": "Paired comparison of frozen deterministic-plus-Luna and Luna-only architectures",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "human_labels_used_to_select_or_route_cases": False,
        "records": len(all_records),
        "counts": {
            "deterministic_classifications": len(rule_decisions),
            "deterministic_abstentions": len(deterministic_abstentions),
            "hybrid_luna_calls": len(hybrid_luna_input),
            "luna_only_calls": len(all_records),
        },
        "model": "gpt-6-luna",
        "reasoning_effort": "high",
        "evidence_file": str(EVIDENCE.relative_to(ROOT)),
        "evidence_sha256": sha256(EVIDENCE),
        "human_sample_key_sha256": sha256(HUMAN_KEY),
        "rules_sha256": sha256(RULES),
        "prompt_sha256": sha256(PROMPT),
        "schema_sha256": sha256(SCHEMA),
        "outputs": {name: {"path": str(path.relative_to(ROOT)), "sha256": sha256(path)} for name, path in paths.items()},
    }
    (OUTPUT / "PRE_RUN_MANIFEST.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest["counts"], indent=2))


if __name__ == "__main__":
    main()
