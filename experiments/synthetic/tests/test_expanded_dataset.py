import unittest
from datetime import date
from experiments.synthetic.cohort import design
from experiments.synthetic.personas import reference_personas
from experiments.synthetic.expanded_dataset import balanced_plan
from experiments.synthetic.generator import generate
from experiments.synthetic.spatial import contains

class ExpandedTests(unittest.TestCase):
    def test_plan_covers_every_zone_in_each_split(self):
        people=reference_personas(32);slots=design(2)
        for row,slot in zip(people['personas'],slots):row['driver_id']=slot['driver_id']
        people['provenance']['design']={'slots':slots}
        zones={f'P{i}':{'name':str(i),'lat':10.7+i*.001,'lng':106.6} for i in range(47)}
        plan,split,dates,stats=balanced_plan(people,zones,date(2026,10,14),120,7)
        for group in stats:
            ids=split['validation'] if group=='calibration' else split[group]
            days=set(dates['train'] if group=='validation' else dates[group])
            self.assertEqual(set(z for (did,day),z in plan.items() if did in ids and day in days),set(zones))
        self.assertEqual(plan,balanced_plan(people,zones,date(2026,10,14),120,7)[0])
    def test_samples_remain_inside_small_polygon(self):
        people=reference_personas(1)
        zones={'Z1':{'name':'test','lat':10.7,'lng':106.6},'Z2':{'name':'test2','lat':10.7001,'lng':106.6001}}
        people['personas'][0]['preferred_zones']=['Z1','Z2']
        geometry={'type':'Polygon','coordinates':[[[106.5998,10.6998],[106.6002,10.6998],[106.6002,10.7002],[106.5998,10.7002],[106.5998,10.6998]]]}
        plan={(people['personas'][0]['driver_id'],f'2026-10-{d:02}'): 'Z1' for d in range(8,15)}
        out=generate(people,end_date=date(2026,10,14),days=7,zone_catalog=zones,shift_plan=plan,point_allowed=lambda pt:contains(pt,geometry))
        self.assertTrue(all(r['valid'] for r in out['manifest']['validation'].values()))
        for event in out['drivers'][0]['events']:
            self.assertTrue(contains(event['start_point'],geometry));self.assertTrue(contains(event['end_point'],geometry))

if __name__=='__main__':unittest.main()
