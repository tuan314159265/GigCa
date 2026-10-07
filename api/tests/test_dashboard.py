import json
import threading
import os
from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from api.dashboard import DashboardHandler, recommend


class DashboardTests(unittest.TestCase):
    def test_recomputes_and_enforces_radius(self):
        full = recommend({})
        limited = recommend({"context": {"max_reposition_km": 0}})
        self.assertEqual(full["snapshot"]["mode"], "simulation")
        self.assertEqual(len(full["objectives"]), 4)
        self.assertNotEqual(full["objectives"], limited["objectives"])
        self.assertEqual(limited["objectives"]["rest_spot"]["status"], "insufficient_data")

    def test_source_sample_does_not_invent_fares(self):
        result = recommend({"mode": "sample"})
        self.assertEqual(result["snapshot"]["mode"], "sample")
        self.assertIsNone(result["objectives"]["max_trip_value"]["plan"])

    def test_pipeline_data_runs_through_engine_without_simulated_fares(self):
        result = recommend({"mode": "pipeline"})
        self.assertEqual(result["snapshot"]["mode"], "pipeline")
        self.assertGreater(len(result["places"]), 0)
        self.assertIsNone(result["objectives"]["max_trip_value"]["plan"])

    def test_database_mode_calls_data_interface_and_preserves_sources(self):
        sample = json.loads((Path(__file__).resolve().parents[2] / "data/samples/engine_input/hcmc_demo_snapshot.json").read_text(encoding="utf-8"))
        with patch.dict(os.environ, {"GIGCA_DATABASE_URL": "test-database", "GIGCA_AREA_ID": "test-area"}), patch("api.dashboard.read_tomtom_key", side_effect=RuntimeError("missing")), patch("api.dashboard.EngineDataInterface.from_env") as factory:
            factory.return_value.get_engine_input.return_value = deepcopy(sample)
            result = recommend({"mode": "database", "rain_tolerance_level": "high", "context": {"horizon_min": 90}})
            factory.return_value.get_engine_input.assert_called_once_with("test-area", rain_tolerance_level="high", forecast_hours=2)
            self.assertEqual(result["snapshot"]["mode"], "database")
            self.assertEqual(result["snapshot"]["sources"], sample["data_status"])
            self.assertIsNone(result["objectives"]["max_trip_value"]["plan"])

    def test_database_missing_config_is_explicit(self):
        with patch.dict(os.environ, {}, clear=True), self.assertRaisesRegex(RuntimeError, "Chưa cấu hình"):
            recommend({"mode": "database"})

    def test_rejects_invalid_input(self):
        for payload in [{"mode": "live"}, {"context": {"current_lat": 91}},
                        {"context": {"horizon_min": 0}}, {"context": {"max_reposition_km": float("nan")}},
                        {"context": {"idle_duration_min": 1.5}}, {"rain_tolerance_level": "invalid"}]:
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                recommend(payload)

    def test_traffic_tiles_are_proxied_and_coordinates_validated(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), DashboardHandler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{server.server_port}"
        try:
            for path in ["/api/traffic/tiles/23/0/0.png", "/api/traffic/tiles/1/2/0.png"]:
                with self.assertRaises(HTTPError) as error:
                    urlopen(base + path)
                self.assertEqual(error.exception.code, 400)
            with patch("api.provider_proxy.read_tomtom_key", return_value="test-secret"), patch("api.dashboard.request_upstream", return_value=(b"test-image", "image/png")) as upstream:
                with urlopen(base + "/api/traffic/tiles/12/2044/1360.png") as response:
                    self.assertEqual(response.headers["Content-Type"], "image/png")
                    self.assertEqual(response.read(), b"test-image")
                    self.assertNotIn("test-secret", str(response.headers))
                self.assertIn("/tile/flow/relative/12/2044/1360.png", upstream.call_args.args[0])
                self.assertIn("key=test-secret", upstream.call_args.args[0])
            with patch("api.provider_proxy.read_tomtom_key", side_effect=RuntimeError("TomTom chưa cấu hình")), patch("api.dashboard.request_upstream") as upstream:
                with self.assertRaises(HTTPError) as error:
                    urlopen(base + "/api/traffic/tiles/12/2045/1360.png")
                self.assertEqual(error.exception.code, 502)
                upstream.assert_not_called()
        finally:
            server.shutdown()
            server.server_close()

    def test_http_contract_and_file_isolation(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), DashboardHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"
        try:
            request = Request(base + "/api/recommendations", data=b'{}', headers={"Content-Type": "application/json"})
            with urlopen(request) as response:
                self.assertEqual(response.status, 200)
                self.assertIn("snapshot", json.load(response))
            for path in ["/api/dashboard.py", "/.env", "/data/samples/engine_input/hcmc_demo_snapshot.json"]:
                with self.assertRaises(HTTPError) as error:
                    urlopen(base + path)
                self.assertEqual(error.exception.code, 404)
            with self.assertRaises(HTTPError) as error:
                urlopen(Request(base + "/api/recommendations", data=b'{"context": []}'))
            self.assertEqual(error.exception.code, 400)
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
