"""Run the frozen longitudinal v2 judge on the held-out semantic queue."""

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
INPUT = ROOT / "results" / "validation" / "holdout_v1" / "hybrid_stage" / "llm_queue.jsonl"
PROMPT = ROOT / "validation" / "LLM_JUDGE_PROMPT_LONGITUDINAL_V2.md"
SCHEMA = ROOT / "validation" / "llm_judge_output_schema_v2.json"
RAW = ROOT / "results" / "validation" / "holdout_v1" / "llm_raw"
RESULTS = ROOT / "data" / "interim" / "holdout_llm_v1_results.csv"
MANIFEST = ROOT / "data" / "interim" / "holdout_llm_v1_manifest.json"
FREEZE = ROOT / "results" / "validation" / "holdout_v1" / "FROZEN_CONFIG.json"
AUTH = Path("/Users/pedroodorize/.codex/auth.json")
MODEL = "gpt-6-sol"
REASONING_EFFORT = "low"
LABELS = {
    "confirmed_exists", "confirmed_missing_problematic", "expected_absence_create",
    "expected_absence_move_or_delete", "external_repository_reference",
    "non_file_reference", "ambiguous_reference", "inaccessible_or_invalid",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_records(path: Path) -> list[dict[str, Any]]:
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    ids = [str(record["review_id"]) for record in records]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate review IDs")
    return records


def render_prompt(record: dict[str, Any]) -> str:
    template = PROMPT.read_text(encoding="utf-8")
    if "{{record}}" not in template:
        raise ValueError("Frozen prompt is missing {{record}}")
    return template.replace("{{record}}", json.dumps(record, ensure_ascii=False, indent=2))


def validate_response(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    expected = {"decision", "classification", "confidence", "evidence_quote", "rationale", "missing_evidence"}
    if set(payload) != expected:
        errors.append("unexpected or missing keys")
    decision = payload.get("decision")
    classification = payload.get("classification")
    if decision not in {"classify", "abstain"}:
        errors.append("invalid decision")
    if classification not in LABELS:
        errors.append("invalid classification")
    if decision == "abstain" and classification not in {"ambiguous_reference", "inaccessible_or_invalid"}:
        errors.append("abstention must use an abstention label")
    if decision == "classify" and classification in {"ambiguous_reference", "inaccessible_or_invalid"}:
        errors.append("semantic ambiguity must abstain")
    confidence = payload.get("confidence")
    if not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
        errors.append("invalid confidence")
    if not isinstance(payload.get("evidence_quote"), str) or len(str(payload.get("evidence_quote", ""))) > 200:
        errors.append("invalid evidence_quote")
    if not isinstance(payload.get("rationale"), str) or len(str(payload.get("rationale", ""))) > 600:
        errors.append("invalid rationale")
    missing = payload.get("missing_evidence")
    if not isinstance(missing, list) or len(missing) > 6 or not all(isinstance(value, str) for value in missing):
        errors.append("invalid missing_evidence")
    return errors


def run_one(codex: str, record: dict[str, Any]) -> dict[str, Any]:
    review_id = str(record["review_id"])
    started = datetime.now(timezone.utc)
    RAW.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f"holdout-v1-{review_id}-") as temp:
        temp_path = Path(temp)
        codex_home = temp_path / "codex-home"
        codex_home.mkdir()
        if not AUTH.exists():
            raise RuntimeError("Codex authentication file not found")
        shutil.copy2(AUTH, codex_home / "auth.json")
        local_schema = temp_path / "output_schema.json"
        shutil.copy2(SCHEMA, local_schema)
        final_path = temp_path / "final.json"
        command = [
            codex, "exec", "--ephemeral", "--ignore-user-config", "--ignore-rules",
            "--skip-git-repo-check", "--sandbox", "read-only", "--model", MODEL,
            "-c", f'model_reasoning_effort="{REASONING_EFFORT}"',
            "--output-schema", str(local_schema), "--output-last-message", str(final_path),
            "--json", "--cd", str(temp_path), "-",
        ]
        environment = os.environ.copy()
        environment["CODEX_HOME"] = str(codex_home)
        completed = subprocess.run(command, input=render_prompt(record), text=True, capture_output=True, check=False, env=environment)
        final_text = final_path.read_text(encoding="utf-8") if final_path.exists() else ""
    (RAW / f"{review_id}.events.jsonl").write_text(completed.stdout, encoding="utf-8")
    (RAW / f"{review_id}.final.txt").write_text(final_text, encoding="utf-8")
    (RAW / f"{review_id}.stderr.txt").write_text(completed.stderr, encoding="utf-8")
    parsed: dict[str, Any] = {}
    errors: list[str] = []
    try:
        candidate = json.loads(final_text)
        if isinstance(candidate, dict):
            parsed = candidate
            errors.extend(validate_response(parsed))
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
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    if not 1 <= args.workers <= 8:
        raise ValueError("--workers must be between 1 and 8")
    codex = shutil.which("codex")
    if not codex:
        raise RuntimeError("codex executable not found")
    records = load_records(INPUT)
    run_started = datetime.now(timezone.utc)
    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(run_one, codex, record): record for record in records}
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            print(f"{result['review_id']}: {'valid' if result['valid_response'] else 'invalid'}", flush=True)
    results.sort(key=lambda row: row["review_id"])
    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    with RESULTS.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(results[0]))
        writer.writeheader()
        writer.writerows(results)
    valid = sum(bool(row["valid_response"]) for row in results)
    version = subprocess.run([codex, "--version"], text=True, capture_output=True, check=False).stdout.strip()
    run_finished = datetime.now(timezone.utc)
    manifest = {
        "purpose": "Held-out v1 semantic LLM queue",
        "held_out_evaluation": True,
        "human_labels_observed": False,
        "started_at_utc": run_started.isoformat(),
        "finished_at_utc": run_finished.isoformat(),
        "duration_seconds": round((run_finished - run_started).total_seconds(), 3),
        "provider": "OpenAI authenticated through Codex CLI",
        "model": MODEL,
        "reasoning_effort": REASONING_EFFORT,
        "temperature": "not exposed by Codex CLI",
        "workers": args.workers,
        "codex_cli_version": version,
        "input_file": str(INPUT.relative_to(ROOT)),
        "input_sha256": sha256(INPUT),
        "prompt_file": str(PROMPT.relative_to(ROOT)),
        "prompt_sha256": sha256(PROMPT),
        "schema_file": str(SCHEMA.relative_to(ROOT)),
        "schema_sha256": sha256(SCHEMA),
        "frozen_config_sha256": sha256(FREEZE),
        "records_requested": len(records),
        "valid_responses": valid,
        "valid_response_rate": valid / len(records),
        "results_file": str(RESULTS.relative_to(ROOT)),
        "results_sha256": sha256(RESULTS),
        "raw_directory": str(RAW.relative_to(ROOT)),
    }
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Results: {RESULTS}")
    print(f"Valid responses: {valid}/{len(results)}")


if __name__ == "__main__":
    main()
