"""Core search and retrieval workflow for ``getpapers`` CLI invocations.

This module coordinates searches across Nexus, CrossRef, Unpaywall, and
publisher APIs, while handling caching, configuration, and output formatting.
Functions here are designed for reuse by other modules (for example
``request.py``) and are intentionally asynchronous-aware so they can run in
concurrent contexts.
"""

import argparse
import asyncio
import json
from libstc_geck.advices import format_document
from libstc_geck.client import StcGeck
import aiohttp
import sys
import platform
import re
from datetime import datetime
import functools
from urllib.parse import quote_plus
import os
import requests
import time
import unpywall
from unpywall import Unpywall
import pandas as pd
from unpywall.utils import UnpywallCredentials
from unpywall.cache import UnpywallCache
from urllib.parse import urljoin
from crossref.restful import Works
import PyPDF2
import signal
import threading
import queue
import shutil
from pathlib import Path
from typing import Dict, Optional

from . import nexus  # Import Nexus bot functions from .nexus module
from . import libgen  # Import LibGen functions from .libgen module
from . import configuration

DEFAULT_LIMIT = configuration.DEFAULT_LIMIT

VERBOSE = False  # Global verbose flag


def vprint(*args, **kwargs):
    if VERBOSE:
        print(*args, **kwargs)

# Global variable for default config file location
GETPAPERS_CONFIG_FILE = str(configuration.GETPAPERS_CONFIG_FILE)

# Set Unpywall cache directory to the same folder as the config file
UNPYWALL_CACHE_DIR = str(configuration.UNPYWALL_CACHE_DIR)
UNPYWALL_CACHE_FILE = str(configuration.UNPYWALL_CACHE_FILE)

DEFAULT_DOWNLOAD_FOLDER = configuration.DEFAULT_DOWNLOAD_FOLDER
# Increase the tolerance for slow networks when downloading PDFs.
DOWNLOAD_TIMEOUT = 120
DB_CHOICES: tuple[str, ...] = ("nexus", "scihub", "anna", "unpaywall", "libgen")

def ensure_directory_exists(path: str) -> None:
    configuration.ensure_directory_exists(Path(path))


def save_credentials(
    email: str | None = None,
    elsevier_api_key: str | None = None,
    wiley_tdm_token: str | None = None,
    ieee_api_key: str | None = None,
    config_file: str | None = None,
):
    return configuration.save_credentials(
        email=email,
        elsevier_api_key=elsevier_api_key,
        wiley_tdm_token=wiley_tdm_token,
        ieee_api_key=ieee_api_key,
        config_file=config_file,
        verbose=VERBOSE,
    )


def normalize_db_selection(db: str | list[str] | tuple[str, ...] | None) -> list[str]:
    """Normalize the ``--db`` selection to a concrete list of services.

    The CLI accepts comma-delimited strings or multiple ``--db`` flags. Any
    request containing ``"all"`` or no explicit services resolves to the full
    list defined in :data:`DB_CHOICES`.
    """

    if db is None:
        return list(DB_CHOICES)

    if isinstance(db, str):
        # Support comma-separated values from older invocations or GUI input
        parts = [part.strip() for part in db.split(",") if part.strip()]
    else:
        parts = [str(part).strip() for part in db if str(part).strip()]

    if not parts or any(part == "all" for part in parts):
        return list(DB_CHOICES)

    filtered = [part for part in parts if part in DB_CHOICES]
    return filtered or list(DB_CHOICES)


def load_credentials(
    config_file: str | None = None,
    interactive: Optional[bool] = None,
    env_prefix: str = "GETSCIPAPERS_",
):
    return configuration.load_credentials(
        config_file=config_file,
        interactive=interactive,
        env_prefix=env_prefix,
        verbose=VERBOSE,
    )


require_email = configuration.require_email
# def is_paper_doi(doi: str) -> bool:
#     """
#     Check if a DOI corresponds to a scholarly paper (article, preprint, or book) using the Crossref API.
#     Returns True if the DOI is for a journal article, proceeding, preprint, or book, False otherwise.
#     Falls back to direct HTTP request if the python API returns None.
#     """
#     try:
#         works = Works()
#         result = works.doi(doi)
#         if not result:
#             # Fallback: try direct HTTP request to Crossref API
#             result = fetch_crossref_data(doi)
#             if not result:
#                 return False
        
#         # Accept common scholarly types
#         valid_types = [
#             'journal-article',
#             'proceedings-article',
#             'book',
#             'book-chapter',
#             'monograph',
#             'reference-book',
#             'posted-content',  # preprints
#             'report'
#         ]
#         return result.get('type') in valid_types
#     except Exception:
#         return False

def fetch_crossref_data(doi):
    """
    Fetch data from Crossref API for a given DOI.
    Returns the message part of the response if successful, None otherwise.
    """
    url = f"https://api.crossref.org/works/{requests.utils.quote(doi)}"
    active_email = require_email()

    headers = {
        "User-Agent": f"PythonScript/1.0 (mailto:{active_email})",
        "Accept": "application/json, text/plain, */*",
        "Connection": "keep-alive",
        "DNT": "1",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://doi.org/",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }
    
    try:
        with requests.Session() as session:
            session.headers.update(headers)
            response = session.get(url, timeout=10, allow_redirects=True)
            response.raise_for_status()  # Raise an error for bad status codes
            data = response.json()
            
            # Extract and return the message part if status is ok
            if data.get("status") == "ok":
                item = data.get("message", {})
                vprint(f"Crossref data fetched for DOI {doi}:")
                vprint(f"Title: {item.get('title', ['N/A'])[0]}")
                vprint(f"Authors: {[author.get('given', '') + ' ' + author.get('family', '') for author in item.get('author', [])]}")
                vprint(f"Published: {item.get('published', {}).get('date-parts', [['N/A']])[0][0]}")
                vprint(f"Journal: {item.get('container-title', ['N/A'])[0]}")
                return item
            else:
                vprint(f"Crossref API returned non-ok status for DOI {doi}")
                return None
                
    except requests.exceptions.RequestException as e:
        vprint(f"Error fetching Crossref data for DOI {doi}: {e}")
        return None
    except json.JSONDecodeError:
        vprint(f"Error decoding JSON response for DOI {doi}")
        return None
    except Exception as e:
        vprint(f"Unexpected error fetching Crossref data for DOI {doi}: {e}")
        return None

async def is_open_access_unpaywall(doi: str, email: Optional[str] = None) -> bool:
    """
    Check if a DOI is open access using the Unpaywall API.
    Returns True if open access, False otherwise.
    """
    active_email = email or require_email()
    api_url = f"https://api.unpaywall.org/v2/{quote_plus(doi)}?email={quote_plus(active_email)}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url, timeout=15) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("is_oa", False)
                else:
                    vprint(f"Unpaywall API returned status {resp.status} for DOI {doi}")
                    return False
    except Exception as e:
        vprint(f"Error checking OA status for DOI {doi} via Unpaywall API: {e}")
        return False

def resolve_pii_to_doi(pii: str) -> str:
    """
    Try to resolve a ScienceDirect PII to a DOI using Elsevier's API.
    Returns DOI string if found, else None.
    """
    # Clean PII by removing hyphens and brackets
    clean_pii = pii.replace('-', '').replace('(', '').replace(')', '')
    vprint(f"Cleaned PII from {pii} to {clean_pii}")
    
    api_url = f"https://api.elsevier.com/content/article/pii/{clean_pii}"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.2478.67',
        'Accept': 'application/json,text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-User': '?1',
        'Pragma': 'no-cache',
        'Cache-Control': 'no-cache',
        'DNT': '1',
        'X-ELS-APIKey': configuration.ELSEVIER_API_KEY,
    }
    try:
        resp = requests.get(api_url, headers=headers, timeout=10)
        if resp.status_code == 200:
            content_type = resp.headers.get('content-type', '').lower()
            if 'application/json' in content_type:
                try:
                    data = resp.json()
                    doi = (
                        data.get("full-text-retrieval-response", {})
                            .get("coredata", {})
                            .get("prism:doi")
                    )
                    if doi:
                        vprint(f"Resolved PII {clean_pii} to DOI {doi} via Elsevier API")
                        return doi
                    else:
                        vprint(f"PII {clean_pii} found but no DOI in Elsevier API response")
                except json.JSONDecodeError:
                    vprint(f"Elsevier API returned invalid JSON for PII {clean_pii}")
                    vprint(f"Response content: {resp.text[:200]}...")
            elif 'xml' in content_type:
                # Handle XML response
                import xml.etree.ElementTree as ET
                try:
                    root = ET.fromstring(resp.text)
                    # Look for DOI in XML namespaces
                    namespaces = {
                        'ns': 'http://www.elsevier.com/xml/svapi/article/dtd',
                        'prism': 'http://prismstandard.org/namespaces/basic/2.0/'
                    }
                    doi_element = root.find('.//prism:doi', namespaces)
                    if doi_element is not None and doi_element.text:
                        doi = doi_element.text
                        vprint(f"Resolved PII {clean_pii} to DOI {doi} via Elsevier API (XML)")
                        return doi
                    else:
                        vprint(f"PII {clean_pii} found but no DOI in Elsevier API XML response")
                except ET.ParseError:
                    vprint(f"Elsevier API returned invalid XML for PII {clean_pii}")
                    vprint(f"Response content: {resp.text[:200]}...")
            else:
                vprint(f"Elsevier API returned unexpected content type '{content_type}' for PII {clean_pii}")
                vprint(f"Response content: {resp.text[:200]}...")
        else:
            vprint(f"Elsevier API returned status {resp.status_code} for PII {clean_pii}")
    except Exception as e:
        vprint(f"Error resolving PII {clean_pii} to DOI: {e}")
    return None

def extract_mdpi_doi_from_url(url: str) -> str:
    """
    Try to extract an MDPI DOI from a URL.
    Returns DOI string if found, else None.
    """
    mdpi_match = re.search(r'mdpi\.com/([^/]+)/([^/]+)/([^/]+)/([^/?#]+)', url)
    if mdpi_match:
        issn = mdpi_match.group(1)
        volume = mdpi_match.group(2)
        issue = mdpi_match.group(3)
        article = mdpi_match.group(4)
        mdpi_issn_to_journal = {
            "2071-1050": "su",
            "1424-8220": "sensors",
            "1996-1944": "ma",
            "2073-4441": "water",
            "1660-4601": "ijerph",
            "2072-6643": "nu",
            "2079-4991": "nanomaterials",
            "2073-4360": "polymers",
            "1999-4915": "viruses",
            "2075-163X": "minerals",
            "2227-9717": "processes",
            "2227-9040": "chemosensors",
            "2076-3417": "app",
            "2220-9964": "ijgi",
            "2076-2615": "animals",
            "2072-4292": "remotesensing",
            "2079-6382": "antibiotics",
            "2076-3921": "antioxidants",
            "2077-0383": "jcm",
            "2079-7737": "biology",
            "2223-7747": "plants",
            "2072-6651": "toxins",
            "2073-8994": "symmetry",
            "2075-5309": "buildings",
            "2079-9284": "cosmetics",
            "2073-4433": "atmosphere",
            "2079-6374": "biosensors",
            "2072-6694": "cancers",
            "2073-4344": "catalysts",
            "2079-9292": "electronics",
            "2075-4450": "insects",
            "2073-4352": "crystals",
            "2079-6412": "coatings",
            "2072-6643": "nutrients",
        }
        journal_code = mdpi_issn_to_journal.get(issn, issn)
        # The correct DOI format is: 10.3390/{journal_code}{volume}{issue_padded}{article_padded}
        # Issue is always 2 digits, article is always at least 4 digits
        issue_padded = issue.zfill(2)
        article_padded = article.zfill(4)
        mdpi_doi = f"10.3390/{journal_code}{volume}{issue_padded}{article_padded}"
        vprint(f"Extracted MDPI DOI from URL: {mdpi_doi}")
        return mdpi_doi
    else:
        vprint(f"Could not extract MDPI DOI from URL: {url}")
        return None

def fetch_dois_from_url(url: str, doi_pattern: str) -> list:
    """
    Fetch a URL and extract DOIs from its content.
    Returns a list with up to 3 valid DOIs found, or an empty list if none.
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.2478.67',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-User': '?1',
        'Pragma': 'no-cache',
        'Cache-Control': 'no-cache',
        'DNT': '1',
    }
    try:
        session = requests.Session()
        session.headers.update(headers)
        response = session.get(url, timeout=15, allow_redirects=True)
        if 'unsupported_browser' in response.url or response.status_code == 403:
            vprint(f"Access denied or unsupported browser page for {url}")
            return []
        if response.url != url:
            vprint(f"URL redirected from {url} to {response.url}")
            time.sleep(2)
            vprint("Waited 2 seconds after redirect")
        if response.status_code == 200:
            page_dois = re.findall(doi_pattern, response.text)
            if page_dois:
                vprint(f"Found DOIs in {response.url}: {page_dois}")
                # Return up to the first 3 valid DOIs found
                return page_dois[:3]
            else:
                vprint(f"No DOIs found in {response.url}")
        else:
            vprint(f"Failed to fetch {url}: HTTP {response.status_code}")
    except requests.exceptions.TooManyRedirects:
        vprint(f"Too many redirects for {url}")
    except requests.exceptions.RequestException as e:
        vprint(f"Error fetching {url}: {e}")
    return []

# def filter_paper_dois(dois: list) -> list:
#     """
#     Filter a list of DOIs, keeping only those that are scholarly papers.
#     """
#     filtered = []
#     for doi in dois:
#         if is_paper_doi(doi):
#             filtered.append(doi)
#         else:
#             vprint(f"Ignored non-paper DOI: {doi}")
#     return filtered

def is_valid_doi(doi: str) -> bool:
    """
    Check if a single DOI is valid using the DOI System Proxy Server REST API.
    Returns True if the DOI exists and resolves properly.
    Falls back to Crossref if the API doesn't work.
    """
    vprint(f"Checking validity of DOI: {doi}")
    
    # First, try using the DOI System Proxy Server REST API with comprehensive headers
    api_url = f"https://doi.org/api/handles/{doi}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.2478.67",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Referer": "https://doi.org/",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "DNT": "1"
    }
    
    try:
        response = requests.get(api_url, headers=headers, timeout=15)
        if response.status_code == 200:
            data = response.json()
            response_code = data.get("responseCode")
            
            # Response code 1 means success (DOI exists)
            if response_code == 1:
                vprint(f"DOI {doi} is valid (responseCode=1)")
                return True
                
            # Response code 100 means handle not found (DOI doesn't exist)
            elif response_code == 100:
                vprint(f"DOI {doi} is invalid (responseCode=100, handle not found)")
                return False
                
            # Response code 200 means values not found (handle exists but has no values)
            elif response_code == 200:
                vprint(f"DOI {doi} exists but has no values (responseCode=200)")
                return True
                
            else:
                vprint(f"DOI {doi} check returned unexpected responseCode: {response_code}")
        else:
            vprint(f"DOI API returned status code {response.status_code} for {doi}")
            
    except Exception as e:
        vprint(f"Error checking DOI via REST API: {doi}: {e}")

    # Fallback: Try using Crossref API
    vprint(f"Using Crossref as fallback for DOI validation: {doi}")
    try:
        works = Works()
        result = works.doi(doi)
        if result:
            vprint(f"DOI {doi} found in Crossref, treating as valid")
            return True
        else:
            vprint(f"DOI {doi} not found in Crossref")
    except Exception as e:
        vprint(f"Error checking DOI in Crossref: {doi}: {e}")

    # Last resort: try a HEAD request to see if doi.org redirects properly
    try:
        browser_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.2478.67",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate", 
            "Sec-Fetch-Site": "none",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "DNT": "1"
        }
        url = f"https://doi.org/{doi}"
        resp = requests.head(url, allow_redirects=True, timeout=10, headers=browser_headers)
        if resp.status_code in (200, 301, 302):
            vprint(f"DOI {doi} resolves via HEAD request (status={resp.status_code})")
            return True
    except Exception as e:
        vprint(f"Error on HEAD request for DOI {doi}: {e}")
    
    return False

