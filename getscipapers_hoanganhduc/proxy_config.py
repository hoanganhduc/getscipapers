"""Proxy configuration utilities shared between CLI and GUI flows.

This module centralizes reading proxy settings from JSON files or
environment variables and exposes helpers for applying those settings to
``requests``/``aiohttp`` callers. Keeping proxy handling in one place
makes it easier to provide consistent controls for every service the
package talks to.
"""

from __future__ import annotations

import json
import os
import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import requests
from bs4 import BeautifulSoup

from . import configuration


DEFAULT_PROXY_FILE = configuration.GETPAPERS_CONFIG_FILE.parent / "proxy.json"
PROXY_LIST_SUFFIX = "_list.json"

# Countries that block or restrict Telegram access
BLOCKED_COUNTRIES = {
    "VN": "Vietnam",
    "CN": "China",
    "IR": "Iran",
    "RU": "Russia",
    "BY": "Belarus",
    "TH": "Thailand",
    "ID": "Indonesia",
    "BD": "Bangladesh",
    "PK": "Pakistan",
    "IN": "India",
    "KZ": "Kazakhstan",
    "UZ": "Uzbekistan",
    "TJ": "Tajikistan",
    "TM": "Turkmenistan",
    "KG": "Kyrgyzstan",
    "MY": "Malaysia",
    "SG": "Singapore",
    "AE": "UAE",
    "SA": "Saudi Arabia",
    "EG": "Egypt",
    "TR": "Turkey",
    "UA": "Ukraine",
}


@dataclass
class ProxySettings:
    """Lightweight container for normalized proxy configuration."""

    enabled: bool = False
    proxy_url: Optional[str] = None
    source: Optional[str] = None

    def requests_proxies(self) -> Optional[Dict[str, str]]:
        if not self.enabled or not self.proxy_url:
            return None
        return {"http": self.proxy_url, "https": self.proxy_url}

    def apply_environment(self) -> None:
        """Apply or clear proxy environment variables for downstream libraries."""

        keys = ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY")
        if self.enabled and self.proxy_url:
            for key in keys:
                os.environ[key] = self.proxy_url
        else:
            for key in keys:
                os.environ.pop(key, None)


class ProxyConfigError(RuntimeError):
    """Raised when proxy configuration cannot be parsed."""


def _parse_proxy_candidates(html: str, verbose: bool = False) -> List[Dict[str, object]]:
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", {"class": "table table-striped table-bordered"}) or soup.find(
        "table", {"id": "proxylisttable"}
    )
    if not table:
        if verbose:
            print("❌ Unable to locate proxy table from provider site")
        return []

    candidates: list[dict[str, object]] = []
    body = table.find("tbody") or table
    for row in body.find_all("tr"):
        columns = row.find_all("td")
        if len(columns) < 7:
            continue
        ip = columns[0].text.strip()
        port = columns[1].text.strip()
        country_code = columns[2].text.strip().upper()
        https_support = columns[6].text.strip().lower() == "yes"
        if not https_support or not ip or not port:
            continue
        if country_code in BLOCKED_COUNTRIES:
            continue
        try:
            candidates.append(
                {
                    "addr": ip,
                    "port": int(port),
                    "type": "https",
                    "country_code": country_code,
                }
            )
        except ValueError:
            continue

    if verbose:
        print(f"Found {len(candidates)} HTTPS proxy candidates from provider site")
    return candidates


def _probe_proxy(candidate: Dict[str, object], timeout: int = 8, verbose: bool = False) -> Optional[Dict[str, object]]:
    proxy_url = f"http://{candidate['addr']}:{candidate['port']}"
    start = time.time()
    try:
        response = requests.get(
            "https://httpbin.org/ip",
            proxies={"http": proxy_url, "https": proxy_url},
            timeout=timeout,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        response.raise_for_status()
    except Exception:
        return None

    elapsed_ms = (time.time() - start) * 1000
    probed = dict(candidate)
    probed["speed_ms"] = elapsed_ms
    if verbose:
        print(f"✓ Proxy {proxy_url} responded in {elapsed_ms:.0f} ms")
    return probed


def auto_discover_proxy(
    *,
    config_path: str | Path = DEFAULT_PROXY_FILE,
    sample: int = 25,
    timeout: int = 8,
    save_list: bool = True,
    verbose: bool = False,
) -> ProxySettings:
    """Fetch and test free proxies, persisting a working one to ``config_path``."""

    try:
        response = requests.get(
            "https://free-proxy-list.net/",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10,
        )
        response.raise_for_status()
    except Exception as exc:  # pragma: no cover - network dependent
        settings = ProxySettings(enabled=False, proxy_url=None, source=str(config_path))
        if verbose:
            print(f"❌ Failed to retrieve proxy list automatically: {exc}")
        return settings

    candidates = _parse_proxy_candidates(response.text, verbose=verbose)
    if not candidates:
        settings = ProxySettings(enabled=False, proxy_url=None, source=str(config_path))
        if verbose:
            print("❌ No suitable proxies discovered from provider site")
        return settings

    sampled = random.sample(candidates, min(sample, len(candidates)))
    results: list[dict[str, object]] = []
    with ThreadPoolExecutor(max_workers=min(10, len(sampled))) as pool:
        future_map = {pool.submit(_probe_proxy, cand, timeout, verbose): cand for cand in sampled}
        for future in as_completed(future_map):
            probed = future.result()
            if probed:
                results.append(probed)

    if not results:
        settings = ProxySettings(enabled=False, proxy_url=None, source=str(config_path))
        if verbose:
            print("❌ No working proxies responded during automatic discovery")
        return settings

    results.sort(key=lambda item: item.get("speed_ms", float("inf")))
    best = results[0]

    config_path = Path(config_path).expanduser()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"type": best.get("type", "https"), "addr": best["addr"], "port": best["port"]}
    config_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    if save_list:
        list_path = config_path.with_name(f"{config_path.stem}{PROXY_LIST_SUFFIX}")
        list_payload = {
            "working": results,
            "timestamp": time.time(),
            "source": "https://free-proxy-list.net/",
        }
        list_path.write_text(json.dumps(list_payload, indent=2), encoding="utf-8")

    proxy_url = _build_proxy_url(payload)
    settings = ProxySettings(enabled=True, proxy_url=proxy_url, source=str(config_path))
    settings.apply_environment()
    if verbose:
        print(f"✅ Auto-selected proxy saved to {config_path}: {proxy_url}")
    return settings


