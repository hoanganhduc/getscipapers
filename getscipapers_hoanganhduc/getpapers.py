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

from . import nexus  # Import Nexus bot functions from .nexus module
from . import libgen  # Import LibGen functions from .libgen module

DEFAULT_LIMIT = 5

VERBOSE = False  # Global verbose flag

# Emails and API keys for various services
EMAIL = ""
ELSEVIER_API_KEY = ""
WILEY_TDM_TOKEN = ""
IEEE_API_KEY = ""
    
def vprint(*args, **kwargs):
    if VERBOSE:
        print(*args, **kwargs)

# Global variable for default config file location
GETPAPERS_CONFIG_FILE = os.path.join(
    os.path.expanduser("~"),
    ".config", "getscipapers", "getpapers", "config.json"
) if platform.system() != "Windows" else os.path.join(
    os.path.expanduser("~"),
    "AppData", "Local", "getscipapers", "getpapers", "config.json"
)

# Ensure the folder to save the config file exists
config_dir = os.path.dirname(GETPAPERS_CONFIG_FILE)
if not os.path.exists(config_dir):
    try:
        os.makedirs(config_dir, exist_ok=True)
    except Exception as e:
        print(f"Error creating config directory {config_dir}: {e}")

# Set Unpywall cache directory to the same folder as the config file
UNPYWALL_CACHE_DIR = os.path.dirname(GETPAPERS_CONFIG_FILE)
UNPYWALL_CACHE_FILE = os.path.join(UNPYWALL_CACHE_DIR, "unpywall_cache")

def get_default_download_folder():
    """
    Get the default download folder for the current OS.
    - Windows: %USERPROFILE%\Downloads\getscipapers\getpapers
    - macOS: ~/Downloads/getscipapers/getpapers
    - Linux: ~/Downloads/getscipapers/getpapers
    """
    system = platform.system()
    if system == "Windows":
        base = os.environ.get('USERPROFILE', os.path.expanduser('~'))
        folder = os.path.join(base, 'Downloads', 'getscipapers', 'getpapers')
    else:
        folder = os.path.join(os.path.expanduser('~'), 'Downloads', 'getscipapers', 'getpapers')
    os.makedirs(folder, exist_ok=True)
    return folder

DEFAULT_DOWNLOAD_FOLDER = get_default_download_folder()

def save_credentials(email: str = None, elsevier_api_key: str = None, 
                    wiley_tdm_token: str = None, ieee_api_key: str = None, 
                    config_file: str = None):
    """
    Save credentials and API keys to a JSON configuration file.
    Only updates provided values, preserving existing ones.
    If the config file's parent directory does not exist, create it.
    """
    if config_file is None:
        config_file = GETPAPERS_CONFIG_FILE

    # Ensure the parent directory exists
    config_dir = os.path.dirname(config_file)
    if not os.path.exists(config_dir):
        try:
            os.makedirs(config_dir, exist_ok=True)
            vprint(f"Created config directory: {config_dir}")
        except Exception as e:
            vprint(f"Error creating config directory {config_dir}: {e}")
            return False

    # Load existing config or create new one
    existing_config = {}
    if os.path.exists(config_file):
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                existing_config = json.load(f)
        except Exception as e:
            vprint(f"Warning: Could not read existing config file {config_file}: {e}")

    # Update with new values if provided
    if email is not None:
        existing_config["email"] = email
    if elsevier_api_key is not None:
        existing_config["elsevier_api_key"] = elsevier_api_key
    if wiley_tdm_token is not None:
        existing_config["wiley_tdm_token"] = wiley_tdm_token
    if ieee_api_key is not None:
        existing_config["ieee_api_key"] = ieee_api_key

    try:
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(existing_config, f, indent=2)
        vprint(f"Saved credentials to {config_file}")
        return True
    except Exception as e:
        vprint(f"Error saving config file {config_file}: {e}")
        return False

