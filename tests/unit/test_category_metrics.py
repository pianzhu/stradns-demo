"""Tests for category coverage and gating recall metrics."""

import unittest

from context_retrieval.category_metrics import ( # type: ignore
    CategoryCoverage,
    MappingStats,
    RecallCase,
    RecallComparison,
    compare_gating_recall,
    compute_category_coverage,
    compute_mapping_stats,
)


class TestCategoryCoverage(unittest.TestCase):
    """Tests for category coverage stats."""

    def test_counts_and_rates(self):
        """Counts categories across components and computes rates."""
        items = [
            {
                "components": [
                    {"categories": []},
                    {"categories": [{"name": "Light"}]},
                ]
            },
            {"components": [{"categories": []}]},
            {"components": []},
            {"components": [{"categories": [{"name": "Blind"}]}]},
        ]

        stats = compute_category_coverage(items)

        self.assertIsInstance(stats, CategoryCoverage)
        self.assertEqual(stats.total, 4)
        self.assertEqual(stats.with_category, 2)
        self.assertEqual(stats.missing, 2)
        self.assertAlmostEqual(stats.coverage_rate, 0.5)
        self.assertAlmostEqual(stats.missing_rate, 0.5)


class TestMappingStats(unittest.TestCase):
    """Tests for type hint mapping stats."""

    def test_hit_and_trigger_rates(self):
        """Computes hit rate from non-empty hints and trigger rate overall."""
        type_hints = ["light", "ac", "unknown", "", None]
        mapping = {"light": "Light", "ac": "AirConditioner"}

        stats = compute_mapping_stats(type_hints, mapping)

        self.assertIsInstance(stats, MappingStats)
        self.assertEqual(stats.total, 5)
        self.assertEqual(stats.with_type_hint, 3)
        self.assertEqual(stats.hits, 2)
        self.assertAlmostEqual(stats.hit_rate, 2 / 3)
        self.assertAlmostEqual(stats.trigger_rate, 2 / 5)


class TestGatingRecallComparison(unittest.TestCase):
    """Tests for hard vs soft gating recall curves."""

    def test_recall_curve(self):
        """Computes recall@k for hard and soft gating."""
        cases = [
            RecallCase(
                expected_ids=["cap_on"],
                hard_ranked_ids=["cap_off", "cap_on"],
                soft_ranked_ids=["cap_on"],
            ),
            RecallCase(
                expected_ids=["cap_dim"],
                hard_ranked_ids=["cap_off"],
                soft_ranked_ids=["cap_dim", "cap_off"],
            ),
        ]

        result = compare_gating_recall(cases, k_values=[1, 2])

        self.assertIsInstance(result, RecallComparison)
        self.assertAlmostEqual(result.hard[1], 0.0)
        self.assertAlmostEqual(result.hard[2], 0.5)
        self.assertAlmostEqual(result.soft[1], 1.0)
        self.assertAlmostEqual(result.soft[2], 1.0)


if __name__ == "__main__":
    unittest.main()
