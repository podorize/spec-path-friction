"""Import human round 2 and measure same-reviewer test-retest stability."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
INTERIM = ROOT / "data" / "interim"
DEFAULT_WORKBOOK = INTERIM / "holdout_human_v1_90_r2_reviews_completed.xlsx"
R2_KEY = INTERIM / "holdout_human_v1_90_r2_key.csv"
R1_LABELS = INTERIM / "holdout_human_v1_90_labels.csv"
R1_KEY = INTERIM / "holdout_human_v1_90_key.csv"
OUTPUT_DIR = ROOT / "results" / "validation" / "holdout_v1" / "human_retest"

LABELS = [
    "confirmed_exists",
    "confirmed_missing_problematic",
    "expected_absence_create",
    "expected_absence_move_or_delete",
    "external_repository_reference",
    "non_file_reference",
    "ambiguous_reference",
    "inaccessible_or_invalid",
]
NONPROBLEMATIC = {
    "confirmed_exists",
    "expected_absence_create",
    "expected_absence_move_or_delete",
    "external_repository_reference",
    "non_file_reference",
}
UNKNOWN = {"ambiguous_reference", "inaccessible_or_invalid"}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def state(label: str) -> str:
    if label == "confirmed_missing_problematic":
        return "problematic"
    if label in NONPROBLEMATIC:
        return "nonproblematic"
    if label in UNKNOWN:
        return "unknown"
    raise ValueError(f"Unknown label: {label}")


def agreement_metrics(left: pd.Series, right: pd.Series, categories: list[str]) -> dict[str, float | int]:
    n = len(left)
    if n == 0:
        return {"n": 0, "observed_agreement": float("nan"), "cohen_kappa": float("nan"), "gwet_ac1": float("nan")}
    observed = float((left == right).mean())
    p_left = left.value_counts(normalize=True).reindex(categories, fill_value=0.0)
    p_right = right.value_counts(normalize=True).reindex(categories, fill_value=0.0)
    kappa_expected = float((p_left * p_right).sum())
    kappa = (observed - kappa_expected) / (1 - kappa_expected) if kappa_expected < 1 else float("nan")
    average_marginal = (p_left + p_right) / 2
    if len(categories) > 1:
        ac1_expected = float((average_marginal * (1 - average_marginal)).sum() / (len(categories) - 1))
    else:
        ac1_expected = 0.0
    ac1 = (observed - ac1_expected) / (1 - ac1_expected) if ac1_expected < 1 else float("nan")
    return {
        "n": n,
        "observed_agreement": observed,
        "cohen_kappa": kappa,
        "gwet_ac1": ac1,
    }


def markdown_table(frame: pd.DataFrame) -> str:
    headers = [str(frame.index.name or "")] + [str(value) for value in frame.columns]
    rows = [[str(index)] + [str(value) for value in row] for index, row in frame.iterrows()]
    return "\n".join(
        [
            "| " + " | ".join(headers) + " |",
            "| " + " | ".join(["---"] * len(headers)) + " |",
            *["| " + " | ".join(row) + " |" for row in rows],
        ]
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workbook", type=Path, default=DEFAULT_WORKBOOK)
    args = parser.parse_args()

    r2 = pd.read_excel(args.workbook, sheet_name="Review", dtype=str, keep_default_na=False)
    expected_columns = {
        "Review ID", "Reviewer", "Classification", "Evidence note (required)", "Access issue"
    }
    if not expected_columns.issubset(r2.columns):
        raise ValueError(f"Missing workbook columns: {sorted(expected_columns - set(r2.columns))}")
    if len(r2) != 90 or r2["Review ID"].duplicated().any():
        raise ValueError("Round 2 must contain 90 unique Review IDs")
    for column in ["Review ID", "Reviewer", "Classification", "Evidence note (required)"]:
        if (r2[column].str.strip() == "").any():
            raise ValueError(f"Blank required field: {column}")
    invalid = sorted(set(r2["Classification"]) - set(LABELS))
    if invalid:
        raise ValueError(f"Invalid round-2 labels: {invalid}")

    r2_key = pd.read_csv(R2_KEY, dtype=str, keep_default_na=False)
    r1 = pd.read_csv(R1_LABELS, dtype=str, keep_default_na=False)
    r1_key = pd.read_csv(R1_KEY, dtype=str, keep_default_na=False)
    if set(r2["Review ID"]) != set(r2_key["round2_review_id"]):
        raise ValueError("Round-2 workbook IDs do not match the private key")

    r2_clean = r2.rename(
        columns={
            "Review ID": "round2_review_id",
            "Reviewer": "round2_reviewer_id",
            "Classification": "round2_classification",
            "Evidence note (required)": "round2_evidence_note",
            "Access issue": "round2_access_issue",
        }
    )[[
        "round2_review_id", "round2_reviewer_id", "round2_classification",
        "round2_evidence_note", "round2_access_issue",
    ]]
    merged = (
        r2_clean
        .merge(r2_key, on="round2_review_id", validate="one_to_one")
        .merge(
            r1[["human_review_id", "reviewer_id", "manual_classification", "evidence_note", "access_issue"]],
            left_on="round1_review_id",
            right_on="human_review_id",
            validate="one_to_one",
        )
        .merge(r1_key, left_on="round1_review_id", right_on="human_review_id", validate="one_to_one", suffixes=("", "_key"))
    )
    merged = merged.rename(
        columns={
            "reviewer_id": "round1_reviewer_id",
            "manual_classification": "round1_classification",
            "evidence_note": "round1_evidence_note",
            "access_issue": "round1_access_issue",
        }
    )
    merged["round1_state"] = merged["round1_classification"].map(state)
    merged["round2_state"] = merged["round2_classification"].map(state)
    merged["exact_label_agreement"] = merged["round1_classification"] == merged["round2_classification"]
    merged["three_state_agreement"] = merged["round1_state"] == merged["round2_state"]
    merged["stable_decisive_reference"] = merged["three_state_agreement"] & merged["round1_state"].isin(["problematic", "nonproblematic"])
    merged["stable_unknown"] = merged["three_state_agreement"] & (merged["round1_state"] == "unknown")
    merged["unstable_reference"] = ~merged["three_state_agreement"]
    merged["round2_temporary_access_failure"] = merged["round2_access_issue"].str.contains("temporary", case=False, na=False)

    exact = agreement_metrics(merged["round1_classification"], merged["round2_classification"], LABELS)
    states = ["problematic", "nonproblematic", "unknown"]
    three = agreement_metrics(merged["round1_state"], merged["round2_state"], states)
    no_temp = merged.loc[~merged["round2_temporary_access_failure"]]
    three_no_temp = agreement_metrics(no_temp["round1_state"], no_temp["round2_state"], states)

    exact_matrix = pd.crosstab(
        merged["round1_classification"], merged["round2_classification"],
        rownames=["Round 1"], colnames=["Round 2"], dropna=False,
    ).reindex(index=LABELS, columns=LABELS, fill_value=0)
    state_matrix = pd.crosstab(
        merged["round1_state"], merged["round2_state"],
        rownames=["Round 1"], colnames=["Round 2"], dropna=False,
    ).reindex(index=states, columns=states, fill_value=0)

    summary = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "workbook": str(args.workbook),
        "workbook_sha256": sha256(args.workbook),
        "n_cases": len(merged),
        "round1_label_counts": merged["round1_classification"].value_counts().sort_index().to_dict(),
        "round2_label_counts": merged["round2_classification"].value_counts().sort_index().to_dict(),
        "round1_state_counts": merged["round1_state"].value_counts().sort_index().to_dict(),
        "round2_state_counts": merged["round2_state"].value_counts().sort_index().to_dict(),
        "exact_eight_class": exact,
        "three_state": three,
        "three_state_excluding_round2_temporary_access_failures": three_no_temp,
        "stable_decisive_cases": int(merged["stable_decisive_reference"].sum()),
        "stable_problematic_cases": int((merged["stable_decisive_reference"] & (merged["round1_state"] == "problematic")).sum()),
        "stable_nonproblematic_cases": int((merged["stable_decisive_reference"] & (merged["round1_state"] == "nonproblematic")).sum()),
        "stable_unknown_cases": int(merged["stable_unknown"].sum()),
        "unstable_cases": int(merged["unstable_reference"].sum()),
        "round2_access_issue_cases": int((merged["round2_access_issue"].str.strip() != "").sum()),
        "round2_temporary_access_failure_cases": int(merged["round2_temporary_access_failure"].sum()),
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    merged.to_csv(OUTPUT_DIR / "human_retest_cases.csv", index=False)
    exact_matrix.to_csv(OUTPUT_DIR / "exact_label_transition_matrix.csv")
    state_matrix.to_csv(OUTPUT_DIR / "three_state_transition_matrix.csv")
    (OUTPUT_DIR / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    report = f"""# Human test-retest analysis