def validate_dois(dois: list) -> list:
    """
    Given a list of DOIs, return only those that are valid (resolve at doi.org or found in Crossref).
    """
    valid_dois = []
    for doi in dois:
        if is_valid_doi(doi):
            valid_dois.append(doi)
    return valid_dois

def extract_isbns_from_text(text: str) -> list:
    """
    Extract ISBN-13 (preferred) and ISBN-10 numbers from text content.
    Returns a list of (isbn, doi) tuples, preferring ISBN-13 if found, otherwise ISBN-10.
    Only includes valid ISBNs (according to Crossref) and their associated DOI(s) if available.
    If multiple DOIs are found for an ISBN, tries to extract the common DOI prefix (e.g., <common doi>.ch001, <common doi>.ch002).
    If the common prefix is not a valid DOI, returns None for DOI.
    Prints details with vprint.
    Only extracts ISBN-10 if no ISBN-13 is found.
    """
    # ISBN-10: 10 digits, last digit can be X, may have hyphens or spaces
    isbn10_pattern = r'\b(?:ISBN(?:-10)?:?\s*)?((?:\d[\s-]*){9}[\dXx])\b'
    # ISBN-13: 13 digits, may have hyphens or spaces, starts with 978 or 979
    isbn13_pattern = r'\b(?:ISBN(?:-13)?:?\s*)?((97[89][\s-]*){1}([\d][\s-]*){10})\b'

    def normalize_isbn(isbn):
        return re.sub(r'[\s-]', '', isbn).upper()

    def extract_common_doi_prefix(dois):
        """
        Given a list of DOIs, extract the longest common prefix before a chapter/article suffix.
        E.g., for ['10.1007/978-3-030-12345-6.ch001', '10.1007/978-3-030-12345-6.ch002'],
        returns '10.1007/978-3-030-12345-6'.
        """
        if not dois:
            return None
        split_dois = [re.split(r'(\.ch\d+|\.\d+)$', d)[0] for d in dois]
        prefix = os.path.commonprefix(split_dois)
        if prefix.endswith('.'):
            prefix = prefix[:-1]
        return prefix if prefix else None

    # Extract ISBN-13s
    isbn13s = []
    for match in re.findall(isbn13_pattern, text):
        if isinstance(match, tuple):
            isbn = next((m for m in match if m and isinstance(m, str)), None)
        else:
            isbn = match
        if isbn:
            norm_isbn = normalize_isbn(isbn)
            if norm_isbn not in isbn13s:
                isbn13s.append(norm_isbn)
    vprint(f"Found ISBN-13s: {isbn13s}")

    works = Works()
    results = []

    # Prefer ISBN-13s
    if isbn13s:
        for isbn in isbn13s:
            try:
                vprint(f"Querying Crossref for ISBN-13: {isbn}")
                items = list(works.filter(isbn=isbn))
                vprint(f"Crossref returned {len(items)} items for ISBN-13 {isbn}")
                if items:
                    dois = []
                    for item in items:
                        doi = item.get("DOI")
                        if doi:
                            dois.append(doi)
                    if dois:
                        if len(dois) == 1:
                            vprint(f"Found DOI {dois[0]} for ISBN-13 {isbn}")
                            results.append((isbn, dois[0]))
                        else:
                            common_prefix = extract_common_doi_prefix(dois)
                            if common_prefix:
                                # Check if common prefix is a valid DOI
                                if is_valid_doi(common_prefix):
                                    vprint(f"Multiple DOIs found for ISBN-13 {isbn}, common prefix is a valid DOI: {common_prefix}")
                                    results.append((isbn, common_prefix))
                                else:
                                    vprint(f"Common prefix {common_prefix} for ISBN-13 {isbn} is not a valid DOI. Trying to append ISBN to the prefix...")
                                    # Try appending the ISBN in a few plausible ways and test validity
                                    tried_candidates = []
                                    candidates = [
                                        f"{common_prefix}.{isbn}",
                                        f"{common_prefix}{isbn}",
                                        f"{common_prefix}-{isbn}"
                                    ]
                                    found_candidate = None
                                    for cand in candidates:
                                        if cand in tried_candidates:
                                            continue
                                        tried_candidates.append(cand)
                                        try:
                                            vprint(f"Testing candidate DOI: {cand}")
                                            if is_valid_doi(cand):
                                                vprint(f"Appended ISBN produced a valid DOI: {cand}")
                                                found_candidate = cand
                                                break
                                        except Exception as e:
                                            vprint(f"Error validating candidate DOI {cand}: {e}")
                                            continue
                                    if found_candidate:
                                        results.append((isbn, found_candidate))
                                    else:
                                        vprint(f"No valid DOI found by appending ISBN {isbn} to prefix {common_prefix}")
                                        results.append((isbn, None))
                            else:
                                vprint(f"Multiple DOIs found for ISBN-13 {isbn}, no common prefix. Returning all DOIs.")
                                results.append((isbn, dois))
                    else:
                        vprint(f"No DOI found for ISBN-13 {isbn}")
                        results.append((isbn, None))
                else:
                    vprint(f"No Crossref entry found for ISBN-13 {isbn}")
            except Exception as e:
                vprint(f"Error querying Crossref for ISBN-13 {isbn}: {e}")
                continue
        return results

    # Only extract ISBN-10 if no ISBN-13 found
    isbn10s = []
    for match in re.findall(isbn10_pattern, text):
        if isinstance(match, tuple):
            isbn = next((m for m in match if m and isinstance(m, str)), None)
        else:
            isbn = match
        if isbn:
            norm_isbn = normalize_isbn(isbn)
            if norm_isbn not in isbn10s:
                isbn10s.append(norm_isbn)
    vprint(f"Found ISBN-10s: {isbn10s}")

    for isbn in isbn10s:
        try:
            vprint(f"Querying Crossref for ISBN-10: {isbn}")
            items = list(works.filter(isbn=isbn))
            vprint(f"Crossref returned {len(items)} items for ISBN-10 {isbn}")
            if items:
                dois = []
                for item in items:
                    doi = item.get("DOI")
                    if doi:
                        dois.append(doi)
                if dois:
                    if len(dois) == 1:
                        vprint(f"Found DOI {dois[0]} for ISBN-10 {isbn}")
                        results.append((isbn, dois[0]))
                    else:
                        common_prefix = extract_common_doi_prefix(dois)
                        if common_prefix:
                            # If common prefix is already a valid DOI, use it
                            if is_valid_doi(common_prefix):
                                vprint(f"Multiple DOIs found for ISBN-10 {isbn}, common prefix is a valid DOI: {common_prefix}")
                                results.append((isbn, common_prefix))
                            else:
                                vprint(f"Common prefix {common_prefix} for ISBN-10 {isbn} is not a valid DOI. Trying to append ISBN to the prefix...")
                                # Try appending the ISBN in a few plausible ways and test validity
                                tried_candidates = []
                                candidates = [
                                    f"{common_prefix}.{isbn}",
                                    f"{common_prefix}{isbn}",
                                    f"{common_prefix}-{isbn}"
                                ]
                                found_candidate = None
                                for cand in candidates:
                                    if cand in tried_candidates:
                                        continue
                                    tried_candidates.append(cand)
                                    try:
                                        vprint(f"Testing candidate DOI: {cand}")
                                        if is_valid_doi(cand):
                                            vprint(f"Appended ISBN produced a valid DOI: {cand}")
                                            found_candidate = cand
                                            break
                                    except Exception as e:
                                        vprint(f"Error validating candidate DOI {cand}: {e}")
                                        continue
                                if found_candidate:
                                    results.append((isbn, found_candidate))
                                else:
                                    vprint(f"No valid DOI found by appending ISBN {isbn} to prefix {common_prefix}")
                                    results.append((isbn, None))
                        else:
                            vprint(f"Multiple DOIs found for ISBN-10 {isbn}, no common prefix. Returning all DOIs.")
                            results.append((isbn, dois))
                else:
                    vprint(f"No DOI found for ISBN-10 {isbn}")
                    results.append((isbn, None))
            else:
                vprint(f"No Crossref entry found for ISBN-10 {isbn}")
        except Exception as e:
            vprint(f"Error querying Crossref for ISBN-10 {isbn}: {e}")
            continue
    return results

