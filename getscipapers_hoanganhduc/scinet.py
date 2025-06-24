from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
import time
import os
import argparse
import pickle
import json
from datetime import datetime, timedelta
import re
import requests
from selenium.webdriver.common.keys import Keys
import readline
import glob
import stat
import argcomplete
import signal
import getpass
import platform
import sys
import random
import tempfile

# Global variables for credentials
USERNAME = ""  # Replace with your actual username/email
PASSWORD = ""  # Replace with your actual password

# Cache and download configuration
def get_cache_directory():
    """Get the appropriate cache directory for the current platform, using getscipapers/scinet subfolder"""
    system = platform.system()
    subfolder = os.path.join('getscipapers', 'scinet')

    if system == "Windows":
        # Use %APPDATA% on Windows
        appdata = os.environ.get('APPDATA')
        if appdata:
            cache_dir = os.path.join(appdata, subfolder)
        else:
            # Fallback to user home directory
            cache_dir = os.path.join(os.path.expanduser('~'), 'AppData', 'Roaming', subfolder)
    elif system == "Darwin":  # macOS
        # Use ~/Library/Caches on macOS
        cache_dir = os.path.join(os.path.expanduser('~'), 'Library', 'Caches', subfolder)
    else:  # Linux and other Unix-like systems
        # Use ~/.config on Linux
        cache_dir = os.path.join(os.path.expanduser('~'), '.config', subfolder)
    # Create cache directory if it doesn't exist
    os.makedirs(cache_dir, exist_ok=True)
    return cache_dir

def get_download_directory():
    """Get the default download directory for the current platform, using getscipapers/scinet_downloads subfolder"""
    system = platform.system()
    subfolder = os.path.join('getscipapers', 'scinet')

    if system == "Windows":
        # Use %USERPROFILE%\Downloads on Windows
        userprofile = os.environ.get('USERPROFILE')
        if userprofile:
            download_dir = os.path.join(userprofile, 'Downloads', subfolder)
        else:
            download_dir = os.path.join(os.path.expanduser('~'), 'Downloads', subfolder)
    elif system == "Darwin":  # macOS
        # Use ~/Downloads on macOS
        download_dir = os.path.join(os.path.expanduser('~'), 'Downloads', subfolder)
    else:  # Linux and other Unix-like systems
        # Use ~/Downloads on Linux
        download_dir = os.path.join(os.path.expanduser('~'), 'Downloads', subfolder)
    # Ensure all parent directories exist
    os.makedirs(download_dir, exist_ok=True)
    return download_dir

CACHE_FILE = os.path.join(get_cache_directory(), "scinet_cache.pkl")
CACHE_DURATION_HOURS = 24  # Cache validity in hours
DEFAULT_DOWNLOAD_DIR = get_download_directory()

# Log configuration
LOG_FILE = "scinet.log"

# Global verbose flag
VERBOSE = False

def debug_print(message):
    """Print debug message only if verbose mode is enabled"""
    if VERBOSE:
        print(f"Debug: {message}")

def is_valid_doi(doi):
    """
    Validate DOI format using regex pattern
    
    Args:
        doi: DOI string to validate
    
    Returns:
        bool: True if DOI format is valid, False otherwise
    """
    # DOI regex pattern that matches:
    # - Standard DOI: 10.xxxx/yyyy
    # - DOI URL: https://doi.org/10.xxxx/yyyy or http://dx.doi.org/10.xxxx/yyyy
    doi_pattern = r'^(https?://(dx\.)?doi\.org/)?10\.\d{4,}/[^\s]+$'
    
    return bool(re.match(doi_pattern, doi.strip(), re.IGNORECASE))

def read_dois_with_rewards_from_file(file_path):
    """
    Read DOIs with optional reward tokens from a text file (one DOI per line or DOI,reward per line)
    
    Args:
        file_path: Path to the text file containing DOIs and optional reward tokens
    
    Returns:
        list: List of tuples (doi, reward_tokens) where reward_tokens defaults to 1 if not specified
    """
    doi_reward_pairs = []
    seen_dois = set()
    
    try:
        if not os.path.exists(file_path):
            print(f"DOI file not found: {file_path}")
            return doi_reward_pairs
        
        with open(file_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if line and not line.startswith('#'):  # Skip empty lines and comments
                    # Parse DOI and optional reward tokens
                    if ',' in line:
                        # DOI,reward_tokens format
                        parts = line.split(',', 1)
                        doi = parts[0].strip()
                        try:
                            reward_tokens = int(parts[1].strip())
                            if reward_tokens < 1:
                                print(f"Error: Reward tokens must be at least 1 at line {line_num}: '{line}'")
                                exit(1)
                        except ValueError:
                            print(f"Error: Invalid reward tokens '{parts[1].strip()}' at line {line_num}: '{line}'")
                            exit(1)
                    else:
                        # Just DOI, use default reward tokens
                        doi = line
                        reward_tokens = 1
                    
                    # Validate DOI format
                    if not is_valid_doi(doi):
                        print(f"Error: Invalid DOI format at line {line_num}: '{doi}'")
                        print("DOI format should be like: 10.1000/182 or https://doi.org/10.1000/182")
                        print("Exiting due to invalid DOI format.")
                        exit(1)
                    
                    # Check for duplicate DOIs
                    if doi in seen_dois:
                        print(f"Warning: Duplicate DOI found at line {line_num}: '{doi}' - skipping")
                        continue
                    
                    seen_dois.add(doi)
                    doi_reward_pairs.append((doi, reward_tokens))
                    debug_print(f"Read valid DOI {len(doi_reward_pairs)}: {doi} (reward tokens: {reward_tokens})")
        
        print(f"Read {len(doi_reward_pairs)} valid DOI-reward pairs from file: {file_path}")
        
    except Exception as e:
        print(f"Error reading DOI file {file_path}: {str(e)}")
        exit(1)
    
    return doi_reward_pairs

def get_pdf_files_from_directory(directory_path, recursive=False):
    """
    Get all PDF files from a directory
    
    Args:
        directory_path: Path to the directory containing PDF files
        recursive: Whether to search subdirectories recursively
    
    Returns:
        list: List of PDF file paths
    """
    pdf_files = []
    
    if not os.path.exists(directory_path):
        print(f"Directory not found: {directory_path}")
        return pdf_files
    
    if not os.path.isdir(directory_path):
        print(f"Path is not a directory: {directory_path}")
        return pdf_files
    
    try:
        if recursive:
            # Search recursively
            for root, dirs, files in os.walk(directory_path):
                for file in files:
                    if file.lower().endswith('.pdf'):
                        pdf_files.append(os.path.join(root, file))
        else:
            # Search only in the specified directory
            for file in os.listdir(directory_path):
                file_path = os.path.join(directory_path, file)
                if os.path.isfile(file_path) and file.lower().endswith('.pdf'):
                    pdf_files.append(file_path)
        
        pdf_files.sort()  # Sort alphabetically
        print(f"Found {len(pdf_files)} PDF files in {directory_path}")
        
    except Exception as e:
        print(f"Error reading directory {directory_path}: {str(e)}")
    
    return pdf_files

def save_login_cache(driver, username):
    """Save browser cookies and session data to cache file for the single user (no multi-user support)"""
    try:
        cache_data = {
            'cookies': driver.get_cookies(),
            'timestamp': datetime.now(),
            'user_agent': driver.execute_script("return navigator.userAgent;"),
            'username': username
        }
        with open(CACHE_FILE, 'wb') as f:
            pickle.dump(cache_data, f)
        os.chmod(CACHE_FILE, stat.S_IRUSR | stat.S_IWUSR)
        debug_print(f"Login cache saved successfully for user: {username}")
        return True
    except Exception as e:
        debug_print(f"Failed to save login cache for user {username}: {str(e)}")
        return False

def load_login_cache():
    """Load cached login data for the single user (no multi-user support)"""
    try:
        if not os.path.exists(CACHE_FILE):
            debug_print("No login cache file found")
            return None

        with open(CACHE_FILE, 'rb') as f:
            cache_data = pickle.load(f)

        # Expect cache_data to be a dict with required fields
        if not isinstance(cache_data, dict) or 'timestamp' not in cache_data:
            debug_print("Cache file format invalid, removing...")
            os.remove(CACHE_FILE)
            return None

        # Check if cache is still valid
        cache_age = datetime.now() - cache_data['timestamp']
        if cache_age > timedelta(hours=CACHE_DURATION_HOURS):
            debug_print(f"Login cache expired (age: {cache_age})")
            os.remove(CACHE_FILE)
            return None

        debug_print(f"Valid login cache found (age: {cache_age})")
        return cache_data

    except Exception as e:
        debug_print(f"Failed to load login cache: {str(e)}")
        try:
            os.remove(CACHE_FILE)
        except:
            pass
        return None

def apply_login_cache(driver, cache_data):
    """Apply cached cookies to current session (single-user cache)"""
    try:
        # Navigate to the site first
        driver.get("https://sci-net.xyz")
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )

        # Add each cookie from the cache_data (single user dict)
        cookies = cache_data.get('cookies', [])
        for cookie in cookies:
            try:
                # Ensure cookie domain is compatible
                if 'domain' in cookie and not cookie['domain'].endswith('sci-net.xyz'):
                    cookie['domain'] = '.sci-net.xyz'
                driver.add_cookie(cookie)
                debug_print(f"Added cookie: {cookie.get('name', 'unknown')}")
            except Exception as e:
                debug_print(f"Failed to add cookie {cookie.get('name', 'unknown')}: {str(e)}")

        # Refresh to apply cookies
        driver.refresh()
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        debug_print("Login cache applied successfully")
        return True
    except Exception as e:
        debug_print(f"Failed to apply login cache: {str(e)}")
        return False

def is_logged_in(driver):
    """Check if user is currently logged in"""
    try:
        # Navigate to upload page to test login status
        driver.get("https://sci-net.xyz/upload")
        time.sleep(2)
        
        # Check if we're redirected to login page or if upload elements are present
        current_url = driver.current_url
        
        # If we're on upload page and can see the upload pool, we're logged in
        if "upload" in current_url:
            try:
                WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.ID, "pool"))
                )
                debug_print("User is logged in (upload page accessible)")
                return True
            except:
                pass
        
        # Check for login form elements (indicates not logged in)
        try:
            driver.find_element(By.CSS_SELECTOR, "input[name='user']")
            debug_print("User is not logged in (login form present)")
            return False
        except:
            pass
        
        debug_print("Login status unclear, assuming not logged in")
        return False
        
    except Exception as e:
        debug_print(f"Error checking login status: {str(e)}")
        return False

def simulate_human_typing(element, text, log_func=None):
    """
    Simulate human-like typing patterns into a Selenium element.

    Args:
        element: Selenium WebElement to type into.
        text: The text string to type.
        log_func: Optional logging function for debug output.
    """
    if log_func:
        log_func(f"Typing text: {text[:20]}{'...' if len(text) > 20 else ''}")
    for char in text:
        element.send_keys(char)
        time.sleep(random.uniform(0.1, 0.3))
        if random.random() < 0.1:
            pause_time = random.uniform(0.3, 0.7)
            if log_func:
                log_func(f"Random pause: {pause_time:.2f}s")
            time.sleep(pause_time)

def perform_login(driver, username, password):
    """Perform actual login process with human-like typing and paste."""
    try:
        print("Navigating to sci-net.xyz for login...")
        driver.get("https://sci-net.xyz")

        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )

        debug_print("Looking for username field...")
        # Try to find the username field by name or by input[type='text'] in .login .form
        try:
            username_field = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.NAME, "user"))
            )
        except Exception:
            # Fallback: try input[type='text'] inside .login .form
            username_field = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".login .form input[type='text'][name='user']"))
            )

        debug_print("Looking for password field...")
        try:
            password_field = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.NAME, "pass"))
            )
        except Exception:
            # Fallback: try input[type='password'] inside .login .form
            password_field = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".login .form input[type='password'][name='pass']"))
            )

        # Enter credentials with human-like typing for first 3 chars, then paste the rest
        debug_print("Entering credentials with human-like typing and paste...")
        username_field.clear()
        if len(username) > 3:
            simulate_human_typing(username_field, username[:3], debug_print)
            username_field.send_keys(username[3:])
        else:
            simulate_human_typing(username_field, username, debug_print)

        password_field.clear()
        if len(password) > 3:
            simulate_human_typing(password_field, password[:3], debug_print)
            password_field.send_keys(password[3:])
        else:
            simulate_human_typing(password_field, password, debug_print)

        # Find and click login button
        debug_print("Looking for login button...")
        try:
            # Try button.round[type='submit'], fallback to button.round, fallback to button in .login .form
            try:
                login_button = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, "button.round[type='submit']"))
                )
            except:
                try:
                    login_button = WebDriverWait(driver, 10).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, "button.round"))
                    )
                except:
                    login_button = WebDriverWait(driver, 10).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, ".login .form button"))
                    )
        except Exception as e:
            print(f"Login button not found: {str(e)}")
            return False

        debug_print("Clicking login button...")
        login_button.click()

        time.sleep(3)

        if is_logged_in(driver):
            print("Login successful!")
            save_login_cache(driver, username)
            return True
        else:
            print("Login failed!")
            return False

    except Exception as e:
        print(f"Login error: {str(e)}")
        return False

def load_credentials_from_json(json_path):
    """
    Load login credentials from a JSON file
    
    Args:
        json_path: Path to the JSON file containing credentials
    
    Returns:
        dict: Dictionary containing username and password, or None if failed
    
    Expected JSON format:
    {
        "scinet_username": "your_username",
        "scinet_password": "your_password"
    }
    """
    try:
        # Expand user home directory
        json_path = os.path.expanduser(json_path)
        
        if not os.path.exists(json_path):
            print(f"Credentials file not found: {json_path}")
            return None
        
        # Check file permissions for security
        file_stat = os.stat(json_path)
        file_mode = stat.filemode(file_stat.st_mode)
        
        # Warn if file is readable by others (not secure)
        if file_stat.st_mode & (stat.S_IRGRP | stat.S_IROTH):
            print(f"Warning: Credentials file {json_path} is readable by others ({file_mode})")
            print("Consider setting more restrictive permissions: chmod 600 {json_path}")
        
        with open(json_path, 'r', encoding='utf-8') as f:
            credentials = json.load(f)
        
        # Validate required fields
        if not isinstance(credentials, dict):
            print(f"Error: Credentials file must contain a JSON object")
            return None
        
        username = credentials.get('scinet_username', '').strip()
        password = credentials.get('scinet_password', '').strip()
        
        if not username:
            print(f"Error: Missing or empty 'scinet_username' field in credentials file")
            return None
        
        if not password:
            print(f"Error: Missing or empty 'scinet_password' field in credentials file")
            return None
        
        debug_print(f"Successfully loaded credentials for user: {username}")
        return {
            'scinet_username': username,
            'scinet_password': password
        }
        
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON format in credentials file {json_path}: {str(e)}")
        return None
    except Exception as e:
        print(f"Error loading credentials from {json_path}: {str(e)}")
        return None

def login_to_scinet(username, password, headless=False):
    """
    Login to sci-net.xyz with caching support
    Returns driver instance if successful, None otherwise
    """
    # Setup webdriver
    options = webdriver.ChromeOptions()
    if headless:
        options.add_argument("--headless")
        debug_print("Running in headless mode")
    else:
        debug_print("Running with visible browser")
        
    # Use a temporary directory to avoid conflicts
    user_data_dir = os.getenv("USER_DATA_DIR", tempfile.mkdtemp())
    if not os.path.exists(user_data_dir):
        os.makedirs(user_data_dir, exist_ok=True)
    options.add_argument(f"--user-data-dir={user_data_dir}")
    
    # Add options to ignore permission requests
    options.add_argument("--disable-notifications")
    options.add_argument("--disable-popup-blocking")
    options.add_argument("--disable-infobars")
    options.add_argument("--disable-extensions")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-web-security")
    options.add_argument("--allow-running-insecure-content")
    
    debug_print("Initializing Chrome driver...")
    driver = webdriver.Chrome(options=options)
    
    try:
        # Try to use cached login first
        cache_data = load_login_cache()
        login_success = False
        
        if cache_data:
            print("Attempting to use cached login...")
            if apply_login_cache(driver, cache_data):
                if is_logged_in(driver):
                    print("Successfully logged in using cache!")
                    login_success = True
                else:
                    print("Cached login expired, performing fresh login...")
        
        # If cache didn't work, perform fresh login
        if not login_success:
            print("Performing fresh login...")
            login_success = perform_login(driver, username, password)
            # Save cache after successful login
            if login_success:
                save_login_cache(driver, username)
        
        # If login failed, ask user for manual input
        if not login_success:
            def timeout_handler(signum, frame):
                print("\nTimeout: No input received within 30 seconds. Login failed.")
                raise TimeoutError("Login timeout")
            
            try:
                print("\nLogin failed. Please enter credentials manually:")
                
                # Set up timeout signal (only on Unix-like systems)
                if hasattr(signal, 'SIGALRM'):
                    signal.signal(signal.SIGALRM, timeout_handler)
                    signal.alarm(30)  # 30 second timeout
                
                manual_username = input("Username: ").strip()
                manual_password = getpass.getpass("Password: ")
                
                # Cancel the alarm (only on Unix-like systems)
                if hasattr(signal, 'alarm'):
                    signal.alarm(0)
                
                if manual_username and manual_password:
                    print("Attempting login with manually entered credentials...")
                    login_success = perform_login(driver, manual_username, manual_password)
                    # Save cache after successful manual login
                    if login_success:
                        save_login_cache(driver, manual_username)
                else:
                    print("Error: Username or password is empty")
                    
            except (KeyboardInterrupt, TimeoutError):
                if hasattr(signal, 'alarm'):
                    signal.alarm(0)  # Cancel alarm
                print("\nLogin cancelled or timeout. Operation aborted.")
                login_success = False
            except Exception as manual_error:
                if hasattr(signal, 'alarm'):
                    signal.alarm(0)  # Cancel alarm
                print(f"Error during manual login: {str(manual_error)}")
                login_success = False
            finally:
                # Make sure alarm is always cancelled (only on Unix-like systems)
                if hasattr(signal, 'alarm'):
                    signal.alarm(0)
        
        if login_success:
            return driver
        else:
            print("Failed to login!")
            driver.quit()
            return None
            
    except Exception as e:
        print(f"Login error: {str(e)}")
        driver.quit()
        return None

def upload_pdf_to_scinet(driver, pdf_path, headless=False):
    """
    Upload a PDF file to sci-net.xyz using an authenticated driver session
    """
    try:
        # Check if PDF file exists
        if not os.path.exists(pdf_path):
            print(f"Error: PDF file not found at {pdf_path}")
            return False
        
        debug_print(f"PDF file found at {pdf_path}")
        debug_print(f"File size: {os.path.getsize(pdf_path)} bytes")
        
        # Navigate to upload page
        print("Navigating to upload page...")
        driver.get("https://sci-net.xyz/upload")
        debug_print(f"Current URL: {driver.current_url}")
        
        print("Uploading PDF file...")
        # Wait for the upload pool to be available
        debug_print("Looking for upload pool element...")
        WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.ID, "pool"))
        )
        debug_print("Upload pool element found")
        
        # Try to find existing file input or create one
        debug_print("Looking for file input element...")
        try:
            file_input = driver.find_element(By.CSS_SELECTOR, "input[type='file']")
            debug_print("Found existing file input")
        except:
            debug_print("Creating file input via JavaScript...")
            driver.execute_script("""
                var input = document.createElement('input');
                input.type = 'file';
                input.accept = '.pdf';
                input.multiple = false;
                input.style.position = 'absolute';
                input.style.left = '-9999px';
                input.id = 'selenium-file-input';
                document.body.appendChild(input);
            """)
            file_input = driver.find_element(By.ID, "selenium-file-input")
        
        # Send file to the input
        debug_print("Sending file to input...")
        abs_path = os.path.abspath(pdf_path)
        debug_print(f"Absolute file path: {abs_path}")
        file_input.send_keys(abs_path)
        
        # Trigger the upload using the site's upload mechanism
        debug_print("Triggering upload via JavaScript...")
        result = driver.execute_script("""
            var input = document.getElementById('selenium-file-input') || document.querySelector('input[type="file"]');
            var files = input.files;
            console.log('Files found:', files.length);
            
            if (files.length > 0) {
                var file = files[0];
                console.log('Processing file:', file.name, 'size:', file.size);
                
                // Check if uploads object exists
                if (typeof uploads === 'undefined') {
                    window.uploads = {};
                }
                
                // Check if article class exists
                if (typeof article !== 'undefined') {
                    if (!(file.name in uploads)) {
                        console.log('Starting upload for:', file.name);
                        var articleInstance = new article(file);
                        articleInstance.upload();
                        return 'Upload initiated for ' + file.name;
                    } else {
                        return 'File already in uploads: ' + file.name;
                    }
                } else {
                    // Fallback: trigger change event on file input
                    var event = new Event('change', { bubbles: true });
                    input.dispatchEvent(event);
                    return 'Triggered change event on file input';
                }
            } else {
                return 'No files found in input';
            }
        """)
        debug_print(f"JavaScript execution result: {result}")
        
        # Calculate wait time based on file size
        file_size_mb = os.path.getsize(pdf_path) / (1024 * 1024)
        wait_time = max(10, min(120, int(file_size_mb * 5)))
        
        debug_print(f"File size: {file_size_mb:.2f} MB, waiting {wait_time} seconds...")
        time.sleep(wait_time)
        debug_print(f"{wait_time} second wait completed, checking upload status...")
        
        # Check for upload status and messages
        try:
            # Check for notice messages
            found_messages = driver.find_elements(By.CSS_SELECTOR, ".found")
            for msg in found_messages:
                if msg.is_displayed():
                    message_text = msg.text.strip()
                    if message_text:
                        print(f"Notice: {message_text}")
            
            # Check for error messages
            error_messages = driver.find_elements(By.CSS_SELECTOR, ".error")
            for error in error_messages:
                if error.is_displayed():
                    error_text = error.text.strip()
                    if error_text:
                        print(f"Error: {error_text}")
            
        except Exception as save_error:
            debug_print(f"Error checking upload status: {str(save_error)}")
        
        return True
            
    except Exception as e:
        print(f"Upload error: {str(e)}")
        debug_print(f"Current URL when error occurred: {driver.current_url}")
        debug_print(f"Page title: {driver.title}")
        # Take a screenshot for debugging if not headless
        if not headless:
            try:
                screenshot_path = "debug_screenshot.png"
                driver.save_screenshot(screenshot_path)
                debug_print(f"Screenshot saved to {screenshot_path}")
            except:
                debug_print("Could not save screenshot")
        return False

def upload_multiple_pdfs_to_scinet(driver, pdf_paths, headless=False):
    """
    Upload multiple PDF files to sci-net.xyz using an authenticated driver session
    
    Args:
        driver: Selenium WebDriver instance (already logged in)
        pdf_paths: List of paths to PDF files to upload
        headless: Whether running in headless mode (for debugging)
    
    Returns:
        dict: Summary of upload results
    """
    if not pdf_paths:
        print("No PDF files provided for upload")
        return {
            'total_files': 0,
            'successful_uploads': 0,
            'failed_uploads': 0,
            'results': []
        }
    
    print(f"Starting upload of {len(pdf_paths)} PDF files...")
    
    results = []
    successful_uploads = 0
    failed_uploads = 0
    all_notices = []
    
    for i, pdf_path in enumerate(pdf_paths, 1):
        print(f"\n--- Uploading file {i}/{len(pdf_paths)} ---")
        print(f"File: {os.path.basename(pdf_path)}")
        
        # Check if file exists before attempting upload
        if not os.path.exists(pdf_path):
            result = {
                'file_path': pdf_path,
                'file_name': os.path.basename(pdf_path),
                'success': False,
                'error': f'File not found: {pdf_path}',
                'file_size': 0,
                'notices': []
            }
            results.append(result)
            failed_uploads += 1
            print(f"✗ Error: File not found - {pdf_path}")
            continue
        
        # Get file size for reporting
        file_size = os.path.getsize(pdf_path)
        file_size_mb = file_size / (1024 * 1024)
        
        # Use the existing upload_pdf_to_scinet function
        upload_success = upload_pdf_to_scinet(driver, pdf_path, headless)
        
        # Capture any notices after upload attempt
        file_notices = []
        try:
            # Check for notice messages
            found_messages = driver.find_elements(By.CSS_SELECTOR, ".found")
            for msg in found_messages:
                if msg.is_displayed():
                    message_text = msg.text.strip()
                    if message_text and message_text not in file_notices:
                        file_notices.append(message_text)
                        all_notices.append(f"{os.path.basename(pdf_path)}: {message_text}")
            
            # Check for error messages
            error_messages = driver.find_elements(By.CSS_SELECTOR, ".error")
            for error in error_messages:
                if error.is_displayed():
                    error_text = error.text.strip()
                    if error_text and error_text not in file_notices:
                        file_notices.append(f"Error: {error_text}")
                        all_notices.append(f"{os.path.basename(pdf_path)}: Error: {error_text}")
        except Exception as notice_error:
            debug_print(f"Error capturing notices for {pdf_path}: {str(notice_error)}")
        
        result = {
            'file_path': pdf_path,
            'file_name': os.path.basename(pdf_path),
            'success': upload_success,
            'error': None if upload_success else 'Upload failed (see previous error messages)',
            'file_size': file_size,
            'file_size_mb': round(file_size_mb, 2),
            'notices': file_notices
        }
        
        results.append(result)
        
        if upload_success:
            successful_uploads += 1
            print(f"✓ Successfully uploaded: {os.path.basename(pdf_path)} ({result['file_size_mb']} MB)")
        else:
            failed_uploads += 1
            print(f"✗ Failed to upload: {os.path.basename(pdf_path)}")
        
        # Print notices for this file if any
        if file_notices:
            for notice in file_notices:
                print(f"  Notice: {notice}")
        
        # Add delay between uploads to avoid overwhelming the server
        if i < len(pdf_paths):
            delay_seconds = 3
            print(f"Waiting {delay_seconds} seconds before next upload...")
            time.sleep(delay_seconds)
    
    # Summary
    summary = {
        'total_files': len(pdf_paths),
        'successful_uploads': successful_uploads,
        'failed_uploads': failed_uploads,
        'results': results,
        'all_notices': all_notices,
        'timestamp': datetime.now().isoformat()
    }
    
    print(f"\n{'='*80}")
    print(f"MULTIPLE PDF UPLOAD SUMMARY")
    print(f"{'='*80}")
    print(f"Total files processed: {summary['total_files']}")
    print(f"Successful uploads: {summary['successful_uploads']}")
    print(f"Failed uploads: {summary['failed_uploads']}")
    
    if successful_uploads > 0:
        print(f"\nSuccessfully uploaded files:")
        total_size_mb = 0
        for result in results:
            if result['success']:
                print(f"  ✓ {result['file_name']} ({result['file_size_mb']} MB)")
                total_size_mb += result['file_size_mb']
        print(f"  Total size uploaded: {round(total_size_mb, 2)} MB")
    
    if failed_uploads > 0:
        print(f"\nFailed uploads:")
        for result in results:
            if not result['success']:
                print(f"  ✗ {result['file_name']}")
                if result['error']:
                    print(f"    Error: {result['error']}")
    
    if all_notices:
        print(f"\nNotices received during upload:")
        for notice in all_notices:
            print(f"  • {notice}")
    
    print(f"{'='*80}")
    
    return summary

