import unittest
from unittest.mock import patch
from datetime import datetime,timezone,timedelta
from urllib.parse import urlsplit,parse_qs
from data.live_collector import collect_for_origin,_cache
from api.dashboard import recommend

class LiveTests(unittest.TestCase):
    def setUp(self):_cache.clear();self.calls=[]
    def response(self,url):
        self.calls.append(url)
        if 'open-meteo' in url:
            q=parse_qs(urlsplit(url).query)
            return {'latitude':float(q['latitude'][0]),'longitude':float(q['longitude'][0]),'hourly':{
                'time':[(datetime.now(timezone.utc)+timedelta(hours=1)).strftime('%Y-%m-%dT%H:00')],
                'precipitation':[1.2],'precipitation_probability':[60]}}
        if 'poiSearch' in url:return {'results':[{'id':'cafe1','position':{'lat':10.777,'lon':106.701},'poi':{'name':'Cafe live'}}]}
        if 'calculateRoute' in url:return {'routes':[{'summary':{'lengthInMeters':500,'travelTimeInSeconds':120}}]}
        return {'flowSegmentData':{'currentSpeed':20,'freeFlowSpeed':40,'coordinates':{'coordinate':[{'latitude':10.77,'longitude':106.7}]}}}
    def test_origin_and_no_fares(self):
        with patch('data.live_collector.fetch_json',side_effect=self.response),patch('api.provider_proxy.read_tomtom_key',return_value='test-key'):
            result=recommend({'mode':'live','context':{'current_lat':10.7769,'current_lng':106.7009}})
        self.assertEqual(result['snapshot']['mode'],'live')
        self.assertFalse(result['is_demo'])
        self.assertEqual(result['origin_used']['lat'],10.7769)
        self.assertIsNone(result['objectives']['max_trip_value']['plan'])
        self.assertIsNone(result['objectives']['maintain_position']['plan'])
        self.assertEqual(result['objectives']['rest_spot']['plan']['target_location'],'Cafe live')
        self.assertFalse(result['places'][0]['verified'])
        self.assertEqual(result['weather'][0]['precipitation_probability_pct'],60)
    def test_sources_fail_without_fixture(self):
        with patch('data.live_collector.fetch_json',side_effect=RuntimeError('fail')),patch('api.provider_proxy.read_tomtom_key',return_value='test'):
            result=recommend({'mode':'live','context':{'current_lat':21,'current_lng':105}})
        self.assertEqual(result['places'],[]);self.assertEqual(result['weather'],[])
        for objective in result['objectives'].values():self.assertEqual(objective['status'],'insufficient_data')
    def test_cache_scoped_to_gps_and_radius_routes_filtered(self):
        with patch('data.live_collector.fetch_json',side_effect=self.response),patch('api.provider_proxy.read_tomtom_key',return_value='test'):
            first=collect_for_origin(10.77,106.7,60,.1)
            second=collect_for_origin(21,105,60,.1)
        self.assertEqual(first['areas'][0]['routing_samples'],[])
        self.assertNotEqual(first['areas'][0]['representative_point'],second['areas'][0]['representative_point'])
        self.assertTrue(any('latitude=21' in url for url in self.calls))
    def test_origin_required(self):
        with self.assertRaises(ValueError):recommend({'mode':'live'})
