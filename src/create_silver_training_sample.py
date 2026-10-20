"""Generate a stratified, weighted Silver Training Sample of 450 cases for LLM-as-a-judge distillation."""

from __future__ import annotations

import csv
import json
from pathlib import Path
import re
from typing import Any
from urllib.parse import quote

import duckdb
import numpy as np
import pandas as pd
from langdetect import DetectorFactory, detect_langs

import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.extract_reference_ml_features import extract_features_from_context
RAW = PROJECT_ROOT / "data" / "raw"
INTERIM = PROJECT_ROOT / "data" / "interim"
SHARDS_DIR = INTERIM / "silver_shards"

REFS_PATH = RAW / "openspec_code_refs.parquet"
ARTIFACTS_PATH = RAW / "openspec_artifact_files.parquet"

SAMPLE_PARQUET = INTERIM / "silver_sample_450.parquet"
SAMPLE_CSV = INTERIM / "silver_sample_450.csv"
SAMPLE_KEY_CSV = INTERIM / "silver_sample_450_key.csv"
MANIFEST_JSON = INTERIM / "silver_sample_450_manifest.json"
LLM_INPUT_JSONL = INTERIM / "llm_judge_inputs_silver_450.jsonl"
FEATURES_PARQUET = INTERIM / "silver_ml_features_450.parquet"

SEED = 20261021
N_CANDIDATES_PER_GROUP = 4_000
MAX_CONTEXT_CHARS = 8_000

STRATA_CONFIG = {
    "completed + missing": {"target_n": 175, "task_done": 1, "exists_at_anchor": 0, "pop_n": 34227},
    "open + missing": {"target_n": 100, "task_done": 0, "exists_at_anchor": 0, "pop_n": 17752},
    "completed + exists": {"target_n": 175, "task_done": 1, "exists_at_anchor": 1, "pop_n": 297822},
}

TOTAL_N = sum(v["target_n"] for v in STRATA_CONFIG.values())  # 450
TOTAL_POP_3STRATA = sum(v["pop_n"] for v in STRATA_CONFIG.values())  # 349801

# Calculate sampling weights normalized so sum(weights) == TOTAL_N
for name, cfg in STRATA_CONFIG.items():
    p_pop = cfg["pop_n"] / TOTAL_POP_3STRATA
    p_sample = cfg["target_n"] / TOTAL_N
    cfg["sampling_weight"] = (p_pop / p_sample)

FOREIGN_SCRIPT = re.compile(
    r"[\u0400-\u052f\u0590-\u08ff\u0900-\u0e7f\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]"
)


def github_blob_url(repo: str, commit: str, path: str) -> str:
    encoded_path = quote(path.strip("/"), safe="/")
    return f"https://github.com/{repo}/blob/{commit}/{encoded_path}"