def login_and_upload_multiple_pdfs(username, password, pdf_paths, headless=False):
    """
    Login to sci-net.xyz and upload multiple PDF files with caching support
    
    Args:
        username: Username for login
        password: Password for login
        pdf_paths: List of paths to PDF files to upload
        headless: Whether to run browser in headless mode
    
    Returns:
        dict: Summary of upload results, or None if login failed
    """
    driver = login_to_scinet(username, password, headless)
    if not driver:
        return None
    
    try:
        summary = upload_multiple_pdfs_to_scinet(driver, pdf_paths, headless)
        return summary
    finally:
        print("Multiple PDF upload process completed, closing browser.")
        driver.quit()

def login_and_upload_pdf(username, password, pdf_path, headless=False):
    """
    Login to sci-net.xyz and upload a PDF file with caching support
    """
    driver = login_to_scinet(username, password, headless)
    if not driver:
        return False
    
    try:
        success = upload_pdf_to_scinet(driver, pdf_path, headless)
        return success
    finally:
        print("PDF upload process completed, closing browser.")
        driver.quit()

def login_and_upload_directory_pdfs(username, password, directory_path, recursive=False, headless=False):
    """
    Login to sci-net.xyz and upload all PDF files from a directory
    
    Args:
        username: Username for login
        password: Password for login
        directory_path: Path to the directory containing PDF files
        recursive: Whether to search subdirectories recursively
        headless: Whether to run browser in headless mode
    
    Returns:
        dict: Summary of upload results
    """
    # Get all PDF files from the directory
    pdf_files = get_pdf_files_from_directory(directory_path, recursive)
    
    if not pdf_files:
        print(f"No PDF files found in directory: {directory_path}")
        return {
            'directory_path': directory_path,
            'recursive': recursive,
            'total_files': 0,
            'successful_uploads': 0,
            'failed_uploads': 0,
            'results': []
        }
    
    # Use the existing login_and_upload_multiple_pdfs function
    print(f"Found {len(pdf_files)} PDF files in directory: {directory_path}")
    if recursive:
        print("Including subdirectories in search")
    
    return login_and_upload_multiple_pdfs(username, password, pdf_files, headless)

def request_paper_by_doi(driver, doi, wait_seconds=50, reward_tokens=1):
    """
    Login to sci-net.xyz and request a paper by DOI
    Returns the output/result after submission
    """
    try:
        print(f"Requesting paper with DOI: {doi}")
        
        # Navigate to the main page
        driver.get("https://sci-net.xyz")
        
        # Wait for the page to load
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        
        debug_print("Looking for DOI input field...")
        # Find the DOI input field
        doi_input = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "DOI"))
        )
        
        debug_print("Clearing and entering DOI...")
        # Clear the input and enter the DOI
        doi_input.clear()
        doi_input.send_keys(doi)
        
        debug_print("Looking for search button...")
        # Find and click the search button
        search_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "button[onclick='search()']"))
        )
        
        debug_print("Clicking search button...")
        search_button.click()
        
        # Wait for the specified time for results to load
        debug_print(f"Waiting {wait_seconds} seconds for results...")
        time.sleep(wait_seconds)
        
        # Capture the current page state/output
        try:
            result_data = {
                'doi': doi,
                'current_url': driver.current_url,
                'timestamp': datetime.now().isoformat(),
                'page_title': driver.title,
                'messages': [],
                'paper_info': {},
                'availability': {}
            }
            
            # Check for different availability sources in the .found container
            found_container = driver.find_element(By.CSS_SELECTOR, ".found")
            
            # Check for Sci-Hub availability
            try:
                sci_hub_element = found_container.find_element(By.CSS_SELECTOR, ".sci-hub")
                if sci_hub_element.is_displayed():
                    sci_hub_link = sci_hub_element.get_attribute("href")
                    result_data['availability']['sci_hub'] = {
                        'available': True,
                        'link': sci_hub_link,
                        'message': sci_hub_element.text.strip()
                    }
                    print("Found: Paper available on Sci-Hub")
            except:
                pass
            
            # Check for Open Access availability
            try:
                oa_element = found_container.find_element(By.CSS_SELECTOR, ".openaccess")
                if oa_element.is_displayed():
                    oa_link = oa_element.get_attribute("href")
                    result_data['availability']['open_access'] = {
                        'available': True,
                        'link': oa_link,
                        'message': oa_element.text.strip()
                    }
                    print("Found: Paper is open access")
            except:
                pass
            
            # Check for arXiv availability
            try:
                arxiv_element = found_container.find_element(By.CSS_SELECTOR, ".arxiv")
                if arxiv_element.is_displayed():
                    arxiv_link = arxiv_element.get_attribute("href")
                    result_data['availability']['arxiv'] = {
                        'available': True,
                        'link': arxiv_link,
                        'message': arxiv_element.text.strip()
                    }
                    print("Found: Paper available on arXiv")
            except:
                pass
            
            # Check for preprint availability
            try:
                preprint_element = found_container.find_element(By.CSS_SELECTOR, ".preprint")
                if preprint_element.is_displayed():
                    preprint_link = preprint_element.get_attribute("href")
                    result_data['availability']['preprint'] = {
                        'available': True,
                        'link': preprint_link,
                        'message': preprint_element.text.strip()
                    }
                    print("Found: Paper available as preprint")
            except:
                pass
            
            # Check if already posted on Sci-Net
            try:
                scinet_element = found_container.find_element(By.CSS_SELECTOR, ".sci-net")
                if scinet_element.is_displayed():
                    scinet_link_element = scinet_element.find_element(By.TAG_NAME, "a")
                    scinet_link = scinet_link_element.get_attribute("href")
                    result_data['availability']['sci_net'] = {
                        'already_requested': True,
                        'link': scinet_link,
                        'message': scinet_element.text.strip()
                    }
                    print("Found: Paper already requested on Sci-Net")
            except:
                pass
            
            # Extract paper information from preview section
            try:
                preview_section = driver.find_element(By.CSS_SELECTOR, ".preview")
                
                # Get year and journal
                try:
                    yejo_element = preview_section.find_element(By.CSS_SELECTOR, ".yejo")
                    year = yejo_element.find_element(By.CSS_SELECTOR, ".year").text.strip()
                    journal = yejo_element.find_element(By.CSS_SELECTOR, ".journal").text.strip()
                    result_data['paper_info']['year'] = year
                    result_data['paper_info']['journal'] = journal
                except:
                    pass
                
                # Get title
                try:
                    title_element = preview_section.find_element(By.CSS_SELECTOR, ".title a")
                    title = title_element.text.strip()
                    title_link = title_element.get_attribute("href")
                    result_data['paper_info']['title'] = title
                    result_data['paper_info']['title_link'] = title_link
                except:
                    pass
                
                # Get authors
                try:
                    authors_element = preview_section.find_element(By.CSS_SELECTOR, ".authors")
                    authors = authors_element.text.strip()
                    result_data['paper_info']['authors'] = authors
                except:
                    pass
                
                # Get abstract
                try:
                    abstract_element = preview_section.find_element(By.CSS_SELECTOR, ".abstract")
                    abstract = abstract_element.text.strip()
                    result_data['paper_info']['abstract'] = abstract
                except:
                    pass
                
                # Get publisher
                try:
                    publisher_element = preview_section.find_element(By.CSS_SELECTOR, ".publisher img")
                    publisher_logo = publisher_element.get_attribute("src")
                    publisher_title = publisher_element.get_attribute("title")
                    result_data['paper_info']['publisher'] = {
                        'name': publisher_title,
                        'logo': publisher_logo
                    }
                except:
                    pass
                
            except:
                debug_print("Could not find preview section")
            
            # Check for error messages
            try:
                error_element = driver.find_element(By.CSS_SELECTOR, ".error")
                if error_element.is_displayed():
                    error_text = error_element.text.strip()
                    if error_text:
                        result_data['messages'].append(f"Error: {error_text}")
                        print(f"Error found: {error_text}")
            except:
                pass
            
            # Check if request section is available (paper can be requested)
            try:
                post_section = driver.find_element(By.CSS_SELECTOR, ".post")
                if post_section.is_displayed():
                    result_data['can_request'] = True
                    
                    # Get reward information
                    try:
                        reward_input = post_section.find_element(By.ID, "reward")
                        default_reward = reward_input.get_attribute("value")
                        max_reward = reward_input.get_attribute("max")
                        result_data['request_info'] = {
                            'default_reward': default_reward,
                            'max_reward': max_reward
                        }
                        
                        # Use the specified reward tokens, but respect the max limit
                        max_reward_int = int(max_reward) if max_reward else float('inf')
                        final_reward = min(reward_tokens, max_reward_int)
                        
                        debug_print(f"Requested reward: {reward_tokens}, Max reward: {max_reward_int}, Setting reward to: {final_reward}")
                        reward_input.clear()
                        reward_input.send_keys(str(final_reward))
                        result_data['request_info']['set_reward'] = final_reward
                        
                        # Click the request button
                        try:
                            request_button = post_section.find_element(By.CSS_SELECTOR, "button[onclick='request()']")
                            debug_print("Clicking request button...")
                            request_button.click()
                            result_data['request_submitted'] = True
                            
                            # Wait a moment for the request to be processed
                            time.sleep(3)
                            debug_print("Request submitted successfully")
                            
                        except Exception as request_error:
                            debug_print(f"Error clicking request button: {str(request_error)}")
                            result_data['request_submitted'] = False
                            result_data['request_error'] = str(request_error)
                        
                    except Exception as reward_error:
                        debug_print(f"Error processing reward input: {str(reward_error)}")
                        pass
                else:
                    result_data['can_request'] = False
            except:
                result_data['can_request'] = False
            
            print(f"DOI search completed. Current URL: {driver.current_url}")
            if result_data['messages']:
                for msg in result_data['messages']:
                    print(msg)
            
            return result_data
            
        except Exception as capture_error:
            debug_print(f"Error capturing results: {str(capture_error)}")
            return {
                'doi': doi,
                'error': str(capture_error),
                'timestamp': datetime.now().isoformat()
            }
            
    except Exception as e:
        print(f"DOI search error: {str(e)}")
        return {
            'doi': doi,
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }

def login_and_request_doi(username, password, doi, wait_seconds=50, reward_tokens=1, headless=False):
    """
    Login to sci-net.xyz and request a paper by DOI
    Returns the search results
    """
    driver = login_to_scinet(username, password, headless)
    if not driver:
        return None
    
    try:
        result = request_paper_by_doi(driver, doi, wait_seconds, reward_tokens)
        return result
    finally:
        print("DOI search process completed, closing browser.")
        driver.quit()

def request_multiple_papers_by_dois(driver, dois, wait_seconds=50, reward_tokens=1):
    """
    Request multiple papers by their DOIs
    
    Args:
        driver: Selenium WebDriver instance
        dois: List of DOI strings to request
        wait_seconds: Seconds to wait for each DOI search results
        reward_tokens: Number of reward tokens to offer for each request
    
    Returns:
        dict: Summary of request results
    """
    if not dois:
        print("No DOIs provided for requesting")
        return {
            'total_dois': 0,
            'successful_requests': 0,
            'failed_requests': 0,
            'results': []
        }
    
    print(f"Starting request process for {len(dois)} DOIs...")
    
    results = []
    successful_requests = 0
    failed_requests = 0
    
    for i, doi in enumerate(dois, 1):
        print(f"\n--- Requesting DOI {i}/{len(dois)} ---")
        print(f"DOI: {doi}")
        
        # Clean the DOI string
        clean_doi = doi.strip()
        if not clean_doi:
            result = {
                'doi': doi,
                'success': False,
                'error': 'Empty DOI provided',
                'timestamp': datetime.now().isoformat()
            }
            results.append(result)
            failed_requests += 1
            print(f"✗ Error: Empty DOI")
            continue
        
        # Use the existing request_paper_by_doi function
        result = request_paper_by_doi(driver, clean_doi, wait_seconds, reward_tokens)
        results.append(result)
        
        if result and not result.get('error'):
            successful_requests += 1
            print(f"✓ Successfully processed request for: {clean_doi}")
            
            # Print any availability information
            availability = result.get('availability', {})
            if availability:
                for source, info in availability.items():
                    if info.get('available') or info.get('already_requested'):
                        status = "already requested" if info.get('already_requested') else "available"
                        print(f"  - {source.replace('_', ' ').title()}: {status}")
            
            # Print if request was submitted
            if result.get('request_submitted'):
                reward = result.get('request_info', {}).get('set_reward', reward_tokens)
                print(f"  - New request submitted with {reward} reward token(s)")
            elif result.get('can_request') == False:
                print(f"  - Request not needed (paper already available or requested)")
        else:
            failed_requests += 1
            error_msg = result.get('error', 'Unknown error') if result else 'Request failed'
            print(f"✗ Failed to process: {clean_doi}")
            print(f"  Error: {error_msg}")
        
        # Add delay between requests to avoid overwhelming the server
        if i < len(dois):
            delay_seconds = 3
            print(f"Waiting {delay_seconds} seconds before next request...")
            time.sleep(delay_seconds)
    
    # Summary
    summary = {
        'total_dois': len(dois),
        'successful_requests': successful_requests,
        'failed_requests': failed_requests,
        'results': results,
        'reward_tokens_per_request': reward_tokens,
        'wait_seconds': wait_seconds,
        'timestamp': datetime.now().isoformat()
    }
    
    print(f"\n{'='*80}")
    print(f"MULTIPLE DOI REQUEST SUMMARY")
    print(f"{'='*80}")
    print(f"Total DOIs processed: {summary['total_dois']}")
    print(f"Successful requests: {summary['successful_requests']}")
    print(f"Failed requests: {summary['failed_requests']}")
    
    if successful_requests > 0:
        print(f"\nSuccessfully processed DOIs:")
        new_requests = 0
        already_available = 0
        
        for result in results:
            if result and not result.get('error'):
                doi = result.get('doi', 'Unknown')
                
                if result.get('request_submitted'):
                    new_requests += 1
                    reward = result.get('request_info', {}).get('set_reward', reward_tokens)
                    print(f"  ✓ {doi} - New request submitted ({reward} tokens)")
                else:
                    already_available += 1
                    # Check what type of availability
                    availability = result.get('availability', {})
                    sources = []
                    for source, info in availability.items():
                        if info.get('available') or info.get('already_requested'):
                            sources.append(source.replace('_', ' ').title())
                    
                    if sources:
                        print(f"  ✓ {doi} - Available via: {', '.join(sources)}")
                    else:
                        print(f"  ✓ {doi} - Processed successfully")
        
        if new_requests > 0:
            print(f"\n  New requests submitted: {new_requests}")
            print(f"  Total tokens used: {new_requests * reward_tokens}")
        if already_available > 0:
            print(f"  Papers already available: {already_available}")
    
    if failed_requests > 0:
        print(f"\nFailed requests:")
        for result in results:
            if result and result.get('error'):
                doi = result.get('doi', 'Unknown')
                error = result.get('error', 'Unknown error')
                print(f"  ✗ {doi} - {error}")
    
    print(f"{'='*80}")
    
    return summary

def login_and_request_multiple_dois(username, password, dois, wait_seconds=50, reward_tokens=1, headless=False):
    """
    Login to sci-net.xyz and request multiple papers by DOIs
    
    Args:
        username: Username for login
        password: Password for login
        dois: List of DOI strings to request
        wait_seconds: Seconds to wait for each DOI search results
        reward_tokens: Number of reward tokens to offer for each request
        headless: Whether to run browser in headless mode
    
    Returns:
        dict: Summary of request results, or None if login failed
    """
    driver = login_to_scinet(username, password, headless)
    if not driver:
        return None
    
    try:
        summary = request_multiple_papers_by_dois(driver, dois, wait_seconds, reward_tokens)
        return summary
    finally:
        print("Multiple DOI request process completed, closing browser.")
        driver.quit()

def login_and_request_multiple_dois_with_rewards(username, password, doi_reward_pairs, wait_seconds=50, headless=False):
    """
    Login to sci-net.xyz and request multiple papers by DOIs with individual reward tokens
    
    Args:
        username: Username for login
        password: Password for login
        doi_reward_pairs: List of tuples (doi, reward_tokens)
        wait_seconds: Seconds to wait for each DOI search results
        headless: Whether to run browser in headless mode
    
    Returns:
        dict: Summary of request results, or None if login failed
    """
    driver = login_to_scinet(username, password, headless)
    if not driver:
        return None
    
    try:
        # Convert doi_reward_pairs to separate lists for the existing function
        # But we need to handle different reward tokens per DOI
        results = []
        successful_requests = 0
        failed_requests = 0
        
        print(f"Starting request process for {len(doi_reward_pairs)} DOIs with individual reward tokens...")
        
        for i, (doi, reward_tokens) in enumerate(doi_reward_pairs, 1):
            print(f"\n--- Requesting DOI {i}/{len(doi_reward_pairs)} ---")
            print(f"DOI: {doi}")
            print(f"Reward tokens: {reward_tokens}")
            
            # Use the existing request_paper_by_doi function
            result = request_paper_by_doi(driver, doi, wait_seconds, reward_tokens)
            results.append(result)
            
            if result and not result.get('error'):
                successful_requests += 1
                print(f"✓ Successfully processed request for: {doi}")
                
                # Print any availability information
                availability = result.get('availability', {})
                if availability:
                    for source, info in availability.items():
                        if info.get('available') or info.get('already_requested'):
                            status = "already requested" if info.get('already_requested') else "available"
                            print(f"  - {source.replace('_', ' ').title()}: {status}")
                
                # Print if request was submitted
                if result.get('request_submitted'):
                    actual_reward = result.get('request_info', {}).get('set_reward', reward_tokens)
                    print(f"  - New request submitted with {actual_reward} reward token(s)")
                elif result.get('can_request') == False:
                    print(f"  - Request not needed (paper already available or requested)")
            else:
                failed_requests += 1
                error_msg = result.get('error', 'Unknown error') if result else 'Request failed'
                print(f"✗ Failed to process: {doi}")
                print(f"  Error: {error_msg}")
            
            # Add delay between requests to avoid overwhelming the server
            if i < len(doi_reward_pairs):
                delay_seconds = 3
                print(f"Waiting {delay_seconds} seconds before next request...")
                time.sleep(delay_seconds)
        
        # Summary
        summary = {
            'total_dois': len(doi_reward_pairs),
            'successful_requests': successful_requests,
            'failed_requests': failed_requests,
            'results': results,
            'wait_seconds': wait_seconds,
            'timestamp': datetime.now().isoformat()
        }
        
        print(f"\n{'='*80}")
        print(f"MULTIPLE DOI REQUEST SUMMARY")
        print(f"{'='*80}")
        print(f"Total DOIs processed: {summary['total_dois']}")
        print(f"Successful requests: {summary['successful_requests']}")
        print(f"Failed requests: {summary['failed_requests']}")
        
        if successful_requests > 0:
            print(f"\nSuccessfully processed DOIs:")
            new_requests = 0
            already_available = 0
            total_tokens_used = 0
            
            for i, result in enumerate(results):
                if result and not result.get('error'):
                    doi, reward_tokens = doi_reward_pairs[i]
                    
                    if result.get('request_submitted'):
                        new_requests += 1
                        actual_reward = result.get('request_info', {}).get('set_reward', reward_tokens)
                        total_tokens_used += actual_reward
                        print(f"  ✓ {doi} - New request submitted ({actual_reward} tokens)")
                    else:
                        already_available += 1
                        # Check what type of availability
                        availability = result.get('availability', {})
                        sources = []
                        for source, info in availability.items():
                            if info.get('available') or info.get('already_requested'):
                                sources.append(source.replace('_', ' ').title())
                        
                        if sources:
                            print(f"  ✓ {doi} - Available via: {', '.join(sources)}")
                        else:
                            print(f"  ✓ {doi} - Processed successfully")
            
            if new_requests > 0:
                print(f"\n  New requests submitted: {new_requests}")
                print(f"  Total tokens used: {total_tokens_used}")
            if already_available > 0:
                print(f"  Papers already available: {already_available}")
        
        if failed_requests > 0:
            print(f"\nFailed requests:")
            for i, result in enumerate(results):
                if result and result.get('error'):
                    doi, _ = doi_reward_pairs[i]
                    error = result.get('error', 'Unknown error')
                    print(f"  ✗ {doi} - {error}")
        
        print(f"{'='*80}")
        
        return summary
    finally:
        print("Multiple DOI request process completed, closing browser.")
        driver.quit()

def get_active_requests(driver, limit=None):
    """
    Get the list of active requests from sci-net.xyz
    Returns a list of request dictionaries with details
    
    Args:
        driver: Selenium WebDriver instance
        limit: Optional integer to limit the number of requests returned
    """
    try:
        print("Getting active requests from sci-net.xyz...")
        
        # Navigate to the main page
        driver.get("https://sci-net.xyz")
        
        # Wait for the page to load
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        
        debug_print("Looking for active requests section...")
        
        # Find the requests container
        try:
            requests_container = driver.find_element(By.CSS_SELECTOR, ".requests")
        except:
            debug_print("Could not find requests container")
            return []
        
        active_requests = []
        last_request_count = 0
        scroll_attempts = 0
        max_scroll_attempts = 100  # Prevent infinite scrolling
        
        while True:
            # Find all request items
            request_elements = requests_container.find_elements(By.CSS_SELECTOR, ".request")
            debug_print(f"Found {len(request_elements)} total request elements")
            
            # Process new request elements
            for i in range(last_request_count, len(request_elements)):
                # If we have a limit and reached it, stop processing
                if limit is not None and limit > 0 and len(active_requests) >= limit:
                    debug_print(f"Reached target limit of {limit} valid requests")
                    break
                    
                request_element = request_elements[i]
                
                try:
                    request_data = {
                        'index': len(active_requests) + 1,
                        'title': '',
                        'authors': '',
                        'journal': '',
                        'year': '',
                        'doi': '',
                        'reward': '',
                        'time_left': '',
                        'requester': '',
                        'link': ''
                    }
                    
                    # Get title and link
                    try:
                        title_element = request_element.find_element(By.CSS_SELECTOR, ".title a")
                        request_data['title'] = title_element.text.strip()
                        request_data['link'] = title_element.get_attribute("href")
                    except:
                        try:
                            title_element = request_element.find_element(By.CSS_SELECTOR, ".title")
                            request_data['title'] = title_element.text.strip()
                        except:
                            pass
                    
                    # Get authors
                    try:
                        authors_element = request_element.find_element(By.CSS_SELECTOR, ".authors")
                        request_data['authors'] = authors_element.text.strip()
                    except:
                        pass
                    
                    # Get journal and year
                    try:
                        journal_element = request_element.find_element(By.CSS_SELECTOR, ".journal")
                        request_data['journal'] = journal_element.text.strip()
                    except:
                        pass
                    
                    try:
                        year_element = request_element.find_element(By.CSS_SELECTOR, ".year")
                        request_data['year'] = year_element.text.strip()
                    except:
                        pass
                    
                    # Get DOI
                    try:
                        doi_element = request_element.find_element(By.CSS_SELECTOR, ".doi")
                        request_data['doi'] = doi_element.text.strip()
                    except:
                        pass
                    
                    # Get reward
                    try:
                        reward_element = request_element.find_element(By.CSS_SELECTOR, ".reward")
                        request_data['reward'] = reward_element.text.strip()
                    except:
                        pass
                    
                    # Get time left
                    try:
                        time_element = request_element.find_element(By.CSS_SELECTOR, ".time")
                        request_data['time_left'] = time_element.text.strip()
                    except:
                        pass
                    
                    # Get requester from the user block
                    try:
                        user_block = request_element.find_element(By.CSS_SELECTOR, ".block.user")
                        avatar_link = user_block.find_element(By.CSS_SELECTOR, ".avatar a")
                        href = avatar_link.get_attribute("href")
                        # Extract username from href (format: "/@username")
                        if href and href.startswith("/@"):
                            request_data['requester'] = href[2:]  # Remove "/@" prefix
                        else:
                            # Fallback to img title attribute
                            img_element = avatar_link.find_element(By.TAG_NAME, "img")
                            request_data['requester'] = img_element.get_attribute("title")
                    except:
                        pass
                    
                    # Check if the request has meaningful information
                    # Ignore requests with no title, authors, DOI, or journal
                    has_info = any([
                        request_data['title'],
                        request_data['authors'],
                        request_data['doi'],
                        request_data['journal']
                    ])
                    
                    if has_info:
                        active_requests.append(request_data)
                        debug_print(f"Parsed request {len(active_requests)}: {request_data['title'][:50]}...")
                    else:
                        debug_print(f"Ignoring request {i+1}: no meaningful information found")
                    
                except Exception as parse_error:
                    debug_print(f"Error parsing request {i+1}: {str(parse_error)}")
                    continue
            
            # If we have a limit and reached it, stop
            if limit is not None and limit > 0 and len(active_requests) >= limit:
                debug_print(f"Reached target limit of {limit} valid requests")
                break
            
            # Check if we found new requests
            current_request_count = len(request_elements)
            if current_request_count == last_request_count:
                # No new requests found, try scrolling
                scroll_attempts += 1
                if scroll_attempts >= max_scroll_attempts:
                    debug_print(f"Max scroll attempts ({max_scroll_attempts}) reached, stopping")
                    break
                
                debug_print(f"No new requests found, scrolling down (attempt {scroll_attempts})...")
                
                # Scroll to the bottom of the page
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                
                # Wait for potential new content to load
                time.sleep(2)
                
                # Check if new content was loaded
                new_request_elements = requests_container.find_elements(By.CSS_SELECTOR, ".request")
                if len(new_request_elements) == current_request_count:
                    # Still no new requests after scrolling and waiting
                    debug_print("No new requests loaded after scrolling, assuming end of content")
                    break
            else:
                # New requests found, reset scroll attempts and update count
                scroll_attempts = 0
                last_request_count = current_request_count
                debug_print(f"Found {current_request_count - last_request_count} new request elements")
        
        print(f"Successfully parsed {len(active_requests)} active requests (ignored empty results)")
        return active_requests
        
    except Exception as e:
        print(f"Error getting active requests: {str(e)}")
        return []

