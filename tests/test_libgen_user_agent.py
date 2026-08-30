import ast
import importlib
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import requests

LIBGEN_SOURCE = Path(__file__).resolve().parent.parent / "getscipapers_hoanganhduc" / "libgen.py"

# What every mirror answers to a request carrying no browser User-Agent.
NGINX_PLACEHOLDER = (
    "<!DOCTYPE html>\r\n<html>\r\n<head>\r\n<title>Welcome to nginx!</title>\r\n"
    "</head>\r\n<body>\r\n<h1>Welcome to nginx!</h1>\r\n</body>\r\n</html>\r\n"
)
LIBGEN_PAGE = '<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN"><title>Library Genesis</title>'
RECORD_JSON = '{"91167877": {"doi": "10.1016/j.jallcom.2020.157991", "title": "A paper"}}'


class FakeResponse:
    def __init__(self, text, status_code=200):
        self.text = text
        self.status_code = status_code
        self.content = text.encode()

    def json(self):
        import json

        return json.loads(self.text)


class RecordingGet:
    """Stand-in for ``requests.get`` that answers per host and records headers."""

    def __init__(self, bodies):
        self.bodies = bodies
        self.calls = []

    def __call__(self, url, **kwargs):
        self.calls.append({"url": url, "kwargs": kwargs})
        for host, body in self.bodies.items():
            if host in url:
                return FakeResponse(body)
        return FakeResponse(NGINX_PLACEHOLDER)


def load_libgen(get_stub):
    """Import ``libgen`` with ``requests.get`` stubbed out.

    The module probes every mirror at import time to pick ``LIBGEN_DOMAIN``, so
    importing it for real would put the test suite on the network.
    """

    sys.modules.pop("getscipapers_hoanganhduc.libgen", None)
    with patch.object(requests, "get", get_stub):
        return importlib.import_module("getscipapers_hoanganhduc.libgen")


class PlaceholderDetectionTests(unittest.TestCase):
    """LibGen answers HTTP 200 with nginx's default page when it does not like
    the request, so a mirror cannot be picked on status code alone."""

    def test_a_mirror_serving_the_placeholder_is_skipped(self):
        stub = RecordingGet({"libgen.la": LIBGEN_PAGE})
        libgen = load_libgen(stub)
        with patch.object(requests, "get", stub):
            self.assertEqual(libgen.select_active_libgen_domain(), "libgen.la")

    def test_all_mirrors_placeholder_falls_back_to_the_first(self):
        stub = RecordingGet({})
        libgen = load_libgen(stub)
        with patch.object(requests, "get", stub):
            self.assertEqual(
                libgen.select_active_libgen_domain(), libgen.LIBGEN_MIRRORS[0]
            )

    def test_a_live_mirror_is_still_selected(self):
        stub = RecordingGet({"libgen.li": LIBGEN_PAGE})
        libgen = load_libgen(stub)
        with patch.object(requests, "get", stub):
            self.assertEqual(libgen.select_active_libgen_domain(), "libgen.li")


class UserAgentTests(unittest.TestCase):
    """Without a browser User-Agent every LibGen request gets the placeholder,
    which made the whole module look like a dead site."""

    def test_domain_selection_sends_a_user_agent(self):
        stub = RecordingGet({"libgen.li": LIBGEN_PAGE})
        libgen = load_libgen(stub)
        stub.calls.clear()
        with patch.object(requests, "get", stub):
            libgen.select_active_libgen_domain()
        self.assertTrue(stub.calls)
        for call in stub.calls:
            self.assertIn("User-Agent", call["kwargs"].get("headers", {}))

    def test_doi_search_sends_a_user_agent_and_parses_the_record(self):
        stub = RecordingGet({"json.php": RECORD_JSON, "api.crossref.org": "{}"})
        libgen = load_libgen(stub)
        stub.calls.clear()
        with patch.object(requests, "get", stub):
            result = libgen.search_libgen_by_doi("10.1016/j.jallcom.2020.157991")
        self.assertIn("91167877", result)
        self.assertIn("User-Agent", stub.calls[0]["kwargs"].get("headers", {}))

    def test_every_request_in_the_module_passes_headers(self):
        """A single bare call is enough to bring the placeholder back, so guard
        the whole module rather than the paths exercised above."""

        tree = ast.parse(LIBGEN_SOURCE.read_text(encoding="utf-8"))
        bare = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not (isinstance(func, ast.Attribute) and func.attr in {"get", "post"}):
                continue
            if not (isinstance(func.value, ast.Name) and func.value.id == "requests"):
                continue
            if not any(kw.arg == "headers" for kw in node.keywords):
                bare.append(node.lineno)
        self.assertEqual(bare, [], f"requests calls without headers at lines {bare}")


if __name__ == "__main__":
    unittest.main()
