import copy
import io
import json
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch

from data.driver_log_import import attach_driver_log, validate_trips, validate_waits
from experiments.synthetic.generator import LOCAL, environment, generate, validate_log, write_dataset
from experiments.synthetic.personas import compatible_personas, ollama_personas, reference_personas, validate_personas


class SyntheticTests(unittest.TestCase):
    def test_compatible_provider_validates_without_network(self):
        payload = {'choices': [{'finish_reason': 'stop', 'message': {
            'content': json.dumps({'personas': reference_personas(2)['personas']})}}],
            'usage': {'total_tokens': 100}}
        with patch.dict('os.environ', {'GIGCA_LLM_API_KEY': 'test-secret', 'GIGCA_LLM_MODEL': 'test-model',
                                      'GIGCA_LLM_BASE_URL': 'https://example.com/v1'}):
            with patch('experiments.synthetic.personas.urlopen') as mocked:
                mocked.return_value.__enter__.return_value = io.StringIO(json.dumps(payload))
                result = compatible_personas(2)
                self.assertEqual(len(result['personas']), 2)
                self.assertNotIn('test-secret', json.dumps(result))
                request = mocked.call_args.args[0]
                self.assertEqual(request.full_url, 'https://example.com/v1/chat/completions')
                original = payload['choices'][0]['message']['content']
                payload['choices'][0]['message']['content'] = '```json\n' + original + '\n```'
                mocked.return_value.__enter__.return_value = io.StringIO(json.dumps(payload))
                self.assertEqual(len(compatible_personas(2)['personas']), 2)
                payload['choices'][0]['message']['content'] = 'not JSON'
                mocked.return_value.__enter__.return_value = io.StringIO(json.dumps(payload))
                with self.assertRaisesRegex(RuntimeError, 'dòng 1, cột 1'):
                    compatible_personas(2)
                payload['choices'][0]['message']['content'] = original
                mocked.return_value.__enter__.return_value = io.StringIO(json.dumps(payload))
                with self.assertRaisesRegex(RuntimeError, 'Yêu cầu 3 persona nhưng nhận 2'):
                    compatible_personas(3)
                payload['choices'][0]['finish_reason'] = 'length'
                mocked.return_value.__enter__.return_value = io.StringIO(json.dumps(payload))
                with self.assertRaises(RuntimeError):
                    compatible_personas(2)

    @classmethod
    def setUpClass(cls):
        cls.personas = reference_personas(3)
        cls.dataset = generate(cls.personas, end_date=date(2026, 10, 13), days=14)

    def test_reproducible_and_different_seed_changes_data(self):
        same = generate(self.personas, end_date=date(2026, 10, 13), days=14)
        other = generate(self.personas, end_date=date(2026, 10, 13), days=14, seed=8)
        self.assertEqual(self.dataset, same)
        self.assertNotEqual(self.dataset['drivers'][0]['trip_log'], other['drivers'][0]['trip_log'])

    def test_time_position_fare_links_and_censoring(self):
        for log in self.dataset['drivers']:
            report = validate_log(log)
            self.assertTrue(report['valid'], report)
            self.assertGreater(report['trips'], 0)
            self.assertGreater(report['censored'], 0)
            self.assertTrue(all(datetime.fromisoformat(t['started_at']).tzinfo is not None for t in log['trip_log']))
        broken = copy.deepcopy(self.dataset['drivers'][0])
        broken['events'][1]['start_point'] = [11, 107]
        self.assertFalse(validate_log(broken)['valid'])
        broken = copy.deepcopy(self.dataset['drivers'][0])
        broken['trip_log'][0]['net_vnd'] = -1
        self.assertFalse(validate_log(broken)['valid'])

    def test_shared_environment_and_worlds(self):
        at = datetime(2026, 10, 1, 17, tzinfo=LOCAL)
        self.assertEqual(environment(7, at, 'Z1'), environment(7, at, 'Z1'))
        for world in ('null', 'drift'):
            dataset = generate(self.personas, end_date=date(2026, 10, 13), days=14, world=world)
            self.assertTrue(all(r['valid'] for r in dataset['manifest']['validation'].values()))
            self.assertEqual(dataset['manifest']['world'], world)

    def test_calendar_splits_do_not_overlap(self):
        splits = self.dataset['manifest']['splits']
        train, cal, test = map(set, (splits['train'], splits['calibration'], splits['test']))
        self.assertFalse(train & cal or train & test or cal & test)
        self.assertLess(max(train), min(cal))
        self.assertLess(max(cal), min(test))
        self.assertEqual(len(train | cal | test), 14)

    def test_production_import_rejects_synthetic_json_and_csv_rows(self):
        log = self.dataset['drivers'][0]
        with self.assertRaises(ValueError):
            attach_driver_log({}, log)
        for rows, validator in ((log['trip_log'], validate_trips), (log['wait_spells'], validate_waits)):
            accepted, rejected, _ = validator(rows)
            self.assertFalse(accepted)
            self.assertEqual(len(rows), len(rejected))
            self.assertTrue(all('synthetic' in r['reason'] for r in rejected))

    def test_invalid_personas_and_paths_are_rejected(self):
        for mutate in (
            lambda p: p.update(driver_id='../escape'), lambda p: p.update(work_probability=float('nan')),
            lambda p: p.update(home_zone=[]), lambda p: p.update(shift_hours=20),
            lambda p: p.update(preferred_zones=['Z1', 'Z1']),
        ):
            document = copy.deepcopy(self.personas)
            mutate(document['personas'][0])
            with self.assertRaises(ValueError):
                validate_personas(document)

    def test_output_marks_synthetic_and_never_overwrites(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'dataset'
            write_dataset(self.dataset, target)
            manifest = json.loads((target / 'manifest.json').read_text(encoding='utf8'))
            self.assertEqual(manifest['kind'], 'synthetic')
            self.assertIn('source_kind', (target / 'D01' / 'trips.csv').read_text(encoding='utf8'))
            with self.assertRaises(ValueError):
                write_dataset(self.dataset, target)

    def test_llm_json_contract_and_provenance(self):
        response = {'message': {'content': json.dumps({'personas': self.personas['personas']})}}
        with patch('experiments.synthetic.personas.urlopen', return_value=io.BytesIO(json.dumps(response).encode())) as upstream:
            document = ollama_personas('test-model', 3)
            self.assertEqual(document['provenance']['persona_source'], 'ollama')
            sent = json.loads(upstream.call_args.args[0].data)
            self.assertFalse(sent['stream'])
            self.assertEqual(sent['format']['type'], 'object')
        response['message']['content'] = 'not JSON'
        with patch('experiments.synthetic.personas.urlopen', return_value=io.BytesIO(json.dumps(response).encode())):
            with self.assertRaises(RuntimeError):
                ollama_personas('test-model', 3)


if __name__ == '__main__':
    unittest.main()
