"""Tests for how scinet resolves login credentials before a run."""

import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from getscipapers_hoanganhduc import scinet


class Args:
    """Stand-in for the parsed command line."""

    def __init__(self, credentials=None):
        self.credentials = credentials


class HandleCredentialsTests(unittest.TestCase):
    """``handle_credentials`` should reach the saved file before the prompt."""

    def setUp(self):
        self._username = scinet.USERNAME
        self._password = scinet.PASSWORD
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.addCleanup(self._restore)
        scinet.USERNAME = ""
        scinet.PASSWORD = ""
        self.cred_file = os.path.join(self._tmp.name, "credentials.json")
        self.cache_file = os.path.join(self._tmp.name, "scinet_cache.pkl")

    def _restore(self):
        scinet.USERNAME = self._username
        scinet.PASSWORD = self._password

    def _write_credentials(self):
        with open(self.cred_file, "w", encoding="utf-8") as handle:
            json.dump(
                {"scinet_username": "saved_user", "scinet_password": "saved_pass"},
                handle,
            )

    def test_saved_credentials_are_used_without_the_flag(self):
        """A saved file answers for both fields, so nothing is asked."""
        self._write_credentials()
        with mock.patch.object(scinet, "CREDENTIAL_FILE", self.cred_file), \
             mock.patch.object(scinet, "CACHE_FILE", self.cache_file), \
             mock.patch.object(scinet, "get_username_with_timeout") as ask_user, \
             mock.patch.object(scinet, "get_password_with_timeout") as ask_pass:
            scinet.handle_credentials(Args(), None)
        ask_user.assert_not_called()
        ask_pass.assert_not_called()
        self.assertEqual(scinet.USERNAME, "saved_user")
        self.assertEqual(scinet.PASSWORD, "saved_pass")

    def test_cached_username_still_gets_a_password(self):
        """A cached username names the account but does not log it in."""
        self._write_credentials()
        with mock.patch.object(scinet, "CREDENTIAL_FILE", self.cred_file), \
             mock.patch.object(scinet, "CACHE_FILE", self.cache_file), \
             mock.patch.object(scinet, "get_password_with_timeout") as ask_pass:
            scinet.USERNAME = "cached_user"
            scinet.handle_credentials(Args(), None)
        ask_pass.assert_not_called()
        self.assertEqual(scinet.PASSWORD, "saved_pass")

    def test_missing_file_falls_back_to_the_prompt(self):
        """With nothing saved the prompt is still the last resort."""
        with mock.patch.object(scinet, "CREDENTIAL_FILE", self.cred_file), \
             mock.patch.object(scinet, "CACHE_FILE", self.cache_file), \
             mock.patch.object(
                 scinet, "get_username_with_timeout", return_value="typed_user"
             ) as ask_user:
            scinet.handle_credentials(Args(), None)
        ask_user.assert_called_once()
        self.assertEqual(scinet.USERNAME, "typed_user")

    def test_explicit_flag_still_wins(self):
        """``--credentials`` names the file to read, overriding the default."""
        self._write_credentials()
        other = os.path.join(self._tmp.name, "other.json")
        with open(other, "w", encoding="utf-8") as handle:
            json.dump(
                {"scinet_username": "flag_user", "scinet_password": "flag_pass"},
                handle,
            )
        with mock.patch.object(scinet, "CREDENTIAL_FILE", self.cred_file), \
             mock.patch.object(scinet, "CACHE_FILE", self.cache_file):
            scinet.handle_credentials(Args(credentials=other), None)
        self.assertEqual(scinet.USERNAME, "flag_user")
        self.assertEqual(scinet.PASSWORD, "flag_pass")


class PerformLoginTests(unittest.TestCase):
    """``perform_login`` should cope with a session the profile kept alive."""

    def test_live_session_is_accepted_without_a_form(self):
        """The browser profile outlives the cache, so the form may be absent."""
        driver = mock.Mock()
        with mock.patch.object(scinet, "is_logged_in", return_value=True), \
             mock.patch.object(scinet, "save_login_cache") as save_cache:
            self.assertTrue(scinet.perform_login(driver, "user", "pass"))
        driver.get.assert_not_called()
        save_cache.assert_called_once_with(driver, "user")

    def test_logged_out_session_still_opens_the_login_page(self):
        """Without a live session the usual form flow is left untouched."""
        driver = mock.Mock()
        with mock.patch.object(scinet, "is_logged_in", return_value=False), \
             mock.patch.object(
                 scinet, "WebDriverWait", side_effect=RuntimeError("stop here")
             ):
            self.assertFalse(scinet.perform_login(driver, "user", "pass"))
        driver.get.assert_called_once_with("https://sci-net.xyz")


if __name__ == "__main__":
    unittest.main()
