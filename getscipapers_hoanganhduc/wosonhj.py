import os
import json
import platform
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
import time
import pickle
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select
import getpass
import argparse
import threading
import re
import readline
import glob
import requests as pyrequests
import requests
from . import getpapers
import ast
import datetime

# --- Configuration for Wosonhj Login ---
WOSONHJ_HOME_URL = "https://www.pidantuan.com"
WOSONHJ_LOGIN_URL = f"{WOSONHJ_HOME_URL}/member.php?mod=logging&action=login&referer="
USERNAME = ""
PASSWORD = ""

# --- Directory and Credentials Management ---

def get_cache_directory():
    system = platform.system()
    if system == "Windows":
        return os.path.join(os.environ.get('APPDATA', os.path.expanduser('~')), 'getscipapers', 'wosonhj')
    elif system == "Darwin":
        return os.path.join(os.path.expanduser('~'), 'Library', 'Application Support', 'getscipapers', 'wosonhj')
    else:
        return os.path.join(os.path.expanduser('~'), '.config', 'getscipapers', 'wosonhj')

def get_credentials_directory():
    return get_cache_directory()

cache_dir = get_cache_directory()
os.makedirs(cache_dir, exist_ok=True)
CACHE_FILE = os.path.join(cache_dir, 'wosonhj_cache.pkl')

credentials_dir = get_credentials_directory()
os.makedirs(credentials_dir, exist_ok=True)
CREDENTIALS_FILE = os.path.join(credentials_dir, 'credentials.json')

def get_default_download_folder():
    system = platform.system()
    if system == "Windows":
        base = os.environ.get('USERPROFILE', os.path.expanduser('~'))
        folder = os.path.join(base, 'Downloads', 'getscipapers', 'wosonhj')
    else:
        folder = os.path.join(os.path.expanduser('~'), 'Downloads', 'getscipapers', 'wosonhj')
    os.makedirs(folder, exist_ok=True)
    return folder

DEFAULT_DOWNLOAD_FOLDER = get_default_download_folder()

verbose = False

def debug_print(message):
    if verbose:
        print(f"🛠️ [DEBUG] {message}")

def info_print(message):
    print(f"ℹ️ {message}")

def success_print(message):
    print(f"✅ {message}")

def warning_print(message):
    print(f"⚠️ {message}")

def error_print(message):
    print(f"❌ {message}")

def load_credentials_from_file(filepath):
    global USERNAME, PASSWORD
    debug_print(f"Attempting to load credentials from: {filepath}")

    if not os.path.exists(filepath):
        warning_print(f"Credentials file not found: {filepath}")
        return None, None

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            credentials = json.load(f)

        username = credentials.get('wosonhj_username')
        password = credentials.get('wosonhj_password')

        if not username or not password:
            error_print("Invalid credentials file: missing wosonhj_username or wosonhj_password")
            return None, None

        success_print(f"Successfully loaded credentials for user: {username}")

        USERNAME = username
        PASSWORD = password

        # Update default credentials file if needed
        if os.path.abspath(filepath) != os.path.abspath(CREDENTIALS_FILE):
            need_update = True
            if os.path.exists(CREDENTIALS_FILE):
                try:
                    with open(CREDENTIALS_FILE, 'r', encoding='utf-8') as f2:
                        default_creds = json.load(f2)
                    if (default_creds.get('wosonhj_username') == username and
                        default_creds.get('wosonhj_password') == password):
                        need_update = False
                except Exception as e:
                    warning_print(f"Error reading default credentials file: {e}")
            if need_update:
                try:
                    with open(CREDENTIALS_FILE, 'w', encoding='utf-8') as f2:
                        json.dump({
                            "wosonhj_username": username,
                            "wosonhj_password": password
                        }, f2, ensure_ascii=False, indent=2)
                    info_print("Default credentials file updated with new credentials")
                except Exception as e:
                    error_print(f"Failed to update default credentials file: {e}")
        else:
            if not os.path.exists(CREDENTIALS_FILE):
                try:
                    with open(CREDENTIALS_FILE, 'w', encoding='utf-8') as f2:
                        json.dump({
                            "wosonhj_username": username,
                            "wosonhj_password": password
                        }, f2, ensure_ascii=False, indent=2)
                    info_print("Default credentials file created after loading credentials")
                except Exception as e:
                    error_print(f"Failed to create default credentials file: {e}")

        return username, password

    except json.JSONDecodeError as e:
        error_print(f"Invalid JSON in credentials file: {e}")
        return None, None
    except Exception as e:
        error_print(f"Error reading credentials file: {e}")
        return None, None

def set_default_config_dir(username, password):
    credentials = {
        "wosonhj_username": username,
        "wosonhj_password": password
    }
    with open(CREDENTIALS_FILE, "w", encoding="utf-8") as f:
        json.dump(credentials, f, ensure_ascii=False, indent=2)
    return CREDENTIALS_FILE

def get_chrome_driver(headless=True, enable_download=True, download_folder=None):
    debug_print(f"Creating Chrome driver (headless={headless})")
    options = webdriver.ChromeOptions()
    # Suppress DevTools logging
    options.add_experimental_option('excludeSwitches', ['enable-logging'])
    if headless:
        options.add_argument('--headless=new')
        options.add_argument('--disable-gpu')
    user_data_dir = os.path.join(cache_dir, "chrome_user_data")
    os.makedirs(user_data_dir, exist_ok=True)
    options.add_argument(f"--user-data-dir={user_data_dir}")
    debug_print(f"Using Chrome user data directory: {user_data_dir}")
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-logging')
    options.add_argument('--disable-gpu-logging')
    options.add_argument('--silent')
    options.add_argument('--log-level=3')
    options.add_argument("--disable-notifications")
    options.add_argument("--disable-popup-blocking")
    options.add_argument("--disable-infobars")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-web-security")
    options.add_argument("--allow-running-insecure-content")
    options.add_argument("--enable-unsafe-swiftshader")

    # Set download folder if enabled
    if enable_download:
        if download_folder is None:
            download_folder = DEFAULT_DOWNLOAD_FOLDER
        os.makedirs(download_folder, exist_ok=True)
        prefs = {
            "download.default_directory": download_folder,
            "download.prompt_for_download": False,
            "download.directory_upgrade": True
        }
        options.add_experimental_option("prefs", prefs)
        debug_print(f"Chrome will auto-download files to: {download_folder}")

    driver = webdriver.Chrome(options=options)
    debug_print("Chrome driver created successfully")
    return driver

def prompt_for_credentials_with_timeout(timeout=60):
    result = {}

    def ask():
        info_print("\nAutomatic login failed. Please enter your credentials manually (timeout in 60 seconds):")
        try:
            result['username'] = input("Username: ").strip()
            result['password'] = getpass.getpass("Password: ").strip()
        except Exception:
            result['username'] = None
            result['password'] = None

    thread = threading.Thread(target=ask)
    thread.daemon = True
    thread.start()
    thread.join(timeout)
    if thread.is_alive() or not result.get('username') or not result.get('password'):
        error_print("Login failed: No credentials provided within 60 seconds.")
        return None, None
    return result['username'], result['password']

def login_wosonhj():
    debug_print("Starting login_wosonhj()")
    driver = get_chrome_driver(headless=False)
    driver.get(WOSONHJ_LOGIN_URL)
    time.sleep(2)
    debug_print("Filling in username and password fields")
    driver.find_element(By.NAME, "username").send_keys(USERNAME)
    driver.find_element(By.NAME, "password").send_keys(PASSWORD)
    driver.find_element(By.NAME, "password").send_keys(Keys.RETURN)
    debug_print("Submitted login form, waiting for login to complete")
    time.sleep(5)
    debug_print("Login process finished")
    return driver

def login_and_navigate_wosonhj(url, headless=True, enable_download=True, download_folder=None):
    global USERNAME, PASSWORD
    debug_print(f"Starting login_and_navigate_wosonhj to: {url}")
    driver = get_chrome_driver(headless=headless, enable_download=enable_download, download_folder=download_folder)

    try:
        debug_print("Navigating to homepage")
        max_retries = 3
        for attempt in range(max_retries):
            try:
                driver.get(WOSONHJ_HOME_URL)
                debug_print(f"Homepage loaded successfully on attempt {attempt + 1}")
                break
            except Exception as e:
                warning_print(f"Attempt {attempt + 1} failed: {e}")
                if attempt == max_retries - 1:
                    error_print(f"Failed to load homepage after {max_retries} attempts")
                    driver.quit()
                    return None
                time.sleep(2)

        cache_valid = False
        if os.path.exists(CACHE_FILE):
            debug_print(f"Loading cache from {CACHE_FILE}")
            with open(CACHE_FILE, 'rb') as f:
                cache = pickle.load(f)
            for cookie in cache:
                driver.add_cookie(cookie)
            debug_print(f"Loaded {len(cache)} cookies from cache")

            debug_print("Testing cache validity")
            driver.get(WOSONHJ_HOME_URL)
            driver.get(WOSONHJ_LOGIN_URL)
            time.sleep(10)
            current_url = driver.current_url
            debug_print(f"After visiting login page, current URL: {current_url}")
            if current_url.startswith(WOSONHJ_HOME_URL) and current_url != WOSONHJ_LOGIN_URL:
                success_print("Cache is valid, already logged in (redirected to homepage)")
                cache_valid = True
            else:
                warning_print("Cache is invalid or expired, proceeding with login")
                cache_valid = False
        else:
            debug_print("No cache file found")

        if not cache_valid:
            info_print("Performing full login process")
            username, password = load_credentials_from_file(CREDENTIALS_FILE)
            if not username or not password:
                debug_print("Using hardcoded credentials")
                username, password = USERNAME, PASSWORD

            login_successful = False
            try:
                debug_print("Navigating to login page")
                driver.get(WOSONHJ_LOGIN_URL)
                wait = WebDriverWait(driver, 10)

                debug_print("Waiting for username input field")
                username_input = wait.until(EC.presence_of_element_located((By.NAME, 'username')))
                password_input = driver.find_element(By.NAME, 'password')

                debug_print("Entering credentials")
                username_input.send_keys(username)
                password_input.send_keys(password)
                password_input.send_keys(Keys.RETURN)

                debug_print("Waiting for login redirect")
                time.sleep(5)
                driver.get(WOSONHJ_LOGIN_URL)
                time.sleep(10)
                current_url = driver.current_url
                debug_print(f"After login, visiting login page, current URL: {current_url}")
                if current_url.startswith(WOSONHJ_HOME_URL) and current_url != WOSONHJ_LOGIN_URL:
                    success_print("Login successful (redirected to homepage)")
                    login_successful = True
                else:
                    error_print("Login failed - still not logged in")
                    login_successful = False

            except Exception as e:
                error_print(f"Login with existing credentials failed: {e}")
                login_successful = False

            if not login_successful:
                warning_print("Automatic login failed, requesting manual credentials")
                manual_username, manual_password = prompt_for_credentials_with_timeout(timeout=60)
                if not manual_username or not manual_password:
                    error_print("Invalid credentials provided or timeout reached.")
                    driver.quit()
                    return None

                set_default_config_dir(manual_username, manual_password)
                USERNAME, PASSWORD = manual_username, manual_password

                try:
                    driver.get(WOSONHJ_LOGIN_URL)
                    wait = WebDriverWait(driver, 10)
                    username_input = wait.until(EC.presence_of_element_located((By.NAME, 'username')))
                    password_input = driver.find_element(By.NAME, 'password')
                    username_input.clear()
                    password_input.clear()
                    username_input.send_keys(manual_username)
                    password_input.send_keys(manual_password)
                    password_input.send_keys(Keys.RETURN)
                    debug_print("Manual credentials submitted, waiting for login")
                    time.sleep(5)
                    driver.get(WOSONHJ_LOGIN_URL)
                    time.sleep(10)
                    current_url = driver.current_url
                    debug_print(f"After manual login, visiting login page, current URL: {current_url}")
                    if current_url.startswith(WOSONHJ_HOME_URL) and current_url != WOSONHJ_LOGIN_URL:
                        success_print("Manual login successful (redirected to homepage)")
                        debug_print(f"Saving cache after manual login to {CACHE_FILE}")
                        with open(CACHE_FILE, 'wb') as f:
                            pickle.dump(driver.get_cookies(), f)
                        info_print("Cache saved successfully after manual login")
                        success_print("Login successful! Credentials have been saved for future use.")
                    else:
                        error_print("Manual login failed - still not logged in")
                        error_print("Manual login failed. Please check your credentials.")
                        driver.quit()
                        return None
                except Exception as e:
                    error_print(f"Manual login failed: {e}")
                    driver.quit()
                    return None
            else:
                debug_print(f"Saving cache to {CACHE_FILE}")
                with open(CACHE_FILE, 'wb') as f:
                    pickle.dump(driver.get_cookies(), f)
                info_print("Cache saved successfully")

        debug_print(f"Navigating to target URL: {url}")
        driver.get(url)
        debug_print("Navigation complete")
        return driver

    except Exception as e:
        error_print(f"Error in login_and_navigate_wosonhj: {e}")
        error_print(f"Failed to login and navigate to {url}: {e}")
        driver.quit()
        return None

