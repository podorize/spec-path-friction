"""Adapt the blinded phase-2 CSV to the standard human-review workbook layout."""

from __future__ import annotations

from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data" / "interim" / "holdout_human_v1_90_blinded.csv"
OUTPUT = ROOT / "data" / "interim" / "holdout_human_v1_90_workbook.csv"


def main() -> None:
    frame = pd.read_csv(SOURCE, dtype=str, keep_default_na=False)
    frame = frame.rename(columns={"human_review_id": "review_id"})
    frame["anchor_path"] = frame["resolved_path"].where(frame["resolved_path"].str.strip() != "", frame["code_path"])
    frame["anchor_path_url"] = frame["candidate_path_url"].where(frame["candidate_path_url"].str.strip() != "", frame["literal_path_url"])
    columns = [
        "review_id", "repo_name", "anchor_sha", "artifact_path", "code_path",
        "resolved_path", "task_url", "literal_path_url", "anchor_path", "anchor_path_url",
        "task_context", "reviewer_id", "manual_classification", "evidence_note", "access_issue",
    ]
    frame[columns].to_csv(OUTPUT, index=False)
    print(f"Workbook input: {OUTPUT}")


if __name__ == "__main__":
    main()
