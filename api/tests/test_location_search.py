import unittest
from unittest.mock import patch
from api.provider_proxy import search_locations


class LocationSearchTests(unittest.TestCase):
    def test_encoded_query_and_only_valid_coordinates(self):
        payload = {"results": [
            {"id": "a", "poi": {"name": "Chợ"}, "address": {"freeformAddress": "TP.HCM"}, "position": {"lat": 10.77, "lon": 106.7}},
            {"id": "b", "position": {"lat": 999, "lon": 106}},
        ]}
        with patch("api.provider_proxy.read_tomtom_key", return_value="test-key"), \
             patch("api.provider_proxy.request_json", return_value=payload) as upstream:
            result = search_locations("Chợ / Bến Thành")
        self.assertEqual(len(result["places"]), 1)
        self.assertEqual(result["places"][0]["lat"], 10.77)
        self.assertIn("%2F", upstream.call_args.args[0])
        self.assertIn("countrySet=VN", upstream.call_args.args[0])

    def test_rejects_empty_query_before_calling_provider(self):
        with patch("api.provider_proxy.request_json") as upstream:
            with self.assertRaises(ValueError): search_locations(" ")
            upstream.assert_not_called()
