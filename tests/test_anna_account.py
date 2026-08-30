import io
import json
import os
import stat
import tempfile
import time
import unittest
import urllib.request
from contextlib import redirect_stdout
from unittest.mock import patch

import requests

from getscipapers_hoanganhduc import anna


MD5SUM = "a5efa9791b836507541d615ed3f069e9"
SECRET = "SuperSecretAccountKey"
MINIMAL_PDF = b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"


# A member SciDB page often renders straight into the PDF viewer, with the real
# file URL carried only in the viewer's file= parameter and no anchor at all.
PDFJS_PAGE = (
    '<html><body>'
    '<a href="/md5/{md5}">Record</a>'
    '<iframe src="/pdfjs/web/viewer.html?file=https%3A%2F%2Fwbsg8v.xyz%2Fd1%2F'
    'paper.pdf%3Fkey%3Dabc"></iframe>'
    '</body></html>'
).format(md5=MD5SUM)

# The anonymous shape: a download anchor whose href carries the md5.
PARTNER_ANCHOR_PAGE = (
    '<html><body>'
    '<a href="/md5/{md5}">Record in Anna’s Archive</a>'
    '<a href="/fast_download/Some Paper -- Some Author -- {md5} -- '
    'Anna’s Archive.pdf">下载</a>'
    '</body></html>'
).format(md5=MD5SUM)

# What the hourly cap serves: no record link and no download link.
HOURLY_CAP_PAGE = (
    '<html><body><p>You have reached the maximum number of SciDB downloads '
    'for this hour. Please try again later.</p></body></html>'
)


class FakeResponse:
    def __init__(self, status_code=200, payload=None, body=b"", cookies=None, text=None):
        self.status_code = status_code
        self._payload = payload
        self.content = body
        self._text = text
        self.cookies = cookies or {}

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload

    @property
    def text(self):
        if self._text is not None:
            return self._text
        return self.content.decode("utf-8", "replace")

    def close(self):
        pass


