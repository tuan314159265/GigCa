import unittest
from unittest.mock import patch
from dataclasses import asdict, replace

from api.main_model import apply_main_model
from engine.src.engine import run_driver_engine
from engine.src.types import DriverContext, DriverPreferences, EngineInput


class Wait:
    def predict(self, *args):
        return {'p_le':{'10':.5, '20':.8}, 'expected_wait_min':12, 'median_wait_min':10}


class Cycle:
    def predict(self, *args):
        return {'low':20000, 'median':50000, 'high':80000}


class MainModelTests(unittest.TestCase):
    def setUp(self):
        self.data = EngineInput([], [], [], {}, {}, generated_at='2026-10-15T08:00:00+07:00')
        self.ctx = DriverContext(10.773,106.699)
        self.prefs = DriverPreferences()
        self.base = run_driver_engine(self.data,self.ctx,self.prefs)
        self.model = {'wait_model':Wait(), 'cycle_model':Cycle()}
        self.report = {'artifact_sha256':'test', 'test':{'cycle_coverage':.758,
            'cycle_mae_vnd_per_hour':22000,'cycle_mean_baseline_mae':25000},
            'counts':{'train':{'cycles':2402,'waits':4514},'test':{'cycles':396}}}
        self.catalog = {'training_hours':[8], 'areas':[{'id':'a','name':'Điểm neo giả định', 'lat':10.78,'lng':106.70}]}

    def apply(self, data=None, ctx=None):
        with patch('api.main_model.load_saved_model', return_value=(self.model,self.report,self.catalog)):
            return apply_main_model(self.base,data or self.data,ctx or self.ctx,self.prefs)

    def test_no_personal_history_needed_and_sources_explicit(self):
        with patch('engine.src.ml.wait_model.WaitHazardModel.fit', side_effect=AssertionError('must not fit')):
            out=self.apply()
        self.assertIsNotNone(out.objectives['max_trip_value'].plan)
        self.assertIsNotNone(out.objectives['maintain_position'].plan)
        self.assertIsNone(out.personal_model)
        self.assertEqual(out.ml_insights['source'],'synthetic_base_model')
        self.assertFalse(out.ml_insights['cycle_yield']['backtest']['calibrated'])
        self.assertEqual(out.objectives['rest_spot'],self.base.objectives['rest_spot'])
        self.assertEqual(out.objectives['safety_comfort'],self.base.objectives['safety_comfort'])
        self.assertIsNone(out.objectives['max_trip_value'].candidates[0].expected_net_value_vnd)
        asdict(out)

    def test_outside_training_area_or_hours_has_reason(self):
        for data,ctx in [(self.data,DriverContext(21,105)),
                         (replace(self.data,generated_at='2026-10-15T03:00:00+07:00'),self.ctx)]:
            out=self.apply(data,ctx)
            self.assertEqual(out.ml_insights['status'],'unavailable')
            self.assertIsNone(out.objectives['max_trip_value'].plan)
            self.assertTrue(out.objectives['max_trip_value'].reason_for_insufficiency)

    def test_missing_model_no_personal_fallback(self):
        with patch('api.main_model.load_saved_model',side_effect=OSError('missing artifact')):
            out=apply_main_model(self.base,self.data,self.ctx,self.prefs)
        self.assertFalse(out.ml_insights['wait_model']['used'])
        self.assertIn('missing artifact',out.objectives['max_trip_value'].reason_for_insufficiency)

    def test_zero_reposition_retains_current_point(self):
        out=self.apply(ctx=replace(self.ctx,max_reposition_km=0))
        self.assertEqual([c.area_id for c in out.objectives['max_trip_value'].candidates],['model_current'])

    def test_dashboard_uses_saved_model_and_ignores_personal_training_records(self):
        from api.dashboard import recommend
        from api.tests.test_live import LiveTests
        provider=LiveTests()
        provider.calls=[]
        from data.live_collector import _cache
        _cache.clear()
        with patch('api.main_model.load_saved_model',return_value=(self.model,self.report,self.catalog)), \
             patch('data.live_collector.fetch_json',side_effect=provider.response), \
             patch('api.provider_proxy.read_tomtom_key',return_value='test'), \
             patch('data.live_collector.datetime') as clock:
            # Provider snapshot must use a time within the fake model's support.
            from datetime import datetime,timezone
            clock.now.return_value=datetime(2026,10,15,1,tzinfo=timezone.utc)
            clock.fromisoformat.side_effect=datetime.fromisoformat
            result=recommend({'mode':'live','context':{'current_lat':10.773,'current_lng':106.699}},
                personal_input={'trip_log':[{'bad':'not used'}],'wait_spells':[{'bad':'not used'}]},include_snapshot=True)
        self.assertEqual(result['_input_snapshot']['trip_log'],[])
        self.assertEqual(result['_input_snapshot']['wait_spells'],[])
        self.assertIsNotNone(result['objectives']['max_trip_value']['plan'])