def clear_default_cache_and_config():
    """Delete the default cache and credentials files if they exist."""
    if os.path.exists(CACHE_FILE):
        try:
            os.remove(CACHE_FILE)
            info_print(f"Deleted cache file: {CACHE_FILE}")
        except Exception as e:
            warning_print(f"Failed to delete cache file: {e}")
    if os.path.exists(CREDENTIALS_FILE):
        try:
            os.remove(CREDENTIALS_FILE)
            info_print(f"Deleted credentials file: {CREDENTIALS_FILE}")
        except Exception as e:
            warning_print(f"Failed to delete credentials file: {e}")

def fetch_user_info(headless=True):
    """
    Login and fetch user info, return as dict
    """
    driver = login_and_navigate_wosonhj(WOSONHJ_HOME_URL, headless=headless)
    if driver is None:
        error_print("Failed to login and fetch user info.")
        return None

    time.sleep(3)
    user_info_url = None
    try:
        lis = driver.find_elements(By.CSS_SELECTOR, 'li.ren_top_xlkongjian a')
        for a in lis:
            href = a.get_attribute("href")
            if href and f"{WOSONHJ_HOME_URL}/cuid-" in href and href.endswith(".html"):
                user_info_url = href
                break
    except Exception as e:
        error_print(f"Error finding user info URL: {e}")

    if not user_info_url:
        error_print("Could not find user info URL.")
        driver.quit()
        return None

    driver.get(user_info_url)
    time.sleep(3)

    info = {}
    try:
        page_source = driver.page_source
        li_pattern = r'<li>\s*<em class="ren_gxxx_lb">([^<]+)</em>\s*<div class="ren_lb_mbn[^>]*>(?:<span[^>]*>)?(.*?)(?:</span>)?</div>\s*</li>'
        li_matches = re.findall(li_pattern, page_source, re.S)
        for label, value in li_matches:
            value = re.sub(r'<[^>]+>', '', value).strip()
            info[label] = value

        stats_pattern = r'<a[^>]*>(Points|points|Replies|Threads)[^<]*<span class="ren_gxxx_tc">([^<]+)</span></a>'
        stats_matches = re.findall(stats_pattern, page_source, re.S)
        for label, value in stats_matches:
            label = label.capitalize()
            value = value.strip()
            info[label] = value
    except Exception as e:
        error_print(f"Failed to parse user info: {e}")
        info = None

    driver.quit()
    return info

def print_user_info(info):
    """
    Print user info dict with icons
    """
    if not info:
        error_print("No user info to print.")
        return

    icon_map = {
        "Username": "👤",
        "Email": "📧",
        "Points": "💎",
        "Threads": "📝",
        "Replies": "💬",
        "Registration time": "🕒",
        "Last visit": "👀",
        "User group": "🏷️",
        "Gender": "⚧️",
        "Birthday": "🎂",
        "Location": "📍",
        "Posts": "✉️",
        "Status": "🔖",
        "Online time": "⏳",
        "Homepage": "🏠",
        "QQ": "💬",
        "WeChat": "💬",
        "Mobile": "📱",
        "Signature": "✒️",
    }

    print("\n👤 === Member Information ===")
    for k, v in info.items():
        icon = icon_map.get(k, "🔹")
        print(f"  {icon} {k}: {v}")
    print("=========================\n")

PUBLISHER_TYPEIDS = {
    "Other": 34,
    "Elsevier": 15,
    "Ovid": 31,
    "OSA": 28,
    "Springer": 18,
    "Wiley": 16,
    "Oxford": 24,
    "ACS": 21,
    "Taylor&Francis": 23,
    "AHA": 32,
    "Emerald": 37,
    "APA": 25,
    "IEEE": 19,
    "Cambridge": 38,
    "Bentham": 26,
    "IOP": 33,
    "IGI": 43,
    "RSC": 20,
    "SAGE": 30,
    "JAMA": 39,
    "Liebert": 45,
    "BMJ": 29,
    "Nature": 17,
    "AAAS": 22,
    "SPIE": 40,
    "Brill": 47,
    "World Scientific": 41,
    "AACR": 27,
}

def normalize_publisher_name(name):
    """
    Normalize publisher name and map to corresponding typeid.
    Returns typeid if found, else typeid for 'Other'.
    """
    if not name:
        return PUBLISHER_TYPEIDS["Other"]
    name = name.strip().lower()
    mapping = {k.lower(): v for k, v in PUBLISHER_TYPEIDS.items()}
    # Try exact match
    if name in mapping:
        return mapping[name]
    # Try partial match
    for k in mapping:
        if name in k:
            return mapping[k]
    # Try removing special characters and spaces
    name_clean = re.sub(r'[^a-z0-9]', '', name)
    for k in mapping:
        k_clean = re.sub(r'[^a-z0-9]', '', k)
        if name_clean == k_clean:
            return mapping[k]
    # Default to 'Other'
    return PUBLISHER_TYPEIDS["Other"]

def fetch_request_details(request_link, headless=True, driver=None):
    """
    Given a request link, fetch more details about the request (e.g., DOI number).
    Returns a dict with additional info (e.g., 'doi').
    Always performs this function in a new tab.
    If driver is provided, reuse it; otherwise, create a new one.
    """
    details = {}
    created_driver = False
    tab_opened = False

    if driver is None:
        driver = login_and_navigate_wosonhj(WOSONHJ_HOME_URL, headless=headless)
        created_driver = True

    if driver is None:
        error_print(f"Failed to open browser for request details: {request_link}")
        return details

    try:
        # Open a new tab and switch to it
        driver.execute_script(f"window.open('{request_link}', '_blank');")
        time.sleep(1)
        tabs = driver.window_handles
        driver.switch_to.window(tabs[-1])
        tab_opened = True

        time.sleep(2)
        # Try to find DOI in the page source using regex
        page_source = driver.page_source
        doi_match = re.search(r'(10\.\d{4,9}/[-._;()/:A-Z0-9]+)', page_source, re.I)
        if doi_match:
            details['doi'] = doi_match.group(1)
        else:
            # Try to find DOI in a specific element if available
            try:
                doi_elem = driver.find_element(By.XPATH, "//span[contains(text(),'DOI')]/following-sibling::*[1]")
                details['doi'] = doi_elem.text.strip()
            except Exception:
                details['doi'] = ""
    except Exception as e:
        debug_print(f"Error fetching request details: {e}")
        details['doi'] = ""
    finally:
        # Close the tab if opened
        if tab_opened:
            driver.close()
            # Switch back to the first tab
            if driver.window_handles:
                driver.switch_to.window(driver.window_handles[0])
        if created_driver:
            driver.quit()
    return details

def get_active_requests(limit=20, order_by_point=False, publisher=None, headless=True, driver=None):
    """
    Fetch active requests from Wosonhj, optionally filtered by publisher.
    Returns a list of dicts with request info, including DOI if available.
    Handles stale element reference errors gracefully.
    Uses normalize_publisher_name for publisher typeid mapping.
    Supports publisher=None, a single publisher name, or a comma-separated list of publisher names.
    If publisher is None, lists publishers and asks user to select; if no selection, fetches all requests (no publisher filter).
    If multiple publishers are specified, fetch at most 'limit' requests for each publisher.
    """
    all_requests = []
    page = 1
    typeids = []

    url_base = f"{WOSONHJ_HOME_URL}/forum.php?status=waiting"
    created_driver = False

    # Handle publisher argument: None, int, str, or comma-separated str
    if publisher is None:
        publisher_names = list(PUBLISHER_TYPEIDS.keys())
        print("\n📚 === Available Publishers ===")
        for idx, name in enumerate(publisher_names, 1):
            print(f"{idx}. {name}")
        print("=============================")
        print("Select publisher(s) by number or range (e.g. 1,3-5). Press Enter to skip (no publisher filter).")

        selected_indices = []

        def parse_indices(response):
            items = [item.strip() for item in response.split(",") if item.strip()]
            for item in items:
                if "-" in item:
                    try:
                        start, end = map(int, item.split("-", 1))
                        for i in range(start, end + 1):
                            if 1 <= i <= len(publisher_names):
                                selected_indices.append(i - 1)
                    except Exception:
                        warning_print(f"Invalid range: {item}")
                elif item.isdigit():
                    idx = int(item)
                    if 1 <= idx <= len(publisher_names):
                        selected_indices.append(idx - 1)
                else:
                    warning_print(f"Invalid selection: {item}")

        response = [None]

        def ask():
            try:
                response[0] = input("Publisher(s): ").strip()
            except Exception:
                response[0] = None

        t = threading.Thread(target=ask)
        t.daemon = True
        t.start()
        t.join(60)
        if t.is_alive():
            info_print("No response within 60 seconds. Fetching all requests (no publisher filter).")
        elif not response[0]:
            info_print("No selection made. Fetching all requests (no publisher filter).")
        else:
            parse_indices(response[0])

        # If no valid selection, fetch all requests (no publisher filter)
        if selected_indices:
            typeids = [normalize_publisher_name(publisher_names[i]) for i in selected_indices]
        else:
            typeids = []

    else:
        # Accept int, str, or comma-separated str
        if isinstance(publisher, int):
            typeids = [publisher]
        elif isinstance(publisher, str):
            publisher = publisher.strip()
            if "," in publisher:
                names = [p.strip() for p in publisher.split(",") if p.strip()]
                typeids = [normalize_publisher_name(name) for name in names]
            else:
                typeids = [normalize_publisher_name(publisher)]
        else:
            typeids = [normalize_publisher_name(str(publisher))]

    try:
        if driver is None:
            driver = login_and_navigate_wosonhj(url_base, headless=headless)
            created_driver = True
        else:
            driver.get(url_base)
        if driver is None:
            error_print("Failed to login and fetch requests.")
            return all_requests

        # If typeids is empty, fetch all requests (no publisher filter)
        if not typeids:
            page = 1
            while len(all_requests) < limit:
                url = f"{url_base}&page={page}"
                if order_by_point:
                    url += "&order=point"
                debug_print(f"Fetching requests from: {url}")
                driver.get(url)
                time.sleep(3)
                try:
                    items = driver.find_elements(By.CSS_SELECTOR, 'li.ren-reward-list-li')
                    if not items:
                        debug_print("No more requests found on this page.")
                        break

                    for item in items:
                        try:
                            item_id = item.get_attribute("id")
                            if item_id:
                                try:
                                    item = driver.find_element(By.ID, item_id)
                                except Exception:
                                    pass

                            summary_div = item.find_element(By.CSS_SELECTOR, 'div.ren-list-summary')
                            author_elem = summary_div.find_element(By.CSS_SELECTOR, 'div.ren-reward-us a.ren-index-us-name')
                            author = author_elem.text.strip() if author_elem else ""
                            time_elem = summary_div.find_element(By.CSS_SELECTOR, 'div.ren-reward-us span.time span')
                            post_time = time_elem.get_attribute('title') if time_elem else time_elem.text.strip() if time_elem else ""
                            h2_elem = summary_div.find_element(By.TAG_NAME, 'h2')
                            a_elem = h2_elem.find_element(By.CSS_SELECTOR, 'a[target="_blank"]')
                            link = a_elem.get_attribute('href') if a_elem else ""
                            icon_elem = a_elem.find_elements(By.CSS_SELECTOR, 'span img')
                            icon_url = icon_elem[0].get_attribute('src') if icon_elem else ""
                            title_spans = a_elem.find_elements(By.TAG_NAME, 'span')
                            title = ""
                            if len(title_spans) > 1:
                                title = title_spans[-1].text.strip()
                            elif title_spans:
                                title = title_spans[0].text.strip()
                            publisher_elem = summary_div.find_elements(By.CSS_SELECTOR, 'div.ren-summary-tag a')
                            publisher_name = publisher_elem[0].text.strip() if publisher_elem else ""
                            box_div = item.find_element(By.CSS_SELECTOR, 'div.ren-reward-list-box')
                            views_elem = box_div.find_elements(By.CSS_SELECTOR, 'div.views')
                            points = views_elem[0].text.split()[0].strip() if views_elem else ""
                            replies_elem = box_div.find_elements(By.CSS_SELECTOR, 'div.replies')
                            replies = replies_elem[0].text.split()[0].strip() if replies_elem else ""

                            details = fetch_request_details(link, headless=headless, driver=driver)
                            doi = details.get('doi', "")

                            all_requests.append({
                                "title": title,
                                "link": link,
                                "points": points,
                                "author": author,
                                "post_time": post_time,
                                "publisher": publisher_name,
                                "replies": replies,
                                "icon_url": icon_url,
                                "doi": doi
                            })
                            if len(all_requests) >= limit:
                                break
                        except Exception as e:
                            if "stale element reference" in str(e):
                                warning_print("Skipped a request item due to stale element reference.")
                                continue
                            debug_print(f"Error parsing request item: {e}")
                    if len(items) == 0 or len(all_requests) >= limit:
                        break
                    page += 1
                except Exception as e:
                    error_print(f"Failed to fetch requests: {e}")
                    break
        else:
            # Loop for each typeid (publisher filter)
            for typeid in typeids:
                page = 1
                publisher_requests = []
                while len(publisher_requests) < limit:
                    url = f"{url_base}&page={page}"
                    if order_by_point:
                        url += "&order=point"
                    if typeid:
                        url += f"&typeid={typeid}"
                    debug_print(f"Fetching requests from: {url}")
                    driver.get(url)
                    time.sleep(3)
                    try:
                        items = driver.find_elements(By.CSS_SELECTOR, 'li.ren-reward-list-li')
                        if not items:
                            debug_print("No more requests found on this page.")
                            break

                        for item in items:
                            try:
                                item_id = item.get_attribute("id")
                                if item_id:
                                    try:
                                        item = driver.find_element(By.ID, item_id)
                                    except Exception:
                                        pass

                                summary_div = item.find_element(By.CSS_SELECTOR, 'div.ren-list-summary')
                                author_elem = summary_div.find_element(By.CSS_SELECTOR, 'div.ren-reward-us a.ren-index-us-name')
                                author = author_elem.text.strip() if author_elem else ""
                                time_elem = summary_div.find_element(By.CSS_SELECTOR, 'div.ren-reward-us span.time span')
                                post_time = time_elem.get_attribute('title') if time_elem else time_elem.text.strip() if time_elem else ""
                                h2_elem = summary_div.find_element(By.TAG_NAME, 'h2')
                                a_elem = h2_elem.find_element(By.CSS_SELECTOR, 'a[target="_blank"]')
                                link = a_elem.get_attribute('href') if a_elem else ""
                                icon_elem = a_elem.find_elements(By.CSS_SELECTOR, 'span img')
                                icon_url = icon_elem[0].get_attribute('src') if icon_elem else ""
                                title_spans = a_elem.find_elements(By.TAG_NAME, 'span')
                                title = ""
                                if len(title_spans) > 1:
                                    title = title_spans[-1].text.strip()
                                elif title_spans:
                                    title = title_spans[0].text.strip()
                                publisher_elem = summary_div.find_elements(By.CSS_SELECTOR, 'div.ren-summary-tag a')
                                publisher_name = publisher_elem[0].text.strip() if publisher_elem else ""
                                box_div = item.find_element(By.CSS_SELECTOR, 'div.ren-reward-list-box')
                                views_elem = box_div.find_elements(By.CSS_SELECTOR, 'div.views')
                                points = views_elem[0].text.split()[0].strip() if views_elem else ""
                                replies_elem = box_div.find_elements(By.CSS_SELECTOR, 'div.replies')
                                replies = replies_elem[0].text.split()[0].strip() if replies_elem else ""

                                details = fetch_request_details(link, headless=headless, driver=driver)
                                doi = details.get('doi', "")

                                publisher_requests.append({
                                    "title": title,
                                    "link": link,
                                    "points": points,
                                    "author": author,
                                    "post_time": post_time,
                                    "publisher": publisher_name,
                                    "replies": replies,
                                    "icon_url": icon_url,
                                    "doi": doi
                                })
                                if len(publisher_requests) >= limit:
                                    break
                            except Exception as e:
                                if "stale element reference" in str(e):
                                    warning_print("Skipped a request item due to stale element reference.")
                                    continue
                                debug_print(f"Error parsing request item: {e}")
                        if len(items) == 0 or len(publisher_requests) >= limit:
                            break
                        page += 1
                    except Exception as e:
                        error_print(f"Failed to fetch requests: {e}")
                        break
                all_requests.extend(publisher_requests)
    finally:
        if created_driver and driver:
            driver.quit()
    return all_requests