def extract_dois_from_text(text: str) -> list:
    """
    Extract DOI numbers from text content.
    Returns a list of unique, valid paper DOIs.
    Only keeps DOIs that resolve at https://doi.org/<doi> (HTTP 200, 301, 302).
    If no DOI is found, tries to extract ISBN and resolve to DOI.
    """
    vprint(f"Extracting DOIs from text {text[:100]}... (length: {len(text)})")
    dois = []

    doi_patterns = [
        r'\b10\.\d{4,9}/[A-Za-z0-9\-._;()/:]+',
        r'\b10\.\d{4,9}\s*/\s*[A-Za-z0-9\-._;()/:]+',
        r'\bdoi:\s*(10\.\d{4,9}/[A-Za-z0-9\-._;()/:]+)',
        r'\bhttps?://doi\.org/(10\.\d{4,9}/[A-Za-z0-9\-._;()/:]+)',
        r'\bhttps?://dx\.doi\.org/(10\.\d{4,9}/[A-Za-z0-9\-._;()/:]+)',
        r'\bdoi\s*=\s*["\']?(10\.\d{4,9}/[A-Za-z0-9\-._;()/:]+)',
        r'\bDigital Object Identifier[:\s]*(10\.\d{4,9}/[A-Za-z0-9\-._;()/:]+)',
        r'\bDOI Identifier[:\s]*(10\.\d{4,9}/[A-Za-z0-9\-._;()/:]+)',
        r'\bDOI\s*(10\.\d{4,9}/[A-Za-z0-9\-._;()/:]+)',  
        r'\bDOI[:\s]+(10\.\d{4,9}/[A-Za-z0-9\-._;()/:]+)', 
        r'\b(10\.\d{4,9}/[A-Za-z0-9\-._;()/:]+)',
        r'\b10\.1109/[A-Z]+(?:\.[0-9]{4})+\.[0-9]+'
    ]
    for pattern in doi_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        if matches:
            for match in matches:
                if isinstance(match, tuple):
                    doi_part = next((group for group in match if group.startswith('10.')), None)
                    if doi_part:
                        dois.append(doi_part)
                elif isinstance(match, str):
                    doi_match = re.search(r'(10\.\d{4,9}/[A-Za-z0-9\-._;()/:]+)', match)
                    if doi_match:
                        dois.append(doi_match.group(1))
                    else:
                        dois.append(match)

    # Remove trailing dot from DOIs
    dois = [doi[:-1] if doi.endswith('.') else doi for doi in dois]

    dois = list(dict.fromkeys(dois))

    url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+[^\s<>"{}|\\^`\[\].,;:!?]|https?://[^\s<>"{}|\\^`\[\]]+\.\.\.[^\s<>"{}|\\^`\[\]]+[^\s<>"{}|\\^`\[\].,;:!?]'
    urls = re.findall(url_pattern, text)
    vprint(f"Found {len(urls)} URLs in text for DOI extraction: {urls}")

    for url in urls:
        already_has_doi = False
        for pattern in [
            r'10\.\d{4,9}/[A-Za-z0-9\-._;()/:]+',
            r'10\.\d{4,9}\s*/\s*[A-Za-z0-9\-._;()/:]+'
        ]:
            if re.search(pattern, url):
                already_has_doi = True
                break
        if already_has_doi:
            continue

        if "sciencedirect.com" in url or "kidney-international.org" in url or "journal.chestnet.org" in url:
            pii_match = re.search(r'/(?:pii|article)/([S][A-Z0-9()-]+)', url, re.IGNORECASE)
            if pii_match:
                pii = pii_match.group(1)
                vprint(f"Detected ScienceDirect PII in URL: {pii}")
                doi = resolve_pii_to_doi(pii)
                if doi:
                    # Remove trailing dot if present
                    doi = doi[:-1] if doi.endswith('.') else doi
                    dois.append(doi)
                else:
                    vprint(f"Could not resolve PII {pii} to DOI")
            else:
                vprint(f"No PII found in ScienceDirect URL: {url}")
            continue

        if "mdpi.com" in url:
            mdpi_doi = extract_mdpi_doi_from_url(url)
            if mdpi_doi:
                mdpi_doi = mdpi_doi[:-1] if mdpi_doi.endswith('.') else mdpi_doi
                dois.append(mdpi_doi)
            continue

        vprint(f"Checking URL for DOI: {url}")
        for doi_pattern in doi_patterns:
            page_dois = fetch_dois_from_url(url, doi_pattern)
            # Remove trailing dot from DOIs found in page
            page_dois = [d[:-1] if d.endswith('.') else d for d in page_dois]
            dois.extend(page_dois)

    unique_dois = list(dict.fromkeys(dois))
    valid_dois = validate_dois(unique_dois)

    # If no DOI found, try to extract ISBN and resolve to DOI
    if not valid_dois:
        vprint("No DOI found, trying to extract ISBN and resolve to DOI...")
        isbn_results = extract_isbns_from_text(text)
        if isbn_results:
            # isbn_results is a list of (isbn, doi) tuples
            for isbn, doi in isbn_results:
                if doi:
                    doi = doi[:-1] if doi.endswith('.') else doi
                    vprint(f"Resolved ISBN {isbn} to DOI {doi}")
                    valid_dois = [doi]
                    break
                else:
                    vprint(f"ISBN {isbn} did not resolve to a DOI")
    return valid_dois

def extract_doi_from_title(title: str) -> str:
    """
    Search Crossref for a given paper title and return the DOI if there is a unique match.
    If Crossref returns more than one matching item, return None.
    """
    if not title or not title.strip():
        vprint("extract_doi_from_title: empty title provided")
        return None

    try:
        works = Works()
        # Query Crossref for the title. Limit scanning to two results:
        # if more than one result is found we will bail out.
        results = works.query(title).select(['DOI', 'title']).sort('relevance').order('desc')

        found = []
        for item in results:
            doi = item.get('DOI')
            if doi:
                found.append(item)
            # Stop early if more than one match
            if len(found) > 1:
                vprint(f"extract_doi_from_title: more than one Crossref result for title '{title}' -> giving up")
                return None

        if len(found) == 1:
            doi = found[0].get('DOI')
            vprint(f"extract_doi_from_title: unique DOI found for title '{title}': {doi}")
            return doi

        vprint(f"extract_doi_from_title: no Crossref results for title '{title}'")
        return None

    except Exception as e:
        vprint(f"extract_doi_from_title: Crossref query failed for title '{title}': {e}")
        return None

def extract_dois_from_file(input_file: str):
    """
    Extract DOI numbers from a text file and write them to a new file.
    Also tries to extract Elsevier PII numbers from the file name and resolve them to DOIs.
    Additionally attempts to extract ISBN numbers from the file name and resolve them to DOIs via Crossref.
    As a final fallback, use the file name (cleaned) as a title and try to extract a DOI via Crossref title search.
    Returns the list of extracted DOIs.
    Prints status messages with icons for better readability.
    """
    ICON_START = "🚀"
    ICON_FILE = "📄"
    ICON_SUCCESS = "✅"
    ICON_FAIL = "❌"
    ICON_DOI = "🔎"
    ICON_OUTPUT = "📝"
    ICON_WARN = "⚠️"
    ICON_ISBN = "📚"
    ICON_TITLE = "📰"

    vprint(f"{ICON_START} Extracting DOIs from file: {input_file}")
    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            content = f.read()
        vprint(f"{ICON_FILE} Read input file: {input_file}")
    except Exception as e:
        vprint(f"{ICON_FAIL} Failed to read input file: {e}")
        return []

    # Use the new extract_dois_from_text function
    filtered_dois = extract_dois_from_text(content)

    # Try to extract PII numbers from the file name and resolve to DOI
    filename = os.path.basename(input_file)
    pii_patterns = [
        r'PII([A-Z0-9\-()]+)',  # e.g., PIIS235246422200092X.pdf
        r'1-s2\.0-([A-Z0-9\-()]+)-main',  # e.g., 1-s2.0-S2949813924000843-main.pdf
        r'([S][A-Z0-9\-()]{15,})'  # generic S-prefixed PII, at least 15 chars
    ]
    found_pii = set()
    for pattern in pii_patterns:
        matches = re.findall(pattern, filename, re.IGNORECASE)
        for m in matches:
            found_pii.add(m)
    vprint(f"PII numbers found in filename: {found_pii}")

    for pii in found_pii:
        doi = resolve_pii_to_doi(pii)
        if doi and doi not in filtered_dois:
            filtered_dois.append(doi)
            vprint(f"Resolved PII {pii} to DOI {doi}")

    # Additionally, try to extract ISBN from the file name and resolve to DOI(s)
    # This uses extract_isbns_from_text which queries Crossref for ISBN -> DOI mapping.
    try:
        vprint(f"{ICON_ISBN} Attempting to extract ISBN(s) from filename: {filename}")
        isbn_results = extract_isbns_from_text(filename)
        vprint(f"{ICON_ISBN} ISBN resolution results: {isbn_results}")
        for isbn, doi_info in isbn_results:
            if not doi_info:
                vprint(f"{ICON_ISBN} ISBN {isbn} did not resolve to a DOI")
                continue
            # doi_info can be a string DOI, None, or a list of DOIs
            doi_candidates = doi_info if isinstance(doi_info, list) else [doi_info]
            for candidate in doi_candidates:
                if not candidate:
                    continue
                # Normalize candidate and validate
                candidate = candidate.rstrip('.')
                try:
                    if is_valid_doi(candidate):
                        if candidate not in filtered_dois:
                            filtered_dois.append(candidate)
                            vprint(f"{ICON_ISBN} Resolved ISBN {isbn} -> DOI {candidate} (added)")
                        break  # stop after first valid DOI for this ISBN
                    else:
                        vprint(f"{ICON_ISBN} Candidate DOI {candidate} for ISBN {isbn} is not valid")
                except Exception as e:
                    vprint(f"{ICON_ISBN} Error validating DOI {candidate} for ISBN {isbn}: {e}")
    except Exception as e:
        vprint(f"{ICON_ISBN} Error while extracting ISBN from filename: {e}")

    # Final fallback: use filename (without extension) as a title and try Crossref title search
    if not filtered_dois:
        try:
            base_name = os.path.splitext(filename)[0]
            # Clean the base name to make a reasonable title: replace underscores/dashes/dots with spaces
            title_candidate = re.sub(r'[_\-\.\s]+', ' ', base_name).strip()
            vprint(f"{ICON_TITLE} No DOIs found yet. Trying to use filename as title: '{title_candidate}'")
            if title_candidate:
                doi_from_title = extract_doi_from_title(title_candidate)
                if doi_from_title:
                    doi_from_title = doi_from_title.rstrip('.')
                    vprint(f"{ICON_TITLE} Crossref returned DOI '{doi_from_title}' for title candidate")
                    try:
                        if is_valid_doi(doi_from_title):
                            filtered_dois.append(doi_from_title)
                            vprint(f"{ICON_TITLE} Added DOI from title fallback: {doi_from_title}")
                        else:
                            vprint(f"{ICON_TITLE} DOI from title '{doi_from_title}' did not validate as a resolvable DOI")
                    except Exception as e:
                        vprint(f"{ICON_TITLE} Error validating DOI from title '{doi_from_title}': {e}")
                else:
                    vprint(f"{ICON_TITLE} No unique DOI found for title candidate via Crossref")
        except Exception as e:
            vprint(f"{ICON_TITLE} Error during title-fallback DOI extraction: {e}")

    if not filtered_dois:
        print(f"{ICON_WARN} No valid paper DOIs found in {input_file}")
        return []

    base_name = os.path.splitext(input_file)[0]
    output_file = f"{base_name}.dois.txt"

    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            for doi in filtered_dois:
                f.write(f"{doi}\n")
        print(f"{ICON_SUCCESS} Extracted {len(filtered_dois)} paper DOIs")
        print(f"{ICON_DOI} DOIs found: {filtered_dois}")
        print(f"{ICON_OUTPUT} Written DOIs to: {output_file}")
    except Exception as e:
        print(f"{ICON_FAIL} Failed to write DOIs to output file: {e}")
        return []

    return filtered_dois

def extract_text_from_pdf(pdf_file: str, max_pages: int = None) -> str:
    """
    Extract text from a PDF file using PyMuPDF (pymupdf) if available,
    otherwise fall back to PyPDF2. Uses text blocks to intelligently
    preserve document structure including paragraphs and headings.
    Returns the extracted text as a string.
    If max_pages is specified, only extract up to the first N pages.
    """
    vprint(f"extract_text_from_pdf: Starting extraction for {pdf_file} (max_pages={max_pages})")
    try:
        import pymupdf  # PyMuPDF package
        vprint("extract_text_from_pdf: Using PyMuPDF for extraction.")
        text_chunks = []
        
        # Use context manager to ensure document is properly closed
        with pymupdf.open(pdf_file) as doc:
            num_pages = len(doc)
            vprint(f"extract_text_from_pdf: PDF has {num_pages} pages.")
            page_range = range(num_pages) if max_pages is None else range(min(num_pages, max_pages))
            
            for page_num in page_range:
                page = doc[page_num]
                vprint(f"extract_text_from_pdf: Processing page {page_num+1}/{num_pages}")
                
                # Try first with the 'text' option which preserves some layout
                try:
                    page_text = page.get_text("text")
                    if page_text and len(page_text.strip()) > 100:  # Reasonable text found
                        text_chunks.append(page_text)
                        vprint(f"extract_text_from_pdf: Extracted {len(page_text)} chars with 'text' mode from page {page_num+1}")
                        continue
                except Exception as e:
                    vprint(f"extract_text_from_pdf: Error with 'text' mode: {e}")
                
                # If 'text' mode didn't provide good results, use more detailed extraction
                try:
                    # Get all blocks with their bounding boxes using 'dict' mode
                    page_dict = page.get_text("dict")
                    blocks = page_dict.get("blocks", [])
                    vprint(f"extract_text_from_pdf: Found {len(blocks)} blocks on page {page_num+1}")
                    
                    paragraphs = []
                    for block in blocks:
                        if block.get("type") == 0:  # Text block
                            block_text = ""
                            for line in block.get("lines", []):
                                line_text = "".join(span.get("text", "") for span in line.get("spans", []))
                                if line_text.strip():
                                    if block_text:
                                        block_text += " "  # Space between lines within same block
                                    block_text += line_text
                            if block_text.strip():
                                paragraphs.append(block_text)
                    
                    # Join paragraphs with double newlines to preserve structure
                    page_text = "\n\n".join(paragraphs)
                    if page_text:
                        vprint(f"extract_text_from_pdf: Extracted {len(page_text)} chars with 'dict' mode from page {page_num+1}")
                        text_chunks.append(page_text)
                    else:
                        vprint(f"extract_text_from_pdf: No text extracted with 'dict' mode from page {page_num+1}")
                except Exception as e:
                    vprint(f"extract_text_from_pdf: Error with 'dict' mode: {e}")
                    
                    # Last resort: try 'blocks' mode which is simpler
                    try:
                        blocks_text = page.get_text("blocks")
                        if blocks_text:
                            text_chunks.append("\n\n".join(b[4] for b in blocks_text if b[4].strip()))
                            vprint(f"extract_text_from_pdf: Extracted text with 'blocks' mode from page {page_num+1}")
                    except Exception as e2:
                        vprint(f"extract_text_from_pdf: Error with 'blocks' mode: {e2}")
        
        if text_chunks:
            vprint(f"extract_text_from_pdf: Extraction complete using PyMuPDF. Total text length: {sum(len(t) for t in text_chunks)}")
            return "\n\n".join(text_chunks)
        else:
            vprint("extract_text_from_pdf: No text extracted with PyMuPDF, falling back to PyPDF2.")
    except ImportError:
        vprint("extract_text_from_pdf: PyMuPDF not installed, falling back to PyPDF2.")
    except Exception as e:
        vprint(f"extract_text_from_pdf: PyMuPDF failed to extract text: {e}. Falling back to PyPDF2.")

    # Fallback: PyPDF2
    try:
        vprint("extract_text_from_pdf: Using PyPDF2 for extraction.")
        with open(pdf_file, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            num_pages = len(reader.pages)
            vprint(f"extract_text_from_pdf: PDF has {num_pages} pages (PyPDF2).")
            page_range = range(num_pages) if max_pages is None else range(min(num_pages, max_pages))
            text_chunks = []
            for i in page_range:
                try:
                    page = reader.pages[i]
                    page_text = page.extract_text()
                    if page_text:
                        vprint(f"extract_text_from_pdf: Extracted {len(page_text)} characters from page {i+1} (PyPDF2)")
                        text_chunks.append(page_text)
                    else:
                        vprint(f"extract_text_from_pdf: No text extracted from page {i+1} (PyPDF2)")
                except Exception as e:
                    vprint(f"extract_text_from_pdf: Exception extracting page {i+1} (PyPDF2): {e}")
                    continue
        total_len = sum(len(t) for t in text_chunks)
        vprint(f"extract_text_from_pdf: Extraction complete using PyPDF2. Total text length: {total_len}")
        return "\n".join(text_chunks)
    except Exception as e:
        vprint(f"extract_text_from_pdf: PyPDF2 failed to extract text: {e}")
        return ""

def extract_doi_from_pdf(pdf_file: str) -> str:
    """
    Extract the most likely DOI found in a PDF file.
    If multiple DOIs are found, fetch the paper title from Crossref for each DOI,
    and check if a similar title exists in the first page of the PDF.
    Select the DOI whose title matches; if none match, select the first found.
    Also tries to extract Elsevier PII numbers from the file name and resolve them to DOIs.
    Only considers the first five pages of the PDF.
    Keeps newlines intact when extracting text from PDF pages.
    Prints more details for debug in verbose mode.

    Fallback: if no DOI can be extracted from text or PII, try to extract ISBN(s)
    from the file name and resolve them to DOI(s) via Crossref (using extract_isbns_from_text).
    """
    try:
        vprint(f"extract_doi_from_pdf: Extracting text from PDF (first 5 pages): {pdf_file}")
        text = extract_text_from_pdf(pdf_file, max_pages=5)
        if not text:
            print(f"extract_doi_from_pdf: No text could be extracted from PDF: {pdf_file}")
            text = ""
        vprint(f"extract_doi_from_pdf: Extracting text from PDF (first page only): {pdf_file}")
        first_page_text = extract_text_from_pdf(pdf_file, max_pages=1) or ""
        vprint(f"extract_doi_from_pdf: First page text length: {len(first_page_text)}")
    except Exception as e:
        print(f"extract_doi_from_pdf: Failed to extract text from PDF file: {e}")
        return None

    vprint(f"extract_doi_from_pdf: Extracting DOIs from PDF text...")
    dois = extract_dois_from_text(text) if text else []
    vprint(f"extract_doi_from_pdf: DOIs found in PDF: {dois}")

    # Try to extract PII numbers from the file name and resolve to DOI
    filename = os.path.basename(pdf_file)
    pii_patterns = [
        r'PII([A-Z0-9\-()]+)',  # e.g., PIIS235246422200092X.pdf
        r'1-s2\.0-([A-Z0-9\-()]+)-main',  # e.g., 1-s2.0-S2949813924000843-main.pdf
        r'([S][A-Z0-9\-()]{15,})'  # generic S-prefixed PII, at least 15 chars
    ]
    found_pii = set()
    for pattern in pii_patterns:
        matches = re.findall(pattern, filename, re.IGNORECASE)
        for m in matches:
            found_pii.add(m)
    vprint(f"extract_doi_from_pdf: PII numbers found in filename: {found_pii}")

    for pii in found_pii:
        doi_from_pii = resolve_pii_to_doi(pii)
        vprint(f"extract_doi_from_pdf: resolve_pii_to_doi({pii}) -> {doi_from_pii}")
        if doi_from_pii and doi_from_pii not in dois:
            vprint(f"extract_doi_from_pdf: Resolved PII {pii} to DOI {doi_from_pii}, inserting at front of DOI list")
            dois.insert(0, doi_from_pii)  # Prefer DOI from PII

    # If no DOIs found from text or PII, try ISBN extraction from filename as a fallback
    if not dois:
        vprint("extract_doi_from_pdf: No DOIs found in text or via PII, attempting ISBN extraction from filename...")
        try:
            isbn_results = extract_isbns_from_text(filename)
            vprint(f"extract_doi_from_pdf: ISBN extraction results: {isbn_results}")
            if isbn_results:
                # isbn_results is a list of (isbn, doi_info) tuples
                for isbn, doi_info in isbn_results:
                    if not doi_info:
                        vprint(f"extract_doi_from_pdf: ISBN {isbn} did not resolve to a DOI")
                        continue
                    candidates = doi_info if isinstance(doi_info, list) else [doi_info]
                    for candidate in candidates:
                        if not candidate:
                            continue
                        candidate = candidate.rstrip('.')
                        vprint(f"extract_doi_from_pdf: Validating candidate DOI from ISBN {isbn}: {candidate}")
                        try:
                            if is_valid_doi(candidate):
                                vprint(f"extract_doi_from_pdf: Candidate DOI {candidate} validated, returning it.")
                                return candidate
                            else:
                                vprint(f"extract_doi_from_pdf: Candidate DOI {candidate} is not valid.")
                        except Exception as e:
                            vprint(f"extract_doi_from_pdf: Error validating DOI {candidate}: {e}")
                vprint("extract_doi_from_pdf: No valid DOI found from ISBN extraction.")
            else:
                vprint("extract_doi_from_pdf: No ISBNs found in filename.")
        except Exception as e:
            vprint(f"extract_doi_from_pdf: Error during ISBN extraction from filename: {e}")

    if not dois:
        vprint("extract_doi_from_pdf: No DOIs found after all fallbacks.")
        return None

    if len(dois) == 1:
        vprint(f"extract_doi_from_pdf: Only one DOI found, returning: {dois[0]}")
        return dois[0]

    # If multiple DOIs, try to match Crossref title with first page text
    def normalize(s):
        return re.sub(r'\W+', '', s or '').lower()

    for doi in dois:
        vprint(f"extract_doi_from_pdf: Fetching Crossref data for DOI: {doi}")
        try:
            crossref_data = fetch_crossref_data(doi)
        except ValueError as exc:
            vprint(f"extract_doi_from_pdf: Skipping Crossref lookup for {doi} due to missing email: {exc}")
            crossref_data = None
        title = None
        if crossref_data:
            title_list = crossref_data.get("title")
            if isinstance(title_list, list) and title_list:
                title = title_list[0]
            elif isinstance(title_list, str):
                title = title_list
        vprint(f"extract_doi_from_pdf: Crossref title for DOI {doi}: {title}")
        if title:
            norm_title = normalize(title)
            norm_first_page = normalize(first_page_text)
            vprint(f"extract_doi_from_pdf: Normalized Crossref title: {norm_title}")
            vprint(f"extract_doi_from_pdf: Normalized first page text (first 100 chars): {norm_first_page[:100]}...")
            if norm_title and norm_title in norm_first_page:
                vprint(f"extract_doi_from_pdf: Title match found for DOI {doi}, returning this DOI.")
                return doi

    vprint(f"extract_doi_from_pdf: No title match found, returning first DOI: {dois[0]}")
    return dois[0]

async def search_documents(query: str, limit: int = 1):
    """
    Search for documents using StcGeck, Nexus bot, Crossref, and DOI REST API in order.
    Build a StcGeck-style document with all fields empty, and iteratively fill fields
    by searching each source in order. Return up to the requested limit of results.
    Always tries all sources before returning results.
    Prints important search steps with icons for better readability.
    """
    ICON_SEARCH = "🔎"
    ICON_SUCCESS = "✅"
    ICON_WARNING = "⚠️"
    ICON_ERROR = "❌"
    ICON_STEP = "➡️"
    ICON_SOURCE = {
        "stcgeck": "🪐",
        "nexus": "🤖",
        "crossref": "🌐",
        "doi_rest": "🔗"
    }

    vprint(f"{ICON_SEARCH} Searching for: {query} (limit={limit})")

    # Helper: create empty stcgeck-style doc
    def empty_doc():
        return {
            'id': None,
            'title': None,
            'authors': [],
            'metadata': {},
            'uris': [],
            'issued_at': None,
            'oa_status': None
        }

    # Helper: merge fields from src into dst (only fill empty fields)
    def merge_doc(dst, src):
        if not src:
            return
        if dst['id'] is None and src.get('id'):
            dst['id'] = src.get('id')
        if (not dst['title'] or dst['title'] == 'N/A') and src.get('title'):
            dst['title'] = src.get('title')
        if not dst['authors'] and src.get('authors'):
            dst['authors'] = src.get('authors')
        if src.get('metadata'):
            for k, v in src['metadata'].items():
                if k not in dst['metadata'] or not dst['metadata'][k]:
                    dst['metadata'][k] = v
        if not dst['uris'] and src.get('uris'):
            dst['uris'] = src.get('uris')
        if not dst['issued_at'] and src.get('issued_at'):
            dst['issued_at'] = src.get('issued_at')
        if dst['oa_status'] is None and src.get('oa_status') is not None:
            dst['oa_status'] = src.get('oa_status')

    # Try each source, collect up to limit unique DOIs
    collected = {}

    # 1. StcGeck
    print(f"{ICON_STEP} {ICON_SOURCE['stcgeck']} Searching with StcGeck...")
    try:
        vprint("Trying StcGeck search...")
        geck = StcGeck(
            ipfs_http_base_url="http://127.0.0.1:8080",
            timeout=300,
        )
        try:
            await geck.start()
            summa_client = geck.get_summa_client()
            if query.lower().startswith("10."):
                search_query = {"term": {"field": "uris", "value": f"doi:{query}"}}
                vprint(f"StcGeck: Searching by DOI: {query}")
            else:
                search_query = {"match": {"value": f"{query}"}}
                vprint(f"StcGeck: Searching by keyword: {query}")

            search_response = await summa_client.search(
                {
                    "index_alias": "stc",
                    "query": search_query,
                    "collectors": [{"top_docs": {"limit": limit}}],
                    "is_fieldnorms_scoring_enabled": False,
                }
            )
            stc_results = search_response.collector_outputs[0].documents.scored_documents
            print(f"{ICON_SUCCESS} StcGeck returned {len(stc_results)} results.")
            for scored in stc_results:
                doc = json.loads(scored.document)
                doi = None
                for uri in doc.get('uris', []):
                    if uri.startswith('doi:'):
                        doi = uri[4:]
                        break
                key = doi or doc.get('id') or doc.get('title')
                if key and key not in collected:
                    base = empty_doc()
                    merge_doc(base, doc)
                    collected[key] = base
        finally:
            await geck.stop()
    except Exception as e:
        print(f"{ICON_ERROR} StcGeck failed")
        vprint(f"StcGeck failed: {e}")

    # 2. Nexus bot
    print(f"{ICON_STEP} {ICON_SOURCE['nexus']} Searching with Nexus bot...")
    try:
        vprint("Trying Nexus bot search...")
        nexus_results = await search_with_nexus_bot(query, limit)
        print(f"{ICON_SUCCESS} Nexus bot returned {len(nexus_results)} results.")
        for scored in nexus_results:
            doc = json.loads(scored.document)
            doi = None
            for uri in doc.get('uris', []):
                if uri.startswith('doi:'):
                    doi = uri[4:]
                    break
            key = doi or doc.get('id') or doc.get('title')
            if key in collected:
                merge_doc(collected[key], doc)
            elif key:
                base = empty_doc()
                merge_doc(base, doc)
                collected[key] = base
    except Exception as e:
        print(f"{ICON_ERROR} Nexus bot failed: {e}")
        vprint(f"Nexus bot failed: {e}")

    # 3. Crossref
    print(f"{ICON_STEP} {ICON_SOURCE['crossref']} Searching with Crossref...")
    try:
        vprint("Trying Crossref search...")
        crossref_results = await search_with_crossref(query, limit)
        print(f"{ICON_SUCCESS} Crossref returned {len(crossref_results)} results.")
        for scored in crossref_results:
            doc = json.loads(scored.document)
            doi = None
            for uri in doc.get('uris', []):
                if uri.startswith('doi:'):
                    doi = uri[4:]
                    break
            key = doi or doc.get('id') or doc.get('title')
            if key in collected:
                merge_doc(collected[key], doc)
            elif key:
                base = empty_doc()
                merge_doc(base, doc)
                collected[key] = base
    except Exception as e:
        print(f"{ICON_ERROR} Crossref failed: {e}")
        vprint(f"Crossref failed: {e}")

    # 4. DOI REST API
    print(f"{ICON_STEP} {ICON_SOURCE['doi_rest']} Searching with DOI REST API...")
    try:
        vprint("Trying DOI REST API search...")
        doi_rest_results = await search_with_doi_rest_api(query, limit)
        print(f"{ICON_SUCCESS} DOI REST API returned {len(doi_rest_results)} results.")
        for scored in doi_rest_results:
            doc = json.loads(scored.document)
            doi = None
            for uri in doc.get('uris', []):
                if uri.startswith('doi:'):
                    doi = uri[4:]
                    break
            key = doi or doc.get('id') or doc.get('title')
            if key in collected:
                merge_doc(collected[key], doc)
            elif key:
                base = empty_doc()
                merge_doc(base, doc)
                collected[key] = base
    except Exception as e:
        print(f"{ICON_ERROR} DOI REST API failed: {e}")
        vprint(f"DOI REST API failed: {e}")

    if not collected:
        print(f"{ICON_WARNING} No results found from any source.")
        vprint("No results found from any source.")
        return []

    print(f"{ICON_SUCCESS} Search complete. Returning {min(len(collected), limit)} result(s).")
    # Wrap as ScoredDocument-like objects
    return [type('ScoredDocument', (), {'document': json.dumps(doc)})() for doc in list(collected.values())[:limit]]

async def search_with_nexus_bot(query: str, limit: int = 1):
    """
    Search for documents using the Nexus bot (functions imported from .nexus).
    Returns a list of ScoredDocument-like objects with a .document JSON string.
    Tries first without proxy, then with proxy if it fails.
    """
    try:
        TG_API_ID, TG_API_HASH, PHONE, BOT_USERNAME = await nexus.load_credentials_from_file(nexus.CREDENTIALS_FILE, print_result=False)
        proxies = [None, nexus.DEFAULT_PROXY_FILE]
        for proxy in proxies:
            try:
                results = await nexus.send_message_to_bot(
                    api_id=TG_API_ID,
                    api_hash=TG_API_HASH,
                    phone_number=PHONE,
                    bot_username=BOT_USERNAME,
                    message=query,
                    session_file=nexus.SESSION_FILE,
                    proxy=proxy,
                    limit=limit
                )
                # If results is a list of dicts, convert each to stc format
                docs = []
                if isinstance(results, list):
                    for item in results:
                        docs.extend(convert_nexus_to_stc_format(item))
                elif isinstance(results, dict):
                    docs = convert_nexus_to_stc_format(results)
                else:
                    docs = []
                # Wrap as ScoredDocument-like objects
                return [type('ScoredDocument', (), {'document': json.dumps(doc)})() for doc in docs]
            except Exception as e:
                vprint(f"Nexus bot search failed with proxy={proxy}: {e}")
                # Try next proxy if available
                continue
        return []
    except Exception as e:
        vprint(f"Nexus bot search failed: {e}")
        return []

def convert_nexus_to_stc_format(nexus_item):
    """
    Convert a Nexus bot result (raw dict) to a list of StcGeck compatible documents.
    Handles both search (multiple results) and DOI (single result) formats.
    Returns a list of dicts (one per result).
    """
    # If this is a raw result, extract the 'bot_reply'->'text'
    if "bot_reply" in nexus_item and "text" in nexus_item["bot_reply"]:
        text = nexus_item["bot_reply"]["text"]
    elif "text" in nexus_item:
        text = nexus_item["text"]
    else:
        return []

    # If this is a DOI query, the text starts with a marker emoji and contains "**DOI:**" or "**DOI:** [doi](...)"
    if "**DOI:**" in text:
        # Try to extract fields
        title = None
        authors = []
        journal = None
        volume = None
        issue = None
        first_page = None
        last_page = None
        doi = None
        year = None
        issued_at = None
        nexus_id = None

        # Title: after marker emoji + "**", before "**"
        title_match = re.search(r"(?:\[\d+\]\s*)?([🔬🔖📚])\s*\*\*(.*?)\*\*", text)
        if title_match:
            title = title_match.group(2).strip()
        # Authors: after title, before "in __" or "\n"
        authors_match = re.search(r"\*\*.*\*\*\s*\n([^\n_]+)", text)
        if authors_match:
            authors_str = authors_match.group(1).strip()
            # Remove "et al"
            authors_str = authors_str.replace("et al", "")
            # Remove "in ..." if present
            authors_str = re.sub(r"\s+in\s+.*", "", authors_str)
            # Split by ";" or "," or " and "
            for a in re.split(r";|,| and ", authors_str):
                name = a.strip()
                if name:
                    names = name.split()
                    if len(names) > 1:
                        authors.append({'given': ' '.join(names[:-1]), 'family': names[-1]})
                    else:
                        authors.append({'given': '', 'family': name})
        # Journal: in __...__
        journal_match = re.search(r"in __([^_]+)__", text)
        if journal_match:
            journal = journal_match.group(1).strip()
        # DOI: after "**DOI:** [" or "**DOI:** "
        doi_match = re.search(r"\*\*DOI:\*\*\s*(?:\[)?([^\s\]\n]+)", text)
        if doi_match:
            doi = doi_match.group(1).strip()
        # Year: look for (YYYY-MM) or (YYYY) after title, or at end after "|"
        year_match = re.search(r"\((\d{4})(?:-\d{2})?\)", text)
        if not year_match:
            year_match = re.search(r"\|\s*(\d{4})(?:-\d{2})?\s*$", text)
        if not year_match:
            year_match = re.search(r"\b(19|20)\d{2}\b", text)
        if year_match:
            year = year_match.group(1)
            try:
                issued_at = int(datetime(int(year), 1, 1).timestamp())
            except Exception:
                issued_at = None
        # Compose metadata
        metadata = {}
        if journal:
            metadata['container_title'] = journal
        # Publisher: after "**Publisher:** [name]"
        publisher_match = re.search(r"\*\*Publisher:\*\*\s*\[([^\]]+)\]", text)
        if publisher_match:
            metadata['publisher'] = publisher_match.group(1).strip()
        # Extract Nexus ID from LibSTC.cc link: after nid: and before )
        nexus_id_match = re.search(r"LibSTC\.cc\]\([^)]+nid:([a-z0-9]+)\)", text, re.IGNORECASE)
        if nexus_id_match:
            nexus_id = nexus_id_match.group(1)
        # Compose doc
        doc = {
            'id': nexus_id,
            'title': title or "N/A",
            'authors': authors,
            'metadata': metadata,
            'uris': [f"doi:{doi}"] if doi else [],
            'issued_at': issued_at,
            'oa_status': None
        }
        return [doc]

    # Otherwise, treat as search results (multiple entries)
    # Split into entries by the marker emojis, possibly preceded by [number]
    marker_pattern = r"(?:\[\d+\]\s*)?[🔬🔖📚]"
    # Find all marker positions
    marker_matches = list(re.finditer(marker_pattern, text))
    docs = []
    if not marker_matches:
        return docs
    for idx, match in enumerate(marker_matches):
        start = match.start()
        end = marker_matches[idx + 1].start() if idx + 1 < len(marker_matches) else len(text)
        entry = text[start:end].strip()
        if not entry:
            continue
        # Title: after "**<P>" or "**", before "**"
        title_match = re.search(r"\*\*(?:<P>)?\s*(.*?)\*\*", entry)
        title = title_match.group(1).strip() if title_match else "N/A"

        # Authors: after title, before "__" or "\n"
        authors = []
        authors_match = re.search(r"\*\*.*\*\*\s*\n([^\n_]+)", entry)
        if authors_match:
            # Try to split by "et al", "and", or comma
            authors_str = authors_match.group(1).strip()
            # Remove "in ..." if present
            authors_str = re.sub(r"\s+in\s+.*", "", authors_str)
            # Remove "et al"
            authors_str = authors_str.replace("et al", "")
            # Split by "and" or ","
            for a in re.split(r",| and ", authors_str):
                name = a.strip()
                if name:
                    names = name.split()
                    if len(names) > 1:
                        authors.append({'given': ' '.join(names[:-1]), 'family': names[-1]})
                    else:
                        authors.append({'given': '', 'family': name})

        # Journal/metadata: look for "in __...__"
        journal = None
        journal_match = re.search(r"in __([^_]+)__", entry)
        if journal_match:
            journal = journal_match.group(1).strip()

        # Volume/issue/pages: look for "__vol. X__ __(Y)__ pp. Z"
        volume = None
        issue = None
        first_page = None
        last_page = None
        volume_match = re.search(r"__vol\. ([^_]+)__", entry)
        if volume_match:
            volume = volume_match.group(1).strip()
        issue_match = re.search(r"__\(([^)]+)\)__", entry)
        if issue_match:
            issue = issue_match.group(1).strip()
        pages_match = re.search(r"pp\. ([\d\-]+)", entry)
        if pages_match:
            pages = pages_match.group(1).strip()
            if '-' in pages:
                first_page, last_page = pages.split('-', 1)
            else:
                first_page = pages

        # DOI: look for "doi.org" link
        doi = None
        doi_match = re.search(r"https?://doi\.org/([^\s|)]+)", entry)
        if doi_match:
            doi = doi_match.group(1).strip()

        # Year: look for 4-digit year at end or after "|"
        year = None
        year_match = re.search(r"\|\s*(\d{4})(?:-\d{2})?\s*$", entry)
        if not year_match:
            year_match = re.search(r"\b(19|20)\d{2}\b", entry)
        if year_match:
            year = year_match.group(1)

        # Compose metadata
        metadata = {}
        if journal:
            metadata['container_title'] = journal
        if volume:
            metadata['volume'] = volume
        if issue:
            metadata['issue'] = issue
        if first_page:
            metadata['first_page'] = first_page
        if last_page:
            metadata['last_page'] = last_page

        # issued_at: try to build from year
        issued_at = None
        try:
            if year:
                issued_at = int(datetime(int(year), 1, 1).timestamp())
        except Exception:
            pass

        # OA status: not available from Nexus, set None
        doc = {
            'id': None,
            'title': title,
            'authors': authors,
            'metadata': metadata,
            'uris': [f"doi:{doi}"] if doi else [],
            'issued_at': issued_at,
            'oa_status': None
        }
        docs.append(doc)
    return docs

async def search_with_crossref(query: str, limit: int = 1):
    try:
        works = Works()
        
        if query.lower().startswith("10."):
            # Search by DOI
            vprint(f"Searching Crossref by DOI: {query}")
            result = works.doi(query)
            if result:
                # Convert Crossref result to compatible format
                crossref_doc = convert_crossref_to_stc_format(result)
                # Check OA status using Unpaywall
                doi = result.get('DOI')
                if doi:
                    crossref_doc['oa_status'] = await is_open_access_unpaywall(doi)
                return [type('ScoredDocument', (), {'document': json.dumps(crossref_doc)})()]
            else:
                return []
        else:
            # Search by keyword
            vprint(f"Searching Crossref by keyword: {query}")
            results = works.query(query).select(['DOI', 'title', 'author', 'published-print', 
                                                'container-title', 'volume', 'issue', 'page', 
                                                'publisher', 'ISSN']).sort('relevance').order('desc')
            
            crossref_results = []
            count = 0
            for item in results:
                if count >= limit:
                    break
                crossref_doc = convert_crossref_to_stc_format(item)
                # Check OA status using Unpaywall
                doi = item.get('DOI')
                if doi:
                    crossref_doc['oa_status'] = await is_open_access_unpaywall(doi)
                crossref_results.append(type('ScoredDocument', (), {'document': json.dumps(crossref_doc)})())
                count += 1
            
            vprint(f"Found {len(crossref_results)} results from Crossref for query: {query}")
            return crossref_results
    except ImportError:
        print("crossref-commons package not installed. Please install with: pip install crossref-commons")
        return []
    except Exception as e:
        vprint(f"Crossref search failed: {e}")
        return []

def convert_crossref_to_stc_format(crossref_item):
    """Convert Crossref API result to StcGeck compatible format"""
    doc = {
        'id': None,  # Crossref doesn't provide StcGeck ID
        'title': crossref_item.get('title', ['N/A'])[0] if crossref_item.get('title') else 'N/A',
        'authors': [],
        'metadata': {},
        'uris': [],
        'issued_at': None
    }

    # Convert authors
    if 'author' in crossref_item:
        for author in crossref_item['author']:
            doc['authors'].append({
                'given': author.get('given', ''),
                'family': author.get('family', '')
            })

    # Add DOI URI
    doi = crossref_item.get('DOI')
    if doi:
        doc['uris'].append(f"doi:{doi}")

    # Convert metadata
    metadata = doc['metadata']
    if 'container-title' in crossref_item and crossref_item['container-title']:
        metadata['container_title'] = crossref_item['container-title'][0]
    if 'volume' in crossref_item:
        metadata['volume'] = crossref_item['volume']
    if 'issue' in crossref_item:
        metadata['issue'] = crossref_item['issue']
    if 'page' in crossref_item:
        pages = crossref_item['page'].split('-')
        if len(pages) >= 1:
            metadata['first_page'] = pages[0]
        if len(pages) >= 2:
            metadata['last_page'] = pages[1]
    if 'publisher' in crossref_item:
        metadata['publisher'] = crossref_item['publisher']
    if 'ISSN' in crossref_item:
        metadata['issns'] = crossref_item['ISSN']

    # Convert issued date
    if 'published-print' in crossref_item or 'published-online' in crossref_item:
        date_parts = (crossref_item.get('published-print') or crossref_item.get('published-online'))['date-parts'][0]
        if date_parts:
            try:
                year = date_parts[0] if len(date_parts) > 0 else 1970
                month = date_parts[1] if len(date_parts) > 1 else 1
                day = date_parts[2] if len(date_parts) > 2 else 1
                doc['issued_at'] = int(datetime(year, month, day).timestamp())
            except Exception:
                pass

    # OA status is set in the search function, do not check here
    doc['oa_status'] = crossref_item.get('oa_status', None)

    return doc

def fetch_doi_rest_api(doi: str, params: dict = None) -> dict:
    """
    Fetch DOI metadata using the DOI Proxy REST API.
    Returns the parsed JSON response, or None if not found/error.
    """
    base_url = f"https://doi.org/api/handles/{doi}"
    if params:
        query = "&".join(f"{k}={quote_plus(str(v))}" for k, v in params.items())
        url = f"{base_url}?{query}"
    else:
        url = base_url
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json",
        "Referer": "https://doi.org/",
        "DNT": "1",
    }
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        vprint(f"Error fetching DOI REST API for {doi}: {e}")
        return None

def convert_doi_rest_to_stc_format(rest_data: dict) -> dict:
    """
    Convert DOI REST API response to StcGeck compatible document format.
    Only fills fields available in the REST API response.
    Handles cases where 'DESCRIPTION', 'EMAIL', etc. may not be present.
    """
    doc = {
        'id': None,
        'title': None,
        'authors': [],
        'metadata': {},
        'uris': [],
        'issued_at': None,
        'oa_status': None
    }
    if not rest_data or rest_data.get("responseCode") != 1:
        return doc
    handle = rest_data.get("handle")
    if handle:
        doc['id'] = handle
        doc['uris'].append(f"doi:{handle}")
    elements = rest_data.get("values", [])
    url = None
    description = None
    email = None
    timestamp = None
    for el in elements:
        typ = el.get("type", "").upper()
        data = el.get("data", {})
        fmt = data.get("format")
        val = data.get("value")
        # URL field
        if typ == "URL" and fmt == "string" and isinstance(val, str):
            url = val
        # DESCRIPTION field
        elif typ == "DESCRIPTION" and fmt == "string" and isinstance(val, str):
            description = val
        # EMAIL field
        elif typ == "EMAIL" and fmt == "string" and isinstance(val, str):
            email = val
        # Try to get timestamp from any element
        if not timestamp and el.get("timestamp"):
            timestamp = el.get("timestamp")
    if url:
        doc['metadata']['url'] = url
    if description:
        doc['title'] = description
    if email:
        doc['metadata']['email'] = email
    if timestamp:
        try:
            # DOI REST API timestamp is usually ISO format with Z
            dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            doc['issued_at'] = int(dt.timestamp())
        except Exception:
            pass
    return doc

async def search_with_doi_rest_api(query: str, limit: int = 1):
    """
    Search for a DOI using the DOI REST API and convert to StcGeck format.
    Returns a list of ScoredDocument-like objects.
    """
    if not query.lower().startswith("10."):
        return []
    rest_data = fetch_doi_rest_api(query, params={"pretty": "true"})
    doc = convert_doi_rest_to_stc_format(rest_data)
    if doc and doc.get("uris"):
        return [type('ScoredDocument', (), {'document': json.dumps(doc)})()]
    return []

def format_reference(document):
    title = document.get('title', 'N/A')
    authors = document.get('authors', [])
    if authors:
        formatted_authors = ', '.join(
            f"{a.get('given', '')} {a.get('family', '')}".strip() for a in authors
        )
    else:
        formatted_authors = 'N/A'
    metadata = document.get('metadata', {})
    journal = metadata.get('container_title', 'N/A')
    volume = metadata.get('volume', None)
    issue = metadata.get('issue', None)
    first_page = metadata.get('first_page', None)
    last_page = metadata.get('last_page', None)
    issued_at = document.get('issued_at', None)
    if issued_at:
        try:
            year = datetime.utcfromtimestamp(int(issued_at)).year
        except Exception:
            year = 'N/A'
    else:
        year = 'N/A'
    publisher = metadata.get('publisher', 'N/A')
    issns = metadata.get('issns', [])
    issn_str = ', '.join(issns) if issns else 'N/A'
    doi_uri = next((uri for uri in document.get("uris", []) if uri.startswith("doi:")), None)
    doi = doi_uri.split("doi:")[1] if doi_uri else 'N/A'
    oa_status = document.get('oa_status', None)
    if oa_status is True:
        oa_str = "Open Access"
    elif oa_status is False:
        oa_str = "Closed Access"
    else:
        oa_str = "OA status unknown"
    ref = f"{formatted_authors} ({year}). {title}. {journal}"
    if volume:
        ref += f", {volume}"
    if issue:
        ref += f"({issue})"
    if first_page and last_page:
        ref += f", {first_page}-{last_page}"
    elif first_page:
        ref += f", {first_page}"
    if publisher and publisher != 'N/A':
        ref += f". {publisher}"
    if issn_str and issn_str != 'N/A':
        ref += f". ISSN: {issn_str}"
    if doi and doi != 'N/A':
        ref += f". https://doi.org/{doi}"
    ref += f". [{oa_str}]"
    return ref

async def search_and_print(query: str, limit: int):
    vprint(f"Starting search_and_print for query: {query}, limit: {limit}")
    results = await search_documents(query, limit)
    if not results:
        print("No results found.")
        return

    for idx, scored_document in enumerate(results, 1):
        document = json.loads(scored_document.document)
        print(f"Result #{idx}")
        print(format_reference(document))
        if VERBOSE:
            print("Full document JSON:")
            print(json.dumps(document, indent=2))
        print('-----')

def is_elsevier_doi(doi: str) -> bool:
    """
    Check if a DOI is published by Elsevier.
    First, try to fetch metadata from DOI REST API and check if publisher is Elsevier.
    If not available, fallback to prefix/domain check.
    Returns True if the DOI is published by Elsevier.
    """
    # Try DOI REST API first
    try:
        rest_data = fetch_doi_rest_api(doi)
        if rest_data and rest_data.get("responseCode") == 1:
            values = rest_data.get("values", [])
            publisher = None
            for el in values:
                typ = el.get("type", "").upper()
                val = el.get("data", {}).get("value", "")
                if typ == "PUBLISHER" and isinstance(val, str):
                    publisher = val.lower()
                    break
            if publisher and "elsevier" in publisher:
                return True
    except Exception:
        pass

    # Fallback: prefix/domain check
    elsevier_prefixes = [
        "10.1016",  # Elsevier
        "10.1017",  # Cambridge/Cell Press (sometimes)
        "10.1018",  # Elsevier (rare)
        "10.1019",  # Elsevier (rare)
        "10.1010",  # Elsevier (rare)
        "10.1015",  # Elsevier (rare)
        "10.1012",  # Elsevier (rare)
        "10.1013",  # Elsevier (rare)
        "10.1014",  # Elsevier (rare)
        "10.1011",  # Elsevier (rare)
    ]
    doi = doi.lower().strip()
    if not any(doi.startswith(prefix) for prefix in elsevier_prefixes):
        return False

    try:
        url = f"https://doi.org/{doi}"
        resp = requests.head(url, allow_redirects=True, timeout=10)
        final_url = resp.url.lower()
        elsevier_domains = [
            "elsevier.com",
            "sciencedirect.com",
            "cell.com",
            "thelancet.com",
            "journals.elsevierhealth.com",
        ]
        if any(domain in final_url for domain in elsevier_domains):
            return True
    except Exception:
        pass

    return False

async def download_elsevier_pdf_by_doi(
    doi: str,
    download_folder: str = DEFAULT_DOWNLOAD_FOLDER,
    api_key: str | None = None,
):
    """
    Try to download a PDF from Elsevier Full-Text API using DOI.
    Returns True if successful, else False.
    """
    if not doi:
        return False
        
    safe_doi = doi.replace('/', '_')
    
    # First get metadata to check page count
    metadata_url = f"https://api.elsevier.com/content/article/doi/{quote_plus(doi)}"
    active_api_key = api_key or configuration.ELSEVIER_API_KEY

    metadata_headers = {
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0",
        "X-ELS-APIKey": active_api_key,
    }
    
    expected_pages = None
    try:
        metadata_resp = requests.get(metadata_url, headers=metadata_headers, timeout=15)
        if metadata_resp.status_code == 200:
            metadata = metadata_resp.json()
            # Extract page count from various possible fields
            full_text = metadata.get("full-text-retrieval-response", {})
            coredata = full_text.get("coredata", {})
            
            # Try different page count fields
            page_count = (
                coredata.get("pageRange") or 
                coredata.get("page-count") or 
                coredata.get("prism:pageRange")
            )
            
            if page_count:
                # Handle page ranges like "123-145" or just page counts
                if isinstance(page_count, str) and '-' in page_count:
                    try:
                        start, end = page_count.split('-')
                        expected_pages = int(end) - int(start) + 1
                    except (ValueError, IndexError):
                        pass
                elif isinstance(page_count, (int, str)):
                    try:
                        expected_pages = int(page_count)
                    except ValueError:
                        pass
                        
            vprint(f"Expected page count from Elsevier metadata: {expected_pages}")
    except Exception as e:
        vprint(f"Error fetching Elsevier metadata for DOI {doi}: {e}")

    # Now download the PDF
    api_url = f"https://api.elsevier.com/content/article/doi/{quote_plus(doi)}?httpAccept=application/pdf"

    # Check if DOI is open access
    is_oa = await is_open_access_unpaywall(doi)
    
    headers = {
        "Accept": "application/pdf",
        "User-Agent": "Mozilla/5.0",
        "X-ELS-APIKey": active_api_key,
    }
    try:
        resp = requests.get(api_url, headers=headers, timeout=20, allow_redirects=True)
        if resp.status_code == 200 and resp.headers.get("Content-Type", "").startswith("application/pdf"):
            # Name file based on OA status
            if is_oa:
                filename = f"{safe_doi}_unpaywall_elsevier.pdf"
            else:
                filename = f"{safe_doi}_elsevier.pdf"
                
            filepath = os.path.join(download_folder, filename)
            
            # Write PDF content to a temporary file first for verification
            temp_filepath = filepath + ".tmp"
            with open(temp_filepath, "wb") as f:
                f.write(resp.content)
            
            # Verify PDF page count if we have expected pages
            if expected_pages:
                try:
                    with open(temp_filepath, "rb") as pdf_file:
                        pdf_reader = PyPDF2.PdfReader(pdf_file)
                        actual_pages = len(pdf_reader.pages)
                        
                    vprint(f"PDF verification - Expected: {expected_pages}, Actual: {actual_pages}")
                    
                    if actual_pages != expected_pages:
                        print(f"Error: Downloaded PDF has {actual_pages} pages but expected {expected_pages} pages")
                        print(f"This indicates an incomplete or invalid PDF download")
                        os.remove(temp_filepath)  # Remove invalid PDF
                        return False
                    else:
                        vprint(f"PDF page count verified: {actual_pages} pages")
                        
                except ImportError:
                    vprint("PyPDF2 not installed, cannot verify page count. Install with: pip install PyPDF2")
                    # Without verification, we'll assume the PDF is valid
                except Exception as e:
                    vprint(f"Error verifying PDF: {e}")
                    print(f"Error: PDF verification failed, download considered invalid")
                    os.remove(temp_filepath)  # Remove potentially invalid PDF
                    return False
            
            # If we reach here, PDF is valid - move temp file to final location
            os.rename(temp_filepath, filepath)
            print(f"Downloaded PDF from Elsevier Full-Text API: {filepath}")
            return True
        elif resp.status_code == 403:
            print("Access to Elsevier Full-Text API is forbidden. You may need an API key. See https://dev.elsevier.com/")
        else:
            vprint(f"Elsevier API did not return PDF for DOI {doi} (status {resp.status_code})")
    except Exception as e:
        vprint(f"Error downloading PDF from Elsevier API for DOI {doi}: {e}")
    return False

def is_wiley_doi(doi: str) -> bool:
    """
    Check if a DOI is published by Wiley.
    First, try to fetch metadata from DOI REST API and check if publisher is Wiley.
    If not available, fallback to prefix/domain check.
    Returns True if the DOI is published by Wiley.
    """
    # Try DOI REST API first
    try:
        rest_data = fetch_doi_rest_api(doi)
        if rest_data and rest_data.get("responseCode") == 1:
            values = rest_data.get("values", [])
            publisher = None
            for el in values:
                typ = el.get("type", "").upper()
                val = el.get("data", {}).get("value", "")
                if typ == "PUBLISHER" and isinstance(val, str):
                    publisher = val.lower()
                    break
            if publisher and "wiley" in publisher:
                return True
    except Exception:
        pass

    # Fallback: prefix/domain check
    wiley_prefixes = [
        "10.1002",  # Wiley
        "10.1111",  # Wiley
        "10.1007",  # Springer, but some Wiley journals
        "10.1046",  # Wiley (legacy)
        "10.15252", # EMBO Press (Wiley)
        "10.22541", # Authorea (Wiley)
    ]
    doi = doi.lower().strip()
    if not any(doi.startswith(prefix) for prefix in wiley_prefixes):
        return False

    try:
        url = f"https://doi.org/{doi}"
        resp = requests.head(url, allow_redirects=True, timeout=10)
        final_url = resp.url.lower()
        wiley_domains = [
            "wiley.com",
            "onlinelibrary.wiley.com",
            "emboj.embopress.org",
            "authorea.com"
        ]
        if any(domain in final_url for domain in wiley_domains):
            return True
    except Exception:
        pass

    return False

async def download_wiley_pdf_by_doi(
    doi: str,
    download_folder: str = DEFAULT_DOWNLOAD_FOLDER,
    tdm_token: str | None = None,
) -> bool:
    """
    Attempt to download a PDF from Wiley using the DOI and Wiley-TDM-Client-Token.
    Returns True if successful, else False.
    """
    active_token = tdm_token or configuration.WILEY_TDM_TOKEN

    if not active_token:
        print("Error: Wiley-TDM-Client-Token is required to download from Wiley TDM API.")
        return False

    safe_doi = doi.replace('/', '_')
    filename = f"{safe_doi}_wiley.pdf"
    filepath = os.path.join(download_folder, filename)
    headers_path = os.path.join(download_folder, f"{safe_doi}_wiley_headers.txt")

    pdf_url = f"https://api.wiley.com/onlinelibrary/tdm/v1/articles/{quote_plus(doi)}"

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/pdf,application/octet-stream;q=0.9,*/*;q=0.8",
        "Referer": f"https://doi.org/{doi}",
        "Wiley-TDM-Client-Token": active_token,
    }

    try:
        async with aiohttp.TCPConnector() as conn:
            async with aiohttp.ClientSession(connector=conn) as session:
                async with session.get(
                    pdf_url,
                    headers=headers,
                    timeout=DOWNLOAD_TIMEOUT,
                    allow_redirects=True,
                ) as resp:
                    # Save headers for debugging
                    with open(headers_path, "w", encoding="utf-8") as hfile:
                        for k, v in resp.headers.items():
                            hfile.write(f"{k}: {v}\n")
                    if resp.status == 200 and resp.content_type == "application/pdf":
                        with open(filepath, "wb") as f:
                            f.write(await resp.read())
                        print(f"Downloaded PDF from Wiley: {filepath}")
                        return True
                    elif resp.status == 200:
                        # Sometimes content-type is not set correctly, try anyway
                        with open(filepath, "wb") as f:
                            f.write(await resp.read())
                        print(f"Downloaded (possibly non-PDF) file from Wiley: {filepath}")
                        return True
                    else:
                        vprint(f"Wiley PDF not found at {pdf_url} (HTTP {resp.status})")
    except Exception as e:
        vprint(f"Error downloading Wiley PDF for DOI {doi} from {pdf_url}: {e}")

    print(f"PDF file is not available from Wiley for DOI: {doi}.")
    return False

def is_pmc_doi(doi: str) -> bool:
    """
    Check if a DOI is associated with PubMed Central (PMC).
    Returns True if the DOI can be found in PMC via NCBI E-utilities.
    """
    try:
        esearch_url = (
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
            f"?db=pmc&term={quote_plus(doi)}[DOI]&retmode=json"
        )
        resp = requests.get(esearch_url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        idlist = data.get("esearchresult", {}).get("idlist", [])
        return bool(idlist)
    except Exception:
        return False

async def download_from_pmc(doi: str, download_folder: str = DEFAULT_DOWNLOAD_FOLDER) -> bool:
    """
    Download a PDF from PubMed Central (PMC) using the DOI.
    Returns True if successful, else False.
    """
    safe_doi = doi.replace('/', '_')
    filename = f"{safe_doi}_pmc.pdf"
    filepath = os.path.join(download_folder, filename)

    # Step 1: Use NCBI E-utilities to get the PMC ID from the DOI
    try:
        # ESearch to get pmcid
        esearch_url = (
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
            f"?db=pmc&term={quote_plus(doi)}[DOI]&retmode=json"
        )
        resp = requests.get(esearch_url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        idlist = data.get("esearchresult", {}).get("idlist", [])
        if not idlist:
            vprint(f"No PMC ID found for DOI: {doi}")
            return False
        pmcid = idlist[0]
        vprint(f"Found PMC ID {pmcid} for DOI: {doi}")
    except Exception as e:
        vprint(f"Error retrieving PMC ID for DOI {doi}: {e}")
        return False

    # Step 2: Try to find direct PDF link for the PMC ID
    try:
        # Use browser-like headers to avoid 403 errors
        browser_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Referer": "https://www.ncbi.nlm.nih.gov/",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }
        
        # Access the PMC article page
        pmc_url = f"https://pmc.ncbi.nlm.nih.gov/articles/PMC{pmcid}/"
        vprint(f"Accessing PMC article page: {pmc_url}")
        resp = requests.get(pmc_url, headers=browser_headers, timeout=15)
        resp.raise_for_status()
        
        # Look for PDF links using various patterns
        html = resp.text
        
        # Pattern to find PDF links in the HTML
        pdf_patterns = [
            rf'href="(/pmc/articles/PMC{pmcid}/pdf/[^"]+\.pdf)"',
            rf'href="(https://www\.ncbi\.nlm\.nih\.gov/pmc/articles/PMC{pmcid}/pdf/[^"]+\.pdf)"',
            rf'href="(https://pmc\.ncbi\.nlm\.nih\.gov/articles/PMC{pmcid}/pdf/[^"]+\.pdf)"',
            r'href="([^"]+\.pdf)"',  # Any PDF link
            r'data-src="([^"]+\.pdf)"',  # Sometimes PDFs are in data-src attributes
        ]
        
        pdf_url = None
        for pattern in pdf_patterns:
            matches = re.findall(pattern, html)
            if matches:
                pdf_url = matches[0]
                break
        
        if pdf_url:
            # Make relative URLs absolute
            if pdf_url.startswith('/'):
                pdf_url = f"https://pmc.ncbi.nlm.nih.gov/articles/PMC{pmcid}{pdf_url}"
            else:
                pdf_url = f"https://pmc.ncbi.nlm.nih.gov/articles/PMC{pmcid}/{pdf_url}"
                
            vprint(f"Found PDF URL: {pdf_url}")
        else:
            vprint(f"No PDF link found on PMC page for PMCID {pmcid}")

        
    except Exception as e:
        vprint(f"Error downloading from PMC for PMCID {pmcid}: {e}")

    print(f"PDF file is not available from PMC for DOI: {doi}.")
    return False

    
async def download_from_unpaywall(
    doi: str,
    download_folder: str = DEFAULT_DOWNLOAD_FOLDER,
    email: Optional[str] = None,
):
    """
    Download all possible open access PDFs for a DOI via Unpaywall.
    Each PDF is saved as <safe_doi>_unpaywall_file1.pdf, <safe_doi>_unpaywall_file2.pdf, etc.
    Returns True if at least one PDF was downloaded, else False.
    Always uses custom headers to bypass HTTP 418.
    If the DOI is from PMC, Elsevier or Wiley, try their API first.
    """
    # Try PMC first if DOI is PMC
    if is_pmc_doi(doi):
        print(f"DOI {doi} appears to be a PMC article. Attempting PMC download before Unpaywall...")
        if await download_from_pmc(doi, download_folder):
            return True

    # Try Elsevier API first if DOI is Elsevier
    if is_elsevier_doi(doi):
        print(f"DOI {doi} appears to be an Elsevier article. Attempting Elsevier Full-Text API download before Unpaywall...")
        if await download_elsevier_pdf_by_doi(doi=doi, download_folder=download_folder, api_key=configuration.ELSEVIER_API_KEY):
            return True

    # Try Wiley API first if DOI is Wiley
    if is_wiley_doi(doi):
        print(f"DOI {doi} appears to be a Wiley article. Attempting Wiley TDM API download before Unpaywall...")
        if await download_wiley_pdf_by_doi(doi, download_folder, tdm_token=configuration.WILEY_TDM_TOKEN):
            return True

    try:
        safe_doi = doi.replace('/', '_')
        active_email = email or require_email()
        UnpywallCredentials(active_email)

        # Get all OA links (should include all PDF URLs)
        all_links = Unpywall.get_all_links(doi=doi)
        vprint(f"Found {len(all_links)} open access links on Unpaywall for DOI: {doi}")
        vprint(f"All links: {all_links}")
        if not all_links:
            vprint(f"No open access links found on Unpaywall for DOI: {doi}")
            return False

        # Filter for PDF links (endswith .pdf or content-type check)
        pdf_links = [url for url in all_links if url.lower().endswith('.pdf')]

        downloaded = 0
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "application/pdf,application/octet-stream;q=0.9,*/*;q=0.8",
            "Referer": f"https://doi.org/{doi}",
            "DNT": "1",
            "Connection": "keep-alive",
        }

        # Try direct PDF links first
        for idx, pdf_url in enumerate(pdf_links, 1):
            filename = f"{safe_doi}_unpaywall_{idx}.pdf"
            filepath = os.path.join(download_folder, filename)
            vprint(f"Attempting to download Unpaywall PDF #{idx}: {pdf_url} -> {filepath}")
            try:
                async with aiohttp.TCPConnector() as conn:
                    async with aiohttp.ClientSession(connector=conn) as session:
                        async with session.get(pdf_url, headers=headers, timeout=DOWNLOAD_TIMEOUT) as resp:
                            vprint(f"Unpaywall PDF HTTP status: {resp.status}")
                            if resp.status == 200 and resp.content_type == "application/pdf":
                                with open(filepath, "wb") as f:
                                    f.write(await resp.read())
                                print(f"Downloaded PDF from Unpaywall: {filepath}")
                                downloaded += 1
                                continue
                            elif resp.status == 200:
                                # Sometimes content-type is not set correctly, try anyway
                                with open(filepath, "wb") as f:
                                    f.write(await resp.read())
                                print(f"Downloaded (possibly non-PDF) file from Unpaywall: {filepath}")
                                downloaded += 1
                                continue
                            else:
                                print(f"Failed to download PDF from Unpaywall for DOI: {doi} (HTTP {resp.status})")
            except Exception as e:
                print(f"Error downloading PDF from Unpaywall for DOI {doi} at {pdf_url}: {e}")

        if downloaded > 0:
            return True

        # If no direct PDF, try to download OA link directly as a PDF (browser-style request)
        for idx, url in enumerate(all_links, 1):
            if url in pdf_links:
                continue  # Already tried direct PDF links
            vprint(f"Trying to download OA link directly as PDF: {url}")
            try:
                async with aiohttp.TCPConnector() as conn:
                    async with aiohttp.ClientSession(connector=conn) as session:
                        browser_headers = {
                            "User-Agent": (
                                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                "AppleWebKit/537.36 (KHTML, like Gecko) "
                                "Chrome/124.0.0.0 Safari/537.36 Edg/124.0.2478.67"
                            ),
                            "Accept": "application/pdf,application/octet-stream;q=0.9,*/*;q=0.8",
                            "Referer": f"https://doi.org/{doi}",
                            "DNT": "1",
                            "Connection": "keep-alive",
                        }
                        async with session.get(url, headers=browser_headers, timeout=DOWNLOAD_TIMEOUT) as resp:
                            if resp.status == 200 and resp.content_type == "application/pdf":
                                filename = f"{safe_doi}_unpaywall_browser_{idx}.pdf"
                                filepath = os.path.join(download_folder, filename)
                                with open(filepath, "wb") as f:
                                    f.write(await resp.read())
                                print(f"Downloaded PDF by direct OA link (browser): {filepath}")
                                downloaded += 1
                                # Don't break, try all links
                            elif resp.status == 200:
                                # Sometimes content-type is not set correctly, try anyway
                                filename = f"{safe_doi}_unpaywall_browser_{idx}.pdf"
                                filepath = os.path.join(download_folder, filename)
                                with open(filepath, "wb") as f:
                                    f.write(await resp.read())
                                print(f"Downloaded (possibly non-PDF) file by direct OA link (browser): {filepath}")
                                downloaded += 1
            except Exception as e:
                vprint(f"Error downloading OA link directly as PDF {url}: {e}")

        if downloaded > 0:
            return True
        
        # If no direct PDF, try to follow each OA link and look for PDF
        for idx, url in enumerate(all_links, 1):
            if url in pdf_links:
                continue  # Already tried direct PDF links
            vprint(f"Trying to follow OA link to find PDF: {url}")
            try:
                async with aiohttp.TCPConnector() as conn:
                    async with aiohttp.ClientSession(connector=conn) as session:
                        # Use a more realistic browser header to avoid 403 errors
                        oa_headers = {
                            "User-Agent": (
                                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                "AppleWebKit/537.36 (KHTML, like Gecko) "
                                "Chrome/124.0.0.0 Safari/537.36 Edg/124.0.2478.67"
                            ),
                            "Accept": (
                                "text/html,application/xhtml+xml,application/xml;"
                                "q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,"
                                "application/signed-exchange;v=b3;q=0.7"
                            ),
                            "Accept-Language": "en-US,en;q=0.9",
                            "Accept-Encoding": "gzip, deflate, br",
                            "Connection": "keep-alive",
                            "Upgrade-Insecure-Requests": "1",
                            "Sec-Fetch-Dest": "document",
                            "Sec-Fetch-Mode": "navigate",
                            "Sec-Fetch-Site": "none",
                            "Sec-Fetch-User": "?1",
                            "Pragma": "no-cache",
                            "Cache-Control": "no-cache",
                            "DNT": "1",
                            "Referer": f"https://doi.org/{doi}",
                        }
                        async with session.get(url, headers=oa_headers, timeout=DOWNLOAD_TIMEOUT) as resp:
                            if resp.status != 200:
                                vprint(f"Failed to fetch OA link {url} (HTTP {resp.status})")
                                continue
                            html = await resp.text()
                            # Try to find PDF links in the HTML
                            found_pdf = False
                            pdf_candidates = re.findall(r'href=["\']([^"\']+\.pdf[^"\']*)["\']', html, re.IGNORECASE)
                            for pdf_candidate in pdf_candidates:
                                # Make absolute URL if needed
                                if pdf_candidate.startswith("//"):
                                    pdf_candidate_url = "https:" + pdf_candidate
                                elif pdf_candidate.startswith("/"):
                                    pdf_candidate_url = urljoin(url, pdf_candidate)
                                elif pdf_candidate.startswith("http"):
                                    pdf_candidate_url = pdf_candidate
                                else:
                                    pdf_candidate_url = url.rstrip("/") + "/" + pdf_candidate
                                vprint(f"Found candidate PDF link: {pdf_candidate_url}")
                                try:
                                    async with session.get(
                                        pdf_candidate_url,
                                        headers=oa_headers,
                                        timeout=DOWNLOAD_TIMEOUT,
                                    ) as pdf_resp:
                                        if pdf_resp.status == 200 and pdf_resp.content_type == "application/pdf":
                                            filename = f"{safe_doi}_unpaywall_follow_{idx}.pdf"
                                            filepath = os.path.join(download_folder, filename)
                                            with open(filepath, "wb") as f:
                                                f.write(await pdf_resp.read())
                                            print(f"Downloaded PDF by following OA link: {filepath}")
                                            downloaded += 1
                                            found_pdf = True
                                            break
                                except Exception as e:
                                    vprint(f"Error downloading candidate PDF {pdf_candidate_url}: {e}")
                            if found_pdf:
                                break
            except Exception as e:
                vprint(f"Error following OA link {url}: {e}")

        if downloaded > 0:
            return True

        print(f"No direct PDF could be downloaded from Unpaywall for DOI: {doi}")
        print("The following open access links are available from Unpaywall:")
        for url in all_links:
            print(f"  {url}")
        print("Please try to download manually from one of these links.")
        return False

    except ImportError:
        print("unpywall package not installed. Please install with: pip install unpywall")
        return False
    except Exception as e:
        print(f"Error querying Unpaywall for DOI {doi}: {e}")
        return False

