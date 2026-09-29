"""Consolidate LLM triage and create a blinded workbook for human validation.

All inputs and outputs belong to ``data/interim`` and are intentionally
excluded from version control: they contain public repository identifiers
while the study is under double-anonymous review.
"""

from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
INTERIM = PROJECT_ROOT / "data" / "interim"
WORKBOOK_PATH = INTERIM / "validation_workbook_pilot.csv"
TRIAGE_PATHS = sorted(INTERIM.glob("llm_triage_*.csv"))
EVIDENCE_PATH = INTERIM / "validation_evidence_pilot.csv"
BLINDED_WORKBOOK_PATH = INTERIM / "validation_human_blinded_pilot.csv"
BLINDING_KEY_PATH = INTERIM / "validation_blinding_key_pilot.csv"
SEED = 20260928


def load_triage() -> pd.DataFrame:
    if len(TRIAGE_PATHS) != 3:
        raise ValueError(f"Expected three LLM triage files, found {len(TRIAGE_PATHS)}")

    triage = pd.concat((pd.read_csv(path) for path in TRIAGE_PATHS), ignore_index=True)
    required = {"id", "validation_group", "llm_triage", "evidence_note"}
    missing = required.difference(triage.columns)
    if missing:
        raise ValueError(f"Triage files are missing columns: {sorted(missing)}")
    if triage["id"].duplicated().any():
        raise ValueError("LLM triage contains duplicate reference ids")
    return triage.rename(
        columns={
            "llm_triage": "llm_triage_label",
            "evidence_note": "llm_triage_note",
        }
    )


def main() -> None:
    workbook = pd.read_csv(WORKBOOK_PATH)
    triage = load_triage()
    if workbook["id"].duplicated().any():
        raise ValueError("Validation workbook contains duplicate reference ids")

    evidence = workbook.merge(
        triage[["id", "llm_triage_label", "llm_triage_note"]],
        on="id",
        how="left",
        validate="one_to_one",
    )
    if evidence["llm_triage_label"].isna().any():
        raise ValueError("At least one sampled reference has no LLM triage label")
    evidence.to_csv(EVIDENCE_PATH, index=False)

    shuffled = evidence.sample(frac=1, random_state=SEED).reset_index(drop=True)
    shuffled.insert(0, "review_id", [f"R{index:03d}" for index in range(1, len(shuffled) + 1)])

    human_columns = [
        "review_id",
        "repo_name",
        "anchor_sha",
        "artifact_path",
        "code_path",
        "resolved_path",
        "artifact_url",
        "literal_code_url",
        "anchor_code_path",
        "anchor_code_url",
        "reference_excerpt",
    ]
    human_workbook = shuffled[human_columns].copy()
    human_workbook["reviewer_id"] = ""
    human_workbook["manual_classification"] = ""
    human_workbook["evidence_note"] = ""
    human_workbook["access_issue"] = ""
    human_workbook.to_csv(BLINDED_WORKBOOK_PATH, index=False)

    blinding_key = shuffled[
        ["review_id", "id", "validation_group", "task_done", "exists_at_anchor"]
    ]
    blinding_key.to_csv(BLINDING_KEY_PATH, index=False)

    print(f"Consolidated {len(evidence):,} references in {EVIDENCE_PATH}")
    print(f"Created blinded human workbook: {BLINDED_WORKBOOK_PATH}")
    print(f"Created private blinding key: {BLINDING_KEY_PATH}")


if __name__ == "__main__":
    main()
