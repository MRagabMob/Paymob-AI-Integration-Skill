#!/usr/bin/env python3
"""Validate local Paymob configuration without printing credential values."""

from __future__ import annotations

import os
import ipaddress
import re
import sys
from dataclasses import dataclass
from urllib.parse import urlparse


REGIONS = {
    "egypt": "https://accept.paymob.com",
    "uae": "https://uae.paymob.com",
    "ksa": "https://ksa.paymob.com",
    "oman": "https://oman.paymob.com",
}
PLACEHOLDER_PARTS = ("xxxxx", "changeme", "replace_me", "your_", "example")
KEY_MODE = re.compile(r"^(?:[a-z]{3}_)?(?:sk|pk)_(test|live)_", re.IGNORECASE)


@dataclass(frozen=True)
class Result:
    level: str
    name: str
    message: str


def configured(value: str | None) -> bool:
    if not value or not value.strip():
        return False
    lowered = value.strip().lower()
    return not any(part in lowered for part in PLACEHOLDER_PARTS)


def credential_mode(value: str | None) -> str | None:
    if not value:
        return None
    match = KEY_MODE.match(value.strip())
    return match.group(1).lower() if match else None


def safe_port(parsed) -> int | None:
    """Return the parsed port while turning malformed ports into validation failures."""
    try:
        return parsed.port
    except ValueError:
        return -1


def is_public_callback_origin(parsed) -> bool:
    host = (parsed.hostname or "").lower()
    if (
        parsed.scheme != "https"
        or not host
        or parsed.username
        or parsed.password
        or safe_port(parsed) not in {None, 443}
        or parsed.path not in {"", "/"}
        or parsed.params
        or parsed.query
        or parsed.fragment
        or host == "localhost"
        or host.endswith(".localhost")
        or host.endswith(".local")
    ):
        return False
    try:
        return ipaddress.ip_address(host).is_global
    except ValueError:
        return True


def validate(env: dict[str, str]) -> list[Result]:
    results: list[Result] = []
    region = env.get("PAYMOB_REGION", "").strip().lower()
    mode = env.get("PAYMOB_MODE", "").strip().lower()

    if region not in REGIONS:
        results.append(Result("FAIL", "region", "Set PAYMOB_REGION to egypt, uae, ksa, or oman."))
    else:
        results.append(Result("PASS", "region", "A supported region is selected."))

    if mode not in {"test", "live"}:
        results.append(Result("FAIL", "mode", "Set PAYMOB_MODE explicitly to test or live."))
    else:
        results.append(Result("PASS", "mode", "An explicit mode is selected."))

    base = env.get("PAYMOB_BASE_URL", "").strip().rstrip("/")
    expected = REGIONS.get(region)
    parsed = urlparse(base) if base else None
    if not base:
        results.append(Result("FAIL", "base_url", "Set PAYMOB_BASE_URL for the selected region."))
    elif not parsed or parsed.scheme != "https" or parsed.username or parsed.password or safe_port(parsed):
        results.append(Result("FAIL", "base_url", "Use an exact HTTPS Paymob origin with no credentials or custom port."))
    elif expected and base != expected:
        results.append(Result("FAIL", "base_url", "PAYMOB_BASE_URL does not match PAYMOB_REGION."))
    elif base not in REGIONS.values():
        results.append(Result("FAIL", "base_url", "PAYMOB_BASE_URL is not an approved Paymob origin."))
    else:
        results.append(Result("PASS", "base_url", "The regional Paymob origin is allowlisted."))

    for name in ("PAYMOB_SECRET_KEY", "PAYMOB_PUBLIC_KEY", "PAYMOB_HMAC_SECRET"):
        if configured(env.get(name)):
            results.append(Result("PASS", name.lower(), "Configured without displaying its value."))
        else:
            results.append(Result("FAIL", name.lower(), "Missing, blank, or placeholder value."))

    for name in ("PAYMOB_SECRET_KEY", "PAYMOB_PUBLIC_KEY"):
        found = credential_mode(env.get(name))
        if found and mode in {"test", "live"} and found != mode:
            results.append(Result("FAIL", f"{name.lower()}_mode", "Credential prefix conflicts with PAYMOB_MODE."))
        elif found:
            results.append(Result("PASS", f"{name.lower()}_mode", "Credential prefix matches the selected mode."))
        else:
            results.append(Result("WARN", f"{name.lower()}_mode", "Could not infer mode from the credential prefix; confirm in the dashboard."))

    integration_names = sorted(name for name in env if name.startswith("PAYMOB_INTEGRATION_ID_"))
    valid_ids = [name for name in integration_names if env.get(name, "").strip().isdigit()]
    if not valid_ids:
        results.append(Result("FAIL", "integration_ids", "Configure at least one numeric PAYMOB_INTEGRATION_ID_* value."))
    elif len(valid_ids) != len(integration_names):
        results.append(Result("FAIL", "integration_ids", "Every configured PAYMOB_INTEGRATION_ID_* must be numeric."))
    else:
        results.append(Result("PASS", "integration_ids", f"{len(valid_ids)} numeric Integration ID variable(s) configured."))
    results.append(Result("WARN", "integration_id_mode", "Confirm every Integration ID's account and test/live mode in the dashboard."))

    app_url = env.get("APP_URL", "").strip().rstrip("/")
    app = urlparse(app_url) if app_url else None
    if not app_url or not app or not is_public_callback_origin(app):
        results.append(Result("FAIL", "app_url", "Set APP_URL to a public HTTPS origin with no path, query, credentials, or custom port."))
    else:
        results.append(Result("PASS", "app_url", "A public HTTPS application origin is configured."))

    return results


def main() -> int:
    results = validate(dict(os.environ))
    for item in results:
        print(f"{item.level:4} {item.name}: {item.message}")
    failures = sum(item.level == "FAIL" for item in results)
    warnings = sum(item.level == "WARN" for item in results)
    print(f"Summary: {failures} failure(s), {warnings} warning(s). No credential values were printed.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
