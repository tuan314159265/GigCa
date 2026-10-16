import unittest

from experiments.synthetic.train_base import driver_split


class DriverSplitTest(unittest.TestCase):
    def test_types_and_unseen_driver_holdouts(self):
        slots = [{'driver_id': f'D{i:03}', 'cell': f'C{(i+1)//2:02}'} for i in range(1, 33)]
        ids = [s['driver_id'] for s in slots]
        split = driver_split(ids, slots, 7)
        self.assertEqual(split, driver_split(ids, slots, 7))
        self.assertEqual([len(split[k]) for k in ('train', 'validation', 'test')], [16, 8, 8])
        self.assertEqual(len(set(sum(split.values(), []))), 32)
        self.assertEqual({s['cell'] for s in slots if s['driver_id'] in split['train']}, {s['cell'] for s in slots})

    def test_missing_design_is_rejected(self):
        with self.assertRaises(ValueError):
            driver_split(['D001'], [], 7)
