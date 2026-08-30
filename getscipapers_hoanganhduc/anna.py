"""Account-aware document retrieval from Anna's Archive.

Anna's Archive deliberately triggers a DDoS-Guard recheck on every request to
its ``/search``, ``/md5/``, ``/doi/``, ``/scidb/`` and ``/slow_download/``
pages, so a plain HTTP client can never read them. This module reaches the same
documents through the routes that are *not* challenge-gated, and falls back to
a real browser when no account is configured:

``R1``
    ``/db/aarecord_elasticsearch/md5:<md5>.json`` read with a member cookie,
    then one of the IPFS gateways it lists. Needs an md5, but consumes no
    download quota, so it is tried first.
``R2``
    ``/dyn/api/fast_download.json`` keyed by the account secret. Needs an md5
    and spends one of the daily fast downloads.
``R4``
    ``/scidb/<doi>`` fetched with the account cookie, which bypasses the
    challenge for paid members. This is the only fast DOI-addressed route, but
    Anna's Archive restricts the perk to "normal browser use", so it stays
    behind an explicit opt-in.
``R5``
    Chromium with a software WebGL stack, left to solve the challenge on its
    own. Needs no credentials and takes about 30-45 seconds.

Routes ``R1`` and ``R2`` are addressed by md5 rather than by DOI, so a DOI has
to be resolved first. Only ``R4``, ``R5``, an explicit ``--md5`` or the local
md5 cache can do that; there is no working external oracle. A membership alone
therefore does not make a cold DOI resolvable unless ``--scidb`` is armed.

The login cookie, the "key routes are disabled" flag and the browser attempt
counter are module globals, so they are shared by every download in a process.
That is safe today because callers download one DOI at a time.
"""

import argparse
import base64
import json
import os
import platform
import re
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import datetime
from getpass import getpass
from urllib.parse import unquote, urlparse

import requests

from . import proxy_config
from .document_utils import save_document_if_valid

VERBOSE = False
ACTIVE_PROXY = proxy_config.ProxySettings()
PROXY_RETRY_STATUSES = {403, 407, 408, 429, 500, 502, 503, 504}

DOMAINS = (
    "https://annas-archive.gl",
    "https://annas-archive.pk",
    "https://annas-archive.gd",
)

# Cookie that /account/ sets on a successful login, and the environment
# variable that supplies the secret key without touching disk.
ACCOUNT_COOKIE_NAME = "aa_account_id2"
SECRET_KEY_ENV = "GETSCIPAPERS_ANNA_SECRET_KEY"

# Title of the DDoS-Guard interstitial. The solved record page still mentions
# "ddos-guard" in its own scripts, so the challenge must never be detected by
# searching the body for that string.
CHALLENGE_TITLE = "DDoS-Guard"

REQUEST_TIMEOUT = 30
DOWNLOAD_TIMEOUT = 120
# Observed solve times are 33-45s; the cap leaves room for a slow network.
BROWSER_TIMEOUT = 120
# A --doi-file run must not be able to spend hours in Chromium.
MAX_BROWSER_ATTEMPTS = 3

DEFAULT_ROUTES = ("R1", "R2", "R4", "R5")

# Software WebGL. A GPU-less host otherwise blocklists WebGL entirely and the
# automatic check degrades to hCaptcha.
SWIFTSHADER_FLAGS = (
    "--use-gl=angle",
    "--use-angle=swiftshader",
    "--enable-unsafe-swiftshader",
    "--ignore-gpu-blocklist",
    "--enable-gpu-rasterization",
)

# Process-wide session state.
_SESSION_COOKIE = None
_KEY_ROUTES_DISABLED = False
_QUOTA_EXHAUSTED = False
_BROWSER_ATTEMPTS = 0


def debug_print(message):
    """Print debug message only if verbose mode is enabled"""
    if VERBOSE:
        print(f"Debug: {message}")


def _redact(text):
    """Hide the account secret in anything that may be printed or logged."""
    if not text:
        return text
    return re.sub(r"(key=)[^&\s]+", r"\1<redacted>", str(text))


def _requests_request(method: str, url: str, **kwargs):
    """Run a requests call direct first, then retry with proxy if direct fails."""

    proxies = ACTIVE_PROXY.requests_proxies()
    direct_kwargs = kwargs.copy()
    direct_kwargs.pop("proxies", None)

    try:
        with requests.Session() as session:
            session.trust_env = False
            response = session.request(method, url, **direct_kwargs)
            if proxies and response.status_code in PROXY_RETRY_STATUSES:
                debug_print(
                    f"Direct {method.upper()} request to {_redact(url)} returned "
                    f"HTTP {response.status_code}; retrying with configured proxy."
                )
                response.close()
                proxy_kwargs = direct_kwargs.copy()
                proxy_kwargs["proxies"] = proxies
                return session.request(method, url, **proxy_kwargs)
            return response
    except requests.exceptions.RequestException as exc:
        if not proxies:
            raise
        debug_print(
            f"Direct {method.upper()} request to {_redact(url)} failed: {exc}; "
            "retrying with configured proxy."
        )
        proxy_kwargs = direct_kwargs.copy()
        proxy_kwargs["proxies"] = proxies
        with requests.Session() as session:
            session.trust_env = False
            return session.request(method, url, **proxy_kwargs)


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

