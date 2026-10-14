"""Run the frozen LLM judge independently on H001-H090.

Every reference is sent to a fresh ephemeral Codex process with an isolated
configuration directory. The process receives only the frozen prompt, output
schema, and the leakage-free record for that reference.
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
INPUT_PATH = INTERIM / "llm_judge_inputs_human_90.jsonl"
PROMPT_PATH = VALIDATION / "LLM_JUDGE_PROMPT.md"
SCHEMA_PATH = VALIDATION / "llm_judge_output_schema.json"
RAW_DIR = INTERIM / "llm_human_90_raw"
RESULTS_PATH = INTERIM / "llm_human_90_results.csv"
MANIFEST_PATH = INTERIM / "llm_human_90_run_manifest.json"

# Kept identical to the earlier pilot configuration for comparability.
MODEL = "gpt-6-sol"
REASONING_EFFORT = "low"
MAX_WORKERS = 4
AUTH_PATH = Path("/Users/pedroodorize/.codex/auth.json")

LABELS = {
    "confirmed_exists",
    "confirmed_missing_problematic",
    "expected_absence_create",
    "expected_absence_move_or_delete",
    "non_file_reference",
    "ambiguous_reference",
    "inaccessible_or_invalid",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_records(input_path: Path, expected_count: int | None = None) -> list[dict[str, object]]:
    with input_path.open(encoding="utf-8") as handle:
        records = [json.loads(line) for line in handle if line.strip()]
    if expected_count is not None and len(records) != expected_count:
        raise ValueError(f"Expected {expected_count} LLM inputs; found {len(records)}")
    ids = [str(record["review_id"]) for record in records]
    if len(set(ids)) != len(ids):
        raise ValueError("Duplicate review IDs in LLM input")
    return records


def frozen_prompt(record: dict[str, object], prompt_path: Path) -> str:
    template = prompt_path.read_text(encoding="utf-8")
    if "{{record}}" not in template:
        raise ValueError("Frozen prompt is missing the {{record}} placeholder")
    record_json = json.dumps(record, ensure_ascii=False, indent=2)
    return (
        "Apply the following frozen classification protocol. The sections "
        "labelled 'Mensagem de sistema' and 'Mensagem de usuário' are the "
        "experiment's fixed instructions. Return only the required JSON.\n\n"
        + template.replace("{{record}}", record_json)
    )


def validate_response(payload: dict[str, object]) -> list[str]:
    errors: list[str] = []
    if payload.get("classification") not in LABELS:
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
    model: str,
    raw_dir: Path,
    prompt_path: Path,
) -> dict[str, object]:
    review_id = str(record["review_id"])
    started = datetime.now(timezone.utc)
    raw_dir.mkdir(parents=True, exist_ok=True)

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
            model,
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
            input=frozen_prompt(record, prompt_path),
            text=True,
            capture_output=True,
            check=False,
            env=child_env,
        )
        final_text = final_path.read_text(encoding="utf-8") if final_path.exists() else ""

    event_path = raw_dir / f"{review_id}.events.jsonl"
    final_raw_path = raw_dir / f"{review_id}.final.txt"
    stderr_path = raw_dir / f"{review_id}.stderr.txt"
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
    parser.add_argument("--model", default=MODEL)
    parser.add_argument("--raw-dir", type=Path, default=RAW_DIR)
    parser.add_argument("--results-path", type=Path, default=RESULTS_PATH)
    parser.add_argument("--manifest-path", type=Path, default=MANIFEST_PATH)
    parser.add_argument("--input-path", type=Path, default=INPUT_PATH)
    parser.add_argument("--prompt-path", type=Path, default=PROMPT_PATH)
    parser.add_argument("--expected-count", type=int, default=None)
    args = parser.parse_args()

    codex_path = shutil.which("codex")
    if codex_path is None:
        raise RuntimeError("codex executable not found")
    if args.workers < 1 or args.workers > 8:
        raise ValueError("--workers must be between 1 and 8")

    records = load_records(args.input_path, args.expected_count)
    if args.ids:
        selected = set(args.ids)
        records = [row for row in records if str(row["review_id"]) in selected]
        found = {str(row["review_id"]) for row in records}
        if selected != found:
            raise ValueError(f"Unknown review IDs: {sorted(selected - found)}")
    if not records:
        raise ValueError("No LLM input records selected")

    run_started = datetime.now(timezone.utc)
    results: list[dict[str, object]] = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            pool.submit(
                run_one, codex_path, row, args.model, args.raw_dir, args.prompt_path
            ): row
            for row in records
        }
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            status = "valid" if result["valid_response"] else "invalid"
            print(f"{result['review_id']}: {status}", flush=True)

    results.sort(key=lambda row: str(row["review_id"]))
    fieldnames = list(results[0])
    args.results_path.parent.mkdir(parents=True, exist_ok=True)
    with args.results_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    version = subprocess.run(
        [codex_path, "--version"], text=True, capture_output=True, check=False
    ).stdout.strip()
    valid_count = sum(bool(row["valid_response"]) for row in results)
    run_finished = datetime.now(timezone.utc)
    manifest = {
        "purpose": "Independent frozen-prompt LLM judge run for H001-H090",
        "started_at_utc": run_started.isoformat(),
        "finished_at_utc": run_finished.isoformat(),
        "duration_seconds": round((run_finished - run_started).total_seconds(), 3),
        "provider": "OpenAI authenticated through Codex CLI",
        "model": args.model,
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
        "input_file": str(args.input_path),
        "input_sha256": sha256(args.input_path),
        "prompt_file": str(args.prompt_path),
        "prompt_sha256": sha256(args.prompt_path),
        "schema_file": str(SCHEMA_PATH.relative_to(PROJECT_ROOT)),
        "schema_sha256": sha256(SCHEMA_PATH),
        "records_requested": len(records),
        "review_ids": [row["review_id"] for row in results],
        "valid_responses": valid_count,
        "valid_response_rate": valid_count / len(results),
        "results_file": str(args.results_path),
        "results_sha256": sha256(args.results_path),
        "raw_directory": str(args.raw_dir),
    }
    args.manifest_path.parent.mkdir(parents=True, exist_ok=True)
    args.manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"Results: {args.results_path}")
    print(f"Valid responses: {valid_count}/{len(results)}")
    print(f"Manifest: {args.manifest_path}")


if __name__ == "__main__":
    main()
