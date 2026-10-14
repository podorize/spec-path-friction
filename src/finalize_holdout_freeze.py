"""Add immutable sample hashes to an already generated holdout-v1 freeze."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from create_longitudinal_holdout_screening import FROZEN_FILES


ROOT = Path(__file__).resolve().parents[1]
INTERIM = ROOT / "data" / "interim"
SAMPLE = INTERIM / "holdout_screening_v1_240.csv"
KEY = INTERIM / "holdout_screening_v1_240_key.csv"
MANIFEST = INTERIM / "holdout_screening_v1_240_manifest.json"
FREEZE = ROOT / "results" / "validation" / "holdout_v1" / "FROZEN_CONFIG.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    manifest["screening_file_sha256"] = sha256(SAMPLE)
    manifest["private_key_sha256"] = sha256(KEY)
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    freeze = json.loads(FREEZE.read_text(encoding="utf-8"))
    freeze["sample_manifest_sha256"] = sha256(MANIFEST)
    freeze["screening_file_sha256"] = sha256(SAMPLE)
    freeze["private_key_sha256"] = sha256(KEY)
    freeze["configuration_files"] = {
        str(path.relative_to(ROOT)): sha256(path) for path in FROZEN_FILES
    }
    FREEZE.write_text(json.dumps(freeze, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Screening SHA-256: {freeze['screening_file_sha256']}")
    print(f"Private key SHA-256: {freeze['private_key_sha256']}")


if __name__ == "__main__":
    main()
