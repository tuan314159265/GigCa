"""Provider secrets can be injected at runtime without copying .env into an image."""
import os
import unittest
from unittest.mock import patch
from api.provider_proxy import read_tomtom_key


class ContainerConfigurationTests(unittest.TestCase):
    def test_runtime_key_takes_precedence_without_reading_file(self):
        with patch.dict(os.environ, {"API_TOMTOM": " runtime-key "}), \
             patch("pathlib.Path.is_file", side_effect=AssertionError("Must not read .env")):
            self.assertEqual(read_tomtom_key(), "runtime-key")

    def test_blank_runtime_key_keeps_local_file_support(self):
        with patch.dict(os.environ, {"API_TOMTOM": " "}), \
             patch("pathlib.Path.is_file", return_value=True), \
             patch("pathlib.Path.read_text", return_value="API_TOMTOM=local-key\n"):
            self.assertEqual(read_tomtom_key(), "local-key")
