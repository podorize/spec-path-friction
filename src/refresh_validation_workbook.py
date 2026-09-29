"""Add resolver-aware links to the local validation workbook."""

from pathlib import Path
from urllib.parse import quote

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
INTERIM = PROJECT_ROOT / "data" / "interim"
CANDIDATES_PATH = INTERIM / "validation_candidates_pilot.csv"
WORKBOOK_PATH = INTERIM / "validation_workbook_pilot.csv"


def github_blob_url(repo_name: str, sha: str, path: str) -> str:
    return f"https://github.com/{repo_name}/blob/{sha}/{quote(path, safe='/')}"


def main() -> None:
    candidates = pd.read_csv(CANDIDATES_PATH)
    workbook = pd.read_csv(WORKBOOK_PATH)

    resolver_data = candidates[["id", "resolved_path"]]
    workbook = workbook.drop(columns=["resolved_path"], errors="ignore").merge(
        resolver_data, on="id", how="left", validate="one_to_one"
    )
    workbook = workbook.rename(columns={"code_url": "literal_code_url"})
    workbook["anchor_code_path"] = workbook["resolved_path"].fillna(
        workbook["code_path"]
    )
    workbook["anchor_code_url"] = workbook.apply(
        lambda row: github_blob_url(
            row["repo_name"], row["anchor_sha"], row["anchor_code_path"]
        ),
        axis=1,
    )

    preferred_columns = [
        "id",
        "validation_group",
        "sample_rank",
        "repo_name",
        "anchor_sha",
        "artifact_path",
        "code_path",
        "resolved_path",
        "task_done",
        "exists_at_anchor",
        "artifact_url",
        "literal_code_url",
        "anchor_code_path",
        "anchor_code_url",
        "reference_excerpt",
        "audit_status",
        "manual_classification",
        "evidence_note",
    ]
    workbook = workbook[[column for column in preferred_columns if column in workbook]]
    workbook.to_csv(WORKBOOK_PATH, index=False)
    print(f"Updated workbook: {WORKBOOK_PATH}")


if __name__ == "__main__":
    main()
