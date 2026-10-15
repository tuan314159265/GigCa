import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch

from api.session_service import Backend, ApiError
from api.v1_server import Handler

TRIP = {'trip_id': 'trip-1', 'started_at': '2026-10-13T08:10:00+07:00',
        'pickup_lat': 10.77, 'pickup_lng': 106.7, 'net_vnd': 45000,
        'duration_min': 20, 'distance_km': 5}
WAIT = {'spell_id': 'wait-1', 'start': '2026-10-13T08:00:00+07:00',
        'end': '2026-10-13T08:10:00+07:00', 'lat': 10.77, 'lng': 106.7, 'ended_by': 'trip'}
PASSWORD = 'test-only-password-2026'


class DriverAccountTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'backend.sqlite3'
        self.backend = Backend(self.path)
        # Keep tests fast; production uses 600,000 PBKDF2 iterations.
        self.hashing = patch('api.driver_accounts.PASSWORD_ITERATIONS', 1000)
        self.hashing.start()
        self.a = self.backend.register({'username': 'driver_a', 'password': PASSWORD})
        self.b = self.backend.register({'username': 'driver_b', 'password': PASSWORD})

    def tearDown(self):
        self.hashing.stop()
        self.tmp.cleanup()

    def preview(self, token=None, **kwargs):
        return self.backend.preview_import(token or self.a['token'],
            {'trips': [TRIP], 'wait_spells': [WAIT], 'consent_reference': 'self-submitted',
             'collected_via': 'personal log', **kwargs})

    def run_driver(self, token):
        s = self.backend.create(token)
        self.backend.update(s['session_id'], token, {'context_version': 0,
            'current_lat': 10.77, 'current_lng': 106.7})
        with patch.dict(os.environ, {'GIGCA_DATA_MODE': 'sample'}):
            result = self.backend.run(s['session_id'], token, {'context_version': 1})
        return s, result

    def test_password_and_token_are_not_stored_in_plaintext(self):
        with self.backend.db() as db:
            row = db.execute('SELECT * FROM drivers WHERE id=?', (self.a['driver']['id'],)).fetchone()
            self.assertNotIn(PASSWORD, row['password_hash'])
            self.assertTrue(row['password_hash'].startswith('pbkdf2_sha256$'))
            hashes = [r['token_hash'] for r in db.execute('SELECT token_hash FROM driver_tokens')]
            self.assertNotIn(self.a['token'], hashes)

    def test_login_logout_and_revocation_of_owned_session(self):
        with self.assertRaises(ApiError):
            self.backend.login({'username': 'driver_a', 'password': 'wrong-password-123'})
        auth = self.backend.login({'username': 'DRIVER_A', 'password': PASSWORD})
        s = self.backend.create(auth['token'])
        self.backend.logout(auth['token'])
        with self.assertRaises(ApiError):
            self.backend.history(s['session_id'], auth['token'])
        self.assertEqual(self.backend.me(self.a['token'])['id'], self.a['driver']['id'])

    def test_profile_isolation_and_validation(self):
        self.backend.profile(self.a['token'], {'driver_share': .75, 'fuel_l_per_100km': 2.1})
        self.assertEqual(self.backend.profile(self.b['token'])['profile'], {})
        for value in (True, float('nan'), -1, 2):
            with self.subTest(value=value), self.assertRaises(ApiError):
                self.backend.profile(self.a['token'], {'driver_share': value})
        self.backend.profile(self.a['token'], {'fuel_l_per_100km': None})
        self.assertNotIn('fuel_l_per_100km', self.backend.profile(self.a['token'])['profile'])

    def test_import_preview_confirmation_and_deduplication(self):
        bad = {'trip_id': 'bad'}
        preview = self.preview(trips=[TRIP, bad])
        self.assertEqual(preview['report']['trips']['accepted'], 1)
        self.assertEqual(len(preview['report']['trips']['rejected']), 1)
        self.assertEqual(self.backend.records(self.a['token'], 'trips')['total'], 0)
        with self.assertRaises(ApiError) as err:
            self.backend.confirm_import(self.b['token'], preview['import_id'])
        self.assertEqual(err.exception.status, 404)
        confirmed = self.backend.confirm_import(self.a['token'], preview['import_id'])
        self.assertEqual(confirmed, self.backend.confirm_import(self.a['token'], preview['import_id']))
        self.assertEqual(self.backend.records(self.a['token'], 'trips')['total'], 1)
        self.assertEqual(self.backend.records(self.b['token'], 'trips')['total'], 0)
        self.assertEqual(self.preview()['report']['trips']['duplicate_ids'], ['trip-1'])

    def test_same_trip_id_is_allowed_for_different_drivers(self):
        for auth in (self.a, self.b):
            preview = self.preview(auth['token'])
            self.backend.confirm_import(auth['token'], preview['import_id'])
            self.assertEqual(self.backend.records(auth['token'], 'trips')['total'], 1)

    def test_synthetic_rows_cannot_enter_personal_history(self):
        preview = self.preview(trips=[{**TRIP, 'source_kind': 'synthetic'}],
                               wait_spells=[{**WAIT, 'source_kind': 'synthetic'}])
        self.assertEqual(preview['report']['trips']['accepted'], 0)
        self.assertEqual(preview['report']['waits']['accepted'], 0)
        self.backend.confirm_import(self.a['token'], preview['import_id'])
        self.assertEqual(self.backend.records(self.a['token'], 'trips')['total'], 0)
        self.assertEqual(self.backend.records(self.a['token'], 'waits')['total'], 0)

    def test_csv_import_and_conflicting_previews_do_not_double_insert(self):
        csv_text = 'spell_id,start,end,lat,lng,ended_by\nwait-1,2026-10-13 08:00,2026-10-13 08:10,10.77,106.7,trip\n'
        first = self.preview(wait_spells=csv_text)
        second = self.preview(wait_spells=csv_text)
        self.backend.confirm_import(self.a['token'], first['import_id'])
        result = self.backend.confirm_import(self.a['token'], second['import_id'])
        self.assertEqual(result['report']['waits']['inserted'], 0)
        self.assertEqual(self.backend.records(self.a['token'], 'waits')['total'], 1)

    def test_authenticated_history_survives_relogin_and_restart(self):
        s, result = self.run_driver(self.a['token'])
        again = Backend(self.path)
        auth = again.login({'username': 'driver_a', 'password': PASSWORD})
        self.assertEqual(again.driver_history(auth['token'])['total'], 1)
        self.assertEqual(again.driver_history(auth['token'], rid=result['recommendation_id']), result)
        self.assertEqual(again.driver_history(self.b['token'])['total'], 0)
        with self.assertRaises(ApiError):
            again.driver_history(self.b['token'], rid=result['recommendation_id'])
        with self.assertRaises(ApiError):
            again.history(s['session_id'], self.b['token'])

    def test_only_own_history_and_profile_are_loaded_into_engine(self):
        preview = self.preview()
        self.backend.confirm_import(self.a['token'], preview['import_id'])
        self.backend.profile(self.a['token'], {'driver_share': .8})
        with patch('api.session_service.recommend', side_effect=lambda *a, **kw: {'_input_snapshot': {}, 'objectives': {}}) as engine:
            self.run_driver(self.a['token'])
            personal = engine.call_args.kwargs['personal_input']
            self.assertEqual(personal['trip_log'][0]['trip_id'], 'trip-1')
            self.assertEqual(personal['driver_profile']['driver_share'], .8)
            self.run_driver(self.b['token'])
            self.assertEqual(engine.call_args.kwargs['personal_input']['trip_log'], [])

    def test_account_input_reaches_actual_engine_and_data_status_is_scoped(self):
        preview = self.preview()
        self.backend.confirm_import(self.a['token'], preview['import_id'])
        _, result = self.run_driver(self.a['token'])
        self.assertIsNone(result['personal_model'])
        self.assertEqual(result['ml_insights']['source'], 'synthetic_base_model')
        self.assertEqual(self.backend.data_status(self.a['token'])['trips'], 1)
        self.assertEqual(self.backend.data_status(self.b['token'])['trips'], 0)
        self.assertEqual(self.backend.data_status(self.a['token'])['model_status'], 'not_evaluated')

    def test_expiry_rate_limit_and_forbidden_owner_override(self):
        with self.backend.db() as db:
            db.execute('UPDATE driver_tokens SET expires=0 WHERE token_hash=?', (self.backend.hash(self.b['token']),))
        with self.assertRaises(ApiError):
            self.backend.me(self.b['token'])
        with self.assertRaises(ApiError):
            self.preview(driver_id=self.b['driver']['id'])
        for _ in range(9):
            with self.assertRaises(ApiError):
                self.backend.login({'username': 'driver_a', 'password': 'wrong-password-123'})
        with self.assertRaises(ApiError) as err:
            self.backend.login({'username': 'driver_a', 'password': PASSWORD})
        self.assertEqual(err.exception.status, 429)

    def test_http_auth_import_history_and_invalid_body(self):
        server_type = type('TestHandler', (Handler,), {'backend': self.backend})
        server = ThreadingHTTPServer(('127.0.0.1', 0), server_type)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f'http://127.0.0.1:{server.server_port}'
        def call(path, method='GET', payload=None, token=None):
            headers = {'Content-Type': 'application/json'}
            if token:
                headers['Authorization'] = 'Bearer ' + token
            body = json.dumps(payload).encode() if payload is not None else None
            with urlopen(Request(base + path, data=body, headers=headers, method=method)) as response:
                return response.status, json.load(response)
        try:
            code, auth = call('/api/v1/auth/login', 'POST', {'username': 'driver_a', 'password': PASSWORD})
            self.assertEqual(code, 200)
            _, me = call('/api/v1/me', token=auth['token'])
            self.assertEqual(me['username'], 'driver_a')
            code, _ = call('/api/v1/sessions', 'POST', {}, token=auth['token'])
            self.assertEqual(code, 201)
            _, items = call('/api/v1/me/trips?limit=1', token=auth['token'])
            self.assertEqual(items['total'], 0)
            code, preview = call('/api/v1/me/log-imports/preview', 'POST', {
                'trips': [TRIP], 'consent_reference': 'self-submitted', 'collected_via': 'personal log'
            }, token=auth['token'])
            self.assertEqual(code, 201)
            _, confirmed = call('/api/v1/me/log-imports/' + preview['import_id'] + '/confirm',
                                'POST', {}, token=auth['token'])
            self.assertEqual(confirmed['report']['trips']['inserted'], 1)
            _, trips = call('/api/v1/me/trips', token=self.b['token'])
            self.assertEqual(trips['total'], 0)
            with self.assertRaises(HTTPError) as err:
                call('/api/v1/me/log-imports/' + preview['import_id'] + '/confirm',
                     'POST', {}, token=self.b['token'])
            self.assertEqual(err.exception.code, 404)
            with self.assertRaises(HTTPError) as err:
                call('/api/v1/me/trips')
            self.assertEqual(err.exception.code, 401)
            with self.assertRaises(HTTPError) as err:
                call('/api/v1/research/drivers')
            self.assertEqual(err.exception.code, 401)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == '__main__':
    unittest.main()
