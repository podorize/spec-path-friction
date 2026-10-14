import fs from "node:fs/promises";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const args = process.argv.slice(2);
const argValue = (name, fallback) => {
  const index = args.indexOf(name);
  return index >= 0 && args[index + 1] ? args[index + 1] : fallback;
};
const inputPath = argValue("--input", "data/interim/validation_human_blinded_confirmatory_en.csv");
const outputPath = argValue("--output", "data/interim/validation_human_blinded_confirmatory_en.xlsx");
const previewPath = argValue("--preview", "data/interim/validation_human_blinded_confirmatory_en_preview.png");
const guidePreviewPath = argValue("--guide-preview", previewPath.replace(/\.png$/i, "_guide.png"));
const language = argValue("--language", "pt");
const english = language.toLowerCase().startsWith("en");
const categories = [
  ["confirmed_exists", english
    ? "The referenced repository file exists at the indicated commit."
    : "O arquivo referenciado existe no commit indicado."],
  ["confirmed_missing_problematic", english
    ? "The context expects an already-existing repository file, but the file is absent."
    : "A tarefa requer o arquivo, mas ele está ausente."],
  ["expected_absence_create", english
    ? "The task explicitly instructs the developer to create the referenced file."
    : "A tarefa pede explicitamente a criação de novo arquivo."],
  ["expected_absence_move_or_delete", english
    ? "The task moves, renames, replaces, or deletes the referenced path."
    : "O caminho é movido, renomeado, substituído ou removido."],
  ["external_repository_reference", english
    ? "The reference identifies a file that affirmative evidence places in another repository."
    : "A evidência identifica o arquivo como pertencente a outro repositório."],
  ["non_file_reference", english
    ? "The text denotes a pattern, directory, external resource, library, or another non-unique repository file reference."
    : "O texto não designa um arquivo único do repositório."],
  ["ambiguous_reference", english
    ? "The available context is insufficient to determine the reference semantics safely."
    : "O contexto não permite decidir com segurança."],
  ["inaccessible_or_invalid", english
    ? "The repository, commit, task artifact, or other necessary evidence cannot be accessed or is invalid."
    : "O commit ou evidência necessária não está acessível."],
];

const csv = await fs.readFile(inputPath, "utf8");
const workbook = await Workbook.fromCSV(csv, { sheetName: "Review" });
const review = workbook.worksheets.getItem("Review");
const rowCount = review.getUsedRange(true).values.length;

review.getRange("A1:O1").values = [[
  "Review ID", english ? "Repository" : "Repositório", "Commit",
  english ? "Task artifact" : "Artefato da tarefa",
  english ? "Literal path" : "Caminho literal",
  english ? "Resolved path" : "Caminho resolvido",
  english ? "Task URL" : "URL da tarefa",
  english ? "Literal path URL" : "URL do caminho literal",
  english ? "Path at commit" : "Caminho no commit",
  english ? "Path-at-commit URL" : "URL do caminho no commit",
  english ? "Task context" : "Contexto da tarefa",
  english ? "Reviewer" : "Revisor",
  english ? "Classification" : "Classificação",
  english ? "Evidence note (required)" : "Nota de evidência",
  english ? "Access issue" : "Problema de acesso",
]];

review.showGridLines = false;
review.freezePanes.freezeRows(1);
review.freezePanes.freezeColumns(2);
review.getRange(`A1:O${rowCount}`).format.font = { name: "Arial", size: 10, color: "#1F2937" };
review.getRange("A1:O1").format = {
  fill: "#1F4E78",
  font: { name: "Arial", size: 10, bold: true, color: "#FFFFFF" },
  horizontalAlignment: "center",
  verticalAlignment: "center",
  wrapText: true,
  borders: { preset: "outside", style: "thin", color: "#1F4E78" },
};
review.getRange(`A2:O${rowCount}`).format.verticalAlignment = "top";
review.getRange(`D2:F${rowCount}`).format.wrapText = true;
review.getRange(`K2:O${rowCount}`).format.wrapText = true;
review.getRange(`L2:O${rowCount}`).format.fill = "#FFF2CC";
review.getRange(`A2:O${rowCount}`).format.borders = { preset: "inside", style: "thin", color: "#E5E7EB" };
review.getRange(`A2:O${rowCount}`).format.rowHeight = 72;
review.getRange("A:A").format.columnWidth = 12;
review.getRange("B:B").format.columnWidth = 30;
review.getRange("C:C").format.columnWidth = 14;
review.getRange("D:D").format.columnWidth = 48;
review.getRange("E:F").format.columnWidth = 34;
review.getRange("G:J").format.columnWidth = 28;
review.getRange("K:K").format.columnWidth = 84;
review.getRange("L:L").format.columnWidth = 18;
review.getRange("M:M").format.columnWidth = 36;
review.getRange("N:O").format.columnWidth = 52;
review.dataValidations.add({
  range: `M2:M${rowCount}`,
  rule: { type: "list", values: categories.map(([label]) => label) },
});

