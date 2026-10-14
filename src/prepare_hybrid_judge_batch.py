"""Partition evidence into rule decisions, abstentions, and an LLM review queue."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from .classify_reference_rules import classify_record
except ImportError:  # Support direct execution as a script.
    from classify_reference_rules import classify_record


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCHEMA = ROOT / "validation" / "llm_judge_output_schema_v2.json"
DEFAULT_PROMPT = ROOT / "validation" / "LLM_JUDGE_PROMPT_LONGITUDINAL_V2.md"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def partition(records: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    partitions: dict[str, list[dict[str, Any]]] = {"rule_decisions": [], "abstentions": [], "llm_queue": []}
    for record in records:
        decision = classify_record(record)
        common = {"review_id": record["review_id"], **decision}
        if decision["decision"] == "classified":
            partitions["rule_decisions"].append(common)
        elif decision["decision"] == "abstain":
            partitions["abstentions"].append(common)
        else:
            partitions["llm_queue"].append(
                {
                    "review_id": record["review_id"],
                    "evidence": record,
                    "routing": common,
                }
            )
    return partitions


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--prompt", type=Path, default=DEFAULT_PROMPT)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    args = parser.parse_args()
    records = read_jsonl(args.input)
    partitions = partition(records)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    files = {
        "rule_decisions": args.output_dir / "rule_decisions.jsonl",
        "abstentions": args.output_dir / "abstentions.jsonl",
        "llm_queue": args.output_dir / "llm_queue.jsonl",
    }
    for name, path in files.items():
        write_jsonl(path, partitions[name])
    total = len(records)
    manifest = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "development_data": True,
        "input": str(args.input),
        "input_sha256": sha256(args.input),
        "prompt": str(args.prompt),
        "prompt_sha256": sha256(args.prompt),
        "schema": str(args.schema),
        "schema_sha256": sha256(args.schema),
        "counts": {name: len(rows) for name, rows in partitions.items()},
        "automatic_rule_coverage": len(partitions["rule_decisions"]) / total if total else 0,
        "abstention_rate_before_llm": len(partitions["abstentions"]) / total if total else 0,
        "llm_queue_rate": len(partitions["llm_queue"]) / total if total else 0,
        "note": "No model calls are made by this script; the queue is frozen for a separately configured run.",
    }
    (args.output_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest["counts"], indent=2))


if __name__ == "__main__":
    main()