async def download_from_nexus(id: str, doi: str, download_folder: str = DEFAULT_DOWNLOAD_FOLDER):
    safe_doi = doi.replace('/', '_')
    filename = f"{safe_doi}_nexus.pdf"
    filepath = f"{download_folder}/{filename}"
    
    # Try both URL formats
    file_urls = [
        f"https://libstc-cc.ipns.dweb.link/repo/{id}.pdf",
        f"https://libstc-cc.ipns.dweb.link/dois/{quote_plus(quote_plus(doi.lower())).lower()}.pdf"
    ]
    
    for file_url in file_urls:
        vprint(f"Attempting to download from Nexus: {file_url} -> {filepath}")
        try:
            async with aiohttp.TCPConnector() as conn:
                async with aiohttp.ClientSession(connector=conn) as session:
                    async with session.get(file_url) as resp:
                        vprint(f"Nexus HTTP status: {resp.status}")
                        if resp.status == 200:
                            with open(filepath, "wb") as f:
                                f.write(await resp.read())
                            print(f"Downloaded PDF location: {filepath}")
                            return True
        except Exception as e:
            vprint(f"Exception occurred while downloading file for DOI {doi} from Nexus URL {file_url}: {e}")
    
    return False

async def download_from_nexus_bot(doi: str, download_folder: str = DEFAULT_DOWNLOAD_FOLDER):
    """
    Download a PDF by DOI using the Nexus bot (via .nexus module).
    Returns True if successful, else False.
    Uses decide_proxy_usage function to determine whether to use proxy.
    """
    safe_doi = doi.replace('/', '_')
    filename = f"{safe_doi}_nexusbot.pdf"
    filepath = os.path.join(download_folder, filename)
    try:
        TG_API_ID, TG_API_HASH, PHONE, BOT_USERNAME = await nexus.load_credentials_from_file(nexus.CREDENTIALS_FILE)
        
        # Use decide_proxy_usage to determine if proxy should be used
        proxy_result = await nexus.decide_proxy_usage(TG_API_ID, TG_API_HASH, PHONE, nexus.SESSION_FILE, nexus.DEFAULT_PROXY_FILE, print_result=False)
        if proxy_result is False:
            print("Error: Could not establish connection to Telegram (neither direct nor via proxy)")
            return False
        proxy = proxy_result if proxy_result else None
        
        pdf_bytes = await nexus.check_doi_availability_on_nexus(
            api_id=TG_API_ID,
            api_hash=TG_API_HASH,
            phone_number=PHONE,
            bot_username=BOT_USERNAME,
            doi=doi,
            session_file=nexus.SESSION_FILE,
            proxy=proxy,
            download=True
        )
        download_result = pdf_bytes.get('download_result', {})
        if download_result.get("success"):
            nexus_bot_download_file = download_result.get('file_path')
            if nexus_bot_download_file and os.path.exists(nexus_bot_download_file):
                shutil.move(nexus_bot_download_file, filepath)
                print(f"Downloaded PDF from Nexus bot: {filepath}")
                return True
            else:
                print(f"Downloaded file not found at {nexus_bot_download_file}.")
                return False
        else:
            # print(f"PDF file is not available from Nexus bot for DOI: {doi}.")
            return False
    except Exception as e:
        print(f"Error downloading PDF from Nexus bot for DOI {doi}: {e}")
    return False

