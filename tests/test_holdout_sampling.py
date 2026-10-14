from __future__ import annotations

import unittest

from src.create_holdout_human_sample import allocate_counts


class HoldoutAllocationTests(unittest.TestCase):
    def test_balanced_when_every_stratum_has_capacity(self):
        counts = {"predicted_problematic": 50, "pipeline_abstention": 50, "predicted_non_problematic": 140}
        self.assertEqual(allocate_counts(counts), {"predicted_problematic": 30, "pipeline_abstention": 30, "predicted_non_problematic": 30})

    def test_small_positive_stratum_is_exhaustively_reviewed(self):
        counts = {"predicted_problematic": 10, "pipeline_abstention": 30, "predicted_non_problematic": 200}
        allocation = allocate_counts(counts)
        self.assertEqual(allocation["predicted_problematic"], 10)
        self.assertEqual(sum(allocation.values()), 90)
        self.assertLessEqual(allocation["pipeline_abstention"], counts["pipeline_abstention"])

    def test_raises_when_total_capacity_is_insufficient(self):
        with self.assertRaises(ValueError):
            allocate_counts({"predicted_problematic": 10, "pipeline_abstention": 10, "predicted_non_problematic": 10})


if __name__ == "__main__":
    unittest.main()
