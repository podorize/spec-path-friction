# False-positive audit: evidence-equivalent GPT-6 Sol

These are the six accessible cases that GPT-6 Sol classified as `confirmed_missing_problematic` while the final human reference assigned another label. There were no false negatives in the 57-case binary subset.

| Case | Human reference | Path | Main explanation |
|---|---|---|---|
| H017 | `ambiguous_reference` | `packages/shared-types/src/node-types.ts` | The task describes a TypeScript monorepo, but the anchor repository is a Go project. The reference may belong to another repository or an unimplemented plan; the evidence does not establish a defect. |
| H025 | `expected_absence_move_or_delete` | `TopoRelaxGmgEquivalence.cpp` | The archived `remove-gmg-stokes-solver` task at the anchor explicitly deletes `DisabledBenchmarks/*Gmg*` fixtures. The path is absent because the GMG implementation and its tests were retired. |
| H027 | `expected_absence_create` | `compendium/wiki/page.py` | The next commit adds the Page model. The anchor is the planning stage, so absence is expected. |
| H047 | `ambiguous_reference` | `Main.ts` | The task names a file absent from the complete tree, but the available evidence does not establish whether it belongs to another location or repository. |
| H067 | `non_file_reference` | `loading-sequence.ts` | The task migrates code from a separate frontend repository; the path is external to the SpecMine repository. |
| H074 | `expected_absence_create` | `src/screens/wallet/WalletHomeScreen.tsx` | The file is introduced after the anchor commit as part of a new application plan. The completed checkbox reflects a later state, not a defect at the anchor. |

## Pattern

All six errors are false positives caused by temporal or repository-boundary reasoning:

- planned creation or explicit retirement interpreted as a missing implementation;
- a task file marked complete at a later commit compared with an earlier anchor;
- a path belonging to another repository;
- insufficient evidence to distinguish an external reference from a broken local path.

This suggests adding explicit temporal and repository-boundary evidence before scaling the judge, rather than treating the six cases as random model failures.

The H025 semantic correction does not change the binary result: it remains
non-problematic. The accessible binary confusion matrix is therefore still
`[[46, 6], [0, 5]]` (TN, FP / FN, TP), with positive precision `5/11 = 45.5%`.