const guide = workbook.worksheets.add("Guide");
guide.showGridLines = false;
guide.getRange("A1:B1").merge();
guide.getRange("A1").values = [[english
  ? "Independent human review of OpenSpec code references"
  : "Revisão humana de referências OpenSpec"]];
guide.getRange("A1").format = {
  font: { name: "Arial", size: 14, bold: true, color: "#1F2937" },
  verticalAlignment: "center",
};
guide.getRange("A3:B3").values = [[english ? "Review procedure" : "Como revisar", ""]];
guide.getRange("A4:A12").values = english ? [
  ["0. This is a blind review. Do not consult an LLM or any previous classification."],
  ["1. Open the Task URL and read the full task. The workbook context may be truncated for very long tasks."],
  ["2. First confirm that the repository and commit are accessible."],
  ["3. Open the Path-at-commit URL. A 404 means the path is absent only when the repository and commit are accessible."],
  ["4. Interpret the path in the task context. A missing path is not automatically problematic."],
  ["5. Do not decide from the checkbox alone. Creation, move, deletion, patterns, directories, and external resources require semantic interpretation."],
  ["6. Fill Reviewer, Classification, and a factual Evidence note of one or two sentences."],
  ["7. Use Access issue only when necessary evidence cannot be verified."],
  ["8. If the evidence is genuinely insufficient, use ambiguous_reference."],
] : [
  ["0. Esta é uma amostra cega: não consulte uma LLM nem classificações anteriores para decidir o caso."],
  ["1. Abra a tarefa e leia o contexto próximo à referência."],
  ["2. Confirme primeiro que o repositório e o commit estão acessíveis."],
  ["3. Abra o caminho no commit indicado."],
  ["4. Interprete o caminho no contexto da tarefa; ausência não implica automaticamente problema."],
  ["5. Não decida apenas pela caixa de seleção da tarefa."],
  ["6. Preencha Revisor, Classificação e uma nota de evidência factual de uma ou duas frases."],
  ["7. Use Problema de acesso apenas quando a evidência não puder ser verificada."],
  ["8. Se não houver evidência suficiente, use ambiguous_reference."],
];
guide.getRange("A14:B14").values = [[english ? "Classification" : "Classificação", english ? "Definition" : "Definição"]];
guide.getRange(`A15:B${14 + categories.length}`).values = categories;
guide.getRange("A3:B3").format = {
  fill: "#D9EAF7",
  font: { name: "Arial", size: 10, bold: true, color: "#1F2937" },
};
guide.getRange("A14:B14").format = {
  fill: "#1F4E78",
  font: { name: "Arial", size: 10, bold: true, color: "#FFFFFF" },
  horizontalAlignment: "center",
};
guide.getRange(`A1:B${14 + categories.length}`).format.font = { name: "Arial", size: 10, color: "#1F2937" };
guide.getRange("A14:B14").format.font = { name: "Arial", size: 10, bold: true, color: "#FFFFFF" };
guide.getRange(`A4:B${14 + categories.length}`).format.wrapText = true;
guide.getRange(`A4:B${14 + categories.length}`).format.verticalAlignment = "top";
guide.getRange(`A14:B${14 + categories.length}`).format.borders = { preset: "all", style: "thin", color: "#D9D9D9" };
guide.getRange("A:A").format.columnWidth = 42;
guide.getRange("B:B").format.columnWidth = 74;
guide.getRange("A1:B1").format.rowHeight = 26;
guide.getRange("A4:A12").format.autofitRows();
guide.getRange(`A15:B${14 + categories.length}`).format.rowHeight = 38;

workbook.recalculate();
const inspection = await workbook.inspect({
  kind: "table",
  range: `Review!A1:O6`,
  include: "values,formulas",
  tableMaxRows: 6,
  tableMaxCols: 15,
});
console.log(inspection.ndjson);

const errors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!",
  options: { useRegex: true, maxResults: 100 },
  summary: "final formula error scan",
});
console.log(errors.ndjson);

const preview = await workbook.render({
  sheetName: "Review",
  range: "A1:O8",
  scale: 1,
  format: "png",
});
await fs.writeFile(previewPath, new Uint8Array(await preview.arrayBuffer()));

const guidePreview = await workbook.render({
  sheetName: "Guide",
  range: `A1:B${14 + categories.length}`,
  scale: 1.5,
  format: "png",
});
await fs.writeFile(guidePreviewPath, new Uint8Array(await guidePreview.arrayBuffer()));

const xlsx = await SpreadsheetFile.exportXlsx(workbook);
await xlsx.save(outputPath);
console.log(`Wrote ${outputPath}`);