def print_requests(requests, header="📄 === Requests ==="):
    """
    Print a list of requests (active, waiting, fulfilled) with details and icons.
    Prints all available fields: publisher, title, points, replies, author, post_time, views, link, doi.
    Only prints non-empty fields.
    Optional header can be set via the 'header' argument.
    """
    if not requests:
        error_print("No requests to print.")
        return

    print(f"\n{header}")
    for idx, req in enumerate(requests, 1):
        line = f"{idx}."
        if req.get('publisher'):
            line += f" [{req['publisher']}]"
        if req.get('title'):
            line += f" {req['title']}"
        print(line)
        details = []
        if req.get('points'):
            details.append(f"💎 Points: {req['points']}")
        if req.get('replies'):
            details.append(f"💬 Replies: {req['replies']}")
        if req.get('views'):
            details.append(f"👁️ Views: {req['views']}")
        if req.get('author'):
            details.append(f"👤 Author: {req['author']}")
        if req.get('post_time'):
            details.append(f"🕒 Time: {req['post_time']}")
        if details:
            print("    " + " | ".join(details))
        if req.get('link'):
            print(f"    🔗 Link: {req['link']}")
        if req.get('doi'):
            print(f"    📖 DOI: {req['doi']}")
    print("=========================\n")

def prompt_file_path(message="File path: ", timeout=60):
    """
    Prompt user for a file path with autocomplete support and custom message.
    Returns the entered file path as a string, or None if timeout.
    """
    def complete_path(text, state):
        line = readline.get_line_buffer().split()
        if '~' in text:
            text = os.path.expanduser(text)
        return (glob.glob(text + '*') + [None])[state]

    try:
        readline.set_completer_delims(' \t\n;')
        readline.parse_and_bind("tab: complete")
        readline.set_completer(complete_path)
    except Exception:
        pass  # Autocomplete may not work on all platforms

    file_path = [None]

    def ask():
        try:
            file_path[0] = input(message).strip()
        except Exception:
            error_print("Failed to read file path.")
            file_path[0] = None

    t = threading.Thread(target=ask)
    t.daemon = True
    t.start()
    t.join(timeout)
    if t.is_alive() or not file_path[0]:
        error_print(f"No file path provided within {timeout} seconds.")
        return None
    return file_path[0]

def solve_active_requests(limit=20, order_by_point=False, publisher=None, headless=True, driver=None):
    """
    List active requests using get_active_requests, prompt user to select one or more, and upload a file to help.
    Allows user to quit by entering 'q' or 'quit' at any prompt.
    Handles file upload, including temp.sh for large files.
    """
    FILE_SIZE_LIMIT_MB = 20
    FILE_SIZE_LIMIT = FILE_SIZE_LIMIT_MB * 1024 * 1024

    # List active requests using get_active_requests
    requests = get_active_requests(
        limit=limit,
        order_by_point=order_by_point,
        publisher=publisher,
        headless=headless,
        driver=driver
    )

    created_driver = driver is None

    if not requests:
        error_print("No active requests found.")
        if created_driver and driver:
            driver.quit()
        return

    print_requests(requests)

    print("Select request(s) to help (e.g. 1,3-5). Type 'q' or 'quit' to exit:")
    selected_indices = []

    def parse_indices(response):
        items = [item.strip() for item in response.split(",") if item.strip()]
        for item in items:
            if item.lower() in ("q", "quit"):
                return "quit"
            if "-" in item:
                try:
                    start, end = map(int, item.split("-", 1))
                    for i in range(start, end + 1):
                        if 1 <= i <= len(requests):
                            selected_indices.append(i - 1)
                except Exception:
                    warning_print(f"Invalid range: {item}")
            elif item.isdigit():
                idx = int(item)
                if 1 <= idx <= len(requests):
                    selected_indices.append(idx - 1)
            else:
                warning_print(f"Invalid selection: {item}")

    try:
        response = input("Request(s): ").strip()
        if response.lower() in ("q", "quit"):
            info_print("Quitting as requested by user.")
            if created_driver and driver:
                driver.quit()
            return
        if response:
            quit_flag = parse_indices(response)
            if quit_flag == "quit":
                info_print("Quitting as requested by user.")
                if created_driver and driver:
                    driver.quit()
                return
    except Exception:
        error_print("Failed to read selection.")
        if created_driver and driver:
            driver.quit()
        return

    if not selected_indices:
        info_print("No valid request selected.")
        if created_driver and driver:
            driver.quit()
        return

    for idx in selected_indices:
        req = requests[idx]
        info_print(f"Solving request: {req.get('title', '')} ({req.get('link', '')})")
        if driver is None:
            req_driver = login_and_navigate_wosonhj(req.get('link', ''), headless=headless)
        else:
            driver.get(req.get('link', ''))
            req_driver = driver

        if req_driver is None:
            error_print("Failed to open request page.")
            continue

        file_path = prompt_file_path("Please provide the file path to upload for this request (Tab for autocomplete, or type 'q' to quit): ", timeout=120)
        if file_path is None or file_path.lower() in ("q", "quit"):
            info_print("Quitting as requested by user.")
            if req_driver is not driver:
                req_driver.quit()
            break

        if not os.path.isfile(file_path):
            error_print(f"File not found: {file_path}")
            if req_driver is not driver:
                req_driver.quit()
            continue

        file_size = os.path.getsize(file_path)
        upload_path = file_path
        temp_txt_created = False

        if file_size > FILE_SIZE_LIMIT:
            info_print(f"File size exceeds {FILE_SIZE_LIMIT_MB}MB. Uploading to temp.sh instead.")
            try:
                with open(file_path, "rb") as f:
                    resp = pyrequests.post("https://temp.sh", files={"file": f})
                if resp.status_code == 200:
                    temp_url = resp.text.strip().splitlines()[-1]
                    info_print(f"Uploaded to temp.sh: {temp_url}")
                    temp_txt_path = os.path.join(os.path.dirname(file_path), "download_urls.txt")
                    with open(temp_txt_path, "w", encoding="utf-8") as txtf:
                        txtf.write(temp_url + "\n")
                    upload_path = temp_txt_path
                    temp_txt_created = True
                else:
                    error_print(f"Failed to upload to temp.sh: {resp.status_code}")
                    if req_driver is not driver:
                        req_driver.quit()
                    continue
            except Exception as e:
                error_print(f"Error uploading to temp.sh: {e}")
                if req_driver is not driver:
                    req_driver.quit()
                continue

        try:
            upload_span = None
            try:
                upload_span = req_driver.find_element(By.ID, "spanButtonPlaceholder")
            except Exception:
                debug_print("spanButtonPlaceholder not found, trying alternative file input search.")

            file_inputs = req_driver.find_elements(By.CSS_SELECTOR, "input[type='file']")
            upload_input = None
            for inp in file_inputs:
                if inp.is_displayed() or inp.get_attribute("id") or inp.get_attribute("name"):
                    upload_input = inp
                    break
            if not upload_input and upload_span:
                try:
                    parent = upload_span.find_element(By.XPATH, "..")
                    upload_input = parent.find_element(By.CSS_SELECTOR, "input[type='file']")
                except Exception:
                    pass
            if not upload_input:
                try:
                    upload_input = req_driver.find_element(By.CSS_SELECTOR, "input[type='file']")
                except Exception:
                    error_print("Failed to locate file input for upload.")
                    if req_driver is not driver:
                        req_driver.quit()
                    continue

            try:
                wait_time = min(max(int(file_size / (1024 * 1024)), 5), 60)
                debug_print(f"Calculated wait time for upload: {wait_time}s")

                req_driver.execute_script("""
                    var input = arguments[0];
                    input.style.display = 'block';
                    input.style.visibility = 'visible';
                """, upload_input)

                upload_input.send_keys(upload_path)
                info_print("File selected for upload, waiting for upload to finish...")

                attachlist_found = False
                for _ in range(wait_time * 2):
                    try:
                        attachlist = req_driver.find_element(By.ID, "attachlist")
                        if attachlist and attachlist.text and os.path.basename(upload_path) in attachlist.text:
                            attachlist_found = True
                            break
                    except Exception:
                        pass
                    time.sleep(0.5)
                if attachlist_found:
                    success_print("Upload finished and file listed in attachlist.")
                else:
                    warning_print("Upload may not have finished or file not listed in attachlist.")

                try:
                    textarea = req_driver.find_element(By.ID, "fastpostmessage")
                    if textarea.is_displayed():
                        if temp_txt_created:
                            message = f"File too large, uploaded to temp.sh. See download_urls.txt for link."
                        else:
                            message = f"Auto-uploaded file for request: {req.get('title', '')}"
                        textarea.clear()
                        textarea.send_keys(message)
                except Exception:
                    pass

                try:
                    submit_btn = req_driver.find_element(By.ID, "fastpostsubmit")
                    submit_btn.click()
                    info_print("Submitted reply after upload, waiting for response...")
                    for _ in range(10):
                        try:
                            msg_elems = req_driver.find_elements(By.CSS_SELECTOR, ".alert_info, .alert_error, .alert_success")
                            for msg_elem in msg_elems:
                                msg_text = msg_elem.text.strip()
                                if msg_text:
                                    print(f"📝 Response: {msg_text}")
                                    break
                            else:
                                time.sleep(1)
                                continue
                            break
                        except Exception:
                            time.sleep(1)
                    success_print(f"File uploaded for request: {req.get('title', '')}")

                    try:
                        reply_btn = req_driver.find_element(By.ID, "fastpostsubmit")
                        if reply_btn and reply_btn.is_displayed():
                            reply_btn.click()
                            info_print("Clicked Reply post button after upload.")
                        else:
                            debug_print("Reply post button not found or not visible.")
                    except Exception as e:
                        debug_print(f"Could not click Reply post button: {e}")

                except Exception as e:
                    error_print(f"Failed to submit after upload: {e}")
            except Exception as e:
                error_print(f"Failed to upload file using JavaScript: {e}")
        except Exception as e:
            error_print(f"Failed to upload file: {e}")
        if req_driver is not driver:
            req_driver.quit()

        if temp_txt_created and os.path.exists(upload_path):
            try:
                os.remove(upload_path)
            except Exception:
                pass

    if created_driver and driver:
        driver.quit()

