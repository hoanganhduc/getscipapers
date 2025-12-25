"""Centralized configuration and credential utilities for getscipapers.

This module keeps runtime settings in one place to reduce the amount of
cross-module global state. Functions that previously lived in
``getpapers.py`` now reside here so other modules can import and share a
single source of truth for paths and credentials.
"""

from __future__ import annotations

import json
import os
import platform
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

DEFAULT_LIMIT = 5

EMAIL = ""
ELSEVIER_API_KEY = ""
WILEY_TDM_TOKEN = ""
IEEE_API_KEY = ""


def _default_config_file() -> Path:
    if platform.system() == "Windows":
        return Path(os.path.expanduser("~")) / "AppData" / "Local" / "getscipapers" / "getpapers" / "config.json"
    return Path(os.path.expanduser("~")) / ".config" / "getscipapers" / "getpapers" / "config.json"


GETPAPERS_CONFIG_FILE = _default_config_file()
UNPYWALL_CACHE_DIR = GETPAPERS_CONFIG_FILE.parent
UNPYWALL_CACHE_FILE = UNPYWALL_CACHE_DIR / "unpywall_cache"


@dataclass
class Credentials:
    email: str = ""
    elsevier_api_key: str = ""
    wiley_tdm_token: str = ""
    ieee_api_key: str = ""

    def normalized_email(self) -> str:
        return (self.email or "").strip()

    def require_email(self) -> str:
        email = self.normalized_email()
        if not email:
            raise ValueError(
                "Missing required email for API requests. Set GETSCIPAPERS_EMAIL "
                "or provide a config file via --credentials (or run interactively "
                "without --non-interactive)."
            )
        return email

    def to_dict(self) -> Dict[str, str]:
        return {
            "email": self.email,
            "elsevier_api_key": self.elsevier_api_key,
            "wiley_tdm_token": self.wiley_tdm_token,
            "ieee_api_key": self.ieee_api_key,
        }


def ensure_directory_exists(path: Path) -> None:
    if path and not path.exists():
        path.mkdir(parents=True, exist_ok=True)


def get_default_download_folder(create: bool = False) -> str:
    system = platform.system()
    if system == "Windows":
        base = os.environ.get("USERPROFILE", os.path.expanduser("~"))
        folder = Path(base) / "Downloads" / "getscipapers" / "getpapers"
    else:
        folder = Path(os.path.expanduser("~")) / "Downloads" / "getscipapers" / "getpapers"
    if create:
        ensure_directory_exists(folder)
    return str(folder)


DEFAULT_DOWNLOAD_FOLDER = get_default_download_folder()


def _update_globals(creds: Credentials) -> None:
    global EMAIL, ELSEVIER_API_KEY, WILEY_TDM_TOKEN, IEEE_API_KEY
    EMAIL = creds.email
    ELSEVIER_API_KEY = creds.elsevier_api_key
    WILEY_TDM_TOKEN = creds.wiley_tdm_token
    IEEE_API_KEY = creds.ieee_api_key


def save_credentials(
    email: str | None = None,
    elsevier_api_key: str | None = None,
    wiley_tdm_token: str | None = None,
    ieee_api_key: str | None = None,
    config_file: Optional[str] = None,
    verbose: bool = False,
) -> bool:
    ICON_SUCCESS = "✅"
    ICON_ERROR = "❌"
    ICON_INFO = "ℹ️"

    if config_file is None:
        config_file = str(GETPAPERS_CONFIG_FILE)

    config_path = Path(config_file)
    config_dir = config_path.parent
    try:
        ensure_directory_exists(config_dir)
        if verbose:
            print(f"{ICON_SUCCESS} Ensured config directory exists: {config_dir}")
    except Exception as e:  # pragma: no cover - defensive logging
        if verbose:
            print(f"{ICON_ERROR} Error creating config directory {config_dir}: {e}")
        return False

    existing_config: Dict[str, str] = {}
    if config_path.exists():
        try:
            existing_config = json.loads(config_path.read_text(encoding="utf-8"))
        except Exception as e:  # pragma: no cover - defensive logging
            if verbose:
                print(f"{ICON_INFO} Warning: Could not read existing config file {config_file}: {e}")

    if email is not None:
        existing_config["email"] = email
    if elsevier_api_key is not None:
        existing_config["elsevier_api_key"] = elsevier_api_key
    if wiley_tdm_token is not None:
        existing_config["wiley_tdm_token"] = wiley_tdm_token
    if ieee_api_key is not None:
        existing_config["ieee_api_key"] = ieee_api_key

    try:
        config_path.write_text(json.dumps(existing_config, indent=2), encoding="utf-8")
        if verbose:
            print(f"{ICON_SUCCESS} Saved credentials to {config_file}")
        return True
    except Exception as e:  # pragma: no cover - defensive logging
        if verbose:
            print(f"{ICON_ERROR} Error saving config file {config_file}: {e}")
        return False


