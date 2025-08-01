import argparse
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import pickle
import os
import re
import time
import signal
import sys
import threading
import queue
import json
import readline
import getpass
import glob
import platform
from . import getpapers
import tempfile
import datetime

USERNAME = "" # Replace with your actual username/email
PASSWORD = "" # Replace with your actual password
# Determine the appropriate directory for storing cache based on the operating system

def get_cache_directory():
    """Get the appropriate directory for storing cache based on the operating system."""
    system = platform.system()
    if system == "Windows":
        # Use %APPDATA%\getscipapers\ablesci on Windows
        return os.path.join(os.environ.get('APPDATA', os.path.expanduser('~')), 'getscipapers', 'ablesci')
    elif system == "Darwin":  # macOS
        # Use ~/Library/Application Support/getscipapers/ablesci on macOS
        return os.path.join(os.path.expanduser('~'), 'Library', 'Application Support', 'getscipapers', 'ablesci')
    else:  # Linux and other Unix-like systems
        # Use ~/.config/getscipapers/ablesci on Linux
        return os.path.join(os.path.expanduser('~'), '.config', 'getscipapers', 'ablesci')

def get_credentials_directory():
    """Get the appropriate directory for storing credentials based on the operating system."""
    # Use the same logic as cache directory for consistency
    return get_cache_directory()

# Create the cache directory if it doesn't exist
cache_dir = get_cache_directory()
os.makedirs(cache_dir, exist_ok=True)

CACHE_FILE = os.path.join(cache_dir, 'ablesci_cache.pkl')
# Determine the credentials file location (default: credentials.json in credentials directory)
credentials_dir = get_credentials_directory()
os.makedirs(credentials_dir, exist_ok=True)
CREDENTIALS_FILE = os.path.join(credentials_dir, 'credentials.json')

def get_default_download_folder():
    """
    Get the default download folder for the current OS.
    - Windows: %USERPROFILE%\Downloads\getscipapers\ablesci
    - macOS: ~/Downloads/getscipapers/ablesci
    - Linux: ~/Downloads/getscipapers/ablesci
    """
    system = platform.system()
    if system == "Windows":
        base = os.environ.get('USERPROFILE', os.path.expanduser('~'))
        folder = os.path.join(base, 'Downloads', 'getscipapers', 'ablesci')
    else:
        folder = os.path.join(os.path.expanduser('~'), 'Downloads', 'getscipapers', 'ablesci')
    os.makedirs(folder, exist_ok=True)
    return folder

DEFAULT_DOWNLOAD_FOLDER = get_default_download_folder()

verbose = False

def debug_print(message):
    if verbose:
        print(f"[DEBUG] {message}")

def load_credentials_from_file(filepath):
    """Load login credentials from a JSON file.

    Args:
        filepath: Path to JSON file containing credentials

    Returns:
        tuple: (username, password) or (None, None) if file doesn't exist or is invalid

    Expected JSON format:
    {
        "ablesci_username": "your_email@example.com",
        "ablesci_password": "your_password"
    }
    """
    global USERNAME, PASSWORD
    debug_print(f"Attempting to load credentials from: {filepath}")

    if not os.path.exists(filepath):
        debug_print(f"Credentials file not found: {filepath}")
        return None, None

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            credentials = json.load(f)

        username = credentials.get('ablesci_username')
        password = credentials.get('ablesci_password')

        if not username or not password:
            debug_print("Invalid credentials file: missing ablesci_username or ablesci_password")
            return None, None

        debug_print(f"Successfully loaded credentials for user: {username}")

        # Set global variables
        USERNAME = username
        PASSWORD = password

        # If credentials file is not the default, update default if different
        if os.path.abspath(filepath) != os.path.abspath(CREDENTIALS_FILE):
            debug_print("Credentials loaded from non-default location, checking if update needed")
            need_update = True
            if os.path.exists(CREDENTIALS_FILE):
                try:
                    with open(CREDENTIALS_FILE, 'r', encoding='utf-8') as f2:
                        default_creds = json.load(f2)
                    if (default_creds.get('ablesci_username') == username and
                        default_creds.get('ablesci_password') == password):
                        need_update = False
                except Exception as e:
                    debug_print(f"Error reading default credentials file: {e}")
            if need_update:
                try:
                    with open(CREDENTIALS_FILE, 'w', encoding='utf-8') as f2:
                        json.dump({
                            "ablesci_username": username,
                            "ablesci_password": password
                        }, f2, ensure_ascii=False, indent=2)
                    debug_print("Default credentials file updated with new credentials")
                except Exception as e:
                    debug_print(f"Failed to update default credentials file: {e}")
        else:
            # If credentials file is the default and does not exist, save it
            if not os.path.exists(CREDENTIALS_FILE):
                try:
                    with open(CREDENTIALS_FILE, 'w', encoding='utf-8') as f2:
                        json.dump({
                            "ablesci_username": username,
                            "ablesci_password": password
                        }, f2, ensure_ascii=False, indent=2)
                    debug_print("Default credentials file created after loading credentials")
                except Exception as e:
                    debug_print(f"Failed to create default credentials file: {e}")

        return username, password

    except json.JSONDecodeError as e:
        debug_print(f"Invalid JSON in credentials file: {e}")
        return None, None
    except Exception as e:
        debug_print(f"Error reading credentials file: {e}")
        return None, None

def get_chrome_driver(headless=True):
    debug_print(f"Creating Chrome driver (headless={headless})")
    # Suppress DevTools logging
    options = webdriver.ChromeOptions()
    # Suppress DevTools logging
    options.add_experimental_option('excludeSwitches', ['enable-logging'])
    if headless:
        options.add_argument('--headless=new')
        options.add_argument('--disable-gpu')
        
    # Use a subdirectory of cache_dir for Chrome user data
    user_data_dir = os.path.join(cache_dir, "chrome_user_data")
    os.makedirs(user_data_dir, exist_ok=True)
    options.add_argument(f"--user-data-dir={user_data_dir}")
    debug_print(f"Using Chrome user data directory: {user_data_dir}")
    
    # Suppress Chrome messages
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

def login_and_navigate(url, headless=True):
    """Login to ablesci.com and navigate to the specified URL.
    Uses cache if available and valid, otherwise performs full login."""
    debug_print(f"Starting login and navigate to: {url}")
    driver = get_chrome_driver(headless)
    
    try:
        debug_print("Navigating to homepage")
        max_retries = 3
        for attempt in range(max_retries):
            try:
                driver.get('https://www.ablesci.com')
                break
            except Exception as e:
                debug_print(f"Attempt {attempt + 1} failed: {e}")
                if attempt == max_retries - 1:
                    print(f"Failed to load homepage after {max_retries} attempts")
                    driver.quit()
                    return None
                time.sleep(2)
        
        # Load and test cache if they exist
        cache_valid = False
        if os.path.exists(CACHE_FILE):
            debug_print(f"Loading cache from {CACHE_FILE}")
            with open(CACHE_FILE, 'rb') as f:
                cache = pickle.load(f)
            for cookie in cache:
                driver.add_cookie(cookie)
            debug_print(f"Loaded {len(cache)} cache")
            
            # Test if cache are still valid by checking user status
            debug_print("Testing cache validity")
            driver.get('https://www.ablesci.com/my/home')
            wait = WebDriverWait(driver, 5)
            
            try:
                # Check if we can access user home page (logged in)
                wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, '.fly-home')))
                debug_print("Cache are valid, already logged in")
                cache_valid = True
            except:
                debug_print("Cache are invalid or expired, proceeding with login")
                cache_valid = False
        else:
            debug_print("No cache file found")
        
        # If cache are invalid, perform full login
        if not cache_valid:
            debug_print("Performing full login process")
            
            # Load credentials from file first, then fallback to hardcoded
            username, password = load_credentials_from_file(CREDENTIALS_FILE)
            if not username or not password:
                debug_print("Using hardcoded credentials")
                username, password = USERNAME, PASSWORD
            
            # Try login with existing credentials
            login_successful = False
            try:
                # Navigate to login page
                debug_print("Navigating to login page")
                driver.get('https://www.ablesci.com/site/login')
                wait = WebDriverWait(driver, 10)
                
                debug_print("Waiting for username input field")
                username_input = wait.until(EC.presence_of_element_located((By.ID, 'LAY-user-login-email')))
                password_input = driver.find_element(By.ID, 'LAY-user-login-password')

                # Ensure the "remember me" checkbox is checked
                debug_print("Checking remember me checkbox")
                remember_checkbox = driver.find_element(By.NAME, 'remember')
                if not remember_checkbox.is_selected():
                    remember_checkbox.click()
                    debug_print("Remember me checkbox clicked")

                debug_print("Entering credentials")
                username_input.send_keys(username)
                password_input.send_keys(password)

                debug_print("Clicking login button")
                login_button = driver.find_element(By.CSS_SELECTOR, 'button[lay-filter="do-submit"]')
                login_button.click()

                debug_print("Waiting for login redirect")
                wait.until(lambda d: d.current_url != 'https://www.ablesci.com/site/login')
                
                # Verify login success by checking if we're on a valid page
                if 'login' not in driver.current_url.lower():
                    debug_print(f"Login successful, current URL: {driver.current_url}")
                    login_successful = True
                else:
                    debug_print("Login failed - still on login page")
                    
            except Exception as e:
                debug_print(f"Login with existing credentials failed: {e}")
                login_successful = False
            
            # If login failed, ask user for manual credentials
            if not login_successful:
                debug_print("Automatic login failed, requesting manual credentials")
                print("\nAutomatic login failed. Please enter your credentials manually:")
                
                manual_username = input("Email: ").strip()
                manual_password = getpass.getpass("Password: ").strip()
                
                if not manual_username or not manual_password:
                    print("Invalid credentials provided")
                    driver.quit()
                    return None
                
                try:
                    # Navigate to login page again
                    debug_print("Navigating to login page for manual login")
                    driver.get('https://www.ablesci.com/site/login')
                    wait = WebDriverWait(driver, 10)
                    
                    debug_print("Waiting for username input field (manual login)")
                    username_input = wait.until(EC.presence_of_element_located((By.ID, 'LAY-user-login-email')))
                    password_input = driver.find_element(By.ID, 'LAY-user-login-password')

                    # Clear any existing values
                    username_input.clear()
                    password_input.clear()

                    # Ensure the "remember me" checkbox is checked
                    debug_print("Checking remember me checkbox (manual login)")
                    remember_checkbox = driver.find_element(By.NAME, 'remember')
                    if not remember_checkbox.is_selected():
                        remember_checkbox.click()
                        debug_print("Remember me checkbox clicked (manual login)")

                    debug_print("Entering manual credentials")
                    username_input.send_keys(manual_username)
                    password_input.send_keys(manual_password)

                    debug_print("Clicking login button (manual login)")
                    login_button = driver.find_element(By.CSS_SELECTOR, 'button[lay-filter="do-submit"]')
                    login_button.click()

                    debug_print("Waiting for manual login redirect")
                    wait.until(lambda d: d.current_url != 'https://www.ablesci.com/site/login')
                    
                    # Verify manual login success
                    if 'login' not in driver.current_url.lower():
                        debug_print(f"Manual login successful, current URL: {driver.current_url}")
                        login_successful = True
                        
                        # Save cache after successful manual login
                        debug_print(f"Saving cache after manual login to {CACHE_FILE}")
                        with open(CACHE_FILE, 'wb') as f:
                            pickle.dump(driver.get_cookies(), f)
                        debug_print("Cache saved successfully after manual login")
                        print("Login successful! Credentials have been saved for future use.")
                    else:
                        debug_print("Manual login failed - still on login page")
                        print("Manual login failed. Please check your credentials.")
                        driver.quit()
                        return None
                        
                except Exception as e:
                    debug_print(f"Manual login failed: {e}")
                    print(f"Manual login failed: {e}")
                    driver.quit()
                    return None
            else:
                # Save cache after successful automatic login
                debug_print(f"Saving cache to {CACHE_FILE}")
                with open(CACHE_FILE, 'wb') as f:
                    pickle.dump(driver.get_cookies(), f)
                debug_print("Cache saved successfully")
        
        # Navigate to target URL
        debug_print(f"Navigating to target URL: {url}")
        driver.get(url)
        
        return driver
        
    except Exception as e:
        debug_print(f"Error in login_and_navigate: {e}")
        print(f"Failed to login and navigate to {url}: {e}")
        driver.quit()
        return None