async def download_from_scihub(doi: str, download_folder: str = DEFAULT_DOWNLOAD_FOLDER):
    safe_doi = doi.replace('/', '_')
    filename = f"{safe_doi}_scihub.pdf"
    filepath = os.path.join(download_folder, filename)
    sci_hub_domains = [
        "https://sci-hub.se",
        "https://sci-hub.st",
        "https://sci-hub.ru",
        "https://sci-hub.red",
        "https://sci-hub.box",
        "https://sci-net.xyz",
        "https://sci-net.ru"
    ]
    for domain in sci_hub_domains:
        # Use different filename for sci-net domains
        if "sci-net" in domain:
            filename = f"{safe_doi}_scinet.pdf"
            filepath = os.path.join(download_folder, filename)
        else:
            filename = f"{safe_doi}_scihub.pdf"
            filepath = os.path.join(download_folder, filename)
        sci_hub_url = f"{domain}/{doi}"
        vprint(f"Trying Sci-Hub domain: {sci_hub_url}")
        try:
            async with aiohttp.TCPConnector() as conn:
                async with aiohttp.ClientSession(connector=conn) as session:
                    async with session.get(sci_hub_url) as resp:
                        vprint(f"Sci-Hub HTTP status: {resp.status}")
                        html = await resp.text()
                        m = re.search(r'src\s*=\s*["\'](.*?\.pdf.*?)["\']', html)
                        if m:
                            pdf_url = m.group(1)
                            if pdf_url.startswith("//"):
                                pdf_url = "https:" + pdf_url
                            elif pdf_url.startswith("/"):
                                pdf_url = domain + pdf_url
                            vprint(f"Found PDF URL on Sci-Hub: {pdf_url}")
                            async with session.get(pdf_url) as pdf_resp:
                                vprint(f"Sci-Hub PDF HTTP status: {pdf_resp.status}")
                                if pdf_resp.status == 200:
                                    with open(filepath, "wb") as f:
                                        f.write(await pdf_resp.read())
                                    print(f"Downloaded PDF from {domain}: {filepath}")
                                    return True
        except Exception as e:
            print(f"Error accessing Sci-Hub at {domain}: {e}")
    return False