def get_cache_directory():
    """Get the appropriate cache directory for the current platform, using getscipapers/anna subfolder"""
    system = platform.system()
    subfolder = os.path.join('getscipapers', 'anna')

    if system == "Windows":
        appdata = os.environ.get('APPDATA')
        if appdata:
            cache_dir = os.path.join(appdata, subfolder)
        else:
            cache_dir = os.path.join(os.path.expanduser('~'), 'AppData', 'Roaming', subfolder)
    elif system == "Darwin":
        cache_dir = os.path.join(os.path.expanduser('~'), 'Library', 'Caches', subfolder)
    else:
        cache_dir = os.path.join(os.path.expanduser('~'), '.config', subfolder)
    os.makedirs(cache_dir, exist_ok=True)
    return cache_dir


def get_credentials_directory():
    """Get the directory holding the saved account secret."""
    return get_cache_directory()


def get_download_directory():
    """Get the default download directory for the current platform, using getscipapers/anna subfolder"""
    system = platform.system()
    subfolder = os.path.join('getscipapers', 'anna')

    if system == "Windows":
        userprofile = os.environ.get('USERPROFILE')
        base = userprofile if userprofile else os.path.expanduser('~')
        download_dir = os.path.join(base, 'Downloads', subfolder)
    else:
        download_dir = os.path.join(os.path.expanduser('~'), 'Downloads', subfolder)
    os.makedirs(download_dir, exist_ok=True)
    return download_dir


def default_credentials_file():
    return os.path.join(get_credentials_directory(), "credentials.json")


def md5_cache_file():
    return os.path.join(get_cache_directory(), "md5_cache.json")


# ---------------------------------------------------------------------------
# Credentials
# ---------------------------------------------------------------------------

def load_credentials_from_file(filepath):
    """Read the account secret from a JSON credentials file.

    Expected format::

        {"anna_secret_key": "your_secret_key"}

    Returns the secret key, or None when the file is missing or unusable.
    """
    if not filepath or not os.path.exists(filepath):
        debug_print(f"Credentials file not found: {filepath}")
        return None

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            credentials = json.load(f)
    except json.JSONDecodeError as e:
        debug_print(f"Invalid JSON in credentials file: {e}")
        return None
    except Exception as e:
        debug_print(f"Error reading credentials file: {e}")
        return None

    secret_key = credentials.get('anna_secret_key')
    if not secret_key:
        debug_print("Invalid credentials file: missing anna_secret_key")
        return None

    debug_print(f"Loaded Anna's Archive secret key from {filepath}")

    # Mirror a non-default credentials file into the default location so later
    # runs work without repeating --credentials.
    default_file = default_credentials_file()
    if os.path.abspath(filepath) != os.path.abspath(default_file):
        if _read_secret_key(default_file) != secret_key:
            save_credentials_to_file(secret_key, default_file)

    return secret_key


def _read_secret_key(filepath):
    """Read the secret key from a file without mirroring it anywhere."""
    if not filepath or not os.path.exists(filepath):
        return None
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f).get('anna_secret_key')
    except Exception:
        return None


def save_credentials_to_file(secret_key, filepath=None):
    """Write the account secret to a credentials file with owner-only permissions."""
    filepath = filepath or default_credentials_file()
    try:
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump({"anna_secret_key": secret_key}, f, ensure_ascii=False, indent=2)
        if os.name == 'posix':
            os.chmod(filepath, stat.S_IRUSR | stat.S_IWUSR)
        debug_print(f"Credentials saved to {filepath}")
        return True
    except Exception as e:
        debug_print(f"Failed to save credentials to {filepath}: {e}")
        return False


def resolve_secret_key(explicit=None, credentials_file=None, interactive=False):
    """Find the account secret, preferring the least persistent source.

    The order is explicit argument, environment variable, ``--credentials``
    file, default credentials file, and finally an interactive prompt. Callers
    running a batch download pass ``interactive=False`` so a missing key can
    never block on a prompt.
    """
    if explicit:
        if explicit == "-":
            explicit = sys.stdin.readline().strip()
        if explicit:
            debug_print("Using Anna's Archive secret key from the command line")
            return explicit

    from_env = os.environ.get(SECRET_KEY_ENV)
    if from_env:
        debug_print(f"Using Anna's Archive secret key from ${SECRET_KEY_ENV}")
        return from_env.strip()

    if credentials_file:
        key = load_credentials_from_file(credentials_file)
        if key:
            return key

    key = _read_secret_key(default_credentials_file())
    if key:
        debug_print("Using Anna's Archive secret key from the default credentials file")
        return key

    if interactive and sys.stdin.isatty():
        key = getpass("Anna's Archive secret key: ").strip()
        if key:
            save_credentials_to_file(key)
            return key

    debug_print("No Anna's Archive secret key configured")
    return None


# ---------------------------------------------------------------------------
# Account session
# ---------------------------------------------------------------------------

def login(secret_key, domain):
    """Exchange the account secret for a session cookie.

    Anna's Archive answers a bad key with HTTP 200 as well, so success is
    decided by whether the account cookie came back, never by the status code.
    """
    url = f"{domain}/account/"
    try:
        resp = _requests_request(
            "post", url, data={"key": secret_key},
            allow_redirects=False, timeout=REQUEST_TIMEOUT,
        )
    except Exception as e:
        debug_print(f"Login request to {domain} failed: {e}")
        return None

    cookie = resp.cookies.get(ACCOUNT_COOKIE_NAME)
    if not cookie:
        debug_print(f"Login at {domain} did not return an account cookie (HTTP {resp.status_code})")
        return None

    expiry = account_cookie_expiry(cookie)
    debug_print(f"Logged in at {domain}" + (f", cookie valid until {expiry}" if expiry else ""))
    return cookie