def get_user_info(headless=True):
    debug_print("Starting get user info process")
    driver = login_and_navigate('https://www.ablesci.com/my/home', headless)
    
    if driver is None:
        print("Failed to login and navigate to user home page")
        return None, None
        
    try:
        wait = WebDriverWait(driver, 10)
        
        debug_print("Waiting for .fly-home element")
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, '.fly-home')))

        # Get username from <h1> inside .fly-home
        debug_print("Extracting username")
        user_name_elem = driver.find_element(By.CSS_SELECTOR, '.fly-home h1')
        user_name = user_name_elem.get_attribute('innerText').strip().split('\n')[0]
        debug_print(f"Username extracted: {user_name}")

        # Get points from .fly-home-info span[style*="color: #FF7200;"]
        debug_print("Extracting points")
        points_elem = driver.find_element(By.CSS_SELECTOR, '.fly-home-info span[style*="color: #FF7200;"]')
        points_text = points_elem.text.strip()
        debug_print(f"Points text: {points_text}")
        points_match = re.search(r'(\d+)', points_text)
        points = int(points_match.group(1)) if points_match else 0
        debug_print(f"Points extracted: {points}")

        print(f"Username: {user_name}")
        print(f"Points: {points}")
        return user_name, points
    except Exception as e:
        debug_print(f"Error getting user info: {e}")
        print(f"Error retrieving user info: {e}")
        return None, None
    finally:
        debug_print("Closing user info driver")
        driver.quit()

def request_paper_by_doi(doi, headless=True):
    debug_print(f"Starting paper request for DOI: {doi}")
    driver = login_and_navigate('https://www.ablesci.com/assist/create', headless)
    
    if driver is None:
        print(f"Failed to login and navigate for DOI: {doi}")
        return
        
    try:
        wait = WebDriverWait(driver, 10)
        
        # Wait for the DOI/PMID/title input field with id="onekey"
        debug_print("Waiting for DOI input field")
        doi_input = wait.until(EC.presence_of_element_located((By.ID, 'onekey')))
        doi_input.clear()
        doi_input.send_keys(doi)
        debug_print(f"DOI entered: {doi}")
        
        # Click the "智能提取文献信息" button (button with class "onekey-search")
        debug_print("Clicking search button")
        search_btn = driver.find_element(By.CSS_SELECTOR, 'button.onekey-search')
        search_btn.click()
        
        # Wait for the system to extract info
        debug_print("Waiting for extraction results")
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, '.assist-detail, .layui-layer-content')))
        
        # Wait for loading to complete
        max_retries = 10
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                debug_print("Waiting for layer dialog")
                wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, '.layui-layer-content')))
                
                debug_print("Checking dialog content")
                result = driver.execute_script("""
                var content = document.querySelector('.layui-layer-content');
                if (content) {
                    var contentText = content.innerText.trim();
                    if (contentText.includes('正在查询') || contentText.includes('请稍候')) {
                        return {isLoading: true, message: contentText};
                    }
                }
                return {isLoading: false};
                """)
                
                if result['isLoading']:
                    debug_print(f"System is still loading: {result['message']}, waiting...")
                    retry_count += 1
                    time.sleep(3)
                    continue
                else:
                    break
                    
            except Exception as e:
                debug_print(f"Error checking dialog state: {e}")
                break
        
        if retry_count >= max_retries:
            print(f"Timeout waiting for paper extraction for DOI: {doi}")
            return
        
        # Process the dialog result
        try:
            debug_print("Executing JavaScript to extract paper info")
            result = driver.execute_script("""
            var buttons = document.querySelectorAll('.layui-layer-btn a');
            var content = document.querySelector('.layui-layer-content');
            
            if (buttons.length === 3) {
                var paperInfo = {};
                var contentText = content.innerHTML;
                
                var titleMatch = contentText.match(/<span class="layui-badge layui-bg-gray">标题<\/span>\s*([^<]+)/);
                paperInfo.title = titleMatch ? titleMatch[1].trim() : '';
                
                var doiMatch = contentText.match(/<span class="layui-badge layui-bg-gray">DOI<\/span>\s*([^<]+)/);
                paperInfo.doi = doiMatch ? doiMatch[1].trim() : '';
                
                var journalMatch = contentText.match(/<span class="layui-badge layui-bg-gray">期刊<\/span>\s*([^<]+)/);
                paperInfo.journal = journalMatch ? journalMatch[1].trim() : '';
                
                var authorsMatch = contentText.match(/<span class="layui-badge layui-bg-gray">作者<\/span>\s*([^<]+)/);
                paperInfo.authors = authorsMatch ? authorsMatch[1].trim() : '';
                
                var publishMatch = contentText.match(/<span class="layui-badge layui-bg-gray">出版日期<\/span>\s*([^<]+)/);
                paperInfo.publishDate = publishMatch ? publishMatch[1].trim() : '';
                
                var urlMatch = contentText.match(/<span class="layui-badge layui-bg-gray">网址<\/span>\s*([^<]+)/);
                paperInfo.url = urlMatch ? urlMatch[1].trim() : '';
                
                var similarMatch = contentText.match(/<span class="layui-badge layui-bg-gray">相似度<\/span>\s*(\d+)%/);
                paperInfo.similarity = similarMatch ? similarMatch[1] : '';
                
                var pointsMatch = contentText.match(/最低悬赏\s*<span[^>]*>\s*(\d+)\s*<\/span>\s*积分/);
                paperInfo.minPoints = pointsMatch ? pointsMatch[1] : '';
                
                return {success: true, paperInfo: paperInfo};
            } else if (buttons.length === 1) {
                var errorMsg = content.innerText.trim();
                return {success: false, error: errorMsg};
            } else if (buttons.length === 0) {
                var errorMsg = content ? content.innerText.trim() : 'Dialog content not found';
                return {success: false, error: errorMsg};
            }
            return {success: false, error: 'Unknown dialog state - found ' + buttons.length + ' buttons'};
            """)
            
            debug_print(f"JavaScript result: {result}")
            
            if result and result.get('success'):
                paper_info = result['paperInfo']
                print(f"\nPaper information for DOI: {doi}")
                print(f"  Title: {paper_info.get('title', 'N/A')}")
                print(f"  Journal: {paper_info.get('journal', 'N/A')}")
                print(f"  Authors: {paper_info.get('authors', 'N/A')}")
                print(f"  Publish Date: {paper_info.get('publishDate', 'N/A')}")
                print(f"  URL: {paper_info.get('url', 'N/A')}")
                if paper_info.get('similarity'):
                    print(f"  Similarity: {paper_info['similarity']}%")
                if paper_info.get('minPoints'):
                    print(f"  Minimum Points: {paper_info['minPoints']}")
                
                # Get user confirmation with timeout
                try:
                    def get_user_response():
                        try:
                            if hasattr(signal, 'SIGALRM'):
                                def timeout_handler(_, __):
                                    raise TimeoutError("Input timeout")
                                
                                signal.signal(signal.SIGALRM, timeout_handler)
                                signal.alarm(30)
                                response = input(f"\nDo you want to request this paper? (Y/n): ").strip().lower()
                                signal.alarm(0)
                                return response
                            else:
                                # Windows fallback
                                q = queue.Queue()
                                def input_thread():
                                    try:
                                        response = input(f"\nDo you want to request this paper? (Y/n): ").strip().lower()
                                        q.put(response)
                                    except:
                                        q.put('')
                                
                                thread = threading.Thread(target=input_thread)
                                thread.daemon = True
                                thread.start()
                                thread.join(timeout=30)
                                
                                if thread.is_alive():
                                    raise TimeoutError("Input timeout")
                                
                                return q.get_nowait() if not q.empty() else 'y'
                        except (TimeoutError, queue.Empty):
                            print("\nNo response received. Proceeding with request...")
                            return 'y'
                    
                    response = get_user_response()
                    
                    if response and response not in ['y', 'yes']:
                        print("Request cancelled by user.")
                        driver.execute_script("""
                        var buttons = document.querySelectorAll('.layui-layer-btn a');
                        if (buttons.length === 3) {
                            buttons[2].click();
                        }
                        """)
                        return
                
                except Exception as e:
                    debug_print(f"Error in confirmation prompt: {e}")
                    print("\nProceeding with request...")
                
                # Submit the request
                debug_print("Submitting paper request")
                driver.execute_script("""
                var buttons = document.querySelectorAll('.layui-layer-btn a');
                if (buttons.length === 3) {
                    buttons[0].click();
                }
                """)
                
                print(f"Successfully requested paper for DOI: {doi}")
                time.sleep(2)
            else:
                print(f"Failed to request paper for DOI: {doi}. Error: {result['error']}")
                driver.execute_script("""
                var buttons = document.querySelectorAll('.layui-layer-btn a');
                if (buttons.length === 1) {
                    buttons[0].click();
                }
                """)
            
        except Exception as e:
            debug_print(f"Exception in dialog processing: {e}")
            print(f"Error processing dialog for DOI: {doi}: {e}")
    finally:
        debug_print("Closing paper request driver")
        driver.quit()

def is_valid_doi(doi):
    # Basic DOI validation: starts with "10." and has a "/" and some suffix
    pattern = r'^10\.\d{4,9}/[-._;()/:A-Z0-9]+$'
    is_valid = re.match(pattern, doi, re.IGNORECASE) is not None
    debug_print(f"DOI validation for '{doi}': {is_valid}")
    return is_valid

def parse_dois_input(doi_input):
    """Parse input which can be a file path or a space/comma separated list of DOIs."""
    debug_print(f"Parsing DOI input: {doi_input}")
    if os.path.isfile(doi_input):
        debug_print("Input is a file path")
        return getpapers.extract_dois_from_file(doi_input)
    return getpapers.extract_dois_from_text(doi_input)

def request_multiple_dois(dois, headless=True):
    """
    Request multiple DOIs and return a list of results.

    Args:
        dois (list): List of DOI strings.
        headless (bool): Whether to run browser in headless mode.

    Returns:
        list: List of dicts with keys: 'doi', 'success', 'error' (if any).
    """
    debug_print(f"Starting batch request for {len(dois)} DOIs")
    results = []
    for i, doi in enumerate(dois, 1):
        debug_print(f"Processing DOI {i}/{len(dois)}: {doi}")
        if not is_valid_doi(doi):
            print(f"Invalid DOI: {doi}")
            results.append({'doi': doi, 'success': False, 'error': 'Invalid DOI'})
            continue
        print(f"Requesting paper for DOI: {doi}")
        try:
            request_paper_by_doi(doi, headless=headless)
            results.append({'doi': doi, 'success': True})
        except Exception as e:
            debug_print(f"Exception requesting DOI {doi}: {e}")
            results.append({'doi': doi, 'success': False, 'error': str(e)})
    return results

