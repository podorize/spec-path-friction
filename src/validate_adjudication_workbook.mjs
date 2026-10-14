import crypto from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";

import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const projectRoot = process.cwd();
const workbookPath = process.argv[2] || "/Users/pedroodorize/Downloads/validation_human_90_adjudication_R1_adjudicated.xlsx";
const disagreementPath = path.join(projectRoot, "results/validation/human_90/disagreements_for_adjudication.csv");
const initialPath = path.join(projectRoot, "data/interim/validation_human_fresh_90_R1_initial.csv");
const outputPath = path.join(projectRoot, "data/interim/validation_human_90_R1_adjudicated.csv");
const manifestPath = path.join(projectRoot, "data/interim/validation_human_90_R1_adjudicated_manifest.json");

const labels = new Set([
  "confirmed_exists",
  "confirmed_missing_problematic",
  "expected_absence_create",
  "expected_absence_move_or_delete",
  "non_file_reference",
  "ambiguous_reference",
  "inaccessible_or_invalid",
]);
const decisionSources = new Set([
  "human_label_changed",
  "llm_label_rejected",
  "both_labels_plausible",
  "evidence_or_protocol_gap",
]);
const normalizedHeaders = [
  "review_id", "repo_name", "anchor_sha", "artifact_path", "code_path",
  "resolved_path", "task_url", "literal_path_url", "anchor_path", "anchor_path_url",
  "task_context", "reviewer_id", "initial_human_classification", "initial_evidence_note",
  "initial_access_issue", "llm_classification", "llm_confidence", "llm_evidence_quote",
  "llm_rationale", "final_classification", "adjudication_rationale", "decision_source",
  "adjudication_status",
];
const immutableFields = [
  "review_id", "repo_name", "artifact_path", "code_path", "resolved_path",
  "task_url", "anchor_path_url", "task_context",
];

const cellText = (value) => value == null ? "" : String(value);
const csvCell = (value) => {
  const text = cellText(value);
  return /[",\r\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
};
const readCsv = async (filePath) => {
  const text = await fs.readFile(filePath, "utf8");
  const lines = [];
  let field = "";
  let row = [];
  let quoted = false;
  for (let index = 0; index < text.length; index += 1) {
    const char = text[index];
    if (quoted) {
      if (char === '"' && text[index + 1] === '"') { field += '"'; index += 1; }
      else if (char === '"') quoted = false;
      else field += char;
    } else if (char === '"') quoted = true;
    else if (char === ",") { row.push(field); field = ""; }
    else if (char === "\n") { row.push(field); lines.push(row); row = []; field = ""; }
    else if (char !== "\r") field += char;
  }
  if (field || row.length) { row.push(field); lines.push(row); }
  const headers = lines.shift();
  return lines.filter((values) => values.some((value) => value !== "")).map((values) =>
    Object.fromEntries(headers.map((header, index) => [header, values[index] ?? ""])),
  );
};
const sha256 = (bytes) => crypto.createHash("sha256").update(bytes).digest("hex");

const initialRows = await readCsv(initialPath);
const disagreementRows = await readCsv(disagreementPath);
const initialById = new Map(initialRows.map((row) => [row.review_id, row]));
const disagreementById = new Map(disagreementRows.map((row) => [row.review_id, row]));
if (initialRows.length !== 90 || disagreementRows.length !== 24) {
  throw new Error(`Expected 90 initial rows and 24 disagreement rows; found ${initialRows.length} and ${disagreementRows.length}`);
}

const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(workbookPath));
const sheet = workbook.worksheets.getItem("Adjudication");
const values = sheet.getUsedRange(true).values.map((row) => row.map(cellText));
const headers = values[0];
const headerIndex = Object.fromEntries(headers.map((header, index) => [header, index]));
const requiredHeaders = [
  "Review ID", "Repository", "Task artifact", "Literal path", "Resolved path", "Task URL",
  "Path-at-commit URL", "Task context", "R1 initial classification", "R1 evidence note",
  "R1 access issue", "LLM classification", "LLM confidence", "LLM evidence quote", "LLM rationale",
  "Final classification (required)", "Adjudication rationale (required)", "Decision source (required)",
];
if (requiredHeaders.some((header) => headerIndex[header] == null)) throw new Error("Adjudication sheet headers are incomplete");
const adjudicationRows = values.slice(1);
if (adjudicationRows.length !== 24) throw new Error(`Expected 24 adjudication rows; found ${adjudicationRows.length}`);