## Scope

The same reviewer classified the same 90 cases twice. Round 2 used a new order and new identifiers. This is an intra-rater test-retest analysis, not an inter-rater study.

## Main results

- Exact eight-class agreement: **{exact['observed_agreement']:.1%}** ({int(merged['exact_label_agreement'].sum())}/90)
- Eight-class Cohen's kappa: **{exact['cohen_kappa']:.3f}**
- Eight-class Gwet's AC1: **{exact['gwet_ac1']:.3f}**
- Three-state agreement: **{three['observed_agreement']:.1%}** ({int(merged['three_state_agreement'].sum())}/90)
- Three-state Cohen's kappa: **{three['cohen_kappa']:.3f}**
- Three-state Gwet's AC1: **{three['gwet_ac1']:.3f}**
- Stable decisive cases for primary binary evaluation: **{summary['stable_decisive_cases']}**
- Stable problematic cases: **{summary['stable_problematic_cases']}**
- Stable nonproblematic cases: **{summary['stable_nonproblematic_cases']}**
- Stable unknown cases: **{summary['stable_unknown_cases']}**
- Unstable three-state cases: **{summary['unstable_cases']}**

## Access sensitivity

Round 2 contains **{summary['round2_access_issue_cases']}** access-issue records, including **{summary['round2_temporary_access_failure_cases']}** described as temporary GitHub failures. Excluding those temporary failures, three-state agreement is **{three_no_temp['observed_agreement']:.1%}** across {three_no_temp['n']} cases. This is a sensitivity analysis, not a replacement for the prespecified full-sample result.

## Three-state transition matrix

{markdown_table(state_matrix)}

## Exact-label transition matrix

{markdown_table(exact_matrix)}

## Interpretation rule for system evaluation

Primary binary performance uses only stable decisive cases. Stable unknown cases contribute to coverage and abstention reporting but not binary diagnostic metrics. Three-state disagreements are retained as human-reference instability and are not adjudicated after seeing system predictions. Round-1-only and round-2-only analyses are secondary sensitivity checks.
"""
    (OUTPUT_DIR / "HUMAN_RETEST_ANALYSIS.md").write_text(report, encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
