import unittest
from dataclasses import replace
from unittest.mock import patch

from api.live_candidates import discover
from engine.src.types import DriverContext


class LiveCandidateTests(unittest.TestCase):
    def setUp(self):
        self.ctx = DriverContext(10.773, 106.699, max_reposition_km=3)
        self.anchors = [{'id': 'anchor', 'lat': 10.773, 'lng': 106.699}]

    def discover(self, rows, ctx=None):
        with patch('api.provider_proxy.tomtom_url', return_value='https://provider/test'), \
             patch('api.llm_explanations.cached', side_effect=lambda key, ttl, fn: fn()), \
             patch('api.llm_explanations.fetch_nearby', return_value={'results': rows}):
            return discover(ctx or self.ctx, self.anchors)

    def row(self, identity, lat, lng=106.699):
        return {'id': identity, 'position': {'lat': lat, 'lon': lng},
                'poi': {'name': identity, 'categories': ['College/University']}}

    def test_filters_duplicates_invalid_origin_and_outside_support(self):
        rows = [self.row('valid', 10.778), self.row('valid', 10.778),
                self.row('origin', 10.773), self.row('outside', 10.795),
                self.row('invalid', float('nan'))]
        areas, meta = self.discover(rows)
        self.assertEqual([a['name'] for a in areas], ['valid'])
        self.assertEqual(meta['status'], 'ok')
        self.assertEqual(areas[0]['candidate_source'], 'tomtom_live')
        self.assertFalse(areas[0]['parking_verified'])

    def test_distance_budget_and_zero_move(self):
        areas, _ = self.discover([self.row('far', 10.778)],
                                replace(self.ctx, max_reposition_km=.1))
        self.assertEqual(areas, [])
        with patch('api.llm_explanations.fetch_nearby', side_effect=AssertionError('no request')):
            areas, meta = discover(replace(self.ctx, max_reposition_km=0), self.anchors)
        self.assertEqual(meta['status'], 'current_only')

    def test_actual_provider_places_change_with_request(self):
        first, _ = self.discover([self.row('A', 10.778)])
        second, _ = self.discover([self.row('B', 10.779)])
        self.assertNotEqual(first[0]['id'], second[0]['id'])
        self.assertEqual(second[0]['name'], 'B')

    def test_bounded_pool_retains_other_direction(self):
        rows = [self.row(f'north{i}', 10.774+i*.0001) for i in range(40)]
        rows += [self.row('south', 10.768)]
        areas, _ = self.discover(rows)
        self.assertLessEqual(len(areas), 24)
        self.assertIn('south', [a['name'] for a in areas])

    def test_bounded_pool_retains_more_distant_places_not_only_nearest_shops(self):
        rows = [self.row(f'near{i}', 10.774+i*.0001) for i in range(40)]
        rows += [self.row('outer', 10.787)]
        areas, meta = self.discover(rows)
        self.assertIn('outer', [a['name'] for a in areas])
        self.assertEqual(meta['probe_count'], 5)

    def test_small_businesses_are_fallback_not_removed_entirely(self):
        shop = self.row('Local shop', 10.778)
        shop['poi']['categories'] = ['Retail Store']
        areas, meta = self.discover([shop])
        self.assertEqual(meta['destination_tier'], 'local_fallback')
        self.assertEqual(areas[0]['name'], 'Local shop')

    def test_landmarks_exclude_small_shops_when_both_available(self):
        shop = self.row('Small shop', 10.779)
        shop['poi']['categories'] = ['Retail Store']
        areas, meta = self.discover([shop, self.row('University', 10.778)])
        self.assertEqual([a['name'] for a in areas], ['University'])
        self.assertEqual(meta['destination_tier'], 'landmark_type')

    def test_storefront_mistagged_as_mall_is_not_primary_destination(self):
        shop = self.row('Bread and Butter', 10.779)
        shop['poi']['categories'] = ['Shopping Center']
        tower = self.row('Centec Tower', 10.780)
        tower['poi']['categories'] = ['Commercial Building']
        areas, _ = self.discover([shop, tower, self.row('University', 10.778)])
        self.assertEqual({a['name'] for a in areas}, {'University', 'Centec Tower'})