def get_waiting_requests(headless=True):
    debug_print("Starting to get waiting requests")
    driver = login_and_navigate('https://www.ablesci.com/my/assist-my?status=waiting', headless)
    
    if driver is None:
        print("Failed to login and navigate to waiting requests page")
        return []
        
    try:
        wait = WebDriverWait(driver, 10)
        
        # Wait for the page to load
        debug_print("Waiting for page content to load")
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'body')))
        time.sleep(5)  # Additional wait for dynamic content
        
        # Get all waiting request items from table
        debug_print("Extracting waiting requests from table")
        requests = driver.execute_script("""
        var requests = [];
        var tableRows = document.querySelectorAll('table tr, .layui-table tr');
        
        tableRows.forEach(function(row) {
            var request = {};
            
            // Look for the paper title link in the row
            var titleLink = row.querySelector('a[href*="/assist/detail"]');
            if (titleLink) {
                request.title = titleLink.innerText.trim();
                request.detailUrl = titleLink.href;
                
                // Get title from the link's title attribute if text is empty
                if (!request.title && titleLink.title) {
                    request.title = titleLink.title;
                }
            }
            
            // Look for publisher info
            var publisherImg = row.querySelector('.paper-publisher img.publisher-icon');
            if (publisherImg) {
                request.publisher = publisherImg.title || publisherImg.alt || '';
            }
            
            // Try to find DOI in the row content
            var textContent = row.innerText;
            var doiMatch = textContent.match(/10\\.\\d{4,9}\\/[-._;()\\/:A-Z0-9]+/i);
            if (doiMatch) {
                request.doi = doiMatch[0];
            }
            
            // Look for time/status information in table cells
            var cells = row.querySelectorAll('td');
            cells.forEach(function(cell) {
                var cellText = cell.innerText.trim();
                
                // Look for points/reward information
                var pointsMatch = cellText.match(/(\\d+)\\s*积分|(\\d+)\\s*points?/i);
                if (pointsMatch) {
                    request.points = pointsMatch[1] || pointsMatch[2];
                }
                
                // Look for time information
                if (cellText.match(/\\d{4}-\\d{2}-\\d{2}|\\d+天前|\\d+小时前|\\d+分钟前/)) {
                    request.time = cellText;
                }
                
                // Look for status information
                if (cellText.includes('等待') || cellText.includes('waiting')) {
                    request.status = cellText;
                }
            });
            
            // Set default points to 10 if not found
            if (!request.points) {
                request.points = '10';
            }
            
            // Only add if we found at least a title
            if (request.title) {
                requests.push(request);
            }
        });
        
        return requests;
        """)
        
        debug_print(f"Found {len(requests)} waiting requests")
        
        if requests:
            print(f"\nFound {len(requests)} waiting requests:")
            print("-" * 80)
            for i, request in enumerate(requests, 1):
                print(f"{i}. Title: {request.get('title', 'N/A')}")
                if request.get('publisher'):
                    print(f"   Publisher: {request['publisher']}")
                if request.get('doi'):
                    print(f"   DOI: {request['doi']}")
                if request.get('time'):
                    print(f"   Time: {request['time']}")
                if request.get('points'):
                    print(f"   Points: {request['points']}")
                if request.get('status'):
                    print(f"   Status: {request['status']}")
                if request.get('detailUrl'):
                    print(f"   Detail URL: {request['detailUrl']}")
                print()
        else:
            print("No waiting requests found.")
            
        return requests
        
    except Exception as e:
        debug_print(f"Error getting waiting requests: {e}")
        print(f"Error retrieving waiting requests: {e}")
        return []
    finally:
        debug_print("Closing waiting requests driver")
        driver.quit()

def cancel_waiting_request(detail_url, headless=True):
    """
    Follow the detail URL of a waiting request and cancel it.
    Based on the JavaScript code that handles assist-close-btn clicks.
    """
    debug_print(f"Starting to cancel waiting request: {detail_url}")
    driver = login_and_navigate(detail_url, headless)
    if driver is None:
        print(f"Failed to open detail page: {detail_url}")
        return False
    try:
        wait = WebDriverWait(driver, 10)
        # Wait for the assist-close-btn button to appear
        debug_print("Waiting for assist-close-btn button")
        close_btn = wait.until(
            EC.element_to_be_clickable(
                (By.CSS_SELECTOR, '.assist-close-btn')
            )
        )
        # Click the assist-close-btn button
        debug_print("Clicking assist-close-btn button")
        close_btn.click()
        
        # Wait for the dialog with textarea to appear
        debug_print("Waiting for close reason dialog")
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, '#handle-note')))
        
        # Fill in the required close reason textarea
        debug_print("Filling close reason")
        reason_textarea = driver.find_element(By.ID, 'handle-note')
        reason_textarea.clear()
        reason_textarea.send_keys("不再需要此文件")  # Default reason
        
        # Find and click the confirm button in the layer dialog
        debug_print("Looking for confirm button")
        confirm_btn = wait.until(
            EC.element_to_be_clickable(
                (By.CSS_SELECTOR, '.layui-layer-btn0, .layui-layer-btn a:first-child')
            )
        )
        debug_print("Clicking confirm button")
        confirm_btn.click()
        
        # Wait a moment for the request to be processed
        time.sleep(2)
        
        print(f"Successfully cancelled request: {detail_url}")
        return True
    except Exception as e:
        debug_print(f"Error cancelling request: {e}")
        print(f"Failed to cancel request: {detail_url} ({e})")
        return False
    finally:
        debug_print("Closing cancel request driver")
        driver.quit()
        
def interactive_cancel_waiting_requests(headless=True):
    """
    List waiting requests, prompt user to select one or more (comma-separated or range, e.g., 1,3,5-7) to cancel, and cancel them.
    Supports single numbers, comma-separated list, and ranges (e.g., 1,3,5-7).
    If no response from user for 30 seconds, quit.
    """
    requests = get_waiting_requests(headless=headless)
    if not requests:
        print("No waiting requests to cancel.")
        return

    print("Enter the numbers of the requests you want to cancel (comma-separated or range, e.g., 1,3,5-7), or press Enter to skip:")

    # Input with 30s timeout (cross-platform)
    def input_with_timeout(prompt, timeout=30):
        q = queue.Queue()

        def inner():
            try:
                q.put(input(prompt))
            except Exception:
                q.put(None)

        t = threading.Thread(target=inner)
        t.daemon = True
        t.start()
        t.join(timeout)
        if t.is_alive():
            return None
        return q.get() if not q.empty() else None

    selection = input_with_timeout("Selection: ", 30)
    if selection is None:
        print("\nNo input received in 30 seconds. Cancel operation aborted.")
        return

    selection = selection.strip()
    if not selection:
        print("No requests selected for cancellation.")
        return

    # Parse user input (comma-separated numbers and ranges)
    indices = set()
    for part in selection.split(','):
        part = part.strip()
        if '-' in part:
            try:
                start, end = map(int, part.split('-', 1))
                if start > end:
                    print(f"Invalid range: {part} (start > end)")
                    continue
                for idx in range(start, end + 1):
                    if 1 <= idx <= len(requests):
                        indices.add(idx - 1)
                    else:
                        print(f"Invalid selection: {idx} (out of range)")
            except Exception:
                print(f"Invalid range input: {part}")
        elif part.isdigit():
            idx = int(part)
            if 1 <= idx <= len(requests):
                indices.add(idx - 1)
            else:
                print(f"Invalid selection: {part} (out of range)")
        elif part:
            print(f"Invalid input: {part}")

    if not indices:
        print("No valid requests selected for cancellation.")
        return

    for idx in sorted(indices):
        req = requests[idx]
        print(f"Cancelling request {idx+1}: {req.get('title', 'N/A')}")
        success = cancel_waiting_request(req.get('detailUrl'), headless=headless)
        if not success:
            print(f"Failed to cancel request {idx+1}.")

def get_fulfilled_requests(headless=True):
    debug_print("Starting to get fulfilled requests")
    driver = login_and_navigate('https://www.ablesci.com/my/assist-my?status=uploaded', headless)
    
    if driver is None:
        print("Failed to login and navigate to fulfilled requests page")
        return []
        
    try:
        wait = WebDriverWait(driver, 10)
        debug_print("Waiting for page content to load")
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'body')))
        time.sleep(5)  # Wait for dynamic content
        
        debug_print("Extracting fulfilled requests from table")
        requests = driver.execute_script("""
        var requests = [];
        var tableRows = document.querySelectorAll('table tr, .layui-table tr');
        
        tableRows.forEach(function(row) {
            var request = {};
            var titleLink = row.querySelector('a[href*="/assist/detail"]');
            if (titleLink) {
                request.title = titleLink.innerText.trim();
                request.detailUrl = titleLink.href;
                if (!request.title && titleLink.title) {
                    request.title = titleLink.title;
                }
            }
            var publisherImg = row.querySelector('.paper-publisher img.publisher-icon');
            if (publisherImg) {
                request.publisher = publisherImg.title || publisherImg.alt || '';
            }
            var textContent = row.innerText;
            var doiMatch = textContent.match(/10\\.\\d{4,9}\\/[-._;()\\/:A-Z0-9]+/i);
            if (doiMatch) {
                request.doi = doiMatch[0];
            }
            var cells = row.querySelectorAll('td');
            cells.forEach(function(cell) {
                var cellText = cell.innerText.trim();
                var pointsMatch = cellText.match(/(\\d+)\\s*积分|(\\d+)\\s*points?/i);
                if (pointsMatch) {
                    request.points = pointsMatch[1] || pointsMatch[2];
                }
                if (cellText.match(/\\d{4}-\\d{2}-\\d{2}|\\d+天前|\\d+小时前|\\d+分钟前/)) {
                    request.time = cellText;
                }
                if (cellText.includes('已上传') || cellText.lowerCase?.().includes('uploaded')) {
                    request.status = cellText;
                }
            });
            if (request.title) {
                requests.push(request);
            }
        });
        return requests;
        """)
        
        debug_print(f"Found {len(requests)} fulfilled requests")
        if requests:
            print(f"\nFound {len(requests)} fulfilled requests:")
            print("-" * 80)
            for i, request in enumerate(requests, 1):
                print(f"{i}. Title: {request.get('title', 'N/A')}")
                if request.get('publisher'):
                    print(f"   Publisher: {request['publisher']}")
                if request.get('doi'):
                    print(f"   DOI: {request['doi']}")
                if request.get('time'):
                    print(f"   Time: {request['time']}")
                if request.get('points'):
                    print(f"   Points: {request['points']}")
                if request.get('status'):
                    print(f"   Status: {request['status']}")
                if request.get('detailUrl'):
                    print(f"   Detail URL: {request['detailUrl']}")
                print()
        else:
            print("No fulfilled requests found.")
        return requests
    except Exception as e:
        debug_print(f"Error getting fulfilled requests: {e}")
        print(f"Error retrieving fulfilled requests: {e}")
        return []
    finally:
        debug_print("Closing fulfilled requests driver")
        driver.quit()
        