def _build_proxy_url(entry: Dict[str, object]) -> str:
    addr = entry.get("addr")
    port = entry.get("port")
    if not addr or not port:
        raise ProxyConfigError("Proxy configuration requires both 'addr' and 'port'.")

    scheme = str(entry.get("type") or "http").lower()
    username = entry.get("username")
    password = entry.get("password")
    auth = ""
    if username and password:
        auth = f"{username}:{password}@"
    elif username or password:
        raise ProxyConfigError("Proxy configuration must include both username and password or neither.")

    return f"{scheme}://{auth}{addr}:{port}"


def _load_entry_from_payload(payload: object) -> Dict[str, object]:
    if isinstance(payload, dict):
        return payload
    if isinstance(payload, list):
        if not payload:
            raise ProxyConfigError("Proxy configuration list is empty.")
        first = payload[0]
        if not isinstance(first, dict):
            raise ProxyConfigError("Proxy list must contain dictionaries.")
        return first
    raise ProxyConfigError("Unsupported proxy configuration format; expected dict or list of dicts.")


def load_proxy_settings(
    config_file: str | Path | None = None,
    *,
    enabled: bool = True,
    auto_fetch: bool = False,
    env_prefix: str = "GETSCIPAPERS_",
    verbose: bool = False,
) -> ProxySettings:
    """Load proxy settings from file or environment.

    Environment variables can override the config file location using
    ``<env_prefix>PROXY_FILE``. If ``enabled`` is False, the returned
    settings will disable proxies and clear any related environment
    variables.
    """

    def _disabled_settings(path: Path) -> ProxySettings:
        settings = ProxySettings(enabled=False, proxy_url=None, source=str(path))
        settings.apply_environment()
        return settings

    if not enabled:
        return _disabled_settings(Path(config_file or DEFAULT_PROXY_FILE))

    config_path = config_file or os.getenv(f"{env_prefix}PROXY_FILE") or DEFAULT_PROXY_FILE
    config_path = Path(config_path).expanduser()

    if not config_path.exists() and auto_fetch:
        return auto_discover_proxy(config_path=config_path, verbose=verbose)
    if not config_path.exists():
        settings = _disabled_settings(config_path)
        if verbose:
            print(f"⚠️ Proxy configuration file not found: {config_path}")
        return settings

    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
        entry = _load_entry_from_payload(payload)
        proxy_url = _build_proxy_url(entry)
    except ProxyConfigError:
        if auto_fetch:
            return auto_discover_proxy(config_path=config_path, verbose=verbose)
        raise
    except Exception as exc:  # pragma: no cover - defensive parsing
        if auto_fetch:
            return auto_discover_proxy(config_path=config_path, verbose=verbose)
        raise ProxyConfigError(f"Failed to parse proxy configuration {config_path}: {exc}") from exc

    settings = ProxySettings(enabled=True, proxy_url=proxy_url, source=str(config_path))
    settings.apply_environment()
    if verbose:
        print(f"✅ Using proxy from {config_path}: {proxy_url}")
    return settings


def configure_from_cli(
    proxy_path: str | Path | None,
    no_proxy: bool = False,
    *,
    auto_fetch: bool = False,
    verbose: bool = False,
) -> ProxySettings:
    """Load proxy settings for standalone modules using CLI flags.

    This helper mirrors :func:`load_proxy_settings` but catches
    :class:`ProxyConfigError` to keep individual service CLIs resilient.
    """

    try:
        return load_proxy_settings(proxy_path, enabled=not no_proxy, auto_fetch=auto_fetch, verbose=verbose)
    except ProxyConfigError as exc:
        if verbose:
            print(f"❌ {exc}")
        settings = ProxySettings(enabled=False, proxy_url=None, source=str(proxy_path or DEFAULT_PROXY_FILE))
        settings.apply_environment()
        return settings


__all__ = [
    "BLOCKED_COUNTRIES",
    "DEFAULT_PROXY_FILE",
    "PROXY_LIST_SUFFIX",
    "auto_discover_proxy",
    "ProxyConfigError",
    "ProxySettings",
    "configure_from_cli",
    "load_proxy_settings",
]
