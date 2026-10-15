import unittest

from experiments.synthetic.parameter_search import configurations


class ConfigurationTests(unittest.TestCase):
    def test_deterministic_unique_and_includes_baseline(self):
        rows = configurations(30, 7)
        self.assertEqual(rows, configurations(30, 7))
        self.assertEqual(len({tuple(sorted(r.items())) for r in rows}), 30)
        self.assertEqual(rows[0], dict(learning_rate=0.06, max_depth=2, min_samples_leaf=8, subsample=0.8))

    def test_invalid_budget(self):
        for budget in (0, -1, 101):
            with self.assertRaises(ValueError):
                configurations(budget, 7)
