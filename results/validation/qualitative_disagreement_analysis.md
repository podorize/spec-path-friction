# Qualitative analysis of human-LLM disagreements

## Scope

This analysis examines the 11 disagreements in the independent `B001-B030`
comparison. It does not adjudicate the cases, replace the human labels, or
modify the frozen LLM prompt. Its purpose is to identify why the two judgments
differed and what those differences imply for construct validity.

The comparison evaluates the complete classification pipeline, not only the
reasoning ability of the model. The human reviewer could open the full task
artifact and GitHub paths. The LLM received a bounded task excerpt, the literal
and resolved paths when available, and SpecMine's automatic resolution signal.

## Primary disagreement modes

| Primary mode | Cases | Count | Interpretation |
| --- | --- | ---: | --- |
| Taxonomy overlap or boundary conflict | B002, B008, B017, B020, B023, B024, B028 | 7 | The flat label set mixes repository state, task intent, generated artifacts, globs, and uncertainty. More than one label can reasonably describe the same record. |
| Evidence asymmetry or provenance gap | B011, B026, B030 | 3 | The human and LLM did not have equivalent verifiable evidence, or the automated resolution signal lacked the path needed to reproduce it. |
| Human conservatism despite explicit creation language | B018 | 1 | The human retained uncertainty, while the model applied the frozen prompt's explicit-action precedence rule. |

These modes are analytical explanations, not corrected ground-truth labels.

## Case-level analysis

### B002: generated report output

- Human: `ambiguous_reference`
- LLM: `expected_absence_create`
- Path: `reports/index.html`

The task says to implement generation or regeneration of the HTML file at the
end of a match. The LLM treated generation as explicit creation. The human
treated the file as a potentially local runtime output whose absence from Git
may be normal. The current taxonomy has no dedicated category for generated
or runtime artifacts. `expected_absence_create` describes the production
action, while `ambiguous_reference` reflects uncertainty about whether the
output should be version-controlled.

Primary cause: taxonomy overlap between a newly produced file and a generated
artifact whose repository presence is not required.

### B008: glob pattern

- Human: `non_file_reference`
- LLM: `ambiguous_reference`
- Path: `biu/src/service/fav-resource*.ts`

The string is a glob referring to a family of files rather than one literal
path. The category definition for `non_file_reference` includes patterns, but
the prompt's decision rules say that a glob is ambiguous unless its context is
unequivocal. The human followed the category definition; the model followed
the more specific glob rule.

Primary cause: an internal boundary conflict in the rubric.

### B011: repository unavailable at review time

- Human: `inaccessible_or_invalid`
- LLM: `confirmed_exists`
- Path: `backend/app/main.py`

The human could not access the repository. The LLM was not given live access
and received `path_resolved_at_anchor` from SpecMine, so it classified the path
as existing. Both responses are coherent relative to their evidence. This is
not a clean test of semantic classification because the human judged current
accessibility while the model consumed the archived resolution signal.

Primary cause: temporal access and evidence asymmetry.

### B017: explicit creation language plus an existing file

- Human: `confirmed_exists`
- LLM: `expected_absence_create`
- Path: `docs/privacy/index.html`

The path resolved at the anchor commit, while the task explicitly says to
write the file. The human prioritized observed repository state. The LLM
followed the prompt rule that explicit creation language takes precedence.
The label `expected_absence_create` is semantically awkward when the file is
known to exist, showing that the taxonomy combines two axes in one category.

Primary cause: overlap between observed state and task intent.

### B018: explicit module creation

- Human: `ambiguous_reference`
- LLM: `expected_absence_create`
- Path: `python/carnot/inference/ebt_embeddings.py`

The task describes creating a module at the named path. The model applied the
explicit-action rule. The human note recognized that the path was a planned
new module but retained uncertainty. This disagreement reflects different
thresholds for using the uncertainty category rather than missing evidence.

Primary cause: reviewer conservatism despite explicit creation language.

### B020: pending modification of an absent path

- Human: `non_file_reference`
- LLM: `confirmed_missing_problematic`
- Path: `pokemon_team_builder/cli.py`

The record clearly names a file and asks for a CLI flag to be added, so
`non_file_reference` does not match the literal semantics of the string. At
the same time, the task is open. An absent target in unfinished work is not
necessarily implementation friction. The model treated the absence as
problematic because the task did not say to create the file. The taxonomy has
no category for a pending modification whose target is currently absent.

Primary cause: a missing category for unfinished modification work, which
forced both sides toward imperfect labels.

### B023: explicit creation language plus an existing file

- Human: `confirmed_exists`
- LLM: `expected_absence_create`
- Path: `web/app/api/session/route.ts`

As in B017, the path resolved at the anchor commit and the task says to create
it. The human prioritized state; the model prioritized task intent. Neither
flat label records both facts.

Primary cause: overlap between observed state and task intent.

