"""Create a new balanced, blinded English sample of 90 cases for final validation.

Stratification:
- 30 completed + missing (task_done = 1, exists_at_anchor = 0)
- 30 open + missing (task_done = 0, exists_at_anchor = 0)
- 30 completed + exists (task_done = 1, exists_at_anchor = 1) [Control group]

Excludes all references used in all prior validation rounds.
Ensures 1 reference per repository, English language >= 0.90, and creates both
CSV, private key, LLM judge input JSONL, and a formatted Excel workbook with dropdowns.
"""

from __future__ import annotations

import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import duckdb
import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.worksheet.datavalidation import DataValidation
import pandas as pd
from langdetect import DetectorFactory, detect_langs

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW = PROJECT_ROOT / "data" / "raw"
INTERIM = PROJECT_ROOT / "data" / "interim"
REFS_PATH = RAW / "openspec_code_refs.parquet"
ARTIFACTS_PATH = RAW / "openspec_artifact_files.parquet"

REVIEW_CSV = INTERIM / "validation_final_90_en.csv"
KEY_CSV = INTERIM / "validation_final_90_en_key.csv"
MANIFEST_JSON = INTERIM / "validation_final_90_en_manifest.json"
REVIEW_XLSX = INTERIM / "validation_final_90_en.xlsx"
LLM_INPUT_JSONL = INTERIM / "llm_judge_inputs_final_90.jsonl"

SEED = 20261020
N_PER_GROUP = 30
N_CANDIDATES_PER_GROUP = 2_500
MAX_CONTEXT_CHARS = 8_000

GROUP_ORDER = [
    "completed + missing",
    "open + missing",
    "completed + exists",
]

FOREIGN_SCRIPT = re.compile(
    r"[\u0400-\u052f\u0590-\u08ff\u0900-\u0e7f\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]"
)

TAXONOMY = [
    ("confirmed_exists", "O arquivo referenciado local existe no commit verificável."),
    ("confirmed_missing_problematic", "O caminho local deveria existir no contexto, mas está ausente sem explicação válida de ciclo de vida ou outro repositório."),
    ("expected_absence_create", "A tarefa pede explicitamente criar, introduzir ou implementar um novo arquivo."),
    ("expected_absence_move_or_delete", "A tarefa ou commit move, renomeia, substitui, depreca ou remove o arquivo."),
    ("external_repository_reference", "A evidência identifica explicitamente que o arquivo pertence a outro repositório."),
    ("non_file_reference", "O texto denota glob, padrão, diretório, biblioteca, URL, extensão ou placeholder documental."),
    ("ambiguous_reference", "O contexto disponível é insuficiente para decidir com segurança entre as opções."),
    ("inaccessible_or_invalid", "O commit, repositório ou artefato não pode ser acessado ou é inválido."),
]

DetectorFactory.seed = 0


def github_blob_url(repo_name: str, sha: str, path: str) -> str:
    return f"https://github.com/{repo_name}/blob/{sha}/{quote(path, safe='/')}"


