"""Compute final LLM performance against adjudicated H001-H090 labels."""

from __future__ import annotations

import csv
import json
import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from compare_human_llm_fresh_90 import (  # noqa: E402
    COLLAPSE,
    COLLAPSED_LABELS,
    LABELS,
    RESULTS as PRELIM_RESULTS,
    with_intervals,
    write_confusion,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
INTERIM = PROJECT_ROOT / "data" / "interim"
FINAL_PATH = INTERIM / "validation_human_90_R1_adjudicated.csv"
LLM_PATH = INTERIM / "llm_human_90_results.csv"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--human-path", type=Path, default=FINAL_PATH)
    parser.add_argument("--llm-path", type=Path, default=LLM_PATH)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "results" / "validation" / "human_90_adjudicated",
    )
    parser.add_argument("--model", default="gpt-6-sol")
    args = parser.parse_args()
    results_dir = args.output_dir
    cases_output = results_dir / "final_comparison_cases.csv"
    changes_output = results_dir / "adjudication_changes.csv"
    per_class_output = results_dir / "final_per_class_metrics.csv"
    confusion_output = results_dir / "final_confusion_matrix.csv"
    collapsed_confusion_output = results_dir / "final_collapsed_confusion_matrix.csv"
    summary_output = results_dir / "final_summary.json"
    report_output = results_dir / "FINAL_REPORT.md"
    results_dir.mkdir(parents=True, exist_ok=True)
    final = {row["review_id"]: row for row in read_csv(args.human_path)}
    llm = {row["review_id"]: row for row in read_csv(args.llm_path)}
    if set(final) != set(llm) or len(final) != 90:
        raise ValueError("Final labels and LLM results must contain the same 90 IDs")

    cases: list[dict[str, object]] = []
    changes: list[dict[str, str]] = []
    for review_id in sorted(final):
        row = final[review_id]
        model = llm[review_id]
        final_label = row["final_classification"]
        model_label = model["classification"]
        if final_label not in LABELS or model_label not in LABELS:
            raise ValueError(f"Invalid label for {review_id}")
        case = {
            "review_id": review_id,
            "repo_name": row["repo_name"],
            "artifact_path": row["artifact_path"],
            "code_path": row["code_path"],
            "initial_human_classification": row["initial_human_classification"],
            "final_classification": final_label,
            "llm_classification": model_label,
            "llm_confidence": float(model["confidence"]),
            "agreement": final_label == model_label,
            "collapsed_final": COLLAPSE[final_label],
            "collapsed_llm": COLLAPSE[model_label],
            "collapsed_agreement": COLLAPSE[final_label] == COLLAPSE[model_label],
            "adjudication_status": row["adjudication_status"],
            "decision_source": row["decision_source"],
        }
        cases.append(case)
        if row["initial_human_classification"] != final_label:
            changes.append(
                {
                    "review_id": review_id,
                    "initial_human_classification": row["initial_human_classification"],
                    "final_classification": final_label,
                    "decision_source": row["decision_source"],
                    "adjudication_rationale": row["adjudication_rationale"],
                }
            )

    all_pairs = [(str(row["final_classification"]), str(row["llm_classification"])) for row in cases]
    semantic_cases = [row for row in cases if row["final_classification"] != "inaccessible_or_invalid"]
    semantic_pairs = [(str(row["final_classification"]), str(row["llm_classification"])) for row in semantic_cases]
    collapsed_pairs = [(str(row["collapsed_final"]), str(row["collapsed_llm"])) for row in cases]
    collapsed_semantic_pairs = [(str(row["collapsed_final"]), str(row["collapsed_llm"])) for row in semantic_cases]

    full = with_intervals(all_pairs, LABELS, 10)
    semantic = with_intervals(semantic_pairs, LABELS[:-1], 11)
    collapsed = with_intervals(collapsed_pairs, COLLAPSED_LABELS, 12)
    collapsed_semantic = with_intervals(collapsed_semantic_pairs, COLLAPSED_LABELS[:-1], 13)
    summary = {
        "reference": "R1 adjudicated final labels",
        "adjudicated_cases": sum(
            row["adjudication_status"] != "initial_label_retained"
            for row in final.values()
        ),
        "human_label_changes": len(changes),
        "full_90": full,
        "primary_semantic_subset": semantic,
        "collapsed_full_90": collapsed,
        "collapsed_primary_semantic_subset": collapsed_semantic,
        "exact_disagreements_full_90": int(full["n"]) - int(full["matches"]),
        "exact_disagreements_primary_semantic_subset": int(semantic["n"]) - int(semantic["matches"]),
        "model": args.model,
        "human_results_file": str(args.human_path),
        "llm_results_file": str(args.llm_path),
        "pre_adjudication_summary": str(PRELIM_RESULTS / "summary.json"),
    }

    with cases_output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(cases[0]))
        writer.writeheader()
        writer.writerows(cases)
    with changes_output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(changes[0]) if changes else ["review_id"])
        writer.writeheader()
        writer.writerows(changes)

    per_class_rows: list[dict[str, object]] = []
    for scope, bundle in [
        ("final_full_90", full),
        ("final_primary_semantic", semantic),
        ("final_collapsed_full_90", collapsed),
        ("final_collapsed_primary_semantic", collapsed_semantic),
    ]:
        for row in bundle["per_class"]:  # type: ignore[index]
            per_class_rows.append({"scope": scope, **row})
    with per_class_output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(per_class_rows[0]))
        writer.writeheader()
        writer.writerows(per_class_rows)

    write_confusion(confusion_output, all_pairs, LABELS)
    write_confusion(collapsed_confusion_output, collapsed_pairs, COLLAPSED_LABELS)
    summary_output.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    report = f"""# Final adjudicated comparison: H001–H090 ({args.model})

The reference labels are the final R1 decisions after adjudicating 24 initial human–LLM disagreements. The original first-pass human labels remain preserved separately.

| Scope | Exact agreement | Cohen's kappa | Macro-F1 | Disagreements |
|---|---:|---:|---:|---:|
| Primary semantic subset (n={semantic['n']}) | {semantic['matches']}/{semantic['n']} ({float(semantic['accuracy']):.1%}) | {float(semantic['cohen_kappa']):.3f} | {float(semantic['macro_f1']):.3f} | {int(semantic['n']) - int(semantic['matches'])} |
| Full set (n={full['n']}) | {full['matches']}/{full['n']} ({float(full['accuracy']):.1%}) | {float(full['cohen_kappa']):.3f} | {float(full['macro_f1']):.3f} | {int(full['n']) - int(full['matches'])} |
| Collapsed full taxonomy (n={collapsed['n']}) | {collapsed['matches']}/{collapsed['n']} ({float(collapsed['accuracy']):.1%}) | {float(collapsed['cohen_kappa']):.3f} | {float(collapsed['macro_f1']):.3f} | {int(collapsed['n']) - int(collapsed['matches'])} |

R1 changed {len(changes)} of the 24 disputed labels. These final metrics are the appropriate primary comparison for the paper. The pre-adjudication metrics should be reported as a sensitivity analysis, not as the final estimate.
"""
    report_output.write_text(report, encoding="utf-8")
    print(report)
    print(f"Final cases: {cases_output}")
    print(f"Final summary: {summary_output}")
    print(f"Adjudication changes: {changes_output}")


if __name__ == "__main__":
    main()
