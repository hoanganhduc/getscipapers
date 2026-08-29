import re
import unittest

from getscipapers_hoanganhduc import getpapers


class ScihubDirectPdfUrlTests(unittest.TestCase):
    """Sci-Hub's PDF host is case-sensitive: an uppercase DOI returns 404."""

    def test_builds_url_from_doi(self):
        self.assertEqual(
            getpapers.scihub_direct_pdf_url("10.1086/524017"),
            "https://sci.bban.top/pdf/10.1086/524017.pdf",
        )

    def test_lowercases_doi(self):
        self.assertEqual(
            getpapers.scihub_direct_pdf_url("10.2105/AJPH.2015.302779"),
            "https://sci.bban.top/pdf/10.2105/ajph.2015.302779.pdf",
        )

    def test_strips_whitespace(self):
        self.assertEqual(
            getpapers.scihub_direct_pdf_url("  10.1086/524017\n"),
            "https://sci.bban.top/pdf/10.1086/524017.pdf",
        )

    def test_strips_doi_url_prefix(self):
        for prefix in ("https://doi.org/", "http://dx.doi.org/", "doi:"):
            with self.subTest(prefix=prefix):
                self.assertEqual(
                    getpapers.scihub_direct_pdf_url(f"{prefix}10.1086/524017"),
                    "https://sci.bban.top/pdf/10.1086/524017.pdf",
                )


class ScihubRobotCheckTests(unittest.TestCase):
    ROBOT = (
        b"<!DOCTYPE html><html><head><title translate = \"en:title\">"
        b"Sci-Hub: are you are robot?</title>"
        b"<script async defer src = \"/scripts/altcha.min.js\"></script></head></html>"
    )
    ARTICLE = (
        b"<html><head><title>Sci-Hub. Extensively Drug-Resistant Tuberculosis</title>"
        b"</head><body><iframe src=\"https://sci.bban.top/pdf/10.1086/524017.pdf#view=FitH\""
        b" id=\"pdf\"></iframe></body></html>"
    )
    # Every mirror page loads the Altcha widget, so its presence alone says
    # nothing.  Only the challenge page asks the "are you a robot?" question.
    ARTICLE_WITH_WIDGET = (
        b"<html><head><title>Sci-Hub. Marital violence in Azerbaijan</title>"
        b"<script async defer src = \"/scripts/altcha.min.js\" type=\"module\"></script>"
        b"</head><body>"
        b"<div class = \"robot\" translate = \"ru:robot\">\xd0\xaf \xd0\xbd\xd0\xb5 \xd1\x80\xd0\xbe\xd0\xb1\xd0\xbe\xd1\x82</div>"
        b"<altcha-widget challengeurl = \"/captcha/challenge\" hidelogo></altcha-widget>"
        b"<a href=\"#\" onclick=\"location.href='/storage/zero/5523/"
        b"f643a371a8a5fc0b0264ce7ce2111f27/ismayilova2015.pdf?download=true'\">save</a>"
        b"</body></html>"
    )
    # The real gate: a numbered challenge plus the "\xd0\x92\xd1\x8b \xd1\x80\xd0\xbe\xd0\xb1\xd0\xbe\xd1\x82?" prompt.
    GATE = (
        b"<html><head><script async defer src = \"/scripts/altcha.min.js\""
        b" type=\"module\"></script></head><body>"
        b"<div class = \"ask\" translate = \"ru:isrobot\">\xd0\x92\xd1\x8b \xd1\x80\xd0\xbe\xd0\xb1\xd0\xbe\xd1\x82?</div>"
        b"<altcha-widget challengeurl = \"/captcha/challenge/52207953\" hidelogo></altcha-widget>"
        b"<img src = \"/pictures/robot.svg\"></body></html>"
    )

    def test_detects_robot_check(self):
        self.assertTrue(getpapers.is_scihub_robot_check(self.ROBOT.decode()))

    def test_article_page_is_not_robot_check(self):
        self.assertFalse(getpapers.is_scihub_robot_check(self.ARTICLE.decode()))

    def test_article_carrying_altcha_widget_is_not_robot_check(self):
        self.assertFalse(
            getpapers.is_scihub_robot_check(self.ARTICLE_WITH_WIDGET.decode())
        )

    def test_detects_numbered_challenge_gate(self):
        self.assertTrue(getpapers.is_scihub_robot_check(self.GATE.decode()))


