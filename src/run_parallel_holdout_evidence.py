"""Run the frozen evidence generator in parallel shards and merge by review ID."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "data" / "interim" / "holdout_screening_v1_240.csv"
DEFAULT_OUTPUT = ROOT / "data" / "interim" / "holdout_longitudinal_evidence_v1_240.jsonl"
DEFAULT_MANIFEST = ROOT / "data" / "interim" / "holdout_longitudinal_evidence_v1_240_manifest.json"
DEFAULT_WORK = ROOT / "results" / "validation" / "holdout_v1" / "evidence_shards"
GENERATOR = ROOT / "src" / "build_longitudinal_evidence.py"
FREEZE = ROOT / "results" / "validation" / "holdout_v1" / "FROZEN_CONFIG.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--work-dir", type=Path, default=DEFAULT_WORK)
    parser.add_argument("--shards", type=int, default=4)
    args = parser.parse_args()
    if not (os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")):
        raise SystemExit("GH_TOKEN or GITHUB_TOKEN is required")
    with args.input.open(newline="", encoding="utf-8-sig") as handle:
        ids = [row["review_id"] for row in csv.DictReader(handle)]
    chunks = [ids[index:: args.shards] for index in range(args.shards)]
    args.work_dir.mkdir(parents=True, exist_ok=True)
    processes: list[tuple[int, subprocess.Popen[str], object, object]] = []
    for index, chunk in enumerate(chunks, start=1):
        output = args.work_dir / f"shard_{index}.jsonl"
        manifest = args.work_dir / f"shard_{index}_manifest.json"
        cache = args.work_dir / f"cache_{index}"
        stdout_handle = (args.work_dir / f"shard_{index}.stdout.log").open("w", encoding="utf-8")
        stderr_handle = (args.work_dir / f"shard_{index}.stderr.log").open("w", encoding="utf-8")
        command = [
            sys.executable, str(GENERATOR), "--input", str(args.input), "--ids", *chunk,
            "--output", str(output), "--manifest", str(manifest), "--cache-dir", str(cache),
            "--max-history", "10", "--max-compare", "5",
        ]
        process = subprocess.Popen(command, cwd=ROOT, text=True, stdout=stdout_handle, stderr=stderr_handle)
        processes.append((index, process, stdout_handle, stderr_handle))
    failures: list[int] = []
    for index, process, stdout_handle, stderr_handle in processes:
        return_code = process.wait()
        stdout_handle.close()
        stderr_handle.close()
        if return_code:
            failures.append(index)
    if failures:
        raise SystemExit(f"Evidence shards failed: {failures}")

    by_id: dict[str, dict[str, object]] = {}
    shard_manifests: list[dict[str, object]] = []
    for index in range(1, args.shards + 1):
        output = args.work_dir / f"shard_{index}.jsonl"
        for line in output.read_text(encoding="utf-8").splitlines():
            record = json.loads(line)
            if record["review_id"] in by_id:
                raise ValueError(f"Duplicate evidence record: {record['review_id']}")
            by_id[record["review_id"]] = record
        manifest_path = args.work_dir / f"shard_{index}_manifest.json"
        shard_manifests.append({"path": str(manifest_path.relative_to(ROOT)), "sha256": sha256(manifest_path)})
    if set(by_id) != set(ids):
        raise ValueError(f"Evidence ID mismatch: missing={sorted(set(ids) - set(by_id))}, extra={sorted(set(by_id) - set(ids))}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("".join(json.dumps(by_id[review_id], ensure_ascii=False) + "\n" for review_id in ids), encoding="utf-8")
    gap_counts: dict[str, int] = {}
    for record in by_id.values():
        for gap in record.get("evidence_gaps", []):
            gap_counts[str(gap)] = gap_counts.get(str(gap), 0) + 1
    manifest = {
        "purpose": "Held-out v1 longitudinal evidence collection",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "held_out_evaluation": True,
        "human_labels_observed": False,
        "records": len(by_id),
        "input": str(args.input.relative_to(ROOT)),
        "input_sha256": sha256(args.input),
        "frozen_config_sha256": sha256(FREEZE),
        "generator_sha256": sha256(GENERATOR),
        "shards": shard_manifests,
        "evidence_gap_counts": gap_counts,
        "output": str(args.output.relative_to(ROOT)),
        "output_sha256": sha256(args.output),
    }
    args.manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Merged evidence records: {len(by_id)}")
    print(f"Evidence gaps: {gap_counts}")
    print(f"Output: {args.output}")


if __name__ == "__main__":
    main()
