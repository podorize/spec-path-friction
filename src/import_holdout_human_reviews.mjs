import crypto from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";

import { FileBlob, SpreadsheetFile, Workbook } from "@oai/artifact-tool";


const args = process.argv.slice(2);
const argValue = (name, fallback = null) => {
  const index = args.indexOf(name);
  return index >= 0 && args[index + 1] ? args[index + 1] : fallback;
};

const inputPath = argValue("--input");
const sourcePath = argValue("--source", "data/interim/holdout_human_v1_90_workbook.csv");
const outputPath = argValue("--output", "data/interim/holdout_human_v1_90_labels.csv");
const manifestPath = argValue("--manifest", "data/interim/holdout_human_v1_90_labels_manifest.json");
const archivedWorkbookPath = argValue(
  "--archive-workbook",
  "data/interim/holdout_human_v1_90_reviews_filled.xlsx",
);

if (!inputPath) throw new Error("--input is required");

const reviewHeaders = [
  "Review ID", "Repository", "Commit", "Task artifact", "Literal path",
  "Resolved path", "Task URL", "Literal path URL", "Path at commit",
  "Path-at-commit URL", "Task context", "Reviewer", "Classification",
  "Evidence note (required)", "Access issue",
];
const normalizedHeaders = [
  "human_review_id", "repo_name", "anchor_sha", "artifact_path", "code_path",
  "resolved_path", "task_url", "literal_path_url", "anchor_path",
  "anchor_path_url", "task_context", "reviewer_id", "manual_classification",
  "evidence_note", "access_issue",
];
const immutableHeaders = normalizedHeaders.slice(0, 11);
const sourceHeaderFor = {
  human_review_id: "review_id",
  repo_name: "repo_name",
  anchor_sha: "anchor_sha",
  artifact_path: "artifact_path",
  code_path: "code_path",
  resolved_path: "resolved_path",
  task_url: "task_url",
  literal_path_url: "literal_path_url",
  anchor_path: "anchor_path",
  anchor_path_url: "anchor_path_url",
  task_context: "task_context",
};
const validClassifications = new Set([
  "confirmed_exists",
  "confirmed_missing_problematic",
  "expected_absence_create",
  "expected_absence_move_or_delete",
  "external_repository_reference",
  "non_file_reference",
  "ambiguous_reference",
  "inaccessible_or_invalid",
]);

const cellText = (value) => value == null ? "" : String(value);
const csvCell = (value) => {
  const text = cellText(value);
  return /[",\r\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
};
const sha256 = (bytes) => crypto.createHash("sha256").update(bytes).digest("hex");

const inputBytes = await fs.readFile(inputPath);
const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(inputPath));
const reviewSheet = workbook.worksheets.getItem("Review");
if (!reviewSheet) throw new Error("Review sheet is missing");
const usedRange = reviewSheet.getUsedRange(true);
if (!usedRange) throw new Error("Review sheet is empty");
const values = usedRange.values.map((row) => row.map(cellText));
if (JSON.stringify(values[0]) !== JSON.stringify(reviewHeaders)) {
  throw new Error(`Unexpected Review headers: ${JSON.stringify(values[0])}`);
}
const rows = values.slice(1).filter((row) => row[0].trim());
if (rows.length !== 90) throw new Error(`Expected 90 populated reviews, found ${rows.length}`);
const expectedIds = Array.from({ length: 90 }, (_, index) => `V${String(index + 1).padStart(3, "0")}`);
const actualIds = rows.map((row) => row[0]);
if (JSON.stringify(actualIds) !== JSON.stringify(expectedIds)) {
  throw new Error(`Unexpected or reordered review IDs: ${JSON.stringify(actualIds)}`);
}

const sourceCsv = await fs.readFile(sourcePath, "utf8");
const sourceWorkbook = await Workbook.fromCSV(sourceCsv, { sheetName: "Source" });
const sourceValues = sourceWorkbook.worksheets.getItem("Source").getUsedRange(true).values;
const sourceHeader = sourceValues[0].map(cellText);
const sourceIndexes = Object.fromEntries(
  immutableHeaders.map((header) => [header, sourceHeader.indexOf(sourceHeaderFor[header])]),
);
if (Object.values(sourceIndexes).some((index) => index < 0)) {
  throw new Error("Frozen source CSV does not contain all immutable fields");
}
const sourceById = new Map(
  sourceValues.slice(1).map((row) => [cellText(row[sourceIndexes.human_review_id]), row.map(cellText)]),
);

const immutableMismatches = [];
for (const row of rows) {
  const sourceRow = sourceById.get(row[0]);
  if (!sourceRow) throw new Error(`Review ${row[0]} is absent from the frozen source sample`);
  immutableHeaders.forEach((header, index) => {
    if (row[index] !== sourceRow[sourceIndexes[header]]) {
      immutableMismatches.push({ human_review_id: row[0], field: header });
    }
  });
}
if (immutableMismatches.length) {
  throw new Error(`Immutable fields changed: ${JSON.stringify(immutableMismatches)}`);
}

const validationErrors = [];
for (const row of rows) {
  if (!row[11].trim()) validationErrors.push(`${row[0]}: blank reviewer`);
  if (!validClassifications.has(row[12].trim())) {
    validationErrors.push(`${row[0]}: invalid classification ${row[12]}`);
  }
  if (!row[13].trim()) validationErrors.push(`${row[0]}: blank evidence note`);
}
if (validationErrors.length) {
  throw new Error(`Incomplete human reviews: ${validationErrors.join("; ")}`);
}

const outputLines = [
  normalizedHeaders.map(csvCell).join(","),
  ...rows.map((row) => row.map(csvCell).join(",")),
];
await fs.mkdir(path.dirname(outputPath), { recursive: true });
await fs.writeFile(outputPath, `${outputLines.join("\n")}\n`, "utf8");
if (path.resolve(inputPath) !== path.resolve(archivedWorkbookPath)) {
  await fs.copyFile(inputPath, archivedWorkbookPath);
}

const classificationCounts = {};
for (const row of rows) {
  classificationCounts[row[12]] = (classificationCounts[row[12]] ?? 0) + 1;
}
const manifest = {
  status: "accepted_as_independent_human_reference",
  reference_standard: "single_reviewer_blinded_labels",
  adjudicated: false,
  llm_or_pipeline_labels_visible_during_review: false,
  input_workbook: path.basename(inputPath),
  archived_workbook: path.basename(archivedWorkbookPath),
  input_sha256: sha256(inputBytes),
  frozen_source_sample: path.basename(sourcePath),
  frozen_source_sha256: sha256(Buffer.from(sourceCsv)),
  output_csv: path.basename(outputPath),
  output_sha256: sha256(Buffer.from(`${outputLines.join("\n")}\n`)),
  n_reviews: rows.length,
  immutable_field_mismatches: 0,
  blank_reviewers: 0,
  blank_classifications: 0,
  invalid_classifications: 0,
  blank_evidence_notes: 0,
  access_issue_count: rows.filter((row) => row[14].trim()).length,
  classification_counts: Object.fromEntries(Object.entries(classificationCounts).sort()),
};
await fs.writeFile(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`, "utf8");
console.log(JSON.stringify(manifest, null, 2));
