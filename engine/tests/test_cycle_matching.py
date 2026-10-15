import unittest
from dataclasses import replace

from engine.src.ml.cycle_model import build_cycles
from engine.src.types import TripRecord, WaitSpell


class MatchingTest(unittest.TestCase):
    def setUp(self):
        self.trip = TripRecord('t', '2026-09-03T08:05:00+07:00', 10.77, 106.7, 30000, 10, distance_km=3)
        self.wait = WaitSpell('w', '2026-09-03T07:50:00+07:00', '2026-09-03T08:00:00+07:00', 10.77, 106.7, 'trip')

    def match(self, trips, waits):
        report = {}
        cycles = build_cycles(trips, waits, 500, matching_report=report)
        self.assertEqual(sum(report['counts'].values()), len(trips))
        return cycles, report

    def test_five_minutes_inclusive_and_target_unchanged(self):
        cs, r = self.match([self.trip], [self.wait])
        self.assertEqual(r['counts']['inferred'], 1)
        self.assertEqual(cs[0].yield_vnd_per_hour, (30000-1500)/(20/60))

    def test_future_wait_and_distant_pickup_rejected(self):
        for w in (replace(self.wait, end='2026-09-03T08:05:01+07:00'), replace(self.wait, lat=10.78)):
            cs, r = self.match([self.trip], [w])
            self.assertEqual(cs, [])
            self.assertEqual(r['counts']['unmatched'], 1)

    def test_two_waits_ambiguous(self):
        cs, r = self.match([self.trip], [self.wait, replace(self.wait, spell_id='w2')])
        self.assertEqual(cs, [])
        self.assertEqual(r['counts']['ambiguous'], 1)

    def test_two_trips_claiming_one_wait_both_ambiguous(self):
        cs, r = self.match([self.trip, replace(self.trip, trip_id='t2')], [self.wait])
        self.assertEqual(cs, [])
        self.assertEqual(r['counts']['ambiguous'], 2)

    def test_censored_and_duplicate_records_not_matched(self):
        self.assertEqual(self.match([self.trip], [replace(self.wait, ended_by='offline')])[0], [])
        self.assertEqual(self.match([self.trip], [self.wait, self.wait])[0], [])
        self.assertEqual(self.match([self.trip, self.trip], [self.wait])[1]['counts']['invalid'], 2)
