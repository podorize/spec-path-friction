import fs from "node:fs/promises";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const base = "/Users/pedroodorize/.codex/.chatgpt-projects/g-p-6abaf5bf87e481919dc29fec1c4d1433/msr2027-specmine";
const outputDir = `${base}/results/validation/evidence_equivalent_90`;
const outputPath = `${outputDir}/false_positive_audit.xlsx`;
const ids = ["H017", "H025", "H027", "H047", "H067", "H074"];

function parseCsv(text) {
  const rows = [];
  let row = [], cell = "", quoted = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (quoted) {
      if (ch === '"' && text[i + 1] === '"') { cell += '"'; i++; }
      else if (ch === '"') quoted = false;
      else cell += ch;
    } else if (ch === '"') quoted = true;
    else if (ch === ',') { row.push(cell); cell = ""; }
    else if (ch === '\n') { row.push(cell); rows.push(row); row = []; cell = ""; }
    else if (ch !== '\r') cell += ch;
  }
  if (cell.length || row.length) { row.push(cell); rows.push(row); }
  const headers = rows.shift();
  return rows.filter(r => r.length === headers.length).map(r => Object.fromEntries(headers.map((h, i) => [h, r[i]])));
}

function shorten(s, n = 600) {
  if (!s) return "";
  return s.length > n ? `${s.slice(0, n)}…` : s;
}

const correctedHumanPath = `${base}/data/interim/validation_human_90_R1_adjudicated_v2.csv`;
const originalHumanPath = `${base}/data/interim/validation_human_90_R1_adjudicated.csv`;
const humanPath = await fs.access(correctedHumanPath).then(() => correctedHumanPath).catch(() => originalHumanPath);
const humanRows = parseCsv(await fs.readFile(humanPath, "utf8"));
const llmRows = parseCsv(await fs.readFile(`${base}/data/interim/llm_evidence_equivalent_90_results.csv`, "utf8"));
const keyRows = parseCsv(await fs.readFile(`${base}/data/interim/validation_human_fresh_90_en_key.csv`, "utf8"));
const human = new Map(humanRows.map(r => [r.review_id, r]));
const llm = new Map(llmRows.map(r => [r.review_id, r]));
const key = new Map(keyRows.map(r => [r.review_id, r]));
const evidence = new Map();
const evidenceText = await fs.readFile(`${base}/data/interim/evidence_equivalent_90_augmented.jsonl`, "utf8");
for (const line of evidenceText.trim().split("\n")) { const r = JSON.parse(line); evidence.set(r.review_id, r); }

const cases = ids.map(id => {
  const h = human.get(id), l = llm.get(id), e = evidence.get(id);
  const lit = e.literal_path_observation || {}, tree = e.repository_tree_observation || {}, cand = e.resolved_candidate_observation || {};
  return {
    review_id: id,
    repo_name: h.repo_name,
    anchor_sha: h.anchor_sha,
    artifact_path: h.artifact_path,
    code_path: h.code_path,
    resolved_path: h.resolved_path,
    validation_group: key.get(id)?.validation_group || "",
    task_url: h.task_url,
    literal_path_url: h.literal_path_url,
    anchor_path_url: h.anchor_path_url,
    literal_status: lit.status || "",
    literal_http_status: lit.http_status ?? "",
    literal_content_excerpt: lit.content_excerpt || "",
    candidate_status: cand.status || "",
    candidate_path: cand.path || "",
    candidate_http_status: cand.http_status ?? "",
    candidate_excerpt: cand.content_excerpt || "",
    tree_status: tree.status || "",
    matching_paths_at_anchor: (tree.matching_paths_at_anchor || []).join("\n"),
    tree_match_count: tree.match_count ?? "",
    initial_human_classification: h.initial_human_classification,
    final_human_classification: h.final_classification,
    human_initial_evidence_note: h.initial_evidence_note,
    human_access_issue: h.initial_access_issue,
    human_adjudication_rationale: h.adjudication_rationale,
    human_decision_source: h.decision_source,
    llm_classification: l.classification,
    llm_confidence: Number(l.confidence),
    llm_evidence_quote: l.evidence_quote,
    llm_rationale: l.rationale,
    audit_category: id === "H017" ? "Insufficient context / likely cross-repository plan" : id === "H025" ? "Expected absence after explicit retirement" : id === "H027" ? "Expected creation (new module)" : id === "H047" ? "Insufficient context / path ambiguity" : id === "H067" ? "Cross-repository reference" : "Expected creation (new screen)",
    reviewer_confirmation: "",
    reviewer_revised_classification: "",
    reviewer_notes: "",
    task_context: h.task_context,
  };
});