def build_task_context(content: str, code_path: str, max_chars: int = MAX_CONTEXT_CHARS) -> tuple[str, bool]:
    content = str(content or "")
    code_path = str(code_path or "")
    if len(content) <= max_chars:
        return content, False

    positions: list[int] = []
    start = 0
    while code_path and len(positions) < 8:
        pos = content.find(code_path, start)
        if pos < 0:
            break
        positions.append(pos)
        start = pos + max(1, len(code_path))

    if not positions:
        return content[:max_chars], True

    radius = max(700, min(1500, max_chars // (2 * len(positions))))
    windows: list[tuple[int, int]] = []
    for pos in positions:
        left_hint = max(0, pos - radius)
        right_hint = min(len(content), pos + len(code_path) + radius)
        left = content.rfind("\n", 0, left_hint)
        right = content.find("\n", right_hint)
        left = 0 if left < 0 else left + 1
        right = len(content) if right < 0 else right
        if windows and left <= windows[-1][1]:
            windows[-1] = (windows[-1][0], max(windows[-1][1], right))
        else:
            windows.append((left, right))

    chunks: list[str] = []
    used = 0
    for idx, (left, right) in enumerate(windows, start=1):
        prefix = f"[Context around occurrence {idx}]\n"
        remaining = max_chars - used - len(prefix)
        if remaining <= 0:
            break
        chunk = content[left:right][:remaining]
        chunks.append(prefix + chunk)
        used += len(prefix) + len(chunk) + 2
    return "\n\n".join(chunks)[:max_chars], True


def english_detection(text: str) -> tuple[str, float, bool]:
    DetectorFactory.seed = 0
    foreign = bool(FOREIGN_SCRIPT.search(text))
    try:
        top = detect_langs(text)[0]
        return top.lang, float(top.prob), foreign
    except Exception:
        return "und", 0.0, foreign


def load_excluded_ids() -> tuple[set[int], dict[str, int]]:
    excluded: set[int] = set()
    sources: dict[str, int] = {}
    for path in sorted(INTERIM.glob("*.csv")):
        try:
            with path.open(newline="", encoding="utf-8-sig") as handle:
                header = next(csv.reader(handle), [])
                if "id" not in header:
                    continue
            df = pd.read_csv(path, usecols=["id"])
            ids = set(pd.to_numeric(df["id"], errors="coerce").dropna().astype(int).tolist())
            if ids:
                sources[path.name] = len(ids)
                excluded.update(ids)
        except Exception:
            pass
    return excluded, sources


def create_excel_workbook(df: pd.DataFrame, output_path: Path) -> None:
    wb = openpyxl.Workbook()
    ws_review = wb.active
    ws_review.title = "Review"

    # Guide sheet
    ws_guide = wb.create_sheet(title="Guide")
    ws_guide.views.sheetView[0].showGridLines = True
    guide_headers = ["Categoria", "Definição e Regra de Decisão"]
    ws_guide.append(guide_headers)
    for cat, desc in TAXONOMY:
        ws_guide.append([cat, desc])

    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    guide_header_fill = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
    for col_idx in [1, 2]:
        cell = ws_guide.cell(row=1, column=col_idx)
        cell.font = header_font
        cell.fill = guide_header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center")
    ws_guide.column_dimensions["A"].width = 35
    ws_guide.column_dimensions["B"].width = 90
    for row_idx in range(2, len(TAXONOMY) + 2):
        ws_guide.cell(row=row_idx, column=1).font = Font(name="Calibri", size=10, bold=True)
        ws_guide.cell(row=row_idx, column=2).font = Font(name="Calibri", size=10)
        ws_guide.cell(row=row_idx, column=2).alignment = Alignment(wrap_text=True, vertical="center")

    # Review sheet
    ws_review.views.sheetView[0].showGridLines = True
    headers = [
        "Review ID",
        "Repositório",
        "Commit",
        "Artefato da Tarefa",
        "Caminho Literal",
        "Caminho Resolvido",
        "URL da Tarefa",
        "URL do Caminho Literal",
        "Caminho no Commit",
        "URL do Caminho no Commit",
        "Contexto da Tarefa",
        "Revisor",
        "Classificação",
        "Nota de Evidência (obrigatório)",
        "Problema de Acesso",
    ]
    ws_review.append(headers)

    review_header_fill = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
    input_header_fill = PatternFill(start_color="2CA02C", end_color="2CA02C", fill_type="solid")
    thin_border = Border(
        left=Side(style="thin", color="D9D9D9"),
        right=Side(style="thin", color="D9D9D9"),
        top=Side(style="thin", color="D9D9D9"),
        bottom=Side(style="thin", color="D9D9D9"),
    )

    for col_idx, h in enumerate(headers, start=1):
        cell = ws_review.cell(row=1, column=col_idx)
        cell.font = header_font
        cell.fill = input_header_fill if col_idx in [12, 13, 14, 15] else review_header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    row_data_cols = [
        "review_id",
        "repo_name",
        "anchor_sha",
        "artifact_path",
        "code_path",
        "resolved_path",
        "task_url",
        "literal_path_url",
        "anchor_path",
        "anchor_path_url",
        "task_context",
    ]

    highlight_fill = PatternFill(start_color="FCF8E3", end_color="FCF8E3", fill_type="solid")

    for _, row in df.iterrows():
        row_vals = [row.get(col, "") for col in row_data_cols]
        row_vals.extend(["", "", "", ""])  # Revisor, Classificação, Nota, Problema
        ws_review.append(row_vals)

    # Style data rows
    for row_idx in range(2, len(df) + 2):
        ws_review.row_dimensions[row_idx].height = 45
        for col_idx in range(1, len(headers) + 1):
            cell = ws_review.cell(row=row_idx, column=col_idx)
            cell.border = thin_border
            if col_idx in [13, 14]:  # Classification, Note
                cell.fill = highlight_fill
            if col_idx in [1, 2, 3]:
                cell.alignment = Alignment(horizontal="center", vertical="center")
            elif col_idx in [7, 8, 10]:
                cell.alignment = Alignment(horizontal="left", vertical="center")
                cell.font = Font(name="Calibri", size=9, color="0000FF", underline="single")
            elif col_idx in [11, 14]:
                cell.alignment = Alignment(horizontal="left", vertical="top", wrap_text=True)
            else:
                cell.alignment = Alignment(horizontal="left", vertical="center")

    # Column widths
    col_widths = {
        "A": 12, "B": 28, "C": 14, "D": 38, "E": 32, "F": 32,
        "G": 22, "H": 22, "I": 32, "J": 22, "K": 55, "L": 14,
        "M": 32, "N": 40, "O": 22,
    }
    for col_letter, width in col_widths.items():
        ws_review.column_dimensions[col_letter].width = width

    # Data validation dropdown for Classificação (Col M)
    cat_formula = '"' + ",".join([c[0] for c in TAXONOMY]) + '"'
    dv = DataValidation(type="list", formula1=cat_formula, allow_blank=True)
    dv.error = "Por favor, selecione uma categoria válida da taxonomia."
    dv.errorTitle = "Entrada inválida"
    dv.prompt = "Selecione uma das 8 categorias da taxonomia semântica."
    dv.promptTitle = "Classificação"
    ws_review.add_data_validation(dv)
    dv.add(f"M2:M{len(df) + 1}")

    # Freeze panes at cell D2 so Review ID, Repo, and Commit remain visible
    ws_review.freeze_panes = "D2"

    wb.save(output_path)


def main() -> None:
    print("Loading excluded IDs from prior pilots and holdouts...")
    excluded_ids, exclusion_sources = load_excluded_ids()
    print(f"Total excluded unique IDs: {len(excluded_ids)} from {len(exclusion_sources)} sources.")

    excluded_frame = pd.DataFrame({"id": sorted(excluded_ids)}, dtype="int64")

    con = duckdb.connect()
    con.register("excluded_ids", excluded_frame)

    query = """
        WITH eligible AS (
            SELECT
                r.id,
                r.repo_name,
                r.artifact_path,
                r.code_path,
                r.resolved_path,
                r.task_done,
                r.anchor_sha,
                r.exists_at_anchor,
                CASE
                    WHEN r.task_done = 1 AND r.exists_at_anchor = 0
                        THEN 'completed + missing'
                    WHEN r.task_done = 0 AND r.exists_at_anchor = 0
                        THEN 'open + missing'
                    WHEN r.task_done = 1 AND r.exists_at_anchor = 1
                        THEN 'completed + exists'
                END AS validation_group
            FROM read_parquet(?) AS r
            LEFT JOIN excluded_ids AS x USING (id)
            WHERE x.id IS NULL
              AND r.repo_name IS NOT NULL
              AND r.anchor_sha IS NOT NULL
              AND r.artifact_path IS NOT NULL
              AND r.code_path IS NOT NULL
              AND trim(r.code_path) <> ''
              AND (
                  (r.task_done = 1 AND r.exists_at_anchor = 0)
                  OR (r.task_done = 0 AND r.exists_at_anchor = 0)
                  OR (
                      r.task_done = 1
                      AND r.exists_at_anchor = 1
                      AND r.resolved_path IS NOT NULL
                      AND trim(r.resolved_path) <> ''
                  )
              )
        ), ranked AS (
            SELECT
                *,
                ROW_NUMBER() OVER (
                    PARTITION BY validation_group
                    ORDER BY hash(id, ?)
                ) AS candidate_rank
            FROM eligible
        )
        SELECT ranked.*, a.content
        FROM ranked
        JOIN read_parquet(?) AS a
          ON ranked.repo_name = a.repo_name
         AND ranked.artifact_path = a.file_path
        WHERE candidate_rank <= ?
        ORDER BY validation_group, candidate_rank
    """

    print("Querying eligible candidate records from parquet files...")
    candidates = con.execute(
        query,
        [str(REFS_PATH), SEED, str(ARTIFACTS_PATH), N_CANDIDATES_PER_GROUP],
    ).fetchdf()
    print(f"Retrieved {len(candidates)} candidate rows across strata.")

    print("Extracting task context around references...")
    contexts = [
        build_task_context(content, code_path)
        for content, code_path in zip(candidates["content"], candidates["code_path"], strict=True)
    ]
    candidates["task_context"] = [context for context, _ in contexts]
    candidates["context_truncated"] = [truncated for _, truncated in contexts]

    print("Running English language detection and script validation...")
    lang_data = [english_detection(text) for text in candidates["task_context"]]
    candidates[["detected_language", "language_probability", "has_foreign_script"]] = pd.DataFrame(
        lang_data, index=candidates.index
    )

    filtered = candidates.loc[
        (candidates["detected_language"] == "en")
        & (candidates["language_probability"] >= 0.90)
        & ~candidates["has_foreign_script"]
    ].copy()
    print(f"Filtered to {len(filtered)} high-confidence English candidates.")

    selected_parts: list[pd.DataFrame] = []
    used_repositories: set[str] = set()

    for group in GROUP_ORDER:
        group_rows = filtered.loc[filtered["validation_group"] == group]
        chosen_indices: list[int] = []
        for idx, row in group_rows.iterrows():
            repo = str(row["repo_name"])
            if repo in used_repositories:
                continue
            chosen_indices.append(idx)
            used_repositories.add(repo)
            if len(chosen_indices) == N_PER_GROUP:
                break
        if len(chosen_indices) != N_PER_GROUP:
            raise ValueError(f"Only {len(chosen_indices)} unique-repository English cases for group {group}")
        selected_parts.append(filtered.loc[chosen_indices])

    selected = pd.concat(selected_parts, ignore_index=True)
    selected["sample_rank_within_group"] = selected.groupby("validation_group", sort=False).cumcount() + 1
    selected = selected.sample(frac=1, random_state=SEED).reset_index(drop=True)
    selected.insert(0, "review_id", [f"F{num:03d}" for num in range(1, len(selected) + 1)])

    selected["task_url"] = selected.apply(
        lambda r: github_blob_url(str(r["repo_name"]), str(r["anchor_sha"]), str(r["artifact_path"])),
        axis=1,
    )
    selected["literal_path_url"] = selected.apply(
        lambda r: github_blob_url(str(r["repo_name"]), str(r["anchor_sha"]), str(r["code_path"])),
        axis=1,
    )
    selected["anchor_path"] = selected["resolved_path"].fillna(selected["code_path"])
    selected["anchor_path_url"] = selected.apply(
        lambda r: github_blob_url(str(r["repo_name"]), str(r["anchor_sha"]), str(r["anchor_path"])),
        axis=1,
    )

    # Prepare blinded review CSV
    review_cols = [
        "review_id",
        "repo_name",
        "anchor_sha",
        "artifact_path",
        "code_path",
        "resolved_path",
        "task_url",
        "literal_path_url",
        "anchor_path",
        "anchor_path_url",
        "task_context",
        "reviewer_id",
        "manual_classification",
        "evidence_note",
        "access_issue",
    ]
    blinded_df = selected.copy()
    for col in ["reviewer_id", "manual_classification", "evidence_note", "access_issue"]:
        blinded_df[col] = ""

    blinded_df[review_cols].to_csv(REVIEW_CSV, index=False, quoting=csv.QUOTE_MINIMAL)
    print(f"Saved blinded review CSV: {REVIEW_CSV}")

    # Prepare private key CSV
    key_cols = [
        "review_id",
        "id",
        "validation_group",
        "task_done",
        "exists_at_anchor",
        "repo_name",
        "artifact_path",
        "code_path",
        "resolved_path",
        "candidate_rank",
        "sample_rank_within_group",
        "detected_language",
        "language_probability",
        "has_foreign_script",
        "context_truncated",
    ]
    selected[key_cols].to_csv(KEY_CSV, index=False)
    print(f"Saved private key CSV: {KEY_CSV}")

    # Create formatted Excel workbook
    create_excel_workbook(blinded_df, REVIEW_XLSX)
    print(f"Saved blinded review Excel workbook: {REVIEW_XLSX}")

    # Prepare LLM judge inputs JSONL (unleaked, blinded)
    llm_records = []
    for _, row in selected.iterrows():
        rec = {
            "review_id": row["review_id"],
            "repo_name": row["repo_name"],
            "anchor_sha": row["anchor_sha"],
            "artifact_path": row["artifact_path"],
            "code_path": row["code_path"],
            "resolved_path": row["resolved_path"] if pd.notna(row["resolved_path"]) else None,
            "exists_at_anchor": int(row["exists_at_anchor"]),
            "task_context": row["task_context"],
        }
        llm_records.append(rec)

    with LLM_INPUT_JSONL.open("w", encoding="utf-8") as f:
        for rec in llm_records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"Saved LLM input records: {LLM_INPUT_JSONL}")

    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "seed": SEED,
        "n_total": len(selected),
        "group_counts": selected["validation_group"].value_counts().to_dict(),
        "unique_repos": int(selected["repo_name"].nunique()),
        "output_files": {
            "review_csv": str(REVIEW_CSV.relative_to(PROJECT_ROOT)),
            "key_csv": str(KEY_CSV.relative_to(PROJECT_ROOT)),
            "review_xlsx": str(REVIEW_XLSX.relative_to(PROJECT_ROOT)),
            "llm_input_jsonl": str(LLM_INPUT_JSONL.relative_to(PROJECT_ROOT)),
        },
        "exclusions_count": len(excluded_ids),
    }
    with MANIFEST_JSON.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    print(f"Saved manifest: {MANIFEST_JSON}")
    print("\nSummary:")
    print(f"Total cases: {len(selected)}")
    print(f"By stratum: {selected['validation_group'].value_counts().to_dict()}")
    print(f"Unique repositories: {selected['repo_name'].nunique()}/90")


if __name__ == "__main__":
    main()