def download_file_from_fulfilled_request(detail_url, download_folder=None, headless=True):
    """
    Download file from a fulfilled request detail page.
    First navigates to the detail page to extract the actual download URL,
    then downloads the file (can be PDF or other formats).
    Only handles files with extensions like pdf, txt, mp4, pptx, doc, docx, xlsx, and similar.
    Renames the downloaded file to <request_article_title>.<extension>, but strips to first 3-4 words if too long.
    
    Args:
        detail_url: URL of the fulfilled request detail page
        download_folder: Directory to save the downloaded file (default: current directory)
        headless: Whether to run browser in headless mode
    """
    debug_print(f"Starting to download file from: {detail_url}")
    
    allowed_extensions = {
        '.pdf', '.txt', '.doc', '.docx', '.ppt', '.pptx', '.xls', '.xlsx',
        '.mp4', '.avi', '.mov', '.wmv', '.flv', '.mkv', '.webm',
        '.zip', '.rar', '.7z', '.tar', '.gz',
        '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff',
        '.html', '.htm', '.xml', '.json', '.csv',
        '.rtf', '.odt', '.odp', '.ods'
    }
    
    if download_folder is None:
        download_folder = DEFAULT_DOWNLOAD_FOLDER
    os.makedirs(download_folder, exist_ok=True)
    abs_download_path = os.path.abspath(download_folder)
    print(f"Download directory: {abs_download_path}")
    debug_print(f"Download folder set to: {abs_download_path}")
    
    max_retries = 3
    for attempt in range(max_retries):
        debug_print(f"Attempt {attempt + 1} of {max_retries}")
        options = webdriver.ChromeOptions()
        if headless:
            options.add_argument('--headless=new')
            options.add_argument('--disable-gpu')
        prefs = {
            "download.default_directory": abs_download_path,
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "safebrowsing.enabled": True,
            "plugins.always_open_pdf_externally": True
        }
        options.add_experimental_option("prefs", prefs)
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
        options.add_argument("--disable-proxy-server")
        options.add_argument("--no-proxy-server")
        options.add_argument("--disable-background-timer-throttling")
        options.add_argument("--disable-backgrounding-occluded-windows")
        options.add_argument("--disable-renderer-backgrounding")
        options.page_load_strategy = 'normal'
        try:
            driver = webdriver.Chrome(options=options)
            driver.set_page_load_timeout(180)
            driver.implicitly_wait(30)
            debug_print("Chrome driver created with download preferences")
            break
        except Exception as e:
            debug_print(f"Failed to create driver on attempt {attempt + 1}: {e}")
            if attempt == max_retries - 1:
                print(f"Failed to create Chrome driver after {max_retries} attempts: {e}")
                return False
            time.sleep(5)
    try:
        debug_print("Navigating to homepage to load cache")
        driver.get('https://www.ablesci.com')
        if os.path.exists(CACHE_FILE):
            debug_print(f"Loading cache from {CACHE_FILE}")
            with open(CACHE_FILE, 'rb') as f:
                cache = pickle.load(f)
            for cookie in cache:
                driver.add_cookie(cookie)
            debug_print(f"Loaded {len(cache)} cache")
        else:
            debug_print("No cache file found")
        debug_print(f"Navigating to detail page: {detail_url}")
        driver.get(detail_url)
        wait = WebDriverWait(driver, 10)
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'body')))
        time.sleep(3)
        # Extract download link and file size
        debug_print("Looking for download link and file size")
        download_link = driver.find_element(By.CSS_SELECTOR, 'a.able-link.name[href*="/assist/download"]')
        download_href = download_link.get_attribute('href')
        filename = download_link.text.strip()
        file_extension = os.path.splitext(filename)[1].lower()
        if file_extension not in allowed_extensions:
            print(f"Skipping file with unsupported extension: {filename} ({file_extension})")
            print(f"Supported extensions: {', '.join(sorted(allowed_extensions))}")
            return False
        debug_print(f"File has supported extension: {file_extension}")
        file_size_text = "Unknown"
        file_size_mb = 0
        try:
            size_span = driver.find_element(By.CSS_SELECTOR, 'span.size')
            file_size_text = size_span.text.strip()
            debug_print(f"Extracted file size: {file_size_text}")
            size_match = re.search(r'(\d+\.?\d*)\s*(MB|GB|KB|mb|gb|kb)', file_size_text)
            if size_match:
                size_value = float(size_match.group(1))
                size_unit = size_match.group(2).upper()
                if size_unit == 'GB':
                    file_size_mb = size_value * 1024
                elif size_unit == 'MB':
                    file_size_mb = size_value
                elif size_unit == 'KB':
                    file_size_mb = size_value / 1024
                debug_print(f"Parsed file size: {file_size_mb:.2f} MB")
        except Exception as e:
            debug_print(f"Could not extract file size: {e}")
        if file_size_mb > 0:
            max_wait_time = max(60, min(600, int(file_size_mb * 1.5)))
        else:
            max_wait_time = 120
        debug_print(f"Setting max wait time to {max_wait_time} seconds based on file size")
        print(f"File size: {file_size_text}, estimated max wait time: {max_wait_time} seconds")
        if not download_href:
            print("Could not find download link on the detail page")
            return False
        debug_print(f"Raw download href: {download_href}")
        if '?id=' in download_href:
            download_id = download_href.split('?id=')[1]
            if '&' in download_id:
                download_id = download_id.split('&')[0]
        else:
            print("Could not find id parameter in download link")
            return False
        download_url = f"https://www.ablesci.com/assist/download?id={download_id}"
        debug_print(f"Extracted download ID: {download_id}")
        debug_print(f"Constructed download URL: {download_url}")
        debug_print(f"Filename: {filename}")
        # Extract article title for renaming
        try:
            title_elem = driver.find_element(By.CSS_SELECTOR, '.assist-detail .assist-title, .assist-detail .fly-detail-title')
            article_title = title_elem.text.strip()
        except Exception:
            # Fallback: try to extract from page title or use filename without extension
            article_title = os.path.splitext(filename)[0]
        # Clean up title for filesystem
        safe_title = re.sub(r'[\\/*?:"<>|]', '_', article_title)
        safe_title = safe_title.strip()
        # If title is too long, strip to first 3-4 words
        max_title_len = 60
        if len(safe_title) > max_title_len:
            words = safe_title.split()
            safe_title = '_'.join(words[:4]) if len(words) >= 4 else '_'.join(words)
            safe_title = safe_title[:max_title_len]
        # Get list of existing files before download
        existing_files = set(os.listdir(abs_download_path))
        debug_print(f"Found {len(existing_files)} existing files")
        debug_print(f"Navigating to download URL: {download_url}")
        driver.get(download_url)
        debug_print(f"Waiting for download to complete (max {max_wait_time}s)")
        check_interval = 2
        waited_time = 0
        downloaded_file = None
        while waited_time < max_wait_time:
            time.sleep(check_interval)
            waited_time += check_interval
            current_files = set(os.listdir(abs_download_path))
            new_files = current_files - existing_files
            if new_files:
                complete_files = []
                for f in new_files:
                    if not f.endswith('.crdownload'):
                        file_ext = os.path.splitext(f)[1].lower()
                        if file_ext in allowed_extensions:
                            complete_files.append(f)
                if complete_files:
                    downloaded_file = complete_files[0]
                    break
            if waited_time % 10 == 0:
                debug_print(f"Waiting for download... ({waited_time}s/{max_wait_time}s)")
        if downloaded_file:
            downloaded_path = os.path.join(abs_download_path, downloaded_file)
            actual_size = os.path.getsize(downloaded_path)
            file_extension = os.path.splitext(downloaded_file)[1].lower()
            # Rename file to <request_article_title>.<extension>
            new_filename = f"{safe_title}{file_extension}"
            new_path = os.path.join(abs_download_path, new_filename)
            try:
                if downloaded_path != new_path:
                    os.rename(downloaded_path, new_path)
                    print(f"File renamed to: {new_path}")
                else:
                    print(f"File already named: {new_path}")
            except Exception as e:
                print(f"Failed to rename file: {e}")
                new_path = downloaded_path
            print(f"File downloaded successfully: {new_path}")
            print(f"File type: {file_extension if file_extension else 'Unknown'}")
            print(f"Actual file size: {actual_size} bytes ({actual_size/1024/1024:.2f} MB)")
            return True
        else:
            print(f"Download timeout or failed after {max_wait_time} seconds")
            print(f"Download URL: {download_url}")
            return False
    except Exception as e:
        debug_print(f"Error downloading file: {e}")
        print(f"Failed to download file from: {detail_url} ({e})")
        return False
    finally:
        debug_print("Closing download driver")
        driver.quit()

def interactive_download_fulfilled_requests(headless=True, download_folder=None):
    """
    List fulfilled requests, prompt user to select one or more (comma-separated or range, e.g., 1,3,5-7) to download files, and download them.
    Supports single numbers, comma-separated list, and ranges (e.g., 1,3,5-7).
    If no response from user for 30 seconds, quit.
    
    Args:
        headless: Whether to run browser in headless mode
        download_folder: Directory to save the downloaded files (default: DEFAULT_DOWNLOAD_FOLDER)
    """
    requests = get_fulfilled_requests(headless=headless)
    if not requests:
        print("No fulfilled requests to download.")
        return

    print("Enter the numbers of the requests you want to download files from (comma-separated or range, e.g., 1,3,5-7), or press Enter to skip:")

    # Input with 30s timeout (cross-platform)
    def input_with_timeout(prompt, timeout=30):
        q = queue.Queue()

        def inner():
            try:
                q.put(input(prompt))
            except Exception:
                q.put(None)

        t = threading.Thread(target=inner)
        t.daemon = True
        t.start()
        t.join(timeout)
        if t.is_alive():
            return None
        return q.get() if not q.empty() else None

    selection = input_with_timeout("Selection: ", 30)
    if selection is None:
        print("\nNo input received in 30 seconds. Download operation aborted.")
        return

    selection = selection.strip()
    if not selection:
        print("No requests selected for download.")
        return

    # Parse user input (comma-separated numbers and ranges)
    indices = set()
    for part in selection.split(','):
        part = part.strip()
        if '-' in part:
            try:
                start, end = map(int, part.split('-', 1))
                if start > end:
                    print(f"Invalid range: {part} (start > end)")
                    continue
                for idx in range(start, end + 1):
                    if 1 <= idx <= len(requests):
                        indices.add(idx - 1)
                    else:
                        print(f"Invalid selection: {idx} (out of range)")
            except Exception:
                print(f"Invalid range input: {part}")
        elif part.isdigit():
            idx = int(part)
            if 1 <= idx <= len(requests):
                indices.add(idx - 1)
            else:
                print(f"Invalid selection: {part} (out of range)")
        elif part:
            print(f"Invalid input: {part}")

    if not indices:
        print("No valid requests selected for download.")
        return

    # Show download folder info
    folder_path = download_folder if download_folder else DEFAULT_DOWNLOAD_FOLDER
    print(f"\nDownload folder: {folder_path}")
    print(f"Starting download for {len(indices)} requests...")
    
    for idx in sorted(indices):
        req = requests[idx]
        print(f"Downloading file for request {idx+1}: {req.get('title', 'N/A')}")
        success = download_file_from_fulfilled_request(req.get('detailUrl'), download_folder=folder_path, headless=headless)
        if not success:
            print(f"Failed to download file for request {idx+1}.")
        time.sleep(2)  # Small delay between downloads