async def download_from_anna_archive(doi: str, download_folder: str = DEFAULT_DOWNLOAD_FOLDER):
    safe_doi = doi.replace('/', '_')
    filename = f"{safe_doi}_anna.pdf"
    filepath = os.path.join(download_folder, filename)
    anna_domains = [
        "https://annas-archive.li",
        "https://annas-archive.se",
        "https://annas-archive.org"
    ]
    for domain in anna_domains:
        anna_url = f"{domain}/scidb/{doi}"
        vprint(f"Trying Anna's Archive domain: {anna_url}")
        try:
            async with aiohttp.TCPConnector() as conn:
                async with aiohttp.ClientSession(connector=conn) as session:
                    async with session.get(anna_url) as resp:
                        vprint(f"Anna's Archive HTTP status: {resp.status}")
                        if resp.status != 200:
                            vprint(f"Anna's Archive page not found for DOI: {doi} at {domain}")
                            continue
                        html = await resp.text()
                        # Find md5sum from the "Record in Anna’s Archive" link
                        md5_match = re.search(r'<a[^>]+href=["\']/md5/([a-fA-F0-9]{32})["\']', html)
                        if not md5_match:
                            vprint(f"No md5sum found on Anna's Archive for DOI: {doi} at {domain}")
                            continue
                        md5sum = md5_match.group(1)
                        vprint(f"Found md5sum on Anna's Archive: {md5sum}")
                        # Find all links ending with <md5sum>.pdf
                        pdf_links = re.findall(r'<a[^>]+href=["\']([^"\']*' + re.escape(md5sum) + r'\.pdf[^"\']*)["\']', html)
                        if not pdf_links:
                            vprint(f"No PDF links found for md5sum {md5sum} on Anna's Archive for DOI: {doi} at {domain}")
                            continue
                        for pdf_url in pdf_links:
                            # Make absolute URL if needed
                            if pdf_url.startswith("/"):
                                pdf_url_full = domain + pdf_url
                            elif pdf_url.startswith("http"):
                                pdf_url_full = pdf_url
                            else:
                                pdf_url_full = domain + "/" + pdf_url
                            vprint(f"Trying PDF link from Anna's Archive: {pdf_url_full}")
                            try:
                                async with session.get(pdf_url_full) as pdf_resp:
                                    vprint(f"Anna's Archive PDF HTTP status: {pdf_resp.status}")
                                    if pdf_resp.status == 200:
                                        with open(filepath, "wb") as f:
                                            f.write(await pdf_resp.read())
                                        print(f"Downloaded PDF from Anna's Archive: {filepath}")
                                        return True
                                    else:
                                        print(f"PDF download failed from Anna's Archive for DOI: {doi} at {pdf_url_full}")
                            except Exception as e:
                                print(f"Error downloading PDF from Anna's Archive for DOI {doi} at {pdf_url_full}: {e}")
                        print(f"All PDF links tried for md5sum {md5sum} but failed for DOI: {doi} at {domain}")
        except Exception as e:
            print(f"Error accessing Anna's Archive for DOI {doi} at {domain}: {e}")
    return False

