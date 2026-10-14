"""Estimate semantic outcomes among unresolved references with stratification.

The 90-case validation sample was balanced by design, so its raw label
frequencies are not population estimates. This script reweights the two
unresolved strata by their corpus sizes and reports conservative and
inaccessible-excluded sensitivity analyses.
"""

from __future__ import annotations

import csv
import json
import random
from collections import Counter
from pathlib import Path

import duckdb


PROJECT_ROOT = Path(__file__).resolve().parents[1]
INTERIM = PROJECT_ROOT / "data" / "interim"
RAW = PROJECT_ROOT / "data" / "raw"
RESULTS = PROJECT_ROOT / "results" / "validation" / "human_90_adjudicated"

FINAL_PATH = INTERIM / "validation_human_90_R1_adjudicated.csv"
KEY_PATH = INTERIM / "validation_human_fresh_90_en_key.csv"
REFS_PATH = RAW / "openspec_code_refs.parquet"
SUMMARY_PATH = RESULTS / "prevalence_summary.json"
STRATA_PATH = RESULTS / "stratum_prevalence.csv"
REPORT_PATH = RESULTS / "PREVALENCE_REPORT.md"

LABELS = [
    "confirmed_exists",
    "confirmed_missing_problematic",
    "expected_absence_create",
    "expected_absence_move_or_delete",
    "non_file_reference",
    "ambiguous_reference",
    "inaccessible_or_invalid",
]
MISSING_GROUPS = ["completed + missing", "open + missing"]
SEED = 20261010
BOOTSTRAP_REPLICATES = 10_000


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def wilson(successes: int, total: int) -> tuple[float, float]:
    if total == 0:
        return (0.0, 0.0)
    z = 1.959963984540054
    p = successes / total
    denominator = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denominator
    half = z * ((p * (1 - p) / total + z * z / (4 * total * total)) ** 0.5) / denominator
    return (center - half, center + half)


