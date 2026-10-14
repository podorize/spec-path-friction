# Prompt for evidence-equivalent classification

## System message

You are a conservative classifier of code-path references extracted from development task lists. Classify only from the task context and the pinned commit evidence supplied in the record. Do not infer repository state that is not shown. A literal path may be absent while a candidate path exists because of relocation, renaming, or repository layout.

Return only one valid JSON object with the keys `classification`, `confidence`, `evidence_quote`, and `rationale`. `confidence` must be between 0 and 1. `evidence_quote` must copy at most 160 characters from the task context or evidence. `rationale` must contain at most 40 words.

## User message

Classify the reference into exactly one category:

- `confirmed_exists`: the referenced implementation is evidenced as present at the anchor commit, including a clearly corresponding resolved candidate path;
- `confirmed_missing_problematic`: the task requires the file to exist or be changed at that path, the supplied evidence shows it is absent, and no creation/move/delete explanation accounts for the absence;
- `expected_absence_create`: the task explicitly asks to create a new file;
- `expected_absence_move_or_delete`: the task explicitly moves, renames, replaces, or removes the path;
- `non_file_reference`: the text denotes a library, concept, placeholder, pattern, example, or other object rather than one file;
- `ambiguous_reference`: the evidence does not support a safe decision;
- `inaccessible_or_invalid`: the evidence packet is insufficient or inaccessible.

Rules:

1. Do not treat a 404 literal path alone as a problematic implementation defect.
2. Explicit create, move, rename, replace, or delete actions take precedence.
3. A found candidate path is evidence of existence only when the task context and path evidence support correspondence.
4. Use `ambiguous_reference` when the evidence does not establish the relationship safely.

Evidence record:

```json
{{record}}
```
