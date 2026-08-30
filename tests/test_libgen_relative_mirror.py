import importlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import requests

LIBGEN_PAGE = '<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN"><title>Library Genesis</title>'

# A record whose mirrors are the raw hrefs LibGen puts in ``json.php``. Only the
# ads.php one is absolute-ish; the torrent link is relative to the mirror root.
RECORD = {
    "91167877": {
        "title": "A paper",
        "files": {
            "1": {
                "extension": "pdf",
                "mirrors": {
                    "100k Torrent": "/torrents/scimag/sm_84900000-84999999.torrent",
                    "Libgen": "/ads.php?md5=a5efa9791b836507541d615ed3f069e9",
                },
            }
        },
    }
}


class NotADocument:
    """Enough of a streamed ``requests`` response to drive the download loop."""

    status_code = 200

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def raise_for_status(self):
        return None

    def iter_content(self, chunk_size=8192):
        yield b"not a pdf"


class RecordingGet:
    def __init__(self):
        self.urls = []

    def __call__(self, url, **kwargs):
        self.urls.append(url)
        return NotADocument()


def load_libgen():
    """Import ``libgen`` without letting its import-time mirror probe reach the
    network."""

    def offline(url, **kwargs):
        class Page:
            status_code = 200
            text = LIBGEN_PAGE

        return Page()

    sys.modules.pop("getscipapers_hoanganhduc.libgen", None)
    with patch.object(requests, "get", offline):
        return importlib.import_module("getscipapers_hoanganhduc.libgen")


class RelativeMirrorTests(unittest.TestCase):
    """Mirror hrefs come straight out of the record and some are relative, so
    handing them to ``requests`` unchanged raises ``MissingSchema`` and burns
    the mirror."""

    def test_a_relative_mirror_is_resolved_against_the_active_domain(self):
        libgen = load_libgen()
        stub = RecordingGet()
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(libgen, "search_libgen_by_doi", return_value=RECORD), \
                 patch.object(requests, "get", stub):
                libgen.download_libgen_paper_by_doi(
                    "10.1016/j.jallcom.2020.157991",
                    dest_folder=tmp,
                    print_result=False,
                )
        self.assertTrue(stub.urls)
        for url in stub.urls:
            self.assertTrue(
                url.startswith("https://"),
                f"mirror URL was passed through unresolved: {url!r}",
            )
        self.assertIn(
            f"https://{libgen.LIBGEN_DOMAIN}/torrents/scimag/sm_84900000-84999999.torrent",
            stub.urls,
        )


if __name__ == "__main__":
    unittest.main()