const comparisonHeaders = [
  "review_id", "repo_name", "anchor_sha", "artifact_path", "code_path", "resolved_path", "validation_group",
  "task_url", "literal_path_url", "anchor_path_url", "literal_status", "literal_http_status", "candidate_status",
  "candidate_path", "tree_status", "matching_paths_at_anchor", "tree_match_count", "initial_human_classification",
  "final_human_classification", "human_initial_evidence_note", "human_access_issue", "human_adjudication_rationale",
  "human_decision_source", "llm_classification", "llm_confidence", "llm_evidence_quote", "llm_rationale", "audit_category",
  "reviewer_confirmation", "reviewer_revised_classification", "reviewer_notes"
];
const comparisonRows = cases.map(c => comparisonHeaders.map(h => c[h] ?? ""));

const evidenceHeaders = ["review_id", "task_context", "literal_content_excerpt", "candidate_excerpt", "literal_path_url", "anchor_path_url", "tree_status", "matching_paths_at_anchor", "tree_match_count", "human_adjudication_rationale", "llm_evidence_quote", "llm_rationale"];
const evidenceRows = cases.map(c => evidenceHeaders.map(h => c[h] ?? ""));

const workbook = Workbook.create();
const comparison = workbook.worksheets.add("Comparison");
const detail = workbook.worksheets.add("Evidence");
const guide = workbook.worksheets.add("Guide");
for (const s of [comparison, detail, guide]) { s.showGridLines = false; s.tabColor = "#1F4E78"; }

comparison.getRange(`A1:${String.fromCharCode(64 + comparisonHeaders.length)}1`).values = [["False-positive audit: evidence-equivalent LLM vs. human adjudication"]];
comparison.mergeCells(`A1:${String.fromCharCode(64 + comparisonHeaders.length)}1`);
comparison.getRange("A2").values = [["All six rows are cases where the LLM predicted confirmed_missing_problematic but the final human label was not problematic. Yellow columns are reserved for your independent review."]];
comparison.mergeCells(`A2:${String.fromCharCode(64 + comparisonHeaders.length)}2`);
comparison.getRange("A4").write([comparisonHeaders, ...comparisonRows]);
comparison.getRange(`A4:${String.fromCharCode(64 + comparisonHeaders.length)}10`).format = { font: { name: "Arial", size: 9, color: "#1F2937" }, verticalAlignment: "center", wrapText: true };
comparison.getRange(`A4:${String.fromCharCode(64 + comparisonHeaders.length)}4`).format = { fill: "#1F4E78", font: { name: "Arial", size: 9, bold: true, color: "#FFFFFF" }, horizontalAlignment: "center", verticalAlignment: "center", wrapText: true };
comparison.getRange("S5:S10").format.fill = "#DDEBF7";
comparison.getRange("X5:X10").format.fill = "#FCE4D6";
comparison.getRange("AB5:AE10").format.fill = "#FFF2CC";
comparison.getRange(`A4:${String.fromCharCode(64 + comparisonHeaders.length)}10`).format.borders = { preset: "all", style: "thin", color: "#D9E2F3" };
comparison.freezePanes.freezeRows(4);
comparison.freezePanes.freezeColumns(5);
comparison.getRange("A:A").format.columnWidth = 11;
comparison.getRange("B:B").format.columnWidth = 25;
comparison.getRange("C:C").format.columnWidth = 42;
comparison.getRange("D:F").format.columnWidth = 34;
comparison.getRange("G:G").format.columnWidth = 20;
comparison.getRange("H:J").format.columnWidth = 42;
comparison.getRange("K:Q").format.columnWidth = 18;
comparison.getRange("R:S").format.columnWidth = 25;
comparison.getRange("T:W").format.columnWidth = 46;
comparison.getRange("X:X").format.columnWidth = 25;
comparison.getRange("Y:Y").format.columnWidth = 13;
comparison.getRange("Z:AA").format.columnWidth = 46;
comparison.getRange("AB:AE").format.columnWidth = 30;
comparison.getRange("A5:AE10").format.rowHeight = 78;
comparison.getRange("Y5:Y10").format.numberFormat = "0.00";