def load_credentials(config_file: str = None):
    """
    Load credentials and API keys from a JSON configuration file.
    If the file doesn't exist or has empty values, prompt user for input and create/update the file.
    If no response from user after 30 seconds, report loading fails.
    Returns a dictionary with the loaded configuration.
    """
    global EMAIL, ELSEVIER_API_KEY, WILEY_TDM_TOKEN, IEEE_API_KEY
    
    if config_file is None:
        config_file = GETPAPERS_CONFIG_FILE
    
    default_config = {
        "email": "",
        "elsevier_api_key": "",
        "wiley_tdm_token": "",
        "ieee_api_key": ""
    }
    
    existing_config = default_config.copy()
    file_exists = os.path.exists(config_file)
    
    if file_exists:
        # Try to load existing config
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                existing_config = json.load(f)
            vprint(f"Loaded existing config from {config_file}")
        except (json.JSONDecodeError, Exception) as e:
            vprint(f"Error loading config file {config_file}: {e}")
            print(f"Configuration file {config_file} is corrupted. Will recreate.")
            file_exists = False

    # After loading, save to default config file if it does not exist
    if file_exists and config_file != GETPAPERS_CONFIG_FILE and not os.path.exists(GETPAPERS_CONFIG_FILE):
        save_credentials(
            email=existing_config.get("email"),
            elsevier_api_key=existing_config.get("elsevier_api_key"),
            wiley_tdm_token=existing_config.get("wiley_tdm_token"),
            ieee_api_key=existing_config.get("ieee_api_key"),
            config_file=GETPAPERS_CONFIG_FILE
        )
    
    # Check if any required fields are empty
    needs_input = (not file_exists or 
                   not existing_config.get("email", "").strip() or
                   not existing_config.get("elsevier_api_key", "").strip() or
                   not existing_config.get("wiley_tdm_token", "").strip() or
                   not existing_config.get("ieee_api_key", "").strip())
    
    if needs_input:
        if file_exists:
            vprint(f"Configuration file found but some values are empty: {config_file}")
        else:
            vprint(f"Configuration file not found: {config_file}")
        print("Please enter credentials:")
        print("You will be asked for the following information:")
        print("  - Email address (required, for Unpaywall and polite API usage)")
        print("  - Elsevier API Key (optional, for Elsevier Full-Text API)")
        print("  - Wiley TDM Token (optional, for Wiley TDM API)")
        print("  - IEEE API Key (optional, for IEEE Xplore API)")
        
        # Prompt for input with timeout
        try:
            if platform.system() != "Windows":
                # Unix-like systems - use signal
                def timeout_handler(signum, frame):
                    raise TimeoutError("Input timeout")
                
                signal.signal(signal.SIGALRM, timeout_handler)
                signal.alarm(60)  # 30 second timeout
                
                try:
                    current_email = existing_config.get("email", "")
                    email_prompt = f"Email (current: '{current_email}', press Enter to keep): " if current_email else "Email (required): "
                    email = input(email_prompt).strip()
                    if not email and current_email:
                        email = current_email
                    
                    current_elsevier = existing_config.get("elsevier_api_key", "")
                    elsevier_prompt = f"Elsevier API Key (current: '{current_elsevier[:10]}...', press Enter to keep): " if current_elsevier else "Elsevier API Key (press Enter to skip): "
                    elsevier_key = input(elsevier_prompt).strip()
                    if not elsevier_key and current_elsevier:
                        elsevier_key = current_elsevier
                    
                    current_wiley = existing_config.get("wiley_tdm_token", "")
                    wiley_prompt = f"Wiley TDM Token (current: '{current_wiley[:10]}...', press Enter to keep): " if current_wiley else "Wiley TDM Token (press Enter to skip): "
                    wiley_token = input(wiley_prompt).strip()
                    if not wiley_token and current_wiley:
                        wiley_token = current_wiley
                    
                    current_ieee = existing_config.get("ieee_api_key", "")
                    ieee_prompt = f"IEEE API Key (current: '{current_ieee[:10]}...', press Enter to keep): " if current_ieee else "IEEE API Key (press Enter to skip): "
                    ieee_key = input(ieee_prompt).strip()
                    if not ieee_key and current_ieee:
                        ieee_key = current_ieee
                    
                    signal.alarm(0)  # Cancel timeout
                    
                except TimeoutError:
                    signal.alarm(0)
                    print("\nTimeout: No input received within 30 seconds.")
                    return default_config
            else:
                # Windows - use threading with timeout
                def get_input(prompt, result_queue):
                    try:
                        result = input(prompt).strip()
                        result_queue.put(result)
                    except (KeyboardInterrupt, EOFError):
                        result_queue.put(None)
                
                def get_input_with_timeout(prompt, timeout_seconds=30):
                    result_queue = queue.Queue()
                    thread = threading.Thread(target=get_input, args=(prompt, result_queue))
                    thread.daemon = True
                    thread.start()
                    thread.join(timeout_seconds)
                    
                    if thread.is_alive():
                        print(f"\nTimeout: No input received within {timeout_seconds} seconds.")
                        return None
                    
                    try:
                        return result_queue.get_nowait()
                    except queue.Empty:
                        return None
                
                current_email = existing_config.get("email", "")
                email_prompt = f"Email (current: '{current_email}', press Enter to keep): " if current_email else "Email (required): "
                email = get_input_with_timeout(email_prompt)
                if email is None:
                    return default_config
                if not email and current_email:
                    email = current_email
                
                current_elsevier = existing_config.get("elsevier_api_key", "")
                elsevier_prompt = f"Elsevier API Key (current: '{current_elsevier[:10]}...', press Enter to keep): " if current_elsevier else "Elsevier API Key (press Enter to skip): "
                elsevier_key = get_input_with_timeout(elsevier_prompt)
                if elsevier_key is None:
                    return default_config
                if not elsevier_key and current_elsevier:
                    elsevier_key = current_elsevier
                
                current_wiley = existing_config.get("wiley_tdm_token", "")
                wiley_prompt = f"Wiley TDM Token (current: '{current_wiley[:10]}...', press Enter to keep): " if current_wiley else "Wiley TDM Token (press Enter to skip): "
                wiley_token = get_input_with_timeout(wiley_prompt)
                if wiley_token is None:
                    return default_config
                if not wiley_token and current_wiley:
                    wiley_token = current_wiley
                
                current_ieee = existing_config.get("ieee_api_key", "")
                ieee_prompt = f"IEEE API Key (current: '{current_ieee[:10]}...', press Enter to keep): " if current_ieee else "IEEE API Key (press Enter to skip): "
                ieee_key = get_input_with_timeout(ieee_prompt)
                if ieee_key is None:
                    return default_config
                if not ieee_key and current_ieee:
                    ieee_key = current_ieee
            
            # Create config with user input
            new_config = {
                "email": email or "",
                "elsevier_api_key": elsevier_key or "",
                "wiley_tdm_token": wiley_token or "",
                "ieee_api_key": ieee_key or ""
            }
            
            # Save to config file
            if save_credentials(email=new_config["email"], 
                              elsevier_api_key=new_config["elsevier_api_key"],
                              wiley_tdm_token=new_config["wiley_tdm_token"], 
                              ieee_api_key=new_config["ieee_api_key"],
                              config_file=config_file):
                vprint(f"Configuration file {'updated' if file_exists else 'created'}: {config_file}")
            else:
                vprint("Warning: Failed to save configuration file.")
            
            # Update global variables
            EMAIL = new_config["email"]
            ELSEVIER_API_KEY = new_config["elsevier_api_key"]
            WILEY_TDM_TOKEN = new_config["wiley_tdm_token"]
            IEEE_API_KEY = new_config["ieee_api_key"]
            
            return new_config
                
        except (KeyboardInterrupt, EOFError):
            print("\nConfiguration input cancelled.")
            return default_config
        except Exception as e:
            vprint(f"Error during input: {e}")
            return default_config
    
    # File exists and has all values, use existing config
    EMAIL = existing_config.get("email", EMAIL)
    ELSEVIER_API_KEY = existing_config.get("elsevier_api_key", ELSEVIER_API_KEY)
    WILEY_TDM_TOKEN = existing_config.get("wiley_tdm_token", WILEY_TDM_TOKEN)
    IEEE_API_KEY = existing_config.get("ieee_api_key", IEEE_API_KEY)
    
    vprint(f"Using existing credentials from {config_file}")
    return existing_config

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
    headers = {
        "User-Agent": f"PythonScript/1.0 (mailto:{EMAIL})",
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

async def is_open_access_unpaywall(doi: str, email: str = "anhduc.hoang1990@googlemail.com") -> bool:
    """
    Check if a DOI is open access using the Unpaywall API.
    Returns True if open access, False otherwise.
    """
    api_url = f"https://api.unpaywall.org/v2/{quote_plus(doi)}?email={quote_plus(email)}"
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
        'X-ELS-APIKey': ELSEVIER_API_KEY,
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
    Check if a single DOI is valid (resolves at doi.org or found in Crossref).
    """
    browser_headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36 Edg/124.0.2478.67"
        ),
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;"
            "q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,"
            "application/signed-exchange;v=b3;q=0.9"
        ),
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "DNT": "1",
        "Referer": "https://doi.org/",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-User": "?1",
    }
    json_headers = {
        "User-Agent": browser_headers["User-Agent"],
        "Accept": "application/json",
        "Referer": "https://doi.org/",
        "DNT": "1",
    }
    try:
        url = f"https://doi.org/{doi}"
        resp = requests.head(url, allow_redirects=True, timeout=20, headers=browser_headers)
        browser_ok = resp.status_code in (200, 301, 302)
        forbidden = resp.status_code == 403
        json_ok = False
        try:
            json_resp = requests.get(url, headers=json_headers, timeout=20)
            if json_resp.status_code == 200:
                try:
                    data = json_resp.json()
                    if "publisher" in data or "title" in data:
                        json_ok = True
                except Exception:
                    pass
            elif json_resp.status_code == 403:
                vprint(f"DOI {doi} returned 403 for JSON metadata, may be rate-limited, treating as valid")
                json_ok = True
        except Exception as e:
            vprint(f"Error fetching machine-readable metadata for DOI {doi}: {e}")

        if browser_ok and json_ok:
            return True
        elif browser_ok or json_ok or forbidden:
            vprint(f"DOI {doi} partially valid (browser_ok={browser_ok}, json_ok={json_ok}, forbidden={forbidden}), treating as valid")
            return True
        else:
            works = Works()
            try:
                result = works.doi(doi)
                if result:
                    vprint(f"DOI {doi} found in Crossref, treating as valid")
                    return True
                else:
                    vprint(f"DOI {doi} does not resolve at doi.org and not found in Crossref")
            except Exception as e:
                vprint(f"Error checking DOI in Crossref: {doi}: {e}")
    except Exception as e:
        vprint(f"Error checking DOI at doi.org: {doi}: {e}")
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

def extract_dois_from_text(text: str) -> list:
    """
    Extract DOI numbers from text content.
    Returns a list of unique, valid paper DOIs.
    Only keeps DOIs that resolve at https://doi.org/<doi> (HTTP 200, 301, 302).
    """
    dois = []

    ieee_doi_pattern = r'\b10\.1109/[A-Z]+(?:\.[0-9]{4})+\.[0-9]+'
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
        r'\b(10\.\d{4,9}/[A-Za-z0-9\-._;()/:]+)',
        ieee_doi_pattern,
    ]
    for pattern in doi_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        if matches:
            for match in matches:
                if isinstance(match, tuple):
                    # Extract the captured group (the DOI part starting with 10.)
                    doi_part = next((group for group in match if group.startswith('10.')), None)
                    if doi_part:
                        dois.append(doi_part)
                elif isinstance(match, str):
                    # For patterns without capture groups, extract the 10. part
                    doi_match = re.search(r'(10\.\d{4,9}/[A-Za-z0-9\-._;()/:]+)', match)
                    if doi_match:
                        dois.append(doi_match.group(1))
                    else:
                        dois.append(match)

    dois = list(dict.fromkeys(dois))

    url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+[^\s<>"{}|\\^`\[\].,;:!?]|https?://[^\s<>"{}|\\^`\[\]]+\.\.\.[^\s<>"{}|\\^`\[\]]+[^\s<>"{}|\\^`\[\].,;:!?]'
    urls = re.findall(url_pattern, text)
    vprint(f"Found {len(urls)} URLs in text for DOI extraction: {urls}")

    for url in urls:
        already_has_doi = False
        for pattern in [
            ieee_doi_pattern,
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
                    dois.append(doi)
                else:
                    vprint(f"Could not resolve PII {pii} to DOI")
            else:
                vprint(f"No PII found in ScienceDirect URL: {url}")
            continue

        if "mdpi.com" in url:
            mdpi_doi = extract_mdpi_doi_from_url(url)
            if mdpi_doi:
                dois.append(mdpi_doi)
            continue

        vprint(f"Checking URL for DOI: {url}")
        for doi_pattern in doi_patterns:
            page_dois = fetch_dois_from_url(url, doi_pattern)
            dois.extend(page_dois)

    unique_dois = list(dict.fromkeys(dois))
    return validate_dois(unique_dois)

def extract_dois_from_file(input_file: str):
    """Extract DOI numbers from a text file and write them to a new file"""
    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"Failed to read input file: {e}")
        return

    # Use the new extract_dois_from_text function
    filtered_dois = extract_dois_from_text(content)

    if not filtered_dois:
        print(f"No valid paper DOIs found in {input_file}")
        return

    base_name = os.path.splitext(input_file)[0]
    output_file = f"{base_name}.dois.txt"

    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            for doi in filtered_dois:
                f.write(f"{doi}\n")
        print(f"Extracted {len(filtered_dois)} paper DOIs from {input_file} to {output_file}")
        vprint(f"DOIs found: {filtered_dois}")
    except Exception as e:
        print(f"Failed to write DOIs to output file: {e}")

def extract_doi_from_pdf(pdf_file: str) -> str:
    """
    Extract the first DOI found in a PDF file.
    Returns the DOI string if found and valid (resolves at doi.org), else None.
    Only considers the first three pages of the PDF.
    Tries to preserve newlines when extracting text from PDF.
    """
    try:
        with open(pdf_file, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            text_chunks = []
            for i, page in enumerate(reader.pages):
                if i >= 3:
                    break
                try:
                    page_text = page.extract_text()
                    if page_text:
                        text_chunks.append(page_text)
                except Exception:
                    continue
            text = "\n".join(text_chunks)
    except Exception as e:
        print(f"Failed to read PDF file: {e}")
        return None

    dois = extract_dois_from_text(text)
    if not dois:
        return None

    doi = dois[0]
    return doi

async def search_documents(query: str, limit: int = 1):
    """
    Search for documents using StcGeck, Nexus bot, and Crossref in order.
    Build a StcGeck-style document with all fields empty, and iteratively fill fields
    by searching each source in order. Return up to the requested limit of results.
    Always tries all sources before returning results.
    """
    vprint(f"Searching for: {query} (limit={limit})")

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
            for scored in stc_results:
                doc = json.loads(scored.document)
                # Use DOI as key if present, else fallback to id or title
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
            vprint(f"StcGeck returned {len(stc_results)} results.")
        finally:
            await geck.stop()
    except Exception as e:
        vprint(f"StcGeck failed: {e}")

    # 2. Nexus bot
    try:
        vprint("Trying Nexus bot search...")
        nexus_results = await search_with_nexus_bot(query, limit)
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
        vprint(f"Nexus bot returned {len(nexus_results)} results.")
    except Exception as e:
        vprint(f"Nexus bot failed: {e}")

    # 3. Crossref
    try:
        vprint("Trying Crossref search...")
        crossref_results = await search_with_crossref(query, limit)
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
        vprint(f"Crossref returned {len(crossref_results)} results.")
    except Exception as e:
        vprint(f"Crossref failed: {e}")

    if not collected:
        vprint("No results found from any source.")
        return []

    # Wrap as ScoredDocument-like objects
    return [type('ScoredDocument', (), {'document': json.dumps(doc)})() for doc in list(collected.values())[:limit]]

async def search_with_nexus_bot(query: str, limit: int = 1):
    """
    Search for documents using the Nexus bot (functions imported from .nexus).
    Returns a list of ScoredDocument-like objects with a .document JSON string.
    Tries first without proxy, then with proxy if it fails.
    """
    try:
        TG_API_ID, TG_API_HASH, PHONE, BOT_USERNAME = await nexus.load_credentials_from_file(nexus.CREDENTIALS_FILE)
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
    Returns True if the DOI prefix matches known Elsevier prefixes
    and resolving https://doi.org/<doi> leads to an Elsevier site.
    """
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

    # Try to resolve the DOI and check if it leads to an Elsevier domain
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
    api_key: str = ELSEVIER_API_KEY # Use the global API key by default
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
    metadata_headers = {
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0",
        "X-ELS-APIKey": api_key,
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
        "X-ELS-APIKey": api_key,
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
    Returns True if the DOI prefix matches known Wiley prefixes
    and resolving https://doi.org/<doi> leads to a Wiley site.
    """
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

    # Try to resolve the DOI and check if it leads to a Wiley domain
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
    tdm_token: str = WILEY_TDM_TOKEN  # Use the global token by default
) -> bool:
    """
    Attempt to download a PDF from Wiley using the DOI and Wiley-TDM-Client-Token.
    Returns True if successful, else False.
    """
    if not tdm_token:
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
        "Wiley-TDM-Client-Token": tdm_token,
    }

    try:
        async with aiohttp.TCPConnector() as conn:
            async with aiohttp.ClientSession(connector=conn) as session:
                async with session.get(pdf_url, headers=headers, timeout=30, allow_redirects=True) as resp:
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
    email: str = "anhduc.hoang1990@googlemail.com"
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
        if await download_elsevier_pdf_by_doi(doi=doi, download_folder=download_folder, api_key=ELSEVIER_API_KEY):
            return True

    # Try Wiley API first if DOI is Wiley
    if is_wiley_doi(doi):
        print(f"DOI {doi} appears to be a Wiley article. Attempting Wiley TDM API download before Unpaywall...")
        if await download_wiley_pdf_by_doi(doi, download_folder, tdm_token=WILEY_TDM_TOKEN):
            return True

    try:
        safe_doi = doi.replace('/', '_')
        UnpywallCredentials(email)

        # Get all OA links (should include all PDF URLs)
        all_links = Unpywall.get_all_links(doi=doi)
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
                        async with session.get(pdf_url, headers=headers, timeout=60) as resp:
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
                        async with session.get(url, headers=oa_headers, timeout=60) as resp:
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
                                    async with session.get(pdf_candidate_url, headers=oa_headers, timeout=60) as pdf_resp:
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
        proxy_result = await nexus.decide_proxy_usage(TG_API_ID, TG_API_HASH, PHONE, nexus.SESSION_FILE, nexus.DEFAULT_PROXY_FILE)
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
            print(f"PDF file is not available from Nexus bot for DOI: {doi}.")
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

async def download_by_doi(doi: str, download_folder: str = DEFAULT_DOWNLOAD_FOLDER, db: str = "all", no_download: bool = False):
    # Extract DOI from input if possible (handles cases where input is a URL or contains a DOI)
    dois = extract_dois_from_text(doi)
    if dois:
        doi = dois[0]
    else:
        print(f"Input does not appear to be a valid DOI or DOI-containing string: {doi}")
        return False
    vprint(f"Starting download_by_doi for DOI: {doi}, folder: {download_folder}, db: {db}, no_download: {no_download}")
    results = await search_documents(doi, 1)
    
    if results:
        document = json.loads(results[0].document)
        print("Search result for DOI:")
        print(format_reference(document))
        if VERBOSE:
            print("Full document JSON:")
            print(json.dumps(document, indent=2))
        print('-----')
        
        id = document.get('id')
    else:
        print(f"No document found for DOI: {doi}")
        id = None

    if no_download:
        print("--no-download specified, skipping download.")
        return None

    # Check if the DOI is open access via Unpaywall
    is_oa = await is_open_access_unpaywall(doi)
    oa_status_text = "Open Access" if is_oa else "Closed Access"
    
    if is_oa:
        print(f"DOI {doi} is Open Access. Using Unpaywall for download...")
        if await download_from_unpaywall(doi, download_folder):
            print(f"\nDownload Summary:")
            print(f"Successfully downloaded: 1 PDF")
            print(f"  ✓ {doi} [{oa_status_text}]")
            return True
        print(f"\nDownload Summary:")
        print(f"Failed to download: 1 PDF")
        print(f"  ✗ {doi} [{oa_status_text}]")
        print(f"No PDF could be downloaded with this script for DOI: {doi}.")
        return False

    if not id and db in ["all", "nexus"]:
        print(f"No ID available for Nexus download for DOI: {doi}.")

    tried = False

    if db in ["all", "nexus"] and id:
        tried = True
        vprint(f"Trying Nexus download for id: {id}, doi: {doi}")
        if await download_from_nexus(id, doi, download_folder):
            print(f"\nDownload Summary:")
            print(f"Successfully downloaded: 1 PDF")
            print(f"  ✓ {doi} [{oa_status_text}]")
            return True
        print(f"PDF file is not available on the Nexus server for DOI: {doi}.")
        # Try Nexus bot as fallback
        print(f"Trying Nexus bot for DOI: {doi}...")
        if await download_from_nexus_bot(doi, download_folder):
            print(f"\nDownload Summary:")
            print(f"Successfully downloaded: 1 PDF")
            print(f"  ✓ {doi} [{oa_status_text}]")
            return True
        print(f"PDF file is not available from Nexus bot for DOI: {doi}.")

    if db in ["all", "scihub"]:
        tried = True
        print(f"Trying Sci-Hub for DOI: {doi}...")
        if await download_from_scihub(doi, download_folder):
            print(f"\nDownload Summary:")
            print(f"Successfully downloaded: 1 PDF")
            print(f"  ✓ {doi} [{oa_status_text}]")
            return True
        print(f"PDF file is not available on Sci-Hub for DOI: {doi}.")

    if db in ["all", "anna"]:
        tried = True
        print(f"Trying Anna's Archive for DOI: {doi}...")
        if await download_from_anna_archive(doi, download_folder):
            print(f"\nDownload Summary:")
            print(f"Successfully downloaded: 1 PDF")
            print(f"  ✓ {doi} [{oa_status_text}]")
            return True
        print(f"PDF file is not available on Anna's Archive for DOI: {doi}.")

    if db in ["all", "libgen"]:
        tried = True
        print(f"Trying LibGen for DOI: {doi}...")
        try:
            # Call the libgen module's download_by_doi function
            result = libgen.download_libgen_paper_by_doi(doi, dest_folder=download_folder)
            if result:
                print(f"\nDownload Summary:")
                print(f"Successfully downloaded: 1 PDF")
                print(f"  ✓ {doi} [{oa_status_text}]")
                return True
            else:
                print(f"PDF file is not available on LibGen for DOI: {doi}.")
        except Exception as e:
            print(f"Error downloading from LibGen for DOI {doi}: {e}")

    if db in ["all", "unpaywall"]:
        tried = True
        print(f"Trying Unpaywall for DOI: {doi}...")
        if await download_from_unpaywall(doi, download_folder):
            print(f"\nDownload Summary:")
            print(f"Successfully downloaded: 1 PDF")
            print(f"  ✓ {doi} [{oa_status_text}]")
            return True
        print(f"PDF file is not available on Unpaywall for DOI: {doi}.")

    # Special handling for Elsevier and Wiley DOIs
    if is_elsevier_doi(doi):
        print(f"DOI {doi} appears to be an Elsevier article. Attempting Elsevier Full-Text API download...")
        if await download_elsevier_pdf_by_doi(doi=doi, download_folder=download_folder, api_key=ELSEVIER_API_KEY):
            print(f"\nDownload Summary:")
            print(f"Successfully downloaded: 1 PDF")
            print(f"  ✓ {doi} [{oa_status_text}]")
            return True
        print(f"PDF file is not available from Elsevier Full-Text API for DOI: {doi}.")

    if is_wiley_doi(doi):
        print(f"DOI {doi} appears to be a Wiley article. Attempting Wiley TDM API download...")
        if await download_wiley_pdf_by_doi(doi, download_folder, tdm_token=WILEY_TDM_TOKEN):
            print(f"\nDownload Summary:")
            print(f"Successfully downloaded: 1 PDF")
            print(f"  ✓ {doi} [{oa_status_text}]")
            return True
        print(f"PDF file is not available from Wiley TDM API for DOI: {doi}.")

    if not tried:
        print(f"No valid database specified for DOI: {doi}.")
    
    # print(f"\nDownload Summary:")
    # print(f"Failed to download: 1 PDF")
    # print(f"  ✗ {doi} [{oa_status_text}]")
    return False

async def download_by_doi_list(doi_file: str, download_folder: str = DEFAULT_DOWNLOAD_FOLDER, db: str = "all", no_download: bool = False):
    vprint(f"Starting download_by_doi_list for file: {doi_file}, folder: {download_folder}, db: {db}, no_download: {no_download}")
    
    # Check if the file contains only DOIs (one per line)
    try:
        with open(doi_file, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip()]
        
        # Check if all lines are DOIs
        doi_pattern = r'^10\.\d{4,}[^\s]*[a-zA-Z0-9]$'
        all_dois = all(re.match(doi_pattern, line) for line in lines)
        
        if not all_dois:
            vprint(f"File {doi_file} does not contain only DOIs. Extracting DOIs...")
            extract_dois_from_file(doi_file)
            # Use the generated .dois.txt file
            base_name = os.path.splitext(doi_file)[0]
            doi_file = f"{base_name}.dois.txt"
            
            # Check if the extracted DOI file exists
            if not os.path.exists(doi_file):
                print(f"Error: DOI numbers cannot be extracted from {base_name}.txt.")
                return {}
            
            vprint(f"Using extracted DOI file: {doi_file}")
            
            # Read the new file
            with open(doi_file, "r", encoding="utf-8") as f:
                dois = [line.strip() for line in f if line.strip()]
        else:
            dois = lines
            
    except Exception as e:
        print(f"Failed to read DOI file: {e}")
        return {}

    download_results = {}
    successful_downloads = []
    failed_downloads = []
    
    for doi in dois:
        print(f"Processing DOI: {doi}")
        # Get open access status
        oa_status = await is_open_access_unpaywall(doi)
        oa_status_text = "Open Access" if oa_status else "Closed Access"
        
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
            
        elif result is False:
            download_results[doi] = ["failed", None]
            failed_downloads.append((doi, oa_status))
        else:  # result is None when no_download is True or no document found
            download_results[doi] = ["no_download" if no_download else "not_found", None]
    
    if not no_download:
        print(f"\nDownload Summary:")
        print(f"Successfully downloaded: {len(successful_downloads)} PDFs")
        if successful_downloads:
            for doi, oa_status in successful_downloads:
                oa_status_text = "Open Access" if oa_status else "Closed Access"
                print(f"  ✓ {doi} [{oa_status_text}]")
        
        print(f"Failed to download: {len(failed_downloads)} PDFs")
        if failed_downloads:
            for doi, oa_status in failed_downloads:
                oa_status_text = "Open Access" if oa_status else "Closed Access"
                print(f"  ✗ {doi} [{oa_status_text}]")
    
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

async def main():
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
        type=str,
        choices=["all", "nexus", "scihub", "anna", "unpaywall", "libgen"],
        default="all",
        help="Specify which database to use for downloading PDFs: all, nexus, scihub, anna, unpaywall, libgen (default: all)"
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
    args = argparser.parse_args()

    # Initialize Unpywall cache
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
    exclusive_options = [args.doi, args.doi_file, args.search, args.extract_doi_from_pdf]
    if sum(bool(opt) for opt in exclusive_options) > 1:
        print("Error: Only one of --doi, --doi-file, --search, or --extract-doi-from-pdf can be specified at a time.")
        sys.exit(1)

    # Set global verbose flag
    global VERBOSE
    VERBOSE = args.verbose

    # Credentials file
    credentials_file = args.credentials if args.credentials else GETPAPERS_CONFIG_FILE

    # Load credentials from credentials file
    load_credentials(credentials_file)

    # If only --credentials is specified, exit after loading credentials
    if args.credentials and not (args.doi or args.doi_file or args.search or args.extract_doi_from_pdf):
        print(f"Loaded credentials from file: {credentials_file}")
        sys.exit(0)

    if args.extract_doi_from_pdf:
        pdf_file = args.extract_doi_from_pdf
        doi = extract_doi_from_pdf(pdf_file)
        if doi:
            print(f"Extracted DOI from PDF: {doi}")
        else:
            print(f"No valid DOI found in PDF: {pdf_file}")
    elif args.doi:
        await download_by_doi(args.doi, download_folder=args.download_folder, db=args.db, no_download=args.no_download)
    elif args.search:
        await search_and_print(args.search, args.limit)
    elif args.doi_file:
        await download_by_doi_list(args.doi_file, download_folder=args.download_folder, db=args.db, no_download=args.no_download)
    else:
        print("Please specify --search <keyword|doi>, --doi <doi>, --doi-file <file>, or --extract-doi-from-pdf <pdf>.")

if __name__ == "__main__":
    # Use the recommended event loop policy for Windows
    if platform.system() == "Windows":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    asyncio.run(main())