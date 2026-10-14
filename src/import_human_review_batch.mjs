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
const sourcePath = argValue("--source", "data/interim/validation_human_fresh_90_en.csv");
const outputPath = argValue("--output", "data/interim/validation_human_fresh_90_batch1_initial.csv");
const manifestPath = argValue("--manifest", "data/interim/validation_human_fresh_90_batch1_initial_manifest.json");
const archivedWorkbookPath = argValue("--archive-workbook", "data/interim/validation_human_first_30_reviews.xlsx");
const expectedStart = Number(argValue("--expected-start", "1"));
const expectedCount = Number(argValue("--expected-count", "30"));

if (!inputPath) {
  throw new Error("--input is required");
}

const reviewHeaders = [
  "Review ID", "Repository", "Commit", "Task artifact", "Literal path",
  "Resolved path", "Task URL", "Literal path URL", "Path at commit",
  "Path-at-commit URL", "Task context", "Reviewer", "Classification",
  "Evidence note (required)", "Access issue",
];
const normalizedHeaders = [
  "review_id", "repo_name", "anchor_sha", "artifact_path", "code_path",
  "resolved_path", "task_url", "literal_path_url", "anchor_path",
  "anchor_path_url", "task_context", "reviewer_id", "manual_classification",
  "evidence_note", "access_issue",
];
const sourceHeaders = normalizedHeaders.slice(0, 11);
const validClassifications = new Set([
  "confirmed_exists",
  "confirmed_missing_problematic",
  "expected_absence_create",
  "expected_absence_move_or_delete",
  "non_file_reference",
  "ambiguous_reference",
  "inaccessible_or_invalid",
]);

const cellText = (value) => value == null ? "" : String(value);
const csvCell = (value) => {
  const text = cellText(value);
  return /[",\r\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
};

const inputBlob = await FileBlob.load(inputPath);
const inputBytes = await fs.readFile(inputPath);
const inputSha256 = crypto.createHash("sha256").update(inputBytes).digest("hex");
const workbook = await SpreadsheetFile.importXlsx(inputBlob);
const reviewSheet = workbook.worksheets.getItem("Review");
const reviewValues = reviewSheet.getUsedRange(true).values.map((row) => row.map(cellText));

if (JSON.stringify(reviewValues[0]) !== JSON.stringify(reviewHeaders)) {
  throw new Error(`Unexpected Review headers: ${JSON.stringify(reviewValues[0])}`);
}
const rows = reviewValues.slice(1);
if (rows.length !== expectedCount) {
  throw new Error(`Expected ${expectedCount} reviews, found ${rows.length}`);
}

const expectedIds = Array.from(
  { length: expectedCount },
  (_, index) => `H${String(expectedStart + index).padStart(3, "0")}`,
);
const actualIds = rows.map((row) => row[0]);
if (JSON.stringify(actualIds) !== JSON.stringify(expectedIds)) {
  throw new Error(`Unexpected review IDs: ${JSON.stringify(actualIds)}`);
}
if (new Set(actualIds).size !== actualIds.length) {
  throw new Error("Duplicate review IDs found");
}

const sourceCsv = await fs.readFile(sourcePath, "utf8");
const sourceWorkbook = await Workbook.fromCSV(sourceCsv, { sheetName: "Source" });
const sourceValues = sourceWorkbook.worksheets.getItem("Source").getUsedRange(true).values;
const sourceHeader = sourceValues[0].map(cellText);
const sourceIndexes = Object.fromEntries(sourceHeaders.map((header) => [header, sourceHeader.indexOf(header)]));
if (Object.values(sourceIndexes).some((index) => index < 0)) {
  throw new Error("Source CSV does not contain all immutable fields");
}
const sourceById = new Map(
  sourceValues.slice(1).map((row) => [cellText(row[sourceIndexes.review_id]), row.map(cellText)]),
);

const immutableMismatches = [];
for (const row of rows) {
  const sourceRow = sourceById.get(row[0]);
  if (!sourceRow) {
    throw new Error(`Review ${row[0]} is not present in the frozen source sample`);
  }
  sourceHeaders.forEach((header, index) => {
    if (row[index] !== sourceRow[sourceIndexes[header]]) {
      immutableMismatches.push({ review_id: row[0], field: header });
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
await fs.copyFile(inputPath, archivedWorkbookPath);

const classificationCounts = {};
for (const row of rows) {
  classificationCounts[row[12]] = (classificationCounts[row[12]] ?? 0) + 1;
}
const accessIssueCount = rows.filter((row) => row[14].trim()).length;
const manifest = {
  status: "accepted_as_initial_human_labels",
  final_gold_standard: false,
  input_workbook: path.basename(inputPath),
  archived_workbook: path.basename(archivedWorkbookPath),
  input_sha256: inputSha256,
  frozen_source_sample: path.basename(sourcePath),
  output_csv: path.basename(outputPath),
  review_ids: actualIds,
  n_reviews: rows.length,
  immutable_field_mismatches: 0,
  blank_reviewers: 0,
  blank_classifications: 0,
  invalid_classifications: 0,
  blank_evidence_notes: 0,
  access_issue_count: accessIssueCount,
  classification_counts: classificationCounts,
  note: "These are first-pass independent human labels. Disagreements may be adjudicated later and must not overwrite this file.",
};
await fs.writeFile(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`, "utf8");

console.log(JSON.stringify(manifest, null, 2));