def format_active_requests(requests):
    """
    Format the active requests list in a user-friendly manner
    """
    if not requests:
        print("\nNo active requests found.")
        return
    
    print(f"\n{'='*80}")
    print(f"ACTIVE REQUESTS ON SCI-NET.XYZ ({len(requests)} total)")
    print(f"{'='*80}")
    
    for i, request in enumerate(requests, 1):
        print(f"\n[{i}] {request['title']}")
        
        # Journal and year on same line if both exist
        journal_year_parts = []
        if request['journal']:
            journal_year_parts.append(request['journal'])
        if request['year']:
            journal_year_parts.append(f"({request['year']})")
        if journal_year_parts:
            print(f"    Journal: {' '.join(journal_year_parts)}")
        
        if request['doi']:
            print(f"    DOI: {request['doi']}")
        
        # Reward and time left on same line
        reward_time_parts = []
        if request['reward']:
            reward_time_parts.append(f"Reward: {request['reward']}")
        if request['time_left']:
            reward_time_parts.append(f"Time left: {request['time_left']}")
        if reward_time_parts:
            print(f"    {' | '.join(reward_time_parts)}")
        
        if request['requester']:
            print(f"    Requested by: @{request['requester']} (https://sci-net.xyz/@{request['requester']})")
        
        if request['link']:
            print(f"    Link: {request['link']}")
        
        # Add separator between requests (but not after the last one)
        if i < len(requests):
            print(f"    {'-'*70}")
    
    print(f"\n{'='*80}")

def login_and_get_active_requests(username, password, headless=False, limit=None):
    """
    Login to sci-net.xyz and get the list of active requests
    Returns a list of active request dictionaries
    
    Args:
        username: Username for login
        password: Password for login
        headless: Whether to run browser in headless mode
        limit: Optional integer to limit the number of requests returned
    """
    driver = login_to_scinet(username, password, headless)
    if not driver:
        return []
    
    try:
        requests = get_active_requests(driver, limit)
        format_active_requests(requests)
        return requests
    finally:
        print("Active requests retrieval completed, closing browser.")
        driver.quit()

def check_fulfilled_requests(driver):
    """
    Check if any of the user's requests have been fulfilled
    Returns a dictionary with fulfillment information
    """
    try:
        print("Checking for fulfilled requests...")
        
        # Navigate to the main page
        driver.get("https://sci-net.xyz")
        
        # Wait for the page to load
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        
        debug_print("Looking for solutions section...")
        
        fulfilled_data = {
            'has_fulfilled_requests': False,
            'fulfilled_count': 0,
            'notice_message': '',
            'solved_papers': [],
            'timestamp': datetime.now().isoformat()
        }
        
        try:
            # Look for the solutions div
            solutions_container = driver.find_element(By.CSS_SELECTOR, ".solutions")
            fulfilled_data['has_fulfilled_requests'] = True
            
            # Get the notice message
            try:
                notice_element = solutions_container.find_element(By.CSS_SELECTOR, ".notice")
                notice_text = notice_element.text.strip()
                fulfilled_data['notice_message'] = notice_text
                
                # Extract count from notice message (e.g., "Your requests (3) have been solved!")
                count_match = re.search(r'\((\d+)\)', notice_text)
                if count_match:
                    fulfilled_data['fulfilled_count'] = int(count_match.group(1))
                
                print(f"Notice: {notice_text}")
                
            except Exception as notice_error:
                debug_print(f"Could not find notice element: {str(notice_error)}")
            
            # Get all solved paper links
            try:
                solved_elements = solutions_container.find_elements(By.CSS_SELECTOR, ".solved")
                
                for solved_element in solved_elements:
                    try:
                        paper_info = {
                            'title': solved_element.text.strip(),
                            'link': solved_element.get_attribute("href"),
                            'doi': ''
                        }
                        
                        # Extract DOI from href if it follows the pattern /10.xxxx/...
                        href = paper_info['link']
                        if href and '/10.' in href:
                            # Extract DOI from URL (remove leading slash)
                            doi_start = href.find('/10.')
                            if doi_start != -1:
                                paper_info['doi'] = href[doi_start + 1:]  # Remove leading slash
                        
                        fulfilled_data['solved_papers'].append(paper_info)
                        print(f"Solved paper: {paper_info['title']}")
                        if paper_info['doi']:
                            print(f"  DOI: {paper_info['doi']}")
                        if paper_info['link']:
                            print(f"  Link: {paper_info['link']}")
                        
                    except Exception as paper_error:
                        debug_print(f"Error parsing solved paper: {str(paper_error)}")
                        continue
                
                # Update count if we didn't get it from notice
                if fulfilled_data['fulfilled_count'] == 0:
                    fulfilled_data['fulfilled_count'] = len(fulfilled_data['solved_papers'])
                
            except Exception as solved_error:
                debug_print(f"Could not find solved elements: {str(solved_error)}")
            
        except:
            # This is normal - no fulfilled requests, solutions container doesn't exist
            debug_print("No solutions container found - no fulfilled requests available")
        
        if fulfilled_data['has_fulfilled_requests']:
            print(f"Found {fulfilled_data['fulfilled_count']} fulfilled request(s)")
        else:
            print("No fulfilled requests found")
        
        return fulfilled_data
        
    except Exception as e:
        print(f"Error checking fulfilled requests: {str(e)}")
        return {
            'has_fulfilled_requests': False,
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }

def format_fulfilled_requests(fulfilled_data):
    """
    Format the fulfilled requests data in a user-friendly manner
    """
    if not fulfilled_data or not fulfilled_data.get('has_fulfilled_requests'):
        print("\nNo fulfilled requests found.")
        return
    
    print(f"\n{'='*80}")
    print(f"FULFILLED REQUESTS ON SCI-NET.XYZ")
    print(f"{'='*80}")
    
    if fulfilled_data.get('notice_message'):
        print(f"\n🎉 {fulfilled_data['notice_message']}")
    
    solved_papers = fulfilled_data.get('solved_papers', [])
    if solved_papers:
        print(f"\nYour {len(solved_papers)} solved paper(s):")
        print(f"{'-'*80}")
        
        for i, paper in enumerate(solved_papers, 1):
            print(f"\n[{i}] {paper['title']}")
            
            if paper['doi']:
                print(f"    DOI: {paper['doi']}")
            
            if paper['link']:
                print(f"    Download Link: {paper['link']}")
            
            # Add separator between papers (but not after the last one)
            if i < len(solved_papers):
                print(f"    {'-'*70}")
    
    print(f"\n{'='*80}")
    print(f"Total fulfilled requests: {fulfilled_data.get('fulfilled_count', 0)}")
    print(f"Checked on: {fulfilled_data.get('timestamp', 'Unknown')}")
    print(f"{'='*80}")

def login_and_check_fulfilled_requests(username, password, headless=False):
    """
    Login to sci-net.xyz and check for fulfilled requests
    Returns fulfillment information
    """
    driver = login_to_scinet(username, password, headless)
    if not driver:
        return None
    
    try:
        result = check_fulfilled_requests(driver)
        format_fulfilled_requests(result)
        
        # If there are fulfilled requests, download the PDFs
        if result and result.get('has_fulfilled_requests') and result.get('solved_papers'):
            print("\nDownloading PDFs for fulfilled requests...")
            
            # Use the default download directory
            downloads_dir = DEFAULT_DOWNLOAD_DIR
            print(f"Download directory: {downloads_dir}")
            
            for i, paper in enumerate(result['solved_papers'], 1):
                try:
                    if paper.get('link'):
                        print(f"\n[{i}] Processing: {paper['title']}")
                        print(f"    Navigating to: {paper['link']}")
                        
                        # Navigate to the paper page
                        driver.get(paper['link'])

                        # Try to find and click the "View" button on the paper page
                        try:
                            print("    Looking for View button in preview section...")
                            # First try to find the view link in the preview div
                            preview_div = WebDriverWait(driver, 10).until(
                                EC.presence_of_element_located((By.CSS_SELECTOR, "div.preview"))
                            )
                            try:
                                view_link = preview_div.find_element(By.CSS_SELECTOR, "a.button.green")
                            except:
                                view_link = preview_div.find_element(By.CSS_SELECTOR, "a.button")
                            print("    Found View link, clicking...")
                            view_link.click()
                            time.sleep(3)  # Wait for the PDF to load
                        except:
                            print("    View button not found in preview section, proceeding to look for PDF...")
                        
                        # Wait for a few seconds before parsing the page
                        print("    Waiting for page to load...")
                        time.sleep(5)
                        
                        print("    Looking for PDF Link...")
                        # Look for the PDF div and iframe with increased timeout and error handling
                        try:
                            pdf_div = WebDriverWait(driver, 30).until(
                                EC.presence_of_element_located((By.CSS_SELECTOR, "div.pdf"))
                            )
                            
                            # Try to find iframe first
                            iframe_src = None
                            try:
                                pdf_iframe = pdf_div.find_element(By.TAG_NAME, "iframe")
                                iframe_src = pdf_iframe.get_attribute("src")
                            except:
                                debug_print("    No iframe found in PDF div, trying alternative methods...")
                                
                                # Try to find direct PDF link or embed element
                                try:
                                    # Look for embed element
                                    embed_element = pdf_div.find_element(By.TAG_NAME, "embed")
                                    iframe_src = embed_element.get_attribute("src")
                                    debug_print("    Found embed element with PDF URL")
                                except:
                                    # Look for object element
                                    try:
                                        object_element = pdf_div.find_element(By.TAG_NAME, "object")
                                        iframe_src = object_element.get_attribute("data")
                                        debug_print("    Found object element with PDF URL")
                                    except:
                                        # Look for direct link (a tag)
                                        try:
                                            link_element = pdf_div.find_element(By.TAG_NAME, "a")
                                            iframe_src = link_element.get_attribute("href")
                                            debug_print("    Found direct link to PDF")
                                        except:
                                            debug_print("    No PDF source found in div.pdf")
                            
                            # Extract the PDF URL from the found source
                            
                            if iframe_src:
                                debug_print(f"    Raw iframe src: {iframe_src}")
                                
                                # Process the URL to handle the sci-net.xyz PDF format
                                if iframe_src.startswith("//pdf.sci-net.xyz/"):
                                    # Add https: protocol
                                    pdf_url = "https:" + iframe_src
                                elif iframe_src.startswith("/"):
                                    # Handle relative paths - could be to pdf.sci-net.xyz
                                    if iframe_src.startswith("/pdf/") or "/pdf/" in iframe_src:
                                        # This is likely a PDF path, use pdf.sci-net.xyz domain
                                        pdf_url = "https://pdf.sci-net.xyz" + iframe_src
                                    else:
                                        pdf_url = "https://sci-net.xyz" + iframe_src
                                elif iframe_src.startswith("https://pdf.sci-net.xyz/"):
                                    # Already a complete PDF URL
                                    pdf_url = iframe_src
                                else:
                                    pdf_url = iframe_src
                                
                                # Remove query parameters (everything from ? onwards)
                                if "?" in pdf_url:
                                    pdf_url = pdf_url.split("?")[0]
                                
                                # Remove URL fragments (everything from # onwards)
                                if "#" in pdf_url:
                                    pdf_url = pdf_url.split("#")[0]
                                
                                print(f"    Processed PDF URL: {pdf_url}")
                                
                                # Create a safe filename from the paper title
                                safe_title = re.sub(r'[<>:"/\\|?*]', '_', paper['title'])
                                safe_title = safe_title[:100]  # Limit filename length
                                filename = f"{safe_title}.pdf"
                                filepath = os.path.join(downloads_dir, filename)
                                
                                print(f"    Downloading PDF to: {filepath}")
                                
                                # Download the PDF using Python requests
                                try:
                                    # Get cookies from the current driver session
                                    cookies = {}
                                    for cookie in driver.get_cookies():
                                        cookies[cookie['name']] = cookie['value']
                                    
                                    # Set up headers to mimic browser request
                                    headers = {
                                        'User-Agent': driver.execute_script("return navigator.userAgent;"),
                                        'Accept': 'application/pdf,*/*',
                                        'Referer': driver.current_url
                                    }
                                    
                                    # Make the request to download PDF
                                    response = requests.get(pdf_url, headers=headers, cookies=cookies, stream=True, timeout=30)
                                    response.raise_for_status()
                                    
                                    # Save the PDF content to file
                                    with open(filepath, 'wb') as f:
                                        for chunk in response.iter_content(chunk_size=8192):
                                            if chunk:
                                                f.write(chunk)
                                    
                                    file_size = os.path.getsize(filepath)
                                    print(f"    ✓ PDF downloaded successfully: {filepath}")
                                    print(f"    File size: {file_size} bytes")
                                    
                                except Exception as download_error:
                                    print(f"    Error downloading PDF: {str(download_error)}")
                            else:
                                print(f"    Warning: Could not extract PDF URL from iframe")
                                
                        except TimeoutException:
                            print(f"    Warning: Could not find PDF div/iframe for {paper['title']}")
                        except Exception as pdf_error:
                            print(f"    Error finding PDF div/iframe: {str(pdf_error)}")
                            
                except Exception as paper_error:
                    print(f"    Error processing paper {i}: {str(paper_error)}")
                    continue
            
            print(f"\nDownload process completed. Check {downloads_dir} for downloaded files.")
        
        return result
    finally:
        print("Fulfilled requests check completed, closing browser.")
        driver.quit()

def accept_fulfilled_request_by_doi(driver, doi):
    """
    Accept a single fulfilled request by DOI
    
    Args:
        driver: Selenium WebDriver instance
        doi: DOI of the fulfilled request to accept
    
    Returns:
        dict: Result of the acceptance attempt
    """
    try:
        print(f"Accepting fulfilled request for DOI: {doi}")
        
        result = {
            'doi': doi,
            'success': False,
            'error': None,
            'view_clicked': False,
            'accept_clicked': False,
            'request_url': ''
        }
        
        # Navigate to the DOI page
        doi_url = f"https://sci-net.xyz/{doi}"
        result['request_url'] = doi_url
        
        print(f"Navigating to: {doi_url}")
        driver.get(doi_url)
        
        # Wait for the page to load
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        
        # Try to find and click the "View" button on the paper page
        try:
            print("Looking for View button in preview section...")
            preview_div = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div.preview"))
            )
            try:
                view_link = preview_div.find_element(By.CSS_SELECTOR, "a.button.green")
            except:
                view_link = preview_div.find_element(By.CSS_SELECTOR, "a.button")
            print("Found View link, clicking...")
            view_link.click()
            result['view_clicked'] = True
            
            # Wait for the page to load
            print("Waiting for page to load...")
            time.sleep(5)
        except Exception as view_error:
            print(f"Warning: Could not find or click View button: {str(view_error)}")
            debug_print(f"View button error: {str(view_error)}")
        
        # Look for the Accept button in the .buttons div
        try:
            print("Looking for Accept button in buttons div...")
            
            # Find the buttons div
            buttons_div = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div.buttons"))
            )
            
            # Look for the accept link within the buttons div
            accept_link = buttons_div.find_element(By.CSS_SELECTOR, "a.accept")
            
            print("Found Accept link, clicking...")
            debug_print(f"Accept link href: {accept_link.get_attribute('href')}")
            debug_print(f"Accept link text: '{accept_link.text}'")
            
            # Scroll to the button to ensure it's visible
            driver.execute_script("arguments[0].scrollIntoView(true);", accept_link)
            time.sleep(1)
            
            # Click the accept link
            accept_link.click()
            result['accept_clicked'] = True
            
            print("Accept link clicked, waiting for processing...")
            time.sleep(5)
            
            result['success'] = True
            print("✓ Request accepted successfully")
                
        except Exception as accept_error:
            error_msg = f"Error finding/clicking Accept button: {str(accept_error)}"
            print(f"Error: {error_msg}")
            result['error'] = error_msg
            debug_print(f"Accept button error: {str(accept_error)}")
            
            # Debug: Try to find and log available buttons
            if VERBOSE:
                try:
                    buttons_div = driver.find_element(By.CSS_SELECTOR, "div.buttons")
                    all_links = buttons_div.find_elements(By.TAG_NAME, "a")
                    print("Debug: Available links in buttons div:")
                    for i, link in enumerate(all_links):
                        try:
                            print(f"  {i+1}. class: '{link.get_attribute('class')}', text: '{link.text}', href: '{link.get_attribute('href')}'")
                        except:
                            pass
                except:
                    print("Debug: Could not find buttons div for debugging")
        
        return result
        
    except Exception as e:
        error_msg = f"Error accepting fulfilled request by DOI: {str(e)}"
        print(f"Error: {error_msg}")
        return {
            'doi': doi,
            'success': False,
            'error': error_msg,
            'view_clicked': False,
            'accept_clicked': False,
            'request_url': f"https://sci-net.xyz/{doi}"
        }

def login_and_accept_fulfilled_request_by_doi(username, password, doi, headless=False):
    """
    Login to sci-net.xyz and accept a specific fulfilled request by DOI
    
    Args:
        username: Username for login
        password: Password for login
        doi: DOI of the fulfilled request to accept
        headless: Whether to run browser in headless mode
    
    Returns:
        dict: Result of the acceptance attempt
    """
    driver = login_to_scinet(username, password, headless)
    if not driver:
        return None
    
    try:
        result = accept_fulfilled_request_by_doi(driver, doi)
        return result
    finally:
        print("Accept fulfilled request by DOI process completed, closing browser.")
        driver.quit()

def accept_fulfilled_request(driver, paper):
    """
    Accept a single fulfilled request by DOI
    
    Args:
        driver: Selenium WebDriver instance
        paper: Dictionary containing paper information with 'doi' and other details
    
    Returns:
        dict: Result of the acceptance attempt
    """
    try:
        title = paper.get('title', 'Unknown')
        doi = paper.get('doi', '')
        
        print(f"\nProcessing: {title}")
        
        if not doi:
            error_msg = 'No DOI found for this request'
            print(f"Error: {error_msg}")
            return {
                'title': title,
                'link': paper.get('link', ''),
                'success': False,
                'error': error_msg,
                'view_clicked': False,
                'accept_clicked': False
            }
        
        print(f"DOI: {doi}")
        print("Using DOI-based acceptance method...")
        
        # Use the DOI-based acceptance method
        result = accept_fulfilled_request_by_doi(driver, doi)
        
        # Update the result to include the original paper data
        result['title'] = title
        result['link'] = paper.get('link', '')
        
        return result
        
    except Exception as e:
        error_msg = f"Error accepting fulfilled request: {str(e)}"
        print(f"Error: {error_msg}")
        return {
            'title': paper.get('title', 'Unknown'),
            'link': paper.get('link', ''),
            'success': False,
            'error': error_msg,
            'view_clicked': False,
            'accept_clicked': False
        }

def select_requests_to_accept(fulfilled_requests, no_confirm=False):
    """
    Allow user to select which fulfilled requests to accept
    
    Args:
        fulfilled_requests: List of fulfilled request dictionaries
        no_confirm: If True, automatically accept all requests without user confirmation
    
    Returns:
        list: Selected requests to accept
    """
    if not fulfilled_requests:
        print("No fulfilled requests available to accept.")
        return []
    
    # If no_confirm is True, automatically accept all requests
    if no_confirm:
        print(f"Auto-accepting all {len(fulfilled_requests)} fulfilled request(s) (--noconfirm specified)")
        return fulfilled_requests.copy()
    
    def timeout_handler(signum, frame):
        print("\nTimeout: No input received within 30 seconds. Quitting.")
        exit(1)
    
    print(f"\nYou have {len(fulfilled_requests)} fulfilled request(s) available:")
    print("-" * 60)
    
    for i, paper in enumerate(fulfilled_requests, 1):
        print(f"[{i}] {paper['title']}")
        if paper.get('doi'):
            print(f"    DOI: {paper['doi']}")
    
    print("-" * 60)
    
    while True:
        try:
            print("\nOptions:")
            print("- Enter numbers separated by commas (e.g., 1,3,5) to select specific requests")
            print("- Enter 'all' or 'a' to accept all requests")
            print("- Enter 'none' or 'n' to accept no requests")
            
            # Set up timeout signal (only on Unix-like systems)
            if hasattr(signal, 'SIGALRM'):
                signal.signal(signal.SIGALRM, timeout_handler)
                signal.alarm(30)  # 30 second timeout
            
            user_input = input("\nWhich requests would you like to accept? ").strip().lower()
            
            # Cancel the alarm (only on Unix-like systems)
            if hasattr(signal, 'alarm'):
                signal.alarm(0)
            
            if user_input in ['none', 'n', '']:
                print("No requests selected for acceptance.")
                return []
            
            if user_input in ['all', 'a']:
                print(f"All {len(fulfilled_requests)} requests selected for acceptance.")
                return fulfilled_requests.copy()
            
            # Parse comma-separated numbers
            selected_indices = []
            for part in user_input.split(','):
                try:
                    index = int(part.strip())
                    if 1 <= index <= len(fulfilled_requests):
                        selected_indices.append(index - 1)  # Convert to 0-based index
                    else:
                        print(f"Warning: Index {index} is out of range (1-{len(fulfilled_requests)})")
                except ValueError:
                    print(f"Warning: '{part.strip()}' is not a valid number")
            
            if not selected_indices:
                print("No valid selections made. Please try again.")
                continue
            
            # Remove duplicates and sort
            selected_indices = sorted(list(set(selected_indices)))
            selected_requests = [fulfilled_requests[i] for i in selected_indices]
            
            print(f"\nSelected {len(selected_requests)} request(s) for acceptance:")
            for i, paper in enumerate(selected_requests, 1):
                print(f"  {i}. {paper['title']}")
            
            # Set up timeout for confirmation (only on Unix-like systems)
            if hasattr(signal, 'SIGALRM'):
                signal.signal(signal.SIGALRM, timeout_handler)
                signal.alarm(30)  # 30 second timeout
            
            confirm = input("\nProceed with accepting these requests? (y/n): ").strip().lower()
            
            # Cancel the alarm (only on Unix-like systems)
            if hasattr(signal, 'alarm'):
                signal.alarm(0)
            
            if confirm in ['y', 'yes']:
                return selected_requests
            else:
                print("Selection cancelled. Please choose again.")
                continue
                
        except KeyboardInterrupt:
            if hasattr(signal, 'alarm'):
                signal.alarm(0)  # Cancel alarm
            print("\n\nOperation cancelled by user.")
            return []
        except Exception as e:
            if hasattr(signal, 'alarm'):
                signal.alarm(0)  # Cancel alarm
            print(f"Error in selection: {str(e)}. Please try again.")
            continue
        finally:
            # Make sure alarm is always cancelled (only on Unix-like systems)
            if hasattr(signal, 'alarm'):
                signal.alarm(0)

def login_and_accept_fulfilled_requests(username, password, headless=False, no_confirm=False):
    """
    Login to sci-net.xyz, check for fulfilled requests, allow user to select which ones to accept,
    and then accept the selected requests
    
    Args:
        username: Username for login
        password: Password for login  
        headless: Whether to run browser in headless mode
        no_confirm: If True, automatically accept all requests without user confirmation
    
    Returns:
        dict: Summary of acceptance results
    """
    driver = login_to_scinet(username, password, headless)
    if not driver:
        return None
    
    try:
        # First, check for fulfilled requests
        fulfilled_data = check_fulfilled_requests(driver)
        
        if not fulfilled_data or not fulfilled_data.get('has_fulfilled_requests'):
            print("\nNo fulfilled requests found to accept.")
            return {
                'has_fulfilled_requests': False,
                'total_requests': 0,
                'selected_requests': 0,
                'accepted_requests': 0,
                'failed_requests': 0,
                'results': []
            }
        
        # Display fulfilled requests
        format_fulfilled_requests(fulfilled_data)
        
        solved_papers = fulfilled_data.get('solved_papers', [])
        
        # If no_confirm is True, accept all requests automatically
        if no_confirm:
            print("\nAuto-accepting all fulfilled requests (--noconfirm specified)...")
            selected_requests = solved_papers.copy()
        elif headless:
            # In headless mode without no_confirm, we cannot interact with user
            print("\nRunning in headless mode - cannot select requests interactively.")
            print("Use --noconfirm to automatically accept all requests in headless mode.")
            return {
                'has_fulfilled_requests': True,
                'total_requests': len(solved_papers),
                'selected_requests': 0,
                'accepted_requests': 0,
                'failed_requests': 0,
                'error': 'Cannot select requests interactively in headless mode without --noconfirm',
                'results': []
            }
        else:
            # Let user select which requests to accept
            selected_requests = select_requests_to_accept(solved_papers, no_confirm)
        
        if not selected_requests:
            print("\nNo requests selected for acceptance.")
            return {
                'has_fulfilled_requests': True,
                'total_requests': len(solved_papers),
                'selected_requests': 0,
                'accepted_requests': 0,
                'failed_requests': 0,
                'results': []
            }
        
        # Process each selected request
        print(f"\nProcessing {len(selected_requests)} selected request(s)...")
        results = []
        successful_accepts = 0
        failed_accepts = 0
        
        for i, paper in enumerate(selected_requests, 1):
            print(f"\n--- Processing request {i}/{len(selected_requests)} ---")
            result = accept_fulfilled_request(driver, paper)
            results.append(result)
            
            if result['success']:
                successful_accepts += 1
            else:
                failed_accepts += 1
            
            # Small delay between requests
            if i < len(selected_requests):
                time.sleep(2)
        
        # Summary
        summary = {
            'has_fulfilled_requests': True,
            'total_requests': len(solved_papers),
            'selected_requests': len(selected_requests),
            'accepted_requests': successful_accepts,
            'failed_requests': failed_accepts,
            'results': results,
            'timestamp': datetime.now().isoformat()
        }
        
        print(f"\n{'='*80}")
        print(f"ACCEPTANCE SUMMARY")
        print(f"{'='*80}")
        print(f"Total fulfilled requests: {summary['total_requests']}")
        print(f"Selected for acceptance: {summary['selected_requests']}")
        print(f"Successfully accepted: {summary['accepted_requests']}")
        print(f"Failed to accept: {summary['failed_requests']}")
        
        if failed_accepts > 0:
            print(f"\nFailed requests:")
            for result in results:
                if not result['success']:
                    print(f"  - {result['title']}")
                    if result['error']:
                        print(f"    Error: {result['error']}")
        
        if successful_accepts > 0:
            print(f"\nSuccessfully accepted requests:")
            for result in results:
                if result['success']:
                    print(f"  ✓ {result['title']}")
        
        print(f"{'='*80}")
        
        return summary
        
    finally:
        print("Accept fulfilled requests process completed, closing browser.")
        driver.quit()

