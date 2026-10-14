"""Draw the untouched phase-1 screening sample for longitudinal validation."""

from __future__ import annotations

import csv
import hashlib
import json
import multiprocessing as mp
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import duckdb
import pandas as pd
from langdetect import DetectorFactory, detect_langs


ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
INTERIM = ROOT / "data" / "interim"
RESULTS = ROOT / "results" / "validation" / "holdout_v1"
REFS = RAW / "openspec_code_refs.parquet"
ARTIFACTS = RAW / "openspec_artifact_files.parquet"
OUTPUT = INTERIM / "holdout_screening_v1_240.csv"
KEY = INTERIM / "holdout_screening_v1_240_key.csv"
MANIFEST = INTERIM / "holdout_screening_v1_240_manifest.json"
FREEZE = RESULTS / "FROZEN_CONFIG.json"

SEED = 20261012
N_PER_STRATUM = 120
MAX_CONTEXT_CHARS = 8_000
LANGUAGE_WORKERS = min(8, max(2, os.cpu_count() or 2))
STRATA = {0: "open + missing", 1: "completed + missing"}
FOREIGN_SCRIPT = re.compile(
    r"[\u0400-\u052f\u0590-\u08ff\u0900-\u0e7f\u3040-\u30ff"
    r"\u3400-\u9fff\uac00-\ud7af]"
)
FROZEN_FILES = [
    ROOT / "src" / "create_longitudinal_holdout_screening.py",
    ROOT / "src" / "create_holdout_human_sample.py",
    ROOT / "src" / "build_longitudinal_evidence.py",
    ROOT / "src" / "classify_reference_rules.py",
    ROOT / "src" / "prepare_hybrid_judge_batch.py",
    ROOT / "validation" / "LLM_JUDGE_PROMPT_LONGITUDINAL_V2.md",
    ROOT / "validation" / "llm_judge_output_schema_v2.json",
    ROOT / "validation" / "PROTOCOL_V2_LONGITUDINAL.md",
    ROOT / "validation" / "HOLDOUT_V1_DESIGN.md",
]

DetectorFactory.seed = 0


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def github_blob_url(repo: str, sha: str, path: str) -> str:
    return f"https://github.com/{repo}/blob/{sha}/{quote(path, safe='/')}"


def english_detection(text: str) -> tuple[str, float, bool]:
    DetectorFactory.seed = 0
    foreign = bool(FOREIGN_SCRIPT.search(text))
    try:
        top = detect_langs(text)[0]
        return top.lang, float(top.prob), foreign
    except Exception:
        return "und", 0.0, foreign


def csv_has_column(path: Path, column: str) -> bool:
    try:
        with path.open(newline="", encoding="utf-8-sig") as handle:
            return column in (next(csv.reader(handle), []))
    except (OSError, UnicodeDecodeError):
        return False


def load_excluded_ids() -> tuple[set[int], dict[str, int]]:
    excluded: set[int] = set()
    sources: dict[str, int] = {}
    for path in sorted(INTERIM.glob("*.csv")):
        if path in {OUTPUT, KEY} or not csv_has_column(path, "id"):
            continue
        frame = pd.read_csv(path, usecols=["id"])
        values = pd.to_numeric(frame["id"], errors="coerce").dropna().astype(int)
        ids = set(values.tolist())
        if ids:
            sources[path.name] = len(ids)
            excluded.update(ids)
    return excluded, sources


