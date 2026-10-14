import fs from "node:fs/promises";
import path from "node:path";

import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";


const inputPath = "results/validation/human_90/disagreements_for_adjudication.csv";
const outputPath = "results/validation/human_90/validation_human_90_adjudication_R1.xlsx";
const reviewPreviewPath = "results/validation/human_90/adjudication_preview.png";
const guidePreviewPath = "results/validation/human_90/adjudication_guide_preview.png";

const labels = [
  "confirmed_exists",
  "confirmed_missing_problematic",
  "expected_absence_create",
  "expected_absence_move_or_delete",
  "non_file_reference",
  "ambiguous_reference",
  "inaccessible_or_invalid",
];

const labelDefinitions = [
  ["confirmed_exists", "The referenced repository file exists at the indicated commit."],
  ["confirmed_missing_problematic", "The context expects an already-existing repository file, but the file is absent."],
  ["expected_absence_create", "The task explicitly instructs the developer to create the referenced file."],
  ["expected_absence_move_or_delete", "The task moves, renames, replaces, or deletes the referenced path."],
  ["non_file_reference", "The text denotes a pattern, directory, external resource, library, or another non-unique repository file reference."],
  ["ambiguous_reference", "The available evidence is insufficient to determine the reference semantics safely."],
  ["inaccessible_or_invalid", "The repository, commit, task artifact, or other necessary evidence cannot be accessed or is invalid."],
];

const decisionSources = [
  "human_label_changed",
  "llm_label_rejected",
  "both_labels_plausible",
  "evidence_or_protocol_gap",
];

const csvText = await fs.readFile(inputPath, "utf8");
const imported = await Workbook.fromCSV(csvText, { sheetName: "Source" });
const sourceValues = imported.worksheets.getItem("Source").getUsedRange(true).values;
const text = (value) => value == null ? "" : String(value);
const sourceHeaders = sourceValues[0].map(text);
const sourceIndex = Object.fromEntries(sourceHeaders.map((header, index) => [header, index]));
const required = [
  "review_id", "repo_name", "artifact_path", "code_path", "resolved_path",
  "task_url", "anchor_path_url", "task_context", "human_classification",
  "human_evidence_note", "human_access_issue", "llm_classification",
  "llm_confidence", "llm_evidence_quote", "llm_rationale",
];
if (required.some((header) => sourceIndex[header] == null)) {
  throw new Error("The disagreement CSV is missing required columns");
}

const rows = sourceValues.slice(1).map((row) => [
  text(row[sourceIndex.review_id]),
  text(row[sourceIndex.repo_name]),
  text(row[sourceIndex.artifact_path]),
  text(row[sourceIndex.code_path]),
  text(row[sourceIndex.resolved_path]),
  text(row[sourceIndex.task_url]),
  text(row[sourceIndex.anchor_path_url]),
  text(row[sourceIndex.task_context]),
  text(row[sourceIndex.human_classification]),
  text(row[sourceIndex.human_evidence_note]),
  text(row[sourceIndex.human_access_issue]),
  text(row[sourceIndex.llm_classification]),
  Number(row[sourceIndex.llm_confidence]),
  text(row[sourceIndex.llm_evidence_quote]),
  text(row[sourceIndex.llm_rationale]),
  "",
  "",
  "",
]);
if (rows.length !== 24) {
  throw new Error(`Expected 24 disagreements; found ${rows.length}`);
}

const headers = [
  "Review ID", "Repository", "Task artifact", "Literal path", "Resolved path",
  "Task URL", "Path-at-commit URL", "Task context", "R1 initial classification",
  "R1 evidence note", "R1 access issue", "LLM classification", "LLM confidence",
  "LLM evidence quote", "LLM rationale", "Final classification (required)",
  "Adjudication rationale (required)", "Decision source (required)",
];

const workbook = Workbook.create();
const adjudication = workbook.worksheets.add("Adjudication");
const guide = workbook.worksheets.add("Guide");
const rowCount = rows.length + 1;

adjudication.getRange(`A1:R${rowCount}`).values = [headers, ...rows];
adjudication.showGridLines = false;
adjudication.freezePanes.freezeRows(1);
adjudication.freezePanes.freezeColumns(2);
adjudication.tabColor = "#1F4E78";
adjudication.getRange(`A1:R${rowCount}`).format.font = {
  name: "Arial", size: 10, color: "#1F2937",
};
adjudication.getRange("A1:R1").format = {
  fill: "#1F4E78",
  font: { name: "Arial", size: 10, bold: true, color: "#FFFFFF" },
  horizontalAlignment: "center",
  verticalAlignment: "center",
  wrapText: true,
  borders: { preset: "outside", style: "thin", color: "#1F4E78" },
};
adjudication.getRange(`A2:R${rowCount}`).format.verticalAlignment = "top";
adjudication.getRange(`B2:R${rowCount}`).format.wrapText = true;
adjudication.getRange(`P2:R${rowCount}`).format.fill = "#FFF2CC";
adjudication.getRange(`A2:R${rowCount}`).format.borders = {
  preset: "inside", style: "thin", color: "#E5E7EB",
};
adjudication.getRange(`A2:R${rowCount}`).format.rowHeight = 90;
adjudication.getRange(`M2:M${rowCount}`).setNumberFormat("0.00");