def reject_fulfilled_request_by_doi(driver, doi, reject_message="Paper quality does not meet requirements"):
    """
    Reject a single fulfilled request by DOI
    
    Args:
        driver: Selenium WebDriver instance
        doi: DOI of the fulfilled request to reject
        reject_message: Message to include when rejecting the paper
    
    Returns:
        dict: Result of the rejection attempt
    """
    try:
        print(f"Rejecting fulfilled request for DOI: {doi}")
        
        result = {
            'doi': doi,
            'success': False,
            'error': None,
            'view_clicked': False,
            'reject_clicked': False,
            'reject_message': reject_message,
            'request_url': ''
        }
        
        # Navigate to the DOI page
        doi_url = f"https://sci-net.xyz/{doi}"
        result['request_url'] = doi_url
        
        print(f"Navigating to: {doi_url}")
        driver.get(doi_url)
        
        # Wait for the page to load
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        
        # Try to find and click the "View" button on the paper page
        try:
            print("Looking for View button in preview section...")
            preview_div = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div.preview"))
            )
            try:
                view_link = preview_div.find_element(By.CSS_SELECTOR, "a.button.green")
            except:
                view_link = preview_div.find_element(By.CSS_SELECTOR, "a.button")
            print("Found View link, clicking...")
            view_link.click()
            result['view_clicked'] = True
            
            # Wait for the page to load
            print("Waiting for page to load...")
            time.sleep(5)
        except Exception as view_error:
            print(f"Warning: Could not find or click View button: {str(view_error)}")
            debug_print(f"View button error: {str(view_error)}")
        
        # Look for the Report button
        try:
            print("Looking for Report problem button...")
            
            # Find the report link with class "problem" and onclick "problem()"
            report_link = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "a.problem[onclick='problem()']"))
            )
            
            print("Found Report problem link, clicking...")
            debug_print(f"Report link text: '{report_link.text}'")
            debug_print(f"Report link onclick: {report_link.get_attribute('onclick')}")
            
            # Scroll to the link to ensure it's visible
            driver.execute_script("arguments[0].scrollIntoView(true);", report_link)
            time.sleep(1)
            
            # Click the report link
            report_link.click()
            result['reject_clicked'] = True
            
            print("Report link clicked, waiting for message interface...")
            time.sleep(3)
            
            # Handle the report message input
            if not _handle_report_message_input(driver, reject_message):
                print("Warning: Could not enter rejection message through standard inputs")
                _handle_javascript_prompt(driver, reject_message)
            
            result['success'] = True
            print("✓ Request rejected successfully")
            
        except Exception as reject_error:
            error_msg = f"Error finding/clicking Report button: {str(reject_error)}"
            print(f"Error: {error_msg}")
            result['error'] = error_msg
            debug_print(f"Report button error: {str(reject_error)}")
            
            # Debug information
            if VERBOSE:
                _log_debug_info(driver)
        
        return result
        
    except Exception as e:
        error_msg = f"Error rejecting fulfilled request by DOI: {str(e)}"
        print(f"Error: {error_msg}")
        return {
            'doi': doi,
            'success': False,
            'error': error_msg,
            'view_clicked': False,
            'reject_clicked': False,
            'reject_message': reject_message,
            'request_url': f"https://sci-net.xyz/{doi}"
        }

def login_and_reject_fulfilled_request_by_doi(username, password, doi, reject_message="Paper quality does not meet requirements", headless=False):
    """
    Login to sci-net.xyz and reject a specific fulfilled request by DOI
    
    Args:
        username: Username for login
        password: Password for login
        doi: DOI of the fulfilled request to reject
        reject_message: Message to include when rejecting the paper
        headless: Whether to run browser in headless mode
    
    Returns:
        dict: Result of the rejection attempt
    """
    driver = login_to_scinet(username, password, headless)
    if not driver:
        return None
    
    try:
        result = reject_fulfilled_request_by_doi(driver, doi, reject_message)
        return result
    finally:
        print("Reject fulfilled request by DOI process completed, closing browser.")
        driver.quit()

def reject_fulfilled_request(driver, paper, reject_message="Paper quality does not meet requirements"):
    """
    Reject a single fulfilled request by DOI
    
    Args:
        driver: Selenium WebDriver instance
        paper: Dictionary containing paper information with 'doi' and other details
        reject_message: Message to include when rejecting the paper
    
    Returns:
        dict: Result of the rejection attempt
    """
    try:
        title = paper.get('title', 'Unknown')
        doi = paper.get('doi', '')
        
        print(f"\nProcessing: {title}")
        
        if not doi:
            error_msg = 'No DOI found for this request'
            print(f"Error: {error_msg}")
            return {
                'title': title,
                'link': paper.get('link', ''),
                'success': False,
                'error': error_msg,
                'view_clicked': False,
                'reject_clicked': False,
                'reject_message': reject_message
            }
        
        print(f"DOI: {doi}")
        print("Using DOI-based rejection method...")
        
        # Use the DOI-based rejection method
        result = reject_fulfilled_request_by_doi(driver, doi, reject_message)
        
        # Update the result to include the original paper data
        result['title'] = title
        result['link'] = paper.get('link', '')
        
        return result
        
    except Exception as e:
        error_msg = f"Error rejecting fulfilled request: {str(e)}"
        print(f"Error: {error_msg}")
        return {
            'title': paper.get('title', 'Unknown'),
            'link': paper.get('link', ''),
            'success': False,
            'error': error_msg,
            'view_clicked': False,
            'reject_clicked': False,
            'reject_message': reject_message
        }

def _handle_report_message_input(driver, reject_message):
    """
    Handle entering the rejection message into various input types
    
    Returns:
        bool: True if message was successfully entered, False otherwise
    """
    try:
        print("Looking for report message input box...")
        
        # Try different input selectors in order of preference
        input_selectors = [
            "textarea",
            "input[type='text']", 
            "input[placeholder*='message']",
            "input[placeholder*='reason']",
            "input"
        ]
        
        message_input = None
        for selector in input_selectors:
            try:
                message_input = WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                )
                print(f"Found input using selector: {selector}")
                break
            except TimeoutException:
                continue
        
        if not message_input:
            return False
        
        print("Entering rejection message...")
        message_input.clear()
        message_input.send_keys(reject_message)
        
        print("Looking for submit mechanism...")
        return _submit_report_message(driver, message_input)
        
    except Exception as e:
        debug_print(f"Error handling message input: {str(e)}")
        return False

def _submit_report_message(driver, message_input):
    """
    Submit the report message using various methods
    
    Returns:
        bool: True if submission was attempted, False otherwise
    """
    try:
        # Try to find and click submit button
        submit_selectors = [
            "button[type='submit']",
            "input[type='submit']", 
            "button:contains('Submit')",
            "button:contains('Send')",
            "button"
        ]
        
        for selector in submit_selectors:
            try:
                submit_button = driver.find_element(By.CSS_SELECTOR, selector)
                print(f"Found submit button using selector: {selector}")
                submit_button.click()
                print("Submit button clicked")
                time.sleep(5)
                return True
            except:
                continue
        
        # If no submit button found, try pressing Enter
        print("No submit button found, pressing Enter...")
        message_input.send_keys(Keys.RETURN)
        time.sleep(5)
        return True
        
    except Exception as e:
        debug_print(f"Error submitting message: {str(e)}")
        return False

def _handle_javascript_prompt(driver, reject_message):
    """
    Handle JavaScript prompt/alert for rejection message
    """
    try:
        print("Checking for JavaScript prompt...")
        alert = driver.switch_to.alert
        print("Found JavaScript prompt, entering message...")
        alert.send_keys(reject_message)
        alert.accept()
        print("JavaScript prompt handled successfully")
        time.sleep(3)
    except Exception as e:
        debug_print(f"No JavaScript prompt found: {str(e)}")

def _log_debug_info(driver):
    """
    Log debug information about available elements
    """
    try:
        # Look for problem-related elements
        problem_links = driver.find_elements(By.CSS_SELECTOR, "a.problem")
        print(f"Debug: Found {len(problem_links)} elements with class 'problem'")
        for i, link in enumerate(problem_links):
            try:
                onclick = link.get_attribute('onclick')
                text = link.text.strip()
                print(f"  {i+1}. onclick: '{onclick}', text: '{text}'")
            except:
                pass
        
        # Look for spans containing report text
        spans = driver.find_elements(By.TAG_NAME, "span")
        report_spans = [span for span in spans if "report" in span.text.lower()]
        print(f"Debug: Found {len(report_spans)} spans containing 'report'")
        for i, span in enumerate(report_spans[:3]):
            try:
                print(f"  {i+1}. text: '{span.text.strip()}'")
            except:
                pass
                
    except Exception as debug_error:
        print(f"Debug: Error during debugging: {str(debug_error)}")

def select_requests_to_reject(fulfilled_requests, no_confirm=False):
    """
    Allow user to select which fulfilled requests to reject
    
    Args:
        fulfilled_requests: List of fulfilled request dictionaries
        no_confirm: If True, automatically reject all requests without user confirmation
    
    Returns:
        tuple: (selected_requests, rejection_message)
    """
    if not fulfilled_requests:
        print("No fulfilled requests available to reject.")
        return [], ""
    
    # If no_confirm is True, automatically reject all requests
    if no_confirm:
        print(f"Auto-rejecting all {len(fulfilled_requests)} fulfilled request(s) (--noconfirm specified)")
        default_message = "Paper quality does not meet requirements"
        return fulfilled_requests.copy(), default_message
    
    def timeout_handler(signum, frame):
        print("\nTimeout: No input received within 30 seconds. Quitting.")
        exit(1)
    
    print(f"\nYou have {len(fulfilled_requests)} fulfilled request(s) available:")
    print("-" * 60)
    
    for i, paper in enumerate(fulfilled_requests, 1):
        print(f"[{i}] {paper['title']}")
        if paper.get('doi'):
            print(f"    DOI: {paper['doi']}")
    
    print("-" * 60)
    
    while True:
        try:
            print("\nOptions:")
            print("- Enter numbers separated by commas (e.g., 1,3,5) to select specific requests")
            print("- Enter 'all' or 'a' to reject all requests")
            print("- Enter 'none' or 'n' to reject no requests")
            
            # Set up timeout signal (only on Unix-like systems)
            if hasattr(signal, 'SIGALRM'):
                signal.signal(signal.SIGALRM, timeout_handler)
                signal.alarm(30)  # 30 second timeout
            
            user_input = input("\nWhich requests would you like to reject? ").strip().lower()
            
            # Cancel the alarm (only on Unix-like systems)
            if hasattr(signal, 'alarm'):
                signal.alarm(0)
            
            if user_input in ['none', 'n', '']:
                print("No requests selected for rejection.")
                return [], ""
            
            if user_input in ['all', 'a']:
                selected_requests = fulfilled_requests.copy()
            else:
                # Parse comma-separated numbers
                selected_indices = []
                for part in user_input.split(','):
                    try:
                        index = int(part.strip())
                        if 1 <= index <= len(fulfilled_requests):
                            selected_indices.append(index - 1)  # Convert to 0-based index
                        else:
                            print(f"Warning: Index {index} is out of range (1-{len(fulfilled_requests)})")
                    except ValueError:
                        print(f"Warning: '{part.strip()}' is not a valid number")
                
                if not selected_indices:
                    print("No valid selections made. Please try again.")
                    continue
                
                # Remove duplicates and sort
                selected_indices = sorted(list(set(selected_indices)))
                selected_requests = [fulfilled_requests[i] for i in selected_indices]
            
            print(f"\nSelected {len(selected_requests)} request(s) for rejection:")
            for i, paper in enumerate(selected_requests, 1):
                print(f"  {i}. {paper['title']}")
            
            # Get rejection message
            print("\nPlease provide a reason for rejecting these requests:")
            print("(Common reasons: 'Paper quality does not meet requirements', 'Wrong paper uploaded', 'PDF is corrupted', etc.)")
            
            # Set up timeout for rejection message input (only on Unix-like systems)
            if hasattr(signal, 'SIGALRM'):
                signal.signal(signal.SIGALRM, timeout_handler)
                signal.alarm(30)  # 30 second timeout
            
            reject_message = input("Rejection reason: ").strip()
            
            # Cancel the alarm (only on Unix-like systems)
            if hasattr(signal, 'alarm'):
                signal.alarm(0)
            
            if not reject_message:
                reject_message = "Paper quality does not meet requirements"
                print(f"Using default message: '{reject_message}'")
            
            print(f"\nRejection message: '{reject_message}'")
            
            # Set up timeout for confirmation (only on Unix-like systems)
            if hasattr(signal, 'SIGALRM'):
                signal.signal(signal.SIGALRM, timeout_handler)
                signal.alarm(30)  # 30 second timeout
            
            confirm = input("\nProceed with rejecting these requests? (y/n): ").strip().lower()
            
            # Cancel the alarm (only on Unix-like systems)
            if hasattr(signal, 'alarm'):
                signal.alarm(0)
            
            if confirm in ['y', 'yes']:
                return selected_requests, reject_message
            else:
                print("Selection cancelled. Please choose again.")
                continue
                
        except KeyboardInterrupt:
            if hasattr(signal, 'alarm'):
                signal.alarm(0)  # Cancel alarm
            print("\n\nOperation cancelled by user.")
            return [], ""
        except Exception as e:
            if hasattr(signal, 'alarm'):
                signal.alarm(0)  # Cancel alarm
            print(f"Error in selection: {str(e)}. Please try again.")
            continue
        finally:
            # Make sure alarm is always cancelled (only on Unix-like systems)
            if hasattr(signal, 'alarm'):
                signal.alarm(0)

def login_and_reject_fulfilled_requests(username, password, headless=False, reject_message=None, no_confirm=False):
    """
    Login to sci-net.xyz, check for fulfilled requests, allow user to select which ones to reject,
    and then reject the selected requests
    
    Args:
        username: Username for login
        password: Password for login  
        headless: Whether to run browser in headless mode
        reject_message: Optional default rejection message
        no_confirm: If True, automatically reject all requests without user confirmation
    
    Returns:
        dict: Summary of rejection results
    """
    driver = login_to_scinet(username, password, headless)
    if not driver:
        return None
    
    try:
        # First, check for fulfilled requests
        fulfilled_data = check_fulfilled_requests(driver)
        
        if not fulfilled_data or not fulfilled_data.get('has_fulfilled_requests'):
            print("\nNo fulfilled requests found to reject.")
            return {
                'has_fulfilled_requests': False,
                'total_requests': 0,
                'selected_requests': 0,
                'rejected_requests': 0,
                'failed_requests': 0,
                'results': []
            }
        
        # Display fulfilled requests
        format_fulfilled_requests(fulfilled_data)
        
        solved_papers = fulfilled_data.get('solved_papers', [])
        
        # If no_confirm is True, reject all requests automatically
        if no_confirm:
            print("\nAuto-rejecting all fulfilled requests (--noconfirm specified)...")
            selected_requests = solved_papers.copy()
            rejection_message = reject_message or "Paper quality does not meet requirements"
        elif headless:
            # In headless mode without no_confirm, we cannot interact with user
            print("\nRunning in headless mode - cannot select requests interactively.")
            print("Use --noconfirm to automatically reject all requests in headless mode.")
            return {
                'has_fulfilled_requests': True,
                'total_requests': len(solved_papers),
                'selected_requests': 0,
                'rejected_requests': 0,
                'failed_requests': 0,
                'error': 'Cannot select requests interactively in headless mode without --noconfirm',
                'results': []
            }
        else:
            # Let user select which requests to reject
            selected_requests, rejection_message = select_requests_to_reject(solved_papers, no_confirm)
        
        if not selected_requests:
            print("\nNo requests selected for rejection.")
            return {
                'has_fulfilled_requests': True,
                'total_requests': len(solved_papers),
                'selected_requests': 0,
                'rejected_requests': 0,
                'failed_requests': 0,
                'results': []
            }
        
        # Process each selected request
        print(f"\nProcessing {len(selected_requests)} selected request(s) for rejection...")
        results = []
        successful_rejects = 0
        failed_rejects = 0
        
        for i, paper in enumerate(selected_requests, 1):
            print(f"\n--- Processing rejection {i}/{len(selected_requests)} ---")
            result = reject_fulfilled_request(driver, paper, rejection_message)
            results.append(result)
            
            if result['success']:
                successful_rejects += 1
            else:
                failed_rejects += 1
            
            # Small delay between requests
            if i < len(selected_requests):
                time.sleep(2)
        
        # Summary
        summary = {
            'has_fulfilled_requests': True,
            'total_requests': len(solved_papers),
            'selected_requests': len(selected_requests),
            'rejected_requests': successful_rejects,
            'failed_requests': failed_rejects,
            'rejection_message': rejection_message,
            'results': results,
            'timestamp': datetime.now().isoformat()
        }
        
        print(f"\n{'='*80}")
        print(f"REJECTION SUMMARY")
        print(f"{'='*80}")
        print(f"Total fulfilled requests: {summary['total_requests']}")
        print(f"Selected for rejection: {summary['selected_requests']}")
        print(f"Successfully rejected: {summary['rejected_requests']}")
        print(f"Failed to reject: {summary['failed_requests']}")
        print(f"Rejection message: '{summary['rejection_message']}'")
        
        if failed_rejects > 0:
            print(f"\nFailed rejections:")
            for result in results:
                if not result['success']:
                    print(f"  - {result['title']}")
                    if result['error']:
                        print(f"    Error: {result['error']}")
        
        if successful_rejects > 0:
            print(f"\nSuccessfully rejected requests:")
            for result in results:
                if result['success']:
                    print(f"  ✓ {result['title']}")
        
        print(f"{'='*80}")
        
        return summary
        
    finally:
        print("Reject fulfilled requests process completed, closing browser.")
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

def solve_request_by_doi(driver, doi, pdf_path):
    """
    Solve a single active request by DOI with a provided PDF path
    
    Args:
        driver: Selenium WebDriver instance
        doi: DOI of the request to solve
        pdf_path: Path to the PDF file to upload as solution
    
    Returns:
        dict: Result of the solving attempt
    """
    try:
        # Create a request_data dictionary similar to what get_active_requests returns
        request_data = {
            'doi': doi,
            'title': f'Request for DOI: {doi}',
            'authors': '',
            'journal': '',
            'year': '',
            'reward': '',
            'time_left': '',
            'requester': '',
            'link': f'https://sci-net.xyz/{doi}'
        }
        
        print(f"\nSolving request by DOI: {doi}")
        print(f"PDF: {os.path.basename(pdf_path)}")
        
        # Check if PDF file exists
        if not os.path.exists(pdf_path):
            return {
                'request': request_data,
                'success': False,
                'error': f'PDF file not found: {pdf_path}',
                'pdf_path': pdf_path,
                'upload_attempted': False,
                'submit_attempted': False
            }
        
        # Navigate to the DOI-specific page
        doi_url = f"https://sci-net.xyz/{doi}"
        print(f"Navigating to: {doi_url}")
        driver.get(doi_url)
        
        # Wait for the page to load
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        
        result = {
            'request': request_data,
            'success': False,
            'error': None,
            'pdf_path': pdf_path,
            'doi_url': doi_url,
            'upload_attempted': False,
            'submit_attempted': False
        }
        
        # Check if we're on the correct DOI page and if upload is possible
        current_url = driver.current_url
        debug_print(f"Current URL after navigation: {current_url}")
        
        # Look for upload elements or existing solutions
        try:
            # Check if there's already a solution posted
            existing_solution = driver.find_elements(By.CSS_SELECTOR, ".solved, .solution")
            if existing_solution:
                print("Notice: This request appears to already have a solution posted")
                result['error'] = 'Request already has a solution'
                return result
            
            # Look for the respond block containing the upload button
            debug_print("Looking for respond block with upload button...")
            respond_block = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div.respond.block"))
            )
            debug_print("Respond block found")
            
            # Find the upload button within the respond block
            debug_print("Looking for upload button...")
            upload_button = respond_block.find_element(By.CSS_SELECTOR, "a.button[onclick*='upload']")
            debug_print(f"Upload button found with onclick: {upload_button.get_attribute('onclick')}")
            
            # Create file input for upload (hidden)
            debug_print("Creating file input for upload...")
            driver.execute_script("""
                var input = document.createElement('input');
                input.type = 'file';
                input.accept = '.pdf';
                input.multiple = false;
                input.style.position = 'absolute';
                input.style.left = '-9999px';
                input.id = 'selenium-solve-doi-input';
                document.body.appendChild(input);
            """)
            
            file_input = driver.find_element(By.ID, "selenium-solve-doi-input")
            
            # Upload the PDF file
            debug_print("Uploading PDF file...")
            abs_path = os.path.abspath(pdf_path)
            file_input.send_keys(abs_path)
            result['upload_attempted'] = True
            
            # Click the upload button to initiate the upload process
            debug_print("Clicking upload button...")
            driver.execute_script("arguments[0].scrollIntoView(true);", upload_button)
            time.sleep(1)
            upload_button.click()
            
            # Wait a moment for the upload interface to appear, then trigger upload
            time.sleep(3)
            
            # Trigger the upload using JavaScript with the file from our input
            debug_print("Triggering upload via JavaScript...")
            js_result = driver.execute_script("""
                var input = document.getElementById('selenium-solve-doi-input');
                var files = input.files;
                console.log('Files found:', files.length);
                
                if (files.length > 0) {
                    var file = files[0];
                    console.log('Processing file:', file.name, 'size:', file.size);
                    
                    // Check if uploads object exists
                    if (typeof uploads === 'undefined') {
                        window.uploads = {};
                    }
                    
                    // Check if article class exists and create upload
                    if (typeof article !== 'undefined') {
                        if (!(file.name in uploads)) {
                            console.log('Starting upload for:', file.name);
                            var articleInstance = new article(file);
                            articleInstance.upload();
                            return 'Upload initiated for ' + file.name;
                        } else {
                            return 'File already in uploads: ' + file.name;
                        }
                    } else {
                        // Alternative method: try to find and use existing file input
                        var existingInputs = document.querySelectorAll('input[type="file"]');
                        for (var i = 0; i < existingInputs.length; i++) {
                            if (existingInputs[i] !== input) {
                                existingInputs[i].files = files;
                                var event = new Event('change', { bubbles: true });
                                existingInputs[i].dispatchEvent(event);
                                return 'Triggered change event on existing file input';
                            }
                        }
                        return 'No upload mechanism found';
                    }
                } else {
                    return 'No files found in input';
                }
            """)
            debug_print(f"JavaScript execution result: {js_result}")
            
            # Calculate wait time based on file size
            file_size_mb = os.path.getsize(pdf_path) / (1024 * 1024)
            wait_time = max(15, min(120, int(file_size_mb * 8)))  # Longer wait for solving
            
            debug_print(f"File size: {file_size_mb:.2f} MB, waiting {wait_time} seconds for upload...")
            print(f"Waiting {wait_time} seconds for upload to complete...")
            time.sleep(wait_time)
            
            # Check for uploaded block to confirm successful upload
            try:
                debug_print("Looking for uploaded block...")
                uploaded_block = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "div.uploaded.block"))
                )
                
                # Get upload details from the uploaded block
                try:
                    name_element = uploaded_block.find_element(By.CSS_SELECTOR, ".name")
                    uploaded_name = name_element.text.strip()
                    print(f"✓ Upload successful: {uploaded_name}")
                except:
                    print("✓ Upload successful (uploaded block detected)")
                
                # Look for submit button in buttons div after successful upload
                try:
                    debug_print("Looking for submit button in buttons div...")
                    buttons_div = WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "div.buttons"))
                    )
                    
                    # Find the submit button (green button with "submit" text or href containing "solve")
                    submit_button = buttons_div.find_element(By.CSS_SELECTOR, "a.button.green")
                    
                    # Verify it's actually a submit button
                    button_text = submit_button.text.strip().lower()
                    button_href = submit_button.get_attribute("href")
                    
                    if "submit" in button_text or (button_href and "solve" in button_href):
                        print("Found submit button, attempting to click...")
                        debug_print(f"Submit button text: '{submit_button.text}'")
                        debug_print(f"Submit button href: '{button_href}'")
                        
                        # Try multiple methods to click the button
                        click_success = False
                        
                        # Method 1: Wait for element to be clickable and then click
                        try:
                            clickable_button = WebDriverWait(driver, 10).until(
                                EC.element_to_be_clickable(submit_button)
                            )
                            clickable_button.click()
                            click_success = True
                            debug_print("Submit button clicked using WebDriverWait clickable method")
                        except Exception as e1:
                            debug_print(f"Method 1 failed: {str(e1)}")
                        
                        # Method 2: JavaScript click if regular click failed
                        if not click_success:
                            try:
                                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", submit_button)
                                time.sleep(1)
                                driver.execute_script("arguments[0].click();", submit_button)
                                click_success = True
                                debug_print("Submit button clicked using JavaScript")
                            except Exception as e2:
                                debug_print(f"Method 2 failed: {str(e2)}")
                        
                        # Method 3: Navigate to href directly if clicking failed
                        if not click_success and button_href:
                            try:
                                driver.get(button_href)
                                click_success = True
                                debug_print("Navigated to submit button href directly")
                            except Exception as e3:
                                debug_print(f"Method 3 failed: {str(e3)}")
                        
                        if click_success:
                            result['submit_attempted'] = True
                            print("Submit button activated, waiting for submission to complete...")
                            time.sleep(5)
                            result['success'] = True
                            print("✓ Request solved and submitted successfully")
                        else:
                            print("Warning: Could not activate submit button, but upload was successful")
                            result['success'] = True
                            result['error'] = 'Upload successful but submit button not interactable'
                    else:
                        print(f"Warning: Found button but doesn't appear to be submit button (text: '{button_text}', href: '{button_href}')")
                        result['success'] = True  # Upload was successful even if submit wasn't found
                        result['error'] = 'Upload successful but submit button not recognized'
                    
                except TimeoutException:
                    print("Warning: Submit button not found after upload")
                    result['success'] = True  # Upload was successful even if submit wasn't found
                    result['error'] = 'Upload successful but submit button not found'
                except Exception as submit_error:
                    print(f"Warning: Error with submit button: {str(submit_error)}")
                    result['success'] = True  # Upload was successful even if submit failed
                    result['error'] = f'Upload successful but submit error: {str(submit_error)}'
                
            except TimeoutException:
                debug_print("Uploaded block not found, checking for other success indicators...")
                
                # Check for success messages as fallback
                try:
                    found_messages = driver.find_elements(By.CSS_SELECTOR, ".found, .success")
                    for msg in found_messages:
                        if msg.is_displayed():
                            message_text = msg.text.strip()
                            if message_text:
                                print(f"Success: {message_text}")
                                result['success'] = True
                    
                    # Check for error messages
                    error_messages = driver.find_elements(By.CSS_SELECTOR, ".error")
                    for error in error_messages:
                        if error.is_displayed():
                            error_text = error.text.strip()
                            if error_text:
                                print(f"Upload Error: {error_text}")
                                result['error'] = error_text
                    
                    # If no explicit success message and no errors, check if upload was attempted
                    if not result['success'] and not result['error']:
                        result['error'] = 'Uploaded block not found after upload - upload may have failed'
                        print(f"Warning: {result['error']}")
                
                except Exception as status_error:
                    debug_print(f"Error checking upload status: {str(status_error)}")
                    result['error'] = f'Upload status unclear: {str(status_error)}'
            
        except TimeoutException:
            result['error'] = 'Respond block or upload button not found - page may not support uploads'
            print(f"Error: {result['error']}")
        except Exception as upload_error:
            result['error'] = f'Upload error: {str(upload_error)}'
            print(f"Error: {result['error']}")
        
        return result
        
    except Exception as e:
        error_msg = f"Error solving request by DOI: {str(e)}"
        print(f"Error: {error_msg}")
        return {
            'request': {'doi': doi, 'title': f'Request for DOI: {doi}'},
            'success': False,
            'error': error_msg,
            'pdf_path': pdf_path,
            'upload_attempted': False,
            'submit_attempted': False
        }

