"""Build label-free longitudinal evidence packets for code-reference review."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "data" / "interim" / "validation_human_fresh_90_en.csv"
DEFAULT_OUTPUT = ROOT / "data" / "interim" / "longitudinal_evidence_development_90.jsonl"
DEFAULT_MANIFEST = ROOT / "data" / "interim" / "longitudinal_evidence_development_90_manifest.json"
DEFAULT_CACHE = ROOT / "data" / "interim" / "github_evidence_cache"


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def raw_url(repo: str, sha: str, path: str) -> str:
    return f"https://raw.githubusercontent.com/{repo}/{sha}/{quote(path, safe='/')}"


def github_api(path: str, params: dict[str, object] | None = None) -> str:
    suffix = f"?{urlencode(params)}" if params else ""
    return f"https://api.github.com{path}{suffix}"


def excerpt_around(text: str, needle: str, radius: int = 900) -> str:
    if not text:
        return ""
    candidates = [needle, Path(needle).name]
    positions = [text.lower().find(item.lower()) for item in candidates if item]
    positions = [position for position in positions if position >= 0]
    if not positions:
        return text[: radius * 2]
    position = min(positions)
    start = max(0, position - radius)
    end = min(len(text), position + len(needle) + radius)
    return text[start:end]


def explicit_repository_mentions(text: str) -> list[str]:
    patterns = [
        r"github\.com/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)",
        r"\b(?:repo(?:sitory)?|project)\s+[`'\"]?([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)",
    ]
    mentions: set[str] = set()
    for pattern in patterns:
        mentions.update(match.rstrip(".,);]") for match in re.findall(pattern, text, flags=re.I))
    return sorted(mentions)


class CachedGitHubClient:
    def __init__(self, cache_dir: Path, delay_seconds: float = 0.1) -> None:
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.delay_seconds = delay_seconds
        self.token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        self.requests = 0
        self.cache_hits = 0

    def _cache_path(self, url: str) -> Path:
        return self.cache_dir / f"{hashlib.sha256(url.encode()).hexdigest()}.json"

    def fetch(self, url: str, *, accept: str = "application/vnd.github+json") -> dict[str, Any]:
        cache_path = self._cache_path(url)
        if cache_path.exists():
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            transient = cached.get("status") == "inaccessible" or cached.get("http_status") in {403, 429, 500, 502, 503, 504}
            if not transient:
                self.cache_hits += 1
                return cached
        headers = {"Accept": accept, "User-Agent": "msr2027-specmine-longitudinal-evidence"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
            headers["X-GitHub-Api-Version"] = "2022-11-28"
        request = Request(url, headers=headers)
        self.requests += 1
        try:
            with urlopen(request, timeout=45) as response:
                body = response.read()
                record = {
                    "status": "found",
                    "http_status": response.status,
                    "body": body.decode("utf-8", errors="replace"),
                    "body_sha256": sha256_bytes(body),
                    "rate_limit_remaining": response.headers.get("X-RateLimit-Remaining"),
                }
        except HTTPError as exc:
            body = exc.read()
            record = {
                "status": "not_found" if exc.code == 404 else "http_error",
                "http_status": exc.code,
                "body": body.decode("utf-8", errors="replace")[:4000],
                "body_sha256": sha256_bytes(body),
                "rate_limit_remaining": exc.headers.get("X-RateLimit-Remaining"),
            }
        except (TimeoutError, URLError, OSError) as exc:
            record = {
                "status": "inaccessible",
                "http_status": None,
                "body": "",
                "body_sha256": None,
                "error": type(exc).__name__,
            }
        cache_path.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
        time.sleep(self.delay_seconds)
        return record

    def json(self, url: str) -> tuple[dict[str, Any], Any | None]:
        record = self.fetch(url)
        if record["status"] != "found":
            return record, None
        try:
            return record, json.loads(record["body"])
        except json.JSONDecodeError:
            return {**record, "status": "invalid_json"}, None


def content_observation(client: CachedGitHubClient, url: str, *, needle: str = "") -> dict[str, Any]:
    response = dict(client.fetch(url, accept="text/plain"))
    body = response.pop("body", "")
    return {
        **response,
        "url": url,
        "content_excerpt": excerpt_around(body, needle) if response["status"] == "found" else "",
        "content_length": len(body) if response["status"] == "found" else None,
    }


def compare_relation(client: CachedGitHubClient, repo: str, anchor: str, candidate: str) -> str:
    if anchor == candidate:
        return "at_anchor"
    _, payload = client.json(github_api(f"/repos/{repo}/compare/{anchor}...{candidate}"))
    if not isinstance(payload, dict):
        return "unknown"
    return {
        "ahead": "after_anchor",
        "behind": "before_anchor",
        "identical": "at_anchor",
        "diverged": "diverged_from_anchor",
    }.get(str(payload.get("status")), "unknown")


def build_record(row: dict[str, str], client: CachedGitHubClient, *, max_history: int, max_compare: int) -> dict[str, Any]:
    repo = row["repo_name"]
    anchor = row["anchor_sha"]
    artifact_path = row["artifact_path"]
    literal_path = row["code_path"]
    candidate_path = row.get("resolved_path", "").strip()
    task = content_observation(client, raw_url(repo, anchor, artifact_path), needle=literal_path)
    literal = content_observation(client, raw_url(repo, anchor, literal_path), needle=literal_path)
    candidate = (
        {"path": candidate_path, **content_observation(client, raw_url(repo, anchor, candidate_path), needle=literal_path)}
        if candidate_path
        else {"path": None, "status": "not_applicable", "http_status": None, "url": None, "content_excerpt": ""}
    )

    tree_meta, tree_payload = client.json(github_api(f"/repos/{repo}/git/trees/{anchor}", {"recursive": 1}))
    basename = Path(literal_path).name
    matching_paths: list[str] = []
    tree_truncated = None
    if isinstance(tree_payload, dict):
        matching_paths = [item.get("path", "") for item in tree_payload.get("tree", []) if item.get("type") == "blob" and Path(item.get("path", "")).name == basename]
        tree_truncated = bool(tree_payload.get("truncated"))
    tree = {
        "status": "available" if tree_payload is not None else tree_meta["status"],
        "http_status": tree_meta["http_status"],
        "basename": basename,
        "matching_paths_at_anchor": matching_paths[:100],
        "match_count": len(matching_paths),
        "truncated": tree_truncated or len(matching_paths) > 100,
    }

    commit_meta, commit_payload = client.json(github_api(f"/repos/{repo}/commits/{anchor}"))
    commit = {"status": commit_meta["status"], "http_status": commit_meta["http_status"]}
    if isinstance(commit_payload, dict):
        commit_data = commit_payload.get("commit", {})
        commit.update({
            "sha": commit_payload.get("sha"),
            "message": commit_data.get("message", ""),
            "author_date": commit_data.get("author", {}).get("date"),
            "committer_date": commit_data.get("committer", {}).get("date"),
            "parents": [parent.get("sha") for parent in commit_payload.get("parents", [])],
        })

    history_meta, history_payload = client.json(github_api(f"/repos/{repo}/commits", {"path": literal_path, "per_page": max_history}))
    history: list[dict[str, Any]] = []
    if isinstance(history_payload, list):
        for index, item in enumerate(history_payload[:max_history]):
            sha = str(item.get("sha", ""))
            relation = compare_relation(client, repo, anchor, sha) if index < max_compare and sha else "not_compared"
            history.append({
                "sha": sha,
                "relation_to_anchor": relation,
                "message": item.get("commit", {}).get("message", ""),
                "author_date": item.get("commit", {}).get("author", {}).get("date"),
            })

    languages_meta, languages_payload = client.json(github_api(f"/repos/{repo}/languages"))
    languages = languages_payload if isinstance(languages_payload, dict) else {}
    task_context = row.get("task_context", "")
    task_excerpt = task.get("content_excerpt", "") or task_context
    missing_evidence: list[str] = []
    for name, observation in [("task_at_anchor", task), ("literal_path", literal), ("repository_tree", tree), ("anchor_commit", commit)]:
        if observation.get("status") in {"http_error", "inaccessible", "invalid_json"}:
            missing_evidence.append(name)
    if history_meta["status"] != "found":
        missing_evidence.append("path_history")

    return {
        "review_id": row["review_id"],
        "repo_name": repo,
        "anchor_sha": anchor,
        "artifact_path": artifact_path,
        "literal_code_path": literal_path,
        "resolved_candidate_path": candidate_path or None,
        "task_context": task_context,
        "anchor_task_observation": task,
        "literal_path_observation": literal,
        "resolved_candidate_observation": candidate,
        "repository_tree_observation": tree,
        "anchor_commit_observation": commit,
        "path_history_observation": {
            "status": "available" if isinstance(history_payload, list) else history_meta["status"],
            "http_status": history_meta["http_status"],
            "commits": history,
            "returned_count": len(history),
        },
        "repository_language_observation": {"status": "available" if languages else languages_meta["status"], "languages": languages},
        "explicit_repository_mentions": explicit_repository_mentions(f"{task_context}\n{task_excerpt}"),
        "evidence_gaps": sorted(set(missing_evidence)),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--ids", nargs="*")
    parser.add_argument("--max-history", type=int, default=10)
    parser.add_argument("--max-compare", type=int, default=5)
    args = parser.parse_args()
    rows = read_csv(args.input)
    if args.ids:
        requested = set(args.ids)
        rows = [row for row in rows if row["review_id"] in requested]
        missing = requested - {row["review_id"] for row in rows}
        if missing:
            raise ValueError(f"Unknown review IDs: {sorted(missing)}")
    client = CachedGitHubClient(args.cache_dir)
    records = [build_record(row, client, max_history=args.max_history, max_compare=args.max_compare) for row in rows]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records), encoding="utf-8")
    manifest = {
        "purpose": "Label-free longitudinal evidence packets for development of the hybrid reference classifier",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "development_data": True,
        "records": len(records),
        "review_ids": [record["review_id"] for record in records],
        "source_file": str(args.input),
        "source_sha256": sha256_bytes(args.input.read_bytes()),
        "output_file": str(args.output),
        "output_sha256": sha256_bytes(args.output.read_bytes()),
        "excluded_from_packet": ["validation_group", "task_done", "exists_at_anchor", "manual_classification", "human labels", "LLM labels", "adjudication fields"],
        "max_history": args.max_history,
        "max_compare": args.max_compare,
        "github_requests": client.requests,
        "cache_hits": client.cache_hits,
    }
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Evidence records: {len(records)}")
    print(f"GitHub requests: {client.requests}; cache hits: {client.cache_hits}")
    print(f"Output: {args.output}")


if __name__ == "__main__":
    main()
