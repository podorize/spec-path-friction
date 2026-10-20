"""Extract ML predictive features for OpenSpec code references and map targets.

Processes raw code references joined with artifact markdown files to generate
a high-dimensional tabular feature matrix for supervised predictive modeling.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys
import time
from typing import Any

import duckdb
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
RAW_REFS = ROOT / "data" / "raw" / "openspec_code_refs.parquet"
RAW_ARTIFACTS = ROOT / "data" / "raw" / "openspec_artifact_files.parquet"
DEFAULT_OUTPUT = ROOT / "data" / "interim" / "reference_ml_features_missing.parquet"

CREATE_VERBS = re.compile(
    r"\b(create|creates|created|creating|add|adds|added|adding|new|implement|implements|implemented|scaffold|scaffolding|generate|generated|write|writing|introduce|introduced|build|building|author)\b",
    re.I,
)
UPDATE_VERBS = re.compile(
    r"\b(update|updates|updated|modify|modifies|modified|change|changes|changed|refactor|refactored|fix|fixes|fixed|patch|enhance|edit|adjust|align|rework|convert|rewrite|rewrote|export|exports)\b",
    re.I,
)
DELETE_VERBS = re.compile(
    r"\b(delete|deleted|deleting|remove|removed|removing|drop|dropped|move|moved|moving|rename|renamed|renaming|deprecat\w*|retire|retired|replace|replaced)\b",
    re.I,
)
TEST_VERBS = re.compile(
    r"\b(test|tests|tested|testing|verify|verified|verifying|exercise|exercises|exercised|run|runs|running|check|checks|checked|validate|validated|assert|asserts|cover|covers|covered)\b",
    re.I,
)

TEST_PATH_PATTERN = re.compile(r"(\.test\.|\.spec\.|_test\.|tests?/|test/|fixtures?/|__tests__/)", re.I)
CONFIG_EXTS = {".json", ".yaml", ".yml", ".toml", ".xml", ".ini", ".env", ".config.js", ".config.ts"}
DOC_EXTS = {".md", ".rst", ".txt", ".adoc"}
SOURCE_EXTS = {".ts", ".tsx", ".js", ".jsx", ".py", ".rs", ".go", ".java", ".c", ".cpp", ".cs", ".rb", ".php", ".swift", ".kt"}
MONOREPO_DIRS = ("packages/", "apps/", "services/", "crates/", "modules/", "projects/")


def extract_features_from_context(code_path: str, context_text: str) -> dict[str, Any]:
    norm_path = code_path.replace("\\", "/")
    basename = Path(norm_path).name
    
    lines = context_text.split("\n")
    matching_lines: list[str] = []
    section_headers: list[str] = []
    current_header = ""
    line_idx = -1

    for idx, raw_l in enumerate(lines):
        line = raw_l.strip()
        if line.startswith("#"):
            current_header = line
        if norm_path in line or (basename and basename in line) or (code_path and code_path in line):
            matching_lines.append(line)
            if current_header and current_header not in section_headers:
                section_headers.append(current_header)
            if line_idx < 0:
                line_idx = idx

    task_line = " ".join(matching_lines) if matching_lines else context_text[:300]
    headers_text = " ".join(section_headers)

    # 1. Lexical verbs in line
    has_create = bool(CREATE_VERBS.search(task_line))
    has_update = bool(UPDATE_VERBS.search(task_line))
    has_delete = bool(DELETE_VERBS.search(task_line))
    has_test_verb = bool(TEST_VERBS.search(task_line))

    # Header verbs
    header_has_create = bool(CREATE_VERBS.search(headers_text))
    header_has_delete = bool(DELETE_VERBS.search(headers_text))
    header_has_test = bool(TEST_VERBS.search(headers_text))

    # Checkbox states on task line
    is_task_checkbox_done = bool(re.search(r"^-\s*\[x\]", task_line, re.I))
    is_task_checkbox_open = bool(re.search(r"^-\s*\[\s*\]", task_line, re.I))

    # Document position
    total_lines = max(1, len(lines))
    pos_ratio = (line_idx / total_lines) if line_idx >= 0 else 0.5

    # 2. Path morphology
    suffix = Path(norm_path).suffix.lower()
    is_test_file = bool(TEST_PATH_PATTERN.search(norm_path))
    is_config_file = suffix in CONFIG_EXTS or ".config." in norm_path
    is_doc_file = suffix in DOC_EXTS or "docs/" in norm_path
    is_source_file = suffix in SOURCE_EXTS and not is_test_file

    has_glob = bool(re.search(r"[*?]", code_path))
    has_traversal = "../" in code_path or "./" in code_path
    has_backslash = "\\" in code_path
    is_monorepo = any(norm_path.startswith(prefix) for prefix in MONOREPO_DIRS)

    depth = norm_path.count("/")
    path_len = len(code_path)
    base_len = len(basename)
    line_word_count = len(task_line.split())

    return {
        "verb_create": int(has_create),
        "verb_update": int(has_update),
        "verb_delete": int(has_delete),
        "verb_test": int(has_test_verb),
        "verb_balance": int(has_create) - int(has_update),
        "header_has_create": int(header_has_create),
        "header_has_delete": int(header_has_delete),
        "header_has_test": int(header_has_test),
        "task_checkbox_done": int(is_task_checkbox_done),
        "task_checkbox_open": int(is_task_checkbox_open),
        "task_pos_ratio": float(pos_ratio),
        "task_line_word_count": int(line_word_count),
        "path_depth": int(depth),
        "path_length": int(path_len),
        "path_basename_length": int(base_len),
        "is_test_file": int(is_test_file),
        "is_config_file": int(is_config_file),
        "is_doc_file": int(is_doc_file),
        "is_source_file": int(is_source_file),
        "has_glob_pattern": int(has_glob),
        "has_traversal": int(has_traversal),
        "has_backslash": int(has_backslash),
        "is_monorepo": int(is_monorepo),
    }


def map_targets(classification: str | None) -> dict[str, Any]:
    if not classification or pd.isna(classification):
        return {
            "target_problematic_binary": np.nan,
            "target_lifecycle_multiclass": None,
        }
    
    c = str(classification).strip()
    is_prob = int(c == "confirmed_missing_problematic")

    mapping = {
        "expected_absence_create": "create",
        "expected_absence_move_or_delete": "move_delete",
        "confirmed_missing_problematic": "problematic",
        "external_repository_reference": "external_repo",
        "non_file_reference": "non_file",
        "confirmed_exists": "exists",
        "inaccessible_or_invalid": "inaccessible",
        "ambiguous_reference": "ambiguous",
    }

    return {
        "target_problematic_binary": is_prob,
        "target_lifecycle_multiclass": mapping.get(c, "other"),
    }


def build_features_matrix(
    refs_path: Path = RAW_REFS,
    artifacts_path: Path = RAW_ARTIFACTS,
    output_path: Path = DEFAULT_OUTPUT,
    missing_only: bool = True,
    limit: int | None = None,
) -> pd.DataFrame:
    print(f"Connecting to DuckDB and loading references from {refs_path}...")
    con = duckdb.connect()
    
    filter_clause = "WHERE r.exists_at_anchor = 0" if missing_only else ""
    limit_clause = f"LIMIT {limit}" if limit else ""
    
    query = f"""
    SELECT 
        r.id,
        r.repo_name,
        r.artifact_path,
        r.code_path,
        r.task_done,
        r.exists_at_anchor,
        r.anchor_sha,
        a.n_tasks,
        a.n_tasks_done,
        a.n_code_refs,
        a.n_bytes,
        a.content
    FROM '{refs_path}' r
    JOIN '{artifacts_path}' a
        ON r.repo_name = a.repo_name AND r.artifact_path = a.file_path
    {filter_clause}
    {limit_clause}
    """
    
    t0 = time.time()
    df_raw = con.execute(query).df()
    print(f"Loaded {len(df_raw):,} records in {time.time() - t0:.2f}s.")
    
    print("Extracting lexical, structural, and morphological features...")
    t1 = time.time()
    rows: list[dict[str, Any]] = []
    
    for idx, row in df_raw.iterrows():
        content = str(row.get("content", ""))
        code_path = str(row.get("code_path", ""))
        
        feats = extract_features_from_context(code_path, content)
        
        # Add metadata & structural features
        feats["id"] = int(row["id"])
        feats["repo_name"] = str(row["repo_name"])
        feats["artifact_path"] = str(row["artifact_path"])
        feats["code_path"] = code_path
        feats["task_done"] = int(row["task_done"])
        feats["exists_at_anchor"] = int(row["exists_at_anchor"]) if pd.notna(row["exists_at_anchor"]) else -1
        feats["n_tasks"] = int(row["n_tasks"]) if pd.notna(row["n_tasks"]) else 0
        feats["n_tasks_done"] = int(row["n_tasks_done"]) if pd.notna(row["n_tasks_done"]) else 0
        feats["n_code_refs"] = int(row["n_code_refs"]) if pd.notna(row["n_code_refs"]) else 0
        feats["artifact_bytes"] = int(row["n_bytes"]) if pd.notna(row["n_bytes"]) else 0
        
        # Computed ratios
        n_t = max(1, feats["n_tasks"])
        feats["artifact_completion_ratio"] = feats["n_tasks_done"] / n_t
        feats["artifact_code_ref_density"] = feats["n_code_refs"] / n_t

        rows.append(feats)
        
        if (idx + 1) % 10000 == 0 or (idx + 1) == len(df_raw):
            elapsed = time.time() - t1
            print(f"  Processed {idx + 1:,} / {len(df_raw):,} rows ({elapsed:.1f}s, {(idx + 1)/elapsed:.0f} rows/s)...")

    feat_df = pd.DataFrame(rows)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    feat_df.to_parquet(output_path, compression="zstd", index=False)
    print(f"Successfully saved {len(feat_df):,} feature rows to {output_path} in {time.time() - t0:.2f}s total.")
    return feat_df


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract ML features for OpenSpec code references.")
    parser.add_argument("--refs", type=Path, default=RAW_REFS)
    parser.add_argument("--artifacts", type=Path, default=RAW_ARTIFACTS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--all-refs", action="store_true", help="Extract for all references, not only missing.")
    parser.add_argument("--limit", type=int, default=None, help="Optional row limit for quick tests.")
    args = parser.parse_args()

    build_features_matrix(
        refs_path=args.refs,
        artifacts_path=args.artifacts,
        output_path=args.output,
        missing_only=not args.all_refs,
        limit=args.limit,
    )


if __name__ == "__main__":
    main()
