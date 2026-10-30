"""
Persist the Retail ID API settings between runs.

Settings are stored as JSON in ``settings.json`` at the repository root (or the
path in ``$RID_EXAMPLE_SETTINGS``). The file uses the same keys as the SDK's
``config.json``, so it can be handed straight to ``RetailIdClient.from_config``.
It holds API keys, so it is git-ignored; never commit it.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from retailid import RetailIdConfig

SETTINGS_ENV_VAR = "RID_EXAMPLE_SETTINGS"
DEFAULT_SETTINGS_FILE = Path(__file__).resolve().parent.parent / "settings.json"

# Fields shown on the Settings tab, in order.
FIELDS = ("vendor_api_key", "user_api_key", "state_code", "base_url")

# Remembered between runs for convenience; not a secret.
LICENSE_FIELD = "license_number"


def settings_path() -> Path:
    return Path(os.environ.get(SETTINGS_ENV_VAR) or DEFAULT_SETTINGS_FILE)


def load_settings(path: Path | None = None) -> dict[str, str]:
    """Return the saved settings, or empty values if nothing has been saved yet."""
    path = path or settings_path()
    values = {key: "" for key in (*FIELDS, LICENSE_FIELD)}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return values
    if isinstance(data, dict):
        for key in values:
            if data.get(key) is not None:
                values[key] = str(data[key])
    return values


def save_settings(values: dict[str, str], path: Path | None = None) -> Path:
    """Write the settings, keeping any extra keys (timeout, max_retries, ...) already in the file."""
    path = path or settings_path()
    try:
        existing = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(existing, dict):
            existing = {}
    except (FileNotFoundError, ValueError):
        existing = {}
    for key in (*FIELDS, LICENSE_FIELD):
        value = values.get(key, "").strip()
        # The SDK treats a missing/null base_url or state_code as "not set".
        existing[key] = value or None
    path.write_text(json.dumps(existing, indent=4) + "\n", encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return path


def to_config(values: dict[str, str]) -> RetailIdConfig:
    """Build an SDK config; raises ``RetailIdConfigError`` if keys or location are missing."""
    return RetailIdConfig.from_mapping({k: (v.strip() or None) for k, v in values.items()})