def accept_fulfilled_request(detail_url, headless=True):
    """
    Accept a fulfilled request by navigating to its detail page and clicking the accept button.
    This will confirm receipt of the file and award points to the uploader.
    Based on the JavaScript code that handles .btn-handle-file clicks with data-type='accept'.
    
    Args:
        detail_url: URL of the fulfilled request detail page
        headless: Whether to run browser in headless mode
    
    Returns:
        bool: True if successfully accepted, False otherwise
    """
    debug_print(f"Starting to accept fulfilled request: {detail_url}")
    driver = login_and_navigate(detail_url, headless)
    
    if driver is None:
        print(f"Failed to open detail page: {detail_url}")
        return False
        
    try:
        wait = WebDriverWait(driver, 10)
        
        # Wait for the page to load
        debug_print("Waiting for page content to load")
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'body')))
        time.sleep(3)  # Wait for dynamic content
        
        # Check for and handle any popup dialog that appears on page load
        debug_print("Checking for popup dialog on page load")
        try:
            popup_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, 'a.layui-layer-btn0')))
            debug_print("Found popup dialog with '确定' button, clicking it")
            popup_btn.click()
            time.sleep(2)  # Wait for dialog to close
        except:
            debug_print("No popup dialog found on page load")
        
        # Look for the accept button with data-type='accept'
        debug_print("Looking for accept button with data-type='accept'")
        accept_btn = None
        
        try:
            accept_btn = driver.find_element(By.CSS_SELECTOR, '.btn-handle-file[data-type="accept"]')
            debug_print("Found accept button with data-type='accept'")
        except:
            debug_print("Could not find .btn-handle-file[data-type='accept'], trying alternative selectors")
            # Try alternative selectors
            alternative_selectors = [
                'button[data-type="accept"]',
                '.layui-btn[data-type="accept"]',
                'a[data-type="accept"]'
            ]
            
            for selector in alternative_selectors:
                try:
                    accept_btn = driver.find_element(By.CSS_SELECTOR, selector)
                    debug_print(f"Found accept button with selector: {selector}")
                    break
                except:
                    continue
        
        if not accept_btn:
            print(f"Could not find accept button on page: {detail_url}")
            return False
        
        # Extract assist_file_id from the button's parent li element
        debug_print("Extracting assist_file_id")
        assist_file_id = None
        try:
            parent_li = accept_btn.find_element(By.XPATH, "./ancestor::li[1]")
            assist_file_id_input = parent_li.find_element(By.CSS_SELECTOR, '.assist-file-id')
            assist_file_id = assist_file_id_input.get_attribute('value')
            debug_print(f"Found assist_file_id: {assist_file_id}")
        except Exception as e:
            debug_print(f"Could not extract assist_file_id: {e}")
            print(f"Could not extract assist_file_id from page: {detail_url}")
            return False
        
        debug_print("Clicking accept button to open dialog")
        # Scroll to button to ensure it's visible and not intercepted
        driver.execute_script("""
            arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});
            window.scrollBy(0, -100);
        """, accept_btn)
        time.sleep(2)
        
        # Use JavaScript click to avoid interception issues
        debug_print("Using JavaScript click to avoid element interception")
        driver.execute_script("arguments[0].click();", accept_btn)
        
        # Wait for the layer dialog to appear
        debug_print("Waiting for accept dialog to appear")
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, '#handle-note')))
        
        # Fill in optional thank you message
        debug_print("Filling optional thank you message")
        note_textarea = driver.find_element(By.ID, 'handle-note')
        note_textarea.clear()
        note_textarea.send_keys("谢谢")  # Thank you in Chinese
        
        # Find and click the confirm button (确定)
        debug_print("Looking for confirm button")
        confirm_btn = wait.until(
            EC.element_to_be_clickable(
                (By.CSS_SELECTOR, '.layui-layer-btn0, .layui-layer-btn a:first-child')
            )
        )
        debug_print("Clicking confirm button")
        confirm_btn.click()
        
        # Wait for the AJAX request to complete and handle the response
        debug_print("Waiting for accept operation to complete")
        time.sleep(5)  # Give time for the AJAX request
        
        # Check for success message or dialog
        try:
            # Look for success dialog or message
            success_dialog = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, '.layui-layer-content')))
            dialog_text = success_dialog.text
            debug_print(f"Found dialog with text: {dialog_text}")
            
            # Check if it's a success message
            success_indicators = [
                "成功",
                "确认成功",
                "接受成功",
                "操作成功"
            ]
            
            is_success = any(indicator in dialog_text for indicator in success_indicators)
            
            if is_success:
                debug_print("Success dialog detected, clicking OK")
                # Click OK on the success dialog
                try:
                    ok_btn = driver.find_element(By.CSS_SELECTOR, '.layui-layer-btn0, .layui-layer-btn a:first-child')
                    ok_btn.click()
                    time.sleep(2)
                except:
                    debug_print("Could not click OK button, dialog might auto-close")
                
                print(f"Successfully accepted fulfilled request: {detail_url}")
                return True
            else:
                print(f"Accept operation completed but status unclear: {detail_url}")
                print(f"Dialog message: {dialog_text}")
                return True  # Assume success if no error message
                
        except:
            debug_print("No success dialog found, checking page for success indicators")
            # Check page content for success indicators
            page_content = driver.page_source
            success_indicators = [
                "成功确认",
                "已确认收到", 
                "确认成功",
                "接受成功",
                "操作成功"
            ]
            
            if any(indicator in page_content for indicator in success_indicators):
                print(f"Successfully accepted fulfilled request: {detail_url}")
                return True
            else:
                print(f"Accept operation completed (status unclear): {detail_url}")
                return True  # Assume success if we got this far without errors
            
    except Exception as e:
        debug_print(f"Error accepting fulfilled request: {e}")
        print(f"Failed to accept fulfilled request: {detail_url} ({e})")
        return False
    finally:
        debug_print("Closing accept request driver")
        driver.quit()

def interactive_accept_fulfilled_requests(headless=True):
    """
    List fulfilled requests, prompt user to select one or more (comma-separated or range, e.g., 1,3,5-7) to accept, and accept them.
    Supports single numbers, comma-separated list, and ranges (e.g., 1,3,5-7).
    If no response from user for 30 seconds, quit.
    """
    requests = get_fulfilled_requests(headless=headless)
    if not requests:
        print("No fulfilled requests to accept.")
        return

    print("Enter the numbers of the requests you want to accept (comma-separated or range, e.g., 1,3,5-7), or press Enter to skip:")

    # Input with 30s timeout (cross-platform)
    def input_with_timeout(prompt, timeout=30):
        q = queue.Queue()

        def inner():
            try:
                q.put(input(prompt))
            except Exception:
                q.put(None)

        t = threading.Thread(target=inner)
        t.daemon = True
        t.start()
        t.join(timeout)
        if t.is_alive():
            return None
        return q.get() if not q.empty() else None

    selection = input_with_timeout("Selection: ", 30)
    if selection is None:
        print("\nNo input received in 30 seconds. Accept operation aborted.")
        return

    selection = selection.strip()
    if not selection:
        print("No requests selected for acceptance.")
        return

    # Parse user input (comma-separated numbers and ranges)
    indices = set()
    for part in selection.split(','):
        part = part.strip()
        if '-' in part:
            try:
                start, end = map(int, part.split('-', 1))
                if start > end:
                    print(f"Invalid range: {part} (start > end)")
                    continue
                for idx in range(start, end + 1):
                    if 1 <= idx <= len(requests):
                        indices.add(idx - 1)
                    else:
                        print(f"Invalid selection: {idx} (out of range)")
            except Exception:
                print(f"Invalid range input: {part}")
        elif part.isdigit():
            idx = int(part)
            if 1 <= idx <= len(requests):
                indices.add(idx - 1)
            else:
                print(f"Invalid selection: {part} (out of range)")
        elif part:
            print(f"Invalid input: {part}")

    if not indices:
        print("No valid requests selected for acceptance.")
        return

    for idx in sorted(indices):
        req = requests[idx]
        print(f"Accepting request {idx+1}: {req.get('title', 'N/A')}")
        success = accept_fulfilled_request(req.get('detailUrl'), headless=headless)
        if not success:
            print(f"Failed to accept request {idx+1}.")
        time.sleep(2)  # Small delay between accepts

def reject_fulfilled_request(detail_url, reason="版本错误", headless=True):
    """
    Reject a fulfilled request by navigating to its detail page and clicking the reject button.
    This will reject the uploaded file and provide a reason for rejection.
    Based on the JavaScript code that handles .btn-handle-file clicks with data-type='reject'.
    
    Args:
        detail_url: URL of the fulfilled request detail page
        reason: Reason for rejection (default: "版本错误")
        headless: Whether to run browser in headless mode
    
    Returns:
        bool: True if successfully rejected, False otherwise
    """
    debug_print(f"Starting to reject fulfilled request: {detail_url}")
    driver = login_and_navigate(detail_url, headless)
    
    if driver is None:
        print(f"Failed to open detail page: {detail_url}")
        return False
        
    try:
        wait = WebDriverWait(driver, 10)
        
        # Wait for the page to load
        debug_print("Waiting for page content to load")
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'body')))
        time.sleep(3)  # Wait for dynamic content
        
        # Check for and handle any popup dialog that appears on page load
        debug_print("Checking for popup dialog on page load")
        try:
            popup_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, 'a.layui-layer-btn0')))
            debug_print("Found popup dialog with '确定' button, clicking it")
            popup_btn.click()
            time.sleep(2)  # Wait for dialog to close
        except:
            debug_print("No popup dialog found on page load")
        
        # Look for the reject button with data-type='reject'
        debug_print("Looking for reject button with data-type='reject'")
        reject_btn = None
        
        try:
            reject_btn = driver.find_element(By.CSS_SELECTOR, '.btn-handle-file[data-type="reject"]')
            debug_print("Found reject button with data-type='reject'")
        except:
            debug_print("Could not find .btn-handle-file[data-type='reject'], trying alternative selectors")
            # Try alternative selectors
            alternative_selectors = [
                'button[data-type="reject"]',
                '.layui-btn[data-type="reject"]',
                'a[data-type="reject"]'
            ]
            
            for selector in alternative_selectors:
                try:
                    reject_btn = driver.find_element(By.CSS_SELECTOR, selector)
                    debug_print(f"Found reject button with selector: {selector}")
                    break
                except:
                    continue
        
        if not reject_btn:
            print(f"Could not find reject button on page: {detail_url}")
            return False
        
        # Extract assist_file_id from the button's parent li element
        debug_print("Extracting assist_file_id")
        assist_file_id = None
        try:
            parent_li = reject_btn.find_element(By.XPATH, "./ancestor::li[1]")
            assist_file_id_input = parent_li.find_element(By.CSS_SELECTOR, '.assist-file-id')
            assist_file_id = assist_file_id_input.get_attribute('value')
            debug_print(f"Found assist_file_id: {assist_file_id}")
        except Exception as e:
            debug_print(f"Could not extract assist_file_id: {e}")
            print(f"Could not extract assist_file_id from page: {detail_url}")
            return False
        
        debug_print("Clicking reject button to open dialog")
        # Scroll to button to ensure it's visible and not intercepted
        driver.execute_script("""
            arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});
            window.scrollBy(0, -100);
        """, reject_btn)
        time.sleep(2)
        
        # Use JavaScript click to avoid interception issues
        debug_print("Using JavaScript click to avoid element interception")
        driver.execute_script("arguments[0].click();", reject_btn)
        
        # Wait for the layer dialog to appear
        debug_print("Waiting for reject dialog to appear")
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, '#handle-note')))
        
        # Fill in the rejection reason
        debug_print(f"Filling rejection reason: {reason}")
        note_textarea = driver.find_element(By.ID, 'handle-note')
        note_textarea.clear()
        note_textarea.send_keys(reason)
        
        # Find and click the confirm button (确定)
        debug_print("Looking for confirm button")
        confirm_btn = wait.until(
            EC.element_to_be_clickable(
                (By.CSS_SELECTOR, '.layui-layer-btn0, .layui-layer-btn a:first-child')
            )
        )
        debug_print("Clicking confirm button")
        confirm_btn.click()
        
        # Wait for the AJAX request to complete and handle the response
        debug_print("Waiting for reject operation to complete")
        time.sleep(5)  # Give time for the AJAX request
        
        # Check for success message or dialog
        try:
            # Look for success dialog or message
            success_dialog = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, '.layui-layer-content')))
            dialog_text = success_dialog.text
            debug_print(f"Found dialog with text: {dialog_text}")
            
            # Check if it's a success message
            success_indicators = [
                "成功",
                "驳回成功",
                "操作成功",
                "已驳回"
            ]
            
            is_success = any(indicator in dialog_text for indicator in success_indicators)
            
            if is_success:
                debug_print("Success dialog detected, clicking OK")
                # Click OK on the success dialog
                try:
                    ok_btn = driver.find_element(By.CSS_SELECTOR, '.layui-layer-btn0, .layui-layer-btn a:first-child')
                    ok_btn.click()
                    time.sleep(2)
                except:
                    debug_print("Could not click OK button, dialog might auto-close")
                
                print(f"Successfully rejected fulfilled request: {detail_url}")
                print(f"Rejection reason: {reason}")
                return True
            else:
                print(f"Reject operation completed but status unclear: {detail_url}")
                print(f"Dialog message: {dialog_text}")
                return True  # Assume success if no error message
                
        except:
            debug_print("No success dialog found, checking page for success indicators")
            # Check page content for success indicators
            page_content = driver.page_source
            success_indicators = [
                "驳回成功",
                "已驳回", 
                "操作成功"
            ]
            
            if any(indicator in page_content for indicator in success_indicators):
                print(f"Successfully rejected fulfilled request: {detail_url}")
                print(f"Rejection reason: {reason}")
                return True
            else:
                print(f"Reject operation completed (status unclear): {detail_url}")
                return True  # Assume success if we got this far without errors
            
    except Exception as e:
        debug_print(f"Error rejecting fulfilled request: {e}")
        print(f"Failed to reject fulfilled request: {detail_url} ({e})")
        return False
    finally:
        debug_print("Closing reject request driver")
        driver.quit()

