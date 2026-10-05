"""Test 9.5: Rest spot routing integrity.

Every candidate in rest_spot must have distance_m and duration_s from a verified
routing sample. Unrouted POIs must be excluded without hidden haversine estimation.
"""

from __future__ import annotations

import unittest

from engine.src.engine import run_driver_engine
from engine.src.mock_data import (
    MOCK_POI_CANDIDATES,
    create_default_driver_context,
    create_default_driver_preferences,
    create_mock_engine_input,
)


class TestRestSpotRouting(unittest.TestCase):
    def test_unrouted_poi_is_excluded_without_haversine_fake(self) -> None:
        mock_input = create_mock_engine_input()
        ctx = create_default_driver_context()
        prefs = create_default_driver_preferences()

        output = run_driver_engine(mock_input, ctx, prefs)
        rest_res = output.objectives["rest_spot"]

        candidate_ids = [c.poi_id for c in rest_res.candidates]

        # poi_phuc_long_unrouted_06 has no routing sample in mock_data!
        self.assertNotIn(
            "poi_phuc_long_unrouted_06",
            candidate_ids,
            "POIs without a routing sample must be excluded rather than given a fake haversine distance.",
        )

        # All included candidates must have non-null distance and duration
        for c in rest_res.candidates:
            self.assertIsNotNone(c.distance_m)
            self.assertIsNotNone(c.duration_s)
            self.assertFalse(c.verified, "Candidates must remain unverified until physical verification.")


if __name__ == "__main__":
    unittest.main()
