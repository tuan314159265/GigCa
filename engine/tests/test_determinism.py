"""Test 9.1: Determinism.

Same input -> calling run_driver_engine twice -> output must be identical.
"""

from __future__ import annotations

import unittest

from engine.src.engine import run_driver_engine
from engine.src.mock_data import (
    create_default_driver_context,
    create_default_driver_preferences,
    create_mock_engine_input,
)


class TestEngineDeterminism(unittest.TestCase):
    def test_pure_function_determinism(self) -> None:
        mock_input = create_mock_engine_input()
        ctx = create_default_driver_context()
        prefs = create_default_driver_preferences(rain_tolerance="medium")

        out1 = run_driver_engine(mock_input, ctx, prefs)
        out2 = run_driver_engine(mock_input, ctx, prefs)

        self.assertEqual(out1, out2)


if __name__ == "__main__":
    unittest.main()
