import asyncio
import os
import tempfile
import unittest
from contextlib import asynccontextmanager
from unittest.mock import patch

from getscipapers_hoanganhduc import getpapers


# What ScienceDirect actually returns for an open access Elsevier DOI: an HTML
# interstitial served with HTTP 200, which used to be stored as a PDF.
SCIENCEDIRECT_INTERSTITIAL = (
    b"\n\n\n<!DOCTYPE HTML PUBLIC \"-//W3C//DTD HTML 4.01 Transitional//EN\">\n"
    b"<html>\n<head>\n<meta charset=\"utf-8\">\n"
    b"<meta HTTP-EQUIV=\"REFRESH\" content=\"2; url='/retrieve/articleSelectSinglePerm"
    b"?Redirect=https%3A%2F%2Fwww.sciencedirect.com%2Fscience%2Farticle%2Fpii"
    b"%2FS0022249625000227'\">\n<title>Redirecting</title>\n</head>\n</html>\n"
)

MINIMAL_PDF = b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"


class LooksLikePdfTests(unittest.TestCase):
    def test_accepts_pdf_header(self):
        self.assertTrue(getpapers.looks_like_pdf(MINIMAL_PDF))

    def test_accepts_pdf_header_after_leading_bytes(self):
        self.assertTrue(getpapers.looks_like_pdf(b"\n\r\n" + MINIMAL_PDF))

    def test_rejects_sciencedirect_interstitial(self):
        self.assertFalse(getpapers.looks_like_pdf(SCIENCEDIRECT_INTERSTITIAL))

    def test_rejects_html_error_page(self):
        self.assertFalse(getpapers.looks_like_pdf(b"<html><body>403 Forbidden</body></html>"))

    def test_rejects_empty_body(self):
        self.assertFalse(getpapers.looks_like_pdf(b""))


class SavePdfIfValidTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.filepath = os.path.join(self._tmp.name, "paper.pdf")

    def test_writes_real_pdf(self):
        self.assertTrue(getpapers.save_pdf_if_valid(MINIMAL_PDF, self.filepath, "test"))
        with open(self.filepath, "rb") as f:
            self.assertEqual(f.read(), MINIMAL_PDF)

    def test_refuses_interstitial_and_leaves_no_file(self):
        self.assertFalse(
            getpapers.save_pdf_if_valid(SCIENCEDIRECT_INTERSTITIAL, self.filepath, "test")
        )
        self.assertFalse(os.path.exists(self.filepath))


# What a parked Anna's Archive lookalike serves on a content path: an affiliate
# bounce page delivered with HTTP 200, which used to be stored as a PDF.
SQUATTER_BOUNCE_PAGE = (
    b"<!DOCTYPE html><html lang=\"en\"><head><meta charset=\"utf-8\">"
    b"<title>Loading...</title></head><body><div class=\"w\">"
    b"<div class=\"b\">Click for continue....</div>"
    b"<div class=\"s\">Antibot solution</div></div></body></html>"
)

MD5SUM = "0123456789abcdef0123456789abcdef"

SCIDB_PAGE = (
    '<html><body>'
    '<a href="/md5/{md5}">Record in Anna’s Archive</a>'
    '<a href="/fast_download/Some Paper -- Some Author -- {md5} -- '
    'Anna’s Archive.pdf">Download</a>'
    '</body></html>'
).format(md5=MD5SUM)


class DownloadFromAnnaArchiveTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.folder = self._tmp.name
        self.filepath = os.path.join(self.folder, "10.1000_test_anna.pdf")

    def _run_with_pdf_body(self, body):
        """Serve the scidb page once, then body for every PDF link that follows."""

        @asynccontextmanager
        async def fake_get(url, **kwargs):
            if "/scidb/" in url:
                yield FakeAiohttpResponse(200, SCIDB_PAGE.encode("utf-8"))
            else:
                yield FakeAiohttpResponse(200, body)

        with patch.object(getpapers, "_aiohttp_get", fake_get):
            return asyncio.run(
                getpapers.download_from_anna_archive("10.1000/test", self.folder)
            )

    def test_saves_a_real_pdf(self):
        self.assertTrue(self._run_with_pdf_body(MINIMAL_PDF))
        with open(self.filepath, "rb") as f:
            self.assertEqual(f.read(), MINIMAL_PDF)

    def test_refuses_bounce_page_and_leaves_no_file(self):
        self.assertFalse(self._run_with_pdf_body(SQUATTER_BOUNCE_PAGE))
        self.assertFalse(os.path.exists(self.filepath))


class FakeAiohttpResponse:
    def __init__(self, status, body):
        self.status = status
        self._body = body

    async def text(self):
        return self._body.decode("utf-8", "replace")

    async def read(self):
        return self._body


if __name__ == "__main__":
    unittest.main()