def account_cookie_expiry(cookie):
    """Return the expiry of an account cookie, or None when it cannot be read.

    Anna's Archive strips the constant JWT header before setting the cookie, so
    the value is ``payload.signature`` and the payload is the *first* segment.
    The signature is never verified here; this only reports when a stored
    cookie has gone stale.
    """
    try:
        payload = cookie.split(".")[0]
        padded = payload + "=" * (-len(payload) % 4)
        data = json.loads(base64.urlsafe_b64decode(padded))
        exp = data.get("exp")
        if not exp:
            return None
        return datetime.fromtimestamp(float(exp))
    except Exception:
        return None


def is_logged_in(cookie, domain):
    """Check a session cookie against the ungated /dyn/up/ probe."""
    try:
        resp = _requests_request(
            "get", f"{domain}/dyn/up/",
            cookies={ACCOUNT_COOKIE_NAME: cookie}, timeout=REQUEST_TIMEOUT,
        )
        return bool(resp.json().get("aa_logged_in"))
    except Exception as e:
        debug_print(f"Login probe at {domain} failed: {e}")
        return False


def select_active_domain():
    """Pick a reachable mirror by probing /dyn/up/.

    The homepage is challenge-gated, so probing it would make every mirror look
    dead. ``/dyn/up/`` is not gated and answers with a small JSON body.
    """
    for domain in DOMAINS:
        try:
            resp = _requests_request("get", f"{domain}/dyn/up/", timeout=REQUEST_TIMEOUT)
            if resp.status_code == 200:
                debug_print(f"Using Anna's Archive domain: {domain}")
                return domain
            debug_print(f"{domain} answered HTTP {resp.status_code} on /dyn/up/")
        except Exception as e:
            debug_print(f"{domain} unreachable: {e}")
    return None


def _session_cookie(secret_key, domain):
    """Return the cached session cookie, logging in once per process."""
    global _SESSION_COOKIE
    if _SESSION_COOKIE:
        return _SESSION_COOKIE
    if not secret_key:
        return None
    _SESSION_COOKIE = login(secret_key, domain)
    return _SESSION_COOKIE


# ---------------------------------------------------------------------------
# md5 cache
# ---------------------------------------------------------------------------

def load_md5_cache():
    """Load the DOI to md5 map, discarding it if it has been corrupted."""
    path = md5_cache_file()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if not isinstance(data, dict) or not isinstance(data.get("entries"), dict):
            raise ValueError("unexpected cache layout")
        return data["entries"]
    except Exception as e:
        debug_print(f"md5 cache unreadable ({e}); removing {path}")
        try:
            os.remove(path)
        except OSError:
            pass
        return {}


def _save_md5_cache(entries):
    path = md5_cache_file()
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump({"version": 1, "entries": entries}, f, indent=2)
        return True
    except Exception as e:
        debug_print(f"Failed to write md5 cache {path}: {e}")
        return False


def lookup_md5(doi):
    """Return the md5 previously resolved for a DOI, if any."""
    if not doi:
        return None
    entry = load_md5_cache().get(doi.lower())
    if isinstance(entry, dict):
        return entry.get("md5")
    return None


def remember_md5(doi, md5):
    """Record a DOI to md5 mapping so later downloads can skip resolution."""
    if not doi or not md5:
        return False
    entries = load_md5_cache()
    entries[doi.lower()] = {"md5": md5.lower(), "ts": time.time()}
    debug_print(f"Cached md5 {md5} for DOI {doi}")
    return _save_md5_cache(entries)


def forget_md5(doi):
    """Drop a cached mapping that the server no longer recognises."""
    if not doi:
        return False
    entries = load_md5_cache()
    if entries.pop(doi.lower(), None) is None:
        return False
    debug_print(f"Removed stale cached md5 for DOI {doi}")
    return _save_md5_cache(entries)


# ---------------------------------------------------------------------------
# R1: the member-readable record, downloaded over IPFS
# ---------------------------------------------------------------------------

def db_aarecord(md5, cookie, domain):
    """Fetch the Elasticsearch record for an md5 using a member cookie.

    This page is not challenge-gated and is guarded only by a membership check,
    so any paid tier can read it.
    """
    url = f"{domain}/db/aarecord_elasticsearch/md5:{md5}.json"
    try:
        resp = _requests_request(
            "get", url, cookies={ACCOUNT_COOKIE_NAME: cookie}, timeout=REQUEST_TIMEOUT,
        )
    except Exception as e:
        debug_print(f"Record lookup failed for {md5}: {e}")
        return None

    if resp.status_code != 200:
        debug_print(f"Record lookup for {md5} returned HTTP {resp.status_code}")
        return None
    try:
        record = resp.json()
    except ValueError:
        debug_print(f"Record lookup for {md5} did not return JSON")
        return None
    if isinstance(record, list):
        record = record[0] if record else None
    return record if isinstance(record, dict) else None


def _normalize_url_entry(entry):
    """Pull a URL out of one of the several shapes Anna's Archive uses."""
    if isinstance(entry, str):
        return entry if entry.startswith("http") else None
    if isinstance(entry, dict):
        for key in ("url", "href", "link"):
            value = entry.get(key)
            if isinstance(value, str) and value.startswith("http"):
                return value
        return None
    if isinstance(entry, (list, tuple)):
        for value in entry:
            if isinstance(value, str) and value.startswith("http"):
                return value
    return None