def login_and_solve_request_by_doi(username, password, doi, pdf_path, headless=False):
    """
    Login to sci-net.xyz and solve a specific request by DOI with provided PDF
    
    Args:
        username: Username for login
        password: Password for login
        doi: DOI of the request to solve
        pdf_path: Path to the PDF file to upload as solution
        headless: Whether to run browser in headless mode
    
    Returns:
        dict: Result of the solving attempt
    """
    driver = login_to_scinet(username, password, headless)
    if not driver:
        return None
    
    try:
        result = solve_request_by_doi(driver, doi, pdf_path)
        return result
    finally:
        print("Solve request by DOI process completed, closing browser.")
        driver.quit()


def solve_active_request(driver, request_data):
    """
    Solve a single active request by uploading a PDF for the specified DOI
    
    Args:
        driver: Selenium WebDriver instance
        request_data: Dictionary containing request information with 'doi' and other details
    
    Returns:
        dict: Result of the solving attempt
    """
    try:
        doi = request_data.get('doi', '').strip()
        if not doi:
            return {
                'request': request_data,
                'success': False,
                'error': 'No DOI found in request data',
                'pdf_path': None,
                'upload_attempted': False,
                'submit_attempted': False
            }
        
        title = request_data.get('title', 'Unknown')
        print(f"\nSolving request: {title}")
        print(f"DOI: {doi}")
        
        # Ask user for PDF file path
        print(f"\nPlease provide the PDF file for this request:")
        pdf_path = get_file_path_with_completion("Enter PDF file path: ")
        
        if not pdf_path:
            return {
                'request': request_data,
                'success': False,
                'error': 'No PDF file path provided',
                'pdf_path': None,
                'upload_attempted': False,
                'submit_attempted': False
            }
        
        print(f"PDF: {os.path.basename(pdf_path)}")
        
        # Use the existing solve_request_by_doi function to handle the upload
        result = solve_request_by_doi(driver, doi, pdf_path)
        
        # Update the result to include the original request data
        result['request'] = request_data
        
        return result
        
    except Exception as e:
        error_msg = f"Error solving request: {str(e)}"
        print(f"Error: {error_msg}")
        return {
            'request': request_data,
            'success': False,
            'error': error_msg,
            'pdf_path': None,
            'upload_attempted': False,
            'submit_attempted': False
        }

def select_requests_to_solve(active_requests, no_confirm=False):
    """
    Allow user to select which active requests to solve
    
    Args:
        active_requests: List of active request dictionaries
        no_confirm: If True, automatically select all requests without user confirmation
    
    Returns:
        list: List of selected request dictionaries
    """
    if not active_requests:
        print("No active requests available to solve.")
        return []
    
    # If no_confirm is True, automatically select all requests
    if no_confirm:
        print(f"Auto-selecting all {len(active_requests)} active request(s) (--noconfirm specified)")
        return active_requests.copy()
    
    def timeout_handler(signum, frame):
        print("\nTimeout: No input received within 30 seconds. Quitting.")
        exit(1)
    
    while True:
        try:
            print("\nOptions:")
            print("- Enter numbers separated by commas (e.g., 1,3,5) to select specific requests")
            print("- Enter a range (e.g., 1-5) to select requests 1 through 5")
            print("- Enter 'all' or 'a' to solve all requests")
            print("- Enter 'none' or 'n' to solve no requests")
            
            # Set up timeout signal (only on Unix-like systems)
            if hasattr(signal, 'SIGALRM'):
                signal.signal(signal.SIGALRM, timeout_handler)
                signal.alarm(30)  # 30 second timeout
            
            user_input = input("\nWhich requests would you like to solve? ").strip().lower()
            
            # Cancel the alarm (only on Unix-like systems)
            if hasattr(signal, 'alarm'):
                signal.alarm(0)
            
            if user_input in ['none', 'n', '']:
                print("No requests selected for solving.")
                return []
            
            selected_indices = []
            
            if user_input in ['all', 'a']:
                selected_indices = list(range(len(active_requests)))
            else:
                # Parse input (comma-separated numbers and ranges)
                parts = user_input.replace(' ', '').split(',')
                for part in parts:
                    try:
                        if '-' in part:
                            # Handle range (e.g., "1-5")
                            start, end = map(int, part.split('-'))
                            for idx in range(start, end + 1):
                                if 1 <= idx <= len(active_requests):
                                    selected_indices.append(idx - 1)  # Convert to 0-based
                        else:
                            # Handle single number
                            index = int(part)
                            if 1 <= index <= len(active_requests):
                                selected_indices.append(index - 1)  # Convert to 0-based
                            else:
                                print(f"Warning: Index {index} is out of range (1-{len(active_requests)})")
                    except ValueError:
                        print(f"Warning: '{part}' is not a valid number or range")
            
            if not selected_indices:
                print("No valid selections made. Please try again.")
                continue
            
            # Remove duplicates and sort
            selected_indices = sorted(list(set(selected_indices)))
            selected_requests = [active_requests[i] for i in selected_indices]
            
            print(f"\nSelected {len(selected_requests)} request(s) for solving:")
            for i, request in enumerate(selected_requests, 1):
                print(f"  {i}. {request['title']}")
                if request.get('doi'):
                    print(f"     DOI: {request['doi']}")
            
            # Set up timeout for confirmation (only on Unix-like systems)
            if hasattr(signal, 'SIGALRM'):
                signal.signal(signal.SIGALRM, timeout_handler)
                signal.alarm(30)  # 30 second timeout
            
            confirm = input(f"\nProceed with solving these {len(selected_requests)} requests? (y/n): ").strip().lower()
            
            # Cancel the alarm (only on Unix-like systems)
            if hasattr(signal, 'alarm'):
                signal.alarm(0)
            
            if confirm in ['y', 'yes']:
                return selected_requests
            else:
                print("Selection cancelled. Please choose again.")
                continue
                
        except KeyboardInterrupt:
            if hasattr(signal, 'alarm'):
                signal.alarm(0)  # Cancel alarm
            print("\n\nOperation cancelled by user.")
            return []
        except Exception as e:
            if hasattr(signal, 'alarm'):
                signal.alarm(0)  # Cancel alarm
            print(f"Error in selection: {str(e)}. Please try again.")
            continue
        finally:
            # Make sure alarm is always cancelled (only on Unix-like systems)
            if hasattr(signal, 'alarm'):
                signal.alarm(0)

def solve_active_requests(driver, limit=None, no_confirm=False):
    """
    Get active requests and allow user to select which ones to solve
    
    Args:
        driver: Selenium WebDriver instance
        limit: Optional integer to limit the number of requests retrieved
        no_confirm: If True, automatically select all requests without user confirmation
    
    Returns:
        dict: Summary of solving results
    """
    try:
        # Get active requests
        active_requests = get_active_requests(driver, limit)
        
        if not active_requests:
            print("No active requests found.")
            return {
                'active_requests_found': 0,
                'selected_requests': 0,
                'solved_requests': 0,
                'failed_requests': 0,
                'results': []
            }
        
        # Display active requests
        format_active_requests(active_requests)
        
        # Let user select requests to solve (now returns just the selected requests)
        selected_requests = select_requests_to_solve(active_requests, no_confirm)
        
        if not selected_requests:
            print("No requests selected for solving.")
            return {
                'active_requests_found': len(active_requests),
                'selected_requests': 0,
                'solved_requests': 0,
                'failed_requests': 0,
                'results': []
            }
        
        # Process each selected request
        print(f"\nProcessing {len(selected_requests)} selected request(s)...")
        results = []
        successful_solves = 0
        failed_solves = 0
        
        for i, request in enumerate(selected_requests, 1):
            print(f"\n--- Processing request {i}/{len(selected_requests)} ---")
            result = solve_active_request(driver, request)
            results.append(result)
            
            if result['success']:
                successful_solves += 1
                print(f"✓ Successfully solved: {request.get('title', 'Unknown')}")
            else:
                failed_solves += 1
                print(f"✗ Failed to solve: {request.get('title', 'Unknown')}")
                if result.get('error'):
                    print(f"  Error: {result['error']}")
            
            # Small delay between requests
            if i < len(selected_requests):
                time.sleep(3)
        
        # Summary
        summary = {
            'active_requests_found': len(active_requests),
            'selected_requests': len(selected_requests),
            'solved_requests': successful_solves,
            'failed_requests': failed_solves,
            'results': results,
            'timestamp': datetime.now().isoformat()
        }
        
        print(f"\n{'='*80}")
        print(f"SOLVING SUMMARY")
        print(f"{'='*80}")
        print(f"Active requests found: {summary['active_requests_found']}")
        print(f"Selected for solving: {summary['selected_requests']}")
        print(f"Successfully solved: {summary['solved_requests']}")
        print(f"Failed to solve: {summary['failed_requests']}")
        
        if failed_solves > 0:
            print(f"\nFailed to solve:")
            for result in results:
                if not result['success']:
                    request_title = result['request'].get('title', 'Unknown')
                    print(f"  - {request_title}")
                    if result.get('error'):
                        print(f"    Error: {result['error']}")
        
        if successful_solves > 0:
            print(f"\nSuccessfully solved:")
            for result in results:
                if result['success']:
                    request_title = result['request'].get('title', 'Unknown')
                    pdf_path = result.get('pdf_path')
                    if pdf_path:
                        pdf_name = os.path.basename(pdf_path)
                        print(f"  ✓ {request_title}")
                        print(f"    PDF: {pdf_name}")
                    else:
                        print(f"  ✓ {request_title}")
        
        print(f"{'='*80}")
        
        return summary
        
    except Exception as e:
        print(f"Error in solve_active_requests: {str(e)}")
        return {
            'active_requests_found': 0,
            'selected_requests': 0,
            'solved_requests': 0,
            'failed_requests': 0,
            'error': str(e),
            'results': []
        }

def login_and_solve_active_requests(username, password, headless=False, limit=None, no_confirm=False):
    """
    Login to sci-net.xyz, get active requests, and solve selected ones
    
    Args:
        username: Username for login
        password: Password for login
        headless: Whether to run browser in headless mode
        limit: Optional integer to limit the number of requests retrieved
        no_confirm: If True, automatically select all requests without user confirmation
    
    Returns:
        dict: Summary of solving results
    """
    driver = login_to_scinet(username, password, headless)
    if not driver:
        return None
    
    try:
        result = solve_active_requests(driver, limit, no_confirm)
        return result
    finally:
        print("Solve active requests process completed, closing browser.")
        driver.quit()

def get_waiting_requests(driver, limit=None):
    """
    Get the list of waiting requests from sci-net.xyz/papers/solutions
    Returns a list of waiting request dictionaries with details
    
    Args:
        driver: Selenium WebDriver instance
        limit: Optional integer to limit the number of requests returned
    """
    try:
        print("Getting waiting requests from sci-net.xyz/papers/solutions...")
        
        # Navigate to the solutions page
        driver.get("https://sci-net.xyz/papers/solutions")
        
        # Wait for the page to load
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        
        debug_print("Looking for waiting requests section...")
        
        waiting_requests = []
        last_request_count = 0
        scroll_attempts = 0
        max_scroll_attempts = 100  # Prevent infinite scrolling
        
        while True:
            # Find waiting requests based on the HTML structure provided
            try:
                # Look for links containing articles with waiting status
                waiting_links = driver.find_elements(By.CSS_SELECTOR, "a[href*='/10.']")
                
                debug_print(f"Found {len(waiting_links)} total potential waiting request links")
                
                # Process new request elements
                for i in range(last_request_count, len(waiting_links)):
                    # If we have a limit and reached it, stop processing
                    if limit is not None and limit > 0 and len(waiting_requests) >= limit:
                        debug_print(f"Reached target limit of {limit} waiting requests")
                        break
                    
                    link = waiting_links[i]
                    
                    try:
                        # Check if this link contains an article with waiting status
                        article_div = link.find_element(By.CSS_SELECTOR, "div.article")
                        status_div = article_div.find_element(By.CSS_SELECTOR, "div.status")
                        
                        # Check if status contains "waiting"
                        waiting_span = status_div.find_elements(By.CSS_SELECTOR, "span.waiting")
                        if not waiting_span:
                            continue  # Skip if not a waiting request
                        
                        request_data = {
                            'index': len(waiting_requests) + 1,
                            'title': '',
                            'authors': '',
                            'journal': '',
                            'year': '',
                            'doi': '',
                            'status': 'waiting',
                            'cancel_link': True,  # Any waiting request can be cancelled
                            'request_id': '',
                            'link': link.get_attribute("href"),
                            'datetime': ''
                        }
                        
                        # Extract DOI from href (format: /10.xxxx/xxxxx)
                        href = link.get_attribute("href")
                        if href and '/10.' in href:
                            doi_start = href.find('/10.')
                            if doi_start != -1:
                                request_data['doi'] = href[doi_start + 1:]  # Remove leading slash
                        
                        # Get title
                        try:
                            title_element = article_div.find_element(By.CSS_SELECTOR, "div.title")
                            request_data['title'] = title_element.text.strip()
                        except:
                            pass
                        
                        # Get year
                        try:
                            year_element = article_div.find_element(By.CSS_SELECTOR, "div.year")
                            request_data['year'] = year_element.text.strip()
                        except:
                            pass
                        
                        # Get datetime
                        try:
                            datetime_element = article_div.find_element(By.CSS_SELECTOR, "div.datetime")
                            request_data['datetime'] = datetime_element.text.strip()
                        except:
                            pass
                        
                        # Try to extract request ID from various sources
                        try:
                            # From datetime (might be used as ID)
                            if request_data['datetime'] and request_data['datetime'].isdigit():
                                request_data['request_id'] = request_data['datetime']
                            # From DOI as fallback
                            elif request_data['doi']:
                                request_data['request_id'] = request_data['doi'].replace('/', '_').replace('.', '_')
                        except:
                            pass
                        
                        # Check if this is a valid waiting request (has meaningful information)
                        has_info = any([
                            request_data['title'],
                            request_data['doi'],
                            request_data['year']
                        ])
                        
                        if has_info:
                            waiting_requests.append(request_data)
                            debug_print(f"Parsed waiting request {len(waiting_requests)}: {request_data['title'] or request_data['doi']}...")
                        else:
                            debug_print(f"Ignoring request {i+1}: no meaningful information found")
                    
                    except Exception as parse_error:
                        debug_print(f"Error parsing waiting request {i+1}: {str(parse_error)}")
                        continue
                
                # If we have a limit and reached it, stop
                if limit is not None and limit > 0 and len(waiting_requests) >= limit:
                    debug_print(f"Reached target limit of {limit} waiting requests")
                    break
                
                # Check if we found new requests
                current_request_count = len(waiting_links)
                if current_request_count == last_request_count:
                    # No new requests found, try scrolling
                    scroll_attempts += 1
                    if scroll_attempts >= max_scroll_attempts:
                        debug_print(f"Max scroll attempts ({max_scroll_attempts}) reached, stopping")
                        break
                    
                    debug_print(f"No new requests found, scrolling down (attempt {scroll_attempts})...")
                    
                    # Scroll to the bottom of the page
                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    
                    # Wait for potential new content to load
                    time.sleep(2)
                    
                    # Check if new content was loaded
                    new_waiting_links = driver.find_elements(By.CSS_SELECTOR, "a[href*='/10.']")
                    if len(new_waiting_links) == current_request_count:
                        # Still no new requests after scrolling and waiting
                        debug_print("No new requests loaded after scrolling, assuming end of content")
                        break
                else:
                    # New requests found, reset scroll attempts and update count
                    scroll_attempts = 0
                    last_request_count = current_request_count
                    debug_print(f"Found {current_request_count - last_request_count} new request elements")
            
            except Exception as container_error:
                debug_print(f"Error finding waiting request containers: {str(container_error)}")
                break
        
        print(f"Successfully parsed {len(waiting_requests)} waiting requests (ignored empty results)")
        return waiting_requests
        
    except Exception as e:
        print(f"Error getting waiting requests: {str(e)}")
        return []

def format_waiting_requests(requests):
    """
    Format the waiting requests list in a user-friendly manner
    """
    if not requests:
        print("\nNo waiting requests found.")
        return
    
    print(f"\n{'='*80}")
    print(f"WAITING REQUESTS ON SCI-NET.XYZ ({len(requests)} total)")
    print(f"{'='*80}")
    
    for i, request in enumerate(requests, 1):
        print(f"\n[{i}] {request['title']}")
        
        if request['authors']:
            print(f"    Authors: {request['authors']}")
        
        # Journal and year on same line if both exist
        journal_year_parts = []
        if request['journal']:
            journal_year_parts.append(request['journal'])
        if request['year']:
            journal_year_parts.append(f"({request['year']})")
        if journal_year_parts:
            print(f"    Journal: {' '.join(journal_year_parts)}")
        
        if request['doi']:
            print(f"    DOI: {request['doi']}")
        
        if request['status']:
            print(f"    Status: {request['status']}")
        
        if request['request_id']:
            print(f"    Request ID: {request['request_id']}")
        
        if request.get('link'):
            print(f"    Link: {request['link']}")
        
        # Add separator between requests (but not after the last one)
        if i < len(requests):
            print(f"    {'-'*70}")
    
    print(f"\n{'='*80}")

def select_requests_to_cancel(waiting_requests, no_confirm=False):
    """
    Allow user to select which waiting requests to cancel
    
    Args:
        waiting_requests: List of waiting request dictionaries
        no_confirm: If True, automatically select all requests without user confirmation
    
    Returns:
        list: Selected requests to cancel
    """
    if not waiting_requests:
        print("No waiting requests available to cancel.")
        return []
    
    # Filter out requests that cannot be cancelled
    cancellable_requests = [req for req in waiting_requests if req.get('cancel_link')]
    
    if not cancellable_requests:
        print("No cancellable waiting requests found.")
        return []
    
    # If no_confirm is True, automatically select all requests
    if no_confirm:
        print(f"Auto-selecting all {len(cancellable_requests)} cancellable request(s) (--noconfirm specified)")
        return cancellable_requests.copy()
    
    def timeout_handler(signum, frame):
        print("\nTimeout: No input received within 30 seconds. Quitting.")
        exit(1)
    
    while True:
        try:
            print("\nOptions:")
            print("- Enter numbers separated by commas (e.g., 1,3,5) to select specific requests")
            print("- Enter a range (e.g., 1-5) to select requests 1 through 5")
            print("- Enter 'all' or 'a' to cancel all requests")
            print("- Enter 'none' or 'n' to cancel no requests")
            
            # Set up timeout signal (only on Unix-like systems)
            if hasattr(signal, 'SIGALRM'):
                signal.signal(signal.SIGALRM, timeout_handler)
                signal.alarm(30)  # 30 second timeout
            
            user_input = input("\nWhich waiting requests would you like to cancel? ").strip().lower()
            
            # Cancel the alarm (only on Unix-like systems)
            if hasattr(signal, 'alarm'):
                signal.alarm(0)
            
            if user_input in ['none', 'n', '']:
                print("No requests selected for cancellation.")
                return []
            
            selected_indices = []
            
            if user_input in ['all', 'a']:
                selected_indices = list(range(len(cancellable_requests)))
            else:
                # Parse input (comma-separated numbers and ranges)
                parts = user_input.replace(' ', '').split(',')
                for part in parts:
                    try:
                        if '-' in part:
                            # Handle range (e.g., "1-5")
                            start, end = map(int, part.split('-'))
                            for idx in range(start, end + 1):
                                if 1 <= idx <= len(cancellable_requests):
                                    selected_indices.append(idx - 1)  # Convert to 0-based
                        else:
                            # Handle single number
                            index = int(part)
                            if 1 <= index <= len(cancellable_requests):
                                selected_indices.append(index - 1)  # Convert to 0-based
                            else:
                                print(f"Warning: Index {index} is out of range (1-{len(cancellable_requests)})")
                    except ValueError:
                        print(f"Warning: '{part}' is not a valid number or range")
            
            if not selected_indices:
                print("No valid selections made. Please try again.")
                continue
            
            # Remove duplicates and sort
            selected_indices = sorted(list(set(selected_indices)))
            selected_requests = [cancellable_requests[i] for i in selected_indices]
            
            print(f"\nSelected {len(selected_requests)} request(s) for cancellation:")
            for i, request in enumerate(selected_requests, 1):
                print(f"  {i}. {request['title']}")
                if request.get('doi'):
                    print(f"     DOI: {request['doi']}")
            
            # Set up timeout for confirmation (only on Unix-like systems)
            if hasattr(signal, 'SIGALRM'):
                signal.signal(signal.SIGALRM, timeout_handler)
                signal.alarm(30)  # 30 second timeout
            
            confirm = input(f"\nProceed with cancelling these {len(selected_requests)} requests? (y/n): ").strip().lower()
            
            # Cancel the alarm (only on Unix-like systems)
            if hasattr(signal, 'alarm'):
                signal.alarm(0)
            
            if confirm in ['y', 'yes']:
                return selected_requests
            else:
                print("Selection cancelled. Please choose again.")
                continue
                
        except KeyboardInterrupt:
            if hasattr(signal, 'alarm'):
                signal.alarm(0)  # Cancel alarm
            print("\n\nOperation cancelled by user.")
            return []
        except Exception as e:
            if hasattr(signal, 'alarm'):
                signal.alarm(0)  # Cancel alarm
            print(f"Error in selection: {str(e)}. Please try again.")
            continue
        finally:
            # Make sure alarm is always cancelled (only on Unix-like systems)
            if hasattr(signal, 'alarm'):
                signal.alarm(0)

