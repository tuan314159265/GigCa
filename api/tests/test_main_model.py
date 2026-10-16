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

    def test_live_destinations_replace_named_anchors_without_changing_model_money(self):
        live = {'id':'live_test','name':'Địa điểm API','lat':10.775,'lng':106.699,'candidate_source':'tomtom_live'}
        with patch('api.main_model.load_saved_model',return_value=(self.model,self.report,self.catalog)), \
             patch('api.live_candidates.discover',return_value=([live],{'status':'ok'})):
            out=apply_main_model(self.base,self.data,self.ctx,self.prefs,use_live_candidates=True)
        self.assertEqual({a['id'] for a in out.ml_insights['areas']},{'model_current','live_test'})
        self.assertEqual(out.ml_insights['candidate_discovery']['status'],'ok')
        self.assertEqual(out.objectives['max_trip_value'].candidates[0].yield_vnd_per_hour,50000)
        self.assertNotIn('a',[c.area_id for c in out.objectives['max_trip_value'].candidates])
        candidate=next(c for c in out.objectives['max_trip_value'].candidates if c.area_id=='live_test')
        self.assertGreater(candidate.reposition_km,0)
        self.assertGreater(candidate.reposition_min,0)
        current=next(c for c in out.objectives['max_trip_value'].candidates if c.area_id=='model_current')
        self.assertEqual(current.reposition_km,0)

    def test_live_provider_failure_does_not_silently_reuse_fixed_destinations(self):
        with patch('api.main_model.load_saved_model',return_value=(self.model,self.report,self.catalog)), \
             patch('api.live_candidates.discover',side_effect=OSError('timeout')):
            out=apply_main_model(self.base,self.data,self.ctx,self.prefs,use_live_candidates=True)
        self.assertEqual([a['id'] for a in out.ml_insights['areas']],['model_current'])
        self.assertEqual(out.ml_insights['candidate_discovery']['status'],'provider_unavailable')

    def test_poi_changes_both_rankings_without_inflating_ml_money(self):
        target={'id':'near','name':'Trường gần đây','lat':self.ctx.current_lat+.001,'lng':self.ctx.current_lng}
        self.catalog['areas']=[target]
        origin={'id':'model_current','name':'Vị trí hiện tại','lat':self.ctx.current_lat,'lng':self.ctx.current_lng}
        context=lambda score:{'score':score,'components':[],'policy_version':'test','available':True}
        with patch('api.main_model.load_saved_model',return_value=(self.model,self.report,self.catalog)), patch('api.poi_policy.build_contexts',return_value=([origin,target],{'model_current':context(0),'near':context(90)},True)):
            out=apply_main_model(self.base,self.data,self.ctx,self.prefs,use_poi=True)
        for key in ('max_trip_value','maintain_position'):
            self.assertEqual(out.objectives[key].candidates[0].area_id,'near')
            self.assertEqual(out.objectives[key].plan.key_metrics['yield_vnd_per_hour'],50000)
            self.assertEqual(out.objectives[key].plan.key_metrics['ranking_method'],'ml_poi_secondary_tiebreak')
        self.assertEqual(out.objectives['max_trip_value'].candidates[0].yield_low_vnd_per_hour,20000)

    def test_poi_cannot_reverse_clear_ml_income_advantage_or_force_far_move(self):
        target={'id':'far','name':'Khu vực khác','lat':self.ctx.current_lat+.007,'lng':self.ctx.current_lng}
        self.catalog['areas']=[target]
        class DifferentCycle:
            def predict(_,dt,lat,lng,rain):
                median=60000 if lat>self.ctx.current_lat+.003 else 50000
                return {'low':20000,'median':median,'high':80000}
        self.model['cycle_model']=DifferentCycle()
        origin={'id':'model_current','name':'Vị trí hiện tại','lat':self.ctx.current_lat,'lng':self.ctx.current_lng}
        context=lambda score:{'score':score,'components':[],'available':True}
        with patch('api.main_model.load_saved_model',return_value=(self.model,self.report,self.catalog)), patch('api.poi_policy.build_contexts',return_value=([origin,target],{'model_current':context(100),'far':context(0)},True)):
            out=apply_main_model(self.base,self.data,self.ctx,self.prefs,use_poi=True)
        self.assertEqual(out.objectives['max_trip_value'].candidates[0].area_id,'far')
        self.assertEqual(out.objectives['maintain_position'].candidates[0].area_id,'model_current')
        self.assertEqual(len(out.objectives['max_trip_value'].candidates),2)

    def test_poi_provider_failure_keeps_original_candidate_pool_and_rank(self):
        with patch('api.main_model.load_saved_model',return_value=(self.model,self.report,self.catalog)), patch('api.poi_policy.build_contexts',return_value=([],{},False)):
            out=apply_main_model(self.base,self.data,self.ctx,self.prefs,use_poi=True)
        self.assertEqual(out.objectives['maintain_position'].candidates[0].area_id,'model_current')
        self.assertEqual(len(out.objectives['maintain_position'].candidates),2)
        self.assertFalse(out.ml_insights['poi_ranking']['enabled'])

    def test_dashboard_uses_saved_model_and_ignores_personal_training_records(self):
        from api.dashboard import recommend
        from api.tests.test_live import LiveTests
        provider=LiveTests()
        provider.calls=[]
        from data.live_collector import _cache
        _cache.clear()
        with patch('api.main_model.load_saved_model',return_value=(self.model,self.report,self.catalog)), \
             patch('api.live_candidates.discover',return_value=([],{'status':'no_supported_candidates'})), \
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