def record_download_urls(record):
    """List the direct URLs a stripped record still carries.

    ``strip_partner_urls_from_aarecord`` blanks only the partner URLs, so the
    IPFS gateways and any plain mirrors survive for members.
    """
    if not isinstance(record, dict):
        return []
    source = record.get("additional")
    if not isinstance(source, dict):
        source = record
    urls = []
    for field in ("ipfs_urls", "download_urls"):
        for entry in source.get(field) or []:
            url = _normalize_url_entry(entry)
            if url and url not in urls:
                urls.append(url)
    return urls


def download_via_ipfs(record, filepath):
    """Try each gateway the record lists until one serves a real document."""
    urls = record_download_urls(record)
    if not urls:
        debug_print("Record carried no usable download URLs")
        return False
    for url in urls:
        debug_print(f"Trying record download URL: {url}")
        if _download_to_file(url, filepath):
            print(f"Downloaded from Anna's Archive record (no quota used): {filepath}")
            return True
    return False


# ---------------------------------------------------------------------------
# R2: the keyed fast-download API
# ---------------------------------------------------------------------------

def fast_download_info(md5, secret_key, domain):
    """Ask the fast-download API for a direct URL.

    Returns a dict with a ``status`` the caller can branch on. A HTTP 200 that
    carries no ``download_url`` is a failure, so the status code alone is never
    trusted.
    """
    url = f"{domain}/dyn/api/fast_download.json"
    try:
        resp = _requests_request(
            "get", url, params={"md5": md5, "key": secret_key}, timeout=REQUEST_TIMEOUT,
        )
    except Exception as e:
        debug_print(f"Fast download request failed: {_redact(e)}")
        return {"status": "error"}

    code = resp.status_code
    if code == 400:
        return {"status": "bad_md5"}
    if code == 401:
        return {"status": "invalid_key"}
    if code == 403:
        return {"status": "not_member"}
    if code == 404:
        return {"status": "not_found"}
    if code == 429:
        return {"status": "quota"}
    if code >= 500:
        return {"status": "server_error"}
    if code != 200:
        debug_print(f"Fast download returned unexpected HTTP {code}")
        return {"status": "error"}

    try:
        payload = resp.json()
    except ValueError:
        debug_print("Fast download did not return JSON")
        return {"status": "error"}

    download_url = payload.get("download_url")
    if not download_url:
        debug_print("Fast download returned HTTP 200 without a download URL")
        return {"status": "error"}

    info = payload.get("account_fast_download_info") or {}
    return {
        "status": "ok",
        "download_url": download_url,
        "downloads_left": info.get("downloads_left"),
    }


def download_by_md5(md5, secret_key, domain, filepath, doi=None):
    """Run route R2 for one md5 and report what happened.

    Returns True on success. Failures update the process-wide flags so a batch
    run stops re-trying a key that has already been rejected or exhausted.
    """
    global _KEY_ROUTES_DISABLED, _QUOTA_EXHAUSTED

    info = fast_download_info(md5, secret_key, domain)
    if info["status"] == "server_error":
        debug_print("Fast download hit a server error; retrying once")
        info = fast_download_info(md5, secret_key, domain)

    status = info["status"]
    if status == "ok":
        left = info.get("downloads_left")
        if left is not None:
            print(f"Anna's Archive fast downloads left today: {left}")
        return _download_to_file(info["download_url"], filepath)
    if status == "invalid_key":
        print("❌ Anna's Archive rejected the account secret key; key-based routes disabled.")
        _KEY_ROUTES_DISABLED = True
    elif status == "not_member":
        print("❌ Anna's Archive reports no active membership; key-based routes disabled.")
        _KEY_ROUTES_DISABLED = True
    elif status == "quota":
        print("❌ Anna's Archive daily fast-download quota is exhausted.")
        _QUOTA_EXHAUSTED = True
    elif status == "not_found":
        debug_print(f"Anna's Archive does not know md5 {md5}")
        forget_md5(doi)
    elif status == "bad_md5":
        debug_print(f"Anna's Archive rejected md5 {md5} as malformed")
    return False


# ---------------------------------------------------------------------------
# R4: the member-bypassed SciDB page
# ---------------------------------------------------------------------------

_MD5_HREF_RE = re.compile(r'/md5/([a-fA-F0-9]{32})')
_IFRAME_SRC_RE = re.compile(r'<iframe[^>]+src=["\']([^"\']+)["\']', re.I)
_ANCHOR_HREF_RE = re.compile(r'<a[^>]+href=["\']([^"\']+)["\']', re.I)
_PDFJS_FILE_RE = re.compile(r'[?&]file=([^"\'&]+)')


def _absolutize(url, domain):
    if url.startswith("http"):
        return url
    if url.startswith("/"):
        return domain + url
    return f"{domain}/{url}"


