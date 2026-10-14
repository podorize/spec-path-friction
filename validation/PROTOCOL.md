# Protocol for validating OpenSpec code references

## Purpose

This protocol evaluates the semantic validity of automatically extracted
OpenSpec task-to-code references. It distinguishes literal path absence at the
anchor commit from an implementation or traceability problem.

## Dataset and unit of analysis

- Dataset: SpecMine, July 2026 release.
- Population: rows in `openspec_code_refs.parquet`.
- Unit: one extracted code reference associated with one OpenSpec `tasks.md`
  artifact at its `anchor_sha`.
- The automated field `exists_at_anchor` is treated as a path-resolution
  signal, not as ground truth for implementation friction.

## Pilot sample

The pilot sample contains 60 deterministically selected references, using seed
`20260928`:

- 20 completed + path absent (`task_done = 1`, `exists_at_anchor = 0`)
- 20 completed + path exists (`task_done = 1`, `exists_at_anchor = 1`)
- 20 open + path absent (`task_done = 0`, `exists_at_anchor = 0`)

The sample is stored locally in `data/interim/validation_workbook_pilot.csv`.
It is not committed because it contains public repository identifiers that
should remain private during double-anonymous review.

## Blinded human-review materials

The script `src/consolidate_validation_evidence.py` produces three local,
uncommitted files:

- `validation_evidence_pilot.csv`, the project lead's evidence table, which
  joins the sampled references to exploratory LLM triage;
- `validation_human_blinded_pilot.csv`, shuffled deterministically and stripped
  of `task_done`, `exists_at_anchor`, `validation_group`, and all LLM labels;
- `validation_blinding_key_pilot.csv`, the private mapping used only after
  review to reconnect human labels to the sample strata.

The blinded workbook is the only file sent to a human reviewer. The reviewer
receives the taxonomy and audit procedure, but not the LLM labels. The pilot
LLM triage is retained only to develop the rubric and prompt; it is not a
reference standard.

## LLM-assisted classification at scale

The study uses an LLM judge to classify the unresolved-reference population at
scale, with the same taxonomy used for human review. The frozen prompt is in
`validation/LLM_JUDGE_PROMPT.md`. `src/build_llm_judge_inputs.py` constructs
bounded, task-local JSONL records but never calls a model. This separation
ensures that the exact input set can be preserved before an API run.

The current 60-reference pilot is used only for prompt/rubric development.
`src/create_confirmatory_validation_sample.py` draws a fresh, deterministic,
blinded confirmation sample of 90 English-language references (30 per pilot
stratum), excluding every pilot ID and every ID from the superseded
unrestricted confirmation sample. English eligibility requires `langdetect`
to identify the task context as English with probability at least 0.90 and no
non-Latin writing system in that context. This sample is not used to alter the
prompt. We will compare
the frozen judge's labels against human labels by category, report agreement
and uncertainty, and describe population results as LLM-assisted estimates.
Human labels, rather than LLM labels, remain the reference for measuring
judge performance.

## Independent B001-B030 evaluation

The first 30 completed confirmation reviews were used with interactive
assistance while the reviewer learned the rubric. They are retained as
human-assisted pilot material and are not used as an independent estimate of
LLM performance.

A second sample, `B001` through `B030`, was drawn from the remaining English
confirmation cases with seed `20261001`. It contains ten references from each
automated stratum: completed + absent, completed + present, and open + absent.
The human reviewer classified this sample without case-level LLM assistance.

`src/prepare_blind_evaluation_run.py` validates the returned human CSV against
the original blind input, freezes a canonical human-label file, and creates a
separate LLM JSONL input from the pre-review source and private key. The LLM
input excludes human labels, evidence notes, access notes, task completion,
and validation strata. The original returned CSV remains unchanged. One
metadata normalization was recorded for `B011`: its existing evidence note
said that the repository was unavailable, so the previously blank access-note
field was populated without changing its classification.

The frozen prompt was executed independently once per reference with
`gpt-6-sol`, low reasoning effort, structured JSON output, and a fresh
ephemeral Codex process. The Codex CLI did not expose a temperature parameter;
this is recorded as unavailable rather than inferred. Every process used an
isolated temporary working directory containing no human-label file. The run
produced 30 valid JSON responses and retained the raw event stream, final
message, and stderr log for every case. File hashes, model settings, CLI
version, timestamps, and the complete ID set are stored in
`data/interim/llm_blind_eval_30_run_manifest.json`.

The independent seven-category comparison yielded 19/30 exact agreements
(63.3%), Cohen's kappa of 0.553, and macro-F1 of 0.556. These estimates are
reported with uncertainty because the sample is small and several categories
have very low support. In particular, only one human-labelled case was
`confirmed_missing_problematic`; binary metrics for that outcome are therefore
descriptive and must not be generalized as evidence of reliable rare-event
detection.

The comparison also exposed a taxonomy boundary that must remain visible in
reporting: explicit creation language can coexist with a path that resolves at
the anchor commit. The frozen prompt gives action language precedence, whereas
the human reviewer sometimes selected `confirmed_exists`. Because the prompt
was frozen before independent evaluation, it was not changed after observing
this disagreement. The paper will treat this as a construct-validity and
category-overlap limitation rather than silently adjudicating the cases.

## Audit procedure

For each reference, the reviewer:

1. Opens the task artifact at `anchor_sha`.
2. Reads the task context containing the extracted reference.
3. Opens the path at the same commit. For `exists_at_anchor = 1`, this is
   `resolved_path` when it is available and otherwise the literal `code_path`;
   for `exists_at_anchor = 0`, it is the literal `code_path`.
4. Records a classification and a short factual evidence note.

The classification is based on the repository state at the anchor commit, not
the repository's current default branch. `code_path` preserves the text
extracted from the task, whereas `resolved_path` is the repository path found
by SpecMine's resolver. They may differ, particularly when a task uses a
basename or a path relative to a subproject.

## Classification taxonomy

| Label | Definition |
| --- | --- |
| `confirmed_exists` | The referenced file exists at the anchor commit. |
| `confirmed_missing_problematic` | The task requires an existing file at that path, but it is absent at the anchor commit. |
| `expected_absence_create` | The task explicitly requires creation of a new file; absence is expected. |
| `expected_absence_move_or_delete` | The path is an explicitly moved, replaced, or deleted source path; absence is expected. |
| `non_file_reference` | The extracted string names a library, conceptual artifact, test fixture, URL fragment, or other non-file entity. |
| `ambiguous_reference` | The string is insufficiently qualified or task context does not establish whether the path should exist. |
| `inaccessible_or_invalid` | The anchor commit or artifact cannot be accessed or independently checked. |

## Decision rules

- A bare filename without a directory is not classified as problematic unless
  the task explicitly establishes that it is a repository-root path.
- A string beginning with `../` is not treated as a repository path unless the
  task explicitly identifies its base directory.
- A task explicitly saying “create”, “move”, “rename”, “delete”, “remove”, or
  “replace” takes precedence over literal absence.
- A reference to a framework, package, library, or format is `non_file_reference`
  unless an explicit project-relative path is present.
- When evidence is insufficient, use `ambiguous_reference`; do not infer
  friction from absence alone.

## Planned reporting

We will report the prevalence of each category with uncertainty intervals,
separately by task completion status. Associations with task-list structure
will use only outcomes whose semantic meaning is supported by the human
calibration study. Population estimates will be explicitly identified as
LLM-assisted, and LLM judgments will not constitute final ground truth.
