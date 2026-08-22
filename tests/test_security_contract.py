from __future__ import annotations

import hashlib
import hmac
import json
import importlib.util
from pathlib import Path
import re
import sys
import tempfile
import unittest
import zipfile


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_PATH = ROOT / "scripts" / "package_skill.py"
PACKAGE_SPEC = importlib.util.spec_from_file_location("package_skill_test", PACKAGE_PATH)
assert PACKAGE_SPEC and PACKAGE_SPEC.loader
PACKAGE = importlib.util.module_from_spec(PACKAGE_SPEC)
sys.modules[PACKAGE_SPEC.name] = PACKAGE
PACKAGE_SPEC.loader.exec_module(PACKAGE)


def paymob_string(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


class SecurityContractTests(unittest.TestCase):
    def test_canonical_transaction_hmac_vector(self) -> None:
        fixture = json.loads(
            (
                ROOT
                / "skills/paymob-integration/references/transaction-hmac-fixture.json"
            ).read_text()
        )
        obj = fixture["obj"]
        fields = [
            obj["amount_cents"], obj["created_at"], obj["currency"], obj["error_occured"],
            obj["has_parent_transaction"], obj["id"], obj["integration_id"], obj["is_3d_secure"],
            obj["is_auth"], obj["is_capture"], obj["is_refunded"], obj["is_standalone_payment"],
            obj["is_voided"], obj["order"]["id"], obj["owner"], obj["pending"],
            obj["source_data"]["pan"], obj["source_data"]["sub_type"],
            obj["source_data"]["type"], obj["success"],
        ]
        concatenated = "".join(paymob_string(value) for value in fields)
        digest = hmac.new(
            fixture["secret"].encode(), concatenated.encode(), hashlib.sha512
        ).hexdigest()
        self.assertEqual(concatenated, fixture["concatenated"])
        self.assertEqual(digest, fixture["hmac_sha512"])

    def test_required_safety_references_exist(self) -> None:
        references = ROOT / "skills/paymob-integration/references"
        for name in (
            "integration-safety.md",
            "credentials-and-integration-ids.md",
            "sandbox-quickstart.md",
            "webhook-troubleshooting.md",
            "payment-methods-and-features.md",
        ):
            self.assertTrue((references / name).is_file(), name)

    def test_upload_archive_excludes_python_cache_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            archive_path = Path(temp_dir) / "skill.zip"
            PACKAGE.build_archive(archive_path)
            with zipfile.ZipFile(archive_path) as archive:
                names = archive.namelist()
        self.assertFalse(any("__pycache__" in name for name in names))
        self.assertFalse(any(name.endswith((".pyc", ".pyo")) for name in names))

    def test_json_examples_are_valid_json(self) -> None:
        pattern = re.compile(r"^```json\s*\n(.*?)^```", re.MULTILINE | re.DOTALL)
        for markdown in sorted(ROOT.rglob("*.md")):
            if ".git" in markdown.parts:
                continue
            for index, block in enumerate(pattern.findall(markdown.read_text()), 1):
                with self.subTest(file=str(markdown.relative_to(ROOT)), block=index):
                    json.loads(block)


if __name__ == "__main__":
    unittest.main()
