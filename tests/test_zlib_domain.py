import unittest
from unittest.mock import patch

import requests

from getscipapers_hoanganhduc import Zlibrary

# What a walled host serves on every /eapi/ path.
DIAMWALL_PAGE = (
    "<html><head><title>Verifying your browser | DiamWall</title></head>"
    "<body></body></html>"
)
NGINX_404 = "<html><head><title>404 Not Found</title></head><body></body></html>"
DOMAINS_JSON = '{"success":1,"domains":[{"domain":"z-library.sk"}]}'


class FakeResponse:
    def __init__(self, text, status_code=200, content_type="text/html"):
        self.text = text
        self.status_code = status_code
        self.headers = {"content-type": content_type}

    def json(self):
        import json

        return json.loads(self.text)


class RecordingGet:
    """Stand-in for ``requests.get`` that answers per host and records calls."""

    def __init__(self, bodies):
        self.bodies = bodies
        self.calls = []

    def __call__(self, url, **kwargs):
        self.calls.append({"url": url, "kwargs": kwargs})
        for host, response in self.bodies.items():
            if host in url:
                return response
        return FakeResponse(DIAMWALL_PAGE, status_code=513)


def json_response():
    return FakeResponse(DOMAINS_JSON, content_type="application/json; charset=UTF-8")


class DomainSelectionTests(unittest.TestCase):
    """The hardcoded domain went stale, and the hosts that replaced it answer a
    browser check rather than an error, so a host cannot be picked on the
    status code alone."""

    def setUp(self):
        Zlibrary._active_domain = None
        self.addCleanup(setattr, Zlibrary, "_active_domain", None)

    def test_the_first_domain_answering_json_is_selected(self):
        stub = RecordingGet({"z-lib.gd": json_response()})
        with patch.object(requests, "get", stub):
            self.assertEqual(Zlibrary.select_active_domain(), "z-lib.gd")

    def test_a_browser_checked_domain_is_skipped(self):
        stub = RecordingGet({"article.sk": json_response()})
        with patch.object(requests, "get", stub):
            self.assertEqual(Zlibrary.select_active_domain(), "article.sk")

    def test_a_domain_serving_a_404_page_is_skipped(self):
        stub = RecordingGet({
            "z-lib.gd": FakeResponse(NGINX_404, status_code=404),
            "article.sk": json_response(),
        })
        with patch.object(requests, "get", stub):
            self.assertEqual(Zlibrary.select_active_domain(), "article.sk")

    def test_a_json_body_without_success_is_skipped(self):
        stub = RecordingGet({
            "z-lib.gd": FakeResponse(
                '{"success":0}', content_type="application/json"
            ),
            "article.sk": json_response(),
        })
        with patch.object(requests, "get", stub):
            self.assertEqual(Zlibrary.select_active_domain(), "article.sk")

    def test_a_connection_error_moves_on_to_the_next_domain(self):
        def failing_get(url, **kwargs):
            if "z-lib.gd" in url:
                raise requests.ConnectionError("dns failure")
            return json_response()

        with patch.object(requests, "get", failing_get):
            self.assertEqual(Zlibrary.select_active_domain(), "article.sk")

    def test_every_domain_unusable_falls_back_to_the_first(self):
        stub = RecordingGet({})
        with patch.object(requests, "get", stub):
            self.assertEqual(Zlibrary.select_active_domain(), Zlibrary.DOMAINS[0])

    def test_the_probe_sends_a_user_agent_and_a_timeout(self):
        stub = RecordingGet({"z-lib.gd": json_response()})
        with patch.object(requests, "get", stub):
            Zlibrary.select_active_domain()
        self.assertTrue(stub.calls)
        for call in stub.calls:
            self.assertIn("user-agent", call["kwargs"].get("headers", {}))
            self.assertEqual(
                call["kwargs"].get("timeout"), Zlibrary.DOMAIN_PROBE_TIMEOUT
            )


class DomainCachingTests(unittest.TestCase):
    """Resolving on first use rather than at import keeps the test suite and
    every unrelated CLI invocation off the network."""

    def setUp(self):
        Zlibrary._active_domain = None
        self.addCleanup(setattr, Zlibrary, "_active_domain", None)

    def test_a_selected_domain_is_probed_only_once(self):
        stub = RecordingGet({"z-lib.gd": json_response()})
        with patch.object(requests, "get", stub):
            Zlibrary.select_active_domain()
            Zlibrary.select_active_domain()
        self.assertEqual(len(stub.calls), 1)

    def test_a_failed_selection_is_not_cached(self):
        stub = RecordingGet({})
        with patch.object(requests, "get", stub):
            self.assertEqual(Zlibrary.select_active_domain(), Zlibrary.DOMAINS[0])
        stub = RecordingGet({"article.sk": json_response()})
        with patch.object(requests, "get", stub):
            self.assertEqual(Zlibrary.select_active_domain(), "article.sk")

    def test_importing_the_module_does_not_probe(self):
        import importlib
        import sys

        sys.modules.pop("getscipapers_hoanganhduc.Zlibrary", None)
        stub = RecordingGet({})
        with patch.object(requests, "get", stub):
            module = importlib.import_module("getscipapers_hoanganhduc.Zlibrary")
        self.assertEqual(stub.calls, [])
        self.assertIsNone(module._active_domain)


if __name__ == "__main__":
    unittest.main()
