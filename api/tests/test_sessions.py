import tempfile
from unittest.mock import patch
import unittest
from pathlib import Path
from api.session_service import Backend,ApiError

class SessionTests(unittest.TestCase):
    def setUp(self):
        self.mode=patch.dict("os.environ", {"GIGCA_DATA_MODE":"simulation"});self.mode.start()
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'test.sqlite3'
        self.backend=Backend(self.path);self.s=self.backend.create()
    def tearDown(self):self.tmp.cleanup();self.mode.stop()
    def update(self,**extra):
        return self.backend.update(self.s['session_id'],self.s['token'],{'context_version':0,'current_lat':10.7769,'current_lng':106.7009,**extra})
    def test_persistent_run_and_idempotency(self):
        self.update();payload={'session_id':self.s['session_id'],'context_version':1}
        result=self.backend.run(self.s['session_id'],self.s['token'],payload,'key')
        restored=Backend(self.path)
        self.assertEqual(result,restored.run(self.s['session_id'],self.s['token'],payload,'key'))
        self.assertEqual(result,restored.get(result['recommendation_id'],self.s['session_id'],self.s['token']))
        self.assertEqual(len(result['objectives']),4)
        self.assertTrue(result['is_demo'])
    def test_session_isolation(self):
        self.update();result=self.backend.run(self.s['session_id'],self.s['token'],{'context_version':1})
        other=self.backend.create()
        with self.assertRaises(ApiError) as error:self.backend.get(result['recommendation_id'],other['session_id'],other['token'])
        self.assertEqual(error.exception.status,404)
        with self.assertRaises(ApiError):self.backend.history(self.s['session_id'],other['token'])
    def test_requires_origin(self):
        with self.assertRaises(ApiError) as error:self.backend.run(self.s['session_id'],self.s['token'],{'context_version':0})
        self.assertEqual(error.exception.code,'origin_required')
    def test_conflict_and_invalid_numbers(self):
        for value in (True,float('nan'),91):
            with self.assertRaises(ApiError):self.update(current_lat=value)
        self.update()
        with self.assertRaises(ApiError):self.update()
    def test_waiting_clock_version(self):
        self.update()
        result=self.backend.waiting(self.s['session_id'],self.s['token'],{'action':'start','context_version':1})
        self.assertEqual(result['context_version'],2)
        output=self.backend.run(self.s['session_id'],self.s['token'],{'context_version':2})
        self.assertEqual(output['input_used']['idle_duration_min'],0)
