from __future__ import annotations

import contextlib
import importlib.util
import io
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "skills" / "paymob-integration" / "scripts" / "paymob_setup_check.py"
SPEC = importlib.util.spec_from_file_location("paymob_setup_check", MODULE_PATH)
assert SPEC and SPEC.loader
CHECKER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = CHECKER
SPEC.loader.exec_module(CHECKER)


GOOD_ENV = {
    "PAYMOB_REGION": "uae",
    "PAYMOB_MODE": "test",
    "PAYMOB_BASE_URL": "https://uae.paymob.com",
    "PAYMOB_SECRET_KEY": "uae_sk_test_syntheticvalue",
    "PAYMOB_PUBLIC_KEY": "uae_pk_test_syntheticvalue",
    "PAYMOB_HMAC_SECRET": "synthetic-hmac-value",
    "PAYMOB_INTEGRATION_ID_CARD": "123456",
    "APP_URL": "https://merchant.example.com",
}


class SetupCheckTests(unittest.TestCase):
    def test_valid_configuration_has_no_failures(self) -> None:
        results = CHECKER.validate(GOOD_ENV.copy())
        self.assertFalse([item for item in results if item.level == "FAIL"])

    def test_rejects_secret_exfiltration_origin(self) -> None:
        env = GOOD_ENV | {"PAYMOB_BASE_URL": "https://attacker.invalid"}
        failures = [item for item in CHECKER.validate(env) if item.level == "FAIL"]
        self.assertTrue(any(item.name == "base_url" for item in failures))

    def test_rejects_malformed_base_port_without_crashing(self) -> None:
        env = GOOD_ENV | {"PAYMOB_BASE_URL": "https://uae.paymob.com:not-a-port"}
        failures = [item for item in CHECKER.validate(env) if item.level == "FAIL"]
        self.assertTrue(any(item.name == "base_url" for item in failures))

    def test_rejects_local_or_path_callback_url(self) -> None:
        for app_url in ("https://localhost", "https://merchant.example.com/callback"):
            with self.subTest(app_url=app_url):
                failures = [
                    item
                    for item in CHECKER.validate(GOOD_ENV | {"APP_URL": app_url})
                    if item.level == "FAIL"
                ]
                self.assertTrue(any(item.name == "app_url" for item in failures))

    def test_rejects_cross_mode_keys(self) -> None:
        env = GOOD_ENV | {"PAYMOB_SECRET_KEY": "uae_sk_live_syntheticvalue"}
        failures = [item for item in CHECKER.validate(env) if item.level == "FAIL"]
        self.assertTrue(any(item.name == "paymob_secret_key_mode" for item in failures))

    def test_main_never_prints_secret_values(self) -> None:
        output = io.StringIO()
        with patch.dict(os.environ, GOOD_ENV, clear=True), contextlib.redirect_stdout(output):
            self.assertEqual(CHECKER.main(), 0)
        rendered = output.getvalue()
        for name in ("PAYMOB_SECRET_KEY", "PAYMOB_PUBLIC_KEY", "PAYMOB_HMAC_SECRET"):
            self.assertNotIn(GOOD_ENV[name], rendered)


if __name__ == "__main__":
    unittest.main()
