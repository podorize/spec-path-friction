"""Apply documented post-audit corrections without overwriting source labels."""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "data" / "interim" / "validation_human_90_R1_adjudicated.csv"
DEFAULT_OUTPUT = ROOT / "data" / "interim" / "validation_human_90_R1_adjudicated_v2.csv"
DEFAULT_LOG = ROOT / "results" / "validation" / "evidence_equivalent_90_v2" / "post_audit_corrections.json"

H025_RATIONALE = (
    "Post-audit historical evidence at the anchor commit shows an archived "
    "remove-gmg-stokes-solver change whose task 2.1 explicitly deletes "
    "`TESTS/DisabledBenchmarks/*Gmg*` sources and fixtures. The referenced "
    "TopoRelaxGmgEquivalence.cpp is therefore absent because the GMG fixtures "
    "were retired, not because a completed implementation is missing."
)

CORRECTIONS = {
    "H025": {
        "expected_repo": "tduretz/MDOODZ7.0",
        "expected_code_path": "TopoRelaxGmgEquivalence.cpp",
        "expected_old_label": "expected_absence_create",
        "final_classification": "expected_absence_move_or_delete",
        "adjudication_rationale": H025_RATIONALE,
        "decision_source": "post_audit_historical_evidence",
        "adjudication_status": "post_audit_revised",
        "evidence_url": (
            "https://github.com/tduretz/MDOODZ7.0/blob/"
            "24a5afc64cf79cbdada5e2342d0363a3aeb75203/"
            "openspec/changes/archive/2026-04-21-remove-gmg-stokes-solver/tasks.md"
        ),
    }
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG)
    args = parser.parse_args()

    with args.input.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
        fieldnames = list(rows[0])

    by_id = {row["review_id"]: row for row in rows}
    applied: list[dict[str, str]] = []
    for review_id, correction in CORRECTIONS.items():
        row = by_id.get(review_id)
        if row is None:
            raise ValueError(f"Missing correction target: {review_id}")
        for field, expected in [
            ("repo_name", correction["expected_repo"]),
            ("code_path", correction["expected_code_path"]),
            ("final_classification", correction["expected_old_label"]),
        ]:
            if row[field] != expected:
                raise ValueError(
                    f"{review_id}: expected {field}={expected!r}, found {row[field]!r}"
                )
        old_label = row["final_classification"]
        for field in [
            "final_classification",
            "adjudication_rationale",
            "decision_source",
            "adjudication_status",
        ]:
            row[field] = correction[field]
        applied.append(
            {
                "review_id": review_id,
                "old_label": old_label,
                "new_label": correction["final_classification"],
                "evidence_url": correction["evidence_url"],
                "rationale": correction["adjudication_rationale"],
            }
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    args.log.parent.mkdir(parents=True, exist_ok=True)
    args.log.write_text(
        json.dumps(
            {
                "created_at_utc": datetime.now(timezone.utc).isoformat(),
                "source_file": str(args.input),
                "output_file": str(args.output),
                "corrections": applied,
                "binary_effect": (
                    "No change: H025 remains non-problematic in the binary outcome; "
                    "the evidence-equivalent matrix remains [[46, 6], [0, 5]]."
                ),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Corrected records: {len(applied)}")
    print(f"Output: {args.output}")
    print(f"Log: {args.log}")


if __name__ == "__main__":
    main()
