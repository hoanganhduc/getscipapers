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
import getpass
import argparse
import threading
import re
import readline
import glob
import requests as pyrequests

# --- Configuration for WosonHJ Login ---
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

def get_chrome_driver(headless=True):
    debug_print(f"Creating Chrome driver (headless={headless})")
    options = webdriver.ChromeOptions()
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

def login_and_navigate_wosonhj(url, headless=True):
    global USERNAME, PASSWORD
    debug_print(f"Starting login_and_navigate_wosonhj to: {url}")
    driver = get_chrome_driver(headless)

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
    Fetch active requests from WosonHJ, optionally filtered by publisher.
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

def print_active_requests(requests):
    """
    Print a list of active requests with details and icons.
    """
    if not requests:
        error_print("No active requests to print.")
        return

    print("\n📄 === Active Requests ===")
    for idx, req in enumerate(requests, 1):
        print(f"{idx}. [{req.get('publisher', '')}] {req.get('title', '')}")
        print(f"    💎 Points: {req.get('points', '')} | 💬 Replies: {req.get('replies', '')} | 👤 Author: {req.get('author', '')} | 🕒 Time: {req.get('post_time', '')}")
        print(f"    🔗 Link: {req.get('link', '')}")
        if req.get('doi', ''):
            print(f"    📖 DOI: {req.get('doi', '')}")
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

    print_active_requests(requests)

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
    Login to WosonHJ and perform daily check-in by accessing the check-in URL.
    Returns True if check-in is successful, False otherwise.
    """
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

def list_my_waiting_requests(headless=True):
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
        items = driver.find_elements(By.CSS_SELECTOR, "li.ren-reward-list-li")
        for item in items:
            try:
                summary_div = item.find_element(By.CSS_SELECTOR, 'div.ren-list-summary')
                h2_elem = summary_div.find_element(By.TAG_NAME, 'h2')
                a_elem = h2_elem.find_element(By.CSS_SELECTOR, 'a[target="_blank"]')
                link = a_elem.get_attribute('href') if a_elem else ""
                title_spans = a_elem.find_elements(By.TAG_NAME, 'span')
                title = title_spans[-1].text.strip() if len(title_spans) > 1 else (title_spans[0].text.strip() if title_spans else "")
                publisher_elem = summary_div.find_elements(By.CSS_SELECTOR, 'div.ren-summary-tag a')
                publisher_name = publisher_elem[0].text.strip() if publisher_elem else ""
                box_div = item.find_element(By.CSS_SELECTOR, 'div.ren-reward-list-box')
                views_elem = box_div.find_elements(By.CSS_SELECTOR, 'div.views')
                points = views_elem[0].text.split()[0].strip() if views_elem else ""
                replies_elem = box_div.find_elements(By.CSS_SELECTOR, 'div.replies')
                replies = replies_elem[0].text.split()[0].strip() if replies_elem else ""
                author_elem = summary_div.find_element(By.CSS_SELECTOR, 'div.ren-reward-us a.ren-index-us-name')
                author = author_elem.text.strip() if author_elem else ""
                time_elem = summary_div.find_element(By.CSS_SELECTOR, 'div.ren-reward-us span.time span')
                post_time = time_elem.get_attribute('title') if time_elem else time_elem.text.strip() if time_elem else ""
                icon_elem = a_elem.find_elements(By.CSS_SELECTOR, 'span img')
                icon_url = icon_elem[0].get_attribute('src') if icon_elem else ""

                # Only include requests with 0 replies
                if replies == "0":
                    requests.append({
                        "title": title,
                        "link": link,
                        "points": points,
                        "author": author,
                        "post_time": post_time,
                        "publisher": publisher_name,
                        "replies": replies,
                        "icon_url": icon_url
                    })
            except Exception as e:
                debug_print(f"Error parsing my request item: {e}")
    except Exception as e:
        error_print(f"Failed to fetch my waiting requests: {e}")

    driver.quit()
    return requests

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
        description="WosonHJ login and request helper. Automate login, view user info, list and solve requests.",
        epilog="""
Examples:
  %(prog)s --user-info
  %(prog)s --get-active-requests --limit 10 --publisher Elsevier
  %(prog)s --solve-active-requests --no-headless
  %(prog)s --clear-cache
  %(prog)s --config /path/to/credentials.json --home
  %(prog)s --check-in
  %(prog)s --get-waiting-requests
""",
        prog=program_name,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('--config', type=str, help='Path to JSON config file containing credentials')
    parser.add_argument('--no-headless', action='store_true', help='Disable headless mode for Chrome')
    parser.add_argument('--home', action='store_true', help='Login and navigate to home page after login')
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
    args = parser.parse_args()

    verbose = args.verbose
    debug_print(f"Verbose mode enabled: {verbose}")

    if args.clear_cache:
        debug_print("Clear cache option selected")
        clear_default_cache_and_config()
        success_print("Cache and credentials cleared.")
        return

    # Load credentials from specified config file or default
    if args.config:
        debug_print(f"Loading credentials from config file: {args.config}")
        load_credentials_from_file(args.config)
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
            print_active_requests(requests)
        return

    if args.get_waiting_requests:
        debug_print("Get waiting requests option selected")
        requests = list_my_waiting_requests(headless=not args.no_headless)
        if not requests:
            error_print("No waiting requests found.")
        else:
            print_active_requests(requests)
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

    if args.home:
        debug_print("Login and navigate to home page requested")
        driver = login_and_navigate_wosonhj(WOSONHJ_HOME_URL, headless=not args.no_headless)
        if driver:
            info_print("Logged in and navigated to home page.")
            driver.quit()
    else:
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
        info_print("Logged in to WosonHJ.")
        driver.quit()

if __name__ == "__main__":
    main()