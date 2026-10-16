"""Test 9.2: Input responsiveness.

Changing rain_tolerance_level from low -> medium -> high must monotonically
decrease or keep equal the number of hours where exceeds_tolerance is True.
"""

from __future__ import annotations

import unittest

from engine.src.engine import run_driver_engine
from engine.tests.fixtures import (
    create_default_driver_context,
    create_default_driver_preferences,
    create_mock_engine_input,
)


class TestRainResponsiveness(unittest.TestCase):
    def test_rain_tolerance_monotonicity(self) -> None:
        mock_input = create_mock_engine_input()
        ctx = create_default_driver_context(horizon_min=300)

        out_low = run_driver_engine(
            mock_input, ctx, create_default_driver_preferences(rain_tolerance="low")
        )
        out_med = run_driver_engine(
            mock_input, ctx, create_default_driver_preferences(rain_tolerance="medium")
        )
        out_high = run_driver_engine(
            mock_input, ctx, create_default_driver_preferences(rain_tolerance="high")
        )

        flags_low = out_low.objectives["safety_comfort"].rain_flags or []
        flags_med = out_med.objectives["safety_comfort"].rain_flags or []
        flags_high = out_high.objectives["safety_comfort"].rain_flags or []

        count_low = sum(1 for f in flags_low if f.exceeds_tolerance)
        count_med = sum(1 for f in flags_med if f.exceeds_tolerance)
        count_high = sum(1 for f in flags_high if f.exceeds_tolerance)

        self.assertGreaterEqual(
            count_low,
            count_med,
            f"Low tolerance ({count_low}) should be >= medium ({count_med})",
        )
        self.assertGreaterEqual(
            count_med,
            count_high,
            f"Medium tolerance ({count_med}) should be >= high ({count_high})",
        )


if __name__ == "__main__":
    unittest.main()