def checkin_wosonhj(headless=True):
    """
    Login to Wosonhj and perform daily check-in by accessing the check-in URL.
    Returns True if check-in is successful, False otherwise.
    """
    today = datetime.date.today()
    print(f"Today's date: {today}")
    print("Starting daily check-in process for Wosonhj")
    checkin_url = f"{WOSONHJ_HOME_URL}/plugin.php?id=are_sign:getaward&typeid=1"
    debug_print(f"Check-in URL: {checkin_url}")
    driver = login_and_navigate_wosonhj(checkin_url, headless=headless)
    if driver is None:
        error_print("Failed to login and access check-in page.")
        return False

    time.sleep(3)
    try:
        page_source = driver.page_source
        debug_print(f"Check-in page source length: {len(page_source)}")
        # Check for success message in page source
        if (
            "签到成功" in page_source
            or "已签到" in page_source
            or "成功" in page_source
            or "You have signed in and clocked in!" in page_source
        ):
            success_print("Check-in successful!")
            if verbose:
                debug_print("Check-in success message found in page source.")
            driver.quit()
            return True
        else:
            warning_print("Check-in may have failed or already done today.")
            if verbose:
                debug_print("Check-in failed or already done. Page source snippet:")
                debug_print(page_source[:500])
            driver.quit()
            return False
    except Exception as e:
        error_print(f"Error during check-in: {e}")
        if verbose:
            debug_print(f"Exception details: {e}")
        driver.quit()
        return False

def get_waiting_requests(headless=True):
    """
    Login and navigate to the user's thread page, list all waiting requests with no replies.
    Returns a list of dicts with request info.
    """
    # First, get user info to extract uid
    driver = login_and_navigate_wosonhj(WOSONHJ_HOME_URL, headless=headless)
    if driver is None:
        error_print("Failed to login and fetch user info for UID.")
        return []

    time.sleep(3)
    user_info_url = None
    try:
        lis = driver.find_elements(By.CSS_SELECTOR, 'li.ren_top_xlkongjian a')
        for a in lis:
            href = a.get_attribute("href")
            if href and f"{WOSONHJ_HOME_URL}/cuid-" in href and href.endswith(".html"):
                user_info_url = href
                break
    except Exception as e:
        error_print(f"Error finding user info URL: {e}")

    if not user_info_url:
        error_print("Could not find user info URL for UID.")
        driver.quit()
        return []

    # Extract uid from user_info_url
    uid_match = re.search(r'cuid-(\d+)\.html', user_info_url)
    if not uid_match:
        error_print("Could not extract UID from user info URL.")
        driver.quit()
        return []

    uid = uid_match.group(1)
    user_thread_url = f"{WOSONHJ_HOME_URL}/home.php?mod=space&uid={uid}&do=thread&view=me&from=space"
    driver.get(user_thread_url)
    time.sleep(3)
    requests = []
    try:
        tables = driver.find_elements(By.CSS_SELECTOR, "table")
        for table in tables:
            try:
                rows = table.find_elements(By.TAG_NAME, "tr")
                for row in rows:
                    try:
                        tds = row.find_elements(By.TAG_NAME, "td")
                        ths = row.find_elements(By.TAG_NAME, "th")
                        if not tds or not ths:
                            continue
                        # Icon
                        icon_url = ""
                        try:
                            img_elem = tds[0].find_element(By.CSS_SELECTOR, "img")
                            icon_url = img_elem.get_attribute("src") if img_elem else ""
                        except Exception:
                            icon_url = ""
                        th = ths[0]
                        # Publisher
                        publisher_name = ""
                        try:
                            ztfl_div = th.find_element(By.CSS_SELECTOR, "div.ren_tie_ztfl")
                            publisher_a = ztfl_div.find_element(By.CSS_SELECTOR, "a.xg1")
                            publisher_name = publisher_a.text.strip()
                        except Exception:
                            publisher_name = ""
                        # Title and link
                        title = ""
                        link = ""
                        try:
                            a_title = th.find_element(By.CSS_SELECTOR, "a.xst")
                            title = a_title.text.strip()
                            link = a_title.get_attribute("href")
                        except Exception:
                            continue
                        # Replies and points and views
                        replies = ""
                        points = ""
                        views = ""
                        try:
                            hfck_div = th.find_element(By.CSS_SELECTOR, "div.ren_tie_hfck")
                            reply_a = hfck_div.find_element(By.CSS_SELECTOR, "a")
                            reply_em = reply_a.find_element(By.CSS_SELECTOR, "em")
                            replies = reply_em.text.strip()
                            # Views: get from <div class="ren_zz_ck y">
                            ck_divs = hfck_div.find_elements(By.CSS_SELECTOR, "div.ren_zz_ck")
                            if ck_divs:
                                views = ck_divs[0].text.strip()
                            # Points: get from <span class="xg1">...分</span>
                            points = ""
                            xg1_spans = th.find_elements(By.CSS_SELECTOR, "span.xg1")
                            for span in xg1_spans:
                                text = span.text.strip()
                                if text.endswith("分"):
                                    try:
                                        points = re.search(r'(\d+)\s*分', text).group(1)
                                    except Exception:
                                        points = ""
                        except Exception:
                            replies = ""
                            points = ""
                            views = ""
                        # Author and post time
                        author = ""
                        post_time = ""
                        try:
                            huifu_div = th.find_element(By.CSS_SELECTOR, "div.ren_tie_huifu")
                            author_elem = huifu_div.find_element(By.CSS_SELECTOR, "a[c='1']")
                            author = author_elem.text.strip()
                            time_span = huifu_div.find_element(By.CSS_SELECTOR, "span span")
                            post_time = time_span.get_attribute("title") if time_span else time_span.text.strip()
                        except Exception:
                            author = ""
                            post_time = ""
                        # Only include requests with 0 replies and not closed
                        closed = False
                        try:
                            closed_spans = th.find_elements(By.CSS_SELECTOR, "span.xg1")
                            for span in closed_spans:
                                if "closed" in span.text.lower() or "已关闭" in span.text:
                                    closed = True
                                    break
                        except Exception:
                            pass
                        if replies == "0" and not closed:
                            requests.append({
                                "title": title,
                                "link": link,
                                "points": points,
                                "author": author,
                                "post_time": post_time,
                                "publisher": publisher_name,
                                "replies": replies,
                                "icon_url": icon_url,
                                "views": views
                            })
                    except Exception as e:
                        debug_print(f"Error parsing my request item: {e}")
            except Exception as e:
                debug_print(f"Error parsing table: {e}")
    except Exception as e:
        error_print(f"Failed to fetch my waiting requests: {e}")

    driver.quit()
    return requests

def get_crossref_info(doi):
    """
    Given a DOI, use Crossref API to extract journal, authors, published date, DOI, article link, publisher, and title.
    Returns a dict with the extracted info.
    """
    info = {
        "journal": "",
        "title": "",
        "authors": "",
        "published_date": "",
        "DOI": doi,
        "PDF_link": "",
        "Article_link": f"https://doi.org/{doi}",
        "Article_Source": "",
    }

    data = getpapers.fetch_crossref_data(doi)
    if not data:
        error_print(f"Failed to fetch Crossref info for DOI: {doi}")
        return info

    info["journal"] = "; ".join(data.get("container-title", []))
    info["title"] = "; ".join(data.get("title", []))
    authors = []
    for a in data.get("author", []):
        name = ""
        if "given" in a and "family" in a:
            name = f"{a['given']} {a['family']}"
        elif "name" in a:
            name = a["name"]
        if name:
            authors.append(name)
    info["authors"] = "; ".join(authors)

    # Published date
    pub_date = ""
    if "published-print" in data and "date-parts" in data["published-print"]:
        pub_date = "-".join(str(x) for x in data["published-print"]["date-parts"][0])
    elif "published-online" in data and "date-parts" in data["published-online"]:
        pub_date = "-".join(str(x) for x in data["published-online"]["date-parts"][0])
    elif "created" in data and "date-parts" in data["created"]:
        pub_date = "-".join(str(x) for x in data["created"]["date-parts"][0])
    elif "published" in data and "date-parts" in data["published"]:
        pub_date = "-".join(str(x) for x in data["published"]["date-parts"][0])
    info["published_date"] = pub_date

    # PDF link (if available)
    pdf_link = ""
    for link in data.get("link", []):
        if link.get("content-type", "").lower() == "application/pdf":
            pdf_link = link.get("URL", "")
            break
    info["PDF_link"] = pdf_link

    # Article Source (publisher)
    publisher = data.get("publisher", "")
    info["Article_Source"] = publisher

    # Try to improve PDF link for Elsevier
    if not pdf_link and "elsevier" in publisher.lower():
        sd_url = f"https://www.sciencedirect.com/science/article/pii/{doi.split('.')[-1]}"
        info["PDF_link"] = sd_url + "/pdf"
        info["Article_link"] = f"https://doi.org/{doi}"
        info["Article_Source"] = "Elsevier"

    return info

