import asyncio
import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import Mock, patch

from getscipapers_hoanganhduc import anna, getpapers


DOI = "10.1000/test"
MD5SUM = "a5efa9791b836507541d615ed3f069e9"


class AnnaRouterTests(unittest.TestCase):
    """The router in getpapers keeps the anonymous scrape between the two
    account stages, and hands the anna module the state it needs."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.folder = self._tmp.name

        self.download_paper = Mock(return_value=None)
        p = patch.object(anna, "download_paper", self.download_paper)
        p.start()
        self.addCleanup(p.stop)

        self.legacy = Mock(return_value=False)

        async def legacy_route(doi, download_folder):
            return self.legacy(doi, download_folder)

        p = patch.object(getpapers, "download_from_anna_archive", legacy_route)
        p.start()
        self.addCleanup(p.stop)

        p = patch.object(getpapers, "ANNA_ROUTE_OPTIONS",
                         {"scidb": False, "browser": True, "md5": None})
        p.start()
        self.addCleanup(p.stop)

    def run_router(self, **kwargs):
        with redirect_stdout(io.StringIO()):
            return asyncio.run(
                getpapers.download_from_anna_archive_all_routes(DOI, self.folder, **kwargs)
            )

    def test_the_anonymous_scrape_runs_before_the_account_routes_resolve_the_doi(self):
        self.legacy.return_value = True
        self.assertTrue(self.run_router())
        self.legacy.assert_called_once_with(DOI, self.folder)
        # R1/R2 ran first because they are cheap, but the DOI-resolving stage
        # must not run once the anonymous scrape has already succeeded.
        self.assertEqual(
            [call.kwargs["routes"] for call in self.download_paper.call_args_list],
            [("R1", "R2")],
        )

    def test_both_account_stages_run_when_the_anonymous_scrape_fails(self):
        self.assertFalse(self.run_router())
        self.assertEqual(
            [call.kwargs["routes"] for call in self.download_paper.call_args_list],
            [("R1", "R2"), ("R4", "R5")],
        )

    def test_a_successful_account_route_reports_success(self):
        self.download_paper.return_value = os.path.join(self.folder, "x.pdf")
        self.assertTrue(self.run_router())
        self.legacy.assert_not_called()

    def test_the_existing_filename_convention_is_preserved(self):
        self.run_router()
        self.assertEqual(
            self.download_paper.call_args.kwargs["filename"], "10.1000_test_anna.pdf"
        )

    def test_verbose_and_proxy_settings_are_propagated(self):
        settings = getpapers.proxy_config.ProxySettings(enabled=True, proxy_url="socks5://127.0.0.1:1081")
        seen = {}

        def capture(*args, **kwargs):
            seen["verbose"] = anna.VERBOSE
            seen["proxy"] = anna.ACTIVE_PROXY
            return None

        self.download_paper.side_effect = capture
        with patch.object(getpapers, "VERBOSE", True), patch.object(getpapers, "ACTIVE_PROXY", settings):
            self.run_router()
        self.assertTrue(seen["verbose"])
        self.assertIs(seen["proxy"], settings)

    def test_route_options_from_the_cli_reach_the_module(self):
        with patch.object(getpapers, "ANNA_ROUTE_OPTIONS",
                          {"scidb": True, "browser": False, "md5": MD5SUM}):
            self.run_router()
        kwargs = self.download_paper.call_args.kwargs
        self.assertTrue(kwargs["allow_scidb"])
        self.assertFalse(kwargs["allow_browser"])
        self.assertEqual(kwargs["md5"], MD5SUM)

    def test_explicit_arguments_override_the_cli_options(self):
        with patch.object(getpapers, "ANNA_ROUTE_OPTIONS",
                          {"scidb": True, "browser": True, "md5": None}):
            self.run_router(allow_scidb=False, md5=MD5SUM)
        kwargs = self.download_paper.call_args.kwargs
        self.assertFalse(kwargs["allow_scidb"])
        self.assertEqual(kwargs["md5"], MD5SUM)


class DispatcherTests(unittest.TestCase):
    def test_the_anna_branch_calls_the_router(self):
        source = getpapers.download_by_doi.__code__.co_names
        self.assertIn("download_from_anna_archive_all_routes", source)


if __name__ == "__main__":
    unittest.main()
