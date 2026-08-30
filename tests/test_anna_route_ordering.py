import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import Mock, patch

from getscipapers_hoanganhduc import anna


MD5SUM = "a5efa9791b836507541d615ed3f069e9"
SECRET = "SuperSecretAccountKey"
DOI = "10.1000/test"


class RouteOrderingTests(unittest.TestCase):
    """Pin the order the routes run in, and that a disabled route is not merely
    unused but never reached at all.

    Every route is replaced, and subprocess.Popen is armed to fail, so any
    unexpected network access or browser launch shows up as a test failure
    rather than as a slow test.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.folder = self._tmp.name

        patcher = patch.object(anna, "get_cache_directory", lambda: self.folder)
        patcher.start()
        self.addCleanup(patcher.stop)

        for name, value in (
            ("_SESSION_COOKIE", None),
            ("_KEY_ROUTES_DISABLED", False),
            ("_QUOTA_EXHAUSTED", False),
            ("_BROWSER_ATTEMPTS", 0),
            ("VERBOSE", False),
        ):
            p = patch.object(anna, name, value)
            p.start()
            self.addCleanup(p.stop)

        self.mocks = {}
        defaults = {
            "select_active_domain": Mock(return_value="https://aa.test"),
            "login": Mock(return_value="cookie-value"),
            "db_aarecord": Mock(return_value=None),
            "download_via_ipfs": Mock(return_value=False),
            "fast_download_info": Mock(return_value={"status": "not_found"}),
            "scidb_lookup": Mock(return_value=None),
            "download_via_browser": Mock(return_value=None),
            "_download_to_file": Mock(return_value=False),
            "resolve_secret_key": Mock(return_value=None),
        }
        for name, mock in defaults.items():
            p = patch.object(anna, name, mock)
            p.start()
            self.addCleanup(p.stop)
            self.mocks[name] = mock

        # Nothing in these tests may start a browser.
        popen = patch.object(anna.subprocess, "Popen", Mock(side_effect=AssertionError("Popen called")))
        popen.start()
        self.addCleanup(popen.stop)
        self.mocks["Popen"] = popen

    def run_download(self, **kwargs):
        kwargs.setdefault("doi", DOI)
        kwargs.setdefault("download_folder", self.folder)
        kwargs.setdefault("filename", "out.pdf")
        doi = kwargs.pop("doi")
        with redirect_stdout(io.StringIO()):
            return anna.download_paper(doi, **kwargs)

    def test_without_a_key_only_the_browser_route_runs(self):
        self.mocks["download_via_browser"].return_value = {"md5": MD5SUM, "downloaded": True}
        with patch.object(os.path, "exists", return_value=True):
            result = self.run_download()
        self.assertEqual(result, os.path.join(self.folder, "out.pdf"))
        self.mocks["db_aarecord"].assert_not_called()
        self.mocks["fast_download_info"].assert_not_called()
        self.mocks["scidb_lookup"].assert_not_called()
        self.mocks["download_via_browser"].assert_called_once()

    def test_a_known_md5_takes_the_quota_free_record_route(self):
        self.mocks["db_aarecord"].return_value = {"additional": {"ipfs_urls": ["https://gw/a.pdf"]}}
        self.mocks["download_via_ipfs"].return_value = True
        result = self.run_download(md5=MD5SUM, secret_key=SECRET)
        self.assertEqual(result, os.path.join(self.folder, "out.pdf"))
        self.mocks["db_aarecord"].assert_called_once()
        # R2 spends a daily download, so it must not run once R1 succeeded.
        self.mocks["fast_download_info"].assert_not_called()
        self.mocks["scidb_lookup"].assert_not_called()
        self.mocks["download_via_browser"].assert_not_called()

    def test_a_failed_record_route_falls_through_to_the_fast_download(self):
        self.mocks["db_aarecord"].return_value = None
        self.mocks["fast_download_info"].return_value = {
            "status": "ok", "download_url": "https://partner/a.pdf", "downloads_left": 24,
        }
        self.mocks["_download_to_file"].return_value = True
        result = self.run_download(md5=MD5SUM, secret_key=SECRET)
        self.assertEqual(result, os.path.join(self.folder, "out.pdf"))
        self.mocks["fast_download_info"].assert_called_once()

    def test_the_cached_md5_is_used_when_none_is_given(self):
        anna.remember_md5(DOI, MD5SUM)
        self.mocks["db_aarecord"].return_value = {"additional": {"ipfs_urls": ["https://gw/a.pdf"]}}
        self.mocks["download_via_ipfs"].return_value = True
        self.run_download(secret_key=SECRET)
        self.assertEqual(self.mocks["db_aarecord"].call_args[0][0], MD5SUM)

    def test_the_scidb_route_is_never_reached_without_the_opt_in(self):
        result = self.run_download(secret_key=SECRET, allow_scidb=False, allow_browser=False)
        self.assertIsNone(result)
        self.mocks["scidb_lookup"].assert_not_called()

    def test_the_scidb_route_runs_and_caches_the_md5_when_armed(self):
        self.mocks["scidb_lookup"].return_value = {"md5": MD5SUM, "url": "https://partner/a.pdf"}
        self.mocks["_download_to_file"].return_value = True
        result = self.run_download(secret_key=SECRET, allow_scidb=True)
        self.assertEqual(result, os.path.join(self.folder, "out.pdf"))
        self.mocks["scidb_lookup"].assert_called_once()
        self.assertEqual(anna.lookup_md5(DOI), MD5SUM)
        self.mocks["download_via_browser"].assert_not_called()

    def test_an_expired_partner_link_retries_the_md5_routes(self):
        # The SciDB page resolves the DOI, but its partner link has expired.
        self.mocks["scidb_lookup"].return_value = {"md5": MD5SUM, "url": "https://partner/a.pdf"}
        self.mocks["_download_to_file"].return_value = False
        self.mocks["db_aarecord"].return_value = {"additional": {"ipfs_urls": ["https://gw/a.pdf"]}}
        self.mocks["download_via_ipfs"].return_value = True
        result = self.run_download(secret_key=SECRET, allow_scidb=True)
        self.assertEqual(result, os.path.join(self.folder, "out.pdf"))
        self.assertEqual(self.mocks["db_aarecord"].call_args[0][0], MD5SUM)

    def test_a_rejected_key_stops_the_key_routes_being_retried(self):
        self.mocks["fast_download_info"].return_value = {"status": "invalid_key"}
        result = self.run_download(md5=MD5SUM, secret_key=SECRET,
                                   allow_scidb=True, allow_browser=False)
        self.assertIsNone(result)
        self.assertTrue(anna._KEY_ROUTES_DISABLED)
        # R4 needs the same key, so it must not be attempted afterwards.
        self.mocks["scidb_lookup"].assert_not_called()

    def test_an_exhausted_quota_skips_the_fast_download_route(self):
        anna._QUOTA_EXHAUSTED = True
        self.run_download(md5=MD5SUM, secret_key=SECRET, allow_browser=False)
        self.mocks["fast_download_info"].assert_not_called()

    def test_a_browser_resolved_md5_is_cached_and_retried(self):
        # The browser solved the check and read the md5, but the partner link
        # failed, so the cheaper routes get another chance with the new md5.
        self.mocks["download_via_browser"].return_value = {"md5": MD5SUM, "downloaded": False}
        self.mocks["db_aarecord"].return_value = {"additional": {"ipfs_urls": ["https://gw/a.pdf"]}}
        self.mocks["download_via_ipfs"].return_value = True
        result = self.run_download(secret_key=SECRET)
        self.assertEqual(result, os.path.join(self.folder, "out.pdf"))
        self.assertEqual(anna.lookup_md5(DOI), MD5SUM)

    def test_everything_exhausted_returns_none_without_launching_a_browser(self):
        result = self.run_download(secret_key=SECRET, allow_scidb=True, allow_browser=False)
        self.assertIsNone(result)
        self.mocks["download_via_browser"].assert_not_called()

    def test_neither_a_doi_nor_an_md5_is_refused(self):
        with redirect_stdout(io.StringIO()):
            self.assertIsNone(anna.download_paper(None, download_folder=self.folder))

    def test_the_routes_argument_limits_which_routes_run(self):
        self.mocks["download_via_browser"].return_value = {"md5": MD5SUM, "downloaded": True}
        self.run_download(secret_key=SECRET, allow_scidb=True, routes=("R1", "R2"))
        self.mocks["scidb_lookup"].assert_not_called()
        self.mocks["download_via_browser"].assert_not_called()


class BrowserAttemptCapTests(unittest.TestCase):
    def setUp(self):
        for name, value in (("_BROWSER_ATTEMPTS", 0), ("VERBOSE", False)):
            p = patch.object(anna, name, value)
            p.start()
            self.addCleanup(p.stop)

    def test_the_browser_is_not_retried_forever_across_a_doi_file_run(self):
        available = patch.object(anna, "browser_available", return_value=(True, ""))
        available.start()
        self.addCleanup(available.stop)
        launch = Mock(side_effect=RuntimeError("launch refused"))
        with patch.object(anna, "_launch_browser", launch):
            with redirect_stdout(io.StringIO()):
                for _ in range(anna.MAX_BROWSER_ATTEMPTS + 3):
                    anna.download_via_browser(DOI, "/tmp/x.pdf", "https://aa.test")
        self.assertEqual(launch.call_count, anna.MAX_BROWSER_ATTEMPTS)


if __name__ == "__main__":
    unittest.main()