def request_by_doi(doi, headless=True):
    """
    Go to the new request page and post a new request by DOI number.
    Gets article info from Crossref, fills all required fields except DOI, and posts the request.
    Selects 7 days for close thread, article type, article source, pastes title as subject,
    pastes description to <textarea id="e_textarea">,
    selects e-mail notification, and clicks New Reward.
    Returns True if successful, False otherwise.
    """
    # Get Crossref info
    info = get_crossref_info(doi)
    debug_print(f"Crossref info: {info}")

    publisher_name = info.get("Article_Source", "")
    publisher_text = publisher_name.strip()
    journal = info.get("journal", "")
    authors = info.get("authors", "")
    published_date = info.get("published_date", "")
    article_link = info.get("Article_link", "")
    pdf_link = info.get("PDF_link", "")
    article_title = info.get("title", "")

    # Compose description (raw text, keep new lines)
    req_desc = (
        f"Journal: {journal}\n"
        f"Authors: {authors}\n"
        f"Published date: {published_date}\n"
        f"DOI: {doi}\n"
        f"PDF link: {pdf_link}\n"
        f"Article link: {article_link}\n"
        f"Publisher: {publisher_text}\n"
    )
    debug_print(f"Request description:\n{req_desc}")

    # Normalize publisher for easy detection
    # If publisher has a shorthand version inside brackets, use that as normalized publisher
    bracket_match = re.search(r'\(([^)]+)\)', publisher_text)
    if bracket_match:
        normalized_publisher = bracket_match.group(1).lower().replace(" ", "").replace("&", "and")
    else:
        normalized_publisher = publisher_text.lower().replace(" ", "").replace("&", "and")
    debug_print(f"Normalized publisher: {normalized_publisher}")

    # Get publisher typeid
    publisher_typeid = normalize_publisher_name(normalized_publisher)
    debug_print(f"Publisher typeid: {publisher_typeid}")

    # Default article type is Journal (1)
    article_type = 1
    # Points logic
    default_points = 10
    points = default_points

    # Append &typeid=<publisher_typeid> to post_url
    post_url = f"{WOSONHJ_HOME_URL}/forum.php?mod=post&action=newthread&fid=66&special=3&typeid={publisher_typeid}"
    debug_print(f"Request by DOI: {doi}")
    debug_print(f"Post URL: {post_url}")

    driver = login_and_navigate_wosonhj(post_url, headless=headless)
    if driver is None:
        error_print("Failed to open new request page.")
        return False

    try:
        time.sleep(3)

        # Select article type radio (name="doi_type", value=article_type)
        article_type_radios = driver.find_elements(By.NAME, "doi_type")
        debug_print(f"Found {len(article_type_radios)} article type radios")
        for radio in article_type_radios:
            debug_print(f"Radio value: {radio.get_attribute('value')}")
            if radio.get_attribute("value") == str(article_type):
                driver.execute_script("arguments[0].scrollIntoView(true);", radio)
                driver.execute_script("arguments[0].click();", radio)
                debug_print("Selected article type radio")
                break

        # Fill in points (find by label for="rewardprice" or input[name='rewardprice'])
        try:
            points_input = None
            points_inputs = driver.find_elements(By.NAME, "rewardprice")
            if points_inputs:
                points_input = points_inputs[0]
            else:
                labels = driver.find_elements(By.TAG_NAME, "label")
                for label in labels:
                    if "reward price" in label.text.lower():
                        for_id = label.get_attribute("for")
                        if for_id:
                            points_input = driver.find_element(By.ID, for_id)
                            break
            if points_input:
                driver.execute_script("arguments[0].scrollIntoView(true);", points_input)
                points_input.clear()
                points_input.send_keys(str(points))
                debug_print("Filled in points")
            else:
                warning_print("Points input not found, skipping.")
        except Exception as e:
            debug_print(f"Exception filling points: {e}")

        # Fill in title (input[name="subject"], id="subject") with article title
        try:
            title_input = None
            try:
                title_input = driver.find_element(By.ID, "subject")
            except Exception:
                try:
                    title_input = driver.find_element(By.NAME, "subject")
                except Exception:
                    pass
            if title_input:
                driver.execute_script("arguments[0].scrollIntoView(true);", title_input)
                title_input.clear()
                article_title = info.get("title", "")
                if not article_title:
                    article_title = journal
                title_input.send_keys(article_title)
                debug_print("Filled in title input with article title")
            else:
                warning_print("Title input not found, skipping.")
        except Exception as e:
            debug_print(f"Exception filling title: {e}")

        # Format description in HTML for Discuz editor
        req_desc_html = (
            f"<b>Journal:</b> {journal}<br>"
            f"<b>Authors:</b> {authors}<br>"
            f"<b>Published date:</b> {published_date}<br>"
            f"<b>DOI:</b> <a href='https://doi.org/{doi}' target='_blank'>{doi}</a><br>"
            f"<b>PDF link:</b> <a href='{pdf_link}' target='_blank'>{pdf_link}</a><br>"
            f"<b>Article link:</b> <a href='{article_link}' target='_blank'>{article_link}</a><br>"
            f"<b>Publisher:</b> {publisher_text}<br>"
        )

        # Paste description into <textarea id="e_textarea"> using Discuz editor's JS API
        try:
            textarea = driver.find_element(By.ID, "e_textarea")
            # Try to use Discuz's writeEditorContents if available, otherwise fallback to setting value
            driver.execute_script("""
            try {
            if (typeof writeEditorContents === 'function') {
            writeEditorContents(arguments[0]);
            } else {
            arguments[1].value = arguments[0];
            }
            } catch (e) {
            arguments[1].value = arguments[0];
            }
            """, req_desc_html, textarea)
            debug_print("Filled in description textarea using Discuz editor API (writeEditorContents or fallback)")
            # Save after pasting (simulate Ctrl+S or trigger save event if available)
            try:
                driver.execute_script("""
                if (typeof saveEditorContents === 'function') {
                    saveEditorContents();
                } else {
                    var evt = new Event('change', { bubbles: true });
                    arguments[0].dispatchEvent(evt);
                }
                """, textarea)
                debug_print("Triggered save after pasting description.")
            except Exception as e2:
                debug_print(f"Failed to trigger save after pasting: {e2}")
        except Exception as e:
            warning_print("Failed to locate or fill description textarea.")
            debug_print(f"Exception details: {e}")

        # Select "7 Days" in close thread date dropdown (id="lootan_closethreadthreaddate")
        try:
            close_thread_date_select = driver.find_element(By.ID, "lootan_closethreadthreaddate")
            found_7days = False
            for option in close_thread_date_select.find_elements(By.TAG_NAME, "option"):
                debug_print(f"Close thread option: {option.text}")
                if "7" in option.text:
                    option.click()
                    found_7days = True
                    debug_print("Selected 7 days for close thread")
                    break
            if not found_7days:
                warning_print("Could not find '7 days' option for close thread.")
        except Exception as e:
            debug_print(f"Exception selecting close thread date: {e}")

        # Select e-mail notification checkbox (id="zzbuluo_replyemail")
        try:
            email_alert_checkbox = driver.find_element(By.ID, "zzbuluo_replyemail")
            if not email_alert_checkbox.is_selected():
                email_alert_checkbox.click()
                debug_print("Selected e-mail notification (zzbuluo_replyemail)")
        except Exception as e:
            debug_print(f"Exception selecting e-mail notification: {e}")

        # Click "New Reward" button (button[type='submit'], text contains "New Reward")
        try:
            buttons = driver.find_elements(By.CSS_SELECTOR, "button[type='submit']")
            clicked = False
            for btn in buttons:
                btn_text = btn.text.strip().lower()
                debug_print(f"Submit button text: {btn_text}")
                if "new reward" in btn_text or "新悬赏" in btn_text or "发布" in btn_text:
                    driver.execute_script("arguments[0].click();", btn)
                    clicked = True
                    debug_print("Clicked New Reward button")
                    break
            if not clicked:
                submit_btn = driver.find_element(By.ID, "postsubmit")
                submit_btn.click()
                debug_print("Clicked fallback submit button")
        except Exception as e:
            debug_print(f"Exception clicking submit button: {e}")
            try:
                submit_btn = driver.find_element(By.ID, "postsubmit")
                submit_btn.click()
                debug_print("Clicked fallback submit button in exception")
            except Exception as e2:
                error_print("Failed to locate and click submit button.")
                debug_print(f"Exception details: {e2}")
                driver.quit()
                return False

        info_print("Submitted new request, waiting for response...")

        time.sleep(5)
        page_source = driver.page_source
        debug_print(f"Page source after submit (first 500 chars): {page_source[:500]}")
        if "发布成功" in page_source or "successfully posted" in page_source:
            success_print("New request posted successfully!")
            driver.quit()
            return True
        else:
            warning_print("Request may not have been posted successfully.")
            driver.quit()
            return False
    except Exception as e:
        error_print(f"Failed to post new request: {e}")
        debug_print(f"Exception details: {e}")
        driver.quit()
        return False

def request_multiple_dois(dois, headless=True):
    """
    Request multiple papers by DOI.
    Accepts a list of DOIs (strings), calls request_by_doi for each.
    Returns a dict mapping DOI to True/False for success.
    """
    results = {}
    for doi in dois:
        info_print(f"Requesting DOI: {doi}")
        result = request_by_doi(doi, headless=headless)
        results[doi] = result
        if result:
            success_print(f"Successfully posted request for DOI: {doi}")
        else:
            error_print(f"Failed to post request for DOI: {doi}")
    return results

def is_post_finished(post_url, headless=True, driver=None):
    """
    Open the given post URL in a new tab and check if the post is finished (closed or marked as fulfilled).
    Returns True if finished, False otherwise.
    Always uses a new tab. If driver is provided, reuse it; otherwise, create a new one.
    The post is finished if BOTH:
      - <div class="z ren-view-rwd-rsld z">Reward<cite>...</cite>points</div>
        <p class="pns e y"><button name="answer" ...><span>finished</span></button></p>
      - <span class="icon"><img src="template/rtj1009_012/image/rwdbst.png"></span>
        <h3>Best Answer</h3>
    are found somewhere in the post page.
    """
    finished = False
    created_driver = False
    tab_opened = False

    if driver is None:
        driver = login_and_navigate_wosonhj(WOSONHJ_HOME_URL, headless=headless)
        created_driver = True

    if driver is None:
        error_print(f"Failed to open browser for post: {post_url}")
        return finished

    try:
        # Open a new tab and switch to it
        driver.execute_script(f"window.open('{post_url}', '_blank');")
        time.sleep(1)
        tabs = driver.window_handles
        driver.switch_to.window(tabs[-1])
        tab_opened = True

        time.sleep(2)
        page_source = driver.page_source

        # Check for the first indicator: reward finished
        reward_finished = False
        reward_pattern = (
            r'<div[^>]*class="[^"]*ren-view-rwd-rsld[^"]*"[^>]*>.*?Reward.*?<cite>.*?</cite>.*?points.*?</div>.*?'
            r'<p[^>]*class="[^"]*pns e y[^"]*"[^>]*>.*?<button[^>]*name="answer"[^>]*class="pn"[^>]*>.*?<span>finished</span>.*?</button>.*?</p>'
        )
        if re.search(reward_pattern, page_source, re.S | re.I):
            reward_finished = True

        # Check for the second indicator: best answer
        best_answer = False
        best_answer_pattern = (
            r'<span[^>]*class="icon"[^>]*>.*?<img[^>]*src="template/rtj1009_012/image/rwdbst\.png"[^>]*>.*?</span>.*?'
            r'<h3[^>]*>Best Answer</h3>'
        )
        if re.search(best_answer_pattern, page_source, re.S | re.I):
            best_answer = True

        # The post is finished if both indicators are present
        if reward_finished and best_answer:
            finished = True

    except Exception as e:
        debug_print(f"Error checking post finished status: {e}")
    finally:
        if tab_opened:
            driver.close()
            if driver.window_handles:
                driver.switch_to.window(driver.window_handles[0])
        if created_driver:
            driver.quit()
    return finished