async def download_by_doi(
    doi: str,
    download_folder: str = DEFAULT_DOWNLOAD_FOLDER,
    db: str | list[str] | tuple[str, ...] = "all",
    no_download: bool = False,
):
    # Extract DOI from input if possible (handles cases where input is a URL or contains a DOI)
    dois = extract_dois_from_text(doi)
    if dois:
        doi = dois[0]
    else:
        print(f"❌ Input does not appear to be a valid DOI or DOI-containing string: {doi}")
        return False
    vprint(f"Starting download_by_doi for DOI: {doi}, folder: {download_folder}, db: {db}, no_download: {no_download}")
    selected_dbs = normalize_db_selection(db)
    results = await search_documents(doi, 1)
    
    if results:
        document = json.loads(results[0].document)
        print("🔎 Search result for DOI:")
        print(format_reference(document))
        if VERBOSE:
            print("Full document JSON:")
            print(json.dumps(document, indent=2))
        print('-----')
        
        id = document.get('id')
    else:
        print(f"❌ No document found for DOI: {doi}")
        id = None

    if no_download:
        print("🚫 --no-download specified, skipping download.")
        return None

    print(f"📥 Attempting to download PDF for DOI: {doi}")
    # Check if the DOI is open access via Unpaywall
    try:
        is_oa = await is_open_access_unpaywall(doi)
    except ValueError as exc:
        print(f"❌ {exc}")
        return False
    oa_status_text = "Open Access" if is_oa else "Closed Access"
    oa_icon = "🟢" if is_oa else "🔒"
    
    if is_oa:
        print(f"🌐 DOI {doi} is Open Access. Using Unpaywall for download...")
        if await download_from_unpaywall(doi, download_folder):
            print(f"\n📥 Download Summary:")
            print(f"✅ Successfully downloaded: 1 PDF")
            print(f"  ✓ {doi} [{oa_status_text}] {oa_icon}")
            return True
        print(f"⚠️ Failed to download from Unpaywall for DOI: {doi}. Trying other sources...")

    if not id and "nexus" in selected_dbs:
        print(f"❌ No ID available for Nexus download for DOI: {doi}.")

    tried = False

    if "nexus" in selected_dbs and id:
        tried = True
        vprint(f"Trying Nexus download for id: {id}, doi: {doi}")
        print(f"🪐 Trying Nexus for DOI: {doi}...")
        if await download_from_nexus(id, doi, download_folder):
            print(f"\n📥 Download Summary:")
            print(f"✅ Successfully downloaded: 1 PDF")
            print(f"  ✓ {doi} [{oa_status_text}] {oa_icon}")
            return True
        print(f"❌ PDF file is not available on the Nexus server for DOI: {doi}.")
        # Try Nexus bot as fallback
        print(f"🤖 Trying Nexus bot for DOI: {doi}...")
        if await download_from_nexus_bot(doi, download_folder):
            print(f"\n📥 Download Summary:")
            print(f"✅ Successfully downloaded: 1 PDF")
            print(f"  ✓ {doi} [{oa_status_text}] {oa_icon}")
            return True
        print(f"❌ PDF file is not available from Nexus bot for DOI: {doi}.")

    if "scihub" in selected_dbs:
        tried = True
        print(f"🧪 Trying Sci-Hub for DOI: {doi}...")
        if await download_from_scihub(doi, download_folder):
            print(f"\n📥 Download Summary:")
            print(f"✅ Successfully downloaded: 1 PDF")
            print(f"  ✓ {doi} [{oa_status_text}] {oa_icon}")
            return True
        print(f"❌ PDF file is not available on Sci-Hub for DOI: {doi}.")

    if "anna" in selected_dbs:
        tried = True
        print(f"📚 Trying Anna's Archive for DOI: {doi}...")
        if await download_from_anna_archive(doi, download_folder):
            print(f"\n📥 Download Summary:")
            print(f"✅ Successfully downloaded: 1 PDF")
            print(f"  ✓ {doi} [{oa_status_text}] {oa_icon}")
            return True
        print(f"❌ PDF file is not available on Anna's Archive for DOI: {doi}.")

    if "libgen" in selected_dbs:
        tried = True
        print(f"📖 Trying LibGen for DOI: {doi}...")
        try:
            # Call the libgen module's download_by_doi function
            result = libgen.download_libgen_paper_by_doi(doi, dest_folder=download_folder, print_result=False)
            if result:
                print(f"\n📥 Download Summary:")
                print(f"✅ Successfully downloaded: 1 PDF")
                print(f"  ✓ {doi} [{oa_status_text}] {oa_icon}")
                return True
            else:
                print(f"❌ PDF file is not available on LibGen for DOI: {doi}.")
        except Exception as e:
            print(f"❌ Error downloading from LibGen for DOI {doi}: {e}")

    if "unpaywall" in selected_dbs:
        tried = True
        print(f"🌐 Trying Unpaywall for DOI: {doi}...")
        if await download_from_unpaywall(doi, download_folder):
            print(f"\n📥 Download Summary:")
            print(f"✅ Successfully downloaded: 1 PDF")
            print(f"  ✓ {doi} [{oa_status_text}] {oa_icon}")
            return True
        print(f"❌ PDF file is not available on Unpaywall for DOI: {doi}.")

    # Special handling for Elsevier and Wiley DOIs
    if is_elsevier_doi(doi):
        print(f"🧬 DOI {doi} appears to be an Elsevier article. Attempting Elsevier Full-Text API download...")
        if await download_elsevier_pdf_by_doi(doi=doi, download_folder=download_folder, api_key=configuration.ELSEVIER_API_KEY):
            print(f"\n📥 Download Summary:")
            print(f"✅ Successfully downloaded: 1 PDF")
            print(f"  ✓ {doi} [{oa_status_text}] {oa_icon}")
            return True
        print(f"❌ PDF file is not available from Elsevier Full-Text API for DOI: {doi}.")

    if is_wiley_doi(doi):
        print(f"🧑‍🔬 DOI {doi} appears to be a Wiley article. Attempting Wiley TDM API download...")
        if await download_wiley_pdf_by_doi(doi, download_folder, tdm_token=configuration.WILEY_TDM_TOKEN):
            print(f"\n📥 Download Summary:")
            print(f"✅ Successfully downloaded: 1 PDF")
            print(f"  ✓ {doi} [{oa_status_text}] {oa_icon}")
            return True
        print(f"❌ PDF file is not available from Wiley TDM API for DOI: {doi}.")

    if not tried:
        print(f"❓ No valid database specified for DOI: {doi}.")
    
    # print(f"\nDownload Summary:")
    # print(f"Failed to download: 1 PDF")
    # print(f"  ✗ {doi} [{oa_status_text}]")
    return False

