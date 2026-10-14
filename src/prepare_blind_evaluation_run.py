"""Freeze human labels and leakage-free LLM inputs for the B001-B030 sample.

The supplied human CSV is preserved unchanged. This script validates it against
the original blind sample, writes a canonical research copy, and independently
builds the LLM input from the pre-review sample plus its private key. Human
labels and evidence notes never enter the LLM JSONL file.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
INTERIM = PROJECT_ROOT / "data" / "interim"
VALIDATION = PROJECT_ROOT / "validation"
DEFAULT_ANSWERED = (
    Path("/Users/pedroodorize/Downloads")
    / "validation_blind_eval_30_en - Review.csv"
)
BLIND_SOURCE = INTERIM / "validation_blind_eval_30_en.csv"
PRIVATE_KEY = INTERIM / "validation_blind_eval_30_en_key.csv"
PROMPT = VALIDATION / "LLM_JUDGE_PROMPT.md"

HUMAN_OUTPUT = INTERIM / "validation_blind_eval_30_human_canonical.csv"
LLM_INPUT_OUTPUT = INTERIM / "llm_judge_inputs_blind_eval_30.jsonl"
MANIFEST_OUTPUT = INTERIM / "blind_eval_30_run_manifest.json"

ALLOWED_LABELS = {
    "confirmed_exists",
    "confirmed_missing_problematic",
    "expected_absence_create",
    "expected_absence_move_or_delete",
    "non_file_reference",
    "ambiguous_reference",
    "inaccessible_or_invalid",
}

ANSWER_TO_CANONICAL = {
    "Review ID": "review_id",
    "Repositório": "repo_name",
    "Commit": "anchor_sha",
    "Artefato da tarefa": "artifact_path",
    "Caminho literal": "code_path",
    "Caminho resolvido": "resolved_path",
    "URL da tarefa": "artifact_url",
    "URL do caminho literal": "literal_code_url",
    "Caminho no commit": "anchor_code_path",
    "URL do caminho no commit": "anchor_code_url",
    "Contexto da tarefa": "reference_excerpt",
    "Revisor": "reviewer_id",
    "Classificação": "manual_classification",
    "Nota de evidência": "evidence_note",
    "Problema de acesso": "access_issue",
}

SOURCE_COLUMNS = [
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

CANONICAL_COLUMNS = SOURCE_COLUMNS + [
    "reviewer_id",
    "manual_classification",
    "evidence_note",
    "access_issue",
]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonicalize_answered(
    answered_path: Path,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    answered = read_csv(answered_path)
    if len(answered) != 30:
        raise ValueError(f"Expected 30 answered rows; found {len(answered)}")

    missing = set(ANSWER_TO_CANONICAL).difference(answered[0])
    if missing:
        raise ValueError(f"Answered CSV is missing columns: {sorted(missing)}")

    source = read_csv(BLIND_SOURCE)
    source_by_id = {row["review_id"]: row for row in source}
    if len(source_by_id) != 30:
        raise ValueError("Blind source must contain 30 unique review IDs")

    canonical: list[dict[str, str]] = []
    normalizations: list[dict[str, str]] = []
    seen: set[str] = set()

    for raw in answered:
        row = {
            canonical_name: raw[answer_name].strip()
            for answer_name, canonical_name in ANSWER_TO_CANONICAL.items()
        }
        review_id = row["review_id"]
        if review_id in seen:
            raise ValueError(f"Duplicate review ID: {review_id}")
        seen.add(review_id)

        expected = source_by_id.get(review_id)
        if expected is None:
            raise ValueError(f"Unknown review ID: {review_id}")
        for column in SOURCE_COLUMNS:
            if row[column] != expected[column].strip():
                raise ValueError(
                    f"Source field changed for {review_id}: {column}"
                )

        if not row["reviewer_id"]:
            raise ValueError(f"Missing reviewer for {review_id}")
        if row["manual_classification"] not in ALLOWED_LABELS:
            raise ValueError(
                f"Invalid classification for {review_id}: "
                f"{row['manual_classification']!r}"
            )
        if not row["evidence_note"]:
            raise ValueError(f"Missing evidence note for {review_id}")

        if (
            review_id == "B011"
            and row["manual_classification"] == "inaccessible_or_invalid"
            and not row["access_issue"]
        ):
            row["access_issue"] = "Repository unavailable at review time."
            normalizations.append(
                {
                    "review_id": review_id,
                    "field": "access_issue",
                    "from": "",
                    "to": row["access_issue"],
                    "reason": (
                        "The evidence note already states that the repository "
                        "does not exist; the classification was not changed."
                    ),
                }
            )

        if (
            row["manual_classification"] == "inaccessible_or_invalid"
            and not row["access_issue"]
        ):
            raise ValueError(
                f"Access classification without access_issue: {review_id}"
            )
        canonical.append(row)

    if seen != set(source_by_id):
        missing_ids = sorted(set(source_by_id).difference(seen))
        raise ValueError(f"Answered CSV omits review IDs: {missing_ids}")
    return canonical, normalizations


def write_canonical_human(rows: list[dict[str, str]]) -> None:
    with HUMAN_OUTPUT.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CANONICAL_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def write_llm_inputs() -> list[str]:
    source = read_csv(BLIND_SOURCE)
    key = read_csv(PRIVATE_KEY)
    key_by_id = {row["review_id"]: row for row in key}
    review_ids: list[str] = []

    with LLM_INPUT_OUTPUT.open("w", encoding="utf-8") as handle:
        for row in source:
            review_id = row["review_id"]
            key_row = key_by_id.get(review_id)
            if key_row is None:
                raise ValueError(f"Private key omits {review_id}")
            exists = int(key_row["exists_at_anchor"])
            record = {
                "review_id": review_id,
                "reference_id": int(key_row["id"]),
                "literal_code_path": row["code_path"],
                "resolved_code_path": row["resolved_path"] or None,
                "automatic_resolution": (
                    "path_resolved_at_anchor"
                    if exists == 1
                    else "literal_path_unresolved_at_anchor"
                ),
                "task_context": row["reference_excerpt"],
                "literal_path_found_in_context": (
                    row["code_path"] in row["reference_excerpt"]
                ),
            }
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            review_ids.append(review_id)
    return review_ids


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--answered", type=Path, default=DEFAULT_ANSWERED)
    args = parser.parse_args()

    canonical, normalizations = canonicalize_answered(args.answered)
    write_canonical_human(canonical)
    review_ids = write_llm_inputs()

    label_counts: dict[str, int] = {}
    for row in canonical:
        label = row["manual_classification"]
        label_counts[label] = label_counts.get(label, 0) + 1

    manifest = {
        "purpose": "Independent human-versus-LLM evaluation on B001-B030",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "dataset": "SpecMine July 2026 release",
        "records": len(canonical),
        "review_ids": review_ids,
        "human_source_file": args.answered.name,
        "human_source_sha256": sha256(args.answered),
        "human_canonical_file": HUMAN_OUTPUT.name,
        "human_canonical_sha256": sha256(HUMAN_OUTPUT),
        "human_label_counts": dict(sorted(label_counts.items())),
        "normalizations": normalizations,
        "llm_input_file": LLM_INPUT_OUTPUT.name,
        "llm_input_sha256": sha256(LLM_INPUT_OUTPUT),
        "llm_input_excluded_fields": [
            "reviewer_id",
            "manual_classification",
            "evidence_note",
            "access_issue",
            "validation_group",
            "task_done",
        ],
        "prompt_file": str(PROMPT.relative_to(PROJECT_ROOT)),
        "prompt_sha256": sha256(PROMPT),
    }
    MANIFEST_OUTPUT.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"Human records frozen: {len(canonical)}")
    print(f"LLM inputs frozen: {len(review_ids)}")
    print(f"Normalizations: {len(normalizations)}")
    print(f"Human output: {HUMAN_OUTPUT}")
    print(f"LLM input: {LLM_INPUT_OUTPUT}")
    print(f"Manifest: {MANIFEST_OUTPUT}")


if __name__ == "__main__":
    main()