def load_credentials(
    config_file: Optional[str] = None,
    interactive: Optional[bool] = None,
    env_prefix: str = "GETSCIPAPERS_",
    verbose: bool = False,
) -> Credentials:
    ICON_SUCCESS = "✅"
    ICON_ERROR = "❌"
    ICON_INFO = "ℹ️"
    ICON_INPUT = "📝"
    ICON_TIMEOUT = "⏰"
    ICON_WARNING = "⚠️"

    if config_file is None:
        config_file = str(GETPAPERS_CONFIG_FILE)

    if interactive is None:
        interactive = sys.stdin.isatty()

    default_config = {
        "email": "",
        "elsevier_api_key": "",
        "wiley_tdm_token": "",
        "ieee_api_key": "",
    }

    existing_config = default_config.copy()
    config_path = Path(config_file)
    file_exists = config_path.exists()

    if file_exists:
        try:
            existing_config = json.loads(config_path.read_text(encoding="utf-8"))
            if verbose:
                print(f"{ICON_SUCCESS} Loaded existing config from {config_file}")
        except (json.JSONDecodeError, Exception) as e:
            if verbose:
                print(f"{ICON_ERROR} Error loading config file {config_file}: {e}")
            print(f"{ICON_ERROR} Configuration file {config_file} is corrupted. Will recreate.")
            file_exists = False
            existing_config = default_config.copy()

    env_config = {
        "email": os.getenv(f"{env_prefix}EMAIL", ""),
        "elsevier_api_key": os.getenv(f"{env_prefix}ELSEVIER_API_KEY", ""),
        "wiley_tdm_token": os.getenv(f"{env_prefix}WILEY_TDM_TOKEN", ""),
        "ieee_api_key": os.getenv(f"{env_prefix}IEEE_API_KEY", ""),
    }

    merged_config = existing_config.copy()
    for key, env_val in env_config.items():
        if env_val:
            merged_config[key] = env_val

    missing_keys = [k for k, v in merged_config.items() if not v]

    if missing_keys and interactive:
        try:
            print("🔑 Some credentials are missing. Please enter them below (leave blank to keep existing value):")
            for key in missing_keys:
                prompt = f"{ICON_INPUT} Enter {key.replace('_', ' ').title()}: "
                user_input = input(prompt).strip()
                if user_input:
                    merged_config[key] = user_input
            if merged_config != existing_config:
                if save_credentials(config_file=config_file, verbose=verbose, **merged_config):
                    print(f"{ICON_SUCCESS} Credentials saved to {config_file}")
            elif verbose:
                print(f"{ICON_INFO} No changes made to credentials.")
        except KeyboardInterrupt:
            print(f"\n{ICON_WARNING} Credential input interrupted by user.")
        except Exception as e:  # pragma: no cover - defensive logging
            print(f"{ICON_TIMEOUT} An error occurred while reading input: {e}")

    creds = Credentials(**merged_config)
    _update_globals(creds)
    return creds


def require_email(email: Optional[str] = None) -> str:
    if email is not None:
        normalized = email.strip()
        if normalized:
            return normalized
    creds = Credentials(EMAIL, ELSEVIER_API_KEY, WILEY_TDM_TOKEN, IEEE_API_KEY)
    return creds.require_email()


__all__ = [
    "Credentials",
    "DEFAULT_LIMIT",
    "DEFAULT_DOWNLOAD_FOLDER",
    "EMAIL",
    "ELSEVIER_API_KEY",
    "WILEY_TDM_TOKEN",
    "IEEE_API_KEY",
    "GETPAPERS_CONFIG_FILE",
    "UNPYWALL_CACHE_DIR",
    "UNPYWALL_CACHE_FILE",
    "ensure_directory_exists",
    "get_default_download_folder",
    "load_credentials",
    "require_email",
    "save_credentials",
]
