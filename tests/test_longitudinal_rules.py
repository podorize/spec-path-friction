from __future__ import annotations

import unittest

from src.classify_reference_rules import classify_record
from src.prepare_hybrid_judge_batch import partition


def evidence(path: str = "src/new.py", **overrides):
    record = {
        "repo_name": "owner/repo",
        "literal_code_path": path,
        "task_context": "Implement the requested change.",
        "anchor_task_observation": {"status": "found", "content_excerpt": ""},
        "literal_path_observation": {"status": "not_found"},
        "resolved_candidate_observation": {"status": "not_applicable"},
        "repository_tree_observation": {"status": "available", "matching_paths_at_anchor": []},
        "anchor_commit_observation": {"status": "found", "message": "feature work"},
        "path_history_observation": {"status": "available", "commits": []},
        "explicit_repository_mentions": [],
        "evidence_gaps": [],
    }
    record.update(overrides)
    return record


class LongitudinalRuleTests(unittest.TestCase):
    def test_existing_literal_path_is_confirmed(self):
        record = evidence(literal_path_observation={"status": "found"})
        self.assertEqual(classify_record(record)["classification"], "confirmed_exists")

    def test_retirement_language_explains_absence(self):
        record = evidence(
            path="TESTS/DisabledBenchmarks/TopoRelaxGmgEquivalence.cpp",
            task_context="Delete GMG-specific sources and fixtures in DisabledBenchmarks/*Gmg*.",
            anchor_commit_observation={"status": "found", "message": "retire GMG solver and tests"},
        )
        result = classify_record(record)
        self.assertEqual(result["classification"], "expected_absence_move_or_delete")
        self.assertEqual(result["rule_id"], "R5_LIFECYCLE_RETIRE")

    def test_created_after_anchor_requires_create_language(self):
        record = evidence(
            task_context="Create compendium/wiki/page.py with the Page model.",
            path_history_observation={"status": "available", "commits": [{"relation_to_anchor": "after_anchor"}]},
        )
        self.assertEqual(classify_record(record)["classification"], "expected_absence_create")

    def test_bare_missing_filename_abstains(self):
        result = classify_record(evidence(path="Main.ts"))
        self.assertEqual(result["decision"], "abstain")
        self.assertEqual(result["classification"], "ambiguous_reference")

    def test_external_repository_is_classified(self):
        record = evidence(explicit_repository_mentions=["other/frontend"])
        self.assertEqual(classify_record(record)["classification"], "external_repository_reference")

    def test_inaccessible_core_evidence_abstains(self):
        record = evidence(literal_path_observation={"status": "inaccessible"}, evidence_gaps=["literal_path"])
        self.assertEqual(classify_record(record)["classification"], "inaccessible_or_invalid")

    def test_unresolved_local_path_goes_to_llm(self):
        result = classify_record(evidence(path="src/feature/missing.ts"))
        self.assertEqual(result["decision"], "requires_llm")
        self.assertIsNone(result["classification"])

    def test_hybrid_partition_keeps_routes_disjoint(self):
        records = [
            {"review_id": "A", **evidence(literal_path_observation={"status": "found"})},
            {"review_id": "B", **evidence(path="Main.ts")},
            {"review_id": "C", **evidence(path="src/missing.ts")},
        ]
        result = partition(records)
        self.assertEqual({key: len(value) for key, value in result.items()}, {"rule_decisions": 1, "abstentions": 1, "llm_queue": 1})


if __name__ == "__main__":
    unittest.main()
