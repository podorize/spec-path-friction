"""Post-hoc qualitative audit of the six same-reviewer stable positives."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "results/validation/holdout_v1/luna_comparison/analysis/paired_case_results.csv"
EVIDENCE = ROOT / "data/interim/holdout_longitudinal_evidence_v1_240.jsonl"
OUTPUT = ROOT / "results/validation/holdout_v1/stable_positive_audit"

UNKNOWN = {"ambiguous_reference", "inaccessible_or_invalid"}

AUDIT = {
    "S039": {
        "audit_classification": "confirmed_exists",
        "audit_confidence": "high",
        "audit_finding": "human_not_supported",
        "failure_mode": "module_layout_resolution",
        "decisive_evidence": (
            "The immutable anchor tree contains crates/viewpoint-core/src/context/types/storage/mod.rs. "
            "It is exactly 387 lines and defines StorageState, matching the task's description of "
            "types/storage.rs (387 lines). The literal .rs path is a directory-module shorthand or stale spelling."
        ),
        "evidence_url": (
            "https://github.com/stephenstubbs/viewpoint/blob/"
            "a51f81442bcd6d59aefee962fc3f9ee3a6763bbc/"
            "crates/viewpoint-core/src/context/types/storage/mod.rs"
        ),
    },
    "S010": {
        "audit_classification": "external_repository_reference",
        "audit_confidence": "high",
        "audit_finding": "human_not_supported",
        "failure_mode": "repository_boundary",
        "decisive_evidence": (
            "The task places the follow-up in groundx-studio-harness and says xray_to_extract.py should "
            "delegate to the SDK helper after the groundx-python fix. Absence from groundx-python is therefore expected."
        ),
        "evidence_url": (
            "https://github.com/eyelevelai/groundx-python/blob/"
            "8f56eb14ccd5d2e46d4f36c9444be664e85d5011/"
            "openspec/changes/archive/2026-07-07-generalize-v1-custom-output-reassembly/tasks.md"
        ),
    },
    "S066": {
        "audit_classification": "confirmed_missing_problematic",
        "audit_confidence": "high",
        "audit_finding": "human_supported",
        "failure_mode": "unexplained_missing_prerequisite",
        "decisive_evidence": (
            "The task calls offlineQueue.ts existing logic, requires it to be migrated while preserving web behavior, "
            "and does not mark the file as new. The complete anchor tree has no frontend/src source tree or matching file, "
            "and the supplied evidence gives no lifecycle or repository-boundary explanation."
        ),
        "evidence_url": (
            "https://github.com/ccradle/findABed/blob/"
            "95dc3a66d62393f2fd891ace2eb8330229acd09c/"
            "openspec/changes/capacitor-native-app/tasks.md"
        ),
    },
    "S015": {
        "audit_classification": "expected_absence_move_or_delete",
        "audit_confidence": "high",
        "audit_finding": "human_not_supported",
        "failure_mode": "intentional_deletion",
        "decisive_evidence": (
            "JacksonConfig.java existed before the change and registered JsonNullableJackson3Module. "
            "Commit 06fc0356, immediately before the anchor, explicitly removed that configuration and dependency. "
            "The task itself says to remove the module from the file, so absence at the completed anchor is lifecycle evidence."
        ),
        "evidence_url": (
            "https://github.com/Phunguy65/zero-meeting-system/commit/"
            "06fc0356c10194b9fe362d7e450d46f91b5b8437"
        ),
    },
    "S054": {
        "audit_classification": "confirmed_exists",
        "audit_confidence": "high",
        "audit_finding": "human_not_supported",
        "failure_mode": "near_name_resolution",
        "decisive_evidence": (
            "The anchor tree contains pkg/forgejo/rawhttp_test.go rather than raw_http_test.go. "
            "That 287-line file imports net/http/httptest and defines an httptest.Server helper, exactly matching "
            "the task's cited test pattern. The literal reference has an underscore mismatch, not a missing implementation."
        ),
        "evidence_url": (
            "https://github.com/goern/forgejo-mcp/blob/"
            "7eb8a342346c40f95a9ebd8551e0f52e39469561/pkg/forgejo/rawhttp_test.go"
        ),
    },
    "S020": {
        "audit_classification": "external_repository_reference",
        "audit_confidence": "high",
        "audit_finding": "human_not_supported",
        "failure_mode": "repository_boundary",
        "decisive_evidence": (
            "The anchor repository is liverty-music/specification. The anchor commit says the change was fully implemented "
            "in the frontend repository and cites liverty-music/frontend#253. The src/entities/artist.ts path belongs there."
        ),
        "evidence_url": (
            "https://github.com/liverty-music/specification/commit/"
            "81921e2cc787313309e26044df8a5bacb7ac6e3b"
        ),
    },
}


def state(label: str) -> str:
    if label == "confirmed_missing_problematic":
        return "problematic"
    if label in UNKNOWN:
        return "unknown"
    return "nonproblematic"


def main() -> None:
    frame = pd.read_csv(INPUT, dtype=str, keep_default_na=False)
    selected = frame.loc[
        (frame["stable_decisive_reference"].str.lower() == "true")
        & (frame["round1_state"] == "problematic")
    ].copy()
    if set(selected["review_id"]) != set(AUDIT) or len(selected) != 6:
        raise ValueError("The expected six stable positive cases were not recovered")

    evidence_rows = []
    for line in EVIDENCE.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        if record["review_id"] in AUDIT:
            evidence_rows.append({
                "review_id": record["review_id"],
                "repo_name": record["repo_name"],
                "anchor_sha": record["anchor_sha"],
                "artifact_path": record["artifact_path"],
                "literal_code_path": record["literal_code_path"],
            })
    selected = selected.merge(pd.DataFrame(evidence_rows), on="review_id", validate="one_to_one")

    audit = pd.DataFrame.from_dict(AUDIT, orient="index").rename_axis("review_id").reset_index()
    result = selected.merge(audit, on="review_id", validate="one_to_one")
    result["audit_state"] = result["audit_classification"].map(state)
    result["hybrid_exact_audit_match"] = result["hybrid_classification"] == result["audit_classification"]
    result["luna_only_exact_audit_match"] = result["luna_only_classification"] == result["audit_classification"]
    result["hybrid_state_audit_match"] = result["hybrid_state"] == result["audit_state"]
    result["luna_only_state_audit_match"] = result["luna_only_state"] == result["audit_state"]

    retained = int((result["audit_state"] == "problematic").sum())
    summary = {
        "status": "post_hoc_secondary_audit",
        "human_stable_positive_n": len(result),
        "audit_problematic_n": retained,
        "audit_nonproblematic_n": int((result["audit_state"] == "nonproblematic").sum()),
        "human_positive_retained_fraction": retained / len(result),
        "hybrid_exact_label_matches": int(result["hybrid_exact_audit_match"].sum()),
        "luna_only_exact_label_matches": int(result["luna_only_exact_audit_match"].sum()),
        "hybrid_three_state_matches": int(result["hybrid_state_audit_match"].sum()),
        "luna_only_three_state_matches": int(result["luna_only_state_audit_match"].sum()),
        "hybrid_abstentions": int((result["hybrid_state"] == "unknown").sum()),
        "luna_only_abstentions": int((result["luna_only_state"] == "unknown").sum()),
        "important_limit": (
            "This audit was performed after model outputs were observed and only among human-stable positives. "
            "It must not replace the primary held-out analysis or be interpreted as a recall estimate."
        ),
    }

    columns = [
        "review_id", "repo_name", "anchor_sha", "artifact_path", "literal_code_path", "round1_classification",
        "round1_evidence_note", "round2_classification", "round2_evidence_note",
        "audit_classification", "audit_state", "audit_confidence", "audit_finding",
        "failure_mode", "decisive_evidence", "evidence_url", "hybrid_stage",
        "hybrid_classification", "hybrid_rationale", "luna_only_classification",
        "luna_only_rationale", "hybrid_exact_audit_match", "luna_only_exact_audit_match",
        "hybrid_state_audit_match", "luna_only_state_audit_match",
    ]
    OUTPUT.mkdir(parents=True, exist_ok=True)
    result[columns].sort_values("review_id").to_json(
        OUTPUT / "stable_positive_audit.jsonl",
        orient="records",
        lines=True,
        force_ascii=False,
    )
    (OUTPUT / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    rows = []
    for record in result.sort_values("review_id").to_dict("records"):
        rows.append(
            f"| {record['review_id']} | {record['audit_classification']} | "
            f"{record['audit_finding']} | {record['failure_mode']} |"
        )
    table_rows = "\n".join(rows)
    report = f"""# Auditoria pós-hoc dos seis positivos humanos estáveis