def interactive_reject_fulfilled_requests(headless=True):
    """
    List fulfilled requests, prompt user to select one or more (comma-separated or range, e.g., 1,3,5-7) to reject, and reject them.
    Supports single numbers, comma-separated list, and ranges (e.g., 1,3,5-7).
    If no response from user for 30 seconds, quit.
    """
    requests = get_fulfilled_requests(headless=headless)
    if not requests:
        print("No fulfilled requests to reject.")
        return

    print("Enter the numbers of the requests you want to reject (comma-separated or range, e.g., 1,3,5-7), or press Enter to skip:")

    # Input with 30s timeout (cross-platform)
    def input_with_timeout(prompt, timeout=30):
        q = queue.Queue()

        def inner():
            try:
                q.put(input(prompt))
            except Exception:
                q.put(None)

        t = threading.Thread(target=inner)
        t.daemon = True
        t.start()
        t.join(timeout)
        if t.is_alive():
            return None
        return q.get() if not q.empty() else None

    selection = input_with_timeout("Selection: ", 30)
    if selection is None:
        print("\nNo input received in 30 seconds. Reject operation aborted.")
        return

    selection = selection.strip()
    if not selection:
        print("No requests selected for rejection.")
        return

    # Parse user input (comma-separated numbers and ranges)
    indices = set()
    for part in selection.split(','):
        part = part.strip()
        if '-' in part:
            try:
                start, end = map(int, part.split('-', 1))
                if start > end:
                    print(f"Invalid range: {part} (start > end)")
                    continue
                for idx in range(start, end + 1):
                    if 1 <= idx <= len(requests):
                        indices.add(idx - 1)
                    else:
                        print(f"Invalid selection: {idx} (out of range)")
            except Exception:
                print(f"Invalid range input: {part}")
        elif part.isdigit():
            idx = int(part)
            if 1 <= idx <= len(requests):
                indices.add(idx - 1)
            else:
                print(f"Invalid selection: {part} (out of range)")
        elif part:
            print(f"Invalid input: {part}")

    if not indices:
        print("No valid requests selected for rejection.")
        return

    # Ask for rejection reason
    print("\nCommon rejection reasons:")
    reasons_list = [
        "1. 文件不完整 (File incomplete)",
        "2. 缺页 (Missing pages)",
        "3. 标题错误 (Wrong title)",
        "4. DOI错误 (Wrong DOI)",
        "5. 不是PDF版 (Not PDF version)",
        "6. 版本错误 (Wrong version)"
    ]
    for r in reasons_list:
        print(r)

    reason_input = input_with_timeout("Enter rejection reason (number or custom, press Enter for default '版本错误'): ", 30)
    if reason_input is None:
        print("\nNo input received. Using default reason.")
        reason = "版本错误"
    else:
        reason_input = reason_input.strip()
        if reason_input.isdigit():
            idx = int(reason_input)
            if 1 <= idx <= len(reasons_list):
                # Extract the Chinese part from the selected reason
                # Remove leading number, dot, and any English in parentheses
                chinese_part = re.sub(r'^\d+\.\s*', '', reasons_list[idx-1])
                chinese_part = re.sub(r'\s*\(.*?\)', '', chinese_part)
                reason = chinese_part.strip()
            else:
                reason = reason_input or "版本错误"
        else:
            reason = reason_input or "版本错误"
    
    print(f"\nUsing rejection reason: {reason}")

    for idx in sorted(indices):
        req = requests[idx]
        print(f"Rejecting request {idx+1}: {req.get('title', 'N/A')}")
        success = reject_fulfilled_request(req.get('detailUrl'), reason=reason, headless=headless)
        if not success:
            print(f"Failed to reject request {idx+1}.")
        time.sleep(2)  # Small delay between rejects

def get_active_requests(limit=20, order_by_points=False, headless=True):
    """
    Get a list of active requests from all users (waiting to be fulfilled).
    Only includes entries with status '求助中', ignores the rest.
    Scrolls through pages until the limit is reached or no more requests are found.
    
    Args:
        limit: Maximum number of requests to retrieve
        order_by_points: If True, order by reward points (highest first)
        headless: Whether to run browser in headless mode
    """
    debug_print(f"Starting to get active requests (limit: {limit}, order_by_points: {order_by_points})")
    
    # Choose URL based on ordering preference
    if order_by_points:
        base_url = 'https://www.ablesci.com/assist/index?status=waiting&order=point'
    else:
        base_url = 'https://www.ablesci.com/assist/index?status=waiting'
    
    driver = login_and_navigate(base_url, headless)
    
    if driver is None:
        print("Failed to login and navigate to active requests page")
        return []
        
    try:
        wait = WebDriverWait(driver, 10)
        all_requests = []
        page = 1
        
        while len(all_requests) < limit:
            debug_print(f"Processing page {page}, current requests: {len(all_requests)}")
            
            # Wait for the page to load
            debug_print("Waiting for page content to load")
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'body')))
            time.sleep(3)  # Wait for dynamic content
            
            # Scroll to bottom to load more content if needed
            debug_print("Scrolling to bottom of page")
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)
            
            # Extract requests from current page
            debug_print("Extracting requests from current page")
            page_requests = driver.execute_script("""
            var requests = [];
            var requestItems = document.querySelectorAll('.assist-list-item-handle');
            
            requestItems.forEach(function(handleDiv) {
                var request = {};
                
                // Get the detail container (sibling div)
                var detailDiv = handleDiv.nextElementSibling;
                if (!detailDiv || !detailDiv.classList.contains('assist-list-item-detail')) {
                    return;
                }
                
                // Get status info first to filter
                var statusSpan = detailDiv.querySelector('.assist-badge');
                if (!statusSpan || statusSpan.innerText.trim() !== '求助中') {
                    return; // Skip if status is not '求助中'
                }
                request.status = statusSpan.innerText.trim();
                
                // Get title and main detail URL from detail div
                var titleLink = detailDiv.querySelector('.assist-list-title a[href*="/assist/detail"]');
                if (titleLink) {
                    // Clone the element to avoid modifying the original
                    var titleClone = titleLink.cloneNode(true);
                    
                    // Remove all span elements with the specific styling
                    var spans = titleClone.querySelectorAll('span[style*="background-color: #ededed"]');
                    spans.forEach(function(span) {
                        span.remove();
                    });
                    
                    request.title = titleClone.innerText.trim();
                    request.detailUrl = titleLink.href;
                    
                    // Clean up title by removing extra whitespace
                    request.title = request.title.replace(/\\s+/g, ' ').trim();
                }
                
                // Get publisher info
                var publisherImg = detailDiv.querySelector('.paper-publisher img.publisher-icon');
                if (publisherImg) {
                    request.publisher = publisherImg.title || publisherImg.alt || '';
                }
                
                // Get user info from assist-list-info
                var userLink = detailDiv.querySelector('.assist-list-info-user-name a.assist-list-nickname');
                if (userLink) {
                    request.requestUser = userLink.innerText.trim();
                    request.userUrl = userLink.href;
                    request.userId = userLink.getAttribute('data-id');
                }
                
                // Get location info
                var locationSpan = detailDiv.querySelector('.assist-list-info span[title="来源地"]');
                if (locationSpan) {
                    request.location = locationSpan.innerText.replace('来自', '').trim();
                }
                
                // Get points info
                var pointsSpan = detailDiv.querySelector('.fly-list-kiss[title="奖励积分"]');
                if (pointsSpan) {
                    var pointsText = pointsSpan.innerText.trim();
                    var pointsMatch = pointsText.match(/\\d+/);
                    if (pointsMatch) {
                        request.points = pointsMatch[0];
                    }
                }
                
                // Try to extract DOI from title or other elements
                var fullText = detailDiv.innerText;
                var doiMatch = fullText.match(/10\\.\\d{4,9}\\/[-._;()\\/:A-Z0-9]+/i);
                if (doiMatch) {
                    request.doi = doiMatch[0];
                }
                
                // Only add if we found at least a title
                if (request.title) {
                    requests.push(request);
                }
            });
            
            return requests;
            """)
            
            debug_print(f"Found {len(page_requests)} requests with status '求助中' on page {page}")
            
            # Filter out duplicates based on detail URL
            existing_urls = {req.get('detailUrl') for req in all_requests}
            new_requests = [req for req in page_requests if req.get('detailUrl') not in existing_urls]
            
            debug_print(f"Adding {len(new_requests)} new requests (filtered duplicates)")
            all_requests.extend(new_requests)
            
            # If we reached the limit, stop
            if len(all_requests) >= limit:
                break
            
            # If we didn't get any new requests, try next page anyway (might be filtered out)
            # Navigate to next page
            page += 1
            if order_by_points:
                next_url = f'https://www.ablesci.com/assist/index?status=waiting&order=point&page={page}'
            else:
                next_url = f'https://www.ablesci.com/assist/index?status=waiting&page={page}'
            
            debug_print(f"Navigating to next page: {next_url}")
            driver.get(next_url)
            
            # Check if we actually got a new page (avoid infinite loop)
            try:
                wait.until(lambda d: d.current_url != next_url or EC.presence_of_element_located((By.CSS_SELECTOR, 'body')))
            except:
                debug_print("Timeout waiting for next page, stopping")
                break
            
            # Check if we've reached the end of pages (no more content)
            page_has_content = driver.execute_script("""
            var requestItems = document.querySelectorAll('.assist-list-item-handle');
            return requestItems.length > 0;
            """)
            
            if not page_has_content:
                debug_print("No more content found, stopping pagination")
                break
        
        # Trim to limit
        all_requests = all_requests[:limit]
        
        order_desc = " (ordered by reward points)" if order_by_points else ""
        debug_print(f"Retrieved {len(all_requests)} active requests with status '求助中'{order_desc}")
        
        if all_requests:
            print(f"\nFound {len(all_requests)} active requests with status '求助中'{order_desc}:")
            print("-" * 80)
            for i, request in enumerate(all_requests, 1):
                print(f"{i}. Title: {request.get('title', 'N/A')}")
                if request.get('requestUser'):
                    print(f"   Requested by: {request['requestUser']}")
                if request.get('location'):
                    print(f"   Location: {request['location']}")
                if request.get('publisher'):
                    print(f"   Publisher: {request['publisher']}")
                if request.get('doi'):
                    print(f"   DOI: {request['doi']}")
                if request.get('points'):
                    print(f"   Points: {request['points']}")
                if request.get('detailUrl'):
                    print(f"   Detail URL: {request['detailUrl']}")
                print()
        else:
            print(f"No active requests with status '求助中' found{order_desc}.")
            
        return all_requests
        
    except Exception as e:
        debug_print(f"Error getting active requests: {e}")
        print(f"Error retrieving active requests: {e}")
        return []
    finally:
        debug_print("Closing active requests driver")
        driver.quit()

