"""Create a new balanced, blinded English sample for independent human review.

The sample deliberately excludes every reference used in the pilot and both
confirmatory rounds. It contains one reference per repository and hides the
automatic resolution state and sampling stratum from the reviewer.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import quote

import duckdb
import pandas as pd
from langdetect import DetectorFactory, detect_langs


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW = PROJECT_ROOT / "data" / "raw"
INTERIM = PROJECT_ROOT / "data" / "interim"
REFS_PATH = RAW / "openspec_code_refs.parquet"
ARTIFACTS_PATH = RAW / "openspec_artifact_files.parquet"

EXCLUSION_PATHS = [
    INTERIM / "validation_workbook_pilot.csv",
    INTERIM / "validation_workbook_confirmatory.csv",
    INTERIM / "validation_workbook_confirmatory_en.csv",
    INTERIM / "validation_blind_eval_30_en_key.csv",
]

REVIEW_PATH = INTERIM / "validation_human_fresh_90_en.csv"
KEY_PATH = INTERIM / "validation_human_fresh_90_en_key.csv"
MANIFEST_PATH = INTERIM / "validation_human_fresh_90_en_manifest.json"

SEED = 20261010
N_PER_GROUP = 30
N_CANDIDATES_PER_GROUP = 2_500
MAX_CONTEXT_CHARS = 8_000
GROUP_ORDER = [
    "completed + missing",
    "open + missing",
    "completed + exists",
]
FOREIGN_SCRIPT = re.compile(
    r"[\u0400-\u052f\u0590-\u08ff\u0900-\u0e7f\u3040-\u30ff"
    r"\u3400-\u9fff\uac00-\ud7af]"
)

DetectorFactory.seed = 0


def github_blob_url(repo_name: str, sha: str, path: str) -> str:
    return f"https://github.com/{repo_name}/blob/{sha}/{quote(path, safe='/')}"


def build_task_context(
    content: str, code_path: str, max_chars: int = MAX_CONTEXT_CHARS
) -> tuple[str, bool]:
    """Keep full short tasks; otherwise include bounded windows around every match."""
    content = str(content or "")
    code_path = str(code_path or "")
    if len(content) <= max_chars:
        return content, False

    positions: list[int] = []
    start = 0
    while code_path and len(positions) < 8:
        position = content.find(code_path, start)
        if position < 0:
            break
        positions.append(position)
        start = position + max(1, len(code_path))

    if not positions:
        return content[:max_chars], True

    radius = max(700, min(1_500, max_chars // (2 * len(positions))))
    windows: list[tuple[int, int]] = []
    for position in positions:
        left_hint = max(0, position - radius)
        right_hint = min(len(content), position + len(code_path) + radius)
        left = content.rfind("\n", 0, left_hint)
        right = content.find("\n", right_hint)
        left = 0 if left < 0 else left + 1
        right = len(content) if right < 0 else right
        if windows and left <= windows[-1][1]:
            windows[-1] = (windows[-1][0], max(windows[-1][1], right))
        else:
            windows.append((left, right))

    chunks: list[str] = []
    used = 0
    for index, (left, right) in enumerate(windows, start=1):
        prefix = f"[Context around occurrence {index}]\n"
        remaining = max_chars - used - len(prefix)
        if remaining <= 0:
            break
        chunk = content[left:right][:remaining]
        chunks.append(prefix + chunk)
        used += len(prefix) + len(chunk) + 2
    return "\n\n".join(chunks)[:max_chars], True


def english_detection(text: str) -> tuple[str, float, bool]:
    has_foreign_script = bool(FOREIGN_SCRIPT.search(text))
    try:
        top = detect_langs(text)[0]
        return top.lang, float(top.prob), has_foreign_script
    except Exception:
        return "und", 0.0, has_foreign_script


def load_excluded_ids() -> tuple[set[int], dict[str, int]]:
    excluded: set[int] = set()
    counts: dict[str, int] = {}
    for path in EXCLUSION_PATHS:
        frame = pd.read_csv(path, usecols=["id"])
        ids = {int(value) for value in frame["id"].dropna().tolist()}
        counts[path.name] = len(ids)
        excluded.update(ids)
    return excluded, counts


def main() -> None:
    excluded_ids, exclusion_counts = load_excluded_ids()
    excluded_frame = pd.DataFrame({"id": sorted(excluded_ids)})

    connection = duckdb.connect()
    connection.register("excluded_ids", excluded_frame)
    query = """
        WITH eligible AS (
            SELECT
                r.id,
                r.repo_name,
                r.artifact_path,
                r.code_path,
                r.resolved_path,
                r.task_done,
                r.anchor_sha,
                r.exists_at_anchor,
                CASE
                    WHEN r.task_done = 1 AND r.exists_at_anchor = 0
                        THEN 'completed + missing'
                    WHEN r.task_done = 0 AND r.exists_at_anchor = 0
                        THEN 'open + missing'
                    WHEN r.task_done = 1 AND r.exists_at_anchor = 1
                        THEN 'completed + exists'
                END AS validation_group
            FROM read_parquet(?) AS r
            LEFT JOIN excluded_ids AS x USING (id)
            WHERE x.id IS NULL
              AND r.repo_name IS NOT NULL
              AND r.anchor_sha IS NOT NULL
              AND r.artifact_path IS NOT NULL
              AND r.code_path IS NOT NULL
              AND trim(r.code_path) <> ''
              AND (
                  (r.task_done = 1 AND r.exists_at_anchor = 0)
                  OR (r.task_done = 0 AND r.exists_at_anchor = 0)
                  OR (
                      r.task_done = 1
                      AND r.exists_at_anchor = 1
                      AND r.resolved_path IS NOT NULL
                      AND trim(r.resolved_path) <> ''
                  )
              )
        ), ranked AS (
            SELECT
                *,
                ROW_NUMBER() OVER (
                    PARTITION BY validation_group
                    ORDER BY hash(id, ?)
                ) AS candidate_rank
            FROM eligible
        )
        SELECT ranked.*, a.content
        FROM ranked
        JOIN read_parquet(?) AS a
          ON ranked.repo_name = a.repo_name
         AND ranked.artifact_path = a.file_path
        WHERE candidate_rank <= ?
        ORDER BY validation_group, candidate_rank
    """
    candidates = connection.execute(
        query,
        [str(REFS_PATH), SEED, str(ARTIFACTS_PATH), N_CANDIDATES_PER_GROUP],
    ).fetchdf()

    contexts = [
        build_task_context(content, code_path)
        for content, code_path in zip(
            candidates["content"], candidates["code_path"], strict=True
        )
    ]
    candidates["task_context"] = [context for context, _ in contexts]
    candidates["context_truncated"] = [truncated for _, truncated in contexts]

    language_data = [english_detection(text) for text in candidates["task_context"]]
    candidates[
        ["detected_language", "language_probability", "has_foreign_script"]
    ] = pd.DataFrame(language_data, index=candidates.index)
    candidates = candidates.loc[
        (candidates["detected_language"] == "en")
        & (candidates["language_probability"] >= 0.90)
        & ~candidates["has_foreign_script"]
    ].copy()

    selected_parts: list[pd.DataFrame] = []
    used_repositories: set[str] = set()
    for group in GROUP_ORDER:
        group_rows = candidates.loc[candidates["validation_group"] == group]
        chosen_indices: list[int] = []
        for index, row in group_rows.iterrows():
            repository = str(row["repo_name"])
            if repository in used_repositories:
                continue
            chosen_indices.append(index)
            used_repositories.add(repository)
            if len(chosen_indices) == N_PER_GROUP:
                break
        if len(chosen_indices) != N_PER_GROUP:
            raise ValueError(
                f"Only {len(chosen_indices)} unique-repository English cases for {group}"
            )
        selected_parts.append(candidates.loc[chosen_indices])

    selected = pd.concat(selected_parts, ignore_index=True)
    selected["sample_rank_within_group"] = (
        selected.groupby("validation_group", sort=False).cumcount() + 1
    )
    selected = selected.sample(frac=1, random_state=SEED).reset_index(drop=True)
    selected.insert(
        0, "review_id", [f"H{number:03d}" for number in range(1, len(selected) + 1)]
    )

    selected["task_url"] = selected.apply(
        lambda row: github_blob_url(
            str(row["repo_name"]), str(row["anchor_sha"]), str(row["artifact_path"])
        ),
        axis=1,
    )
    selected["literal_path_url"] = selected.apply(
        lambda row: github_blob_url(
            str(row["repo_name"]), str(row["anchor_sha"]), str(row["code_path"])
        ),
        axis=1,
    )
    selected["anchor_path"] = selected["resolved_path"].fillna(selected["code_path"])
    selected["anchor_path_url"] = selected.apply(
        lambda row: github_blob_url(
            str(row["repo_name"]), str(row["anchor_sha"]), str(row["anchor_path"])
        ),
        axis=1,
    )

    review_columns = [
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
    review = selected[review_columns].copy()
    review["reviewer_id"] = ""
    review["manual_classification"] = ""
    review["evidence_note"] = ""
    review["access_issue"] = ""
    review.to_csv(REVIEW_PATH, index=False)

    key_columns = [
        "review_id",
        "id",
        "validation_group",
        "task_done",
        "exists_at_anchor",
        "repo_name",
        "artifact_path",
        "code_path",
        "resolved_path",
        "candidate_rank",
        "sample_rank_within_group",
        "detected_language",
        "language_probability",
        "has_foreign_script",
        "context_truncated",
    ]
    selected[key_columns].to_csv(KEY_PATH, index=False)

    group_counts = (
        selected["validation_group"].value_counts().reindex(GROUP_ORDER).to_dict()
    )
    overlap = len(set(selected["id"].astype(int)) & excluded_ids)
    if overlap:
        raise ValueError(f"Fresh sample overlaps {overlap} previously used references")
    if selected["repo_name"].nunique() != len(selected):
        raise ValueError("Fresh sample must contain one reference per repository")

    MANIFEST_PATH.write_text(
        json.dumps(
            {
                "purpose": "Independent blinded human validation",
                "dataset": "SpecMine July 2026 release",
                "seed": SEED,
                "n_references": len(review),
                "n_unique_repositories": int(selected["repo_name"].nunique()),
                "n_per_group": N_PER_GROUP,
                "group_counts_private": group_counts,
                "candidate_pool_per_group": N_CANDIDATES_PER_GROUP,
                "excluded_id_sources": exclusion_counts,
                "n_unique_excluded_ids": len(excluded_ids),
                "overlap_with_excluded_ids": overlap,
                "eligibility": {
                    "task_status_and_resolution_strata": GROUP_ORDER,
                    "existing_paths_require_nonempty_resolved_path": True,
                    "one_reference_per_repository": True,
                    "language": "English",
                    "minimum_language_probability": 0.90,
                    "foreign_scripts_excluded": True,
                    "maximum_context_characters": MAX_CONTEXT_CHARS,
                },
                "review_file": REVIEW_PATH.name,
                "private_key": KEY_PATH.name,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    print(f"Created {len(review)} new blinded English cases")
    print(f"Unique repositories: {selected['repo_name'].nunique()}")
    print(f"Private group counts: {group_counts}")
    print(f"Excluded unique prior references: {len(excluded_ids)}")
    print(f"Overlap with prior references: {overlap}")
    print(f"Review CSV: {REVIEW_PATH}")
    print(f"Private key: {KEY_PATH}")


if __name__ == "__main__":
    main()