def get_post_replies(post_url, headless=True, driver=None):
    """
    Go to the post page and list all replies, arranged by time (ascending).
    Returns a list of dicts: {author, reply_time, content, reply_id, floor, attachments, setanswer_id}
    setanswer_id is extracted from the onclick attribute of the "Adopt" button if present.
    Each attachment dict includes 'url', 'download_url', and 'size' (in bytes, if available).
    For attachments, if the URL matches the Wosonhj attachment pattern, the direct download URL is constructed.
    Ignores any reply having nothing (empty author, content, and attachments).
    Always performs this function in a new tab. If driver is provided, reuse it; otherwise, create a new one.
    """
    created_driver = False
    tab_opened = False

    if driver is None:
        driver = login_and_navigate_wosonhj(WOSONHJ_HOME_URL, headless=headless)
        created_driver = True

    if driver is None:
        error_print("Failed to open post page for replies.")
        return []

    try:
        # Open a new tab and switch to it
        driver.execute_script(f"window.open('{post_url}', '_blank');")
        time.sleep(1)
        tabs = driver.window_handles
        driver.switch_to.window(tabs[-1])
        tab_opened = True

        time.sleep(3)
        replies = []
        try:
            # Each reply is in <div id="post_xxx" class="ren_reply cl">
            post_divs = driver.find_elements(By.CSS_SELECTOR, "div.ren_reply.cl")
            for div in post_divs:
                try:
                    # Reply ID
                    reply_id = div.get_attribute("id")

                    # Floor number
                    floor = ""
                    try:
                        strong_elem = div.find_element(By.CSS_SELECTOR, "strong a em")
                        floor = strong_elem.text.strip()
                    except Exception:
                        pass

                    # Author
                    author = ""
                    try:
                        author_elem = div.find_element(By.CSS_SELECTOR, ".authi.ren_authi a.ren_view_author")
                        author = author_elem.text.strip()
                    except Exception:
                        pass

                    # Reply time
                    reply_time = ""
                    try:
                        time_elem = div.find_element(By.CSS_SELECTOR, ".authi.ren_authi em.ren_view_authisj span[title]")
                        reply_time = time_elem.get_attribute("title").strip()
                    except Exception:
                        # fallback: get text
                        try:
                            time_elem = div.find_element(By.CSS_SELECTOR, ".authi.ren_authi em.ren_view_authisj")
                            reply_time = time_elem.text.strip()
                        except Exception:
                            pass

                    # Content
                    content = ""
                    try:
                        content_elem = div.find_element(By.CSS_SELECTOR, "td.t_f")
                        content = content_elem.text.strip()
                    except Exception:
                        # fallback: get from .pcb
                        try:
                            content_elem = div.find_element(By.CSS_SELECTOR, ".pcb")
                            content = content_elem.text.strip()
                        except Exception:
                            pass

                    # Attachments
                    attachments = []
                    try:
                        attach_elems = div.find_elements(By.CSS_SELECTOR, "dl.tattl a")
                        for a in attach_elems:
                            url = a.get_attribute("href")
                            name = a.text.strip()
                            download_url = ""
                            size = None
                            # If the URL matches the Wosonhj attachment pattern, construct direct download URL
                            if url and "forum.php?mod=attachment" in url and "aid=" in url:
                                download_url = url
                            else:
                                # Try to find direct download link if available
                                try:
                                    parent = a.find_element(By.XPATH, "..")
                                    sibling_links = parent.find_elements(By.TAG_NAME, "a")
                                    for sib in sibling_links:
                                        if sib != a and "download" in sib.text.lower():
                                            download_url = sib.get_attribute("href")
                                            break
                                except Exception:
                                    pass
                            if not download_url:
                                download_url = url

                            # Try to get size info from the attachment row (often in a <span> or text after name)
                            try:
                                # Look for a span or text node after the link
                                parent = a.find_element(By.XPATH, "..")
                                spans = parent.find_elements(By.TAG_NAME, "span")
                                for span in spans:
                                    span_text = span.text.strip()
                                    # Match size like "1.2 MB", "123 KB", "456 bytes"
                                    m = re.search(r'([\d\.]+)\s*(KB|MB|bytes)', span_text, re.I)
                                    if m:
                                        val, unit = m.group(1), m.group(2).lower()
                                        try:
                                            if unit == "mb":
                                                size = int(float(val) * 1024 * 1024)
                                            elif unit == "kb":
                                                size = int(float(val) * 1024)
                                            elif unit == "bytes":
                                                size = int(float(val))
                                        except Exception:
                                            size = None
                                        break
                                if size is None:
                                    # Sometimes size is in the parent text, e.g. "filename.pdf (1.2 MB)"
                                    parent_text = parent.text
                                    m = re.search(r'([\d\.]+)\s*(KB|MB|bytes)', parent_text, re.I)
                                    if m:
                                        val, unit = m.group(1), m.group(2).lower()
                                        try:
                                            if unit == "mb":
                                                size = int(float(val) * 1024 * 1024)
                                            elif unit == "kb":
                                                size = int(float(val) * 1024)
                                            elif unit == "bytes":
                                                size = int(float(val))
                                        except Exception:
                                            size = None
                            except Exception:
                                pass

                            # Try to extract size from nearby <p> elements (e.g. <p>1.91 MB, Downloads: 0</p>)
                            if size is None:
                                try:
                                    # Find all <p> elements in the div, look for one containing the attachment name
                                    p_elems = div.find_elements(By.TAG_NAME, "p")
                                    for p in p_elems:
                                        p_text = p.text
                                        if name in p_text or "MB" in p_text or "KB" in p_text or "bytes" in p_text:
                                            m = re.search(r'([\d\.]+)\s*(KB|MB|bytes)', p_text, re.I)
                                            if m:
                                                val, unit = m.group(1), m.group(2).lower()
                                                try:
                                                    if unit == "mb":
                                                        size = int(float(val) * 1024 * 1024)
                                                    elif unit == "kb":
                                                        size = int(float(val) * 1024)
                                                    elif unit == "bytes":
                                                        size = int(float(val))
                                                except Exception:
                                                    size = None
                                                break
                                except Exception:
                                    pass

                            # Try to extract size from hidden <div class="tip tip_4" ...> blocks
                            if size is None:
                                try:
                                    tip_divs = driver.find_elements(By.CSS_SELECTOR, "div.tip.tip_4")
                                    for tip in tip_divs:
                                        tip_html = tip.get_attribute("outerHTML")
                                        # Only check if the attachment name is in the tip block
                                        if name and name in tip_html:
                                            m = re.search(r'([\d\.]+)\s*(KB|MB|bytes)', tip_html, re.I)
                                            if m:
                                                val, unit = m.group(1), m.group(2).lower()
                                                try:
                                                    if unit == "mb":
                                                        size = int(float(val) * 1024 * 1024)
                                                    elif unit == "kb":
                                                        size = int(float(val) * 1024)
                                                    elif unit == "bytes":
                                                        size = int(float(val))
                                                except Exception:
                                                    size = None
                                                break
                                except Exception:
                                    pass

                            if url:
                                attachments.append({"name": name, "url": url, "download_url": download_url, "size": size})
                    except Exception:
                        pass

                    # Extract setanswer_id from "Adopt" button if present
                    setanswer_id = ""
                    try:
                        adopt_btns = div.find_elements(By.XPATH, ".//a[contains(@onclick, 'setanswer(')]")
                        for btn in adopt_btns:
                            onclick = btn.get_attribute("onclick")
                            m = re.search(r"setanswer\((\d+),", onclick)
                            if m:
                                setanswer_id = m.group(1)
                                break
                    except Exception:
                        pass

                    # Ignore reply if author, content, and attachments are all empty
                    if not author and not content and not attachments:
                        continue

                    replies.append({
                        "author": author,
                        "reply_time": reply_time,
                        "content": content,
                        "reply_id": reply_id,
                        "floor": floor,
                        "attachments": attachments,
                        "setanswer_id": setanswer_id
                    })
                except Exception as e:
                    debug_print(f"Error parsing reply: {e}")

            # Sort by reply_time (if possible)
            def parse_time(t):
                try:
                    # Example: "2025-7-23 16:38:14"
                    m = re.search(r'(\d{4}-\d{1,2}-\d{1,2} \d{2}:\d{2}:\d{2})', t)
                    if m:
                        # Convert to timestamp for consistent comparison
                        return time.mktime(time.strptime(m.group(1), "%Y-%m-%d %H:%M:%S"))
                except Exception:
                    pass
                # If parsing fails, return 0 so these replies appear first
                return 0
            replies.sort(key=lambda r: parse_time(r["reply_time"]))
        except Exception as e:
            error_print(f"Failed to fetch replies: {e}")
    finally:
        if tab_opened:
            driver.close()
            if driver.window_handles:
                driver.switch_to.window(driver.window_handles[0])
        if created_driver:
            driver.quit()
    return replies

def print_post_replies(input, header="💬 === Post Replies ==="):
    """
    Print all replies from get_post_replies result.
    Displays author, reply time, content, floor, and attachments (with size).
    Optional header can be set via the 'header' argument.
    """
    replies = input
    if not replies:
        error_print("No replies found for this post.")
        return

    print(f"\n{header}")
    for idx, reply in enumerate(replies, 1):
        print(f"{idx}. 👤 Author: {reply.get('author', '')}")
        print(f"    🕒 Time: {reply.get('reply_time', '')}")
        print(f"    🏠 Floor: {reply.get('floor', '')}")
        print(f"    📝 Content: {reply.get('content', '')}")
        if reply.get('attachments'):
            print("    📎 Attachments:")
            for att in reply['attachments']:
                size = att.get('size')
                if size is not None:
                    if size >= 1024 * 1024:
                        size_str = f"{size / (1024 * 1024):.2f} MB"
                    elif size >= 1024:
                        size_str = f"{size / 1024:.2f} KB"
                    else:
                        size_str = f"{size} bytes"
                else:
                    size_str = "Unknown size"
                print(f"      - {att.get('name', '')}: {att.get('download_url', att.get('url', ''))} ({size_str})")
        print("-" * 40)
    print("=========================\n")

def get_fulfilled_requests(headless=True):
    """
    Login and navigate to the user's thread page, list all fulfilled requests (with replies, not yet closed, not finished).
    For each fulfilled request, go to the post URL and get and print more information using print_post_replies.
    Returns a list of dicts with request info.
    """

    driver = login_and_navigate_wosonhj(WOSONHJ_HOME_URL, headless=headless)
    if driver is None:
        error_print("Failed to login and fetch user info for UID.")
        return []

    time.sleep(3)
    user_info_url = None
    try:
        lis = driver.find_elements(By.CSS_SELECTOR, 'li.ren_top_xlkongjian a')
        for a in lis:
            href = a.get_attribute("href")
            if href and f"{WOSONHJ_HOME_URL}/cuid-" in href and href.endswith(".html"):
                user_info_url = href
                break
    except Exception as e:
        error_print(f"Error finding user info URL: {e}")

    if not user_info_url:
        error_print("Could not find user info URL for UID.")
        driver.quit()
        return []

    # Extract uid from user_info_url
    uid_match = re.search(r'cuid-(\d+)\.html', user_info_url)
    if not uid_match:
        error_print("Could not extract UID from user info URL.")
        driver.quit()
        return []

    uid = uid_match.group(1)
    user_thread_url = f"{WOSONHJ_HOME_URL}/home.php?mod=space&uid={uid}&do=thread&view=me&from=space"
    if verbose:
        debug_print(f"Navigating to user thread URL: {user_thread_url}")
    driver.get(user_thread_url)
    time.sleep(3)
    requests = []
    try:
        tables = driver.find_elements(By.CSS_SELECTOR, "table")
        for table in tables:
            try:
                rows = table.find_elements(By.TAG_NAME, "tr")
                for row in rows:
                    try:
                        tds = row.find_elements(By.TAG_NAME, "td")
                        ths = row.find_elements(By.TAG_NAME, "th")
                        if not tds or not ths:
                            continue
                        # Icon
                        icon_url = ""
                        try:
                            img_elem = tds[0].find_element(By.CSS_SELECTOR, "img")
                            icon_url = img_elem.get_attribute("src") if img_elem else ""
                        except Exception:
                            icon_url = ""
                        # Main info in th
                        th = ths[0]
                        # Title and link
                        title = ""
                        link = ""
                        try:
                            a_title = th.find_element(By.CSS_SELECTOR, "a.xst")
                            title = a_title.text.strip()
                            link = a_title.get_attribute("href")
                        except Exception:
                            continue
                        # Closed status
                        closed = False
                        try:
                            closed_spans = th.find_elements(By.CSS_SELECTOR, "span.xg1")
                            for span in closed_spans:
                                if "closed" in span.text.lower() or "已关闭" in span.text:
                                    closed = True
                                    break
                        except Exception:
                            pass
                        # Author and post time
                        author = ""
                        post_time = ""
                        try:
                            huifu_div = th.find_element(By.CSS_SELECTOR, "div.ren_tie_huifu")
                            author_elem = huifu_div.find_element(By.CSS_SELECTOR, "a[c='1']")
                            author = author_elem.text.strip()
                            time_span = huifu_div.find_element(By.CSS_SELECTOR, "span span")
                            post_time = time_span.get_attribute("title") if time_span else time_span.text.strip()
                        except Exception:
                            pass
                        # Replies and points
                        replies = ""
                        points = ""
                        views = ""
                        try:
                            hfck_div = th.find_element(By.CSS_SELECTOR, "div.ren_tie_hfck")
                            reply_a = hfck_div.find_element(By.CSS_SELECTOR, "a")
                            reply_em = reply_a.find_element(By.CSS_SELECTOR, "em")
                            replies = reply_em.text.strip()
                            # Points: get from <span class="xg1">...分</span>
                            points = ""
                            xg1_spans = th.find_elements(By.CSS_SELECTOR, "span.xg1")
                            for span in xg1_spans:
                                text = span.text.strip()
                                if text.endswith("分"):
                                    try:
                                        points = re.search(r'(\d+)\s*分', text).group(1)
                                    except Exception:
                                        points = ""
                            # Views: get from <div class="ren_zz_ck y">
                            ck_divs = hfck_div.find_elements(By.CSS_SELECTOR, "div.ren_zz_ck")
                            if ck_divs:
                                views = ck_divs[0].text.strip()
                        except Exception:
                            pass
                        # Publisher
                        publisher_name = ""
                        try:
                            ztfl_div = th.find_element(By.CSS_SELECTOR, "div.ren_tie_ztfl")
                            publisher_a = ztfl_div.find_element(By.CSS_SELECTOR, "a.xg1")
                            publisher_name = publisher_a.text.strip()
                        except Exception:
                            pass
                        if replies and replies != "0" and not closed:
                            req_info = {
                                "title": title,
                                "link": link,
                                "points": points,
                                "author": author,
                                "post_time": post_time,
                                "publisher": publisher_name,
                                "replies": replies,
                                "icon_url": icon_url,
                                "views": views
                            }
                            # Check if finished
                            if not is_post_finished(link, headless=headless, driver=driver):
                                if verbose:
                                    debug_print(f"Fulfilled request: {req_info}")
                                requests.append(req_info)
                    except Exception as e:
                        debug_print(f"Error parsing table row: {e}")
            except Exception as e:
                debug_print(f"Error parsing table: {e}")
    except Exception as e:
        error_print(f"Failed to fetch my fulfilled requests: {e}")

    driver.quit()
    if verbose:
        debug_print(f"Total fulfilled requests found: {len(requests)}")
    return requests

