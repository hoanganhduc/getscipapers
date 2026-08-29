import os
import tempfile
import unittest

from getscipapers_hoanganhduc import document_utils


MINIMAL_PDF = b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"
EPUB_BYTES = b"PK\x03\x04\x14\x00\x00\x00\x00\x00mimetypeapplication/epub+zip"
HTML_ERROR = b"<!DOCTYPE html>\n<html><head><title>403 Forbidden</title></head></html>"
INTERSTITIAL = (
    b"\n\n<html>\n<head>\n<meta HTTP-EQUIV=\"REFRESH\" content=\"2; url='/retrieve/"
    b"articleSelectSinglePerm'\">\n<title>Redirecting</title>\n</head>\n</html>\n"
)


class LooksLikeHtmlTests(unittest.TestCase):
    def test_detects_doctype(self):
        self.assertTrue(document_utils.looks_like_html(HTML_ERROR))

    def test_detects_interstitial_with_leading_blank_lines(self):
        self.assertTrue(document_utils.looks_like_html(INTERSTITIAL))

    def test_pdf_is_not_html(self):
        self.assertFalse(document_utils.looks_like_html(MINIMAL_PDF))

    def test_epub_is_not_html(self):
        self.assertFalse(document_utils.looks_like_html(EPUB_BYTES))


class ContentIsValidDownloadTests(unittest.TestCase):
    def test_pdf_path_requires_pdf_magic(self):
        self.assertTrue(document_utils.content_is_valid_download(MINIMAL_PDF, "a/b.pdf"))
        self.assertFalse(document_utils.content_is_valid_download(HTML_ERROR, "a/b.pdf"))
        # An EPUB payload is not acceptable when a PDF was requested.
        self.assertFalse(document_utils.content_is_valid_download(EPUB_BYTES, "a/b.pdf"))

    def test_non_pdf_path_accepts_other_formats(self):
        # libgen and Z-Library legitimately return epub/djvu, so those must pass.
        self.assertTrue(document_utils.content_is_valid_download(EPUB_BYTES, "a/b.epub"))
        self.assertTrue(document_utils.content_is_valid_download(b"AT&TFORM....", "a/b.djvu"))

    def test_non_pdf_path_still_rejects_html_and_empty(self):
        self.assertFalse(document_utils.content_is_valid_download(HTML_ERROR, "a/b.epub"))
        self.assertFalse(document_utils.content_is_valid_download(b"", "a/b.epub"))


class DiscardInvalidDownloadTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

    def _write(self, name, data):
        path = os.path.join(self._tmp.name, name)
        with open(path, "wb") as f:
            f.write(data)
        return path

    def test_keeps_valid_pdf(self):
        path = self._write("good.pdf", MINIMAL_PDF)
        self.assertTrue(document_utils.discard_invalid_download(path))
        self.assertTrue(os.path.exists(path))

    def test_removes_html_saved_as_pdf(self):
        path = self._write("bad.pdf", INTERSTITIAL)
        self.assertFalse(document_utils.discard_invalid_download(path))
        self.assertFalse(os.path.exists(path))

    def test_keeps_valid_epub(self):
        path = self._write("good.epub", EPUB_BYTES)
        self.assertTrue(document_utils.discard_invalid_download(path))
        self.assertTrue(os.path.exists(path))

    def test_removes_empty_file(self):
        path = self._write("empty.pdf", b"")
        self.assertFalse(document_utils.discard_invalid_download(path))
        self.assertFalse(os.path.exists(path))

    def test_missing_file_is_invalid(self):
        self.assertFalse(
            document_utils.discard_invalid_download(os.path.join(self._tmp.name, "nope.pdf"))
        )


if __name__ == "__main__":
    unittest.main()
