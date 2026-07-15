import unittest
from unittest.mock import patch

import requests

from getscipapers_hoanganhduc import getpapers
from getscipapers_hoanganhduc.proxy_config import ProxySettings


class FakeResponse:
    def __init__(self, status_code):
        self.status_code = status_code
        self.closed = False

    def close(self):
        self.closed = True


class FakeSession:
    calls = []
    responses = []

    def __enter__(self):
        self.trust_env = True
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def request(self, method, url, **kwargs):
        self.__class__.calls.append(
            {
                "method": method,
                "url": url,
                "kwargs": kwargs,
                "trust_env": self.trust_env,
            }
        )
        response = self.__class__.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class RequestsProxyFallbackTests(unittest.TestCase):
    def setUp(self):
        self.original_proxy = getpapers.ACTIVE_PROXY
        getpapers.ACTIVE_PROXY = ProxySettings(
            enabled=True,
            proxy_url="http://proxy.example:8080",
            source="test",
        )
        FakeSession.calls = []

    def tearDown(self):
        getpapers.ACTIVE_PROXY = self.original_proxy

    def test_direct_success_does_not_use_proxy(self):
        FakeSession.responses = [FakeResponse(200)]
        with patch.object(getpapers.requests, "Session", FakeSession):
            response = getpapers._requests_get("https://example.test", timeout=1)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(FakeSession.calls), 1)
        self.assertNotIn("proxies", FakeSession.calls[0]["kwargs"])
        self.assertFalse(FakeSession.calls[0]["trust_env"])

    def test_direct_exception_retries_with_proxy(self):
        FakeSession.responses = [
            requests.exceptions.ConnectTimeout("direct failed"),
            FakeResponse(200),
        ]
        with patch.object(getpapers.requests, "Session", FakeSession):
            response = getpapers._requests_get("https://example.test", timeout=1)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(FakeSession.calls), 2)
        self.assertNotIn("proxies", FakeSession.calls[0]["kwargs"])
        self.assertEqual(
            FakeSession.calls[1]["kwargs"]["proxies"],
            {
                "http": "http://proxy.example:8080",
                "https": "http://proxy.example:8080",
            },
        )
        self.assertFalse(FakeSession.calls[0]["trust_env"])
        self.assertFalse(FakeSession.calls[1]["trust_env"])

    def test_retryable_status_retries_with_proxy(self):
        direct_response = FakeResponse(503)
        FakeSession.responses = [direct_response, FakeResponse(200)]
        with patch.object(getpapers.requests, "Session", FakeSession):
            response = getpapers._requests_get("https://example.test", timeout=1)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(direct_response.closed)
        self.assertEqual(len(FakeSession.calls), 2)
        self.assertNotIn("proxies", FakeSession.calls[0]["kwargs"])
        self.assertIn("proxies", FakeSession.calls[1]["kwargs"])


if __name__ == "__main__":
    unittest.main()