def cancel_waiting_request_by_doi(driver, doi):
    """
    Cancel a waiting request by specifying its DOI directly
    
    Args:
        driver: Selenium WebDriver instance
        doi: DOI of the waiting request to cancel
    
    Returns:
        dict: Result of the cancellation attempt
    """
    try:
        print(f"Cancelling waiting request for DOI: {doi}")
        
        result = {
            'doi': doi,
            'success': False,
            'error': None,
            'cancel_attempted': False,
            'cancel_url': ''
        }
        
        # Navigate to the DOI page to find the cancel link
        doi_url = f"https://sci-net.xyz/{doi}"
        result['cancel_url'] = doi_url
        
        try:
            debug_print(f"Navigating to DOI page: {doi_url}")
            driver.get(doi_url)
            
            # Wait for the page to load
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            
            # Look for the preview div containing the cancel link
            try:
                debug_print("Looking for preview div...")
                preview_div = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "div.preview"))
                )
                
                # Look for the cancel/revoke link within the preview div
                debug_print("Looking for cancel/revoke link in preview div...")
                cancel_link = preview_div.find_element(By.CSS_SELECTOR, "a.revoke")
                
                cancel_href = cancel_link.get_attribute("href")
                cancel_text = cancel_link.text.strip()
                
                debug_print(f"Found cancel link - text: '{cancel_text}', href: '{cancel_href}'")
                print(f"Found cancel link: {cancel_text}")
                
                # Scroll to the cancel link and click it
                driver.execute_script("arguments[0].scrollIntoView(true);", cancel_link)
                time.sleep(1)
                
                # Click the cancel link
                try:
                    cancel_link.click()
                    debug_print("Cancel link clicked")
                    result['cancel_attempted'] = True
                except:
                    # Fallback to JavaScript click
                    driver.execute_script("arguments[0].click();", cancel_link)
                    debug_print("Cancel link clicked via JavaScript")
                    result['cancel_attempted'] = True
                
                # Wait for the cancellation to process
                print("Cancel link clicked, waiting for processing...")
                time.sleep(3)
                
                # Check for confirmation dialogs
                try:
                    alert = driver.switch_to.alert
                    alert_text = alert.text
                    print(f"Confirmation dialog: {alert_text}")
                    alert.accept()  # Click OK/Yes to confirm cancellation
                    print("Cancellation confirmed")
                    time.sleep(2)
                except:
                    debug_print("No confirmation dialog found")
                
                # Check current URL or page content to verify cancellation
                current_url = driver.current_url
                debug_print(f"Current URL after cancel attempt: {current_url}")
                
                # Look for success messages or indicators that the request was cancelled
                try:
                    success_indicators = driver.find_elements(By.CSS_SELECTOR, 
                        ".success, .cancelled, .removed, [class*='success'], [class*='cancelled']")
                    
                    if success_indicators:
                        for indicator in success_indicators:
                            if indicator.is_displayed():
                                message = indicator.text.strip()
                                if message:
                                    print(f"Success message: {message}")
                                    break
                except:
                    pass
                
                result['success'] = True
                print("✓ Request cancellation successful")
                
            except TimeoutException:
                result['error'] = 'Preview div not found - page may not have cancel option'
                print(f"Error: {result['error']}")
            except Exception as preview_error:
                # Try alternative method - look for revoke link anywhere on the page
                try:
                    debug_print("Preview div method failed, trying alternative method...")
                    cancel_link = driver.find_element(By.CSS_SELECTOR, "a.revoke, a[href*='/unsolve/']")
                    
                    cancel_href = cancel_link.get_attribute("href")
                    cancel_text = cancel_link.text.strip()
                    
                    debug_print(f"Found alternative cancel link - text: '{cancel_text}', href: '{cancel_href}'")
                    print(f"Found cancel link: {cancel_text}")
                    
                    # Click the cancel link
                    driver.execute_script("arguments[0].scrollIntoView(true);", cancel_link)
                    time.sleep(1)
                    cancel_link.click()
                    result['cancel_attempted'] = True
                    
                    print("Cancel link clicked, waiting for processing...")
                    time.sleep(3)
                    
                    result['success'] = True
                    print("✓ Request cancellation successful")
                    
                except Exception as alt_error:
                    result['error'] = f'Cancel link not found in preview div or elsewhere: {str(preview_error)}'
                    print(f"Error: {result['error']}")
        
        except Exception as nav_error:
            result['error'] = f'Navigation to DOI page failed: {str(nav_error)}'
            print(f"Error: {result['error']}")
        
        return result
        
    except Exception as e:
        error_msg = f"Error cancelling request by DOI: {str(e)}"
        print(f"Error: {error_msg}")
        return {
            'doi': doi,
            'success': False,
            'error': error_msg,
            'cancel_attempted': False,
            'cancel_url': ''
        }

def login_and_cancel_waiting_request_by_doi(username, password, doi, headless=False):
    """
    Login to sci-net.xyz and cancel a specific waiting request by DOI
    
    Args:
        username: Username for login
        password: Password for login
        doi: DOI of the waiting request to cancel
        headless: Whether to run browser in headless mode
    
    Returns:
        dict: Result of the cancellation attempt
    """
    driver = login_to_scinet(username, password, headless)
    if not driver:
        return None
    
    try:
        result = cancel_waiting_request_by_doi(driver, doi)
        return result
    finally:
        print("Cancel waiting request by DOI process completed, closing browser.")
        driver.quit()

def cancel_waiting_request(driver, request_data):
    """
    Cancel a single waiting request
    
    Args:
        driver: Selenium WebDriver instance
        request_data: Dictionary containing request information with 'doi' and other details
    
    Returns:
        dict: Result of the cancellation attempt
    """
    try:
        title = request_data.get('title', 'Unknown')
        doi = request_data.get('doi', '')
        print(f"\nCancelling request: {title}")
        if doi:
            print(f"DOI: {doi}")
        
        if not doi:
            error_msg = 'No DOI found for this request'
            print(f"Error: {error_msg}")
            return {
                'request': request_data,
                'success': False,
                'error': error_msg,
                'cancel_attempted': False,
                'cancel_url': ''
            }
        
        # Use the existing cancel_waiting_request_by_doi function
        result = cancel_waiting_request_by_doi(driver, doi)
        
        # Update the result to include the original request data
        result['request'] = request_data
        
        return result
        
    except Exception as e:
        error_msg = f"Error cancelling request: {str(e)}"
        print(f"Error: {error_msg}")
        return {
            'request': request_data,
            'success': False,
            'error': error_msg,
            'cancel_attempted': False,
            'cancel_url': ''
        }

def cancel_waiting_requests(driver, limit=None, no_confirm=False):
    """
    Get waiting requests and allow user to select which ones to cancel
    
    Args:
        driver: Selenium WebDriver instance
        limit: Optional integer to limit the number of requests retrieved
        no_confirm: If True, automatically select all requests without user confirmation
    
    Returns:
        dict: Summary of cancellation results
    """
    try:
        # Get waiting requests
        waiting_requests = get_waiting_requests(driver)
        
        # Apply limit if specified
        if limit is not None and limit > 0 and len(waiting_requests) > limit:
            print(f"Limiting results to {limit} out of {len(waiting_requests)} waiting requests")
            waiting_requests = waiting_requests[:limit]
        
        if not waiting_requests:
            print("No waiting requests found.")
            return {
                'waiting_requests_found': 0,
                'selected_requests': 0,
                'cancelled_requests': 0,
                'failed_requests': 0,
                'results': []
            }
        
        # Display waiting requests
        format_waiting_requests(waiting_requests)
        
        # Let user select requests to cancel
        selected_requests = select_requests_to_cancel(waiting_requests, no_confirm)
        
        if not selected_requests:
            # print("No requests selected for cancellation.")
            return {
                'waiting_requests_found': len(waiting_requests),
                'selected_requests': 0,
                'cancelled_requests': 0,
                'failed_requests': 0,
                'results': []
            }
        
        # Process each selected request
        print(f"\nProcessing {len(selected_requests)} selected request(s) for cancellation...")
        results = []
        successful_cancels = 0
        failed_cancels = 0
        
        for i, request in enumerate(selected_requests, 1):
            print(f"\n--- Processing cancellation {i}/{len(selected_requests)} ---")
            result = cancel_waiting_request(driver, request)
            results.append(result)
            
            if result['success']:
                successful_cancels += 1
            else:
                failed_cancels += 1
            
            # Small delay between requests
            if i < len(selected_requests):
                time.sleep(2)
        
        # Summary
        summary = {
            'waiting_requests_found': len(waiting_requests),
            'selected_requests': len(selected_requests),
            'cancelled_requests': successful_cancels,
            'failed_requests': failed_cancels,
            'results': results,
            'timestamp': datetime.now().isoformat()
        }
        
        print(f"\n{'='*80}")
        print(f"CANCELLATION SUMMARY")
        print(f"{'='*80}")
        print(f"Waiting requests found: {summary['waiting_requests_found']}")
        print(f"Selected for cancellation: {summary['selected_requests']}")
        print(f"Successfully cancelled: {summary['cancelled_requests']}")
        print(f"Failed to cancel: {summary['failed_requests']}")
        
        if failed_cancels > 0:
            print(f"\nFailed to cancel:")
            for result in results:
                if not result['success']:
                    request_title = result['request'].get('title', 'Unknown')
                    print(f"  - {request_title}")
                    if result.get('error'):
                        print(f"    Error: {result['error']}")
        
        if successful_cancels > 0:
            print(f"\nSuccessfully cancelled:")
            for result in results:
                if result['success']:
                    request_title = result['request'].get('title', 'Unknown')
                    print(f"  ✓ {request_title}")
        
        print(f"{'='*80}")
        
        return summary
        
    except Exception as e:
        print(f"Error in cancel_waiting_requests: {str(e)}")
        return {
            'waiting_requests_found': 0,
            'selected_requests': 0,
            'cancelled_requests': 0,
            'failed_requests': 0,
            'error': str(e),
            'results': []
        }

def login_and_cancel_waiting_requests(username, password, headless=False, limit=None, no_confirm=False):
    """
    Login to sci-net.xyz, get waiting requests, and cancel selected ones
    
    Args:
        username: Username for login
        password: Password for login
        headless: Whether to run browser in headless mode
        limit: Optional integer to limit the number of requests retrieved
        no_confirm: If True, automatically select all requests without user confirmation
    
    Returns:
        dict: Summary of cancellation results
    """
    driver = login_to_scinet(username, password, headless)
    if not driver:
        return None
    
    try:
        result = cancel_waiting_requests(driver, limit, no_confirm)
        return result
    finally:
        print("Cancel waiting requests process completed, closing browser.")
        driver.quit()

def setup_argument_autocomplete(parser):
    """
    Set up tab completion for command line arguments using argcomplete if available
    """
    try:
        
        # Custom completer for file paths (PDFs, directories, text files)
        def file_completer(prefix, parsed_args, **kwargs):
            
            # Expand user home directory
            if prefix.startswith('~'):
                prefix = os.path.expanduser(prefix)
            
            # Get all possible completions
            if prefix.endswith('/'):
                pattern = prefix + '*'
            else:
                pattern = prefix + '*'
            
            matches = glob.glob(pattern)
            
            # Filter and format completions
            completions = []
            for match in matches:
                if os.path.isdir(match):
                    completions.append(match + '/')
                elif match.lower().endswith(('.pdf', '.txt')):
                    completions.append(match)
                elif os.path.isfile(match):
                    completions.append(match)
            
            return sorted(completions)
        
        # Custom completer for DOI arguments
        def doi_completer(prefix, parsed_args, **kwargs):
            
            # If it looks like a file path, use file completion
            if '/' in prefix or prefix.startswith('~') or prefix.startswith('.'):
                # Expand user home directory
                if prefix.startswith('~'):
                    prefix = os.path.expanduser(prefix)
                
                # Get file completions
                pattern = prefix + '*'
                matches = glob.glob(pattern)
                
                completions = []
                for match in matches:
                    if os.path.isdir(match):
                        completions.append(match + '/')
                    elif match.lower().endswith('.txt'):
                        completions.append(match)
                
                return sorted(completions)
            
            # Otherwise, provide DOI format hints
            if not prefix:
                return ['10.', 'https://doi.org/10.', 'http://dx.doi.org/10.']
            elif prefix.startswith('10.'):
                if '/' not in prefix:
                    return [prefix + '1000/']
                else:
                    return [prefix + 'example']
            elif prefix.startswith('https://'):
                if prefix == 'https://':
                    return ['https://doi.org/10.']
                elif 'doi.org' not in prefix:
                    return ['https://doi.org/10.']
            elif prefix.startswith('http://'):
                if prefix == 'http://':
                    return ['http://dx.doi.org/10.']
                elif 'doi.org' not in prefix:
                    return ['http://dx.doi.org/10.']
            
            return []
        
        # Set completers for specific arguments
        parser.add_argument('--pdf', nargs='+', help='Path(s) to PDF file(s) to upload, or directory containing PDFs (can specify multiple paths separated by spaces)').completer = file_completer
        parser.add_argument('--request-doi', nargs='+', help='DOI(s) to request: single DOI with optional reward tokens (DOI,tokens), multiple DOIs with optional reward tokens separated by spaces, or path to text file containing DOIs and optional reward tokens (one per line, format: DOI or DOI,tokens). Default reward tokens: 1').completer = doi_completer
        parser.add_argument('--solve-pdf', help='Path to PDF file to upload as solution (must be used with --solve-doi)').completer = file_completer
        
        # Enable autocomplete
        argcomplete.autocomplete(parser)
        return True
        
    except ImportError:
        # argcomplete not available, continue without autocomplete
        return False

def get_unsolved_requests(driver, limit=None):
    """
    Get the list of unsolved requests from sci-net.xyz/papers
    Returns a list of unsolved request dictionaries with details
    
    Args:
        driver: Selenium WebDriver instance
        limit: Optional integer to limit the number of requests returned
    """
    try:
        print("Getting unsolved requests from sci-net.xyz/papers...")
        
        # Navigate to the papers page
        driver.get("https://sci-net.xyz/papers")
        
        # Wait for the page to load
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        
        debug_print("Looking for unsolved requests section...")
        
        unsolved_requests = []
        last_request_count = 0
        scroll_attempts = 0
        max_scroll_attempts = 100  # Prevent infinite scrolling
        
        while True:
            # Find unsolved requests based on the provided HTML structure
            try:
                # Look for links containing articles with unsolved status
                unsolved_links = driver.find_elements(By.CSS_SELECTOR, "a[href*='/10.']")
                
                debug_print(f"Found {len(unsolved_links)} total potential unsolved request links")
                
                # Process new request elements
                for i in range(last_request_count, len(unsolved_links)):
                    # If we have a limit and reached it, stop processing
                    if limit is not None and limit > 0 and len(unsolved_requests) >= limit:
                        debug_print(f"Reached target limit of {limit} unsolved requests")
                        break
                    
                    link = unsolved_links[i]
                    
                    try:
                        # Check if this link contains an article with unsolved status
                        article_div = link.find_element(By.CSS_SELECTOR, "div.article")
                        status_div = article_div.find_element(By.CSS_SELECTOR, "div.status")
                        
                        # Check if status contains "unsolved"
                        unsolved_span = status_div.find_elements(By.CSS_SELECTOR, "span.unsolved")
                        if not unsolved_span:
                            continue  # Skip if not an unsolved request
                        
                        request_data = {
                            'index': len(unsolved_requests) + 1,
                            'title': '',
                            'authors': '',
                            'journal': '',
                            'year': '',
                            'doi': '',
                            'reward': '',
                            'time_left': '',
                            'requester': '',
                            'link': link.get_attribute("href"),
                            'status': 'unsolved',
                            'datetime': ''
                        }
                        
                        # Extract DOI from href (format: /10.xxxx/xxxxx)
                        href = link.get_attribute("href")
                        if href and '/10.' in href:
                            doi_start = href.find('/10.')
                            if doi_start != -1:
                                request_data['doi'] = href[doi_start + 1:]  # Remove leading slash
                        
                        # Get title
                        try:
                            title_element = article_div.find_element(By.CSS_SELECTOR, "div.title")
                            request_data['title'] = title_element.text.strip()
                        except:
                            pass
                        
                        # Get year
                        try:
                            year_element = article_div.find_element(By.CSS_SELECTOR, "div.year")
                            request_data['year'] = year_element.text.strip()
                        except:
                            pass
                        
                        # Get datetime
                        try:
                            datetime_element = article_div.find_element(By.CSS_SELECTOR, "div.datetime")
                            request_data['datetime'] = datetime_element.text.strip()
                        except:
                            pass
                        
                        # Try to get additional information if available (authors, journal, reward, etc.)
                        # These might not be present in the basic structure but could be in extended versions
                        try:
                            authors_element = article_div.find_element(By.CSS_SELECTOR, "div.authors")
                            request_data['authors'] = authors_element.text.strip()
                        except:
                            pass
                        
                        try:
                            journal_element = article_div.find_element(By.CSS_SELECTOR, "div.journal")
                            request_data['journal'] = journal_element.text.strip()
                        except:
                            pass
                        
                        try:
                            reward_element = article_div.find_element(By.CSS_SELECTOR, "div.reward")
                            request_data['reward'] = reward_element.text.strip()
                        except:
                            pass
                        
                        try:
                            time_element = article_div.find_element(By.CSS_SELECTOR, "div.time")
                            request_data['time_left'] = time_element.text.strip()
                        except:
                            pass
                        
                        # Try to get requester information if available
                        try:
                            user_element = article_div.find_element(By.CSS_SELECTOR, "div.user")
                            request_data['requester'] = user_element.text.strip()
                        except:
                            pass
                        
                        # Check if the request has meaningful information
                        # Require at least title or DOI to be valid
                        has_info = any([
                            request_data['title'],
                            request_data['doi']
                        ])
                        
                        if has_info:
                            unsolved_requests.append(request_data)
                            debug_print(f"Parsed unsolved request {len(unsolved_requests)}: {request_data['title'] or request_data['doi']}...")
                        else:
                            debug_print(f"Ignoring request {i+1}: no meaningful information found")
                    
                    except Exception as parse_error:
                        debug_print(f"Error parsing unsolved request {i+1}: {str(parse_error)}")
                        continue
                
                # If we have a limit and reached it, stop
                if limit is not None and limit > 0 and len(unsolved_requests) >= limit:
                    debug_print(f"Reached target limit of {limit} unsolved requests")
                    break
                
                # Check if we found new requests
                current_request_count = len(unsolved_links)
                if current_request_count == last_request_count:
                    # No new requests found, try scrolling
                    scroll_attempts += 1
                    if scroll_attempts >= max_scroll_attempts:
                        debug_print(f"Max scroll attempts ({max_scroll_attempts}) reached, stopping")
                        break
                    
                    debug_print(f"No new requests found, scrolling down (attempt {scroll_attempts})...")
                    
                    # Scroll to the bottom of the page
                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    
                    # Wait for potential new content to load
                    time.sleep(2)
                    
                    # Check if new content was loaded
                    new_unsolved_links = driver.find_elements(By.CSS_SELECTOR, "a[href*='/10.']")
                    if len(new_unsolved_links) == current_request_count:
                        # Still no new requests after scrolling and waiting
                        debug_print("No new requests loaded after scrolling, assuming end of content")
                        break
                else:
                    # New requests found, reset scroll attempts and update count
                    scroll_attempts = 0
                    last_request_count = current_request_count
                    debug_print(f"Found {current_request_count - last_request_count} new request elements")
            
            except Exception as container_error:
                debug_print(f"Error finding unsolved request containers: {str(container_error)}")
                break
        
        print(f"Successfully parsed {len(unsolved_requests)} unsolved requests (ignored empty results)")
        return unsolved_requests
        
    except Exception as e:
        print(f"Error getting unsolved requests: {str(e)}")
        return []

def format_unsolved_requests(requests):
    """
    Format the unsolved requests list in a user-friendly manner
    """
    if not requests:
        print("\nNo unsolved requests found.")
        return
    
    print(f"\n{'='*80}")
    print(f"UNSOLVED REQUESTS ON SCI-NET.XYZ ({len(requests)} total)")
    print(f"{'='*80}")
    
    for i, request in enumerate(requests, 1):
        print(f"\n[{i}] {request['title'] or 'Untitled Request'}")
        
        if request['authors']:
            print(f"    Authors: {request['authors']}")
        
        # Journal and year on same line if both exist
        journal_year_parts = []
        if request['journal']:
            journal_year_parts.append(request['journal'])
        if request['year']:
            journal_year_parts.append(f"({request['year']})")
        if journal_year_parts:
            print(f"    Journal: {' '.join(journal_year_parts)}")
        elif request['year']:
            print(f"    Year: {request['year']}")
        
        if request['doi']:
            print(f"    DOI: {request['doi']}")
        
        # Reward and time left on same line
        reward_time_parts = []
        if request['reward']:
            reward_time_parts.append(f"Reward: {request['reward']}")
        if request['time_left']:
            reward_time_parts.append(f"Time left: {request['time_left']}")
        if reward_time_parts:
            print(f"    {' | '.join(reward_time_parts)}")
        
        if request['requester']:
            print(f"    Requested by: @{request['requester']} (https://sci-net.xyz/@{request['requester']})")
        
        if request['datetime']:
            print(f"    DateTime: {request['datetime']}")
        
        if request['link']:
            print(f"    Link: {request['link']}")
        
        # Add separator between requests (but not after the last one)
        if i < len(requests):
            print(f"    {'-'*70}")
    
    print(f"\n{'='*80}")

def login_and_get_unsolved_requests(username, password, headless=False, limit=None):
    """
    Login to sci-net.xyz and get the list of unsolved requests
    Returns a list of unsolved request dictionaries
    
    Args:
        username: Username for login
        password: Password for login
        headless: Whether to run browser in headless mode
        limit: Optional integer to limit the number of requests returned
    """
    driver = login_to_scinet(username, password, headless)
    if not driver:
        return []
    
    try:
        requests = get_unsolved_requests(driver, limit)
        format_unsolved_requests(requests)
        return requests
    finally:
        print("Unsolved requests retrieval completed, closing browser.")
        driver.quit()

def cancel_unsolved_request_by_doi(driver, doi):
    """
    Cancel an unsolved request by directly visiting the cancel URL for the DOI
    
    Args:
        driver: Selenium WebDriver instance
        doi: DOI of the unsolved request to cancel
    
    Returns:
        dict: Result of the cancellation attempt
    """
    try:
        print(f"Cancelling unsolved request for DOI: {doi}")
        
        result = {
            'doi': doi,
            'success': False,
            'error': None,
            'cancel_url': '',
            'response_message': ''
        }
        
        # Construct the cancel URL
        cancel_url = f"https://sci-net.xyz/cancel/{doi}"
        result['cancel_url'] = cancel_url
        
        try:
            debug_print(f"Navigating to cancel URL: {cancel_url}")
            driver.get(cancel_url)
            
            # Wait for the page to load
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            
            # Get the current URL to check if we were redirected
            current_url = driver.current_url
            debug_print(f"Current URL after navigation: {current_url}")
            
            # Check for success/error messages on the page
            try:
                # Check for success messages
                success_elements = driver.find_elements(By.CSS_SELECTOR, 
                    ".success, .message, .notice, [class*='success'], [class*='message']")
                
                for element in success_elements:
                    if element.is_displayed():
                        message = element.text.strip()
                        if message:
                            result['response_message'] = message
                            print(f"Response: {message}")
                            # If message indicates success, mark as successful
                            if any(word in message.lower() for word in ['cancelled', 'removed', 'deleted', 'success']):
                                result['success'] = True
                            break
                
                # Check for error messages if no success message found
                if not result['success']:
                    error_elements = driver.find_elements(By.CSS_SELECTOR, 
                        ".error, .warning, [class*='error'], [class*='warning']")
                    
                    for element in error_elements:
                        if element.is_displayed():
                            error_message = element.text.strip()
                            if error_message:
                                result['error'] = error_message
                                result['response_message'] = error_message
                                print(f"Error: {error_message}")
                                break
                
                # If no explicit messages found, check if we're still on a cancel-related page
                if not result['success'] and not result['error']:
                    page_title = driver.title.lower()
                    page_content = driver.find_element(By.TAG_NAME, "body").text.lower()
                    
                    # Look for indicators that cancellation was successful
                    if any(word in page_title for word in ['cancelled', 'removed', 'success']) or \
                        any(word in page_content for word in ['cancelled', 'removed', 'successfully']):
                        result['success'] = True
                        result['response_message'] = 'Request appears to have been cancelled successfully'
                        print("✓ Request appears to have been cancelled successfully")
                    elif any(word in page_content for word in ['not found', 'invalid', 'error', 'failed']):
                        result['error'] = 'Request not found or cancellation failed'
                        result['response_message'] = result['error']
                        print(f"Error: {result['error']}")
                    else:
                        # Default to success if we reached the cancel URL without obvious errors
                        result['success'] = True
                        result['response_message'] = 'Cancel URL accessed successfully'
                        print("✓ Cancel URL accessed successfully")
                
            except Exception as message_error:
                debug_print(f"Error checking page messages: {str(message_error)}")
                # If we can't parse messages but reached the URL, assume success
                result['success'] = True
                result['response_message'] = 'Cancel URL accessed (message parsing failed)'
                print("✓ Cancel URL accessed (message parsing failed)")
            
            if result['success']:
                print("✓ Request cancellation successful")
            
        except Exception as nav_error:
            result['error'] = f'Failed to navigate to cancel URL: {str(nav_error)}'
            print(f"Error: {result['error']}")
        
        return result
        
    except Exception as e:
        error_msg = f"Error cancelling unsolved request: {str(e)}"
        print(f"Error: {error_msg}")
        return {
            'doi': doi,
            'success': False,
            'error': error_msg,
            'cancel_url': f"https://sci-net.xyz/cancel/{doi}",
            'response_message': ''
        }

def login_and_cancel_unsolved_request_by_doi(username, password, doi, headless=False):
    """
    Login to sci-net.xyz and cancel a specific unsolved request by DOI using the cancel URL
    
    Args:
        username: Username for login
        password: Password for login
        doi: DOI of the unsolved request to cancel
        headless: Whether to run browser in headless mode
    
    Returns:
        dict: Result of the cancellation attempt
    """
    driver = login_to_scinet(username, password, headless)
    if not driver:
        return None
    
    try:
        result = cancel_unsolved_request_by_doi(driver, doi)
        return result
    finally:
        print("Cancel unsolved request by DOI process completed, closing browser.")
        driver.quit()