def parse_scidb_page(html, domain):
    """Extract the md5 and a download URL from a SciDB page.

    Only structural signals are used. Link text is localised, so matching on
    the word "Download" fails for every non-English visitor, and for members
    the page often renders straight into the PDF viewer with no anchor at all.
    Returns None when neither piece of information is present.
    """
    if not html:
        return None

    md5 = None
    match = _MD5_HREF_RE.search(html)
    if match:
        md5 = match.group(1).lower()

    url = None

    # The viewer iframe is the most reliable signal: it carries the real file
    # URL in its file= parameter even when no download anchor is rendered.
    for src in _IFRAME_SRC_RE.findall(html):
        file_match = _PDFJS_FILE_RE.search(src)
        if file_match:
            candidate = unquote(file_match.group(1))
            if candidate:
                url = _absolutize(candidate, domain)
                break

    if not url:
        hrefs = _ANCHOR_HREF_RE.findall(html)
        for href in hrefs:
            lowered = href.lower()
            if md5 and md5 in lowered and ".pdf" in lowered:
                url = _absolutize(href, domain)
                break
        if not url:
            for href in hrefs:
                lowered = href.lower()
                if "/fast_download/" in lowered or "/slow_download/" in lowered:
                    url = _absolutize(href, domain)
                    break

    if not md5 and not url:
        return None
    return {"md5": md5, "url": url}


def scidb_lookup(doi, cookie, domain):
    """Read the SciDB page for a DOI using the member cookie.

    Paid members skip the browser check on this page, which is what makes the
    lookup possible at all without a browser.
    """
    url = f"{domain}/scidb/{doi}"
    try:
        resp = _requests_request(
            "get", url, cookies={ACCOUNT_COOKIE_NAME: cookie}, timeout=REQUEST_TIMEOUT,
        )
    except Exception as e:
        debug_print(f"SciDB lookup failed for {doi}: {e}")
        return None
    if resp.status_code != 200:
        debug_print(f"SciDB lookup for {doi} returned HTTP {resp.status_code}")
        return None
    return parse_scidb_page(resp.text, domain)


# ---------------------------------------------------------------------------
# R5: let a real browser solve the challenge
# ---------------------------------------------------------------------------

def _resolve_browser_tools():
    """Locate Chromium and chromedriver without importing Selenium eagerly."""
    try:
        from . import selenium_utils
    except ImportError as exc:
        return None, None, f"Selenium is not installed: {exc}"
    return selenium_utils._resolve_chrome_binary(), selenium_utils._resolve_chromedriver(), None


def browser_available():
    """Report whether route R5 can run, and why not when it cannot.

    A missing tool is a capability gap worth naming: the package-level importer
    swallows ImportError, so an unexplained failure here would look like the
    module had silently disappeared.
    """
    chromium, driver, error = _resolve_browser_tools()
    if error:
        return False, error
    if not chromium:
        return False, "Chromium/Chrome not found (set CHROME_BINARY or CHROMIUM_BINARY)"
    if not driver:
        return False, "chromedriver not found (set CHROMEDRIVER_PATH)"
    if platform.system() == "Linux" and not os.environ.get("DISPLAY"):
        if not shutil.which("xvfb-run"):
            return False, "no display available and xvfb-run not found (install xvfb)"
    return True, ""


def _solved(title):
    """Return True once a page title shows the challenge is behind us.

    Detection is by title because the solved record page still contains the
    string "ddos-guard" in its own scripts, so a substring search of the body
    reports every successful fetch as blocked. Chromium also reports the raw
    URL as the title while a page is still loading, and titles its own network
    error page with the bare host, which a dead proxy would otherwise turn into
    a false solve.
    """
    if not title:
        return False
    title = title.strip()
    if not title or title == CHALLENGE_TITLE:
        return False
    if title.startswith("http"):
        return False
    return title.lower() not in {urlparse(d).hostname for d in DOMAINS}


# The DevTools endpoint is on loopback. Build an opener that never consults the
# proxy environment, since ACTIVE_PROXY.apply_environment() sets http_proxy for
# the ordinary HTTP clients and urlopen would otherwise send this request to the
# proxy, where 127.0.0.1 means the proxy's own machine.
_LOOPBACK_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
_LAST_CDP_ERROR = None


def _cdp_targets(port):
    global _LAST_CDP_ERROR
    try:
        with _LOOPBACK_OPENER.open(f"http://127.0.0.1:{port}/json", timeout=5) as resp:
            return json.load(resp)
    except Exception as e:
        message = f"DevTools target list unavailable on port {port}: {e}"
        if message != _LAST_CDP_ERROR:
            debug_print(message)
            _LAST_CDP_ERROR = message
        return []


def _wait_for_solve(port, deadline, poll=3.0):
    """Poll the DevTools target list until the challenge page turns into content.

    Returns the last title seen, whether or not it counts as solved, so that a
    page which never loaded can be told apart from one that sat on the
    interstitial for the whole budget. Callers must test the result with
    ``_solved`` rather than against None.
    """
    last = None
    while time.time() < deadline:
        for target in _cdp_targets(port):
            if target.get("type") != "page" or "annas-archive" not in target.get("url", ""):
                continue
            title = target.get("title", "")
            if title != last:
                debug_print(f"Browser page title: {title!r}")
                last = title
            if _solved(title):
                return title
        time.sleep(poll)
    return last


def _read_devtools_port(profile, deadline):
    """Read back the port Chromium chose for --remote-debugging-port=0."""
    portfile = os.path.join(profile, "DevToolsActivePort")
    while time.time() < deadline:
        try:
            with open(portfile, "r", encoding="utf-8") as f:
                port = f.readline().strip()
            if port:
                return int(port)
        except (OSError, ValueError):
            pass
        time.sleep(0.5)
    return None


