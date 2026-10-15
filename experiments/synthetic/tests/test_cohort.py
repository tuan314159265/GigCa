import unittest
from experiments.synthetic.cohort import cohort_prompt, design, validate_slots
from experiments.synthetic.personas import reference_personas


class CohortTests(unittest.TestCase):
    def test_balanced_cells_and_independent_pickup_bands(self):
        slots = design(2)
        self.assertEqual(len(slots), 32)
        self.assertEqual(len({s['cell'] for s in slots}), 16)
        for axis in ('shift', 'work', 'strategy', 'rain'):
            values = {s[axis] for s in slots}
            self.assertTrue(all(sum(s[axis] == v for s in slots) == 16 for v in values))
        self.assertIn('not PAFT', cohort_prompt(slots[:4])['prompt'])

    def test_design_validation(self):
        slots = design(1)
        doc = reference_personas(16)
        for row, slot in zip(doc['personas'], slots):
            row['driver_id'] = slot['driver_id']
            row['home_zone'] = slot['home_zone']
            row['preferred_zones'] = [slot['home_zone'], 'Z2' if slot['home_zone'] != 'Z2' else 'Z1']
            for key, (low, high) in slot['bounds'].items():
                row[key] = (low + high) / 2
        validate_slots(doc, slots)
        doc['personas'][0]['rain_tolerance_mm'] = 7
        with self.assertRaisesRegex(ValueError, 'outside prescribed cell'):
            validate_slots(doc, slots)
