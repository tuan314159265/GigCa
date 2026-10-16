import json
import os
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from api.errors import ApiError
from api.research_demo import catalog, recommend_demo
from engine.src.ml.insights import build_ml_insights
from engine.src.personal_model import PersonalModelResult
from engine.src.types import EngineInput
from experiments.synthetic.generator import generate, write_dataset
from experiments.synthetic.personas import reference_personas


class ResearchDemoTests(unittest.TestCase):
    def test_disabled_and_invalid_driver_are_rejected(self):
        with patch.dict(os.environ, {'GIGCA_RESEARCH_DEMO': 'false'}):
            with self.assertRaises(ApiError):
                catalog()
        with self.assertRaises(ApiError):
            recommend_demo({'driver_id': '../backend.sqlite3'})

    def test_demo_replays_tagged_history_without_production_import(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'dataset'
            data = generate(reference_personas(1), end_date=date(2026, 10, 13), days=14)
            write_dataset(data, root)
            with patch.dict(os.environ, {'GIGCA_RESEARCH_DEMO': 'true', 'GIGCA_RESEARCH_DATASET': str(root)}):
                self.assertEqual(len(catalog()['drivers']), 1)
                result = recommend_demo({'driver_id': 'D01'})
                self.assertTrue(result['is_demo'])
                self.assertEqual(result['snapshot']['mode'], 'research')
                self.assertEqual(result['research_driver_id'], 'D01')
                self.assertGreater(datetime.fromisoformat(result['generated_at']).date(), date(2026, 10, 13))
                self.assertTrue(all(h['precipitation_probability_pct'] is None for h in result['weather']))
                json.dumps(result, allow_nan=False)
                with self.assertRaises(ApiError):
                    recommend_demo({'driver_id': 'D01', 'context': {'current_lat': float('nan')}})

    def test_unverified_coverage_does_not_enable_income_band(self):
        inp = EngineInput([], [], [], {}, {}, trip_log=[SimpleNamespace(
            started_at='2026-10-13T08:00:00+07:00', pickup_lat=10.77, pickup_lng=106.7,
            net_vnd=45000, duration_min=20, distance_km=5)])
        pm = PersonalModelResult(economics=SimpleNamespace(fuel_cost_vnd_per_km=500))
        with patch('engine.src.ml.insights.backtest_wait', return_value={'status': 'insufficient'}), \
             patch('engine.src.ml.insights.build_cycles', return_value=[]), \
             patch('engine.src.ml.insights.backtest_cycles', return_value={'status': 'ok', 'calibrated': None}), \
             patch('engine.src.ml.insights.fit_cycle_model') as fit:
            _, info = build_ml_insights(inp, pm, datetime(2026, 10, 14, 8))
            fit.assert_not_called()
            self.assertEqual(info['cycle_yield']['zones'], [])
