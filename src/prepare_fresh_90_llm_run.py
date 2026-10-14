"""Freeze leakage-free LLM inputs for the H001-H090 human-first sample.

The human labels are used only to verify that the frozen first-pass file is
complete and still matches the pre-review sample. The JSONL supplied to the
LLM is constructed independently from the original blind sample and its
private key; human labels, notes, access judgments, and sampling strata never
enter the model input.
"""

from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
INTERIM = PROJECT_ROOT / "data" / "interim"
VALIDATION = PROJECT_ROOT / "validation"

HUMAN_PATH = INTERIM / "validation_human_fresh_90_R1_initial.csv"
BLIND_SOURCE = INTERIM / "validation_human_fresh_90_en.csv"
PRIVATE_KEY = INTERIM / "validation_human_fresh_90_en_key.csv"
PROMPT = VALIDATION / "LLM_JUDGE_PROMPT.md"
SCHEMA = VALIDATION / "llm_judge_output_schema.json"

LLM_INPUT_OUTPUT = INTERIM / "llm_judge_inputs_human_90.jsonl"
MANIFEST_OUTPUT = INTERIM / "human_90_llm_input_manifest.json"

SOURCE_COLUMNS = [
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
]

ALLOWED_LABELS = {
    "confirmed_exists",
    "confirmed_missing_problematic",
    "expected_absence_create",
    "expected_absence_move_or_delete",
    "non_file_reference",
    "ambiguous_reference",
    "inaccessible_or_invalid",
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def assert_unique(rows: list[dict[str, str]], name: str) -> dict[str, dict[str, str]]:
    indexed = {row["review_id"]: row for row in rows}
    if len(indexed) != len(rows):
        raise ValueError(f"{name} contains duplicate review IDs")
    return indexed


def main() -> None:
    human_rows = read_csv(HUMAN_PATH)
    source_rows = read_csv(BLIND_SOURCE)
    key_rows = read_csv(PRIVATE_KEY)

    human = assert_unique(human_rows, "Human labels")
    source = assert_unique(source_rows, "Blind source")
    key = assert_unique(key_rows, "Private key")

    expected_ids = {f"H{index:03d}" for index in range(1, 91)}
    if set(human) != expected_ids or set(source) != expected_ids or set(key) != expected_ids:
        raise ValueError("Human, source, and key must contain exactly H001-H090")

    for review_id in sorted(expected_ids):
        human_row = human[review_id]
        source_row = source[review_id]
        for column in SOURCE_COLUMNS:
            if human_row[column].strip() != source_row[column].strip():
                raise ValueError(f"Source field changed for {review_id}: {column}")
        if not human_row["reviewer_id"].strip():
            raise ValueError(f"Missing reviewer for {review_id}")
        if human_row["manual_classification"].strip() not in ALLOWED_LABELS:
            raise ValueError(f"Invalid human classification for {review_id}")
        if not human_row["evidence_note"].strip():
            raise ValueError(f"Missing human evidence note for {review_id}")

        key_row = key[review_id]
        for column in ["repo_name", "artifact_path", "code_path", "resolved_path"]:
            if source_row[column].strip() != key_row[column].strip():
                raise ValueError(f"Source/key mismatch for {review_id}: {column}")

    records: list[dict[str, object]] = []
    for review_id in sorted(expected_ids):
        row = source[review_id]
        key_row = key[review_id]
        exists = int(key_row["exists_at_anchor"])
        if exists not in {0, 1}:
            raise ValueError(f"Unexpected resolution state for {review_id}: {exists}")
        records.append(
            {
                "review_id": review_id,
                "reference_id": int(key_row["id"]),
                "literal_code_path": row["code_path"],
                "resolved_code_path": row["resolved_path"] or None,
                "automatic_resolution": (
                    "path_resolved_at_anchor"
                    if exists == 1
                    else "literal_path_unresolved_at_anchor"
                ),
                "task_context": row["task_context"],
                "literal_path_found_in_context": row["code_path"] in row["task_context"],
            }
        )

    with LLM_INPUT_OUTPUT.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    label_counts = Counter(
        row["manual_classification"].strip() for row in human_rows
    )
    manifest = {
        "purpose": "Leakage-free LLM input for independent H001-H090 comparison",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "dataset": "SpecMine July 2026 release",
        "records": len(records),
        "review_ids": [record["review_id"] for record in records],
        "human_labels_verified_but_not_used_to_build_inputs": True,
        "human_file": HUMAN_PATH.name,
        "human_sha256": sha256(HUMAN_PATH),
        "human_label_counts_private": dict(sorted(label_counts.items())),
        "blind_source_file": BLIND_SOURCE.name,
        "blind_source_sha256": sha256(BLIND_SOURCE),
        "private_key_file": PRIVATE_KEY.name,
        "private_key_sha256": sha256(PRIVATE_KEY),
        "llm_input_file": LLM_INPUT_OUTPUT.name,
        "llm_input_sha256": sha256(LLM_INPUT_OUTPUT),
        "llm_input_excluded_fields": [
            "reviewer_id",
            "manual_classification",
            "evidence_note",
            "access_issue",
            "validation_group",
            "task_done",
            "repo_name",
            "anchor_sha",
            "task_url",
            "literal_path_url",
            "anchor_path_url",
        ],
        "prompt_file": str(PROMPT.relative_to(PROJECT_ROOT)),
        "prompt_sha256": sha256(PROMPT),
        "schema_file": str(SCHEMA.relative_to(PROJECT_ROOT)),
        "schema_sha256": sha256(SCHEMA),
    }
    MANIFEST_OUTPUT.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"Verified human first-pass labels: {len(human_rows)}")
    print(f"Leakage-free LLM inputs: {len(records)}")
    print(f"LLM input: {LLM_INPUT_OUTPUT}")
    print(f"Manifest: {MANIFEST_OUTPUT}")


if __name__ == "__main__":
    main()