const fieldMap = {
  "Review ID": "review_id", "Repository": "repo_name", "Task artifact": "artifact_path",
  "Literal path": "code_path", "Resolved path": "resolved_path", "Task URL": "task_url",
  "Path-at-commit URL": "anchor_path_url", "Task context": "task_context",
  "R1 initial classification": "initial_human_classification", "R1 evidence note": "initial_evidence_note",
  "R1 access issue": "initial_access_issue", "LLM classification": "llm_classification",
  "LLM confidence": "llm_confidence", "LLM evidence quote": "llm_evidence_quote",
  "LLM rationale": "llm_rationale", "Final classification (required)": "final_classification",
  "Adjudication rationale (required)": "adjudication_rationale", "Decision source (required)": "decision_source",
};
const finalById = new Map();
for (const row of adjudicationRows) {
  const reviewId = row[headerIndex["Review ID"]];
  const initial = initialById.get(reviewId);
  const expectedDisagreement = disagreementById.get(reviewId);
  if (!initial || !expectedDisagreement) throw new Error(`Unexpected review ID in workbook: ${reviewId}`);
  for (const header of Object.keys(fieldMap)) {
    const normalized = fieldMap[header];
    if (normalized === "initial_human_classification") {
      if (row[headerIndex[header]] !== expectedDisagreement.human_classification) throw new Error(`Initial human label changed for ${reviewId}`);
    }
    if (normalized === "llm_classification" && row[headerIndex[header]] !== expectedDisagreement.llm_classification) throw new Error(`LLM label changed for ${reviewId}`);
  }
  for (const field of immutableFields) {
    const sourceField = field === "anchor_path_url" ? "anchor_path_url" : field;
    const workbookField = Object.entries(fieldMap).find(([, normalized]) => normalized === sourceField)?.[0];
    if (workbookField && row[headerIndex[workbookField]] !== expectedDisagreement[sourceField]) throw new Error(`Immutable field changed for ${reviewId}: ${field}`);
  }
  const finalClassification = row[headerIndex["Final classification (required)"]].trim();
  const rationale = row[headerIndex["Adjudication rationale (required)"]].trim();
  const source = row[headerIndex["Decision source (required)"]].trim();
  if (!labels.has(finalClassification)) throw new Error(`Invalid final classification for ${reviewId}: ${finalClassification}`);
  if (!rationale) throw new Error(`Missing adjudication rationale for ${reviewId}`);
  if (!decisionSources.has(source)) throw new Error(`Invalid decision source for ${reviewId}: ${source}`);
  finalById.set(reviewId, { finalClassification, rationale, source });
}
if (finalById.size !== 24) throw new Error("Duplicate or missing adjudication IDs");

const outputRows = initialRows.map((row) => {
  const adjudicated = finalById.get(row.review_id);
  const initialLabel = row.manual_classification;
  return {
    review_id: row.review_id,
    repo_name: row.repo_name,
    anchor_sha: row.anchor_sha,
    artifact_path: row.artifact_path,
    code_path: row.code_path,
    resolved_path: row.resolved_path,
    task_url: row.task_url,
    literal_path_url: row.literal_path_url,
    anchor_path: row.anchor_path,
    anchor_path_url: row.anchor_path_url,
    task_context: row.task_context,
    reviewer_id: row.reviewer_id,
    initial_human_classification: initialLabel,
    initial_evidence_note: row.evidence_note,
    initial_access_issue: row.access_issue,
    llm_classification: adjudicated ? disagreementById.get(row.review_id).llm_classification : "",
    llm_confidence: adjudicated ? disagreementById.get(row.review_id).llm_confidence : "",
    llm_evidence_quote: adjudicated ? disagreementById.get(row.review_id).llm_evidence_quote : "",
    llm_rationale: adjudicated ? disagreementById.get(row.review_id).llm_rationale : "",
    final_classification: adjudicated ? adjudicated.finalClassification : initialLabel,
    adjudication_rationale: adjudicated ? adjudicated.rationale : "No disagreement; first-pass label retained.",
    decision_source: adjudicated ? adjudicated.source : "not_applicable_no_disagreement",
    adjudication_status: adjudicated ? "adjudicated_disagreement" : "initial_label_retained",
  };
});

const csv = [
  normalizedHeaders.join(","),
  ...outputRows.map((row) => normalizedHeaders.map((header) => csvCell(row[header])).join(",")),
].join("\n") + "\n";
await fs.writeFile(outputPath, csv, "utf8");

const workbookBytes = await fs.readFile(workbookPath);
const manifest = {
  status: "validated_adjudication",
  workbook: path.basename(workbookPath),
  workbook_sha256: sha256(workbookBytes),
  rows_in_workbook: adjudicationRows.length,
  rows_adjudicated: finalById.size,
  initial_labels_preserved: true,
  output_csv: path.basename(outputPath),
  output_sha256: sha256(Buffer.from(csv)),
  final_label_counts: Object.fromEntries([...new Set(labels)].sort().map((label) => [label, outputRows.filter((row) => row.final_classification === label).length])),
  decision_source_counts: Object.fromEntries([...decisionSources].sort().map((source) => [source, [...finalById.values()].filter((row) => row.source === source).length])),
};
await fs.writeFile(manifestPath, JSON.stringify(manifest, null, 2) + "\n", "utf8");
console.log(JSON.stringify(manifest, null, 2));