def cancel_unsolved_request(driver, request_data):
    """
    Cancel a single unsolved request
    
    Args:
        driver: Selenium WebDriver instance
        request_data: Dictionary containing request information with 'doi' and other details
    
    Returns:
        dict: Result of the cancellation attempt
    """
    try:
        title = request_data.get('title', 'Unknown')
        doi = request_data.get('doi', '')
        print(f"\nCancelling unsolved request: {title}")
        if doi:
            print(f"DOI: {doi}")
        
        if not doi:
            error_msg = 'No DOI found for this request'
            print(f"Error: {error_msg}")
            return {
                'request': request_data,
                'success': False,
                'error': error_msg,
                'cancel_url': '',
                'response_message': ''
            }
        
        # Use the existing cancel_unsolved_request_by_doi function
        result = cancel_unsolved_request_by_doi(driver, doi)
        
        # Update the result to include the original request data
        result['request'] = request_data
        
        return result
        
    except Exception as e:
        error_msg = f"Error cancelling unsolved request: {str(e)}"
        print(f"Error: {error_msg}")
        return {
            'request': request_data,
            'success': False,
            'error': error_msg,
            'cancel_url': '',
            'response_message': ''
        }

def select_unsolved_requests_to_cancel(unsolved_requests, no_confirm=False):
    """
    Allow user to select which unsolved requests to cancel
    
    Args:
        unsolved_requests: List of unsolved request dictionaries
        no_confirm: If True, automatically select all requests without user confirmation
    
    Returns:
        list: Selected requests to cancel
    """
    if not unsolved_requests:
        print("No unsolved requests available to cancel.")
        return []
    
    # If no_confirm is True, automatically select all requests
    if no_confirm:
        print(f"Auto-selecting all {len(unsolved_requests)} unsolved request(s) (--noconfirm specified)")
        return unsolved_requests.copy()
    
    def timeout_handler(signum, frame):
        print("\nTimeout: No input received within 30 seconds. Quitting.")
        exit(1)
    
    while True:
        try:
            print("\nOptions:")
            print("- Enter numbers separated by commas (e.g., 1,3,5) to select specific requests")
            print("- Enter a range (e.g., 1-5) to select requests 1 through 5")
            print("- Enter 'all' or 'a' to cancel all requests")
            print("- Enter 'none' or 'n' to cancel no requests")
            
            # Set up timeout signal (only on Unix-like systems)
            if hasattr(signal, 'SIGALRM'):
                signal.signal(signal.SIGALRM, timeout_handler)
                signal.alarm(30)  # 30 second timeout
            
            user_input = input("\nWhich unsolved requests would you like to cancel? ").strip().lower()
            
            # Cancel the alarm (only on Unix-like systems)
            if hasattr(signal, 'alarm'):
                signal.alarm(0)
            
            if user_input in ['none', 'n', '']:
                print("No requests selected for cancellation.")
                return []
            
            selected_indices = []
            
            if user_input in ['all', 'a']:
                selected_indices = list(range(len(unsolved_requests)))
            else:
                # Parse input (comma-separated numbers and ranges)
                parts = user_input.replace(' ', '').split(',')
                for part in parts:
                    try:
                        if '-' in part:
                            # Handle range (e.g., "1-5")
                            start, end = map(int, part.split('-'))
                            for idx in range(start, end + 1):
                                if 1 <= idx <= len(unsolved_requests):
                                    selected_indices.append(idx - 1)  # Convert to 0-based
                        else:
                            # Handle single number
                            index = int(part)
                            if 1 <= index <= len(unsolved_requests):
                                selected_indices.append(index - 1)  # Convert to 0-based
                            else:
                                print(f"Warning: Index {index} is out of range (1-{len(unsolved_requests)})")
                    except ValueError:
                        print(f"Warning: '{part}' is not a valid number or range")
            
            if not selected_indices:
                print("No valid selections made. Please try again.")
                continue
            
            # Remove duplicates and sort
            selected_indices = sorted(list(set(selected_indices)))
            selected_requests = [unsolved_requests[i] for i in selected_indices]
            
            print(f"\nSelected {len(selected_requests)} request(s) for cancellation:")
            for i, request in enumerate(selected_requests, 1):
                print(f"  {i}. {request['title'] or 'Untitled Request'}")
                if request.get('doi'):
                    print(f"     DOI: {request['doi']}")
            
            # Set up timeout for confirmation (only on Unix-like systems)
            if hasattr(signal, 'SIGALRM'):
                signal.signal(signal.SIGALRM, timeout_handler)
                signal.alarm(30)  # 30 second timeout
            
            confirm = input(f"\nProceed with cancelling these {len(selected_requests)} unsolved requests? (y/n): ").strip().lower()
            
            # Cancel the alarm (only on Unix-like systems)
            if hasattr(signal, 'alarm'):
                signal.alarm(0)
            
            if confirm in ['y', 'yes']:
                return selected_requests
            else:
                print("Selection cancelled. Please choose again.")
                continue
                
        except KeyboardInterrupt:
            if hasattr(signal, 'alarm'):
                signal.alarm(0)  # Cancel alarm
            print("\n\nOperation cancelled by user.")
            return []
        except Exception as e:
            if hasattr(signal, 'alarm'):
                signal.alarm(0)  # Cancel alarm
            print(f"Error in selection: {str(e)}. Please try again.")
            continue
        finally:
            # Make sure alarm is always cancelled (only on Unix-like systems)
            if hasattr(signal, 'alarm'):
                signal.alarm(0)

def cancel_unsolved_requests(driver, limit=None, no_confirm=False):
    """
    Get unsolved requests and allow user to select which ones to cancel
    
    Args:
        driver: Selenium WebDriver instance
        limit: Optional integer to limit the number of requests retrieved
        no_confirm: If True, automatically select all requests without user confirmation
    
    Returns:
        dict: Summary of cancellation results
    """
    try:
        # Get unsolved requests
        unsolved_requests = get_unsolved_requests(driver, limit)
        
        if not unsolved_requests:
            print("No unsolved requests found.")
            return {
                'unsolved_requests_found': 0,
                'selected_requests': 0,
                'cancelled_requests': 0,
                'failed_requests': 0,
                'results': []
            }
        
        # Display unsolved requests
        format_unsolved_requests(unsolved_requests)
        
        # Let user select requests to cancel
        selected_requests = select_unsolved_requests_to_cancel(unsolved_requests, no_confirm)
        
        if not selected_requests:
            return {
                'unsolved_requests_found': len(unsolved_requests),
                'selected_requests': 0,
                'cancelled_requests': 0,
                'failed_requests': 0,
                'results': []
            }
        
        # Process each selected request
        print(f"\nProcessing {len(selected_requests)} selected request(s) for cancellation...")
        results = []
        successful_cancels = 0
        failed_cancels = 0
        
        for i, request in enumerate(selected_requests, 1):
            print(f"\n--- Processing cancellation {i}/{len(selected_requests)} ---")
            result = cancel_unsolved_request(driver, request)
            results.append(result)
            
            if result['success']:
                successful_cancels += 1
            else:
                failed_cancels += 1
            
            # Small delay between requests
            if i < len(selected_requests):
                time.sleep(2)
        
        # Summary
        summary = {
            'unsolved_requests_found': len(unsolved_requests),
            'selected_requests': len(selected_requests),
            'cancelled_requests': successful_cancels,
            'failed_requests': failed_cancels,
            'results': results,
            'timestamp': datetime.now().isoformat()
        }
        
        print(f"\n{'='*80}")
        print(f"UNSOLVED REQUESTS CANCELLATION SUMMARY")
        print(f"{'='*80}")
        print(f"Unsolved requests found: {summary['unsolved_requests_found']}")
        print(f"Selected for cancellation: {summary['selected_requests']}")
        print(f"Successfully cancelled: {summary['cancelled_requests']}")
        print(f"Failed to cancel: {summary['failed_requests']}")
        
        if failed_cancels > 0:
            print(f"\nFailed to cancel:")
            for result in results:
                if not result['success']:
                    request_title = result['request'].get('title', 'Unknown')
                    print(f"  - {request_title}")
                    if result.get('error'):
                        print(f"    Error: {result['error']}")
        
        if successful_cancels > 0:
            print(f"\nSuccessfully cancelled:")
            for result in results:
                if result['success']:
                    request_title = result['request'].get('title', 'Unknown')
                    print(f"  ✓ {request_title}")
        
        print(f"{'='*80}")
        
        return summary
        
    except Exception as e:
        print(f"Error in cancel_unsolved_requests: {str(e)}")
        return {
            'unsolved_requests_found': 0,
            'selected_requests': 0,
            'cancelled_requests': 0,
            'failed_requests': 0,
            'error': str(e),
            'results': []
        }

def login_and_cancel_unsolved_requests(username, password, headless=False, limit=None, no_confirm=False):
    """
    Login to sci-net.xyz, get unsolved requests, and cancel selected ones
    
    Args:
        username: Username for login
        password: Password for login
        headless: Whether to run browser in headless mode
        limit: Optional integer to limit the number of requests retrieved
        no_confirm: If True, automatically select all requests without user confirmation
    
    Returns:
        dict: Summary of cancellation results
    """
    driver = login_to_scinet(username, password, headless)
    if not driver:
        return None
    
    try:
        result = cancel_unsolved_requests(driver, limit, no_confirm)
        return result
    finally:
        print("Cancel unsolved requests process completed, closing browser.")
        driver.quit()

def get_username_with_timeout():
        """Get username from user with timeout"""
        def timeout_handler(signum, frame):
            print("\nTimeout: No username entered within 30 seconds. Exiting.")
            exit(1)
        if hasattr(signal, 'SIGALRM'):
            signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(30)
        try:
            username = input("Username: ").strip()
            if hasattr(signal, 'alarm'):
                signal.alarm(0)
            return username
        except KeyboardInterrupt:
            if hasattr(signal, 'alarm'):
                signal.alarm(0)
            print("\nOperation cancelled by user.")
            exit(1)
        except Exception as e:
            if hasattr(signal, 'alarm'):
                signal.alarm(0)
            print(f"Error getting username: {str(e)}")
            exit(1)
        finally:
            if hasattr(signal, 'alarm'):
                signal.alarm(0)

def get_password_with_timeout():
    """Get password from user with timeout"""
    def timeout_handler(signum, frame):
        print("\nTimeout: No password entered within 30 seconds. Exiting.")
        exit(1)
    if hasattr(signal, 'SIGALRM'):
        signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(30)
    try:
        password = getpass.getpass("Password: ")
        if hasattr(signal, 'alarm'):
            signal.alarm(0)
        return password
    except KeyboardInterrupt:
        if hasattr(signal, 'alarm'):
            signal.alarm(0)
        print("\nOperation cancelled by user.")
        exit(1)
    except Exception as e:
        if hasattr(signal, 'alarm'):
            signal.alarm(0)
        print(f"Error getting password: {str(e)}")
        exit(1)
    finally:
        if hasattr(signal, 'alarm'):
            signal.alarm(0)

def handle_credentials(args, parser):
    """Handle credential loading and validation"""
    global USERNAME, PASSWORD

    if args.credentials:
        credentials = load_credentials_from_json(args.credentials)
        if not credentials:
            print("Failed to load credentials from JSON file.")
            # Prompt user for username and password manually
            print("Please enter your username and password manually.")
            USERNAME = get_username_with_timeout()
            if not USERNAME:
                print("Error: No username provided")
                exit(1)
            PASSWORD = get_password_with_timeout()
            if not PASSWORD:
                print("Error: No password provided")
                exit(1)
        else:
            USERNAME = credentials['scinet_username']
            PASSWORD = credentials['scinet_password']
            print(f"Using credentials from file: {args.credentials}")
            print(f"Username: {USERNAME}")

def get_password_for_username(username):
    """Get password for username, using cache if available"""
    def timeout_handler(signum, frame):
        print("\nTimeout: No password entered within 30 seconds. Exiting.")
        exit(1)
        # Use the get_password_with_timeout function defined above

        # Check if we have a valid cache for this username (single-user cache)
        cache_data = None
        try:
            if os.path.exists(CACHE_FILE):
                with open(CACHE_FILE, 'rb') as f:
                    cache_data = pickle.load(f)
                # cache_data should be a dict with 'timestamp' and possibly 'cookies'
                if isinstance(cache_data, dict) and 'timestamp' in cache_data:
                    cache_age = datetime.now() - cache_data['timestamp']
                    if cache_age <= timedelta(hours=CACHE_DURATION_HOURS):
                        print(f"Using cached login for {username}")
                        return "cached"
        except Exception:
            pass

        print(f"No valid login cache found for {username}.")
        password = get_password_with_timeout()
        if not password:
            print("Error: No password provided")
            exit(1)
        return password

def handle_pdf_upload(args, headless_mode):
    """Handle PDF upload functionality"""
    pdf_files = []
    
    for path in args.pdf:
        path = os.path.expanduser(path)
        
        if os.path.isfile(path):
            if path.lower().endswith('.pdf'):
                pdf_files.append(path)
                print(f"Added PDF file: {path}")
            else:
                print(f"Warning: Skipping non-PDF file: {path}")
        elif os.path.isdir(path):
            print(f"Scanning directory recursively for PDFs: {path}")
            dir_pdfs = get_pdf_files_from_directory(path, recursive=True)
            pdf_files.extend(dir_pdfs)
        else:
            print(f"Warning: Path not found: {path}")
    
    if not pdf_files:
        print("Error: No valid PDF files found in the specified paths")
        exit(1)
    
    if len(pdf_files) == 1:
        print(f"Uploading single PDF file: {os.path.basename(pdf_files[0])}")
        login_and_upload_pdf(USERNAME, PASSWORD, pdf_files[0], headless=headless_mode)
    else:
        print(f"Uploading {len(pdf_files)} PDF files...")
        login_and_upload_multiple_pdfs(USERNAME, PASSWORD, pdf_files, headless=headless_mode)

def handle_doi_requests(args, headless_mode):
    """Handle DOI request functionality"""
    doi_reward_pairs = []
    seen_dois = set()
    
    for doi_arg in args.request_doi:
        doi_arg = os.path.expanduser(doi_arg)
        
        if os.path.isfile(doi_arg):
            print(f"Reading DOIs from file: {doi_arg}")
            file_pairs = read_dois_with_rewards_from_file(doi_arg)
            doi_reward_pairs.extend(file_pairs)
        else:
            if ',' in doi_arg:
                parts = doi_arg.split(',', 1)
                doi = parts[0].strip()
                try:
                    reward_tokens = int(parts[1].strip())
                    if reward_tokens < 1:
                        print(f"Error: Reward tokens must be at least 1 for DOI: {doi}")
                        exit(1)
                except ValueError:
                    print(f"Error: Invalid reward tokens '{parts[1].strip()}' for DOI: {doi}")
                    exit(1)
            else:
                doi = doi_arg.strip()
                reward_tokens = 1
            
            if is_valid_doi(doi):
                if doi in seen_dois:
                    print(f"Warning: Duplicate DOI found: '{doi}' - skipping")
                    continue
                
                seen_dois.add(doi)
                doi_reward_pairs.append((doi, reward_tokens))
                print(f"Added DOI: {doi} (reward tokens: {reward_tokens})")
            else:
                print(f"Error: Invalid DOI format: '{doi}'")
                print("DOI format should be like: 10.1000/182 or https://doi.org/10.1000/182")
                exit(1)
    
    if not doi_reward_pairs:
        print("Error: No valid DOIs found")
        exit(1)
    
    print(f"Requesting {len(doi_reward_pairs)} DOI{'s' if len(doi_reward_pairs) > 1 else ''}...")
    result = login_and_request_multiple_dois_with_rewards(USERNAME, PASSWORD, doi_reward_pairs, args.wait_seconds, headless=headless_mode)
    if result:
        print(f"\nDOI Request Result:")
        print(f"Successful requests: {result.get('successful_requests', 0)}")
        print(f"Failed requests: {result.get('failed_requests', 0)}")
    else:
        print("\nFailed to request DOIs")

def handle_fulfilled_doi_action(args, headless_mode, action_type):
    """Handle fulfilled DOI actions (accept/reject)"""
    doi = args.accept_fulfilled_doi if action_type == 'accept' else args.reject_fulfilled_doi
    
    if not is_valid_doi(doi):
        print(f"Error: Invalid DOI format: '{doi}'")
        print("DOI format should be like: 10.1000/182 or https://doi.org/10.1000/182")
        exit(1)
    
    if action_type == 'accept':
        result = login_and_accept_fulfilled_request_by_doi(USERNAME, PASSWORD, doi, headless=headless_mode)
        action_verb = "accept"
        past_tense = "accepted"
    else:
        reject_message = args.reject_message or "Paper quality does not meet requirements"
        result = login_and_reject_fulfilled_request_by_doi(USERNAME, PASSWORD, doi, reject_message, headless=headless_mode)
        action_verb = "reject"
        past_tense = "rejected"
    
    if result:
        print(f"\n{action_verb.title()} fulfilled request by DOI completed")
        if result.get('success'):
            print(f"✓ Successfully {past_tense} fulfilled request for DOI: {doi}")
            if action_type == 'reject':
                print(f"  Rejection message: '{reject_message}'")
        else:
            print(f"✗ Failed to {action_verb} fulfilled request for DOI: {doi}")
            if result.get('error'):
                print(f"  Error: {result['error']}")
    else:
        print(f"\nFailed to {action_verb} fulfilled request by DOI")

def handle_cancel_doi_action(args, headless_mode, request_type):
    """Handle cancel DOI actions (unsolved/waiting)"""
    doi = args.cancel_unsolved_doi if request_type == 'unsolved' else args.cancel_waiting_doi
    
    if not is_valid_doi(doi):
        print(f"Error: Invalid DOI format: '{doi}'")
        print("DOI format should be like: 10.1000/182 or https://doi.org/10.1000/182")
        exit(1)
    
    if request_type == 'unsolved':
        result = login_and_cancel_unsolved_request_by_doi(USERNAME, PASSWORD, doi, headless=headless_mode)
    else:
        result = login_and_cancel_waiting_request_by_doi(USERNAME, PASSWORD, doi, headless=headless_mode)
    
    if result:
        print(f"\nCancel {request_type} request by DOI completed")
        if result.get('success'):
            print(f"✓ Successfully cancelled {request_type} request for DOI: {doi}")
        else:
            print(f"✗ Failed to cancel {request_type} request for DOI: {doi}")
            if result.get('error'):
                print(f"  Error: {result['error']}")
    else:
        print(f"\nFailed to cancel {request_type} request by DOI")
        
def get_uploaded_files(driver, limit=None):
    """
    Get the list of uploaded files from sci-net.xyz/papers/uploads
    Returns a list of uploaded file dictionaries with details
    
    Args:
        driver: Selenium WebDriver instance
        limit: Optional integer to limit the number of files returned
    """
    try:
        print("Getting uploaded files from sci-net.xyz/papers/uploads...")
        
        # Navigate to the uploads page
        driver.get("https://sci-net.xyz/papers/uploads")
        
        # Wait for the page to load
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        
        debug_print("Looking for uploaded files section...")
        
        uploaded_files = []
        last_file_count = 0
        scroll_attempts = 0
        max_scroll_attempts = 100  # Prevent infinite scrolling
        
        while True:
            # Find uploaded files based on the HTML structure
            try:
                # Look for links containing articles with uploaded files
                uploaded_links = driver.find_elements(By.CSS_SELECTOR, "a[href*='/10.']")
                
                debug_print(f"Found {len(uploaded_links)} total potential uploaded file links")
                
                # Process new file elements
                for i in range(last_file_count, len(uploaded_links)):
                    # If we have a limit and reached it, stop processing
                    if limit is not None and limit > 0 and len(uploaded_files) >= limit:
                        debug_print(f"Reached target limit of {limit} uploaded files")
                        break
                    
                    link = uploaded_links[i]
                    
                    try:
                        # Check if this link contains an article with uploaded file
                        article_div = link.find_element(By.CSS_SELECTOR, "div.article")
                        
                        file_data = {
                            'index': len(uploaded_files) + 1,
                            'title': '',
                            'authors': '',
                            'journal': '',
                            'year': '',
                            'doi': '',
                            'status': 'uploaded',
                            'link': link.get_attribute("href"),
                            'datetime': '',
                            'file_size': '',
                            'upload_id': ''
                        }
                        
                        # Extract DOI from href (format: /10.xxxx/xxxxx)
                        href = link.get_attribute("href")
                        if href and '/10.' in href:
                            doi_start = href.find('/10.')
                            if doi_start != -1:
                                file_data['doi'] = href[doi_start + 1:]  # Remove leading slash
                        
                        # Get title
                        try:
                            title_element = article_div.find_element(By.CSS_SELECTOR, "div.title")
                            file_data['title'] = title_element.text.strip()
                        except:
                            pass
                        
                        # Get authors
                        try:
                            authors_element = article_div.find_element(By.CSS_SELECTOR, "div.authors")
                            file_data['authors'] = authors_element.text.strip()
                        except:
                            pass
                        
                        # Get journal
                        try:
                            journal_element = article_div.find_element(By.CSS_SELECTOR, "div.journal")
                            file_data['journal'] = journal_element.text.strip()
                        except:
                            pass
                        
                        # Get year
                        try:
                            year_element = article_div.find_element(By.CSS_SELECTOR, "div.year")
                            file_data['year'] = year_element.text.strip()
                        except:
                            pass
                        
                        # Get datetime
                        try:
                            datetime_element = article_div.find_element(By.CSS_SELECTOR, "div.datetime")
                            file_data['datetime'] = datetime_element.text.strip()
                        except:
                            pass
                        
                        # Get file size if available
                        try:
                            size_element = article_div.find_element(By.CSS_SELECTOR, "div.size")
                            file_data['file_size'] = size_element.text.strip()
                        except:
                            pass
                        
                        # Try to extract upload ID from various sources
                        try:
                            # From datetime (might be used as ID)
                            if file_data['datetime'] and file_data['datetime'].isdigit():
                                file_data['upload_id'] = file_data['datetime']
                            # From DOI as fallback
                            elif file_data['doi']:
                                file_data['upload_id'] = file_data['doi'].replace('/', '_').replace('.', '_')
                        except:
                            pass
                        
                        # Check if the file has meaningful information
                        # Require at least title or DOI to be valid
                        has_info = any([
                            file_data['title'],
                            file_data['doi']
                        ])
                        
                        if has_info:
                            uploaded_files.append(file_data)
                            debug_print(f"Parsed uploaded file {len(uploaded_files)}: {file_data['title'] or file_data['doi']}...")
                        else:
                            debug_print(f"Ignoring file {i+1}: no meaningful information found")
                    
                    except Exception as parse_error:
                        debug_print(f"Error parsing uploaded file {i+1}: {str(parse_error)}")
                        continue
                
                # If we have a limit and reached it, stop
                if limit is not None and limit > 0 and len(uploaded_files) >= limit:
                    debug_print(f"Reached target limit of {limit} uploaded files")
                    break
                
                # Check if we found new files
                current_file_count = len(uploaded_links)
                if current_file_count == last_file_count:
                    # No new files found, try scrolling
                    scroll_attempts += 1
                    if scroll_attempts >= max_scroll_attempts:
                        debug_print(f"Max scroll attempts ({max_scroll_attempts}) reached, stopping")
                        break
                    
                    debug_print(f"No new files found, scrolling down (attempt {scroll_attempts})...")
                    
                    # Scroll to the bottom of the page
                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    
                    # Wait for potential new content to load
                    time.sleep(2)
                    
                    # Check if new content was loaded
                    new_uploaded_links = driver.find_elements(By.CSS_SELECTOR, "a[href*='/10.']")
                    if len(new_uploaded_links) == current_file_count:
                        # Still no new files after scrolling and waiting
                        debug_print("No new files loaded after scrolling, assuming end of content")
                        break
                else:
                    # New files found, reset scroll attempts and update count
                    scroll_attempts = 0
                    last_file_count = current_file_count
                    debug_print(f"Found {current_file_count - last_file_count} new file elements")
            
            except Exception as container_error:
                debug_print(f"Error finding uploaded file containers: {str(container_error)}")
                break
        
        print(f"Successfully parsed {len(uploaded_files)} uploaded files (ignored empty results)")
        return uploaded_files
        
    except Exception as e:
        print(f"Error getting uploaded files: {str(e)}")
        return []
   
def format_uploaded_files(files):
    """
    Format the uploaded files list in a user-friendly manner
    """
    if not files:
        print("\nNo uploaded files found.")
        return
    
    print(f"\n{'='*80}")
    print(f"UPLOADED FILES ON SCI-NET.XYZ ({len(files)} total)")
    print(f"{'='*80}")
    
    for i, file_data in enumerate(files, 1):
        print(f"\n[{i}] {file_data['title'] or 'Untitled File'}")
        
        if file_data['authors']:
            print(f"    Authors: {file_data['authors']}")
        
        if file_data['year']:
            print(f"    Year: {file_data['year']}")
        
        if file_data['doi']:
            print(f"    DOI: {file_data['doi']}")
        
        if file_data['file_size']:
            print(f"    File Size: {file_data['file_size']}")
        
        if file_data['datetime']:
            print(f"    Uploaded: {file_data['datetime']}")
        
        if file_data['link']:
            print(f"    Link: {file_data['link']}")
        
        # Add separator between files (but not after the last one)
        if i < len(files):
            print(f"    {'-'*70}")
    
    print(f"\n{'='*80}")

def login_and_get_uploaded_files(username, password, headless=False, limit=None):
    """
    Login to sci-net.xyz and get the list of uploaded files
    Returns a list of uploaded file dictionaries
    
    Args:
        username: Username for login
        password: Password for login
        headless: Whether to run browser in headless mode
        limit: Optional integer to limit the number of files returned
    """
    driver = login_to_scinet(username, password, headless)
    if not driver:
        return []
    
    try:
        files = get_uploaded_files(driver, limit)
        format_uploaded_files(files)
        return files
    finally:
        print("Uploaded files retrieval completed, closing browser.")
        driver.quit()

def get_user_info_logged_in(username, password, headless=False):
    """
    Login and get user info by parsing the https://sci-net.xyz/@<username> page.

    Args:
        username: Username string
        password: Password string
        headless: Whether to run browser in headless mode

    Returns:
        dict: User info dictionary (fields: username, display_name, avatar_url, bio, stats, etc.)
    """
    driver = login_to_scinet(username, password, headless)
    if not driver:
        return None
    try:
        user_info = get_user_info(driver, username)
        return user_info
    finally:
        driver.quit()

