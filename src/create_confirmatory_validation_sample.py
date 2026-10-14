"""Create a fresh, blinded human-validation sample after prompt freezing."""

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
PILOT_PATH = INTERIM / "validation_workbook_pilot.csv"
PREVIOUS_CONFIRMATORY_PATH = INTERIM / "validation_workbook_confirmatory.csv"
CANDIDATES_PATH = INTERIM / "validation_candidates_confirmatory_en.csv"
MASTER_PATH = INTERIM / "validation_workbook_confirmatory_en.csv"
BLINDED_PATH = INTERIM / "validation_human_blinded_confirmatory_en.csv"
KEY_PATH = INTERIM / "validation_blinding_key_confirmatory_en.csv"
MANIFEST_PATH = INTERIM / "validation_confirmatory_en_manifest.json"
SEED = 20260929
N_PER_GROUP = 30
N_CANDIDATES_PER_GROUP = 500
FOREIGN_SCRIPT = re.compile(r"[\u0400-\u052f\u0590-\u08ff\u0900-\u0e7f\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]")

DetectorFactory.seed = 0


def github_blob_url(repo_name: str, sha: str, path: str) -> str:
    return f"https://github.com/{repo_name}/blob/{sha}/{quote(path, safe='/')}"


def task_excerpt(content: str, code_path: str, max_chars: int = 1_600) -> str:
    position = content.find(code_path)
    if position < 0:
        return content[:max_chars]
    start_hint = max(0, position - max_chars // 2)
    start = content.rfind("\n", 0, start_hint)
    start = 0 if start < 0 else start + 1
    return content[start : start + max_chars]


def english_detection(text: str) -> tuple[str, float, bool]:
    """Return top language, confidence, and whether the context has foreign script."""
    has_foreign_script = bool(FOREIGN_SCRIPT.search(text))
    try:
        top = detect_langs(text)[0]
        return top.lang, top.prob, has_foreign_script
    except Exception:
        return "und", 0.0, has_foreign_script


def main() -> None:
    con = duckdb.connect()
    query = """
        WITH eligible AS (
            SELECT
                r.id, r.repo_name, r.artifact_path, r.code_path,
                r.resolved_path, r.task_done, r.anchor_sha, r.exists_at_anchor,
                CASE
                    WHEN r.task_done = 1 AND r.exists_at_anchor = 0
                        THEN 'concluída + ausente'
                    WHEN r.task_done = 0 AND r.exists_at_anchor = 0
                        THEN 'aberta + ausente'
                    WHEN r.task_done = 1 AND r.exists_at_anchor = 1
                        THEN 'concluída + existe'
                END AS validation_group
            FROM read_parquet(?) AS r
            WHERE r.id NOT IN (SELECT id FROM read_csv_auto(?))
              AND r.id NOT IN (SELECT id FROM read_csv_auto(?))
              AND (
                  (r.task_done = 1 AND r.exists_at_anchor = 0)
                  OR (r.task_done = 0 AND r.exists_at_anchor = 0)
                  OR (r.task_done = 1 AND r.exists_at_anchor = 1)
              )
        ), ranked AS (
            SELECT *,
                ROW_NUMBER() OVER (
                    PARTITION BY validation_group
                    ORDER BY hash(id, ?)
                ) AS sample_rank
            FROM eligible
        )
        SELECT ranked.*, a.content
        FROM ranked
        JOIN read_parquet(?) AS a
          ON ranked.repo_name = a.repo_name
         AND ranked.artifact_path = a.file_path
        WHERE sample_rank <= ?
        ORDER BY validation_group, sample_rank
    """
    sampled = con.execute(
        query,
        [
            str(REFS_PATH),
            str(PILOT_PATH),
            str(PREVIOUS_CONFIRMATORY_PATH),
            SEED,
            str(ARTIFACTS_PATH),
            N_CANDIDATES_PER_GROUP,
        ],
    ).fetchdf()
    expected_candidates = 3 * N_CANDIDATES_PER_GROUP
    if len(sampled) != expected_candidates or sampled["id"].duplicated().any():
        raise ValueError(
            f"Expected {expected_candidates} distinct candidates, found {len(sampled)}"
        )

    sampled["reference_excerpt"] = [
        task_excerpt(content, code_path)
        for content, code_path in zip(sampled["content"], sampled["code_path"], strict=True)
    ]
    language_data = [english_detection(text) for text in sampled["reference_excerpt"]]
    sampled[["detected_language", "language_probability", "has_foreign_script"]] = pd.DataFrame(
        language_data, index=sampled.index
    )
    english = sampled.loc[
        (sampled["detected_language"] == "en")
        & (sampled["language_probability"] >= 0.90)
        & ~sampled["has_foreign_script"]
    ].copy()
    english = english.groupby("validation_group", group_keys=False).head(N_PER_GROUP)
    expected = 3 * N_PER_GROUP
    if len(english) != expected:
        counts = english.groupby("validation_group").size().to_dict()
        raise ValueError(f"Insufficient English candidates by group: {counts}")
    english["sample_rank"] = english.groupby("validation_group").cumcount() + 1
    sampled = english

    candidates = sampled.drop(columns=["content"])
    candidates.to_csv(CANDIDATES_PATH, index=False)

    master = candidates.copy()
    master["artifact_url"] = master.apply(
        lambda row: github_blob_url(row["repo_name"], row["anchor_sha"], row["artifact_path"]),
        axis=1,
    )
    master["literal_code_url"] = master.apply(
        lambda row: github_blob_url(row["repo_name"], row["anchor_sha"], row["code_path"]),
        axis=1,
    )
    master["anchor_code_path"] = master["resolved_path"].fillna(master["code_path"])
    master["anchor_code_url"] = master.apply(
        lambda row: github_blob_url(row["repo_name"], row["anchor_sha"], row["anchor_code_path"]),
        axis=1,
    )
    master["audit_status"] = "pending"
    master["manual_classification"] = ""
    master["evidence_note"] = ""
    master.to_csv(MASTER_PATH, index=False)

    shuffled = master.sample(frac=1, random_state=SEED).reset_index(drop=True)
    shuffled.insert(0, "review_id", [f"C{number:03d}" for number in range(1, len(shuffled) + 1)])
    human_columns = [
        "review_id", "repo_name", "anchor_sha", "artifact_path", "code_path",
        "resolved_path", "artifact_url", "literal_code_url", "anchor_code_path",
        "anchor_code_url", "reference_excerpt",
    ]
    blinded = shuffled[human_columns].copy()
    blinded["reviewer_id"] = ""
    blinded["manual_classification"] = ""
    blinded["evidence_note"] = ""
    blinded["access_issue"] = ""
    blinded.to_csv(BLINDED_PATH, index=False)

    key = shuffled[["review_id", "id", "validation_group", "task_done", "exists_at_anchor"]]
    key.to_csv(KEY_PATH, index=False)
    MANIFEST_PATH.write_text(
        json.dumps(
            {
                "dataset": "SpecMine July 2026 release",
                "seed": SEED,
                "n_per_group": N_PER_GROUP,
                "candidate_pool_per_group": N_CANDIDATES_PER_GROUP,
                "groups": ["concluída + ausente", "aberta + ausente", "concluída + existe"],
                "excluded_ids_sources": [PILOT_PATH.name, PREVIOUS_CONFIRMATORY_PATH.name],
                "language_filter": {
                    "detector": "langdetect 1.0.9",
                    "required_language": "en",
                    "minimum_probability": 0.90,
                    "exclude_foreign_script": True,
                },
                "n_references": len(master),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Created {len(master)} fresh English validation references")
    print(f"Human workbook: {BLINDED_PATH}")
    print(f"Private blinding key: {KEY_PATH}")


if __name__ == "__main__":
    main()