class AnnaTestCase(unittest.TestCase):
    """Isolate the on-disk state and the process-wide session flags."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.home = self._tmp.name

        patcher = patch.object(anna, "get_cache_directory", lambda: self.home)
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

        env = patch.dict(os.environ, {}, clear=False)
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop(anna.SECRET_KEY_ENV, None)


class CredentialTests(AnnaTestCase):
    def test_saves_and_reloads_the_secret(self):
        path = anna.default_credentials_file()
        self.assertTrue(anna.save_credentials_to_file(SECRET, path))
        self.assertEqual(anna.load_credentials_from_file(path), SECRET)

    def test_saved_file_is_owner_only_on_posix(self):
        if os.name != "posix":
            self.skipTest("POSIX permissions only")
        path = anna.default_credentials_file()
        anna.save_credentials_to_file(SECRET, path)
        mode = stat.S_IMODE(os.stat(path).st_mode)
        self.assertEqual(mode, stat.S_IRUSR | stat.S_IWUSR)

    def test_missing_and_malformed_files_return_none(self):
        self.assertIsNone(anna.load_credentials_from_file(os.path.join(self.home, "nope.json")))
        bad = os.path.join(self.home, "bad.json")
        with open(bad, "w", encoding="utf-8") as f:
            f.write("{not json")
        self.assertIsNone(anna.load_credentials_from_file(bad))
        empty = os.path.join(self.home, "empty.json")
        with open(empty, "w", encoding="utf-8") as f:
            json.dump({"something_else": "x"}, f)
        self.assertIsNone(anna.load_credentials_from_file(empty))

    def test_non_default_file_is_mirrored_into_the_default_location(self):
        other = os.path.join(self.home, "elsewhere.json")
        anna.save_credentials_to_file(SECRET, other)
        self.assertEqual(anna.load_credentials_from_file(other), SECRET)
        with open(anna.default_credentials_file(), encoding="utf-8") as f:
            self.assertEqual(json.load(f)["anna_secret_key"], SECRET)

    def test_environment_beats_the_default_file(self):
        anna.save_credentials_to_file("from-file")
        os.environ[anna.SECRET_KEY_ENV] = "from-env"
        self.assertEqual(anna.resolve_secret_key(), "from-env")

    def test_explicit_argument_beats_the_environment(self):
        os.environ[anna.SECRET_KEY_ENV] = "from-env"
        self.assertEqual(anna.resolve_secret_key("explicit"), "explicit")

    def test_credentials_flag_beats_the_default_file(self):
        anna.save_credentials_to_file("from-default")
        other = os.path.join(self.home, "flag.json")
        anna.save_credentials_to_file("from-flag", other)
        self.assertEqual(anna.resolve_secret_key(credentials_file=other), "from-flag")

    def test_non_interactive_never_prompts(self):
        with patch.object(anna, "getpass", side_effect=AssertionError("prompted")):
            self.assertIsNone(anna.resolve_secret_key(interactive=False))


class AccountCookieExpiryTests(unittest.TestCase):
    def test_reads_an_unpadded_stripped_jwt(self):
        # Anna's Archive strips the constant JWT header, so the payload is the
        # first segment and its base64 padding has been removed.
        import base64

        payload = base64.urlsafe_b64encode(
            json.dumps({"a": 42, "exp": 1800000000}).encode()
        ).decode().rstrip("=")
        self.assertNotEqual(len(payload) % 4, 0, "fixture must exercise re-padding")
        expiry = anna.account_cookie_expiry(f"{payload}.signaturebytes")
        self.assertIsNotNone(expiry)
        self.assertEqual(int(expiry.timestamp()), 1800000000)

    def test_garbage_returns_none(self):
        for value in ("", "not-a-cookie", "!!!.!!!", "e30.sig"):
            self.assertIsNone(anna.account_cookie_expiry(value))


class LoginTests(AnnaTestCase):
    def test_success_is_decided_by_the_cookie_not_the_status(self):
        response = FakeResponse(200, cookies={anna.ACCOUNT_COOKIE_NAME: "cookie-value"})
        with patch.object(anna, "_requests_request", return_value=response):
            self.assertEqual(anna.login(SECRET, "https://aa.test"), "cookie-value")

    def test_a_rejected_key_still_answers_http_200(self):
        with patch.object(anna, "_requests_request", return_value=FakeResponse(200)):
            self.assertIsNone(anna.login("wrong", "https://aa.test"))


class RecordRouteTests(AnnaTestCase):
    def test_member_record_is_parsed(self):
        payload = {"additional": {"ipfs_urls": [{"url": "https://gw.test/a.pdf"}]}}
        with patch.object(anna, "_requests_request", return_value=FakeResponse(200, payload)):
            record = anna.db_aarecord(MD5SUM, "cookie", "https://aa.test")
        self.assertEqual(anna.record_download_urls(record), ["https://gw.test/a.pdf"])

    def test_non_member_record_lookup_returns_none(self):
        with patch.object(anna, "_requests_request", return_value=FakeResponse(403)):
            self.assertIsNone(anna.db_aarecord(MD5SUM, "cookie", "https://aa.test"))

    def test_download_urls_survive_the_several_entry_shapes(self):
        record = {
            "additional": {
                "ipfs_urls": [
                    {"url": "https://gw.test/a.pdf", "name": "gw"},
                    "https://gw2.test/b.pdf",
                ],
                "download_urls": [
                    ["Mirror", "https://mirror.test/c.pdf", ""],
                    {"nothing": "useful"},
                ],
            }
        }
        self.assertEqual(
            anna.record_download_urls(record),
            ["https://gw.test/a.pdf", "https://gw2.test/b.pdf", "https://mirror.test/c.pdf"],
        )


class FastDownloadStatusTests(AnnaTestCase):
    def _status(self, response):
        with patch.object(anna, "_requests_request", return_value=response):
            return anna.fast_download_info(MD5SUM, SECRET, "https://aa.test")["status"]

    def test_ok(self):
        payload = {
            "download_url": "https://partner.test/a.pdf",
            "account_fast_download_info": {"downloads_left": 24},
        }
        with patch.object(anna, "_requests_request", return_value=FakeResponse(200, payload)):
            info = anna.fast_download_info(MD5SUM, SECRET, "https://aa.test")
        self.assertEqual(info["status"], "ok")
        self.assertEqual(info["downloads_left"], 24)

    def test_http_200_without_a_url_is_a_failure(self):
        self.assertEqual(self._status(FakeResponse(200, {"account_fast_download_info": {}})), "error")

    def test_status_codes_map_to_distinct_outcomes(self):
        self.assertEqual(self._status(FakeResponse(400)), "bad_md5")
        self.assertEqual(self._status(FakeResponse(401)), "invalid_key")
        self.assertEqual(self._status(FakeResponse(403)), "not_member")
        self.assertEqual(self._status(FakeResponse(404)), "not_found")
        self.assertEqual(self._status(FakeResponse(429)), "quota")
        self.assertEqual(self._status(FakeResponse(500)), "server_error")

    def test_rejected_key_disables_the_key_routes(self):
        with patch.object(anna, "_requests_request", return_value=FakeResponse(401)):
            with redirect_stdout(io.StringIO()):
                self.assertFalse(
                    anna.download_by_md5(MD5SUM, SECRET, "https://aa.test", "/tmp/x.pdf")
                )
        self.assertTrue(anna._KEY_ROUTES_DISABLED)

    def test_quota_exhaustion_is_remembered(self):
        with patch.object(anna, "_requests_request", return_value=FakeResponse(429)):
            with redirect_stdout(io.StringIO()):
                anna.download_by_md5(MD5SUM, SECRET, "https://aa.test", "/tmp/x.pdf")
        self.assertTrue(anna._QUOTA_EXHAUSTED)

    def test_unknown_md5_is_dropped_from_the_cache(self):
        anna.remember_md5("10.1000/test", MD5SUM)
        with patch.object(anna, "_requests_request", return_value=FakeResponse(404)):
            with redirect_stdout(io.StringIO()):
                anna.download_by_md5(MD5SUM, SECRET, "https://aa.test", "/tmp/x.pdf",
                                     doi="10.1000/test")
        self.assertIsNone(anna.lookup_md5("10.1000/test"))


class SecretRedactionTests(AnnaTestCase):
    def test_secret_key_never_reaches_stdout(self):
        anna.VERBOSE = True
        failure = requests.exceptions.RequestException(
            f"failed to reach https://aa.test/dyn/api/fast_download.json?md5={MD5SUM}&key={SECRET}"
        )
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            with patch.object(anna, "_requests_request", side_effect=failure):
                anna.fast_download_info(MD5SUM, SECRET, "https://aa.test")
            with patch.object(anna, "_requests_request", return_value=FakeResponse(401)):
                anna.download_by_md5(MD5SUM, SECRET, "https://aa.test", "/tmp/x.pdf")
            anna.debug_print(anna._redact(f"https://aa.test/x?md5={MD5SUM}&key={SECRET}"))
        self.assertNotIn(SECRET, buffer.getvalue())
        self.assertIn("<redacted>", buffer.getvalue())


class Md5CacheTests(AnnaTestCase):
    def test_round_trip(self):
        self.assertIsNone(anna.lookup_md5("10.1000/test"))
        self.assertTrue(anna.remember_md5("10.1000/TEST", MD5SUM))
        self.assertEqual(anna.lookup_md5("10.1000/test"), MD5SUM)
        self.assertTrue(anna.forget_md5("10.1000/test"))
        self.assertIsNone(anna.lookup_md5("10.1000/test"))

    def test_corrupt_cache_is_discarded_rather_than_raised(self):
        path = anna.md5_cache_file()
        with open(path, "w", encoding="utf-8") as f:
            f.write("{ this is not json")
        self.assertEqual(anna.load_md5_cache(), {})
        self.assertFalse(os.path.exists(path))


class ScidbParsingTests(unittest.TestCase):
    def test_reads_the_viewer_file_parameter(self):
        parsed = anna.parse_scidb_page(PDFJS_PAGE, "https://aa.test")
        self.assertEqual(parsed["md5"], MD5SUM)
        self.assertEqual(parsed["url"], "https://wbsg8v.xyz/d1/paper.pdf?key=abc")

    def test_reads_a_localised_download_anchor(self):
        parsed = anna.parse_scidb_page(PARTNER_ANCHOR_PAGE, "https://aa.test")
        self.assertEqual(parsed["md5"], MD5SUM)
        self.assertTrue(parsed["url"].startswith("https://aa.test/fast_download/"))

    def test_hourly_cap_page_yields_nothing(self):
        self.assertIsNone(anna.parse_scidb_page(HOURLY_CAP_PAGE, "https://aa.test"))

    def test_empty_input_yields_nothing(self):
        self.assertIsNone(anna.parse_scidb_page("", "https://aa.test"))


class BrowserCapabilityTests(unittest.TestCase):
    def test_missing_chromium_is_named(self):
        with patch.object(anna, "_resolve_browser_tools", return_value=(None, "/usr/bin/chromedriver", None)):
            available, reason = anna.browser_available()
        self.assertFalse(available)
        self.assertIn("Chromium", reason)

    def test_missing_chromedriver_is_named(self):
        with patch.object(anna, "_resolve_browser_tools", return_value=("/usr/bin/chromium", None, None)):
            available, reason = anna.browser_available()
        self.assertFalse(available)
        self.assertIn("chromedriver", reason)

    def test_missing_xvfb_on_a_headless_linux_host_is_named(self):
        with patch.object(anna, "_resolve_browser_tools",
                          return_value=("/usr/bin/chromium", "/usr/bin/chromedriver", None)):
            with patch.object(anna.platform, "system", return_value="Linux"):
                with patch.dict(os.environ, {}, clear=False):
                    os.environ.pop("DISPLAY", None)
                    with patch.object(anna.shutil, "which", return_value=None):
                        available, reason = anna.browser_available()
        self.assertFalse(available)
        self.assertIn("xvfb-run", reason)

    def test_absent_selenium_is_reported_rather_than_swallowed(self):
        with patch.object(anna, "_resolve_browser_tools", return_value=(None, None, "Selenium is not installed: x")):
            available, reason = anna.browser_available()
        self.assertFalse(available)
        self.assertIn("Selenium", reason)


class CdpTargetTests(unittest.TestCase):
    """The DevTools endpoint is on loopback, so it must never be proxied."""

    def serve_once(self, payload):
        import http.server
        import threading

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                body = json.dumps(payload).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        self.addCleanup(server.server_close)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.shutdown)
        return server.server_address[1]

    def test_targets_are_read_even_when_a_proxy_is_configured(self):
        targets = [{"type": "page", "title": "DDoS-Guard", "url": "https://annas-archive.gl/"}]
        port = self.serve_once(targets)
        # A proxy pointing at a dead port, exactly as apply_environment leaves
        # the environment once a proxy configuration is loaded.
        dead = "socks5://127.0.0.1:1"
        # urlopen caches one default opener per process, so an earlier proxy-free
        # call would otherwise hide the regression this test guards against.
        with patch.object(urllib.request, "_opener", None), \
                patch.dict(os.environ, {"http_proxy": dead, "HTTP_PROXY": dead}, clear=False):
            self.assertEqual(anna._cdp_targets(port), targets)

    def test_an_unreachable_endpoint_is_reported_not_swallowed(self):
        anna._LAST_CDP_ERROR = None
        buf = io.StringIO()
        with patch.object(anna, "VERBOSE", True), redirect_stdout(buf):
            self.assertEqual(anna._cdp_targets(1), [])
        self.assertIn("DevTools", buf.getvalue())


class BrowserTeardownTests(unittest.TestCase):
    """The profile may only be deleted once the whole group has exited."""

    def test_it_returns_as_soon_as_the_group_is_gone(self):
        calls = []

        def killpg(group, sig):
            calls.append(sig)
            if len(calls) >= 2:
                raise ProcessLookupError()

        with patch.object(anna.os, "killpg", killpg):
            self.assertTrue(anna._wait_for_group_exit(4242, time.time() + 5))
        self.assertEqual(calls, [0, 0])

    def test_a_group_that_outlives_the_deadline_is_killed(self):
        sent = []
        with patch.object(anna.os, "killpg", lambda g, s: sent.append(s)):
            self.assertFalse(anna._wait_for_group_exit(4242, time.time() - 1))
        self.assertEqual(sent, [anna.signal.SIGKILL])


class WaitForSolveTests(unittest.TestCase):
    """A run that times out must say which of the two things happened: the page
    never loaded at all, or it sat on the interstitial for the whole budget."""

    def test_a_page_that_never_loads_reports_nothing_seen(self):
        with patch.object(anna, "_cdp_targets", lambda port: []):
            self.assertIsNone(anna._wait_for_solve(1, time.time() + 0.1, poll=0.01))

    def test_a_page_stuck_on_the_interstitial_reports_the_challenge_title(self):
        targets = [{"type": "page", "title": anna.CHALLENGE_TITLE,
                    "url": "https://annas-archive.gl/scidb/10.1000/test/?&check=1"}]
        with patch.object(anna, "_cdp_targets", lambda port: targets):
            self.assertEqual(
                anna._wait_for_solve(1, time.time() + 0.1, poll=0.01),
                anna.CHALLENGE_TITLE,
            )

    def test_a_solved_page_still_returns_its_title(self):
        targets = [{"type": "page", "title": "A paper - Anna\u2019s Archive",
                    "url": "https://annas-archive.gl/scidb/10.1000/test"}]
        with patch.object(anna, "_cdp_targets", lambda port: targets):
            self.assertEqual(
                anna._wait_for_solve(1, time.time() + 5, poll=0.01),
                "A paper - Anna\u2019s Archive",
            )


class BrowserTimeoutMessageTests(unittest.TestCase):
    """Sitting on the interstitial for the whole budget means the exit address is
    being held at the manual captcha, which no unattended run can clear. Saying
    only "not solved in time" invites a pointless retry with a longer timeout."""

    def run_browser(self, last_title):
        with patch.object(anna, "browser_available", lambda: (True, "")), \
                patch.object(anna, "_resolve_browser_tools",
                             lambda: ("/usr/bin/chromium", "/usr/bin/chromedriver", None)), \
                patch.object(anna, "_launch_browser", lambda *a, **k: None), \
                patch.object(anna, "_read_devtools_port", lambda *a, **k: 4242), \
                patch.object(anna, "_wait_for_solve", lambda *a, **k: last_title), \
                patch.object(anna, "_terminate_browser", lambda proc: None):
            buf = io.StringIO()
            with redirect_stdout(buf):
                result = anna.download_via_browser(
                    "10.1000/test", os.path.join(self.folder, "t.pdf"),
                    "https://annas-archive.gl",
                )
            return result, buf.getvalue()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = self.tmp.name
        self.addCleanup(self.tmp.cleanup)
        anna._BROWSER_ATTEMPTS = 0

    def test_the_manual_captcha_wall_is_named(self):
        result, out = self.run_browser(anna.CHALLENGE_TITLE)
        self.assertIsNone(result)
        self.assertIn("manual", out.lower())

    def test_a_page_that_never_loaded_is_not_blamed_on_the_captcha(self):
        result, out = self.run_browser(None)
        self.assertIsNone(result)
        self.assertNotIn("manual", out.lower())


class SolveDetectionTests(unittest.TestCase):
    """The solved record page still mentions ddos-guard in its own scripts, so
    the challenge must be detected by title rather than by a substring search."""

    def test_a_real_title_counts_as_solved(self):
        self.assertTrue(anna._solved(
            "FeSiBCrC amorphous magnetic powder fabricated by gas-water combined "
            "atomization - Anna’s Archive"
        ))

    def test_the_challenge_title_does_not(self):
        self.assertFalse(anna._solved("DDoS-Guard"))

    def test_an_empty_title_does_not(self):
        self.assertFalse(anna._solved(""))
        self.assertFalse(anna._solved(None))

    def test_a_url_title_does_not(self):
        self.assertFalse(anna._solved("https://annas-archive.gl/scidb/10.1000/test"))

    def test_a_bare_host_title_does_not(self):
        """Chromium titles its network-error page with the bare host, so a run
        whose proxy is dead would otherwise be read as a solved challenge."""
        for host in ("annas-archive.gl", "annas-archive.pk", "annas-archive.gd"):
            self.assertFalse(anna._solved(host), host)

    def test_a_paper_title_naming_the_site_still_counts_as_solved(self):
        self.assertTrue(anna._solved("A paper - Anna\u2019s Archive"))


if __name__ == "__main__":
    unittest.main()
