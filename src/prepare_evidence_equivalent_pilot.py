"""Build a leakage-free evidence-equivalent packet for a 10-case pilot."""

from __future__ import annotations

import csv
import hashlib
import json
import argparse
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
INTERIM = ROOT / "data" / "interim"
SOURCE = INTERIM / "validation_human_fresh_90_en.csv"
KEY = INTERIM / "validation_human_fresh_90_en_key.csv"
OUTPUT = INTERIM / "evidence_equivalent_pilot_10.jsonl"
MANIFEST = INTERIM / "evidence_equivalent_pilot_10_manifest.json"

DEFAULT_IDS = [
    "H001", "H003", "H006",  # completed + exists
    "H002", "H004", "H009",  # completed + missing
    "H005", "H008", "H011", "H013",  # open + missing
]


def read_csv(path: Path) -> dict[str, dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return {row["review_id"]: row for row in csv.DictReader(handle)}


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def raw_url(repo: str, sha: str, path: str) -> str:
    return f"https://raw.githubusercontent.com/{repo}/{sha}/{path}"


def fetch(url: str, limit: int = 16000) -> dict[str, object]:
    request = Request(url, headers={"User-Agent": "msr2027-specmine-evidence-pilot"})
    try:
        with urlopen(request, timeout=30) as response:
            raw = response.read(limit + 1)
            truncated = len(raw) > limit
            content = raw[:limit].decode("utf-8", errors="replace")
            return {
                "status": "found",
                "http_status": response.status,
                "content_excerpt": content,
                "content_truncated": truncated,
                "content_sha256": sha256_text(content),
            }
    except HTTPError as exc:
        return {
            "status": "not_found" if exc.code == 404 else "http_error",
            "http_status": exc.code,
            "content_excerpt": "",
            "content_truncated": False,
            "content_sha256": None,
        }


def fetch_tree(repo: str, sha: str, basename: str) -> dict[str, object]:
    url = f"https://api.github.com/repos/{repo}/git/trees/{sha}?recursive=1"
    request = Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "msr2027-specmine-evidence-pilot",
        },
    )
    try:
        with urlopen(request, timeout=45) as response:
            payload = json.loads(response.read().decode("utf-8"))
            paths = [
                item["path"]
                for item in payload.get("tree", [])
                if item.get("type") == "blob"
                and Path(item.get("path", "")).name == basename
            ]
            return {
                "status": "available",
                "http_status": response.status,
                "basename": basename,
                "matching_paths_at_anchor": paths[:100],
                "match_count": len(paths),
                "truncated": len(paths) > 100,
            }
    except HTTPError as exc:
        return {"status": "http_error", "http_status": exc.code, "basename": basename}
    except (TimeoutError, URLError, OSError, json.JSONDecodeError) as exc:
        return {"status": "inaccessible", "http_status": None, "basename": basename, "error": type(exc).__name__}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ids", nargs="*", default=None)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--manifest", type=Path, default=MANIFEST)
    args = parser.parse_args()
    source = read_csv(SOURCE)
    key = read_csv(KEY)
    selected_ids = args.ids or sorted(source)
    if not selected_ids:
        raise ValueError("No review IDs selected")
    unknown = set(selected_ids) - set(source)
    if unknown:
        raise ValueError(f"Unknown review IDs: {sorted(unknown)}")
    records: list[dict[str, object]] = []
    for review_id in selected_ids:
        row = source[review_id]
        key_row = key[review_id]
        repo = row["repo_name"]
        sha = row["anchor_sha"]
        literal_url = raw_url(repo, sha, row["code_path"])
        candidate_path = row["resolved_path"].strip()
        candidate_url = raw_url(repo, sha, candidate_path) if candidate_path else None
        literal = fetch(literal_url)
        time.sleep(0.15)
        candidate = fetch(candidate_url) if candidate_url else {
            "status": "not_applicable",
            "http_status": None,
            "content_excerpt": "",
            "content_truncated": False,
            "content_sha256": None,
        }
        tree = fetch_tree(repo, sha, Path(row["code_path"]).name)
        records.append(
            {
                "review_id": review_id,
                "repo_name": repo,
                "anchor_sha": sha,
                "artifact_path": row["artifact_path"],
                "literal_code_path": row["code_path"],
                "task_url": row["task_url"],
                "literal_path_url": row["literal_path_url"],
                "anchor_path_url": row["anchor_path_url"],
                "task_context": row["task_context"],
                "literal_path_observation": {"url": literal_url, **literal},
                "resolved_candidate_observation": {
                    "path": candidate_path or None,
                    "url": candidate_url,
                    **candidate,
                },
                "repository_tree_observation": tree,
            }
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    manifest = {
        "purpose": "Evidence-equivalent pilot for human/LLM comparison",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "records": len(records),
        "review_ids": selected_ids,
        "source_file": SOURCE.name,
        "source_sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        "key_file_used_only_for_selection": KEY.name,
        "excluded_fields": [
            "reviewer_id", "manual_classification", "evidence_note", "access_issue",
            "validation_group", "task_done", "exists_at_anchor", "candidate_rank",
            "sample_rank_within_group", "detected_language", "language_probability",
        ],
        "evidence_policy": "Pinned raw GitHub content at anchor SHA, with 404/inaccessible status and candidate path content when available.",
        "output_file": str(args.output),
        "output_sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
    }
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Evidence records: {len(records)}")
    print(f"Output: {args.output}")
    print(f"Manifest: {args.manifest}")


if __name__ == "__main__":
    main()