detail.getRange("A1:L1").values = [["Evidence packets and full task context"]];
detail.mergeCells("A1:L1");
detail.getRange("A2").values = [["This tab keeps the long-form evidence separate from the comparison table so the six cases can be reviewed without losing context."]];
detail.mergeCells("A2:L2");
detail.getRange("A4").write([evidenceHeaders, ...evidenceRows]);
detail.getRange("A4:L10").format = { font: { name: "Arial", size: 9, color: "#1F2937" }, verticalAlignment: "top", wrapText: true };
detail.getRange("A4:L4").format = { fill: "#1F4E78", font: { name: "Arial", size: 9, bold: true, color: "#FFFFFF" }, horizontalAlignment: "center", verticalAlignment: "center", wrapText: true };
detail.getRange("A4:L10").format.borders = { preset: "all", style: "thin", color: "#D9E2F3" };
detail.freezePanes.freezeRows(4);
detail.freezePanes.freezeColumns(1);
detail.getRange("A:A").format.columnWidth = 11;
detail.getRange("B:B").format.columnWidth = 90;
detail.getRange("C:D").format.columnWidth = 40;
detail.getRange("E:F").format.columnWidth = 48;
detail.getRange("G:I").format.columnWidth = 22;
detail.getRange("J:L").format.columnWidth = 60;
detail.getRange("A5:L10").format.rowHeight = 220;

const guideRows = [
  ["Purpose", "Review the six false positives from the evidence-equivalent GPT-6 Sol run. Compare the original human interpretation with the LLM interpretation and record an independent confirmation or revision."],
  ["Population", "Six cases with exists_at_anchor = 0, LLM classification = confirmed_missing_problematic, and final human classification different from confirmed_missing_problematic."],
  ["False positive", "The LLM predicts a problematic missing implementation, but the adjudicated human label says the absence is expected, external, or not safely determinable."],
  ["False negative", "The LLM predicts a non-problematic or non-missing interpretation, but the adjudicated human label says confirmed_missing_problematic. None were observed in this six-case false-positive subset."],
  ["How to review", "Read the task context and the evidence packet. Then fill reviewer_confirmation with confirmed / revise-human / revise-llm / unresolved, use reviewer_revised_classification if needed, and explain the decision in reviewer_notes."],
  ["Human labels", "final_human_classification is the post-adjudication label. initial_human_classification is the first-pass label before adjudication."],
  ["LLM labels", "llm_classification, llm_confidence, llm_evidence_quote, and llm_rationale are copied from the evidence-equivalent run. The LLM saw the task context, literal-path observation, candidate observation, and repository-tree observation."],
  ["Important limitation", "A path-level 404 at the anchor commit does not by itself establish a defect. The task may describe a file to be created, a file in another repository, or an underspecified reference."],
  ["Source records", `Human adjudication: ${humanPath.replace(`${base}/`, "")}. LLM comparison: data/interim/llm_evidence_equivalent_90_results.csv. Evidence packet: data/interim/evidence_equivalent_90_augmented.jsonl.`],
  ["Suggested review order", "H017 (cross-repository or mismatched plan), H025 (explicit GMG retirement), H027 (new module creation), H047 (path ambiguity), H067 (external repository), H074 (new screen creation)."],
];
guide.getRange("A1:B1").values = [["Guide for independent review" , ""]];
guide.mergeCells("A1:B1");
guide.getRange("A3:B3").values = [["Item", "Explanation"]];
guide.getRange("A4").write(guideRows);
guide.getRange("A1:B13").format = { font: { name: "Arial", size: 10, color: "#1F2937" }, verticalAlignment: "top", wrapText: true };
guide.getRange("A1:B1").format = { font: { name: "Arial", size: 14, bold: true, color: "#1F4E78" } };
guide.getRange("A3:B3").format = { fill: "#1F4E78", font: { name: "Arial", size: 10, bold: true, color: "#FFFFFF" }, horizontalAlignment: "center" };
guide.getRange("A3:B13").format.borders = { preset: "all", style: "thin", color: "#D9E2F3" };
guide.getRange("A:A").format.columnWidth = 27;
guide.getRange("B:B").format.columnWidth = 115;
guide.getRange("A4:B13").format.rowHeight = 44;
guide.getRange("B8:B8").format.rowHeight = 60;
guide.getRange("B11:B11").format.rowHeight = 60;

workbook.recalculate();
const check = await workbook.inspect({ kind: "table", sheetId: "Comparison", range: "A4:AE10", include: "values,formulas", tableMaxRows: 10, tableMaxCols: 35, tableMaxCellChars: 160 });
console.log(check.ndjson);
const errors = await workbook.inspect({ kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!", options: { useRegex: true, maxResults: 100 }, summary: "formula error scan" });
console.log(errors.ndjson);
await fs.mkdir(outputDir, { recursive: true });
for (const sheetName of ["Comparison", "Evidence", "Guide"]) {
  const png = await workbook.render({ sheetName, autoCrop: "all", scale: 1, format: "png" });
  await fs.writeFile(`${outputDir}/false_positive_audit_${sheetName.toLowerCase()}.png`, new Uint8Array(await png.arrayBuffer()));
}
const xlsx = await SpreadsheetFile.exportXlsx(workbook);
await xlsx.save(outputPath);
console.log(`SAVED ${outputPath}`);
