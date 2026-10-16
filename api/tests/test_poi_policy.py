import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

from api.poi_policy import opportunity, rank_values, build_contexts
from engine.src.types import DriverContext


def groups(category, n=4):
    return [{'category':category,'label':category,'fetch_status':'ok','pois':[
        {'id':str(i),'name':f'Place {i}','distance_m':100,'lat':10.771,'lng':106.7} for i in range(n)]}]


class PoiPolicyTests(unittest.TestCase):
    def test_time_and_weekend_change_school_context_without_asserting_demand(self):
        weekday=opportunity(groups('school'),datetime(2026,10,15,17))
        late=opportunity(groups('school'),datetime(2026,10,15,21))
        weekend=opportunity(groups('school'),datetime(2026,10,17,17))
        self.assertGreater(weekday['score'],late['score'])
        self.assertGreater(weekday['score'],weekend['score'])
        self.assertTrue(weekday['not_measured_demand'])

    def test_half_hour_peak_boundaries_use_arrival_time(self):
        for hour,minute,expected in [(6,29,False),(6,30,True),(7,29,True),(7,30,False),
                                     (16,0,True),(17,29,True),(17,30,False)]:
            out=opportunity(groups('office'),datetime(2026,10,15,hour,minute))
            self.assertEqual(out['reference_commute_window'],expected,(hour,minute))

    def test_shopping_is_more_relevant_in_evening_than_early_morning(self):
        self.assertGreater(opportunity(groups('shopping'),datetime(2026,10,15,19))['score'],
                           opportunity(groups('shopping'),datetime(2026,10,15,7))['score'])

    def test_missing_is_not_zero_opportunity(self):
        out=opportunity([{'fetch_status':'unavailable','pois':[]}],datetime(2026,10,15,17))
        self.assertIsNone(out['score'])
        self.assertFalse(out['available'])

    def test_distance_cost_can_outweigh_context_bonus(self):
        origin={'score':0};strong={'score':90}
        staying=rank_values(50000,32,SimpleNamespace(minutes=0,cost_vnd=0),origin,origin,60)
        nearby=rank_values(50000,31.9,SimpleNamespace(minutes=1,cost_vnd=200),strong,origin,60)
        distant=rank_values(50000,20,SimpleNamespace(minutes=25,cost_vnd=10000),strong,origin,60)
        self.assertGreater(nearby['income'],staying['income'])
        self.assertLess(distant['effective_yield_vnd_per_hour'],staying['effective_yield_vnd_per_hour'])
        self.assertLess(distant['position'],staying['position'])
        self.assertGreater(nearby['position'],staying['position'])

    def test_point_outside_model_support_cannot_be_added_as_poi_candidate(self):
        area={'id':'model_current','name':'Origin','lat':10.77,'lng':106.7}
        raw=groups('school');raw[0]['pois'][0].update(lat=10.8,lng=106.7)
        with patch('api.llm_explanations.poi_context',return_value=raw):
            areas,contexts,active=build_contexts([area],DriverContext(10.77,106.7,max_reposition_km=10),
                datetime(2026,10,15,17),[area])
        self.assertEqual(len(areas),1)
        self.assertTrue(active)