def build_task_context(content: str, code_path: str, max_chars: int = MAX_CONTEXT_CHARS) -> tuple[str, bool]:
    positions: list[int] = []
    start = 0
    while code_path and len(positions) < 8:
        pos = content.find(code_path, start)
        if pos < 0:
            break
        positions.append(pos)
        start = pos + max(1, len(code_path))

    if not positions:
        return content[:max_chars], True

    radius = max(700, min(1500, max_chars // (2 * len(positions))))
    windows: list[tuple[int, int]] = []
    for pos in positions:
        left_hint = max(0, pos - radius)
        right_hint = min(len(content), pos + len(code_path) + radius)
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
    for idx, (left, right) in enumerate(windows, start=1):
        prefix = f"[Context around occurrence {idx}]\n"
        remaining = max_chars - used - len(prefix)
        if remaining <= 0:
            break
        chunk = content[left:right][:remaining]
        chunks.append(prefix + chunk)
        used += len(prefix) + len(chunk) + 2
    return "\n\n".join(chunks)[:max_chars], True


def english_detection(text: str) -> tuple[str, float, bool]:
    DetectorFactory.seed = 0
    foreign = bool(FOREIGN_SCRIPT.search(text))
    try:
        top = detect_langs(text)[0]
        return top.lang, float(top.prob), foreign
    except Exception:
        return "und", 0.0, foreign


def load_all_excluded_ids() -> set[int]:
    excluded: set[int] = set()
    for path in sorted(INTERIM.glob("*.csv")):
        try:
            with path.open(newline="", encoding="utf-8-sig") as handle:
                header = next(csv.reader(handle), [])
                if "id" not in header:
                    continue
            df = pd.read_csv(path, usecols=["id"])
            ids = set(pd.to_numeric(df["id"], errors="coerce").dropna().astype(int).tolist())
            excluded.update(ids)
        except Exception:
            pass
    return excluded


def main() -> None:
    print("=" * 60)
    print("GENERATING SILVER TRAINING SAMPLE (N = 450)")
    print("=" * 60)

    # 1. Load excluded IDs
    excluded_ids = load_all_excluded_ids()
    print(f"Loaded {len(excluded_ids)} previously evaluated unique IDs to exclude (zero contamination).")

    excluded_frame = pd.DataFrame({"id": sorted(excluded_ids)}, dtype="int64")
    con = duckdb.connect()
    con.register("excluded_ids", excluded_frame)

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
                END AS strata_group
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
                    PARTITION BY strata_group
                    ORDER BY hash(id, ?)
                ) AS candidate_rank
            FROM eligible
        )
        SELECT 
            ranked.*, 
            a.content,
            a.n_tasks,
            a.n_tasks_done,
            a.n_code_refs,
            a.n_bytes
        FROM ranked
        JOIN read_parquet(?) AS a
          ON ranked.repo_name = a.repo_name
         AND ranked.artifact_path = a.file_path
        WHERE candidate_rank <= ?
        ORDER BY strata_group, candidate_rank
    """

    print("Querying candidate pool from raw parquet...")
    candidates = con.execute(
        query,
        [str(REFS_PATH), SEED, str(ARTIFACTS_PATH), N_CANDIDATES_PER_GROUP],
    ).fetchdf()
    print(f"Retrieved {len(candidates)} candidate rows.")

    print("Extracting task context...")
    contexts = [
        build_task_context(content, code_path)
        for content, code_path in zip(candidates["content"], candidates["code_path"], strict=True)
    ]
    candidates["task_context"] = [context for context, _ in contexts]

    print("Filtering English language (>= 0.90 confidence)...")
    lang_data = [english_detection(text) for text in candidates["task_context"]]
    candidates[["detected_language", "language_probability", "has_foreign_script"]] = pd.DataFrame(
        lang_data, index=candidates.index
    )

    filtered = candidates.loc[
        (candidates["detected_language"] == "en")
        & (candidates["language_probability"] >= 0.90)
        & ~candidates["has_foreign_script"]
    ].copy()
    print(f"Filtered to {len(filtered)} high-confidence English candidates.")

    # 2. Select exactly target_n per stratum with 100% distinct repositories across the ENTIRE sample
    selected_parts: list[pd.DataFrame] = []
    used_repositories: set[str] = set()

    for strata_name, cfg in STRATA_CONFIG.items():
        group_rows = filtered.loc[filtered["strata_group"] == strata_name]
        chosen_indices: list[int] = []
        for idx, row in group_rows.iterrows():
            repo = str(row["repo_name"])
            if repo in used_repositories:
                continue
            chosen_indices.append(idx)
            used_repositories.add(repo)
            if len(chosen_indices) == cfg["target_n"]:
                break
        if len(chosen_indices) != cfg["target_n"]:
            raise ValueError(f"Could only find {len(chosen_indices)} unique-repo cases for {strata_name}")
        part = filtered.loc[chosen_indices].copy()
        part["sampling_weight"] = cfg["sampling_weight"]
        selected_parts.append(part)

    selected = pd.concat(selected_parts, ignore_index=True)
    assert len(selected) == TOTAL_N, f"Expected {TOTAL_N}, got {len(selected)}"
    assert len(used_repositories) == TOTAL_N, f"Expected {TOTAL_N} unique repos, got {len(used_repositories)}"

    # Shuffle deterministically
    selected = selected.sample(frac=1, random_state=SEED).reset_index(drop=True)
    selected.insert(0, "review_id", [f"S{num:03d}" for num in range(1, len(selected) + 1)])

    # Compute GitHub URLs
    selected["task_url"] = selected.apply(
        lambda r: github_blob_url(str(r["repo_name"]), str(r["anchor_sha"]), str(r["artifact_path"])),
        axis=1,
    )
    selected["literal_path_url"] = selected.apply(
        lambda r: github_blob_url(str(r["repo_name"]), str(r["anchor_sha"]), str(r["code_path"])),
        axis=1,
    )
    selected["anchor_path"] = selected["resolved_path"].fillna(selected["code_path"])
    selected["anchor_path_url"] = selected.apply(
        lambda r: github_blob_url(str(r["repo_name"]), str(r["anchor_sha"]), str(r["anchor_path"])),
        axis=1,
    )

    # 3. Save Private Key (with ground truth strata and weights)
    key_cols = [
        "review_id",
        "id",
        "repo_name",
        "anchor_sha",
        "artifact_path",
        "code_path",
        "resolved_path",
        "strata_group",
        "task_done",
        "exists_at_anchor",
        "sampling_weight",
        "task_url",
    ]
    selected[key_cols].to_csv(SAMPLE_KEY_CSV, index=False)
    print(f"Saved private key: {SAMPLE_KEY_CSV}")

    # 4. Save Public Sample CSV & Parquet
    selected.to_parquet(SAMPLE_PARQUET, compression="zstd", index=False)
    selected.drop(columns=["content"]).to_csv(SAMPLE_CSV, index=False)
    print(f"Saved sample parquet ({SAMPLE_PARQUET}) and CSV ({SAMPLE_CSV})")

    # 5. Extract ML features for these 450 instances
    print("Extracting ML feature matrix for the 450 silver instances...")
    features_list: list[dict[str, Any]] = []
    for _, row in selected.iterrows():
        f = extract_features_from_context(str(row["code_path"]), str(row["content"]))
        f["review_id"] = row["review_id"]
        f["id"] = int(row["id"])
        f["repo_name"] = str(row["repo_name"])
        f["artifact_path"] = str(row["artifact_path"])
        f["code_path"] = str(row["code_path"])
        f["strata_group"] = str(row["strata_group"])
        f["task_done"] = int(row["task_done"])
        f["exists_at_anchor"] = int(row["exists_at_anchor"])
        f["sampling_weight"] = float(row["sampling_weight"])
        f["n_tasks"] = int(row["n_tasks"]) if pd.notna(row["n_tasks"]) else 0
        f["n_tasks_done"] = int(row["n_tasks_done"]) if pd.notna(row["n_tasks_done"]) else 0
        f["n_code_refs"] = int(row["n_code_refs"]) if pd.notna(row["n_code_refs"]) else 0
        f["artifact_bytes"] = int(row["n_bytes"]) if pd.notna(row["n_bytes"]) else 0
        n_t = max(1, f["n_tasks"])
        f["artifact_completion_ratio"] = f["n_tasks_done"] / n_t
        f["artifact_code_ref_density"] = f["n_code_refs"] / n_t
        features_list.append(f)

    feat_df = pd.DataFrame(features_list)
    feat_df.to_parquet(FEATURES_PARQUET, compression="zstd", index=False)
    print(f"Saved ML features parquet: {FEATURES_PARQUET}")

    # 6. Save LLM Judge Input JSONL and Shards
    llm_records: list[dict[str, Any]] = []
    for _, row in selected.iterrows():
        rec = {
            "review_id": row["review_id"],
            "repo_name": row["repo_name"],
            "anchor_sha": row["anchor_sha"],
            "artifact_path": row["artifact_path"],
            "code_path": row["code_path"],
            "resolved_path": row["resolved_path"] if pd.notna(row["resolved_path"]) else "",
            "exists_at_anchor": int(row["exists_at_anchor"]),
            "task_context": row["task_context"],
        }
        llm_records.append(rec)

    with LLM_INPUT_JSONL.open("w", encoding="utf-8") as f:
        for r in llm_records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"Saved LLM input JSONL: {LLM_INPUT_JSONL}")

    # Partition into shards of 25 records (18 shards total)
    SHARDS_DIR.mkdir(parents=True, exist_ok=True)
    records_per_shard = 25
    n_shards = (TOTAL_N + records_per_shard - 1) // records_per_shard
    for s_idx in range(n_shards):
        start = s_idx * records_per_shard
        end = min(TOTAL_N, start + records_per_shard)
        shard_data = llm_records[start:end]
        shard_path = SHARDS_DIR / f"shard_{s_idx + 1:02d}.json"
        with shard_path.open("w", encoding="utf-8") as f:
            json.dump(shard_data, f, indent=2, ensure_ascii=False)
    print(f"Wrote {n_shards} shard files (25 records each) to {SHARDS_DIR}")

    # 7. Write Manifest
    manifest = {
        "dataset_name": "silver_training_sample_450",
        "created_at": pd.Timestamp.now().isoformat(),
        "seed": SEED,
        "sample_size": TOTAL_N,
        "unique_repositories": len(used_repositories),
        "n_shards": n_shards,
        "records_per_shard": records_per_shard,
        "strata_breakdown": {
            k: {
                "count": v["target_n"],
                "sampling_weight": round(v["sampling_weight"], 4),
                "population_total": v["pop_n"],
            }
            for k, v in STRATA_CONFIG.items()
        },
    }
    with MANIFEST_JSON.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    print(f"Saved manifest: {MANIFEST_JSON}")
    print("=" * 60)
    print("SILVER SAMPLE GENERATION COMPLETE!")
    print("=" * 60)


if __name__ == "__main__":
    main()
