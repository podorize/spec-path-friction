"""Run the frozen LLM judge on the leakage-free B001-B030 input set.

Each reference is evaluated in a fresh ephemeral Codex CLI process whose
working directory contains only the output schema. The runner records the raw
event stream, final model message, parsed response, model configuration, file
hashes, and validity status for reproducibility.
"""

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


PROJECT_ROOT = Path(__file__).resolve().parents[1]
INTERIM = PROJECT_ROOT / "data" / "interim"
VALIDATION = PROJECT_ROOT / "validation"
INPUT_PATH = INTERIM / "llm_judge_inputs_blind_eval_30.jsonl"
PROMPT_PATH = VALIDATION / "LLM_JUDGE_PROMPT.md"
SCHEMA_PATH = VALIDATION / "llm_judge_output_schema.json"
RAW_DIR = INTERIM / "llm_blind_eval_30_raw"
RESULTS_PATH = INTERIM / "llm_blind_eval_30_results.csv"
MANIFEST_PATH = INTERIM / "llm_blind_eval_30_run_manifest.json"

MODEL = "gpt-6-sol"
REASONING_EFFORT = "low"
MAX_WORKERS = 4
AUTH_PATH = Path("/Users/pedroodorize/.codex/auth.json")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_records() -> list[dict[str, object]]:
    with INPUT_PATH.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def frozen_prompt(record: dict[str, object]) -> str:
    template = PROMPT_PATH.read_text(encoding="utf-8")
    record_json = json.dumps(record, ensure_ascii=False, indent=2)
    if "{{record}}" not in template:
        raise ValueError("Frozen prompt is missing the {{record}} placeholder")
    rendered = template.replace("{{record}}", record_json)
    return (
        "Apply the following frozen classification protocol. The sections "
        "labelled 'Mensagem de sistema' and 'Mensagem de usuário' are the "
        "experiment's fixed instructions. Return only the required JSON.\n\n"
        + rendered
    )


def validate_response(payload: dict[str, object]) -> list[str]:
    errors: list[str] = []
    labels = {
        "confirmed_exists",
        "confirmed_missing_problematic",
        "expected_absence_create",
        "expected_absence_move_or_delete",
        "non_file_reference",
        "ambiguous_reference",
        "inaccessible_or_invalid",
    }
    if payload.get("classification") not in labels:
        errors.append("invalid classification")
    confidence = payload.get("confidence")
    if not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
        errors.append("invalid confidence")
    evidence = payload.get("evidence_quote")
    if not isinstance(evidence, str) or len(evidence) > 160:
        errors.append("invalid evidence_quote")
    rationale = payload.get("rationale")
    if not isinstance(rationale, str) or len(rationale.split()) > 40:
        errors.append("invalid rationale")
    if set(payload) != {
        "classification",
        "confidence",
        "evidence_quote",
        "rationale",
    }:
        errors.append("unexpected or missing keys")
    return errors