class ScihubPdfLinkExtractionTests(unittest.TestCase):
    def test_finds_bban_iframe_link(self):
        html = (
            '<iframe src="https://sci.bban.top/pdf/10.1086/524017.pdf#view=FitH" id="pdf">'
        )
        self.assertEqual(
            getpapers.extract_scihub_pdf_url(html, "https://sci-hub.ee"),
            "https://sci.bban.top/pdf/10.1086/524017.pdf",
        )

    def test_finds_storage_link(self):
        html = (
            "<a href=\"#\" onclick=\"location.href='/storage/zero/3906/"
            "012cd4781d80a0da8c6195de6fdaa937/jeon2008.pdf?download=true'\">save</a>"
        )
        self.assertEqual(
            getpapers.extract_scihub_pdf_url(html, "https://sci-hub.ru"),
            "https://sci-hub.ru/storage/zero/3906/012cd4781d80a0da8c6195de6fdaa937/jeon2008.pdf",
        )

    def test_unescapes_backslash_escaped_javascript_url(self):
        html = (
            "<a href=\"#\" onclick=\"location.href='https:\\/\\/sci.bban.top\\/pdf\\/"
            "10.1086\\/524017.pdf?download=true'\">save</a>"
        )
        self.assertEqual(
            getpapers.extract_scihub_pdf_url(html, "https://sci-hub.ee"),
            "https://sci.bban.top/pdf/10.1086/524017.pdf",
        )

    def test_protocol_relative_link_gets_scheme(self):
        html = '<iframe src="//sci.bban.top/pdf/10.1086/524017.pdf"></iframe>'
        self.assertEqual(
            getpapers.extract_scihub_pdf_url(html, "https://sci-hub.ee"),
            "https://sci.bban.top/pdf/10.1086/524017.pdf",
        )

    def test_returns_none_when_no_pdf_link(self):
        html = "<html><body><iframe src='//ads.example/x'></iframe></body></html>"
        self.assertIsNone(getpapers.extract_scihub_pdf_url(html, "https://sci-hub.vn"))


class ScihubStorageUrlTests(unittest.TestCase):
    """Several mirrors serve /storage/ files even when they cannot resolve a DOI."""

    PATH = (
        "/storage/zero/5523/f643a371a8a5fc0b0264ce7ce2111f27/ismayilova2015.pdf"
    )

    def test_official_host_is_tried_first(self):
        urls = getpapers.scihub_storage_urls("https://sci-hub.ru" + self.PATH)
        self.assertEqual(urls[0], "https://sci-hub.vn" + self.PATH)

    def test_offers_every_known_storage_host(self):
        urls = getpapers.scihub_storage_urls("https://sci-hub.ru" + self.PATH)
        self.assertEqual(
            urls, [host + self.PATH for host in getpapers.SCI_HUB_STORAGE_HOSTS]
        )

    def test_keeps_bucket_because_unknown_buckets_serve_an_ad_page(self):
        for bucket in ("zero", "2024", "dace", "moscow"):
            with self.subTest(bucket=bucket):
                path = (
                    f"/storage/{bucket}/3906/"
                    "012cd4781d80a0da8c6195de6fdaa937/jeon2008.pdf"
                )
                urls = getpapers.scihub_storage_urls("https://sci-hub.red" + path)
                self.assertTrue(all(u.endswith(path) for u in urls))

    def test_returns_nothing_for_non_storage_url(self):
        self.assertEqual(
            getpapers.scihub_storage_urls("https://sci.bban.top/pdf/10.1086/524017.pdf"),
            [],
        )


class ScihubMirrorListTests(unittest.TestCase):
    """Mirrors verified to serve article pages must stay ahead of stale ones."""

    VERIFIED = (
        "https://sci-hub.ee",
        "https://sci-hub.al",
        "https://sci-hub.mk",
        "https://sci-hub.vg",
    )

    def test_independent_scihub_instances_are_both_asked(self):
        """sci-hub.su is a separate server from sci-hub.ru, so it gates apart."""
        domains = self._domains()
        for mirror in ("https://sci-hub.ru", "https://sci-hub.su"):
            with self.subTest(mirror=mirror):
                self.assertIn(mirror, domains)

    def _domains(self):
        import inspect

        source = inspect.getsource(getpapers.download_from_scihub)
        start = source.index("sci_hub_domains = [")
        end = source.index("]", start)
        return re.findall(r'"(https://[^"]+)"', source[start:end])

    def test_verified_mirrors_present(self):
        domains = self._domains()
        for mirror in self.VERIFIED:
            with self.subTest(mirror=mirror):
                self.assertIn(mirror, domains)

    def test_verified_mirrors_come_first(self):
        domains = self._domains()
        self.assertEqual(set(domains[: len(self.VERIFIED)]), set(self.VERIFIED))

    def test_official_host_is_not_asked_to_resolve_dois(self):
        """Every path under sci-hub.vn answers with the same advertisement."""
        self.assertNotIn(getpapers.SCI_HUB_OFFICIAL_HOST, self._domains())

    def test_storage_files_are_fetched_from_the_official_host_first(self):
        import inspect

        source = inspect.getsource(getpapers.download_from_scihub)
        self.assertIn("scihub_storage_urls(pdf_url)", source)

    def test_bot_challenge_is_retried(self):
        import inspect

        source = inspect.getsource(getpapers.download_from_scihub)
        self.assertIn("range(SCI_HUB_GATE_RETRIES)", source)


if __name__ == "__main__":
    unittest.main()
