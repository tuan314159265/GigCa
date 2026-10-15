import copy
import unittest
from experiments.synthetic.personas import ZONES, reference_personas, validate_personas
from experiments.synthetic.geography import remap_personas
from scripts.build_synthetic_anchor_catalog import inside

class GeographyTests(unittest.TestCase):
    def test_polygon_holes_exclude_points(self):
        geometry={'type':'Polygon','coordinates':[[[0,0],[4,0],[4,4],[0,4],[0,0]],[[1,1],[2,1],[2,2],[1,2],[1,1]]]}
        self.assertTrue(inside(3,3,geometry))
        self.assertFalse(inside(1.5,1.5,geometry))
        self.assertFalse(inside(5,3,geometry))
    def test_remap_does_not_change_original_personas_or_legacy_anchors(self):
        old=copy.deepcopy(ZONES);document=reference_personas(12);original=copy.deepcopy(document)
        zones={f'NEW{i}':{'name':f'Zone {i}','lat':10.7+i*.01,'lng':106.6+i*.01} for i in range(12)}
        remapped=remap_personas(document,zones)
        self.assertEqual(document,original);self.assertEqual(ZONES,old)
        self.assertEqual(len(set(r['home_zone'] for r in remapped['personas'])),12)
        validate_personas(remapped,zones)
        for row in remapped['personas']:
            self.assertEqual(row['preferred_zones'][0],row['home_zone'])
            self.assertLessEqual(len(row['preferred_zones']),6)

if __name__=='__main__': unittest.main()