def download_file_with_browser(url, original_filename, new_filename, download_folder, size=None):
    """
    Download a file using a separate browser instance for each URL.
    Login and navigate to the download URL, wait for download to finish, check file and rename, then quit browser.
    Returns True if successful, False otherwise.
    """
    wait_time = 10
    if size:
        if size >= 10 * 1024 * 1024:
            wait_time = 60
        elif size >= 1 * 1024 * 1024:
            wait_time = 30
        elif size >= 100 * 1024:
            wait_time = 15

    # Use a new driver for each download
    driver = None
    try:
        driver = login_and_navigate_wosonhj(url, headless=True, enable_download=True, download_folder=download_folder)
        if driver is None:
            error_print("Failed to login and navigate to download URL.")
            return False
        info_print(f"Waiting up to {wait_time}s for download to finish...")
        time.sleep(wait_time)
    except Exception as e:
        error_print(f"Failed to download attachment: {e}")
        if driver:
            driver.quit()
        return False
    finally:
        if driver:
            driver.quit()

    # Check if file exists in download folder and rename it
    downloaded_files = os.listdir(download_folder)
    found = False
    for f in downloaded_files:
        # Check for exact filename or partial match (sometimes browser renames)
        if f == original_filename or (original_filename and f.startswith(os.path.splitext(original_filename)[0])):
            found = True
            src_path = os.path.join(download_folder, f)
            dst_path = os.path.join(download_folder, new_filename)
            try:
                if src_path != dst_path:
                    os.rename(src_path, dst_path)
                    success_print(f"Downloaded and renamed: {dst_path}")
                else:
                    success_print(f"Downloaded successfully: {dst_path}")
            except Exception as e:
                warning_print(f"Downloaded but failed to rename: {src_path} -> {dst_path}: {e}")
            break
    if not found:
        warning_print(f"Download may have failed or file not found: {original_filename}")
        return False
    return True

def download_fulfilled_requests(headless=True):
    """
    Download attachments from fulfilled requests using browser for direct download.
    1. Get and print all fulfilled requests.
    2. Ask user to select a range of requests to download (default: all after 60s timeout).
    3. For each selected request, list all replies and download all attachments.
    4. After download, rename file to <original name>_<replyid>.<extension>
    Automatically uses browser to download attachments in a new tab, waits for download to finish based on attachment size.
    Always allow user to quit by entering 'q' or 'quit'.
    Checks if the download is successful by looking for the file in the download folder.
    """
    requests = get_fulfilled_requests(headless=headless)
    if not requests:
        error_print("No fulfilled requests found.")
        return

    print_requests(requests, header="📄 === Fulfilled Requests ===")
    print("Select request(s) to download attachments (e.g. 1,3-5). Type 'q' or 'quit' to exit:")

    selected_indices = []

    def parse_indices(response):
        items = [item.strip() for item in response.split(",") if item.strip()]
        for item in items:
            if item.lower() in ("q", "quit"):
                return "quit"
            if "-" in item:
                try:
                    start, end = map(int, item.split("-", 1))
                    for i in range(start, end + 1):
                        if 1 <= i <= len(requests):
                            selected_indices.append(i - 1)
                except Exception:
                    warning_print(f"Invalid range: {item}")
            elif item.isdigit():
                idx = int(item)
                if 1 <= idx <= len(requests):
                    selected_indices.append(idx - 1)
            else:
                warning_print(f"Invalid selection: {item}")

    response = [None]

    def ask():
        try:
            response[0] = input("Request(s): ").strip()
        except Exception:
            response[0] = None

    t = threading.Thread(target=ask)
    t.daemon = True
    t.start()
    t.join(60)
    if t.is_alive():
        info_print("No response within 60 seconds. Downloading all requests.")
        selected_indices = list(range(len(requests)))
    elif not response[0]:
        info_print("No selection made. Downloading all requests.")
        selected_indices = list(range(len(requests)))
    else:
        quit_flag = parse_indices(response[0])
        if quit_flag == "quit":
            info_print("Quitting as requested by user.")
            return

    if not selected_indices:
        info_print("No valid request selected.")
        return

    download_folder = DEFAULT_DOWNLOAD_FOLDER
    os.makedirs(download_folder, exist_ok=True)

    for idx in selected_indices:
        req = requests[idx]
        info_print(f"Downloading attachments for: {req.get('title', '')} ({req.get('link', '')})")
        replies = get_post_replies(req.get('link', ''), headless=headless)
        if not replies:
            warning_print("No replies found for this request.")
            continue
        else:
            print_post_replies(replies, header=f"💬 === Replies for Request: {req.get('title', '')} ===")

        for reply in replies:
            reply_id = reply.get("reply_id", "")
            attachments = reply.get("attachments", [])
            if not attachments:
                continue
            for att in attachments:
                url = att.get("download_url") or att.get("url")
                name = att.get("name", "")
                size = att.get("size", None)
                if not url or not name:
                    continue
                ext = os.path.splitext(name)[1] if name else ""
                original_filename = name
                new_filename = f"{os.path.splitext(name)[0]}_{reply_id}{ext}" if reply_id else name
                info_print(f"Downloading: {original_filename} from {url}")

                # download_file_with_browser now does not require a driver argument
                download_file_with_browser(
                    url=url,
                    original_filename=original_filename,
                    new_filename=new_filename,
                    download_folder=download_folder,
                    size=size
                )

        success_print(f"Finished downloading attachments for: {req.get('title', '')}")

    success_print(f"All selected fulfilled requests processed. Files saved to: {download_folder}")

def accept_reply_for_post(post_url, setanswer_id, headless=True):
    """
    Login and navigate to a post URL, find the reply with setanswer_id, and click the adopt button.
    After clicking, reload the post page and check if it is finished using is_post_finished.
    Returns True if adopted successfully, False otherwise.
    """
    driver = login_and_navigate_wosonhj(post_url, headless=headless)
    if driver is None:
        error_print("Failed to open request page for adoption.")
        return False

    try:
        time.sleep(3)
        # Find adopt button by onclick attribute
        adopt_btns = driver.find_elements(By.XPATH, f"//a[contains(@onclick, 'setanswer({setanswer_id},')]")
        if not adopt_btns:
            error_print("Adopt button not found on the page.")
            driver.quit()
            return False
        adopt_btn = adopt_btns[0]
        driver.execute_script("arguments[0].scrollIntoView(true);", adopt_btn)
        driver.execute_script("arguments[0].click();", adopt_btn)
        info_print("Clicked adopt button. Waiting for confirmation...")
        # Handle confirmation alert if present
        try:
            WebDriverWait(driver, 5).until(EC.alert_is_present())
            alert = driver.switch_to.alert
            info_print(f"Alert Text: {alert.text}")
            alert.accept()
            info_print("Accepted confirmation alert.")
        except Exception:
            debug_print("No confirmation alert appeared after clicking adopt button.")
        time.sleep(5)
        # Reload the post page and check if finished
        driver.get(post_url)
        time.sleep(3)
        finished = is_post_finished(post_url, headless=headless, driver=driver)
        if finished:
            success_print("Reply adopted successfully and post is finished!")
            driver.quit()
            return True
        else:
            warning_print("Adopt may not have succeeded or post not finished. Please check manually.")
            driver.quit()
            return False
    except Exception as e:
        error_print(f"Failed to adopt reply: {e}")
        driver.quit()
        return False

def accept_fulfilled_requests(headless=True):
    """
    List all fulfilled requests, prompt user to select requests to accept, then for each,
    list all replies and prompt user to choose which reply to accept (adopt).
    Click the adopt button for the selected reply.
    Default is all requests if no response after 60 seconds. Allow user to quit.
    If user does not select a reply within 60 seconds, select the earliest reply (by time).
    """
    requests = get_fulfilled_requests(headless=headless)
    if not requests:
        error_print("No fulfilled requests found.")
        return

    print_requests(requests, header="📄 === Fulfilled Requests ===")
    print("Select request(s) to accept (e.g. 1,3-5). Type 'q' or 'quit' to exit (default: all after 60s timeout):")

    selected_indices = []

    def parse_indices(response):
        items = [item.strip() for item in response.split(",") if item.strip()]
        for item in items:
            if item.lower() in ("q", "quit"):
                return "quit"
            if "-" in item:
                try:
                    start, end = map(int, item.split("-", 1))
                    for i in range(start, end + 1):
                        if 1 <= i <= len(requests):
                            selected_indices.append(i - 1)
                except Exception:
                    warning_print(f"Invalid range: {item}")
            elif item.isdigit():
                idx = int(item)
                if 1 <= idx <= len(requests):
                    selected_indices.append(idx - 1)
            else:
                warning_print(f"Invalid selection: {item}")

    response = [None]

    def ask():
        try:
            response[0] = input("Request(s): ").strip()
        except Exception:
            response[0] = None

    t = threading.Thread(target=ask)
    t.daemon = True
    t.start()
    t.join(60)
    # Default: all requests if no response
    if t.is_alive():
        info_print("No response within 60 seconds. Accepting all requests.")
        selected_indices = list(range(len(requests)))
    elif not response[0]:
        info_print("No selection made. Accepting all requests.")
        selected_indices = list(range(len(requests)))
    else:
        quit_flag = parse_indices(response[0])
        if quit_flag == "quit":
            info_print("Quitting as requested by user.")
            return

    if not selected_indices:
        info_print("No valid request selected.")
        return

    for idx in selected_indices:
        req = requests[idx]
        info_print(f"Processing request: {req.get('title', '')} ({req.get('link', '')})")
        replies = get_post_replies(req.get('link', ''), headless=headless)
        if not replies:
            warning_print("No replies found for this request.")
            continue
        print_post_replies(replies, header=f"💬 === Replies for Request: {req.get('title', '')} ===")
        print("Select reply to accept (by number). Type 'q' or 'quit' to exit (default: earliest reply after 60s timeout):")

        reply_index = [None]

        def ask_reply():
            try:
                reply_index[0] = input("Reply number: ").strip()
            except Exception:
                reply_index[0] = None

        t2 = threading.Thread(target=ask_reply)
        t2.daemon = True
        t2.start()
        t2.join(60)
        # Default: earliest reply if no response
        if t2.is_alive() or not reply_index[0]:
            info_print("No response within 60 seconds. Accepting earliest reply.")
            def parse_time(t):
                try:
                    m = re.search(r'(\d{4}-\d{1,2}-\d{1,2} \d{2}:\d{2}:\d{2})', t)
                    if m:
                        return time.mktime(time.strptime(m.group(1), "%Y-%m-%d %H:%M:%S"))
                except Exception:
                    pass
                return 0
            earliest_idx = min(range(len(replies)), key=lambda i: parse_time(replies[i].get("reply_time", "")))
            selected_reply = earliest_idx
        elif reply_index[0].lower() in ("q", "quit"):
            info_print("Quitting as requested by user.")
            break
        elif reply_index[0].isdigit():
            selected_reply = int(reply_index[0]) - 1
            if not (0 <= selected_reply < len(replies)):
                warning_print("Invalid reply number. Skipping this request.")
                continue
        else:
            warning_print("Invalid input. Skipping this request.")
            continue

        reply = replies[selected_reply]
        setanswer_id = reply.get("setanswer_id")
        if not setanswer_id:
            error_print("No adopt button found for selected reply.")
            continue

        accept_reply_for_post(req.get('link', ''), setanswer_id, headless=headless)

def report_reply_for_post(post_url, reply_id, headless=True):
    """
    Login and navigate to a post URL, find the reply with reply_id, and click the report button.
    After clicking, handle the report window if possible.
    Returns True if reported successfully, False otherwise.
    """
    driver = login_and_navigate_wosonhj(post_url, headless=headless)
    if driver is None:
        error_print("Failed to open request page for reporting.")
        return False

    try:
        time.sleep(3)
        # Find report button by onclick attribute containing showWindow('miscreport<reply_id>'
        report_btns = driver.find_elements(
            By.XPATH,
            f"//a[contains(@onclick, \"showWindow('miscreport{reply_id}\")]")
        if not report_btns:
            error_print("Report button not found on the page.")
            driver.quit()
            return False
        report_btn = report_btns[0]
        driver.execute_script("arguments[0].scrollIntoView(true);", report_btn)
        driver.execute_script("arguments[0].click();", report_btn)
        info_print("Clicked report button. Waiting for report window...")

        # Wait for report window to appear and try to submit a report
        try:
            time.sleep(2)
            # Switch to report window if it appears
            # The report window is usually a popup with id like "fwin_miscreport<reply_id>"
            report_win_id = f"fwin_miscreport{reply_id}"
            report_win = driver.find_element(By.ID, report_win_id)
            # Find textarea for reason (usually name="message" or id="reason")
            reason_input = None
            try:
                reason_input = report_win.find_element(By.NAME, "message")
            except Exception:
                try:
                    reason_input = report_win.find_element(By.ID, "reason")
                except Exception:
                    pass
            if reason_input:
                reason_input.clear()
                reason_input.send_keys("Rejecting reply: not helpful or inappropriate.")
            # Find submit button (type="submit")
            submit_btn = None
            try:
                submit_btn = report_win.find_element(By.CSS_SELECTOR, "button[type='submit'], input[type='submit']")
            except Exception:
                pass
            if submit_btn:
                driver.execute_script("arguments[0].click();", submit_btn)
                info_print("Submitted report.")
                time.sleep(2)
            else:
                warning_print("Report submit button not found.")
        except Exception as e:
            warning_print(f"Could not interact with report window: {e}")
        driver.quit()
        return True
    except Exception as e:
        error_print(f"Failed to report reply: {e}")
        driver.quit()
        return False

