"""Convert the evidence packet into leakage-free LLM records."""

from __future__ import annotations

import csv
import json
import argparse
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INTERIM = ROOT / "data" / "interim"
SOURCE = INTERIM / "evidence_equivalent_pilot_10.jsonl"
KEY = INTERIM / "validation_human_fresh_90_en_key.csv"
OUTPUT = INTERIM / "llm_judge_inputs_evidence_equivalent_pilot_10.jsonl"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    key = {r["review_id"]: r for r in csv.DictReader(KEY.open(encoding="utf-8-sig"))}
    records = []
    for line in args.source.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        review_id = record["review_id"]
        records.append({"reference_id": int(key[review_id]["id"]), **record})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(f"Prepared {len(records)} evidence-equivalent inputs: {args.output}")


if __name__ == "__main__":
    main()
