"""Shared Selenium helpers for cross-platform Chrome setup."""

import os
import platform
import shutil

from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.chrome.service import Service as ChromeService

_LINUX_ARM64 = platform.system() == "Linux" and platform.machine().lower() in {"aarch64", "arm64"}


def _find_executable(candidates):
    for candidate in candidates:
        if not candidate:
            continue
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    return None


def _resolve_chrome_binary():
    env_candidates = [
        os.environ.get("CHROME_BINARY"),
        os.environ.get("CHROMIUM_BINARY"),
    ]
    path_candidates = [
        "google-chrome",
        "google-chrome-stable",
        "chromium",
        "chromium-browser",
    ]
    common_paths = [
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
        "/snap/bin/chromium",
    ]
    return _find_executable(env_candidates + path_candidates + common_paths)


def _resolve_chromedriver():
    env_candidates = [os.environ.get("CHROMEDRIVER_PATH")]
    path_candidates = ["chromedriver"]
    common_paths = [
        "/usr/bin/chromedriver",
        "/usr/lib/chromium-browser/chromedriver",
        "/snap/bin/chromedriver",
    ]
    return _find_executable(env_candidates + path_candidates + common_paths)


def build_chrome_driver(options, log=None):
    """Create a Chrome driver with Linux arm64-aware fallbacks.

    On Linux arm64, Selenium Manager may not be available or may not resolve a
    compatible driver. Prefer system-provided Chromium/Chrome and chromedriver
    when detected.
    """
    if _LINUX_ARM64:
        chrome_binary = _resolve_chrome_binary()
        if chrome_binary:
            options.binary_location = chrome_binary
            if log:
                log(f"Using Chrome/Chromium binary: {chrome_binary}")
        driver_path = _resolve_chromedriver()
        if driver_path:
            if log:
                log(f"Using chromedriver: {driver_path}")
            try:
                return webdriver.Chrome(options=options, service=ChromeService(driver_path))
            except WebDriverException as exc:
                if log:
                    log(f"System chromedriver failed: {exc}")
        if log:
            log("chromedriver not found on Linux arm64; falling back to Selenium Manager")

    def _fallback_webdriver_manager(error):
        try:
            from webdriver_manager.chrome import ChromeDriverManager
        except Exception as exc:
            if log:
                log(f"webdriver-manager not available: {exc}")
            raise error
        try:
            driver_path = ChromeDriverManager().install()
            if log:
                log(f"Using webdriver-manager chromedriver: {driver_path}")
            return webdriver.Chrome(options=options, service=ChromeService(driver_path))
        except Exception as exc:
            if log:
                log(f"webdriver-manager failed: {exc}")
            raise error

    try:
        return webdriver.Chrome(options=options)
    except WebDriverException as exc:
        try:
            return _fallback_webdriver_manager(exc)
        except Exception:
            if _LINUX_ARM64:
                message = (
                    "ChromeDriver not found for Linux arm64. Install chromium/chromedriver "
                    "or set CHROMEDRIVER_PATH and CHROME_BINARY/CHROMIUM_BINARY."
                )
                raise RuntimeError(message) from exc
            raise
