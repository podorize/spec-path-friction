"""Freeze the LLM execution wrapper before the held-out model run."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FREEZE = ROOT / "results" / "validation" / "holdout_v1" / "FROZEN_CONFIG.json"
RUNNER = ROOT / "src" / "run_holdout_llm_judge_v2.py"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    frozen = json.loads(FREEZE.read_text(encoding="utf-8"))
    relative = str(RUNNER.relative_to(ROOT))
    if relative in frozen["configuration_files"]:
        raise SystemExit("The holdout LLM runner is already frozen")
    frozen["configuration_files"][relative] = sha256(RUNNER)
    FREEZE.write_text(json.dumps(frozen, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Frozen {relative}: {frozen['configuration_files'][relative]}")


if __name__ == "__main__":
    main()
