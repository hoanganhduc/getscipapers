import os
import re
import unittest
from pathlib import Path
from unittest.mock import patch

from getscipapers_hoanganhduc import nexus, proxy_config

NEXUS_SOURCE = Path(__file__).resolve().parent.parent / "getscipapers_hoanganhduc" / "nexus.py"
PROXY_ENV = ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY")


def discovery_stub(**kwargs):
    """Stand-in for ``auto_discover_proxy`` reproducing its documented side
    effect: a discovered proxy is applied to the process environment."""

    settings = proxy_config.ProxySettings(
        enabled=True, proxy_url="http://198.51.100.7:8080", source="stub"
    )
    settings.apply_environment()
    return settings


class ProxyEnvironmentIsolationTests(unittest.TestCase):
    """Nexus discovers a free proxy for Telegram alone, but discovery used to
    leave ``http_proxy`` set for the whole process, so a dead free proxy took
    Crossref and LibGen down with it in the same run."""

    def setUp(self):
        self.saved = {key: os.environ.get(key) for key in PROXY_ENV}
        self.addCleanup(self._restore)
        for key in PROXY_ENV:
            os.environ.pop(key, None)

    def _restore(self):
        for key, value in self.saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_discovery_leaves_an_unset_environment_unset(self):
        with patch.object(nexus.proxy_config, "auto_discover_proxy", discovery_stub):
            self.assertTrue(nexus.get_free_proxies())
        for key in PROXY_ENV:
            self.assertIsNone(
                os.environ.get(key),
                f"{key} leaked out of nexus proxy discovery",
            )

    def test_discovery_restores_a_proxy_the_caller_had_set(self):
        os.environ["https_proxy"] = "http://203.0.113.9:3128"
        with patch.object(nexus.proxy_config, "auto_discover_proxy", discovery_stub):
            nexus.get_free_proxies()
        self.assertEqual(os.environ.get("https_proxy"), "http://203.0.113.9:3128")

    def test_nexus_never_reads_the_proxy_environment(self):
        """Dropping the variables is only safe because nexus hands its proxy to
        Telethon explicitly rather than through the environment."""

        source = NEXUS_SOURCE.read_text(encoding="utf-8")
        hits = [
            match.group(0)
            for match in re.finditer(r"\b(?:HTTPS?|https?)_[Pp][Rr][Oo][Xx][Yy]\b", source)
        ]
        self.assertEqual(hits, [], f"nexus reads proxy environment variables: {hits}")


if __name__ == "__main__":
    unittest.main()