### B024: generated TypeScript output

- Human: `non_file_reference`
- LLM: `expected_absence_create`
- Path: `tokens/compiled/tokens.ts`

The task says that a stub writes this output. It is a concrete file, but it is
generated at runtime and may not be intended for version control. The human
used `non_file_reference` to express that it is not a source file expected in
the repository. The model used `expected_absence_create` because the task
explicitly produces it. The taxonomy does not distinguish source targets from
generated outputs.

Primary cause: taxonomy overlap for generated artifacts.

### B026: decisive evidence outside the LLM excerpt

- Human: `expected_absence_move_or_delete`
- LLM: `ambiguous_reference`
- Path: `script/latest_android_sdk_build_tools.sh`

The bounded excerpt shown to the LLM included the first occurrence, which only
asked the developer to confirm that the script had no callers. The full task
later contains an explicit instruction to delete the script. The human could
open the full task and observe this instruction. The model therefore lacked
the evidence required by its own precedence rule.

Primary cause: context-window extraction selected the first mention rather
than the decisive mention.

### B028: suffix pattern for generated files

- Human: `ambiguous_reference`
- LLM: `non_file_reference`
- Path: `.mapper.dart`

The string is a suffix shared by multiple generated Dart files, not a unique
repository path. The model treated it as a non-file pattern; the human treated
it as ambiguous. This mirrors B008 and again shows that the rubric does not
draw a stable boundary between patterns and ambiguous paths.

Primary cause: boundary conflict between pattern and ambiguity categories.

### B030: resolution signal without reproducible resolved path

- Human: `ambiguous_reference`
- LLM: `confirmed_exists`
- Path: `slides/index.tsx`

SpecMine reports `exists_at_anchor = 1`, but `resolved_path` is null. The task
context indicates that report code lives under
`app/client/src/pages/report/`, while the literal root-level GitHub URL returns
404. The LLM trusted the automatic existence signal. The human could not
reconstruct the path represented by that signal and retained ambiguity.

Primary cause: resolver-provenance gap. An existence flag without the resolved
repository path cannot be independently reproduced in this case.

## Cross-case findings

### 1. The categories are not mutually exclusive

`confirmed_exists` records repository state. `expected_absence_create` and
`expected_absence_move_or_delete` record task intent. A path can exist at the
anchor commit while the associated task says to create it, as B017 and B023
demonstrate. A single flat label cannot preserve both observations.

### 2. Generated artifacts require their own semantic treatment

B002 and B024 refer to concrete files produced by programs. They are neither
ordinary non-file references nor necessarily version-controlled source files.
Generated output should not be treated as implementation friction merely
because it is absent from Git.

### 3. Glob and suffix patterns have an unstable category boundary

B008 and B028 show that `non_file_reference` and `ambiguous_reference` overlap
for multi-file patterns. The rubric definition and its more specific decision
rule lead to different reasonable choices.

### 4. Evidence equivalence matters

B026 shows that a bounded excerpt can omit the decisive action. B011 shows a
difference between live accessibility and archived resolver evidence. B030
shows that `exists_at_anchor` is not independently auditable when the resolved
path is missing. Raw agreement therefore measures the full evidence pipeline,
not only model reasoning.

### 5. LLM confidence did not identify disagreements

The mean reported confidence was 0.961 for agreements and 0.957 for
disagreements. High self-reported confidence cannot be used to route only
uncertain cases to a human reviewer in this sample.

## Recommended two-axis representation

Future coding should separate the two constructs currently combined in the
seven labels.

### Axis A: repository evidence

- `resolved`
- `unresolved`
- `inaccessible`
- `resolution_provenance_missing`

### Axis B: semantic role of the reference

- `modify_existing`
- `create_source`
- `move_or_delete`
- `generated_output`
- `multi_file_pattern`
- `external_or_non_file`
- `unclear`

A conservative friction candidate can then be derived rather than directly
annotated. One possible rule is:

```text
repository evidence = unresolved
AND semantic role = modify_existing
AND task status = completed
AND no explicit alternative, generation, move, or deletion instruction
```

This derived rule keeps observable repository state separate from human or LLM
interpretation and makes disagreements easier to diagnose.

## Implications for the current study

1. Keep the original seven-category results unchanged as the preregistered or
   frozen-prompt comparison.
2. Describe 63.3% agreement and kappa 0.553 as performance of the complete
   bounded-context classification pipeline, not pure LLM accuracy.
3. Do not scale `confirmed_missing_problematic` prevalence from the LLM output;
   the human sample contains only one positive case.
4. Use the 1/20 human result to show that literal path absence is not equivalent
   to semantic implementation friction, with its wide uncertainty interval.
5. Treat the two-axis coding scheme as a post-hoc construct refinement. If it
   is used for a new confirmatory analysis, freeze it before drawing and
   reviewing a new sample.

