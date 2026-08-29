import os
import tempfile
import unittest

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


if __name__ == "__main__":
    unittest.main()
