"""Run the longitudinal v2 judge with explicit, recorded batch configuration."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
AUTH = Path("/Users/pedroodorize/.codex/auth.json")
LABELS = {
    "confirmed_exists", "confirmed_missing_problematic", "expected_absence_create",
    "expected_absence_move_or_delete", "external_repository_reference",
    "non_file_reference", "ambiguous_reference", "inaccessible_or_invalid",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_records(path: Path) -> list[dict[str, Any]]:
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    ids = [str(row["review_id"]) for row in records]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate review IDs")
    return records


def render_prompt(record: dict[str, Any], prompt: Path) -> str:
    template = prompt.read_text(encoding="utf-8")
    if "{{record}}" not in template:
        raise ValueError("Prompt is missing {{record}}")
    return template.replace("{{record}}", json.dumps(record, ensure_ascii=False, indent=2))


def validate(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    expected = {"decision", "classification", "confidence", "evidence_quote", "rationale", "missing_evidence"}
    if set(payload) != expected:
        errors.append("unexpected or missing keys")
    decision = payload.get("decision")
    label = payload.get("classification")
    if decision not in {"classify", "abstain"}:
        errors.append("invalid decision")
    if label not in LABELS:
        errors.append("invalid classification")
    if decision == "abstain" and label not in {"ambiguous_reference", "inaccessible_or_invalid"}:
        errors.append("abstention must use an abstention label")
    if decision == "classify" and label in {"ambiguous_reference", "inaccessible_or_invalid"}:
        errors.append("unknown label must abstain")
    confidence = payload.get("confidence")
    if not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
        errors.append("invalid confidence")
    if not isinstance(payload.get("evidence_quote"), str) or len(str(payload.get("evidence_quote", ""))) > 200:
        errors.append("invalid evidence quote")
    if not isinstance(payload.get("rationale"), str) or len(str(payload.get("rationale", ""))) > 600:
        errors.append("invalid rationale")
    missing = payload.get("missing_evidence")
    if not isinstance(missing, list) or len(missing) > 6 or not all(isinstance(value, str) for value in missing):
        errors.append("invalid missing evidence")
    return errors


def usage_from_events(text: str) -> dict[str, int]:
    usage = {"input_tokens": 0, "cached_input_tokens": 0, "cache_write_input_tokens": 0, "output_tokens": 0, "reasoning_output_tokens": 0}
    for line in text.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "turn.completed" and isinstance(event.get("usage"), dict):
            for key in usage:
                value = event["usage"].get(key, 0)
                usage[key] += int(value) if isinstance(value, (int, float)) else 0
    return usage


def run_one(
    codex: str,
    record: dict[str, Any],
    model: str,
    effort: str,
    prompt: Path,
    schema: Path,
    raw_dir: Path,
) -> dict[str, Any]:
    review_id = str(record["review_id"])
    started = datetime.now(timezone.utc)
    raw_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f"luna-compare-{review_id}-") as temp:
        temp_path = Path(temp)
        codex_home = temp_path / "codex-home"
        codex_home.mkdir()
        if not AUTH.exists():
            raise RuntimeError("Codex authentication file not found")
        shutil.copy2(AUTH, codex_home / "auth.json")
        local_schema = temp_path / "schema.json"
        shutil.copy2(schema, local_schema)
        final_path = temp_path / "final.json"
        command = [
            codex, "exec", "--ephemeral", "--ignore-user-config", "--ignore-rules",
            "--skip-git-repo-check", "--sandbox", "read-only", "--model", model,
            "-c", f'model_reasoning_effort="{effort}"', "--output-schema", str(local_schema),
            "--output-last-message", str(final_path), "--json", "--cd", str(temp_path), "-",
        ]
        environment = os.environ.copy()
        environment["CODEX_HOME"] = str(codex_home)
        completed = subprocess.run(
            command,
            input=render_prompt(record, prompt),
            text=True,
            capture_output=True,
            check=False,
            env=environment,
        )
        final_text = final_path.read_text(encoding="utf-8") if final_path.exists() else ""
    (raw_dir / f"{review_id}.events.jsonl").write_text(completed.stdout, encoding="utf-8")
    (raw_dir / f"{review_id}.final.txt").write_text(final_text, encoding="utf-8")
    (raw_dir / f"{review_id}.stderr.txt").write_text(completed.stderr, encoding="utf-8")
    parsed: dict[str, Any] = {}
    errors: list[str] = []
    try:
        candidate = json.loads(final_text)
        if isinstance(candidate, dict):
            parsed = candidate
            errors.extend(validate(parsed))
        else:
            errors.append("response is not an object")
    except json.JSONDecodeError as exc:
        errors.append(f"invalid JSON: {exc.msg}")
    if completed.returncode:
        errors.append(f"Codex exit code {completed.returncode}")
    finished = datetime.now(timezone.utc)
    return {
        "review_id": review_id,
        "decision": parsed.get("decision", ""),
        "classification": parsed.get("classification", ""),
        "confidence": parsed.get("confidence", ""),
        "evidence_quote": parsed.get("evidence_quote", ""),
        "rationale": parsed.get("rationale", ""),
        "missing_evidence": json.dumps(parsed.get("missing_evidence", []), ensure_ascii=False),
        "valid_response": not errors,
        "validation_errors": " | ".join(errors),
        "exit_code": completed.returncode,
        "started_at_utc": started.isoformat(),
        "finished_at_utc": finished.isoformat(),
        "duration_seconds": round((finished - started).total_seconds(), 3),
        **usage_from_events(completed.stdout),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--prompt", type=Path, required=True)
    parser.add_argument("--schema", type=Path, required=True)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--purpose", required=True)
    parser.add_argument("--model", default="gpt-6-luna")
    parser.add_argument("--reasoning-effort", default="high")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--ids", nargs="*", default=None)
    args = parser.parse_args()
    if not 1 <= args.workers <= 8:
        raise ValueError("workers must be between 1 and 8")
    codex = shutil.which("codex")
    if not codex:
        raise RuntimeError("codex executable not found")
    records = load_records(args.input)
    if args.ids:
        selected = set(args.ids)
        records = [record for record in records if str(record["review_id"]) in selected]
        found = {str(record["review_id"]) for record in records}
        if found != selected:
            raise ValueError(f"Unknown review IDs: {sorted(selected - found)}")
    if not records:
        raise ValueError("No records")

    started = datetime.now(timezone.utc)
    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            pool.submit(run_one, codex, record, args.model, args.reasoning_effort, args.prompt, args.schema, args.raw_dir): record
            for record in records
        }
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            print(f"{result['review_id']}: {'valid' if result['valid_response'] else 'invalid'}", flush=True)
    results.sort(key=lambda row: str(row["review_id"]))
    args.results.parent.mkdir(parents=True, exist_ok=True)
    with args.results.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(results[0]))
        writer.writeheader()
        writer.writerows(results)

    finished = datetime.now(timezone.utc)
    valid_count = sum(bool(row["valid_response"]) for row in results)
    totals = {
        key: sum(int(row[key]) for row in results)
        for key in ["input_tokens", "cached_input_tokens", "cache_write_input_tokens", "output_tokens", "reasoning_output_tokens"]
    }
    version = subprocess.run([codex, "--version"], text=True, capture_output=True, check=False).stdout.strip()
    manifest = {
        "purpose": args.purpose,
        "started_at_utc": started.isoformat(),
        "finished_at_utc": finished.isoformat(),
        "duration_seconds": round((finished - started).total_seconds(), 3),
        "model": args.model,
        "reasoning_effort": args.reasoning_effort,
        "temperature": "not exposed by Codex CLI",
        "codex_cli_version": version,
        "records_requested": len(records),
        "valid_responses": valid_count,
        "valid_response_rate": valid_count / len(records),
        "token_usage": totals,
        "input_file": str(args.input),
        "input_sha256": sha256(args.input),
        "prompt_file": str(args.prompt),
        "prompt_sha256": sha256(args.prompt),
        "schema_file": str(args.schema),
        "schema_sha256": sha256(args.schema),
        "results_file": str(args.results),
        "results_sha256": sha256(args.results),
        "raw_directory": str(args.raw_dir),
    }
    args.manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"valid": f"{valid_count}/{len(records)}", "usage": totals}, indent=2))


if __name__ == "__main__":
    main()