## Resultado

Somente **{retained} dos 6** casos permaneceu `confirmed_missing_problematic` após inspeção da árvore completa do commit, do contexto da tarefa, do histórico do caminho e de caminhos semanticamente correspondentes. Cinco decisões humanas repetidas não foram sustentadas pela evidência ampliada.

| Caso | Classificação da auditoria | Avaliação do rótulo humano | Mecanismo |
| --- | --- | --- | --- |
{table_rows}

## Julgamentos individuais

### S039 — `confirmed_exists`

O caminho literal `types/storage.rs` não existe, mas o commit contém `crates/viewpoint-core/src/context/types/storage/mod.rs`. O arquivo tem exatamente 387 linhas e define `StorageState`, coincidindo com a descrição da tarefa. Trata-se de resolução de módulo Rust, não de implementação ausente. O humano e os dois LLMs foram excessivamente literais; a auditoria favorece `confirmed_exists` por caminho correspondente.

### S010 — `external_repository_reference`

A seção se chama Consumer Handoff e atribui explicitamente o follow-up ao `groundx-studio-harness`. O arquivo `xray_to_extract.py` não deveria estar em `groundx-python`. O humano confundiu a ausência local com defeito. O Luna-only identificou corretamente a fronteira de repositório.

### S066 — `confirmed_missing_problematic`