def fetch_papers_category(driver, category, max_items=100):
    """
    Helper to fetch papers from a category page (requests, solutions, uploads).
    Returns a list of dicts with title, doi, year, link.
    """
    # If category is None or empty, fetch from /papers (all articles)
    if not category:
        url = "https://sci-net.xyz/papers"
    else:
        url = f"https://sci-net.xyz/papers/{category}"
    driver.get(url)
    WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.TAG_NAME, "body"))
    )
    items = []
    scroll_attempts = 0
    last_count = 0
    max_scroll_attempts = 10
    while True:
        links = driver.find_elements(By.CSS_SELECTOR, "a[href*='/10.']")
        for link in links[len(items):]:
            try:
                article_div = link.find_element(By.CSS_SELECTOR, "div.article")
                title = ""
                try:
                    title = article_div.find_element(By.CSS_SELECTOR, "div.title").text.strip()
                except Exception:
                    pass
                doi = ""
                href = link.get_attribute("href")
                if href and '/10.' in href:
                    doi_start = href.find('/10.')
                    if doi_start != -1:
                        doi = href[doi_start + 1:]
                year = ""
                try:
                    year = article_div.find_element(By.CSS_SELECTOR, "div.year").text.strip()
                except Exception:
                    pass
                items.append({
                    "title": title,
                    "doi": doi,
                    "year": year,
                    "link": href,
                })
                if len(items) >= max_items:
                    break
            except Exception:
                continue
        if len(items) >= max_items:
            break
        if len(links) == last_count:
            scroll_attempts += 1
            if scroll_attempts >= max_scroll_attempts:
                break
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1)
        else:
            scroll_attempts = 0
            last_count = len(links)
    return items

def get_user_info(driver, username):
    """
    Get user info by parsing the https://sci-net.xyz/@<username> page and extracting variables from JavaScript.
    Also fetches number and list of requests, solutions, and uploads from /papers/<category> pages.

    Args:
        driver: Selenium WebDriver instance
        username: Username string

    Returns:
        dict: User info dictionary (fields: username, display_name, avatar_url, bio, stats, balance, unsolved, etc.)
    """
    user_info = {
        'username': username,
        'display_name': '',
        'avatar_url': '',
        'bio': '',
        'stats': {},
        'profile_url': f"https://sci-net.xyz/@{username}",
        'balance': None,
        'unsolved': None,
        'uid': None,
        'registered': '',
        'last_seen': '',
        'requests_count': None,
        'uploads_count': None,
        'solutions_count': None,
        'requests_list': [],
        'solutions_list': [],
        'uploads_list': [],
        'total_articles_count': None,  # Added field for total number of articles
        'total_articles_list': [],     # Added field for all articles
    }
    try:
        profile_url = f"https://sci-net.xyz/@{username}"
        driver.get(profile_url)
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )

        # Avatar
        try:
            avatar_img = driver.find_element(By.CSS_SELECTOR, ".avatar img")
            user_info['avatar_url'] = avatar_img.get_attribute("src")
        except Exception:
            pass

        # Display name (may be in .name or .display-name)
        try:
            display_name_elem = driver.find_element(By.CSS_SELECTOR, ".name, .display-name")
            user_info['display_name'] = display_name_elem.text.strip()
        except Exception:
            user_info['display_name'] = username

        # Bio/about section
        try:
            bio_elem = driver.find_element(By.CSS_SELECTOR, ".bio, .about, .description")
            user_info['bio'] = bio_elem.text.strip()
        except Exception:
            pass

        # Stats (tokens, uploads, requests, etc.)
        try:
            stats = {}
            stat_elems = driver.find_elements(By.CSS_SELECTOR, ".stats .stat, .stat")
            for elem in stat_elems:
                try:
                    label = elem.find_element(By.CSS_SELECTOR, ".label").text.strip(': ')
                    value = elem.find_element(By.CSS_SELECTOR, ".value").text.strip()
                    stats[label.lower()] = value
                except Exception:
                    # Try alternative: text in format "Label: Value"
                    parts = elem.text.split(':', 1)
                    if len(parts) == 2:
                        stats[parts[0].strip().lower()] = parts[1].strip()
            user_info['stats'] = stats
        except Exception:
            pass

        # Optionally, parse other info (joined date, etc.)
        try:
            joined_elem = driver.find_element(By.XPATH, "//*[contains(text(),'Joined')]")
            user_info['joined'] = joined_elem.text.strip()
        except Exception:
            pass

        # Extract user info from JavaScript variables if available
        try:
            js_vars = driver.execute_script("""
                let result = {};
                try { result.uid = typeof uid !== 'undefined' ? uid : null; } catch(e) { result.uid = null; }
                try { result.uname = typeof uname !== 'undefined' ? uname : null; } catch(e) { result.uname = null; }
                try { result.balance = typeof balance !== 'undefined' ? balance : null; } catch(e) { result.balance = null; }
                try { result.unsolved = typeof unsolved !== 'undefined' ? unsolved : null; } catch(e) { result.unsolved = null; }
                return result;
            """)
            if js_vars:
                user_info['uid'] = js_vars.get('uid')
                user_info['balance'] = js_vars.get('balance')
                user_info['unsolved'] = js_vars.get('unsolved')
                if js_vars.get('uname'):
                    user_info['display_name'] = js_vars['uname']
        except Exception as e:
            debug_print(f"Error extracting JS variables: {str(e)}")

        # Parse additional info from .info section if present
        try:
            info_div = driver.find_element(By.CSS_SELECTOR, ".info")
            # Name (may already be set)
            try:
                name_div = info_div.find_element(By.CSS_SELECTOR, ".name")
                user_info['display_name'] = name_div.text.strip()
            except Exception:
                pass
            # Times: registered and last seen
            try:
                times_div = info_div.find_element(By.CSS_SELECTOR, ".times")
                times_text = times_div.get_attribute("innerHTML").replace('<br>', '\n')
                lines = [line.strip() for line in times_text.split('\n') if line.strip()]
                if lines:
                    user_info['registered'] = lines[0]
                if len(lines) > 1:
                    user_info['last_seen'] = lines[1]
            except Exception:
                pass
            # Numbers: requests and uploads
            try:
                numbers_div = info_div.find_element(By.CSS_SELECTOR, ".numbers")
                numbers_text = numbers_div.text
                req_match = re.search(r'requests\s+(\d+)', numbers_text)
                up_match = re.search(r'uploads\s+(\d+)', numbers_text)
                if req_match:
                    user_info['requests_count'] = int(req_match.group(1))
                if up_match:
                    user_info['uploads_count'] = int(up_match.group(1))
            except Exception:
                pass
        except Exception:
            pass

        # Requests
        try:
            reqs = fetch_papers_category(driver, "requests", max_items=100)
            user_info['requests_list'] = reqs
            user_info['requests_count'] = len(reqs)
        except Exception as e:
            debug_print(f"Error fetching requests: {str(e)}")
        # Solutions
        try:
            sols = fetch_papers_category(driver, "solutions", max_items=100)
            user_info['solutions_list'] = sols
            user_info['solutions_count'] = len(sols)
        except Exception as e:
            debug_print(f"Error fetching solutions: {str(e)}")
        # Uploads
        try:
            ups = fetch_papers_category(driver, "uploads", max_items=100)
            user_info['uploads_list'] = ups
            user_info['uploads_count'] = len(ups)
        except Exception as e:
            debug_print(f"Error fetching uploads: {str(e)}")

        # Fetch total number of articles (all categories)
        try:
            all_articles = fetch_papers_category(driver, "", max_items=1000)
            user_info['total_articles_list'] = all_articles
            user_info['total_articles_count'] = len(all_articles)
        except Exception as e:
            debug_print(f"Error fetching all articles: {str(e)}")

    except Exception as e:
        debug_print(f"Error in get_user_info: {str(e)}")
    return user_info

def handle_user_info(args, headless_mode, details=False):
    """Handle user info/profile display after login

    Args:
        args: argparse.Namespace
        headless_mode: bool
        details: bool, if True print lists of requests, uploads, solutions
    """
    info = get_user_info_logged_in(USERNAME, PASSWORD, headless=headless_mode)
    if info:
        print("\nUser Info:")
        print(f"  Username: {info.get('username')}")
        print(f"  Display Name: {info.get('display_name')}")
        print(f"  Profile URL: {info.get('profile_url')}")
        print(f"  Avatar: {info.get('avatar_url')}")
        print(f"  Bio: {info.get('bio')}")
        if info.get('balance') is not None:
            print(f"  Balance: {info.get('balance')}")
        if info.get('unsolved') is not None:
            print(f"  Unsolved: {info.get('unsolved')}")
        if info.get('requests_count') is not None:
            print(f"  Requests: {info.get('requests_count')}")
        if info.get('uploads_count') is not None:
            print(f"  Uploads: {info.get('uploads_count')}")
        if info.get('solutions_count') is not None:
            print(f"  Solutions: {info.get('solutions_count')}")
        if info.get('total_articles_count') is not None:
            print(f"  Total Articles: {info.get('total_articles_count')}")
        if info.get('stats'):
            print("  Stats:")
            for k, v in info['stats'].items():
                print(f"    {k.title()}: {v}")
        if info.get('registered'):
            print(f"  Registered: {info.get('registered')}")
        if info.get('last_seen'):
            print(f"  Last Seen: {info.get('last_seen')}")
        if details:
            # Print requests list
            if info.get('requests_list'):
                print("\nRequests:")
                for i, req in enumerate(info['requests_list'], 1):
                    print(f"  [{i}] {req.get('title', '')} ({req.get('year', '')}) DOI: {req.get('doi', '')} Link: {req.get('link', '')}")
            # Print uploads list
            if info.get('uploads_list'):
                print("\nUploads:")
                for i, up in enumerate(info['uploads_list'], 1):
                    print(f"  [{i}] {up.get('title', '')} ({up.get('year', '')}) DOI: {up.get('doi', '')} Link: {up.get('link', '')}")
            # Print solutions list
            if info.get('solutions_list'):
                print("\nSolutions:")
                for i, sol in enumerate(info['solutions_list'], 1):
                    print(f"  [{i}] {sol.get('title', '')} ({sol.get('year', '')}) DOI: {sol.get('doi', '')} Link: {sol.get('link', '')}")
            # Print all articles list
            if info.get('total_articles_list'):
                print("\nAll Articles:")
                for i, art in enumerate(info['total_articles_list'], 1):
                    print(f"  [{i}] {art.get('title', '')} ({art.get('year', '')}) DOI: {art.get('doi', '')} Link: {art.get('link', '')}")
    else:
        print("Failed to retrieve user info.")

def print_default_paths():
    """
    Print all default paths and configuration values used by scinet.py
    """
    print("Default configuration paths and values:")
    print(f"  Cache directory: {get_cache_directory()}")
    print(f"  Download directory: {get_download_directory()}")
    print(f"  Cache file: {CACHE_FILE}")
    print(f"  Cache duration (hours): {CACHE_DURATION_HOURS}")
    print(f"  Log file: {LOG_FILE}")
    print(f"  Default download dir: {DEFAULT_DOWNLOAD_DIR}")

def execute_action(args, headless_mode):
    """Execute the appropriate action based on arguments"""
    if getattr(args, "print_default", False):
        print_default_paths()
        return
    if getattr(args, "user_info", False):
        handle_user_info(args, headless_mode)
        return
    if args.pdf:
        handle_pdf_upload(args, headless_mode)
    elif args.request_doi:
        handle_doi_requests(args, headless_mode)
    elif args.get_active_requests is not None:
        requests = login_and_get_active_requests(USERNAME, PASSWORD, headless=headless_mode, limit=args.get_active_requests if args.get_active_requests > 0 else None)
        print(f"\nFound {len(requests)} active requests" if requests else "\nNo active requests found or failed to retrieve requests")
    elif args.get_fulfilled_requests:
        result = login_and_check_fulfilled_requests(USERNAME, PASSWORD, headless=headless_mode)
        print(f"\nFulfilled requests check completed" if result else "\nFailed to check fulfilled requests")
    elif args.get_uploaded_files is not None:
        files = login_and_get_uploaded_files(USERNAME, PASSWORD, headless=headless_mode, limit=args.get_uploaded_files if args.get_uploaded_files > 0 else None)
        print(f"\nFound {len(files)} uploaded files" if files else "\nNo uploaded files found or failed to retrieve files")
    elif args.accept_fulfilled_requests:
        result = login_and_accept_fulfilled_requests(USERNAME, PASSWORD, headless=headless_mode, no_confirm=args.noconfirm)
        if result:
            print(f"\nAccept fulfilled requests completed")
            print(f"Accepted: {result.get('accepted_requests', 0)}, Failed: {result.get('failed_requests', 0)}")
        else:
            print("\nFailed to accept fulfilled requests")
    elif args.reject_fulfilled_requests:
        result = login_and_reject_fulfilled_requests(USERNAME, PASSWORD, headless=headless_mode, reject_message=args.reject_message, no_confirm=args.noconfirm)
        if result:
            print(f"\nReject fulfilled requests completed")
            print(f"Rejected: {result.get('rejected_requests', 0)}, Failed: {result.get('failed_requests', 0)}")
        else:
            print("\nFailed to reject fulfilled requests")
    elif args.accept_fulfilled_doi:
        handle_fulfilled_doi_action(args, headless_mode, 'accept')
    elif args.reject_fulfilled_doi:
        handle_fulfilled_doi_action(args, headless_mode, 'reject')
    elif args.solve_active_requests is not None:
        result = login_and_solve_active_requests(USERNAME, PASSWORD, headless=headless_mode, limit=args.solve_active_requests if args.solve_active_requests > 0 else None, no_confirm=args.noconfirm)
        if result:
            print(f"\nSolve active requests completed")
            print(f"Solved: {result.get('solved_requests', 0)}, Failed: {result.get('failed_requests', 0)}")
        else:
            print("\nFailed to solve active requests")
    elif args.cancel_waiting_requests is not None:
        result = login_and_cancel_waiting_requests(USERNAME, PASSWORD, headless=headless_mode, limit=args.cancel_waiting_requests if args.cancel_waiting_requests > 0 else None, no_confirm=args.noconfirm)
        if result:
            print(f"\nCancel waiting requests completed")
            print(f"Cancelled: {result.get('cancelled_requests', 0)}, Failed: {result.get('failed_requests', 0)}")
        else:
            print("\nFailed to cancel waiting requests")
    elif args.get_unsolved_requests is not None:
        requests = login_and_get_unsolved_requests(USERNAME, PASSWORD, headless=headless_mode, limit=args.get_unsolved_requests if args.get_unsolved_requests > 0 else None)
        print(f"\nFound {len(requests)} unsolved requests" if requests else "\nNo unsolved requests found or failed to retrieve requests")
    elif args.cancel_unsolved_requests is not None:
        result = login_and_cancel_unsolved_requests(USERNAME, PASSWORD, headless=headless_mode, limit=args.cancel_unsolved_requests if args.cancel_unsolved_requests > 0 else None, no_confirm=args.noconfirm)
        if result:
            print(f"\nCancel unsolved requests completed")
            print(f"Cancelled: {result.get('cancelled_requests', 0)}, Failed: {result.get('failed_requests', 0)}")
        else:
            print("\nFailed to cancel unsolved requests")
    elif args.cancel_unsolved_doi:
        handle_cancel_doi_action(args, headless_mode, 'unsolved')
    elif args.solve_doi:
        result = login_and_solve_request_by_doi(USERNAME, PASSWORD, args.solve_doi, args.solve_pdf, headless=headless_mode)
        if result:
            print(f"\nSolve request by DOI completed")
            if result.get('success'):
                print(f"✓ Successfully solved request for DOI: {args.solve_doi}")
                print(f"  PDF: {os.path.basename(args.solve_pdf)}")
            else:
                print(f"✗ Failed to solve request for DOI: {args.solve_doi}")
                if result.get('error'):
                    print(f"  Error: {result['error']}")
        else:
            print("\nFailed to solve request by DOI")

def validate_arguments(args, parser):
    """Validate command line arguments"""
    # Allow --print-default to be used alone
    if getattr(args, "print_default", False):
        return

    # Allow --clear-cache to be used alone
    if getattr(args, "clear_cache", False) and sum([
        bool(args.pdf), 
        bool(args.request_doi), 
        args.get_active_requests is not None, 
        bool(args.get_fulfilled_requests),
        bool(args.accept_fulfilled_requests),
        bool(args.reject_fulfilled_requests),
        bool(args.accept_fulfilled_doi),
        bool(args.reject_fulfilled_doi),
        args.solve_active_requests is not None,
        args.cancel_waiting_requests is not None,
        args.get_unsolved_requests is not None,
        args.cancel_unsolved_requests is not None,
        bool(args.cancel_unsolved_doi),
        bool(args.solve_doi),
        args.get_uploaded_files is not None,
        bool(getattr(args, "user_info", False)),
        bool(getattr(args, "print_default", False)),
        bool(getattr(args, "credentials", None))
    ]) == 1:
        return

    # Allow --credentials to be used alone
    if getattr(args, "credentials", None) and sum([
        bool(args.pdf), 
        bool(args.request_doi), 
        args.get_active_requests is not None, 
        bool(args.get_fulfilled_requests),
        bool(args.accept_fulfilled_requests),
        bool(args.reject_fulfilled_requests),
        bool(args.accept_fulfilled_doi),
        bool(args.reject_fulfilled_doi),
        args.solve_active_requests is not None,
        args.cancel_waiting_requests is not None,
        args.get_unsolved_requests is not None,
        args.cancel_unsolved_requests is not None,
        bool(args.cancel_unsolved_doi),
        bool(args.solve_doi),
        args.get_uploaded_files is not None,
        bool(getattr(args, "user_info", False)),
        bool(getattr(args, "print_default", False)),
        bool(getattr(args, "clear_cache", False))
    ]) == 1:
        return

    if bool(args.solve_doi) != bool(args.solve_pdf):
        parser.error("--solve-doi and --solve-pdf must be used together")
    
    valid_options = [
        bool(args.pdf), 
        bool(args.request_doi), 
        args.get_active_requests is not None, 
        bool(args.get_fulfilled_requests),
        bool(args.accept_fulfilled_requests),
        bool(args.reject_fulfilled_requests),
        bool(args.accept_fulfilled_doi),
        bool(args.reject_fulfilled_doi),
        args.solve_active_requests is not None,
        args.cancel_waiting_requests is not None,
        args.get_unsolved_requests is not None,
        args.cancel_unsolved_requests is not None,
        bool(args.cancel_unsolved_doi),
        bool(args.solve_doi),
        args.get_uploaded_files is not None,
        bool(getattr(args, "user_info", False)),
        bool(getattr(args, "clear_cache", False)),
        bool(getattr(args, "print_default", False)),
        bool(getattr(args, "credentials", None))
    ]
    
    if not any(valid_options):
        parser.error("One of --pdf, --request-doi, --get-active-requests, --get-fulfilled-requests, --accept-fulfilled-requests, --reject-fulfilled-requests, --accept-fulfilled-doi, --reject-fulfilled-doi, --solve-active-requests, --cancel-waiting-requests, --get-unsolved-requests, --cancel-unsolved-requests, --cancel-unsolved-doi, --solve-doi (with --solve-pdf), --get-uploaded-files, --user-info, --credentials, --clear-cache, or --print-default must be specified")
    
    if sum(valid_options) > 1:
        parser.error("Only one of --pdf, --request-doi, --get-active-requests, --get-fulfilled-requests, --accept-fulfilled-requests, --reject-fulfilled-requests, --accept-fulfilled-doi, --reject-fulfilled-doi, --solve-active-requests, --cancel-waiting-requests, --get-unsolved-requests, --cancel-unsolved-requests, --cancel-unsolved-doi, --solve-doi (with --solve-pdf), --get-uploaded-files, --user-info, --credentials, --clear-cache, or --print-default can be specified at a time")

def main():
    # Get the parent package name from the module's __name__
    parent_package = __name__.split('.')[0] if '.' in __name__ else None

    if parent_package is None:
        program_name = 'scinet'
    elif '_' in parent_package:
        # If the parent package has an underscore, strip it
        parent_package = parent_package[:parent_package.index('_')]
        program_name = f"{parent_package} scinet"
    
    parser = argparse.ArgumentParser(
        prog=program_name, 
        description='Login to sci-net.xyz and upload PDF or request paper by DOI',
        epilog='''
    Examples:
      # Upload PDF files
      %(prog)s --pdf paper1.pdf paper2.pdf
      %(prog)s --pdf ~/Downloads/research_papers/
      
      # Request papers by DOI
      %(prog)s --request-doi 10.1038/nature12373
      %(prog)s --request-doi 10.1038/nature12373,5 10.1126/science.1234567,3
      %(prog)s --request-doi dois.txt
      
      # Get active requests (all or limited)
      %(prog)s --get-active-requests
      %(prog)s --get-active-requests 10
      
      # Check and manage fulfilled requests
      %(prog)s --get-fulfilled-requests
      %(prog)s --accept-fulfilled-requests
      %(prog)s --reject-fulfilled-requests --reject-message "Poor quality scan"
      %(prog)s --accept-fulfilled-doi 10.1038/nature12373
      
      # Solve requests from others
      %(prog)s --solve-active-requests
      %(prog)s --solve-doi 10.1038/nature12373 --solve-pdf solution.pdf
      
      # Manage your own requests
      %(prog)s --get-unsolved-requests
      %(prog)s --cancel-unsolved-requests
      %(prog)s --cancel-unsolved-doi 10.1038/nature12373
      
      # Use credentials file and other options
      %(prog)s --credentials ~/.scinet_creds.json --pdf paper.pdf
      %(prog)s --no-headless --verbose --request-doi 10.1038/nature12373
      %(prog)s --noconfirm --accept-fulfilled-requests
    ''',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    # Try to set up autocomplete before adding arguments
    autocomplete_available = setup_argument_autocomplete(parser)
    
    # Add arguments (some may have been added in setup_argument_autocomplete)
    if not autocomplete_available:
        parser.add_argument('--pdf', nargs='+', help='Path(s) to PDF file(s) to upload, or directory containing PDFs (can specify multiple paths separated by spaces)')
        parser.add_argument('--request-doi', nargs='+', help='DOI(s) to request: single DOI with optional reward tokens (DOI,tokens), multiple DOIs with optional reward tokens separated by spaces, or path to text file containing DOIs and optional reward tokens (one per line, format: DOI or DOI,tokens). Default reward tokens: 1')
        parser.add_argument('--solve-pdf', help='Path to PDF file to upload as solution (must be used with --solve-doi)')
    
    parser.add_argument('--accept-fulfilled-doi', help='DOI of a specific fulfilled request to accept')
    parser.add_argument('--reject-fulfilled-doi', help='DOI of a specific fulfilled request to reject')
    parser.add_argument('--get-active-requests', type=int, nargs='?', const=-1, metavar='LIMIT', help='Get list of active requests which you and others made but have not been fulfilled (optional: limit number of results)')
    parser.add_argument('--get-fulfilled-requests', action='store_true', help='Get list of fulfilled requests which others solved for you')
    parser.add_argument('--get-uploaded-files', type=int, nargs='?', const=-1, metavar='LIMIT', help='Get list of uploaded files which you have uploaded (optional: limit number of results)')
    parser.add_argument('--accept-fulfilled-requests', action='store_true', help='Accept fulfilled requests which others solved for you')
    parser.add_argument('--reject-fulfilled-requests', action='store_true', help='Reject fulfilled requests which others solved for you')
    parser.add_argument('--solve-active-requests', type=int, nargs='?', const=-1, metavar='LIMIT', help='Solve active requests from others (optional: limit number of requests to fetch)')
    parser.add_argument('--cancel-waiting-requests', type=int, nargs='?', const=-1, metavar='LIMIT', help='Cancel waiting requests which you own(optional: limit number of requests to fetch)')
    parser.add_argument('--get-unsolved-requests', type=int, nargs='?', const=-1, metavar='LIMIT', help='Get list of unsolved requests which you made but have not been solved (optional: limit number of results)')
    parser.add_argument('--cancel-unsolved-requests', type=int, nargs='?', const=-1, metavar='LIMIT', help='Cancel unsolved requests which you own (optional: limit number of requests to fetch)')
    parser.add_argument('--cancel-unsolved-doi', help='DOI of a specific unsolved request to cancel')
    parser.add_argument('--solve-doi', help='DOI of a specific request to solve (must be used with --solve-pdf)')
    parser.add_argument('--reject-message', help='Custom rejection message (for reject-fulfilled-requests)')
    parser.add_argument('--wait-seconds', type=int, default=50, help='Seconds to wait for DOI search results (default: 50)')
    parser.add_argument('--clear-cache', action='store_true', help='Clear login cache before running')
    parser.add_argument('--verbose', action='store_true', help='Enable verbose debug output')
    parser.add_argument('--no-headless', action='store_true', help='Disable headless mode and show browser window')
    parser.add_argument('--noconfirm', action='store_true', help='Automatically proceed with default options without user confirmation')
    parser.add_argument('--credentials', help='Path to JSON file containing login credentials (format: {"scinet_username": "user", "scinet_password": "pass"})')
    parser.add_argument('--user-info', action='store_true', help='Show user info/profile (tokens, stats, etc) after login')
    parser.add_argument('--print-default', action='store_true', help='Print default configuration paths and values used by scinet.py')

    # Show installation hint if argcomplete is not available
    if not autocomplete_available and VERBOSE:
        print("Info: Install 'argcomplete' package for command-line autocompletion: pip install argcomplete")
        print("Then run: activate-global-python-argcomplete --user")
    
    args = parser.parse_args()
    
    # Set global verbose flag
    VERBOSE = args.verbose
    
    # Determine headless mode (default is True, unless --no-headless is specified)
    headless_mode = not args.no_headless
    
    # Handle credentials and username
    handle_credentials(args, parser)
    
    # Validate arguments
    validate_arguments(args, parser)
    
    # Clear cache if requested
    if args.clear_cache and os.path.exists(CACHE_FILE):
        os.remove(CACHE_FILE)
        print("Login cache cleared")

    # Execute the appropriate action
    execute_action(args, headless_mode)

if __name__ == "__main__":
    main()
