import asyncio
import unittest
from unittest.mock import patch

import requests

from getscipapers_hoanganhduc import getpapers
from tests.test_libgen_user_agent import RecordingGet, load_libgen

DOI = "10.1016/j.jallcom.2020.157991"
MD5 = "a5efa9791b836507541d615ed3f069e9"

RECORD = {
    "91167877": {
        "title": "FeSiBCrC amorphous magnetic powder",
        "doi": DOI,
        "files": {
            MD5: {"md5": MD5, "extension": "pdf", "size": "48 MB (50509261 B)"},
        },
    }
}


class FindMd5Tests(unittest.TestCase):
    """LibGen indexes the same files Anna's Archive serves, so it turns a cold
    DOI into the md5 the quota-free route needs without the browser check."""

    def setUp(self):
        self.libgen = load_libgen(RecordingGet({}))

    def find(self, record):
        with patch.object(self.libgen, "search_libgen_by_doi", return_value=record):
            return self.libgen.find_md5_by_doi(DOI)

    def test_the_pdf_md5_is_returned(self):
        self.assertEqual(self.find(RECORD), MD5)

    def test_no_record_yields_nothing(self):
        self.assertIsNone(self.find({}))

    def test_a_record_without_files_yields_nothing(self):
        self.assertIsNone(self.find({"91167877": {"doi": DOI}}))

    def test_a_pdf_is_preferred_over_another_format(self):
        record = {
            "1": {
                "files": {
                    "b" * 32: {"md5": "b" * 32, "extension": "djvu"},
                    MD5: {"md5": MD5, "extension": "pdf"},
                }
            }
        }
        self.assertEqual(self.find(record), MD5)

    def test_a_non_pdf_is_still_returned_when_it_is_all_there_is(self):
        record = {"1": {"files": {"c" * 32: {"md5": "c" * 32, "extension": "djvu"}}}}
        self.assertEqual(self.find(record), "c" * 32)


class AnnaUsesLibgenForMd5Tests(unittest.TestCase):
    """Without an md5, Anna's routes R1 and R2 cannot run at all, which is what
    forces the slow browser route on a cold DOI."""

    def run_routes(self, cached=None, libgen_md5=MD5):
        seen = {}

        def fake_download_paper(doi, **kwargs):
            seen.setdefault("md5", kwargs.get("md5"))
            seen.setdefault("routes", []).append(kwargs.get("routes"))
            return None

        async def fake_scrape(doi, folder):
            return False

        with patch.object(getpapers.anna, "download_paper", fake_download_paper), \
                patch.object(getpapers.anna, "lookup_md5", lambda doi: cached), \
                patch.object(getpapers.anna, "remember_md5", lambda doi, md5: seen.update(remembered=md5)), \
                patch.object(getpapers, "download_from_anna_archive", fake_scrape), \
                patch("getscipapers_hoanganhduc.libgen.find_md5_by_doi", lambda doi: libgen_md5):
            asyncio.run(getpapers.download_from_anna_archive_all_routes(DOI, "/tmp"))
        return seen

    def test_a_cold_doi_is_resolved_through_libgen(self):
        seen = self.run_routes()
        self.assertEqual(seen["md5"], MD5)
        self.assertEqual(seen.get("remembered"), MD5)

    def test_a_cached_md5_is_used_without_asking_libgen(self):
        def explode(doi):
            raise AssertionError("LibGen must not be queried when the md5 is cached")

        with patch("getscipapers_hoanganhduc.libgen.find_md5_by_doi", explode):
            seen = self.run_routes(cached=MD5)
        self.assertEqual(seen["md5"], MD5)

    def test_a_libgen_miss_still_falls_through_to_the_other_routes(self):
        seen = self.run_routes(libgen_md5=None)
        self.assertIsNone(seen["md5"])
        self.assertIn(("R4", "R5"), seen["routes"])


if __name__ == "__main__":
    unittest.main()
