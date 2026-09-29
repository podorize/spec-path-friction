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
will use only outcomes whose semantic meaning is supported by this validation.
LLM judgments may assist triage but will not constitute the final ground truth.