def _launch_browser(chromium, profile, url):
    """Start Chromium plainly, never through chromedriver.

    A chromedriver-launched browser is rejected by the challenge outright, and
    headless is detected regardless of how the user agent is spoofed, so the
    browser is started as an ordinary process on a real or virtual display and
    only attached to afterwards.
    """
    argv = []
    if platform.system() == "Linux" and not os.environ.get("DISPLAY"):
        argv += ["xvfb-run", "-a", "--server-args=-screen 0 1920x1080x24"]
    argv += [
        chromium,
        f"--user-data-dir={profile}",
        "--remote-debugging-port=0",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-dev-shm-usage",
        "--password-store=basic",
        "--window-size=1920,1080",
    ]
    argv += list(SWIFTSHADER_FLAGS)
    if _needs_no_sandbox():
        argv.append("--no-sandbox")
    if ACTIVE_PROXY.enabled and ACTIVE_PROXY.proxy_url:
        argv.append(f"--proxy-server={ACTIVE_PROXY.proxy_url}")
    argv.append(url)

    debug_print(f"Launching browser: {' '.join(argv)}")
    return subprocess.Popen(
        argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def _needs_no_sandbox():
    if os.path.exists("/.dockerenv"):
        return True
    return hasattr(os, "geteuid") and os.geteuid() == 0


def _wait_for_group_exit(group, deadline):
    """Wait until every process in the group is gone.

    ``proc.wait()`` only covers the xvfb-run wrapper. Chromium's own children
    keep writing the profile directory while they shut down, so deleting it
    before they exit leaves the directory behind, recreated after the delete.
    """
    while time.time() < deadline:
        try:
            os.killpg(group, 0)
        except (ProcessLookupError, PermissionError):
            return True
        time.sleep(0.2)
    try:
        os.killpg(group, signal.SIGKILL)
    except (OSError, ProcessLookupError):
        pass
    return False


def _terminate_browser(proc):
    """Tear the browser down by process group.

    xvfb-run wraps Chromium in a shell, so killing the tracked pid alone leaves
    the browser and the X server running. Killing by name would take out a
    browser the user is using themselves.
    """
    if proc is None or proc.poll() is not None:
        return
    try:
        if hasattr(os, "killpg"):
            group = os.getpgid(proc.pid)
            os.killpg(group, signal.SIGTERM)
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(group, signal.SIGKILL)
            if not _wait_for_group_exit(group, time.time() + 10):
                debug_print(f"Browser process group {group} outlived its teardown")
        else:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
    except (OSError, ProcessLookupError) as e:
        debug_print(f"Browser teardown: {e}")


def _attach_driver(port, driver_path):
    """Attach Selenium to the already-solved browser.

    Selenium Manager cannot resolve a driver on every host even when a matching
    chromedriver is installed, so the service path is always explicit.
    """
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service

    options = webdriver.ChromeOptions()
    options.debugger_address = f"127.0.0.1:{port}"
    return webdriver.Chrome(options=options, service=Service(executable_path=driver_path))


def download_via_browser(doi, filepath, domain, timeout=BROWSER_TIMEOUT):
    """Solve the challenge in a real browser, then download what it found.

    Returns ``{"md5": str | None, "downloaded": bool}`` so the caller can cache
    a resolved md5 even when the partner link itself failed, or None when the
    browser could not be used at all. The payload is fetched with the ordinary
    HTTP client using the browser's cookies rather than through the driver,
    since a 50 MB PDF should not travel over the DevTools connection.
    """
    global _BROWSER_ATTEMPTS

    if _BROWSER_ATTEMPTS >= MAX_BROWSER_ATTEMPTS:
        debug_print(f"Browser route already attempted {_BROWSER_ATTEMPTS} times; skipping")
        return None

    available, reason = browser_available()
    if not available:
        print(f"❌ Anna's Archive browser route unavailable: {reason}")
        return None

    _BROWSER_ATTEMPTS += 1
    chromium, driver_path, _ = _resolve_browser_tools()
    url = f"{domain}/scidb/{doi}"
    deadline = time.time() + timeout

    profile = tempfile.mkdtemp(prefix="anna_profile_")
    proc = None
    driver = None
    parsed = None
    cookies = None
    user_agent = None

    print(f"🌐 Solving the Anna's Archive browser check for {doi} (up to {timeout}s)...")
    try:
        proc = _launch_browser(chromium, profile, url)
        port = _read_devtools_port(profile, deadline)
        if port is None:
            debug_print("Browser never reported a DevTools port")
            return None
        debug_print(f"Browser DevTools port: {port}")

        title = _wait_for_solve(port, deadline)
        if not _solved(title):
            print("❌ The Anna's Archive browser check was not solved in time.")
            if title == CHALLENGE_TITLE:
                print(
                    "   The page stayed on the DDoS-Guard check for the whole "
                    "budget, which means this exit address is being held at the "
                    "manual captcha. A longer timeout will not clear it; a "
                    "different network path is needed."
                )
            return None
        debug_print(f"Browser check solved, page title: {title!r}")

        driver = _attach_driver(port, driver_path)
        parsed = parse_scidb_page(driver.page_source, domain)
        cookies = {c["name"]: c["value"] for c in driver.get_cookies()}
        user_agent = driver.execute_script("return navigator.userAgent")
    except Exception as e:
        debug_print(f"Browser route failed: {e}")
        return None
    finally:
        if driver is not None:
            try:
                driver.quit()
            except Exception as e:
                debug_print(f"Driver quit: {e}")
        _terminate_browser(proc)
        shutil.rmtree(profile, ignore_errors=True)

    if not parsed:
        debug_print(f"Solved page carried no md5 or download link for {doi}")
        return None
    if not parsed.get("url"):
        debug_print(f"Solved page carried md5 {parsed.get('md5')} but no download link")
        return {"md5": parsed.get("md5"), "downloaded": False}

    headers = {"Referer": url}
    if user_agent:
        headers["User-Agent"] = user_agent
    downloaded = _download_to_file(parsed["url"], filepath, headers=headers, cookies=cookies)
    if downloaded:
        print(f"Downloaded PDF from Anna's Archive: {filepath}")
    return {"md5": parsed.get("md5"), "downloaded": downloaded}


# ---------------------------------------------------------------------------
# Shared download helper
# ---------------------------------------------------------------------------

def _download_to_file(url, filepath, headers=None, cookies=None):
    """Fetch a URL and keep it only when the body is really a document."""
    try:
        resp = _requests_request(
            "get", url, headers=headers, cookies=cookies, timeout=DOWNLOAD_TIMEOUT,
        )
    except Exception as e:
        debug_print(f"Download from {_redact(url)} failed: {e}")
        return False
    if resp.status_code != 200:
        debug_print(f"Download from {_redact(url)} returned HTTP {resp.status_code}")
        return False
    os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
    if save_document_if_valid(resp.content, filepath):
        return True
    debug_print(f"Discarded non-document content from {_redact(url)} ({len(resp.content)} bytes)")
    return False


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def download_paper(
    doi=None,
    *,
    md5=None,
    download_folder=None,
    filename=None,
    secret_key=None,
    allow_scidb=False,
    allow_browser=True,
    routes=DEFAULT_ROUTES,
    interactive=False,
    verbose=False,
):
    """Download one document, trying the enabled routes in cost order.

    ``routes`` selects which of R1, R2, R4 and R5 may run, so a caller that
    interleaves its own route between them can invoke this twice. Returns the
    path of the downloaded file, or None.
    """
    global VERBOSE
    old_verbose = VERBOSE
    VERBOSE = VERBOSE or verbose
    try:
        return _download_paper(
            doi, md5, download_folder, filename, secret_key,
            allow_scidb, allow_browser, routes, interactive,
        )
    finally:
        VERBOSE = old_verbose


def _download_paper(doi, md5, download_folder, filename, secret_key,
                    allow_scidb, allow_browser, routes, interactive):
    if not doi and not md5:
        print("❌ Anna's Archive needs either a DOI or an md5.")
        return None

    download_folder = download_folder or get_download_directory()
    if not filename:
        stem = doi.replace('/', '_') if doi else md5
        filename = f"{stem}_anna.pdf"
    filepath = os.path.join(download_folder, filename)

    if md5 is None and doi:
        md5 = lookup_md5(doi)
        if md5:
            debug_print(f"Using cached md5 {md5} for DOI {doi}")

    if secret_key is None:
        secret_key = resolve_secret_key(interactive=interactive)

    domain = None

    def _domain():
        nonlocal domain
        if domain is None:
            domain = select_active_domain() or DOMAINS[0]
        return domain

    def _key_routes_enabled():
        return bool(secret_key) and not _KEY_ROUTES_DISABLED

    def _try_md5_routes(current_md5):
        """Run R1 then R2 for a known md5, cheapest first."""
        if not current_md5:
            return False
        if "R1" in routes and _key_routes_enabled():
            cookie = _session_cookie(secret_key, _domain())
            if cookie:
                debug_print(f"R1: reading the record for md5 {current_md5}")
                record = db_aarecord(current_md5, cookie, _domain())
                if record and download_via_ipfs(record, filepath):
                    return True
            else:
                debug_print("R1 skipped: could not obtain an account session")
        if "R2" in routes and _key_routes_enabled() and not _QUOTA_EXHAUSTED:
            debug_print(f"R2: requesting a fast download for md5 {current_md5}")
            if download_by_md5(current_md5, secret_key, _domain(), filepath, doi=doi):
                print(f"Downloaded PDF from Anna's Archive: {filepath}")
                return True
        elif "R2" in routes and _QUOTA_EXHAUSTED:
            debug_print("R2 skipped: daily fast-download quota already exhausted")
        return False

    if _try_md5_routes(md5):
        return filepath

    if "R4" in routes and doi:
        if not allow_scidb:
            debug_print("R4 skipped: --scidb was not given")
        elif not _key_routes_enabled():
            debug_print("R4 skipped: no usable account secret key")
        else:
            cookie = _session_cookie(secret_key, _domain())
            if cookie:
                debug_print(f"R4: resolving DOI {doi} through the SciDB page")
                parsed = scidb_lookup(doi, cookie, _domain())
                if parsed:
                    if parsed.get("md5"):
                        md5 = parsed["md5"]
                        remember_md5(doi, md5)
                    if parsed.get("url") and _download_to_file(parsed["url"], filepath):
                        print(f"Downloaded PDF from Anna's Archive: {filepath}")
                        return filepath
                    # The partner link expires quickly; a fresh md5 may still
                    # be usable through the cheaper routes.
                    if _try_md5_routes(md5):
                        return filepath

    if "R5" in routes and doi:
        if not allow_browser:
            debug_print("R5 skipped: the browser route is disabled")
        else:
            result = download_via_browser(doi, filepath, _domain())
            if result:
                if result.get("md5"):
                    md5 = result["md5"]
                    remember_md5(doi, md5)
                if result.get("downloaded"):
                    return filepath
                # The browser resolved the DOI even though the partner link
                # failed, so the cheaper md5 routes are worth another try.
                if _try_md5_routes(md5):
                    return filepath

    return None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def print_default_paths():
    print(f"Cache directory:       {get_cache_directory()}")
    print(f"Credentials file:      {default_credentials_file()}")
    print(f"md5 cache file:        {md5_cache_file()}")
    print(f"Download directory:    {get_download_directory()}")
    print(f"Secret key variable:   ${SECRET_KEY_ENV}")
    print(f"Mirrors:               {', '.join(DOMAINS)}")


def print_user_info(secret_key):
    if not secret_key:
        print("Anna's Archive account: not configured")
        print(f"Set ${SECRET_KEY_ENV} or run with --key to configure one.")
        return
    domain = select_active_domain()
    if not domain:
        print("❌ No Anna's Archive mirror is reachable.")
        return
    cookie = login(secret_key, domain)
    if not cookie:
        print("❌ Login failed: the secret key was rejected.")
        return
    expiry = account_cookie_expiry(cookie)
    print(f"Anna's Archive account: logged in at {domain}")
    if expiry:
        print(f"Session cookie expires: {expiry}")
    print(f"Server reports logged in: {is_logged_in(cookie, domain)}")


def main():
    global VERBOSE, ACTIVE_PROXY

    parent_package = __name__.split('.')[0] if '.' in __name__ else None
    if parent_package is None:
        program_name = 'anna'
    else:
        if '_' in parent_package:
            parent_package = parent_package[:parent_package.index('_')]
        program_name = f"{parent_package} anna"

    parser = argparse.ArgumentParser(
        prog=program_name,
        description="Download documents from Anna's Archive by DOI or md5",
        epilog='Example usage:\n'
               '  %(prog)s --user-info\n'
               '  %(prog)s --doi "10.1038/nature12373"\n'
               '  %(prog)s --md5 a5efa9791b836507541d615ed3f069e9\n'
               '  %(prog)s --doi "10.1038/nature12373" --scidb',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('--doi', type=str, help='DOI of the document to download')
    parser.add_argument('--md5', type=str, help="Anna's Archive md5 of the document to download")
    parser.add_argument('--download-folder', type=str, help='Folder to save the document into')
    parser.add_argument('-u', '--user-info', action='store_true', help='Print account status')
    parser.add_argument(
        '-c', '--credentials',
        type=str,
        metavar='FILE',
        help='Path to JSON file containing the account secret (format: {"anna_secret_key": "..."})',
    )
    parser.add_argument(
        '--key',
        type=str,
        metavar='SECRET',
        help="Account secret key, or - to read it from standard input. Prefer "
             f"${SECRET_KEY_ENV} or a credentials file: a key given on the "
             "command line is visible to every user on the machine.",
    )
    parser.add_argument(
        '--scidb',
        action='store_true',
        help="Resolve a cold DOI through the member SciDB page. Anna's Archive "
             "qualifies this membership perk with \"Only for normal browser use. "
             "For scripts please use our metadata torrents.\", so it is off by "
             "default; enabling it risks the account.",
    )
    parser.add_argument(
        '--no-browser',
        action='store_true',
        help='Do not fall back to solving the browser check in Chromium',
    )
    parser.add_argument('--md5-cache-clear', action='store_true', help='Delete the cached DOI to md5 mappings')
    parser.add_argument('-C', '--clear-cache', action='store_true', help='Clear cache before running')
    parser.add_argument('-P', '--print-default', action='store_true', help='Print default paths and settings')
    parser.add_argument('--verbose', action='store_true', help='Enable verbose debug output')
    parser.add_argument('--proxy', type=str, help=f'Path to proxy configuration JSON file (default: {proxy_config.DEFAULT_PROXY_FILE})')
    parser.add_argument('--no-proxy', action='store_true', help='Disable proxy usage even if a proxy configuration is present')
    parser.add_argument('--auto-proxy', action='store_true', help='Automatically fetch a working proxy configuration when missing or invalid')
    args = parser.parse_args()

    VERBOSE = args.verbose
    ACTIVE_PROXY = proxy_config.configure_from_cli(
        args.proxy, no_proxy=args.no_proxy, auto_fetch=args.auto_proxy, verbose=VERBOSE
    )
    proxy_config.ProxySettings(enabled=False).apply_environment()

    if args.print_default:
        print_default_paths()
        return

    if args.clear_cache:
        cache_dir = get_cache_directory()
        shutil.rmtree(cache_dir, ignore_errors=True)
        print(f"Cleared cache directory: {cache_dir}")

    if args.md5_cache_clear:
        path = md5_cache_file()
        try:
            os.remove(path)
            print(f"Cleared md5 cache: {path}")
        except OSError:
            print(f"No md5 cache to clear at {path}")

    interactive = sys.stdin.isatty()
    secret_key = resolve_secret_key(
        args.key, credentials_file=args.credentials, interactive=False
    )

    if args.user_info:
        print_user_info(secret_key)
        return

    if not args.doi and not args.md5:
        if args.clear_cache or args.md5_cache_clear or args.credentials or args.key:
            return
        parser.error("one of --doi or --md5 is required")

    result = download_paper(
        args.doi,
        md5=args.md5,
        download_folder=args.download_folder,
        secret_key=secret_key,
        allow_scidb=args.scidb,
        allow_browser=not args.no_browser,
        interactive=interactive,
        verbose=VERBOSE,
    )
    if result:
        print(f"✅ Saved to {result}")
    else:
        print("❌ Could not download the requested document from Anna's Archive.")
        sys.exit(1)


if __name__ == "__main__":
    main()
