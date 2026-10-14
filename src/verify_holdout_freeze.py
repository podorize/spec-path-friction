"""Fail if a holdout-v1 sample or frozen configuration file has changed."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FREEZE = ROOT / "results" / "validation" / "holdout_v1" / "FROZEN_CONFIG.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    frozen = json.loads(FREEZE.read_text(encoding="utf-8"))
    checks = {
        ROOT / "data" / "interim" / "holdout_screening_v1_240.csv": frozen["screening_file_sha256"],
        ROOT / "data" / "interim" / "holdout_screening_v1_240_key.csv": frozen["private_key_sha256"],
        ROOT / frozen["sample_manifest"]: frozen["sample_manifest_sha256"],
    }
    checks.update({ROOT / path: expected for path, expected in frozen["configuration_files"].items()})
    mismatches = [str(path.relative_to(ROOT)) for path, expected in checks.items() if not path.exists() or sha256(path) != expected]
    if mismatches:
        raise SystemExit(f"Holdout-v1 freeze mismatch: {mismatches}")
    print(f"Holdout-v1 freeze verified: {len(checks)} files unchanged")


if __name__ == "__main__":
    main()
