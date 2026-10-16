import unittest
from unittest.mock import patch
from api.nearby_traffic import nearby_traffic
from api.errors import ApiError


class NearbyTrafficTests(unittest.TestCase):
    def test_deduplicates_samples_and_uses_provider_road_name(self):
        def response(url):
            if 'reverseGeocode' in url:return {'addresses':[{'address':{'streetName':'Đường Lý Thường Kiệt'}}]}
            return {'flowSegmentData':{'openlr':'same-road','currentSpeed':10,'freeFlowSpeed':40,
                'coordinates':{'coordinate':[{'latitude':10.77,'longitude':106.7}]}}}
        with patch('api.nearby_traffic.cached',side_effect=lambda k,t,f:f()), patch('api.nearby_traffic.tomtom_url',side_effect=lambda u,p:u), patch('api.nearby_traffic.request_json',side_effect=response):
            result=nearby_traffic(10.77,106.7)
        self.assertEqual(len(result['roads']),1)
        self.assertEqual(result['roads'][0]['name'],'Đường Lý Thường Kiệt')
        self.assertEqual(result['roads'][0]['status'],'congested')
        self.assertEqual(result['scope'],'nearby_point_samples')

    def test_failure_does_not_invent_clear_roads(self):
        with patch('api.nearby_traffic.cached',side_effect=lambda k,t,f:f()), patch('api.nearby_traffic.tomtom_url',side_effect=lambda u,p:u), patch('api.nearby_traffic.request_json',side_effect=TimeoutError):
            result=nearby_traffic(10.77,106.7)
        self.assertEqual(result['roads'],[])
        self.assertTrue(result['partial'])

    def test_invalid_coordinates_rejected(self):
        for lat,lng in [('nan',106),(91,106),(10,None)]:
            with self.assertRaises(ApiError):nearby_traffic(lat,lng)

    def test_far_snapped_segment_is_not_nearby(self):
        flow={'flowSegmentData':{'coordinates':{'coordinate':[{'latitude':11,'longitude':107}]}}}
        with patch('api.nearby_traffic.cached',side_effect=lambda k,t,f:f()), patch('api.nearby_traffic.tomtom_url',side_effect=lambda u,p:u), patch('api.nearby_traffic.request_json',return_value=flow):
            self.assertEqual(nearby_traffic(10.77,106.7)['roads'],[])