def percentile(values: list[float], p: float) -> float:
    ordered = sorted(values)
    position = p * (len(ordered) - 1)
    low, high = int(position), int(position + 0.999999999)
    if low == high:
        return ordered[low]
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def main() -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    final = {row["review_id"]: row for row in read_csv(FINAL_PATH)}
    key = {row["review_id"]: row for row in read_csv(KEY_PATH)}
    if len(final) != 90 or set(final) != set(key):
        raise ValueError("Final adjudication and key must contain the same 90 cases")

    population_rows = duckdb.sql(
        f"""
        SELECT
          CASE
            WHEN task_done = 1 AND exists_at_anchor = 1 THEN 'completed + exists'
            WHEN task_done = 1 AND exists_at_anchor = 0 THEN 'completed + missing'
            WHEN task_done = 0 AND exists_at_anchor = 1 THEN 'open + exists'
            WHEN task_done = 0 AND exists_at_anchor = 0 THEN 'open + missing'
          END AS validation_group,
          COUNT(*) AS population_references
        FROM read_parquet('{REFS_PATH}')
        WHERE task_done IN (0, 1) AND exists_at_anchor IN (0, 1)
        GROUP BY 1
        ORDER BY 1
        """
    ).fetchall()
    population = {str(group): int(count) for group, count in population_rows}

    sample_by_group: dict[str, list[dict[str, str]]] = {group: [] for group in MISSING_GROUPS}
    for review_id, row in final.items():
        group = key[review_id]["validation_group"]
        if group in sample_by_group:
            sample_by_group[group].append(row | {"review_id": review_id})
    if any(len(rows) != 30 for rows in sample_by_group.values()):
        raise ValueError({group: len(rows) for group, rows in sample_by_group.items()})

    strata: list[dict[str, object]] = []
    for group in MISSING_GROUPS:
        rows = sample_by_group[group]
        counts = Counter(row["final_classification"] for row in rows)
        problematic = counts["confirmed_missing_problematic"]
        inaccessible = counts["inaccessible_or_invalid"]
        known_total = len(rows) - inaccessible
        known_rate = problematic / known_total if known_total else 0.0
        lower_rate = problematic / len(rows)
        strata.append(
            {
                "validation_group": group,
                "sample_n": len(rows),
                "population_n": population[group],
                "problematic_n": problematic,
                "inaccessible_n": inaccessible,
                "problematic_rate_conservative": lower_rate,
                "problematic_rate_known_only": known_rate,
                "conservative_wilson_95_low": wilson(problematic, len(rows))[0],
                "conservative_wilson_95_high": wilson(problematic, len(rows))[1],
                "known_only_wilson_95_low": wilson(problematic, known_total)[0] if known_total else 0.0,
                "known_only_wilson_95_high": wilson(problematic, known_total)[1] if known_total else 0.0,
                "label_counts": dict(sorted(counts.items())),
            }
        )

    total_population = sum(int(row["population_n"]) for row in strata)
    conservative_weighted = sum(
        int(row["population_n"]) * float(row["problematic_rate_conservative"])
        for row in strata
    ) / total_population
    known_only_weighted = sum(
        int(row["population_n"]) * float(row["problematic_rate_known_only"])
        for row in strata
    ) / total_population

    rng = random.Random(SEED)
    conservative_bootstrap: list[float] = []
    known_only_bootstrap: list[float] = []
    for _ in range(BOOTSTRAP_REPLICATES):
        conservative_numerator = 0.0
        known_numerator = 0.0
        for row in strata:
            group = str(row["validation_group"])
            rows = sample_by_group[group]
            draw = [rows[rng.randrange(len(rows))] for _ in rows]
            problematic = sum(item["final_classification"] == "confirmed_missing_problematic" for item in draw)
            inaccessible = sum(item["final_classification"] == "inaccessible_or_invalid" for item in draw)
            conservative_rate = problematic / len(draw)
            known_rate = problematic / (len(draw) - inaccessible) if len(draw) != inaccessible else 0.0
            conservative_numerator += int(row["population_n"]) * conservative_rate
            known_numerator += int(row["population_n"]) * known_rate
        conservative_bootstrap.append(conservative_numerator / total_population)
        known_only_bootstrap.append(known_numerator / total_population)

    summary = {
        "estimand": "confirmed_missing_problematic among literal unresolved references",
        "population_source": "openspec_code_refs.parquet, task_done in {0,1}, exists_at_anchor in {0,1}",
        "population_strata": population,
        "validation_sample": "90 English cases, 30 per private stratum; only the two unresolved strata enter this prevalence estimate",
        "strata": strata,
        "conservative_treat_inaccessible_as_non_problematic": {
            "weighted_rate": conservative_weighted,
            "bootstrap_95_percentile": [percentile(conservative_bootstrap, 0.025), percentile(conservative_bootstrap, 0.975)],
        },
        "known_only_exclude_inaccessible_from_stratum_denominators": {
            "weighted_rate": known_only_weighted,
            "bootstrap_95_percentile": [percentile(known_only_bootstrap, 0.025), percentile(known_only_bootstrap, 0.975)],
        },
        "bootstrap_seed": SEED,
        "bootstrap_replicates": BOOTSTRAP_REPLICATES,
        "interpretation": "Exploratory stratified estimate, not a population gold standard; one human reviewer and 30 cases per stratum limit precision.",
    }
    SUMMARY_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    with STRATA_PATH.open("w", newline="", encoding="utf-8") as handle:
        fieldnames = [key for key in strata[0] if key != "label_counts"]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows({key: row[key] for key in fieldnames} for row in strata)

    report = f"""# Stratified semantic prevalence estimate

The 90-case validation sample was balanced at 30 cases per stratum. Therefore, the raw proportion of `confirmed_missing_problematic` labels is not a corpus estimate. This analysis reweights the two unresolved strata by their population sizes in `openspec_code_refs.parquet`.

| Stratum | Population references | Sample | Problematic | Conservative rate | Known-only rate |
|---|---:|---:|---:|---:|---:|
"""
    for row in strata:
        report += f"| {row['validation_group']} | {row['population_n']:,} | {row['sample_n']} | {row['problematic_n']} | {float(row['problematic_rate_conservative']):.1%} | {float(row['problematic_rate_known_only']):.1%} |\n"
    report += f"""
## Weighted estimate

- Conservative treatment, counting inaccessible cases as non-problematic: **{conservative_weighted:.1%}** (bootstrap 95% interval {summary['conservative_treat_inaccessible_as_non_problematic']['bootstrap_95_percentile'][0]:.1%}–{summary['conservative_treat_inaccessible_as_non_problematic']['bootstrap_95_percentile'][1]:.1%}).
- Known-only sensitivity, excluding inaccessible cases from the stratum denominator: **{known_only_weighted:.1%}** (bootstrap 95% interval {summary['known_only_exclude_inaccessible_from_stratum_denominators']['bootstrap_95_percentile'][0]:.1%}–{summary['known_only_exclude_inaccessible_from_stratum_denominators']['bootstrap_95_percentile'][1]:.1%}).

This estimate is exploratory. It is based on one human reviewer, 30 sampled cases per stratum, and an English-only validation sample. It should be presented as calibrated evidence about the meaning of literal non-resolution, not as a definitive gold-standard prevalence for the entire SpecMine corpus.
"""
    REPORT_PATH.write_text(report, encoding="utf-8")
    print(report)
    print(f"Summary: {SUMMARY_PATH}")


if __name__ == "__main__":
    main()