def get_file_path_with_completion(prompt="Enter file path: "):
    """
    Get file path from user with tab completion support
    
    Args:
        prompt: The prompt to display to the user
    
    Returns:
        str: The selected file path as absolute path, or None if cancelled
    """
    
    def complete_path(text, state):
        """Tab completion function for file paths"""
        # Expand user home directory
        if text.startswith('~'):
            text = os.path.expanduser(text)
        
        # If text ends with a slash, it's a directory - list contents
        if text.endswith('/'):
            directory = text
        else:
            # Get the directory part and filename part
            directory = os.path.dirname(text)
            if not directory:
                directory = '.'
            
        # Get all possible completions
        if text.endswith('/'):
            # List directory contents
            pattern = text + '*'
        else:
            # Complete filename
            pattern = text + '*'
        
        matches = glob.glob(pattern)
        
        # Add trailing slash for directories
        completions = []
        for match in matches:
            if os.path.isdir(match) and not match.endswith('/'):
                completions.append(match + '/')
            else:
                completions.append(match)
        
        # Sort completions
        completions.sort()
        
        try:
            return completions[state]
        except IndexError:
            return None
    def timeout_handler(signum, frame):
        print("\nTimeout: No input received within 30 seconds. Quitting.")
        exit(1)
    
    # Set up readline with tab completion
    readline.parse_and_bind("tab: complete")
    readline.set_completer(complete_path)
    readline.set_completer_delims(' \t\n`!@#$%^&*()=+[{]}\\|;:\'",<>?')
    
    try:
        while True:
            try:
                # Set up timeout signal (only on Unix-like systems)
                if hasattr(signal, 'SIGALRM'):
                    signal.signal(signal.SIGALRM, timeout_handler)
                    signal.alarm(30)  # 30 second timeout
                
                # Get input with tab completion
                file_path = input(prompt).strip()
                
                # Cancel the alarm (only on Unix-like systems)
                if hasattr(signal, 'alarm'):
                    signal.alarm(0)
                
                if not file_path:
                    print("Please enter a valid file path or press Ctrl+C to cancel.")
                    continue
                
                # Expand user home directory
                file_path = os.path.expanduser(file_path)
                
                # Remove quotes if present
                if (file_path.startswith('"') and file_path.endswith('"')) or \
                    (file_path.startswith("'") and file_path.endswith("'")):
                    file_path = file_path[1:-1]
                
                # Check if file exists
                if os.path.exists(file_path):
                    if os.path.isfile(file_path):
                        return os.path.abspath(file_path)
                    else:
                        print(f"Path exists but is not a file: {file_path}")
                        continue
                else:
                    print(f"File not found: {file_path}")
                    retry = input("Try again? (y/n): ").strip().lower()
                    if retry not in ['y', 'yes']:
                        return None
                    continue
                    
            except EOFError:
                if hasattr(signal, 'alarm'):
                    signal.alarm(0)  # Cancel alarm
                print("\nOperation cancelled.")
                return None
                
    except KeyboardInterrupt:
        if hasattr(signal, 'alarm'):
            signal.alarm(0)  # Cancel alarm
        print("\nOperation cancelled by user.")
        return None
    finally:
        # Clean up
        if hasattr(signal, 'alarm'):
            signal.alarm(0)  # Make sure alarm is cancelled
        readline.set_completer(None)

def upload_file_to_active_request(detail_url, headless=True):
    """
    Upload a file to an active request by navigating to its detail page and uploading the file.
    Supports various file types including PDF, DOC, DOCX, PPT, PPTX, XLS, XLSX, ZIP, RAR, 7Z, TXT.
    Maximum file size is 50MB.
    
    Args:
        detail_url: URL of the active request detail page
        headless: Whether to run browser in headless mode
    
    Returns:
        bool: True if successfully uploaded, False otherwise
    """
    debug_print(f"Starting to upload file to active request: {detail_url}")
    
    # Ask user for file path with tab completion
    file_path = get_file_path_with_completion("Enter path to file to upload: ")
    if file_path is None:
        print("Upload cancelled by user.")
        return False
    
    debug_print(f"File path: {file_path}")
    
    # Validate file exists
    if not os.path.exists(file_path):
        print(f"File not found: {file_path}")
        return False
    
    # Validate file size (50MB limit)
    file_size = os.path.getsize(file_path)
    max_size_mb = 50
    if file_size > max_size_mb * 1024 * 1024:
        print(f"File size ({file_size / 1024 / 1024:.2f} MB) exceeds maximum allowed size ({max_size_mb} MB)")
        return False
    
    # Validate file extension
    allowed_extensions = {'.pdf', '.doc', '.docx', '.ppt', '.pptx', '.xls', '.xlsx', '.zip', '.rar', '.7z', '.txt'}
    file_extension = os.path.splitext(file_path)[1].lower()
    if file_extension not in allowed_extensions:
        print(f"File extension {file_extension} is not allowed. Allowed extensions: {', '.join(sorted(allowed_extensions))}")
        return False
    
    debug_print(f"File validation passed - size: {file_size / 1024 / 1024:.2f} MB, extension: {file_extension}")
    
    driver = login_and_navigate(detail_url, headless)
    
    if driver is None:
        print(f"Failed to open detail page: {detail_url}")
        return False
        
    try:
        wait = WebDriverWait(driver, 10)
        
        # Wait for the page to load
        debug_print("Waiting for page content to load")
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'body')))
        time.sleep(3)
        
        # Extract assist_id from the page
        debug_print("Extracting assist_id")
        try:
            assist_id_element = driver.find_element(By.CSS_SELECTOR, '.uploading-assist-id-val')
            assist_id = assist_id_element.get_attribute('value')
            debug_print(f"Found assist_id: {assist_id}")
        except Exception as e:
            debug_print(f"Could not extract assist_id: {e}")
            print(f"Could not extract assist_id from page: {detail_url}")
            return False
        
        # Find the file input element (usually hidden)
        debug_print("Looking for file input element")
        file_input = None
        try:
            # Try to find the file input by various selectors
            file_input_selectors = [
                'input[type="file"]',
                '#browse-btn input[type="file"]',
                '.file-input'
            ]
            
            for selector in file_input_selectors:
                try:
                    file_input = driver.find_element(By.CSS_SELECTOR, selector)
                    debug_print(f"Found file input with selector: {selector}")
                    break
                except:
                    continue
            
            # If still not found, look for the browse button and get its associated input
            if not file_input:
                browse_btn = driver.find_element(By.ID, 'browse-btn')
                # Make the hidden input visible
                driver.execute_script("""
                var inputs = document.querySelectorAll('input[type="file"]');
                for (var i = 0; i < inputs.length; i++) {
                    inputs[i].style.display = 'block';
                    inputs[i].style.visibility = 'visible';
                    inputs[i].style.opacity = '1';
                    inputs[i].style.position = 'static';
                }
                """)
                file_input = driver.find_element(By.CSS_SELECTOR, 'input[type="file"]')
                debug_print("Made file input visible")
                
        except Exception as e:
            debug_print(f"Could not find file input: {e}")
            print(f"Could not find file input on page: {detail_url}")
            return False
        
        # Upload the file
        debug_print(f"Uploading file: {file_path}")
        file_input.send_keys(file_path)
        
        # Wait for file to be processed
        debug_print("Waiting for file to be processed")
        time.sleep(3)
        
        # Wait for upload button to appear
        debug_print("Waiting for upload button")
        upload_btn = wait.until(EC.element_to_be_clickable((By.ID, 'upload-bth')))
        
        # Check if file was accepted (upload button should be visible)
        if not upload_btn.is_displayed():
            debug_print("Upload button not visible, file may have been rejected")
            # Check for error messages
            try:
                error_msg = driver.find_element(By.CSS_SELECTOR, '#file-msgbox .text-danger')
                error_text = error_msg.text
                print(f"File upload error: {error_text}")
                return False
            except:
                print("File was not accepted for upload (unknown reason)")
                return False
        
        debug_print("File accepted, clicking upload button")
        upload_btn.click()
        
        # Monitor upload progress
        debug_print("Monitoring upload progress")
        max_wait_time = 300  # 5 minutes max wait
        check_interval = 2
        waited_time = 0
        
        while waited_time < max_wait_time:
            time.sleep(check_interval)
            waited_time += check_interval
            
            # Check for completion indicators
            try:
                # Check for success message
                success_msg = driver.find_element(By.CSS_SELECTOR, '#file-msgbox .text-success')
                if success_msg.is_displayed():
                    success_text = success_msg.text
                    debug_print(f"Upload success message: {success_text}")
                    print(f"File uploaded successfully: {success_text}")
                    
                    # Wait for any success dialog and handle it
                    try:
                        success_dialog = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, '.layui-layer-content')))
                        dialog_text = success_dialog.text
                        debug_print(f"Success dialog text: {dialog_text}")
                        
                        # Click OK button if present
                        try:
                            ok_btn = driver.find_element(By.CSS_SELECTOR, '.layui-layer-btn0, .layui-layer-btn a:first-child')
                            ok_btn.click()
                            debug_print("Clicked OK on success dialog")
                        except:
                            debug_print("No OK button found or dialog auto-closed")
                        
                    except:
                        debug_print("No success dialog appeared")
                    
                    return True
                    
            except:
                pass  # Success message not found yet
            
            # Check for error messages
            try:
                error_msg = driver.find_element(By.CSS_SELECTOR, '#file-msgbox .text-danger')
                if error_msg.is_displayed():
                    error_text = error_msg.text
                    debug_print(f"Upload error message: {error_text}")
                    print(f"File upload failed: {error_text}")
                    return False
            except:
                pass  # Error message not found
            
            # Check progress bar
            try:
                progress_text = driver.find_element(By.CSS_SELECTOR, '#progressBar-1 .layui-progress-text')
                if progress_text.is_displayed():
                    progress_msg = progress_text.text
                    if "上传完毕" in progress_msg:
                        debug_print("Upload completed, waiting for final processing")
                    elif waited_time % 10 == 0:  # Print progress every 10 seconds
                        debug_print(f"Upload progress: {progress_msg}")
            except:
                pass
            
            if waited_time % 30 == 0:  # Print status every 30 seconds
                debug_print(f"Upload in progress... ({waited_time}s/{max_wait_time}s)")
        
        # If we get here, upload timed out
        print(f"Upload timeout after {max_wait_time} seconds")
        return False
        
    except Exception as e:
        debug_print(f"Error uploading file: {e}")
        print(f"Failed to upload file to: {detail_url} ({e})")
        return False
    finally:
        debug_print("Closing upload driver")
        driver.quit()

