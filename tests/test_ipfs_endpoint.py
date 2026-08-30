import os
import unittest
from unittest.mock import patch

from getscipapers_hoanganhduc import getpapers


class IpfsHttpBaseUrlTests(unittest.TestCase):
    """The gateway address StcGeck is handed when searching the Nexus/STC index."""

    def test_defaults_to_a_local_daemon(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(
                getpapers.get_ipfs_http_base_url(), "http://127.0.0.1:8080"
            )

    def test_environment_overrides_the_default(self):
        with patch.dict(
            os.environ, {getpapers.IPFS_HTTP_BASE_URL_ENV: "http://ipfs:8080"}
        ):
            self.assertEqual(getpapers.get_ipfs_http_base_url(), "http://ipfs:8080")

    def test_blank_environment_falls_back_to_the_default(self):
        with patch.dict(os.environ, {getpapers.IPFS_HTTP_BASE_URL_ENV: "   "}):
            self.assertEqual(
                getpapers.get_ipfs_http_base_url(),
                getpapers.DEFAULT_IPFS_HTTP_BASE_URL,
            )

    def test_surrounding_whitespace_is_ignored(self):
        with patch.dict(
            os.environ, {getpapers.IPFS_HTTP_BASE_URL_ENV: " http://ipfs:8080 "}
        ):
            self.assertEqual(getpapers.get_ipfs_http_base_url(), "http://ipfs:8080")

    def test_value_is_read_at_call_time(self):
        with patch.dict(os.environ, {getpapers.IPFS_HTTP_BASE_URL_ENV: "http://one:8080"}):
            self.assertEqual(getpapers.get_ipfs_http_base_url(), "http://one:8080")
        with patch.dict(os.environ, {getpapers.IPFS_HTTP_BASE_URL_ENV: "http://two:8080"}):
            self.assertEqual(getpapers.get_ipfs_http_base_url(), "http://two:8080")


if __name__ == "__main__":
    unittest.main()
