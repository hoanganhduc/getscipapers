import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from getscipapers_hoanganhduc import proxy_config


PROXY_ENV_KEYS = ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY")


class ProxyCacheExpiryTests(unittest.TestCase):
    """A free proxy stays alive for minutes, so a cached one must not be trusted
    forever. Using a dead proxy makes every download fail in a way that looks
    like the remote site's fault."""

    def setUp(self):
        self.saved_env = {key: os.environ.get(key) for key in PROXY_ENV_KEYS}
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.config_path = Path(self.tempdir.name) / "proxy.json"

    def tearDown(self):
        for key, value in self.saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def write_entry(self, **extra):
        payload = {"type": "https", "addr": "203.0.113.7", "port": 11111}
        payload.update(extra)
        self.config_path.write_text(json.dumps(payload), encoding="utf-8")

    def test_a_recently_discovered_proxy_is_used(self):
        self.write_entry(discovered=time.time())
        settings = proxy_config.load_proxy_settings(self.config_path)
        self.assertTrue(settings.enabled)
        self.assertEqual(settings.proxy_url, "https://203.0.113.7:11111")

    def test_an_expired_proxy_is_not_used(self):
        self.write_entry(discovered=time.time() - proxy_config.AUTO_PROXY_MAX_AGE_SECONDS - 1)
        settings = proxy_config.load_proxy_settings(self.config_path)
        self.assertFalse(settings.enabled)
        self.assertIsNone(settings.proxy_url)
        for key in PROXY_ENV_KEYS:
            self.assertNotIn(key, os.environ)

    def test_an_expired_proxy_is_rediscovered_when_auto_fetching(self):
        self.write_entry(discovered=time.time() - proxy_config.AUTO_PROXY_MAX_AGE_SECONDS - 1)
        replacement = proxy_config.ProxySettings(
            enabled=True, proxy_url="https://198.51.100.9:8080", source=str(self.config_path)
        )
        with patch.object(proxy_config, "auto_discover_proxy", return_value=replacement) as discover:
            settings = proxy_config.load_proxy_settings(self.config_path, auto_fetch=True)
        discover.assert_called_once()
        self.assertEqual(settings.proxy_url, "https://198.51.100.9:8080")

    def test_a_hand_written_proxy_never_expires(self):
        """Only :func:`auto_discover_proxy` stamps a file, so a proxy the user
        configured themselves must be used however old the file is."""

        self.write_entry()
        os.utime(self.config_path, (0, 0))
        with patch.object(proxy_config, "auto_discover_proxy") as discover:
            settings = proxy_config.load_proxy_settings(self.config_path, auto_fetch=True)
        discover.assert_not_called()
        self.assertTrue(settings.enabled)

    def test_auto_discovery_stamps_the_file_it_writes(self):
        probed = {"type": "https", "addr": "198.51.100.9", "port": 8080, "speed_ms": 12.0}
        with patch.object(proxy_config.requests, "get") as fetch, \
                patch.object(proxy_config, "_parse_proxy_candidates", return_value=[probed]), \
                patch.object(proxy_config, "_probe_proxy", return_value=probed):
            fetch.return_value.text = ""
            settings = proxy_config.auto_discover_proxy(
                config_path=self.config_path, save_list=False
            )
        self.assertTrue(settings.enabled)
        payload = json.loads(self.config_path.read_text(encoding="utf-8"))
        self.assertIn("discovered", payload)
        self.assertFalse(proxy_config._entry_is_stale(payload))


class SaveProxyEntryTests(unittest.TestCase):
    """Every machine-written proxy entry has to carry the stamp, whichever
    module probed it, or it silently outlives the expiry check."""

    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.config_path = Path(self.tempdir.name) / "nested" / "proxy.json"

    def test_the_written_entry_is_stamped(self):
        proxy_config.save_proxy_entry(
            self.config_path, {"type": "http", "addr": "198.51.100.9", "port": 8080}
        )
        payload = json.loads(self.config_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["addr"], "198.51.100.9")
        self.assertFalse(proxy_config._entry_is_stale(payload))

    def test_the_written_entry_expires_once_it_ages(self):
        proxy_config.save_proxy_entry(
            self.config_path, {"type": "http", "addr": "198.51.100.9", "port": 8080}
        )
        payload = json.loads(self.config_path.read_text(encoding="utf-8"))
        self.assertTrue(
            proxy_config._entry_is_stale(payload, max_age=-1),
        )

    def test_the_caller_does_not_have_to_create_the_directory(self):
        written = proxy_config.save_proxy_entry(
            self.config_path, {"addr": "198.51.100.9", "port": 8080}
        )
        self.assertTrue(written.exists())


if __name__ == "__main__":
    unittest.main()