def run_one(
    codex_path: str,
    record: dict[str, object],
) -> dict[str, object]:
    review_id = str(record["review_id"])
    started = datetime.now(timezone.utc)
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix=f"msr-judge-{review_id}-") as tmp:
        tmp_path = Path(tmp)
        isolated_codex_home = tmp_path / "codex-home"
        isolated_codex_home.mkdir()
        if not AUTH_PATH.exists():
            raise RuntimeError("Codex authentication file not found")
        shutil.copy2(AUTH_PATH, isolated_codex_home / "auth.json")
        local_schema = tmp_path / "output_schema.json"
        shutil.copy2(SCHEMA_PATH, local_schema)
        final_path = tmp_path / "final.json"
        command = [
            codex_path,
            "exec",
            "--ephemeral",
            "--ignore-user-config",
            "--ignore-rules",
            "--skip-git-repo-check",
            "--sandbox",
            "read-only",
            "--model",
            MODEL,
            "-c",
            f'model_reasoning_effort="{REASONING_EFFORT}"',
            "--output-schema",
            str(local_schema),
            "--output-last-message",
            str(final_path),
            "--json",
            "--cd",
            str(tmp_path),
            "-",
        ]
        child_env = os.environ.copy()
        child_env["CODEX_HOME"] = str(isolated_codex_home)
        completed = subprocess.run(
            command,
            input=frozen_prompt(record),
            text=True,
            capture_output=True,
            check=False,
            env=child_env,
        )
        final_text = final_path.read_text(encoding="utf-8") if final_path.exists() else ""

    event_path = RAW_DIR / f"{review_id}.events.jsonl"
    final_raw_path = RAW_DIR / f"{review_id}.final.txt"
    stderr_path = RAW_DIR / f"{review_id}.stderr.txt"
    event_path.write_text(completed.stdout, encoding="utf-8")
    final_raw_path.write_text(final_text, encoding="utf-8")
    stderr_path.write_text(completed.stderr, encoding="utf-8")

    parsed: dict[str, object] = {}
    validation_errors: list[str] = []
    try:
        candidate = json.loads(final_text)
        if not isinstance(candidate, dict):
            validation_errors.append("response is not a JSON object")
        else:
            parsed = candidate
            validation_errors.extend(validate_response(parsed))
    except json.JSONDecodeError as exc:
        validation_errors.append(f"invalid JSON: {exc.msg}")

    if completed.returncode != 0:
        validation_errors.append(f"Codex exit code {completed.returncode}")

    finished = datetime.now(timezone.utc)
    return {
        "review_id": review_id,
        "reference_id": record["reference_id"],
        "classification": parsed.get("classification", ""),
        "confidence": parsed.get("confidence", ""),
        "evidence_quote": parsed.get("evidence_quote", ""),
        "rationale": parsed.get("rationale", ""),
        "valid_response": not validation_errors,
        "validation_errors": " | ".join(validation_errors),
        "exit_code": completed.returncode,
        "started_at_utc": started.isoformat(),
        "finished_at_utc": finished.isoformat(),
        "duration_seconds": round((finished - started).total_seconds(), 3),
        "events_file": event_path.name,
        "final_file": final_raw_path.name,
        "stderr_file": stderr_path.name,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ids", nargs="*", default=None)
    parser.add_argument("--workers", type=int, default=MAX_WORKERS)
    args = parser.parse_args()

    codex_path = shutil.which("codex")
    if codex_path is None:
        raise RuntimeError("codex executable not found")
    if args.workers < 1 or args.workers > 8:
        raise ValueError("--workers must be between 1 and 8")

    records = load_records()
    if args.ids:
        selected = set(args.ids)
        records = [row for row in records if row["review_id"] in selected]
        missing = selected.difference(str(row["review_id"]) for row in records)
        if missing:
            raise ValueError(f"Unknown review IDs: {sorted(missing)}")
    if not records:
        raise ValueError("No LLM input records selected")

    run_started = datetime.now(timezone.utc)
    results: list[dict[str, object]] = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(run_one, codex_path, row): row for row in records}
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            status = "valid" if result["valid_response"] else "invalid"
            print(f"{result['review_id']}: {status}", flush=True)

    results.sort(key=lambda row: str(row["review_id"]))
    fieldnames = list(results[0])
    with RESULTS_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    version = subprocess.run(
        [codex_path, "--version"],
        text=True,
        capture_output=True,
        check=False,
    ).stdout.strip()
    valid_count = sum(bool(row["valid_response"]) for row in results)
    run_finished = datetime.now(timezone.utc)
    manifest = {
        "purpose": "Independent frozen-prompt LLM judge run for B001-B030",
        "started_at_utc": run_started.isoformat(),
        "finished_at_utc": run_finished.isoformat(),
        "duration_seconds": round((run_finished - run_started).total_seconds(), 3),
        "provider": "OpenAI authenticated through Codex CLI",
        "model": MODEL,
        "reasoning_effort": REASONING_EFFORT,
        "temperature": "not exposed by Codex CLI",
        "generation_parameters": {
            "structured_output": True,
            "one_fresh_ephemeral_process_per_record": True,
            "workers": args.workers,
            "sandbox": "read-only",
            "user_config_loaded": False,
            "project_rules_loaded": False,
        },
        "delivery_mode": (
            "Frozen system and user sections supplied together in a fresh "
            "Codex exec prompt; wrapper text is fixed in the runner."
        ),
        "codex_cli_version": version,
        "input_file": INPUT_PATH.name,
        "input_sha256": sha256(INPUT_PATH),
        "prompt_file": str(PROMPT_PATH.relative_to(PROJECT_ROOT)),
        "prompt_sha256": sha256(PROMPT_PATH),
        "schema_file": str(SCHEMA_PATH.relative_to(PROJECT_ROOT)),
        "schema_sha256": sha256(SCHEMA_PATH),
        "records_requested": len(records),
        "review_ids": [row["review_id"] for row in results],
        "valid_responses": valid_count,
        "valid_response_rate": valid_count / len(results),
        "results_file": RESULTS_PATH.name,
        "results_sha256": sha256(RESULTS_PATH),
        "raw_directory": RAW_DIR.name,
    }
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Results: {RESULTS_PATH}")
    print(f"Valid responses: {valid_count}/{len(results)}")
    print(f"Manifest: {MANIFEST_PATH}")


if __name__ == "__main__":
    main()