def reject_fulfilled_requests(headless=True):
    """
    List all fulfilled requests, prompt user to select requests to reject replies for,
    then for each, list all replies and prompt user to choose which reply to reject (report).
    Click the report button for the selected reply.
    Default is all requests if no response after 60 seconds. Allow user to quit.
    If user does not select a reply within 60 seconds, select the earliest reply (by time).
    """
    requests = get_fulfilled_requests(headless=headless)
    if not requests:
        error_print("No fulfilled requests found.")
        return

    print_requests(requests, header="📄 === Fulfilled Requests ===")
    print("Select request(s) to reject (e.g. 1,3-5). Type 'q' or 'quit' to exit (default: all after 60s timeout):")

    selected_indices = []

    def parse_indices(response):
        items = [item.strip() for item in response.split(",") if item.strip()]
        for item in items:
            if item.lower() in ("q", "quit"):
                return "quit"
            if "-" in item:
                try:
                    start, end = map(int, item.split("-", 1))
                    for i in range(start, end + 1):
                        if 1 <= i <= len(requests):
                            selected_indices.append(i - 1)
                except Exception:
                    warning_print(f"Invalid range: {item}")
            elif item.isdigit():
                idx = int(item)
                if 1 <= idx <= len(requests):
                    selected_indices.append(idx - 1)
            else:
                warning_print(f"Invalid selection: {item}")

    response = [None]

    def ask():
        try:
            response[0] = input("Request(s): ").strip()
        except Exception:
            response[0] = None

    t = threading.Thread(target=ask)
    t.daemon = True
    t.start()
    t.join(60)
    # Default: all requests if no response
    if t.is_alive():
        info_print("No response within 60 seconds. Rejecting all requests.")
        selected_indices = list(range(len(requests)))
    elif not response[0]:
        info_print("No selection made. Rejecting all requests.")
        selected_indices = list(range(len(requests)))
    else:
        quit_flag = parse_indices(response[0])
        if quit_flag == "quit":
            info_print("Quitting as requested by user.")
            return

    if not selected_indices:
        info_print("No valid request selected.")
        return

    for idx in selected_indices:
        req = requests[idx]
        info_print(f"Processing request: {req.get('title', '')} ({req.get('link', '')})")
        replies = get_post_replies(req.get('link', ''), headless=headless)
        if not replies:
            warning_print("No replies found for this request.")
            continue
        print_post_replies(replies, header=f"💬 === Replies for Request: {req.get('title', '')} ===")
        print("Select reply to reject (by number). Type 'q' or 'quit' to exit (default: earliest reply after 60s timeout):")

        reply_index = [None]

        def ask_reply():
            try:
                reply_index[0] = input("Reply number: ").strip()
            except Exception:
                reply_index[0] = None

        t2 = threading.Thread(target=ask_reply)
        t2.daemon = True
        t2.start()
        t2.join(60)
        # Default: earliest reply if no response
        if t2.is_alive() or not reply_index[0]:
            info_print("No response within 60 seconds. Rejecting earliest reply.")
            def parse_time(t):
                try:
                    m = re.search(r'(\d{4}-\d{1,2}-\d{1,2} \d{2}:\d{2}:\d{2})', t)
                    if m:
                        return time.mktime(time.strptime(m.group(1), "%Y-%m-%d %H:%M:%S"))
                except Exception:
                    pass
                return 0
            earliest_idx = min(range(len(replies)), key=lambda i: parse_time(replies[i].get("reply_time", "")))
            selected_reply = earliest_idx
        elif reply_index[0].lower() in ("q", "quit"):
            info_print("Quitting as requested by user.")
            break
        elif reply_index[0].isdigit():
            selected_reply = int(reply_index[0]) - 1
            if not (0 <= selected_reply < len(replies)):
                warning_print("Invalid reply number. Skipping this request.")
                continue
        else:
            warning_print("Invalid input. Skipping this request.")
            continue

        reply = replies[selected_reply]
        reply_id = reply.get("reply_id")
        if not reply_id:
            error_print("No reply ID found for selected reply.")
            continue

        report_reply_for_post(req.get('link', ''), reply_id, headless=headless)

def main():
    global verbose
    # Get the parent package name from the module's __name__
    parent_package = __name__.split('.')[0] if '.' in __name__ else None

    if parent_package is None:
        program_name = 'wosonhj'
    elif '_' in parent_package:
        # If the parent package has an underscore, strip it
        parent_package = parent_package[:parent_package.index('_')]
        program_name = f"{parent_package} wosonhj"

    parser = argparse.ArgumentParser(
        description="Wosonhj login and request helper. Automate login, view user info, list and solve requests.",
        epilog="""
Examples:
  %(prog)s --user-info
  %(prog)s --get-active-requests --limit 10 --publisher Elsevier
  %(prog)s --solve-active-requests --no-headless
  %(prog)s --clear-cache
  %(prog)s --config /path/to/credentials.json
  %(prog)s --check-in
  %(prog)s --get-waiting-requests
  %(prog)s --get-fulfilled-requests
  %(prog)s --download-fulfilled-requests
  %(prog)s --request-doi 10.1234/abcd.efgh
  %(prog)s --doi-file /path/to/dois.txt
  %(prog)s --accept-fulfilled-requests
  %(prog)s --reject-fulfilled-requests
""",
        prog=program_name,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('--credentials', type=str, help='Path to JSON config file containing credentials')
    parser.add_argument('--no-headless', action='store_true', help='Disable headless mode for Chrome')
    parser.add_argument('--verbose', action='store_true', help='Enable verbose debug output')
    parser.add_argument('--clear-cache', action='store_true', help='Clear cached login and credentials')
    parser.add_argument('--user-info', action='store_true', help='Print user info after login')
    parser.add_argument('--get-active-requests', action='store_true', help='List active requests')
    parser.add_argument('--solve-active-requests', action='store_true', help='Solve active requests (upload files)')
    parser.add_argument('--limit', type=int, default=20, help='Limit number of requests to list')
    parser.add_argument('--order-by-point', action='store_true', help='List requests by points (high to low)')
    parser.add_argument('--publisher', type=str, help='Publisher name(s) or typeid(s) for filtering requests (comma-separated for multiple)')
    parser.add_argument('--check-in', action='store_true', help='Perform daily check-in')
    parser.add_argument('--get-waiting-requests', action='store_true', help='List your waiting requests with no replies')
    parser.add_argument('--get-fulfilled-requests', action='store_true', help='List your fulfilled requests (with replies, not closed)')
    parser.add_argument('--download-fulfilled-requests', action='store_true', help='Download attachments from fulfilled requests')
    parser.add_argument('--request-doi', type=str, help='Request a paper by DOI')
    parser.add_argument('--doi-file', type=str, help='Request multiple papers by DOI from a text file')
    parser.add_argument('--accept-fulfilled-requests', action='store_true', help='Accept replies for fulfilled requests')
    parser.add_argument('--reject-fulfilled-requests', action='store_true', help='Reject replies for fulfilled requests')
    args = parser.parse_args()
    
    # Suppress ChromeDriver and Selenium warnings/logs
    os.environ["WDM_LOG_LEVEL"] = "0"
    os.environ["PYTHONWARNINGS"] = "ignore"
    os.environ["SELENIUM_MANAGER_LOG_LEVEL"] = "OFF"
    os.environ["SELOG_LEVEL"] = "OFF"
    os.environ["ABSL_LOG_LEVEL"] = "0"
    os.environ["ABSL_LOG_TO_STDERR"] = "0"
    os.environ["ABSL_LOG_TO_STDOUT"] = "0"
    os.environ["ABSL_LOG_TO_FILE"] = "0"
    os.environ["ABSL_LOG_STREAM"] = "none"

    verbose = args.verbose
    debug_print(f"Verbose mode enabled: {verbose}")

    if args.clear_cache:
        debug_print("Clear cache option selected")
        clear_default_cache_and_config()
        success_print("Cache and credentials cleared.")
        return

    # Load credentials from specified config file or default
    if args.credentials:
        debug_print(f"Loading credentials from credentials file: {args.credentials}")
        load_credentials_from_file(args.credentials)
    else:
        debug_print(f"Loading credentials from default file: {CREDENTIALS_FILE}")
        load_credentials_from_file(CREDENTIALS_FILE)

    if args.check_in:
        debug_print("Check-in option selected")
        result = checkin_wosonhj(headless=not args.no_headless)
        if result:
            success_print("Check-in completed successfully.")
        else:
            error_print("Check-in failed.")
        return

    if args.user_info:
        debug_print("User info requested")
        info = fetch_user_info(headless=not args.no_headless)
        print_user_info(info)
        return

    if args.get_active_requests:
        debug_print("Get active requests option selected")
        publisher = args.publisher
        if publisher and publisher.isdigit():
            publisher = int(publisher)
        requests = get_active_requests(
            limit=args.limit,
            order_by_point=args.order_by_point,
            publisher=publisher,
            headless=not args.no_headless
        )
        if not requests:
            error_print("No active requests found.")
        else:
            print_requests(requests, header="📄 === Active Requests ===")
        return

    if args.get_waiting_requests:
        debug_print("Get waiting requests option selected")
        requests = get_waiting_requests(headless=not args.no_headless)
        if not requests:
            error_print("No waiting requests found.")
        else:
            print_requests(requests, header="📄 === Waiting Requests ===")
        return

    if args.get_fulfilled_requests:
        debug_print("Get fulfilled requests option selected")
        requests = get_fulfilled_requests(headless=not args.no_headless)
        if not requests:
            error_print("No fulfilled requests found.")
        else:
            print_requests(requests, header="📄 === Fulfilled Requests ===")
        return

    if args.download_fulfilled_requests:
        debug_print("Download fulfilled requests option selected")
        download_fulfilled_requests(headless=not args.no_headless)
        return

    if args.solve_active_requests:
        debug_print("Solve active requests option selected")
        publisher = args.publisher
        if publisher and publisher.isdigit():
            publisher = int(publisher)
        solve_active_requests(
            limit=args.limit,
            order_by_point=args.order_by_point,
            publisher=publisher,
            headless=not args.no_headless
        )
        return

    if args.request_doi:
        debug_print(f"Request by DOI option selected: {args.request_doi}")
        result = request_by_doi(args.request_doi, headless=not args.no_headless)
        if result:
            success_print("Request by DOI posted successfully.")
        else:
            error_print("Failed to post request by DOI.")
        return

    if args.doi_file:
        debug_print(f"Request multiple DOIs from file: {args.doi_file}")
        if not os.path.isfile(args.doi_file):
            error_print(f"DOI file not found: {args.doi_file}")
            return
        try:
            with open(args.doi_file, "r", encoding="utf-8") as f:
                text = f.read()
            dois = getpapers.extract_dois_from_text(text)
            if not dois:
                error_print("No DOIs found in the provided file.")
                return
            info_print(f"Found {len(dois)} DOIs in file. Requesting all...")
            results = request_multiple_dois(dois, headless=not args.no_headless)
            for doi, result in results.items():
                if result:
                    success_print(f"Successfully posted request for DOI: {doi}")
                else:
                    error_print(f"Failed to post request for DOI: {doi}")
        except Exception as e:
            error_print(f"Failed to process DOI file: {e}")
        return

    if args.accept_fulfilled_requests:
        debug_print("Accept fulfilled requests option selected")
        accept_fulfilled_requests(headless=not args.no_headless)
        return

    if args.reject_fulfilled_requests:
        debug_print("Reject fulfilled requests option selected")
        reject_fulfilled_requests(headless=not args.no_headless)
        return

    # Default: standard login
    debug_print("Standard login requested")
    driver = get_chrome_driver(headless=not args.no_headless)
    driver.get(WOSONHJ_LOGIN_URL)
    time.sleep(2)
    debug_print("Filling in username and password fields")
    driver.find_element(By.NAME, "username").send_keys(USERNAME)
    driver.find_element(By.NAME, "password").send_keys(PASSWORD)
    driver.find_element(By.NAME, "password").send_keys(Keys.RETURN)
    debug_print("Submitted login form, waiting for login to complete")
    time.sleep(5)
    info_print("Logged in to Wosonhj.")
    driver.quit()

if __name__ == "__main__":
    main()