A tarefa descreve `offlineQueue.ts` como lógica existente, exige migração e preservação de comportamento e não marca o arquivo como novo. A árvore completa do commit não contém sequer o diretório de código `frontend/src`, nem há evidência de criação, remoção, mudança ou outro repositório. Este é o único dos seis casos em que o julgamento humano positivo permanece sustentado; ambos os pipelines também o classificaram corretamente.

### S015 — `expected_absence_move_or_delete`

O arquivo existia antes e registrava `JsonNullableJackson3Module`. O commit de implementação imediatamente anterior ao anchor removeu a configuração e a dependência. A tarefa também manda remover esse módulo. A ausência é consequência esperada da mudança. O humano ignorou a evidência longitudinal; a regra e o Luna-only acertaram.

### S054 — `confirmed_exists`

O literal usa `raw_http_test.go`, mas a árvore contém `pkg/forgejo/rawhttp_test.go`. O arquivo tem 287 linhas, importa `net/http/httptest` e define um helper baseado em `httptest.Server`, exatamente o padrão citado pela tarefa. O caso expõe uma falha do resolvedor de caminhos: ele procurou apenas o basename exato e não reconheceu a variante sem underscore.

### S020 — `external_repository_reference`

O anchor está no repositório `liverty-music/specification`, e a mensagem do commit afirma que a implementação ocorreu no repositório frontend, com referência a `liverty-music/frontend#253`. A ausência local de `src/entities/artist.ts` é esperada. O Luna-only acertou; o rótulo humano não é sustentado.

## Efeito interpretativo

- A concordância humana test-retest mostrou consistência, não validade. O mesmo viés literal foi repetido nas duas rodadas.
- O resultado original de 1 acerto em 6 positivos não deve mais ser interpretado diretamente como recall de 16,7%. Cinco dos seis denominadores eram falsos positivos humanos segundo a auditoria ampliada.
- Nos seis casos auditados, os dois pipelines reconheceram o único caso que permaneceu problemático, classificaram corretamente o estado de outros três e se abstiveram nos dois casos de resolução de caminho.
- Esse recorte não produz uma nova estimativa de recall: ele foi selecionado por rótulo humano positivo, auditado após observar as saídas dos modelos e contém apenas um positivo confirmado.

## Implicação para o pipeline

O próximo gargalo técnico não é apenas o prompt. A coleta deve resolver caminhos equivalentes antes do julgamento semântico, incluindo módulos `path.rs` versus `path/mod.rs`, pequenas variações de nome e referências explícitas a outros repositórios. Depois dessa correção, deve-se auditar uma amostra de negativos e abstenções. Sem isso, ainda não sabemos quantos positivos verdadeiros foram escondidos por erros humanos ou pelo próprio pipeline.
"""
    (OUTPUT / "STABLE_POSITIVE_AUDIT.md").write_text(report, encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