adjudication.getRange("A:A").format.columnWidth = 12;
adjudication.getRange("B:B").format.columnWidth = 28;
adjudication.getRange("C:C").format.columnWidth = 44;
adjudication.getRange("D:E").format.columnWidth = 32;
adjudication.getRange("F:G").format.columnWidth = 28;
adjudication.getRange("H:H").format.columnWidth = 80;
adjudication.getRange("I:I").format.columnWidth = 34;
adjudication.getRange("J:K").format.columnWidth = 46;
adjudication.getRange("L:L").format.columnWidth = 34;
adjudication.getRange("M:M").format.columnWidth = 14;
adjudication.getRange("N:O").format.columnWidth = 46;
adjudication.getRange("P:P").format.columnWidth = 36;
adjudication.getRange("Q:Q").format.columnWidth = 56;
adjudication.getRange("R:R").format.columnWidth = 32;

adjudication.dataValidations.add({
  range: `P2:P${rowCount}`,
  rule: { type: "list", values: labels },
});
adjudication.dataValidations.add({
  range: `R2:R${rowCount}`,
  rule: { type: "list", values: decisionSources },
});
for (const column of ["P", "Q", "R"]) {
  adjudication.getRange(`${column}2:${column}${rowCount}`).conditionalFormats.add(
    "containsBlanks",
    { format: { fill: "#FCE8E6", font: { color: "#B91C1C", bold: true } } },
  );
}

guide.showGridLines = false;
guide.tabColor = "#9FBAD0";
guide.getRange("A1:B1").merge();
guide.getRange("A1").values = [["Adjudication of human–LLM disagreements"]];
guide.getRange("A1").format = {
  font: { name: "Arial", size: 14, bold: true, color: "#1F2937" },
  verticalAlignment: "center",
};
guide.getRange("A3:B3").values = [["Procedure", ""]];
guide.getRange("A4:A12").values = [
  ["1. This is an adjudication, not a blind review: both original judgments are intentionally visible."],
  ["2. Preserve the R1 initial label. Never overwrite columns I–O."],
  ["3. Re-open the Task URL and Path-at-commit URL when accessible; read enough surrounding context to decide."],
  ["4. Treat a 404 as path absence only if the repository and commit are accessible."],
  ["5. Do not accept the LLM label merely because it is confident. Confidence is not evidence."],
  ["6. Fill Final classification with your best evidence-based judgment after reconsideration."],
  ["7. Explain the decisive evidence and why the final label is preferable in Adjudication rationale."],
  ["8. Choose Decision source: changed human label, rejected LLM label, both plausible, or evidence/protocol gap."],
  ["9. Complete all three yellow columns for every row and return the workbook without deleting cases."],
];
guide.getRange("A14:B14").values = [["Classification", "Definition"]];
guide.getRange("A15:B21").values = labelDefinitions;
guide.getRange("A23:B23").values = [["Decision source", "When to use"]];
guide.getRange("A24:B27").values = [
  ["human_label_changed", "The final classification differs from R1's first-pass label after reconsideration."],
  ["llm_label_rejected", "R1's first-pass classification remains the final classification."],
  ["both_labels_plausible", "The protocol permits more than one defensible reading; select the best final label and document the ambiguity."],
  ["evidence_or_protocol_gap", "Missing evidence or an unclear protocol boundary prevents a clean attribution of the disagreement."],
];
for (const range of ["A3:B3", "A14:B14", "A23:B23"]) {
  guide.getRange(range).format = {
    fill: range === "A3:B3" ? "#D9EAF7" : "#1F4E78",
    font: {
      name: "Arial", size: 10, bold: true,
      color: range === "A3:B3" ? "#1F2937" : "#FFFFFF",
    },
    horizontalAlignment: range === "A3:B3" ? "left" : "center",
  };
}
guide.getRange("A1:B27").format.font = { name: "Arial", size: 10, color: "#1F2937" };
guide.getRange("A1").format.font = { name: "Arial", size: 14, bold: true, color: "#1F2937" };
guide.getRange("A14:B14").format.font = { name: "Arial", size: 10, bold: true, color: "#FFFFFF" };
guide.getRange("A23:B23").format.font = { name: "Arial", size: 10, bold: true, color: "#FFFFFF" };
guide.getRange("A4:B27").format.wrapText = true;
guide.getRange("A4:B27").format.verticalAlignment = "top";
guide.getRange("A14:B21").format.borders = { preset: "all", style: "thin", color: "#D9D9D9" };
guide.getRange("A23:B27").format.borders = { preset: "all", style: "thin", color: "#D9D9D9" };
guide.getRange("A:A").format.columnWidth = 42;
guide.getRange("B:B").format.columnWidth = 76;
guide.getRange("A1:B1").format.rowHeight = 26;
guide.getRange("A4:A12").format.autofitRows();
guide.getRange("A15:B21").format.rowHeight = 38;
guide.getRange("A24:B27").format.rowHeight = 42;

workbook.recalculate();
const inspection = await workbook.inspect({
  kind: "table",
  range: "Adjudication!A1:R5",
  include: "values,formulas",
  tableMaxRows: 5,
  tableMaxCols: 18,
});
console.log(inspection.ndjson);

const errors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!",
  options: { useRegex: true, maxResults: 100 },
  summary: "final formula error scan",
});
console.log(errors.ndjson);

await fs.mkdir(path.dirname(outputPath), { recursive: true });
const reviewPreview = await workbook.render({
  sheetName: "Adjudication", range: "A1:R5", scale: 1, format: "png",
});
await fs.writeFile(reviewPreviewPath, new Uint8Array(await reviewPreview.arrayBuffer()));
const guidePreview = await workbook.render({
  sheetName: "Guide", range: "A1:B27", scale: 1.4, format: "png",
});
await fs.writeFile(guidePreviewPath, new Uint8Array(await guidePreview.arrayBuffer()));

const xlsx = await SpreadsheetFile.exportXlsx(workbook);
await xlsx.save(outputPath);
console.log(`Wrote ${outputPath}`);
