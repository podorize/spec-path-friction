"""Build de-identified, context-rich JSONL inputs for an LLM judge.

The script makes no model calls. It freezes the exact records sent to a judge,
allowing a later API runner to record reproducible request and response data.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import duckdb


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW = PROJECT_ROOT / "data" / "raw"
INTERIM = PROJECT_ROOT / "data" / "interim"
REFS_PATH = RAW / "openspec_code_refs.parquet"
ARTIFACTS_PATH = RAW / "openspec_artifact_files.parquet"
VALIDATION_PATHS = {
    "pilot": INTERIM / "validation_workbook_pilot.csv",
    "confirmatory": INTERIM / "validation_workbook_confirmatory.csv",
    "confirmatory_en": INTERIM / "validation_workbook_confirmatory_en.csv",
}


def task_excerpt(content: str, code_path: str, max_chars: int) -> tuple[str, bool]:
    """Extract a bounded task-local context around the literal reference."""
    position = content.find(code_path)
    if position < 0:
        return content[:max_chars], False

    start_hint = max(0, position - max_chars // 2)
    start = content.rfind("\n", 0, start_hint)
    start = 0 if start < 0 else start + 1
    end = min(len(content), start + max_chars)
    next_newline = content.find("\n", end)
    if next_newline >= 0 and next_newline - start <= max_chars + 200:
        end = next_newline
    return content[start:end], True


def load_records(selection: str, limit: int | None) -> list[dict[str, object]]:
    con = duckdb.connect()
    where_clause = "r.exists_at_anchor = 0"
    parameters: list[object] = [str(REFS_PATH), str(ARTIFACTS_PATH)]
    if selection in VALIDATION_PATHS:
        where_clause = "r.id IN (SELECT id FROM read_csv_auto(?))"
        parameters.append(str(VALIDATION_PATHS[selection]))

    limit_clause = "" if limit is None else "LIMIT ?"
    if limit is not None:
        parameters.append(limit)

    query = f"""
        SELECT
            r.id,
            r.code_path,
            r.resolved_path,
            r.exists_at_anchor,
            a.content
        FROM read_parquet(?) AS r
        JOIN read_parquet(?) AS a
          ON r.repo_name = a.repo_name
         AND r.artifact_path = a.file_path
        WHERE {where_clause}
        ORDER BY r.id
        {limit_clause}
    """
    return con.execute(query, parameters).fetchdf().to_dict(orient="records")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--selection",
        choices=["unresolved", "pilot", "confirmatory", "confirmatory_en"],
        default="unresolved",
    )
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--context-chars", type=int, default=1_600)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    if args.context_chars < 200:
        raise ValueError("--context-chars must be at least 200")
    if args.limit is not None and args.limit < 1:
        raise ValueError("--limit must be positive")

    output = args.output or INTERIM / f"llm_judge_inputs_{args.selection}.jsonl"
    records = load_records(args.selection, args.limit)
    if not records:
        raise ValueError("No records matched the requested selection")

    match_count = 0
    with output.open("w", encoding="utf-8") as handle:
        for row in records:
            excerpt, found = task_excerpt(
                str(row["content"]), str(row["code_path"]), args.context_chars
            )
            match_count += found
            payload = {
                "reference_id": int(row["id"]),
                "literal_code_path": row["code_path"],
                "resolved_code_path": row["resolved_path"],
                "automatic_resolution": (
                    "path_resolved_at_anchor"
                    if row["exists_at_anchor"] == 1
                    else "literal_path_unresolved_at_anchor"
                ),
                "task_context": excerpt,
                "literal_path_found_in_context": found,
            }
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")

    manifest = output.with_suffix(".manifest.json")
    manifest.write_text(
        json.dumps(
            {
                "dataset": "SpecMine July 2026 release",
                "selection": args.selection,
                "records": len(records),
                "context_chars": args.context_chars,
                "literal_path_found_in_context": match_count,
                "input_file": output.name,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {len(records):,} judge inputs to {output}")
    print(f"Literal path found in context: {match_count:,}/{len(records):,}")
    print(f"Manifest: {manifest}")


if __name__ == "__main__":
    main()