def main() -> None:
    excluded, exclusion_sources = load_excluded_ids()
    excluded_frame = pd.DataFrame({"id": sorted(excluded)}, dtype="int64")
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
                hash(r.id, ?) AS sample_hash
            FROM read_parquet(?) AS r
            LEFT JOIN excluded_ids AS x USING (id)
            WHERE x.id IS NULL
              AND r.exists_at_anchor = 0
              AND r.task_done IN (0, 1)
              AND r.repo_name IS NOT NULL
              AND r.anchor_sha IS NOT NULL
              AND r.artifact_path IS NOT NULL
              AND r.code_path IS NOT NULL
              AND trim(r.code_path) <> ''
        )
        SELECT
            e.*,
            CASE
                WHEN length(a.content) <= ? THEN a.content
                WHEN strpos(a.content, e.code_path) > 0 THEN
                    substr(
                        a.content,
                        greatest(1, strpos(a.content, e.code_path) - CAST(? / 2 AS INTEGER)),
                        ?
                    )
                ELSE substr(a.content, 1, ?)
            END AS task_context,
            length(a.content) > ? AS context_truncated
        FROM eligible AS e
        JOIN read_parquet(?) AS a
          ON e.repo_name = a.repo_name
         AND e.artifact_path = a.file_path
        ORDER BY e.sample_hash
    """
    candidates = connection.execute(
        query,
        [SEED, str(REFS), MAX_CONTEXT_CHARS, MAX_CONTEXT_CHARS, MAX_CONTEXT_CHARS, MAX_CONTEXT_CHARS, MAX_CONTEXT_CHARS, str(ARTIFACTS)],
    ).fetchdf()
    if candidates["id"].duplicated().any():
        raise ValueError("The screening frame contains duplicate reference IDs")

    texts = [str(text or "") for text in candidates["task_context"]]
    print(f"Language screening: {len(texts)} references across {LANGUAGE_WORKERS} workers", flush=True)
    with mp.Pool(processes=LANGUAGE_WORKERS) as pool:
        language = list(pool.imap(english_detection, texts, chunksize=100))
    candidates[["detected_language", "language_probability", "has_foreign_script"]] = pd.DataFrame(language, index=candidates.index)
    eligible = candidates.loc[
        (candidates["detected_language"] == "en")
        & (candidates["language_probability"] >= 0.90)
        & ~candidates["has_foreign_script"]
    ].copy()
    eligible["sampling_stratum"] = eligible["task_done"].map(STRATA)

    parts: list[pd.DataFrame] = []
    frame_counts: dict[str, int] = {}
    for task_done, stratum in STRATA.items():
        stratum_frame = eligible.loc[eligible["task_done"] == task_done].sort_values("sample_hash")
        frame_size = len(stratum_frame)
        if frame_size < N_PER_STRATUM:
            raise ValueError(f"Only {frame_size} eligible cases for {stratum}")
        frame_counts[stratum] = frame_size
        sample = stratum_frame.head(N_PER_STRATUM).copy()
        sample["phase1_frame_size"] = frame_size
        sample["phase1_sample_size"] = N_PER_STRATUM
        sample["phase1_inclusion_probability"] = N_PER_STRATUM / frame_size
        sample["phase1_sampling_weight"] = frame_size / N_PER_STRATUM
        sample["phase1_rank_within_stratum"] = range(1, N_PER_STRATUM + 1)
        parts.append(sample)

    selected = pd.concat(parts, ignore_index=True)
    selected["display_hash"] = selected["id"].map(lambda value: int(hashlib.sha256(f"{SEED + 1}:{int(value)}".encode()).hexdigest()[:16], 16))
    selected = selected.sort_values("display_hash").reset_index(drop=True)
    selected.insert(0, "review_id", [f"S{number:03d}" for number in range(1, len(selected) + 1)])
    selected["task_url"] = selected.apply(lambda row: github_blob_url(str(row["repo_name"]), str(row["anchor_sha"]), str(row["artifact_path"])), axis=1)
    selected["literal_path_url"] = selected.apply(lambda row: github_blob_url(str(row["repo_name"]), str(row["anchor_sha"]), str(row["code_path"])), axis=1)
    selected["candidate_path_url"] = selected.apply(
        lambda row: github_blob_url(str(row["repo_name"]), str(row["anchor_sha"]), str(row["resolved_path"])) if pd.notna(row["resolved_path"]) and str(row["resolved_path"]).strip() else "",
        axis=1,
    )

    public_columns = [
        "review_id", "repo_name", "anchor_sha", "artifact_path", "code_path",
        "resolved_path", "task_url", "literal_path_url", "candidate_path_url", "task_context",
    ]
    selected[public_columns].to_csv(OUTPUT, index=False)
    key_columns = [
        "review_id", "id", "sampling_stratum", "task_done", "exists_at_anchor",
        "phase1_frame_size", "phase1_sample_size", "phase1_inclusion_probability",
        "phase1_sampling_weight", "phase1_rank_within_stratum", "sample_hash",
        "detected_language", "language_probability", "has_foreign_script", "context_truncated",
    ]
    selected[key_columns].to_csv(KEY, index=False)

    overlap = len(set(selected["id"].astype(int)) & excluded)
    if overlap:
        raise ValueError(f"Held-out screening sample overlaps {overlap} prior references")
    if len(selected) != 2 * N_PER_STRATUM:
        raise ValueError("Unexpected screening sample size")
    RESULTS.mkdir(parents=True, exist_ok=True)
    manifest = {
        "purpose": "Phase-1 untouched screening sample for held-out longitudinal validation",
        "dataset": "SpecMine July 2026 release",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "seed": SEED,
        "n_references": len(selected),
        "n_per_task_status_stratum": N_PER_STRATUM,
        "frame_counts_after_exclusion_and_language_filter": frame_counts,
        "phase1_design": "Stratified simple random sampling without replacement, implemented by seeded hash ordering within task completion status.",
        "phase1_inclusion_probability": {stratum: N_PER_STRATUM / size for stratum, size in frame_counts.items()},
        "phase1_sampling_weight": {stratum: size / N_PER_STRATUM for stratum, size in frame_counts.items()},
        "eligibility": {
            "exists_at_anchor": 0,
            "task_done": [0, 1],
            "language": "en",
            "minimum_language_probability": 0.90,
            "foreign_scripts_excluded": True,
            "maximum_context_characters": MAX_CONTEXT_CHARS,
        },
        "excluded_id_sources": exclusion_sources,
        "n_unique_excluded_ids": len(excluded),
        "overlap_with_prior_references": overlap,
        "screening_file": OUTPUT.name,
        "screening_file_sha256": sha256(OUTPUT),
        "private_key": KEY.name,
        "private_key_sha256": sha256(KEY),
        "status": "screening_sample_drawn_no_human_labels",
        "next_stage": "Generate longitudinal evidence and frozen pipeline predictions before phase-2 human sampling.",
    }
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    freeze = {
        "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
        "sample_manifest": str(MANIFEST.relative_to(ROOT)),
        "sample_manifest_sha256": sha256(MANIFEST),
        "screening_file_sha256": sha256(OUTPUT),
        "private_key_sha256": sha256(KEY),
        "configuration_files": {str(path.relative_to(ROOT)): sha256(path) for path in FROZEN_FILES},
        "development_cases_excluded": True,
        "human_labels_observed": False,
        "warning": "Any change to a listed hash creates a new pipeline version and cannot be evaluated as holdout_v1.",
    }
    FREEZE.write_text(json.dumps(freeze, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Screening cases: {len(selected)}")
    print(f"English frame counts: {frame_counts}")
    print(f"Prior-reference overlap: {overlap}")
    print(f"Output: {OUTPUT}")
    print(f"Freeze manifest: {FREEZE}")


if __name__ == "__main__":
    main()