def interactive_upload_to_active_requests(headless=True):
    """
    Get active requests, let user select one, then upload a file to fulfill the request.
    """
    # Get active requests (limit to 10 for better interaction)
    requests = get_active_requests(limit=10, headless=headless)
    if not requests:
        print("No active requests found to upload to.")
        return

    print("Select a request to upload a file to (enter number), or press Enter to skip:")

    # Input with 30s timeout
    def input_with_timeout(prompt, timeout=30):
        q = queue.Queue()

        def inner():
            try:
                q.put(input(prompt))
            except Exception:
                q.put(None)

        t = threading.Thread(target=inner)
        t.daemon = True
        t.start()
        t.join(timeout)
        if t.is_alive():
            return None
        return q.get() if not q.empty() else None

    selection = input_with_timeout("Selection: ", 30)
    if selection is None:
        print("\nNo input received in 30 seconds. Upload operation aborted.")
        return

    selection = selection.strip()
    if not selection:
        print("No request selected for upload.")
        return

    # Parse selection
    try:
        index = int(selection)
        if not (1 <= index <= len(requests)):
            print(f"Invalid selection: {index} (out of range)")
            return
    except ValueError:
        print(f"Invalid input: {selection}")
        return

    selected_request = requests[index - 1]
    print(f"\nSelected request: {selected_request.get('title', 'N/A')}")
    
    success = upload_file_to_active_request(
        selected_request.get('detailUrl'), 
        headless=headless
    )
    
    if success:
        print("File uploaded successfully!")
    else:
        print("Failed to upload file.")

def check_in(headless=True):
    """
    Login and perform daily check-in by simulating the AJAX request used by the website.
    Then print today's date and extract the number of consecutive check-in days.
    """
    today = datetime.date.today()
    print(f"Today's date: {today}")
    print("Starting daily check-in process for AbleSci")
    # Navigate to homepage for check-in
    driver = login_and_navigate('https://www.ablesci.com', headless)
    if driver is None:
        print("Failed to login and navigate to homepage for check-in")
        return False
    try:
        wait = WebDriverWait(driver, 10)
        # Wait for the page to load (body element)
        debug_print("Waiting for page body to load")
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'body')))
        time.sleep(2)  # Give time for dynamic content to load
        # Use JavaScript to perform the AJAX check-in request and get the response
        debug_print("Executing AJAX check-in request via JavaScript")
        result = driver.execute_async_script("""
            var callback = arguments[arguments.length - 1];
            fetch("https://www.ablesci.com/user/sign", {
                method: "GET",
                credentials: "include"
            }).then(r => r.json()).then(res => callback(res)).catch(e => callback({error: e && e.message ? e.message : String(e)}));
        """)
        debug_print(f"AJAX check-in result: {result}")
        if result.get("error"):
            print(f"Check-in failed: {result['error']}")
            return False
        if result.get("code") == 0:
            print("Check-in successful!")
        elif result.get("code") == 1:
            print(f"Already checked in today: {result.get('msg', '')}")
        else:
            print(f"Check-in failed: {result.get('msg', 'Unknown error')}")
            return False

        # Try to extract consecutive check-in days from the page DOM
        signcount = None
        try:
            debug_print("Trying to extract consecutive check-in days from DOM")
            signcount_elem = driver.find_element(By.CSS_SELECTOR, '#sign-count')
            signcount = signcount_elem.text.strip()
            if signcount.isdigit():
                print(f"Consecutive check-in days: {signcount}")
            else:
                print("Could not extract consecutive check-in days from DOM.")
        except Exception as e:
            debug_print(f"Could not extract signcount from DOM: {e}")
            # Fallback to AJAX response
            signcount = result.get("data", {}).get("signcount")
            if signcount is not None:
                print(f"Consecutive check-in days: {signcount}")
            else:
                print("Could not extract consecutive check-in days.")

        return True
    except Exception as e:
        debug_print(f"Check-in failed: {e}")
        print("Check-in failed or already completed today.")
        return False
    finally:
        debug_print("Closing check-in driver")
        driver.quit()

def print_default_paths():
    print("Default paths and settings:")
    print(f"  Cache directory: {cache_dir}")
    print(f"  Cache file: {CACHE_FILE}")
    print(f"  Credentials file: {CREDENTIALS_FILE}")
    print(f"  Default download folder: {DEFAULT_DOWNLOAD_FOLDER}")

def main():
    global verbose
    # Get the parent package name from the module's __name__
    parent_package = __name__.split('.')[0] if '.' in __name__ else None

    if parent_package is None:
        program_name = 'ablesci'
    elif '_' in parent_package:
        # If the parent package has an underscore, strip it
        parent_package = parent_package[:parent_package.index('_')]
        program_name = f"{parent_package} ablesci"

    parser = argparse.ArgumentParser(
        prog=program_name,
        description='Command-line tool for interacting with ablesci.com',
        epilog='Example usage:\n'
               '  %(prog)s --user-info\n'
               '  %(prog)s --request-doi "10.1038/nature12373"\n'
               '  %(prog)s --request-doi dois.txt\n'
               '  %(prog)s --get-active-requests 50 --by-points\n'
               '  %(prog)s --download-fulfilled-requests ./downloads',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('--user-info', action='store_true', help='Print user info')
    parser.add_argument('--no-headless', action='store_true', help='Run browser in graphic mode')
    parser.add_argument('--request-doi', type=str, metavar='DOI|FILE', help='Specify a DOI, a space/comma separated list of DOIs, or a path to a txt file containing DOIs (one per line)')
    parser.add_argument('--verbose', action='store_true', help='Enable verbose debug output')
    parser.add_argument(
        '--credentials',
        type=str,
        metavar='FILE',
        help='Path to JSON file containing login credentials (format: {"ablesci_username": "...", "ablesci_password": "..."})'
    )
    parser.add_argument('--get-waiting-requests', action='store_true', help='Fetch all waiting requests which you made and not yet fulfilled')
    parser.add_argument('--get-fulfilled-requests', action='store_true', help='Fetch all fulfilled requests which you made and fulfilled by others')
    parser.add_argument('--cancel-waiting-requests', action='store_true', help='Interactively cancel waiting requests which you made')
    parser.add_argument('--download-fulfilled-requests', type=str, nargs='?', const='.', metavar='FOLDER', help='Interactively download files from fulfilled requests (optional download folder, default: current directory)')
    parser.add_argument('--accept-fulfilled-requests', action='store_true', help='Interactively accept fulfilled requests which you made')
    parser.add_argument('--reject-fulfilled-requests', action='store_true', help='Interactively reject fulfilled requests which you made')
    parser.add_argument('--get-active-requests', type=int, nargs='?', const=20, metavar='LIMIT', help='Fetch all active requests made by users which have not yet been fulfilled (optional limit, default: 20)')
    parser.add_argument('--by-points', action='store_true', help='Order active requests by reward points (highest first)')
    parser.add_argument('--solve-active-request', type=str, metavar='URL', help='Upload a file to solve a single active request by specifying its detail URL')
    parser.add_argument('--solve-active-requests', type=int, nargs='?', const=10, metavar='LIMIT', help='Interactively select and solve active requests by uploading files (optional limit, default: 10)')
    parser.add_argument('--clear-cache', action='store_true', help='Clear cache before running')
    parser.add_argument('--print-default', action='store_true', help='Print default paths and settings')
    parser.add_argument('--check-in', action='store_true', help='Perform daily check-in')
    args = parser.parse_args()

    # Validate argument conflicts
    if args.by_points and args.get_active_requests is None:
        parser.error("--by-points can only be used with --get-active-requests")

    verbose = args.verbose
    headless = not args.no_headless

    debug_print(f"Verbose mode: {verbose}")
    debug_print(f"Headless mode: {headless}")

    # Print default paths and settings if requested
    if args.print_default:
        print_default_paths()
        return

    # Clear cache if requested
    if args.clear_cache:
        debug_print("Clearing cache")
        if os.path.exists(CACHE_FILE):
            os.remove(CACHE_FILE)
            debug_print(f"Removed cache file: {CACHE_FILE}")
            print("Cache cleared.")
        else:
            debug_print("No cache file found to clear")
            print("No cache file found.")

    debug_print(f"Cache file exists: {os.path.exists(CACHE_FILE)}")

    # Load credentials from specified file if provided
    if args.credentials:
        username, password = load_credentials_from_file(args.credentials)
        if username and password:
            print(f"Credentials loaded successfully for user: {username}")
            sys.exit(0)
        else:
            print(f"Failed to load credentials from: {args.credentials}")
            sys.exit(1)

    if args.user_info:
        print("Getting user info...")
        get_user_info(headless=headless)
    if args.request_doi:
        dois = parse_dois_input(args.request_doi)
        request_multiple_dois(dois, headless=headless)
    if args.get_waiting_requests:
        print("Getting waiting requests...")
        get_waiting_requests(headless=headless)
    if args.get_fulfilled_requests:
        print("Getting fulfilled requests...")
        get_fulfilled_requests(headless=headless)
    if args.cancel_waiting_requests:
        print("Cancelling waiting requests...")
        interactive_cancel_waiting_requests(headless=headless)
    if args.download_fulfilled_requests is not None:
        print("Downloading files from fulfilled requests...")
        interactive_download_fulfilled_requests(headless=headless, download_folder=args.download_fulfilled_requests)
    if args.accept_fulfilled_requests:
        print("Accepting fulfilled requests...")
        interactive_accept_fulfilled_requests(headless=headless)
    if args.reject_fulfilled_requests:
        print("Rejecting fulfilled requests...")
        interactive_reject_fulfilled_requests(headless=headless)
    if args.get_active_requests is not None:
        print("Getting active requests...")
        get_active_requests(limit=args.get_active_requests, order_by_points=args.by_points, headless=headless)
    if args.solve_active_request:
        print(f"Solving active request: {args.solve_active_request}")
        success = upload_file_to_active_request(args.solve_active_request, headless=headless)
        if success:
            print("File uploaded successfully!")
        else:
            print("Failed to upload file.")
    if args.solve_active_requests is not None:
        print("Solving active requests...")
        interactive_upload_to_active_requests(headless=headless, limit=args.solve_active_requests)
    if args.check_in:
        print("Performing daily check-in...")
        check_in(headless=headless)

if __name__ == "__main__":
    main()