async def download_by_doi_list(
    doi_file: str,
    download_folder: str = DEFAULT_DOWNLOAD_FOLDER,
    db: str | list[str] | tuple[str, ...] = "all",
    no_download: bool = False,
):
    ICON_START = "🚀"
    ICON_DOI = "🔎"
    ICON_SUCCESS = "✅"
    ICON_FAIL = "❌"
    ICON_SKIP = "🚫"
    ICON_OA = "🟢"
    ICON_CLOSED = "🔒"
    ICON_FILE = "📄"
    ICON_SUMMARY = "📥"
    ICON_STEP = "➡️"
    ICON_WARN = "⚠️"

    vprint(
        f"{ICON_START} Starting download_by_doi_list for file: {doi_file}, folder: {download_folder}, db: {normalize_db_selection(db)}, no_download: {no_download}"
    )
    
    # Always extract DOIs from the file using extract_dois_from_file
    try:
        print(f"{ICON_STEP} Extracting DOIs from file: {doi_file}")
        dois = extract_dois_from_file(doi_file)
        if not dois:
            print(f"{ICON_FAIL} Error: No valid DOI numbers could be extracted from {doi_file}.")
            return {}
        vprint(f"{ICON_STEP} Using extracted DOIs from file: {doi_file}")
    except Exception as e:
        print(f"{ICON_FAIL} Failed to extract DOIs from file: {e}")
        return {}

    download_results = {}
    successful_downloads = []
    failed_downloads = []
    
    for doi in dois:
        print(f"{ICON_DOI} Processing DOI: {doi}")
        # Get open access status
        oa_status = await is_open_access_unpaywall(doi)
        oa_status_text = "Open Access" if oa_status else "Closed Access"
        oa_icon = ICON_OA if oa_status else ICON_CLOSED
        
        result = await download_by_doi(doi, download_folder=download_folder, db=db, no_download=no_download)
        
        if result is True:
            # Find the downloaded file
            safe_doi = doi.replace('/', '_')
            # Check for various possible filenames
            possible_files = [
                f"{safe_doi}_unpaywall.pdf",
                f"{safe_doi}_unpaywall_1.pdf",
                f"{safe_doi}_unpaywall_elsevier.pdf",
                f"{safe_doi}_elsevier.pdf",
                f"{safe_doi}_wiley.pdf",
                f"{safe_doi}_nexus.pdf",
                f"{safe_doi}_nexusbot.pdf",
                f"{safe_doi}_scihub.pdf",
                f"{safe_doi}_scinet.pdf",
                f"{safe_doi}_anna.pdf",
                f"{safe_doi}_pmc.pdf",
                f"{safe_doi}_libgen.pdf"
            ]
            
            downloaded_file = None
            for filename in possible_files:
                filepath = os.path.join(download_folder, filename)
                if os.path.exists(filepath):
                    downloaded_file = filepath
                    break
            
            # Also check for numbered unpaywall files
            if not downloaded_file:
                for i in range(1, 10):  # Check up to 10 files
                    filename = f"{safe_doi}_unpaywall_{i}.pdf"
                    filepath = os.path.join(download_folder, filename)
                    if os.path.exists(filepath):
                        downloaded_file = filepath
                        break
            
            download_results[doi] = ["success", downloaded_file if downloaded_file else "file_not_found"]
            successful_downloads.append((doi, oa_status))
            print(f"{ICON_SUCCESS} Downloaded: {doi} [{oa_status_text}] {oa_icon} {ICON_FILE if downloaded_file else ''}")
            
        elif result is False:
            download_results[doi] = ["failed", None]
            failed_downloads.append((doi, oa_status))
            print(f"{ICON_FAIL} Failed: {doi} [{oa_status_text}] {oa_icon}")
        else:  # result is None when no_download is True or no document found
            status = "no_download" if no_download else "not_found"
            download_results[doi] = [status, None]
            if no_download:
                print(f"{ICON_SKIP} Skipped download for: {doi} [{oa_status_text}] {oa_icon}")
            else:
                print(f"{ICON_FAIL} Not found: {doi} [{oa_status_text}] {oa_icon}")
    
    if not no_download:
        print(f"\n{ICON_SUMMARY} Download Summary:")
        print(f"{ICON_SUCCESS} Successfully downloaded: {len(successful_downloads)} PDFs")
        if successful_downloads:
            for doi, oa_status in successful_downloads:
                oa_status_text = "Open Access" if oa_status else "Closed Access"
                oa_icon = ICON_OA if oa_status else ICON_CLOSED
                print(f"  {ICON_SUCCESS} {doi} [{oa_status_text}] {oa_icon}")
        
        print(f"{ICON_FAIL} Failed to download: {len(failed_downloads)} PDFs")
        if failed_downloads:
            for doi, oa_status in failed_downloads:
                oa_status_text = "Open Access" if oa_status else "Closed Access"
                oa_icon = ICON_OA if oa_status else ICON_CLOSED
                print(f"  {ICON_FAIL} {doi} [{oa_status_text}] {oa_icon}")
    
    return download_results

def print_default_paths():
    """
    Print all default paths and configuration file locations used by the script.
    """
    print("Default configuration and data paths:")
    print(f"  GETPAPERS_CONFIG_FILE: {GETPAPERS_CONFIG_FILE}")
    print(f"  Default download folder: {DEFAULT_DOWNLOAD_FOLDER}")
    print(f"  Unpywall cache file: {UNPYWALL_CACHE_FILE}")
    print(f"  Platform: {platform.system()}")

async def main(argv: list[str] | None = None):
    if platform.system() == "Windows":
        # Prefer the selector policy to avoid Proactor cleanup warnings on exit
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    # Get the parent package name from the module's __name__
    parent_package = __name__.split('.')[0] if '.' in __name__ else None

    if parent_package is None:
        program_name = 'getpapers'
    elif '_' in parent_package:
        # If the parent package has an underscore, strip it
        parent_package = parent_package[:parent_package.index('_')]
        program_name = f"{parent_package} getpapers"

    argparser = argparse.ArgumentParser(
        description="Search for and download scientific papers by DOI or keyword. "
                   "Supports downloading from multiple sources including Unpaywall, Sci-Hub, Anna's Archive.",
        epilog=(
            "Examples:\n"
            "  %(prog)s --search \"machine learning\"\n"
            "  %(prog)s --doi 10.1038/nature12373\n"
            "  %(prog)s --doi-file papers.txt\n"
            "  %(prog)s --doi 10.1016/j.cell.2019.05.031 --db unpaywall\n"
            "  %(prog)s --search \"deep learning\" --limit 10\n"
            "  %(prog)s --doi 10.1016/j.cell.2019.05.031 --no-download\n"
            "  %(prog)s --doi 10.1016/j.cell.2019.05.031 --download-folder ./pdfs\n"
            "  %(prog)s --doi-file mylist.txt --db scihub\n"
            "  %(prog)s --search \"climate change\" --verbose\n"
            "  %(prog)s --doi 10.1002/anie.201915678 --credentials mycredentials.json\n"
            "  %(prog)s --clear-credentials\n"
            "  %(prog)s --print-default\n"
            "  %(prog)s --extract-doi-from-pdf mypaper.pdf\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        prog=program_name
    )
    argparser.add_argument("--search", type=str, help="Search keyword or DOI")
    argparser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    argparser.add_argument("--doi", type=str, help="Specify a DOI to download the paper")
    argparser.add_argument("--doi-file", type=str, help="Path to a text file containing DOIs (one per line)")
    argparser.add_argument("--download-folder", type=str, default=DEFAULT_DOWNLOAD_FOLDER, help="Folder to save downloaded PDFs")
    argparser.add_argument(
        "--db",
        action="append",
        choices=["all", *DB_CHOICES],
        help=(
            "Specify which database(s) to use for downloading PDFs: all, nexus, scihub, anna, unpaywall, libgen. "
            "Repeat the flag to target multiple services; defaults to all."
        ),
    )
    argparser.add_argument(
        "--no-download",
        action="store_true",
        help="Only show metadata, do not download PDFs"
    )
    argparser.add_argument(
        "--verbose",
        action="store_true",
        help="Print more details of how the script is running"
    )
    argparser.add_argument(
        "--credentials",
        type=str,
        help="Path to custom JSON credentials file (format: {\"email\": \"your@email.com\", \"elsevier_api_key\": \"key\", \"wiley_tdm_token\": \"token\", \"ieee_api_key\": \"key\"})"
    )
    argparser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Do not prompt for missing credentials; rely on config file or environment variables."
    )
    argparser.add_argument(
        "--clear-credentials",
        action="store_true",
        help="Delete the default configuration directory and all its contents"
    )
    argparser.add_argument(
        "--print-default",
        action="store_true",
        help="Print all default paths and configuration file locations used by the script"
    )
    argparser.add_argument(
        "--extract-doi-from-pdf",
        type=str,
        help="Extract the first valid DOI from a PDF file"
    )
    argparser.add_argument(
        "--extract-doi-from-txt",
        type=str,
        help="Extract all valid DOIs from a text file and write them to <file>.dois.txt"
    )
        
    args = argparser.parse_args(argv)
    args.db = args.db or ["all"]

    # Initialize Unpywall cache
    ensure_directory_exists(UNPYWALL_CACHE_DIR)
    cache = UnpywallCache(UNPYWALL_CACHE_FILE)
    Unpywall.init_cache(cache)

    # Handle --print-default before anything else
    if args.print_default:
        print_default_paths()
        sys.exit(0)

    # Handle --clear-credentials before anything else
    if args.clear_credentials:
        config_dir = os.path.dirname(GETPAPERS_CONFIG_FILE)
        if os.path.exists(config_dir):
            try:
                shutil.rmtree(config_dir)
                print(f"Deleted configuration directory: {config_dir}")
            except Exception as e:
                print(f"Failed to delete configuration directory {config_dir}: {e}")
        else:
            print(f"Configuration directory does not exist: {config_dir}")
        sys.exit(0)

    # Check that mutually exclusive options are not specified together
    exclusive_options = [args.doi, args.doi_file, args.search, args.extract_doi_from_pdf, args.extract_doi_from_txt]
    if sum(bool(opt) for opt in exclusive_options) > 1:
        print("Error: Only one of --doi, --doi-file, --search, --extract-doi-from-pdf, or --extract-doi-from-txt can be specified at a time.")
        sys.exit(1)

    # Set global verbose flag
    global VERBOSE
    VERBOSE = args.verbose

    # Ensure download folder exists before any file IO
    args.download_folder = args.download_folder or DEFAULT_DOWNLOAD_FOLDER
    ensure_directory_exists(args.download_folder)

    # Credentials file
    credentials_file = args.credentials if args.credentials else GETPAPERS_CONFIG_FILE

    # Load credentials from credentials file or environment
    try:
        load_credentials(credentials_file, interactive=not args.non_interactive and sys.stdin.isatty())
    except ValueError as exc:
        print(f"❌ {exc}")
        sys.exit(1)

    # If only --credentials is specified, exit after loading credentials
    if args.credentials and not (args.doi or args.doi_file or args.search or args.extract_doi_from_pdf or args.extract_doi_from_txt):
        print(f"Loaded credentials from file: {credentials_file}")
        sys.exit(0)

    if args.extract_doi_from_pdf:
        pdf_file = args.extract_doi_from_pdf
        doi = extract_doi_from_pdf(pdf_file)
        if doi:
            print(f"Extracted DOI from PDF: {doi}")
        else:
            print(f"No valid DOI found in PDF: {pdf_file}")
    elif args.extract_doi_from_txt:
        txt_file = args.extract_doi_from_txt
        extract_dois_from_file(txt_file)
    elif args.doi:
        await download_by_doi(args.doi, download_folder=args.download_folder, db=args.db, no_download=args.no_download)
    elif args.search:
        await search_and_print(args.search, args.limit)
    elif args.doi_file:
        await download_by_doi_list(args.doi_file, download_folder=args.download_folder, db=args.db, no_download=args.no_download)
    else:
        print("Please specify --search <keyword|doi>, --doi <doi>, --doi-file <file>, --extract-doi-from-pdf <pdf>, or --extract-doi-from-txt <txt>.")

if __name__ == "__main__":
    # Use the recommended event loop policy for Windows
    if platform.system() == "Windows":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    asyncio.run(main())