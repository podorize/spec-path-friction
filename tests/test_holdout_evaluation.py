import unittest

from src.analyze_holdout_v1 import metrics_from_cells, wilson


class HoldoutEvaluationTests(unittest.TestCase):
    def test_end_to_end_recall_counts_abstained_positives(self):
        metrics = metrics_from_cells(
            {
                "predicted_problematic:problematic": 5,
                "predicted_problematic:non_problematic": 0,
                "predicted_non_problematic:problematic": 34,
                "predicted_non_problematic:non_problematic": 153,
                "pipeline_abstention:problematic": 9.6,
                "pipeline_abstention:non_problematic": 38.4,
            }
        )
        self.assertAlmostEqual(metrics["precision"], 1.0)
        self.assertAlmostEqual(metrics["end_to_end_recall"], 5 / 48.6)
        self.assertAlmostEqual(metrics["covered_case_recall"], 5 / 39)

    def test_wilson_interval_for_five_of_five_is_not_degenerate(self):
        low, high = wilson(5, 5)
        self.assertGreater(low, 0.5)
        self.assertLess(low, 1.0)
        self.assertAlmostEqual(high, 1.0)

    def test_zero_denominator_metrics_are_explicitly_unavailable(self):
        metrics = metrics_from_cells({})
        self.assertIsNone(metrics["precision"])
        self.assertIsNone(metrics["end_to_end_recall"])


if __name__ == "__main__":
    unittest.main()
