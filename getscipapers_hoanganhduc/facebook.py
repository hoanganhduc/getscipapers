# Facebook Scraper with Selenium and BeautifulSoup
# Originally from https://github.com/abdosabry21/Facebook-scraping

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import SessionNotCreatedException
from bs4 import BeautifulSoup
import time
import random
import argparse
import re
import html
import pickle
import os
import platform
import signal
import sys
from . import getpapers

if platform.system() == 'Windows':
    import msvcrt
import asyncio
import json
import datetime
import os
import shutil
import sys
import getpass

USERNAME = "" # Replace with your Facebook username
PASSWORD = "" # Replace with your Facebook password

# Global cache file location for Facebook login sessions and default download folder
def get_app_directories():
    """Get the appropriate cache and download directory paths based on the operating system"""
    system = platform.system()
    
    if system == "Windows":
        # Use AppData/Local directory on Windows
        cache_dir = os.path.join(os.environ.get('LOCALAPPDATA', os.path.expanduser('~')), 'getscipapers', 'facebook')
        download_dir = os.path.join(os.path.expanduser('~'), 'Downloads', 'getscipapers', 'facebook')
    elif system == "Darwin":  # macOS
        # Use ~/Library/Caches directory on macOS for cache, Downloads for downloads
        cache_dir = os.path.join(os.path.expanduser('~'), 'Library', 'Caches', 'getscipapers', 'facebook')
        download_dir = os.path.join(os.path.expanduser('~'), 'Downloads', 'getscipapers', 'facebook')
    else:  # Linux and other Unix-like systems
        # Use ~/.config directory on Linux for cache, Downloads for downloads
        cache_dir = os.path.join(os.path.expanduser('~'), '.config', 'getscipapers', 'facebook')
        download_dir = os.path.join(os.path.expanduser('~'), 'Downloads', 'getscipapers', 'facebook')
    
    # Create the directories if they don't exist
    os.makedirs(cache_dir, exist_ok=True)
    os.makedirs(download_dir, exist_ok=True)
    
    return cache_dir, download_dir

# Set up global paths
_CACHE_DIR, _DOWNLOAD_DIR = get_app_directories()
CACHE_FILE = os.path.join(_CACHE_DIR, 'facebook_session_cache.pkl')
DOWNLOAD_FOLDER = _DOWNLOAD_DIR

class FacebookScraper:
    def __init__(self, email, password, verbose=False, headless=True):
        self.email = email
        self.password = password
        self.driver = None
        self.verbose = verbose
        self.headless = headless
        
    def load_credentials(self, json_file_path=None):
        """Load username and password from a JSON file"""
        if json_file_path is None:
            # Look for credentials file in the same directory as the script
            script_dir = os.path.dirname(os.path.abspath(__file__))
            json_file_path = os.path.join(script_dir, 'credentials.json')
        
        try:
            if os.path.exists(json_file_path):
                self.log(f"Loading credentials from: {json_file_path}")
                with open(json_file_path, 'r') as f:
                    credentials = json.load(f)
                
                # Update instance variables with loaded credentials
                if 'fb_username' in credentials or 'fb_email' in credentials:
                    self.email = credentials.get('fb_username', credentials.get('fb_email', self.email))
                    self.log("Username/email loaded from file")

                if 'fb_password' in credentials:
                    self.password = credentials['fb_password']
                    self.log("Password loaded from file")
                
                return True
            else:
                self.log(f"Credentials file not found at: {json_file_path}")
                self.log("Create a credentials.json file with format: {\"fb_username\": \"your_email\", \"fb_password\": \"your_password\"}")
                return False
                
        except Exception as e:
            self.log(f"Error loading credentials from {json_file_path}: {e}")
            return False

    def log(self, message):
        """Print debug messages if verbose mode is enabled"""
        if self.verbose:
            print(f"[DEBUG] {message}")
        
    def initialize_driver(self):
        """Initialize the Chrome webdriver with custom options and support for non-BMP characters"""
        self.log("Initializing Chrome webdriver...")
        options = webdriver.ChromeOptions()
        
        # Add headless mode if enabled
        if self.headless:
            options.add_argument("--headless=new")
            self.log("Running in headless mode")
        else:
            self.log("Running in graphic mode")
        
        # Use a subdirectory of the cache dir for Chrome user data
        user_data_dir = os.path.join(_CACHE_DIR, "chrome_user_data")
        os.makedirs(user_data_dir, exist_ok=True)
        options.add_argument(f"--user-data-dir={user_data_dir}")
        self.log(f"Using Chrome user data directory: {user_data_dir}")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument("--disable-notifications")
        options.add_argument("--disable-popup-blocking")
        options.add_argument("--disable-save-password-bubble")
        options.add_argument("--disable-infobars")
        options.add_argument("--disable-extensions-ui")
        options.add_argument("--disable-component-extensions-with-background-pages")
        options.add_argument("--no-sandbox")  # Often required in Docker
        options.add_argument("--disable-crash-reporter")  # Disable crash reporting
        options.add_experimental_option("prefs", {
            "profile.default_content_setting_values.notifications": 2,
            "profile.default_content_settings.popups": 0,
            "profile.password_manager_enabled": False,
            "credentials_enable_service": False,
            "profile.default_content_setting_values.media_stream": 2,
            "profile.default_content_setting_values.geolocation": 2
        })

        # Enable support for non-BMP characters (e.g., emojis, rare CJK, etc.)
        # This is mainly a matter of ensuring correct input handling in send_keys.
        # For Chrome, we can set the LANG environment variable and font rendering options.
        # Also, ensure UTF-8 encoding is used.
        os.environ["LANG"] = "en_US.UTF-8"
        options.add_argument("--lang=en-US.UTF-8")
        options.add_argument("--disable-features=RendererCodeIntegrity")  # Sometimes helps with emoji rendering
            
        self.driver = webdriver.Chrome(options=options)    
        self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        self.log("Webdriver initialized successfully")
        
    def simulate_human_typing(self, element, text):
        """Simulate human-like typing patterns"""
        self.log(f"Typing text: {text[:20]}{'...' if len(text) > 20 else ''}")
        for char in text:
            element.send_keys(char)
            time.sleep(random.uniform(0.1, 0.3))
            if random.random() < 0.1:
                pause_time = random.uniform(0.3, 0.7)
                self.log(f"Random pause: {pause_time:.2f}s")
                time.sleep(pause_time)

    def click_see_more_buttons(self):
        """Click all 'See more' buttons to expand post content"""
        self.log("Looking for 'See more' buttons...")
        see_more_count = 0
        
        # Multiple selectors for "See more" buttons
        see_more_selectors = [
            "//div[contains(text(), 'See more')]",
            "//span[contains(text(), 'See more')]",
            "//div[contains(@aria-label, 'See more')]",
            "//div[contains(text(), 'See More')]",
            "//span[contains(text(), 'See More')]",
            "//div[text()='See more']",
            "//span[text()='See more']",
            "//div[@role='button' and contains(., 'See more')]",
            "//span[@role='button' and contains(., 'See more')]"
        ]
        
        for selector in see_more_selectors:
            try:
                see_more_buttons = self.driver.find_elements(By.XPATH, selector)
                for button in see_more_buttons:
                    try:
                        # Check if button is visible and clickable
                        if button.is_displayed() and button.is_enabled():
                            # Scroll to the button to ensure it's in view
                            self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", button)
                            time.sleep(1)
                            
                            # Try to click using JavaScript if regular click fails
                            try:
                                button.click()
                            except:
                                self.driver.execute_script("arguments[0].click();", button)
                            
                            see_more_count += 1
                            self.log(f"Clicked 'See more' button #{see_more_count}")
                            time.sleep(random.uniform(1, 2))  # Wait for content to load
                            
                    except Exception as e:
                        self.log(f"Could not click 'See more' button: {e}")
                        continue
                        
            except Exception as e:
                self.log(f"Error finding 'See more' buttons with selector {selector}: {e}")
                continue
        
        if see_more_count > 0:
            self.log(f"Successfully clicked {see_more_count} 'See more' buttons")
            time.sleep(3)  # Wait for all content to fully load
        else:
            self.log("No 'See more' buttons found or clickable")
                
    def login(self):
        """Login to Facebook with session caching"""
        
        # Try to load existing session
        if os.path.exists(CACHE_FILE):
            self.log("Found existing session cache, attempting to restore...")
            try:
                with open(CACHE_FILE, 'rb') as f:
                    cookies = pickle.load(f)
                
                # Navigate to Facebook first
                self.driver.get("https://www.facebook.com")
                time.sleep(3)
                
                # Add cookies to current session
                for cookie in cookies:
                    try:
                        self.driver.add_cookie(cookie)
                    except Exception as e:
                        self.log(f"Could not add cookie: {e}")
                
                # Refresh page to apply cookies
                self.driver.refresh()
                time.sleep(5)
                
                # Check if login was successful by looking for user-specific elements
                if self.is_logged_in():
                    self.log("✅ Successfully logged in using cached session!")
                    return
                else:
                    self.log("❌ Cached session expired, proceeding with fresh login...")
                    os.remove(CACHE_FILE)  # Remove invalid cache
                    
            except Exception as e:
                self.log(f"Error loading cached session: {e}")
                if os.path.exists(CACHE_FILE):
                    os.remove(CACHE_FILE)
        
        # Perform fresh login
        self.log("Performing fresh login...")
        self.log("Navigating to Facebook login page...")
        self.driver.get("https://www.facebook.com/login")

        # Prompt for email and password if not provided
        if not self.email or not self.password:
            def get_input_with_timeout(prompt, timeout=30):
                if platform.system() == "Windows":
                    print(prompt, end='', flush=True)
                    start_time = time.time()
                    input_chars = []
                    while True:
                        if msvcrt.kbhit():
                            char = msvcrt.getch()
                            if char == b'\r':
                                print()
                                return ''.join(input_chars)
                            elif char == b'\x08':
                                if input_chars:
                                    input_chars.pop()
                                    print('\b \b', end='', flush=True)
                            else:
                                try:
                                    decoded_char = char.decode('utf-8')
                                    input_chars.append(decoded_char)
                                    print(decoded_char, end='', flush=True)
                                except UnicodeDecodeError:
                                    pass
                        if time.time() - start_time > timeout:
                            print(f"\n⏰ Timeout: No response received within {timeout} seconds.")
                            return None
                        time.sleep(0.1)
                else:
                    def alarm_handler(signum, frame):
                        raise TimeoutError()
                    try:
                        signal.signal(signal.SIGALRM, alarm_handler)
                        signal.alarm(timeout)
                        result = input(prompt)
                        signal.alarm(0)
                        return result
                    except (TimeoutError, KeyboardInterrupt):
                        signal.alarm(0)
                        print(f"\n⏰ Timeout: No response received within {timeout} seconds.")
                        return None

            if not self.email:
                self.email = get_input_with_timeout("Enter your Facebook email/username: ")
                if not self.email:
                    self.log("❌ Login failed: No email provided (timeout or empty input)")
                    print("❌ Login failed: No email provided (timeout or empty input)")
                    raise Exception("Login failed: No email provided")
            if not self.password:
                if platform.system() == "Windows":
                    # getpass does not support timeout, so use fallback
                    self.password = get_input_with_timeout("Enter your Facebook password: ")
                else:
                    try:
                        self.password = getpass.getpass("Enter your Facebook password: ")
                    except Exception:
                        self.password = get_input_with_timeout("Enter your Facebook password: ")
                if not self.password:
                    self.log("❌ Login failed: No password provided (timeout or empty input)")
                    print("❌ Login failed: No password provided (timeout or empty input)")
                    raise Exception("Login failed: No password provided")
        
        # Enter email
        self.log("Looking for email input field...")
        email_input = WebDriverWait(self.driver, 10).until(
            EC.presence_of_element_located((By.NAME, "email"))
        )
        self.log("Email input found, entering email...")
        self.simulate_human_typing(email_input, self.email)
        
        # Enter password
        self.log("Looking for password input field...")
        password_input = WebDriverWait(self.driver, 10).until(
            EC.presence_of_element_located((By.NAME, "pass"))
        )
        self.log("Password input found, entering password...")
        self.simulate_human_typing(password_input, self.password)
        
        # Click login button
        self.log("Looking for login button...")
        login_button = self.driver.find_element(By.XPATH, "//button[@type='submit']")
        self.log("Login button found, clicking...")
        ActionChains(self.driver)\
            .move_to_element(login_button)\
            .pause(random.uniform(0.2, 0.4))\
            .click()\
            .perform()
            
        self.log("Waiting 15 seconds for login to complete...")
        time.sleep(15)
        
        # Save session cookies for future use
        if self.is_logged_in():
            self.log("Login successful, saving session cache...")
            try:
                cookies = self.driver.get_cookies()
                with open(CACHE_FILE, 'wb') as f:
                    pickle.dump(cookies, f)
                self.log(f"✅ Session cached successfully to {CACHE_FILE}")
            except Exception as e:
                self.log(f"Error saving session cache: {e}")
        else:
            self.log("❌ Login may have failed - not saving cache")

    def is_logged_in(self):
        """Check if user is currently logged in to Facebook"""
        try:
            # Look for elements that only appear when logged in
            login_indicators = [
                "div[role='banner']",  # Top navigation bar
                "div[data-testid='Facepile']",  # Friends suggestions
                "div[aria-label*='Account']",  # Account menu
                "a[aria-label*='Profile']"  # Profile link
            ]
            
            for indicator in login_indicators:
                elements = self.driver.find_elements(By.CSS_SELECTOR, indicator)
                if elements and any(elem.is_displayed() for elem in elements):
                    return True
            
            # Check current URL for login indicators
            current_url = self.driver.current_url.lower()
            if "login" in current_url or "checkpoint" in current_url:
                return False
                
            return "facebook.com" in current_url and "login" not in current_url
            
        except Exception as e:
            self.log(f"Error checking login status: {e}")
            return False
        
    def navigate_to_profile(self, profile_url):
        """Navigate to a specific Facebook profile"""
        self.log(f"Navigating to profile: {profile_url}")
        self.driver.get(profile_url)
        self.log("Waiting 4 seconds for page to load...")
        time.sleep(4)
        
    def slow_scroll(self, step=500):
        """Scroll the page slowly"""
        self.log(f"Scrolling down by {step} pixels...")
        self.driver.execute_script(f"window.scrollBy(0, {step});")
        self.log("Waiting 2 seconds after scroll...")
        time.sleep(2)

    def clean_text(self, text):
        """Clean and format text for better readability"""
        if not text:
            return ""
        
        # Remove extra whitespace and normalize
        text = re.sub(r'\s+', ' ', text.strip())
        
        # Remove redundant repetition patterns
        words = text.split()
        if len(words) > 3:
            # Remove if same word/phrase repeats more than 3 times
            unique_words = []
            for word in words:
                if unique_words.count(word) < 3:
                    unique_words.append(word)
            text = ' '.join(unique_words)
        
        return text

    def format_engagement_count(self, count_text):
        """Format engagement counts (likes, comments, shares) to be more readable"""
        if not count_text or count_text == "0":
            return "0"
        
        # Clean the text and extract numbers
        clean_count = re.sub(r'[^\d.,KMB]', '', count_text.upper())
        
        # Handle K, M, B suffixes
        if 'K' in clean_count:
            return clean_count
        elif 'M' in clean_count:
            return clean_count
        elif 'B' in clean_count:
            return clean_count
        
        # Extract just numbers if no suffix
        numbers = re.findall(r'\d+', clean_count)
        return numbers[0] if numbers else "0"
        
    def extract_posts_with_bs(self):
        """Extract posts data using BeautifulSoup, robustly removing leading Facebook blockquote spam, preserving newlines."""
        self.log("Extracting page source...")
        page_source = self.driver.page_source
        soup = BeautifulSoup(page_source, "html.parser")
        posts_data = []

        # Try multiple selectors for posts
        post_selectors = [
            "div[data-pagelet*='FeedUnit']",
            "div.x1yztbdb.x1n2onr6.xh8yej3.x1ja2u2z",
            "div[role='article']",
            "div.x1n2onr6.x1ja2u2z"
        ]

        posts = []
        for selector in post_selectors:
            posts = soup.select(selector)
            if posts:
                self.log(f"Found {len(posts)} posts using selector: {selector}")
                break

        def remove_leading_facebook_blockquotes(soup_fragment):
            """
            Remove all leading blockquote spam (e.g., 'Facebook' blockquotes) from a soup fragment.
            Returns a cleaned soup fragment.
            """
            # Remove all blockquotes that contain only 'Facebook' or are empty, at any depth
            blockquotes = soup_fragment.find_all("blockquote")
            for bq in blockquotes:
                bq_text = bq.get_text(strip=True)
                if bq_text.lower() in ("facebook", ""):
                    parent = bq.parent
                    bq.decompose()
                    # Remove empty parent divs if any
                    while parent and parent.name == "div" and not parent.get_text(strip=True):
                        grandparent = parent.parent
                        parent.decompose()
                        parent = grandparent
            return soup_fragment

        def get_text_with_newlines(element):
            """Extract text from a BeautifulSoup element, preserving newlines between block-level elements."""
            # If element is None, return empty string
            if element is None:
                return ""
            # Use '\n' as separator for block-level elements
            # This will preserve newlines between <div>, <p>, <br>, etc.
            text = element.get_text(separator="\n")
            # Remove excessive consecutive newlines (max 2)
            text = re.sub(r'\n{3,}', '\n\n', text)
            return text

        for i, post in enumerate(posts):
            try:
                self.log(f"Processing post {i+1}/{len(posts)}...")

                # Extract author name
                author_element = post.select_one("strong a, h3 a, span > a[role='link']")
                author = self.clean_text(author_element.get_text()) if author_element else "Unknown Author"

                # Extract post text with improved selection - now getting more content
                post_text = ""
                text_selectors = [
                    "div[data-ad-preview='message']",
                    "div[dir='auto'] span",
                    "div.xdj266r.x11i5rnm.xat24cr.x1mh8g0r.x1vvkbs",
                    "div[style*='text-align: start'] span",
                    "div[data-ad-comet-preview='message']",
                    "span[dir='auto']"
                ]

                all_text_parts = []
                for selector in text_selectors:
                    text_elements = post.select(selector)
                    for element in text_elements:
                        # Remove leading Facebook blockquote spam
                        cleaned_element = remove_leading_facebook_blockquotes(element)
                        # Extract text with newlines preserved
                        text = get_text_with_newlines(cleaned_element)
                        text = self.clean_text(text)
                        if text and len(text) > 10 and text not in ' '.join(all_text_parts):
                            all_text_parts.append(text)

                post_text = '\n'.join(all_text_parts)
                post_text = self.clean_text(post_text)[:2000]  # Increased length limit to capture more content

                # Extract engagement metrics with better formatting
                likes = "0"
                comments_count = "0"
                shares = "0"

                # Look for engagement section
                engagement_elements = post.select("div[role='button'] span, span[role='img'] + span")
                for elem in engagement_elements:
                    text = elem.get_text().strip()
                    if any(word in text.lower() for word in ['like', 'love', 'reaction']):
                        likes = self.format_engagement_count(text)
                    elif any(word in text.lower() for word in ['comment', 'reply']):
                        comments_count = self.format_engagement_count(text)
                    elif any(word in text.lower() for word in ['share']):
                        shares = self.format_engagement_count(text)

                # Extract post time with better formatting
                time_selectors = [
                    "a[role='link'] span",
                    "span[id*='date']",
                    "abbr[data-utime]"
                ]

                post_time = "Unknown"
                for selector in time_selectors:
                    time_element = post.select_one(selector)
                    if time_element:
                        time_text = time_element.get_text().strip()
                        if any(word in time_text.lower() for word in ['ago', 'hour', 'min', 'day', 'week', 'month', 'year']):
                            post_time = time_text
                            break

                # Extract comments (limited to most relevant ones)
                comment_elements = post.select("div[aria-label*='Comment'] div[dir='auto']")
                actual_comments = []
                for comment in comment_elements[:5]:  # Limit to 5 comments
                    # Remove leading Facebook blockquote spam in comments
                    cleaned_comment = remove_leading_facebook_blockquotes(comment)
                    comment_text = get_text_with_newlines(cleaned_comment)
                    comment_text = self.clean_text(comment_text)
                    if comment_text and len(comment_text) > 5 and comment_text != post_text:
                        actual_comments.append(comment_text[:300])  # Increased comment length

                # Only add posts with meaningful content
                if post_text and len(post_text) > 20:
                    posts_data.append({
                        "author": author,
                        "post_text": post_text,
                        "likes": likes,
                        "comments_count": comments_count,
                        "shares": shares,
                        "post_time": post_time,
                        "top_comments": actual_comments
                    })
                    self.log(f"Post {i+1} successfully processed - Author: {author}")

            except Exception as e:
                self.log(f"Error extracting post {i+1} data: {e}")

        self.log(f"Total posts extracted: {len(posts_data)}")
        return posts_data
        
    def remove_duplicates(self, data_list):
        """Remove duplicate posts based on content similarity"""
        original_count = len(data_list)
        self.log(f"Removing duplicates from {original_count} posts...")
        
        unique_data = []
        seen_texts = set()
        
        for data in data_list:
            # Use first 100 characters of post text as uniqueness key
            text_key = data['post_text'][:100].lower().strip()
            if text_key not in seen_texts and len(text_key) > 10:
                seen_texts.add(text_key)
                unique_data.append(data)
                
        self.log(f"Removed {original_count - len(unique_data)} duplicates, {len(unique_data)} unique posts remain")
        return unique_data
        
    def extract_doi_from_text(self, text):
        """Extract DOI numbers from text using the imported function"""
        if not text:
            return []
        try:
            return getpapers.extract_dois_from_text(text)
        except Exception as e:
            self.log(f"Error extracting DOIs: {e}")
            return []

    def scrape_posts(self, max_posts, having_doi=False, download=None):
        """Scrape a specified number of posts with optional DOI filtering and PDF download"""
        
        # Validate and set download parameter
        if download is not None and not os.path.exists(download):
            self.log(f"Download folder not found: {download}, using default download folder: {DOWNLOAD_FOLDER}")
            download = DOWNLOAD_FOLDER
        
        if download and not having_doi:
            self.log("Download option requires having_doi to be True. Setting having_doi=True automatically.")
            having_doi = True
        
        doi_filter = " with DOIs" if having_doi else ""
        download_filter = f" (with PDF download to {download})" if download else ""
        self.log(f"Starting to scrape {max_posts} posts{doi_filter}{download_filter}...")
        
        all_posts = []
        all_posts_processed = []  # Track all processed posts for DOI filtering
        scroll_count = 0
        max_scrolls = 25 if not having_doi else 50  # Increased scrolls when filtering for DOIs
        
        while len(all_posts) < max_posts and scroll_count < max_scrolls:
            scroll_count += 1
            self.log(f"Scroll iteration {scroll_count}...")
            
            # Click "See more" buttons before extracting posts
            self.click_see_more_buttons()
            
            posts = self.extract_posts_with_bs()
            
            # Filter out notification content and posts without meaningful content
            for post in posts:
                # Skip notification posts
                if self.is_notification_content(post):
                    continue
                    
                # Skip posts without meaningful content
                if not self.has_meaningful_content(post):
                    continue
                    
                post['doi_numbers'] = self.extract_doi_from_text(post['post_text'])
            
            # Remove notification posts and posts without meaningful content
            posts = [post for post in posts if not self.is_notification_content(post) and self.has_meaningful_content(post)]
            
            all_posts_processed.extend(posts)
            all_posts_processed = self.remove_duplicates(all_posts_processed)
            
            if having_doi:
                # Filter posts that have DOI numbers
                posts_with_dois = [post for post in all_posts_processed if post.get('doi_numbers')]
                all_posts = posts_with_dois
                self.log(f"Found {len(all_posts)} posts with DOIs out of {len(all_posts_processed)} total posts processed")
            else:
                all_posts = all_posts_processed
                self.log(f"Extracted {len(all_posts)} unique posts so far")
            
            self.slow_scroll()
            
            if len(all_posts) >= max_posts:
                self.log("Target number of posts reached")
                break
            
        # Final attempt to click any remaining "See more" buttons
        self.log("Final attempt to expand any remaining content...")
        self.click_see_more_buttons()
        
        final_posts = all_posts[:max_posts]
        
        # Download PDFs after all extraction is completed
        if download:
            self.log(f"Starting PDF download for {len(final_posts)} posts to {download}")
            total_downloaded = 0
            for post in final_posts:
                post['downloaded_pdfs'] = []
                if post.get('doi_numbers'):
                    for doi in post['doi_numbers']:
                        try:
                            self.log(f"Attempting to download PDF for DOI: {doi} to {download}")
                            try:
                                # Try to get existing event loop
                                loop = asyncio.get_event_loop()
                                if loop.is_running():
                                    # If loop is already running, use run_coroutine_threadsafe
                                    import concurrent.futures
                                    with concurrent.futures.ThreadPoolExecutor() as executor:
                                        future = executor.submit(asyncio.run, getpapers.download_by_doi(doi, download, no_download=False))
                                        pdf_path = future.result()
                                else:
                                    # If no loop is running, use asyncio.run
                                    pdf_path = asyncio.run(getpapers.download_by_doi(doi, download, no_download=False))
                            except RuntimeError:
                                # If there's no event loop, create one
                                pdf_path = asyncio.run(getpapers.download_by_doi(doi, download, no_download=False))

                            if pdf_path and os.path.exists(pdf_path):
                                absolute_path = os.path.abspath(pdf_path)
                                post['downloaded_pdfs'].append(absolute_path)
                                total_downloaded += 1
                                self.log(f"Successfully downloaded PDF: {absolute_path}")
                            else:
                                self.log(f"Failed to download PDF for DOI: {doi}")
                        except Exception as e:
                            self.log(f"Error downloading PDF for DOI {doi}: {e}")
        
        self.log(f"Scraping completed. Returning {len(final_posts)} posts")
        
        # Log DOI extraction and download summary
        total_dois = sum(len(post.get('doi_numbers', [])) for post in final_posts)
        if download:
            total_downloaded = sum(len(post.get('downloaded_pdfs', [])) for post in final_posts)
            self.log(f"Download enabled: Found {len(final_posts)} posts with {total_dois} DOI numbers, successfully downloaded {total_downloaded} PDFs to {download}")
        elif having_doi:
            self.log(f"DOI filtering enabled: Found {len(final_posts)} posts with {total_dois} DOI numbers")
        else:
            self.log(f"Extracted {total_dois} DOI numbers from {len(final_posts)} posts")
        
        return final_posts

    def has_meaningful_content(self, post):
        """Check if a post has meaningful content beyond just basic information"""
        if not post or not isinstance(post, dict):
            return False
        
        post_text = post.get('post_text', '').strip()
        
        # Must have sufficient text content
        if len(post_text) < 50:
            return False
        
        # Skip posts that are mostly links or URLs
        url_pattern = r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
        urls = re.findall(url_pattern, post_text)
        url_length = sum(len(url) for url in urls)
        
        # If more than 60% of the content is URLs, consider it not meaningful
        if len(post_text) > 0 and url_length / len(post_text) > 0.6:
            return False
        
        # Skip posts that are just repetitive characters or spam-like content
        if len(set(post_text.lower().replace(' ', ''))) < 5:  # Too few unique characters
            return False
        
        # Skip posts with excessive repetition
        words = post_text.lower().split()
        if len(words) > 5:
            unique_words = set(words)
            if len(unique_words) / len(words) < 0.3:  # Less than 30% unique words
                return False
        
        # Skip posts that are mostly emojis or special characters
        text_chars = sum(1 for char in post_text if char.isalnum() or char.isspace())
        if len(post_text) > 0 and text_chars / len(post_text) < 0.5:
            return False
        
        # Skip common low-value content patterns
        low_value_patterns = [
            r'^\.+$',  # Just dots
            r'^-+$',   # Just dashes
            r'^\s*$',  # Just whitespace
            r'^[\d\s]+$',  # Just numbers and spaces
            r'^[^\w\s]*$',  # Just special characters
        ]
        
        for pattern in low_value_patterns:
            if re.match(pattern, post_text):
                return False
        
        return True

    def is_notification_content(self, post):
        """Check if a post is notification content and should be excluded"""
        if not post or not isinstance(post, dict):
            return True
        
        post_text = post.get('post_text', '').lower()
        author = post.get('author', '').lower()
        
        # Skip posts with very short content (likely notifications)
        if len(post_text.strip()) < 30:
            return True
        
        # Skip notification-like content
        notification_indicators = [
            'was live',
            'went live',
            'is live',
            'shared a memory',
            'shared a post',
            'shared an event',
            'added a new photo',
            'updated their',
            'changed their',
            'is feeling',
            'is at',
            'checked in',
            'was tagged',
            'reacted to',
            'commented on',
            'liked a',
            'shared their location',
            'added to their story',
            'created an event',
            'joined',
            'left the group'
        ]
        
        # Check if post contains notification indicators
        for indicator in notification_indicators:
            if indicator in post_text:
                return True
        
        # Skip posts from Facebook system accounts
        system_accounts = [
            'facebook',
            'meta',
            'administrator',
            'admin',
            'moderator'
        ]
        
        for account in system_accounts:
            if account in author:
                return True
        
        return False

    def print_posts(self, posts_data):
        """Print the scraped posts data in a human-readable format"""
        self.log(f"Printing {len(posts_data)} posts...")
        print("\n" + "="*80)
        print(f"FACEBOOK POSTS SUMMARY - {len(posts_data)} Posts Found")
        print("="*80)
        
        for idx, post in enumerate(posts_data, start=1):
            print(f"\n📄 POST #{idx}")
            print("-" * 40)
            
            print(f"👤 Author: {post['author']}")
            print(f"⏰ Posted: {post['post_time']}")
            print(f"\n📝 Content:")
            
            # Format post text with proper line breaks - now showing more content
            content = post['post_text']
            if len(content) > 1000:  # Increased display limit
                content = content[:997] + "..."
            print(f"   {content}")
            
            print(f"\n📊 Engagement:")
            print(f"   👍 Likes: {post['likes']}")
            print(f"   💬 Comments: {post['comments_count']}")
            print(f"   🔗 Shares: {post['shares']}")
            
            # Show DOI information if available
            post_dois = post.get('doi_numbers', [])
            if post_dois:
                print(f"\n📚 DOI Information:")
                print(f"   📄 DOIs found ({len(post_dois)}):")
                for doi in post_dois:
                    print(f"      • {doi}")
            
            # Show download information if available
            downloaded_pdfs = post.get('downloaded_pdfs', [])
            if downloaded_pdfs:
                print(f"\n⬇️ Downloaded PDFs ({len(downloaded_pdfs)}):")
                for pdf_path in downloaded_pdfs:
                    print(f"      • {pdf_path}")
            elif post_dois:
                print(f"\n⬇️ Download Status: No PDFs downloaded for this post")
            
            # Show top comments if available
            if post['top_comments']:
                print(f"\n💭 Top Comments ({len(post['top_comments'])}):")
                for i, comment in enumerate(post['top_comments'][:3], 1):
                    comment_preview = comment[:150] + "..." if len(comment) > 150 else comment  # Increased comment preview
                    print(f"   {i}. {comment_preview}")
            
            print("\n" + "-"*80)
        
        print(f"\n✅ Summary: Successfully extracted {len(posts_data)} posts")
        
        # Summary of total DOIs found and downloads
        total_dois = sum(len(post.get('doi_numbers', [])) for post in posts_data)
        total_downloads = sum(len(post.get('downloaded_pdfs', [])) for post in posts_data)
        
        if total_dois > 0:
            print(f"📚 Total DOIs extracted: {total_dois}")
        
        if total_downloads > 0:
            print(f"⬇️ Total PDFs downloaded: {total_downloads}")
        
        print("="*80)

    def create_post(self, post_content, image_path=None):
        """Create a new post on Facebook"""

        # Check for non-BMP characters (codepoints > 0xFFFF)
        if any(ord(char) > 0xFFFF for char in post_content):
            self.log("❌ Error: Post content contains non-BMP characters (e.g., rare CJK, emoji, etc.) which are not supported by Chrome driver.")
            print("❌ Error: Post content contains non-BMP characters (e.g., rare CJK, emoji, etc.) which are not supported by Chrome driver. Please remove or replace them and try again.")
            return False

        self.log("Starting to create a new post...")

        try:
            # # Navigate to Facebook home page
            # self.log("Navigating to Facebook home...")
            # self.driver.get("https://www.facebook.com")
            # time.sleep(8)  # Increased wait time for page load

            # Find the post composer using the most reliable approach
            self.log("Looking for post composer...")

            composer = None
            try:
                # Try to find the composer by looking for a button with "Write something..." or "What's on your mind?" or "What's do you think" text
                composer = None
                try:
                    composer_candidates = self.driver.find_elements(
                        By.XPATH,
                        "//div[@role='button' and ("
                        ".//span[contains(text(), 'Write something...')] or "
                        ".//span[contains(text(), \"What's on your mind\")] or "
                        ".//span[contains(text(), \"What's do you think\")]"
                        ")]"
                    )
                    for element in composer_candidates:
                        if element.is_displayed():
                            composer = element
                            self.log("Found composer using 'Write something...' or similar button")
                            break
                except Exception as e:
                    self.log(f"Error finding composer with 'Write something...' or similar: {e}")

                # Fallback: try to find composer anywhere on the page if not found below navigation
                if not composer:
                    self.log("No composer found below navigation, using general composer search...")
                    composer_selectors = [
                        "div[aria-label*='What'][role='button']",
                        "div[data-testid='status-attachment-mentions-input']",
                        "div[role='button'][aria-label*='post']",
                        "div[data-testid='react-composer-root']",
                        "div.notranslate._5rpu"
                    ]

                    for selector in composer_selectors:
                        try:
                            potential_composers = self.driver.find_elements(By.CSS_SELECTOR, selector)
                            for element in potential_composers:
                                if element.is_displayed() and element.location['y'] < 600:  # Top portion of page
                                    composer = element
                                    self.log(f"Found composer using selector: {selector}")
                                    break
                            if composer:
                                break
                        except:
                            continue

            except Exception as e:
                self.log(f"Navigation container search failed: {e}")
                # Final fallback - original approach
                self.log("Using original composer search approach...")
                try:
                    potential_composers = self.driver.find_elements(By.XPATH, 
                        "//div[@role='main']//div[@role='button' or @tabindex='0' or @data-testid or contains(@class, 'composer')]")

                    for element in potential_composers:
                        if element.is_displayed() and element.location['y'] < 500:  # Top half of page
                            composer = element
                            self.log("Found composer using original approach")
                            break
                except Exception as fallback_e:
                    self.log(f"Original composer search also failed: {fallback_e}")

            if not composer:
                raise Exception("Could not find the post composer")

            # Click on the composer to open the post creation dialog
            self.log("Clicking on post composer...")
            self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", composer)
            time.sleep(2)
            composer.click()
            time.sleep(5)  # Increased wait time for composer to open

            # Click on the center of the composer before typing
            self.log("Clicking on center of composer...")
            try:
                # Get the composer dialog that opened
                composer_dialog = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "div[role='dialog'], div[data-testid='composer-dialog']"))
                )

                # Scroll to ensure the dialog is in view and click directly
                self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", composer_dialog)
                time.sleep(2)

                # Use ActionChains to move to element and click (safer than calculating coordinates)
                ActionChains(self.driver).move_to_element(composer_dialog).click().perform()
                time.sleep(2)

            except Exception as e:
                self.log(f"Could not click center of composer: {e}")

            # Immediately type the post content after clicking composer
            self.log("Typing post content...")

            # Only type newlines, paste everything else
            lines = post_content.split('\n')
            for line_idx, line in enumerate(lines):
                if line.strip():  # Skip empty lines
                    # Paste the entire line content
                    self.driver.switch_to.active_element.send_keys(line)

                # Type newline if not the last line
                if line_idx < len(lines) - 1:
                    self.driver.switch_to.active_element.send_keys(Keys.SHIFT + Keys.ENTER)
                    time.sleep(random.uniform(0.1, 0.3))

            # Reduced wait time since we're only typing newlines
            base_wait = 1
            self.log(f"Waiting {base_wait} seconds for content to be processed")
            time.sleep(base_wait)

            # Handle image upload if provided
            if image_path:
                self.log(f"Uploading image: {image_path}")
                try:
                    # Look for photo/video button
                    photo_button_selectors = [
                        "div[aria-label*='Photo/video']",
                        "div[data-testid='media-sprout']",
                        "input[type='file'][accept*='image']",
                        "div[role='button'][aria-label*='Photo']"
                    ]

                    file_input = None
                    for selector in photo_button_selectors:
                        try:
                            if 'input' in selector:
                                file_input = self.driver.find_element(By.CSS_SELECTOR, selector)
                            else:
                                button = self.driver.find_element(By.CSS_SELECTOR, selector)
                                button.click()
                                time.sleep(3)
                                file_input = self.driver.find_element(By.CSS_SELECTOR, "input[type='file']")

                            if file_input:
                                break
                        except:
                            continue

                    if file_input:
                        file_input.send_keys(image_path)
                        self.log("Image uploaded successfully")
                        time.sleep(6)  # Wait for image to process
                    else:
                        self.log("Could not find file input for image upload")

                except Exception as e:
                    self.log(f"Error uploading image: {e}")

            # Find and click the Post button
            self.log("Looking for Post button...")
            post_button_selectors = [
                "div[role='button'][aria-label='Post']",
                "div[data-testid='react-composer-post-button']",
                "button[data-testid='react-composer-post-button']",
                "div[role='button']:has-text('Post')",
                "button:has-text('Post')"
            ]

            post_button = None
            for selector in post_button_selectors:
                try:
                    post_button = WebDriverWait(self.driver, 15).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                    )
                    if post_button:
                        self.log(f"Found Post button with selector: {selector}")
                        break
                except:
                    continue

            # Try XPath as fallback for Post button
            if not post_button:
                xpath_selectors = [
                    "//div[@role='button' and @aria-label='Post']",
                    "//div[@role='button' and contains(text(), 'Post')]",
                    "//button[contains(text(), 'Post')]"
                ]

                for xpath in xpath_selectors:
                    try:
                        post_buttons = self.driver.find_elements(By.XPATH, xpath)
                        for button in post_buttons:
                            # Decode HTML entities in button text
                            button_text = html.unescape(button.text)
                            if 'post' in button_text.lower():
                                post_button = button
                                self.log(f"Found Post button with XPath: {xpath}")
                                break

                        if post_button:
                            break
                    except:
                        continue

            if not post_button:
                raise Exception("Could not find the Post button")

            # Click the Post button
            self.log("Clicking Post button...")
            self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", post_button)
            time.sleep(2)

            try:
                post_button.click()
            except:
                # Try JavaScript click as fallback
                self.driver.execute_script("arguments[0].click();", post_button)

            self.log("Post button clicked, waiting for post to be published...")
            time.sleep(10)  # Wait for post to be published

            # Verify post was created by checking for success indicators
            try:
                # Look for post confirmation or return to main feed
                WebDriverWait(self.driver, 15).until(
                    lambda driver: "facebook.com" in driver.current_url and 
                    len(driver.find_elements(By.CSS_SELECTOR, "div[role='main']")) > 0
                )
                self.log("✅ Post created successfully!")
                return True

            except:
                self.log("⚠️ Post may have been created, but couldn't verify")
                return True

        except Exception as e:
            self.log(f"❌ Error creating post: {e}")
            return False

    def search_posts(self, search_query, max_posts=10, group_id=None, user_id=None, having_doi=False, download=None):
        """Search for posts containing specific content, optionally in a specific group or from a specific user, optionally filtering for posts with DOI numbers, and optionally downloading PDFs"""
        
        # Validate and set download parameter
        if download is not None and not os.path.exists(download):
            self.log(f"Download folder not found: {download}, using default download folder: {DOWNLOAD_FOLDER}")
            download = DOWNLOAD_FOLDER
        
        if download and not having_doi:
            self.log("Download option requires having_doi to be True. Setting having_doi=True automatically.")
            having_doi = True
        
        context = f"from user {user_id}" if user_id else (f"in group {group_id}" if group_id else "on Facebook")
        doi_filter = " with DOIs" if having_doi else ""
        download_filter = f" (with PDF download to {download})" if download else ""
        self.log(f"Searching for posts containing: '{search_query}'{doi_filter}{download_filter} {context}")
        
        try:
            # Navigate to specific user search if user_id is provided
            if user_id:
                self.log(f"Searching posts from user: {user_id}")
                # Construct direct search URL for the user
                search_url = f"https://www.facebook.com/profile/{user_id}/search/?q={search_query}"
                self.log(f"Navigating to: {search_url}")
                self.driver.get(search_url)
                time.sleep(5)
            # Navigate to specific group search if group_id is provided
            elif group_id:
                self.log(f"Searching in group: {group_id}")
                # Construct direct search URL for the group
                search_url = f"https://www.facebook.com/groups/{group_id}/search/?q={search_query}"
                self.log(f"Navigating to: {search_url}")
                self.driver.get(search_url)
                time.sleep(5)
            else:
                # Original search approach for general posts
                try:
                    search_box = WebDriverWait(self.driver, 10).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='search'], input[placeholder*='Search']"))
                    )
                    search_box.clear()
                    self.simulate_human_typing(search_box, search_query)
                    search_box.send_keys("\n")  # Press Enter
                    time.sleep(5)
                    
                    # Click on "Posts" tab if available
                    try:
                        posts_tab = self.driver.find_element(By.XPATH, "//div[@role='tab' and contains(text(), 'Posts')]")
                        posts_tab.click()
                        time.sleep(3)
                    except:
                        self.log("Posts tab not found, continuing with current results")
                        
                except Exception as e:
                    self.log(f"Could not use search box, trying direct URL approach: {e}")
            
            # Scrape search results
            self.log(f"Scraping search results for '{search_query}'{doi_filter}{download_filter} {context}...")
            search_results = []
            all_posts_processed = []  # Track all processed posts for DOI filtering
            scroll_count = 0
            max_scrolls = 25 if not having_doi else 40  # Increased scrolls when filtering for DOIs
            
            while len(search_results) < max_posts and scroll_count < max_scrolls:
                scroll_count += 1
                self.log(f"Search scroll iteration {scroll_count}...")
                
                # Click "See more" buttons before extracting posts
                self.click_see_more_buttons()
                
                # Extract posts from the search results page
                posts = self.extract_posts_with_bs()
                
                # Filter out notification content and posts without meaningful content
                posts = [post for post in posts if not self.is_notification_content(post) and self.has_meaningful_content(post)]
                
                if user_id or group_id:
                    # For user or group searches, add all posts since they're already filtered by Facebook
                    for post in posts:
                        post['search_query'] = search_query
                        if user_id:
                            post['user_id'] = user_id
                        if group_id:
                            post['group_id'] = group_id
                        
                        # Extract DOI numbers from post content (but don't download yet)
                        post['doi_numbers'] = self.extract_doi_from_text(post['post_text'])
                        
                        all_posts_processed.append(post)
                else:
                    # For general searches, filter posts that contain the search query
                    for post in posts:
                        post_text_lower = post['post_text'].lower()
                        search_query_lower = search_query.lower()
                        
                        # Also check comments for search query
                        comment_matches = 0
                        for comment in post.get('top_comments', []):
                            if search_query_lower in comment.lower():
                                comment_matches += 1
                        
                        if search_query_lower in post_text_lower or comment_matches > 0:
                            # Add search relevance score
                            post['search_relevance'] = post_text_lower.count(search_query_lower) + comment_matches
                            post['search_query'] = search_query
                            
                            # Extract DOI numbers from post content (but don't download yet)
                            post['doi_numbers'] = self.extract_doi_from_text(post['post_text'])
                            
                            all_posts_processed.append(post)
                
                # Remove duplicates from all processed posts
                all_posts_processed = self.remove_duplicates(all_posts_processed)
                
                if having_doi:
                    # Filter posts that have DOI numbers
                    posts_with_dois = [post for post in all_posts_processed if post.get('doi_numbers')]
                    search_results = posts_with_dois
                    self.log(f"Found {len(search_results)} posts with DOIs out of {len(all_posts_processed)} total posts processed")
                else:
                    search_results = all_posts_processed
                    self.log(f"Found {len(search_results)} relevant posts so far...")
                
                if len(search_results) >= max_posts:
                    self.log("Target number of search results reached")
                    break
                    
                self.slow_scroll()
            
            # Sort by relevance (posts with more mentions of search term first) - only for general searches
            if not user_id and not group_id:
                search_results.sort(key=lambda x: x.get('search_relevance', 0), reverse=True)
            
            final_results = search_results[:max_posts]
            
            # Download PDFs after all extraction is completed
            if download:
                self.log(f"Starting PDF download for {len(final_results)} posts to {download}")
                total_downloaded = 0
                for post in final_results:
                    post['downloaded_pdfs'] = []
                    if post.get('doi_numbers'):
                        for doi in post['doi_numbers']:
                            try:
                                self.log(f"Attempting to download PDF for DOI: {doi} to {download}")
                                try:
                                    # Try to get existing event loop
                                    loop = asyncio.get_event_loop()
                                    if loop.is_running():
                                        # If loop is already running, use run_coroutine_threadsafe
                                        import concurrent.futures
                                        with concurrent.futures.ThreadPoolExecutor() as executor:
                                            future = executor.submit(asyncio.run, getpapers.download_by_doi(doi, download, no_download=False))
                                            pdf_path = future.result()
                                    else:
                                        # If no loop is running, use asyncio.run
                                        pdf_path = asyncio.run(getpapers.download_by_doi(doi, download, no_download=False))
                                except RuntimeError:
                                    # If there's no event loop, create one
                                    pdf_path = asyncio.run(getpapers.download_by_doi(doi, download, no_download=False))

                                if pdf_path and os.path.exists(pdf_path):
                                    absolute_path = os.path.abspath(pdf_path)
                                    post['downloaded_pdfs'].append(absolute_path)
                                    total_downloaded += 1
                                    self.log(f"Successfully downloaded PDF: {absolute_path}")
                                else:
                                    self.log(f"Failed to download PDF for DOI: {doi}")
                            except Exception as e:
                                self.log(f"Error downloading PDF for DOI {doi}: {e}")
                
                self.log(f"Search completed. Found {len(final_results)} posts with DOIs containing '{search_query}' {context}, downloaded {total_downloaded} PDFs to {download}")
            elif having_doi:
                self.log(f"Search completed. Found {len(final_results)} posts with DOIs containing '{search_query}' {context}")
            else:
                self.log(f"Search completed. Found {len(final_results)} posts containing '{search_query}' {context}")
            
            # Log DOI extraction and download summary
            total_dois = sum(len(post.get('doi_numbers', [])) for post in final_results)
            if download:
                total_downloaded = sum(len(post.get('downloaded_pdfs', [])) for post in final_results)
                self.log(f"Download enabled: Found {len(final_results)} posts with {total_dois} DOI numbers, successfully downloaded {total_downloaded} PDFs to {download}")
            elif having_doi:
                self.log(f"DOI filtering enabled: Found {len(final_results)} posts with {total_dois} DOI numbers")
            else:
                self.log(f"Extracted {total_dois} DOI numbers from search results")
            
            return final_results
            
        except Exception as e:
            self.log(f"Error during search: {e}")
            return []

    def print_search_results(self, search_results, search_query):
        """Print search results in a formatted way with improved highlighting and filtering"""
        self.log(f"Printing {len(search_results)} search results...")
        print("\n" + "="*80)
        print(f"FACEBOOK SEARCH RESULTS for: '{search_query}'")
        print(f"Found {len(search_results)} relevant posts")
        print("="*80)
        
        if not search_results:
            print("\n❌ No posts found containing the search term.")
            print("Try using different keywords or a broader search term.")
            return
        
        for idx, post in enumerate(search_results, start=1):
            print(f"\n🔍 SEARCH RESULT #{idx}")
            print("-" * 40)
            
            print(f"👤 Author: {post['author']}")
            print(f"⏰ Posted: {post['post_time']}")
            
            # Show additional context if available
            if 'user_id' in post:
                print(f"🔗 User ID: {post['user_id']}")
            if 'group_id' in post:
                print(f"📁 Group ID: {post['group_id']}")
            
            relevance_score = post.get('search_relevance', 1)
            print(f"🎯 Relevance: {relevance_score} mention(s)")
            
            print(f"\n📝 Content:")
            content = post['post_text']
            
            # Improved highlighting with case-insensitive search
            highlighted_content = self._highlight_search_term(content, search_query)
            
            if len(highlighted_content) > 600:  # Increased display length
                highlighted_content = highlighted_content[:597] + "..."
            print(f"   {highlighted_content}")
            
            print(f"\n📊 Engagement:")
            print(f"   👍 Likes: {post['likes']}")
            print(f"   💬 Comments: {post['comments_count']}")
            print(f"   🔗 Shares: {post['shares']}")
            
            # Show DOI information only for posts
            post_dois = post.get('doi_numbers', [])
            
            if post_dois:
                print(f"\n📚 DOI Information:")
                print(f"   📄 DOIs in post ({len(post_dois)}):")
                for doi in post_dois:
                    print(f"      • {doi}")
            
            # Show download information if available
            downloaded_pdfs = post.get('downloaded_pdfs', [])
            if downloaded_pdfs:
                print(f"\n⬇️ Downloaded PDFs ({len(downloaded_pdfs)}):")
                for pdf_path in downloaded_pdfs:
                    print(f"      • {pdf_path}")
            elif post_dois:
                print(f"\n⬇️ Download Status: No PDFs downloaded for this post")
            
            # Show top comments with highlighting
            if post['top_comments']:
                print(f"\n💭 Top Comments ({len(post['top_comments'])}):")
                for i, comment in enumerate(post['top_comments'][:3], 1):  # Show up to 3 comments
                    highlighted_comment = self._highlight_search_term(comment, search_query)
                    comment_preview = highlighted_comment[:200] + "..." if len(highlighted_comment) > 200 else highlighted_comment
                    print(f"   {i}. {comment_preview}")
            
            print("\n" + "-"*80)
        
        print(f"\n✅ Search Summary: Found {len(search_results)} posts containing '{search_query}'")
        if search_results:
            avg_relevance = sum(post.get('search_relevance', 1) for post in search_results) / len(search_results)
            print(f"📈 Average relevance score: {avg_relevance:.1f}")
            
            # Summary of total DOIs found only in posts
            total_post_dois = sum(len(post.get('doi_numbers', [])) for post in search_results)
            total_downloads = sum(len(post.get('downloaded_pdfs', [])) for post in search_results)
            
            if total_post_dois > 0:
                print(f"📚 Total DOIs extracted: {total_post_dois} (in posts)")
            
            if total_downloads > 0:
                print(f"⬇️ Total PDFs downloaded: {total_downloads}")
        
        print("="*80)

    def _highlight_search_term(self, text, search_term):
        """Helper method to highlight search terms in text"""
        if not text or not search_term:
            return text
        
        # Split search term into individual words for better matching
        search_words = search_term.lower().split()
        highlighted_text = text
        
        for word in search_words:
            # Use regex for better word boundary matching
            pattern = re.compile(re.escape(word), re.IGNORECASE)
            highlighted_text = pattern.sub(f"**{word.upper()}**", highlighted_text)
        
        return highlighted_text

    def search_and_comment(self, search_query, comment_text=None, max_posts=10, group_id=None, user_id=None):
        """Search for posts and interactively select one to comment on"""
        
        context = f"from user {user_id}" if user_id else (f"in group {group_id}" if group_id else "on Facebook")
        self.log(f"Searching for posts to comment on with query: '{search_query}' {context}")
        
        # Search for posts with group_id and user_id filtering
        search_results = self.search_posts(search_query, max_posts, group_id=group_id, user_id=user_id)
        
        if not search_results:
            self.log("No posts found to comment on")
            return False
        
        # Display search results for selection
        print("\n" + "="*80)
        print(f"SELECT A POST TO COMMENT ON - Found {len(search_results)} posts {context}")
        print("="*80)
        
        for idx, post in enumerate(search_results, start=1):
            print(f"\n{idx}. Author: {post['author']}")
            print(f"   Posted: {post['post_time']}")
            print(f"   Likes: {post['likes']} | Comments: {post['comments_count']}")
            
            # Show additional context if available
            if 'user_id' in post:
                print(f"   User ID: {post['user_id']}")
            if 'group_id' in post:
                print(f"   Group ID: {post['group_id']}")
            
            content_preview = post['post_text'][:150] + "..." if len(post['post_text']) > 150 else post['post_text']
            print(f"   Content: {content_preview}")
            print("-" * 40)
        
        # Timeout handler for user input
        def timeout_handler():
            self.log("User input timeout after 30 seconds")
            print("\n⏰ Timeout: No response received within 30 seconds. Operation cancelled.")
            return False
        
        def get_input_with_timeout(prompt, timeout=30):
            """Get user input with timeout handling for both Windows and Unix"""
            if platform.system() == "Windows":
                # Windows-specific timeout handling
                
                print(prompt, end='', flush=True)
                start_time = time.time()
                input_chars = []
                
                while True:
                    if msvcrt.kbhit():
                        char = msvcrt.getch()
                        if char == b'\r':  # Enter key
                            print()  # New line
                            return ''.join(input_chars)
                        elif char == b'\x08':  # Backspace
                            if input_chars:
                                input_chars.pop()
                                print('\b \b', end='', flush=True)
                        else:
                            try:
                                decoded_char = char.decode('utf-8')
                                input_chars.append(decoded_char)
                                print(decoded_char, end='', flush=True)
                            except UnicodeDecodeError:
                                pass
                    
                    if time.time() - start_time > timeout:
                        print(f"\n⏰ Timeout: No response received within {timeout} seconds.")
                        return None
                    
                    time.sleep(0.1)
            else:
                # Unix-like systems (Linux, macOS)
                def alarm_handler(signum, frame):
                    raise TimeoutError()
                
                try:
                    signal.signal(signal.SIGALRM, alarm_handler)
                    signal.alarm(timeout)
                    result = input(prompt)
                    signal.alarm(0)  # Cancel the alarm
                    return result
                except (TimeoutError, KeyboardInterrupt):
                    signal.alarm(0)  # Cancel the alarm
                    print(f"\n⏰ Timeout: No response received within {timeout} seconds.")
                    return None
        
        # Get user selection with timeout
        while True:
            try:
                choice = get_input_with_timeout(f"\nSelect a post to comment on (1-{len(search_results)}) or 'q' to quit: ")
                
                if choice is None:  # Timeout occurred
                    self.log("Operation failed due to user input timeout")
                    return False
                
                choice = choice.strip()
                
                if choice.lower() == 'q':
                    self.log("User cancelled post selection")
                    return False
                
                choice_idx = int(choice) - 1
                if 0 <= choice_idx < len(search_results):
                    selected_post = search_results[choice_idx]
                    break
                else:
                    print(f"Please enter a number between 1 and {len(search_results)}")
                    
            except ValueError:
                print("Please enter a valid number or 'q' to quit")
        
        # Get comment text if not provided
        if comment_text is None:
            print(f"\nSelected post {choice_idx + 1} for commenting")
            print(f"Post content: {selected_post['post_text'][:200]}{'...' if len(selected_post['post_text']) > 200 else ''}")
            
            while True:
                comment_text = get_input_with_timeout("\nEnter your comment (or 'q' to quit): ")
                
                if comment_text is None:  # Timeout occurred
                    self.log("Operation failed due to user input timeout")
                    return False
                
                comment_text = comment_text.strip()
                
                if comment_text.lower() == 'q':
                    self.log("User cancelled comment input")
                    return False
                
                if comment_text:
                    break
                else:
                    print("Comment cannot be empty. Please enter your comment or 'q' to quit.")
        
        # Comment on selected post
        self.log(f"Selected post {choice_idx + 1} for commenting")
        return self.comment_on_post(selected_post, comment_text)

    def comment_on_post(self, post_data, comment_text):
        """Comment on a specific post"""
        self.log(f"Attempting to comment on post by {post_data['author']}")

        # Check for non-BMP characters (codepoints > 0xFFFF)
        if any(ord(char) > 0xFFFF for char in comment_text):
            self.log("❌ Error: Comment contains non-BMP characters (e.g., rare CJK, emoji, etc.) which are not supported by Chrome driver.")
            print("❌ Error: Comment contains non-BMP characters (e.g., rare CJK, emoji, etc.) which are not supported by Chrome driver. Please remove or replace them and try again.")
            return False

        try:
            # Refresh the page to ensure we're working with current content
            self.driver.refresh()
            time.sleep(5)

            # Find the post on the current page by matching author and content
            page_source = self.driver.page_source
            soup = BeautifulSoup(page_source, "html.parser")

            # Try to find the specific post element
            post_element = None
            post_selectors = [
                "div[data-pagelet*='FeedUnit']",
                "div.x1n2onr6.x1ja2u2z",
                "div[role='article']",
                "div.x1yztbdb.x1n2onr6.xh8yej3.x1ja2u2z"
            ]

            for selector in post_selectors:
                posts = self.driver.find_elements(By.CSS_SELECTOR, selector)
                for post in posts:
                    # Check if this post matches our target post
                    post_html = post.get_attribute('innerHTML')
                    if (post_data['author'].lower() in post_html.lower() or 
                        post_data['post_text'][:50].lower() in post_html.lower()):
                        post_element = post
                        self.log("Found matching post element")
                        break
                if post_element:
                    break

            if not post_element:
                self.log("Could not find the specific post to comment on")
                return False

            # Scroll to the post
            self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", post_element)
            time.sleep(3)

            # Look for comment button or comment input within the post
            comment_selectors = [
                ".//div[@role='button' and contains(@aria-label, 'Comment')]",
                ".//div[contains(@aria-label, 'Comment')]",
                ".//div[contains(text(), 'Comment')]",
                ".//span[contains(text(), 'Comment')]",
                ".//div[@data-testid='fb-ufi-comment-action-link']"
            ]

            comment_button = None
            for selector in comment_selectors:
                try:
                    comment_buttons = post_element.find_elements(By.XPATH, selector)
                    for btn in comment_buttons:
                        if btn.is_displayed():
                            comment_button = btn
                            self.log(f"Found comment button with selector: {selector}")
                            break
                    if comment_button:
                        break
                except:
                    continue

            if not comment_button:
                self.log("Could not find comment button for this post")
                return False

            # Click the comment button
            self.log("Clicking comment button...")
            try:
                comment_button.click()
            except:
                self.driver.execute_script("arguments[0].click();", comment_button)

            time.sleep(3)

            # Find the comment input field
            comment_input_selectors = [
                "div[contenteditable='true'][data-testid*='comment']",
                "div[contenteditable='true'][aria-label*='comment']",
                "div[contenteditable='true'][role='textbox']",
                "textarea[placeholder*='comment']",
                "div[data-testid='comment-input']"
            ]

            comment_input = None
            for selector in comment_input_selectors:
                try:
                    comment_inputs = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    for input_elem in comment_inputs:
                        if input_elem.is_displayed():
                            comment_input = input_elem
                            self.log(f"Found comment input with selector: {selector}")
                            break
                    if comment_input:
                        break
                except:
                    continue

            if not comment_input:
                self.log("Could not find comment input field")
                return False

            # Click on the comment input to focus it
            self.log("Focusing on comment input...")
            comment_input.click()
            time.sleep(2)

            # Type the comment
            self.log("Typing comment...")
            filtered_comment = ''.join(char for char in comment_text if ord(char) < 65536)

            # Type a few beginning words of each line, paste the rest, then newline
            lines = filtered_comment.split('\n')
            for line_idx, line in enumerate(lines):
                if line.strip():  # Skip empty lines
                    words = line.split()
                    if len(words) > 3:
                        # Type first 2-3 words manually
                        beginning_words = ' '.join(words[:2])
                        remaining_text = ' '.join(words[2:])

                        # Type beginning words character by character
                        for char in beginning_words:
                            comment_input.send_keys(char)
                            time.sleep(random.uniform(0.05, 0.15))

                        # Add a space before pasting
                        comment_input.send_keys(' ')

                        # Paste the remaining text
                        comment_input.send_keys(remaining_text)
                    else:
                        # For short lines, type normally
                        for char in line:
                            comment_input.send_keys(char)
                            time.sleep(random.uniform(0.05, 0.15))

                # Add newline if not the last line
                if line_idx < len(lines) - 1:
                    comment_input.send_keys(Keys.SHIFT + Keys.ENTER)
                    time.sleep(random.uniform(0.2, 0.5))

            # Adjust wait time based on content length and typing speed
            # Base wait time calculation: ~0.1s per character typed + processing time
            typed_chars = sum(min(len(line.split()[:2]), len(line)) for line in lines if line.strip())
            base_wait = max(1, typed_chars * 0.1)
            time.sleep(base_wait)

            # Submit the comment (usually Enter key or clicking Post button)
            self.log("Submitting comment...")
            try:
                # Try pressing Enter first
                comment_input.send_keys("\n")
                time.sleep(3)

                # If Enter doesn't work, look for a Post/Submit button
                post_comment_selectors = [
                    "div[role='button'][aria-label*='Post']",
                    "button[data-testid*='comment-submit']",
                    "div[role='button']:has-text('Post')",
                    "button:has-text('Post')"
                ]

                for selector in post_comment_selectors:
                    try:
                        post_buttons = self.driver.find_elements(By.CSS_SELECTOR, selector)
                        for btn in post_buttons:
                            if btn.is_displayed() and btn.is_enabled():
                                btn.click()
                                self.log("Clicked post comment button")
                                break
                    except:
                        continue

            except Exception as e:
                self.log(f"Error submitting comment: {e}")

            time.sleep(5)

            # Verify comment was posted
            self.log("Verifying comment was posted...")
            try:
                # Look for the comment in the post
                post_html = post_element.get_attribute('innerHTML')
                if comment_text[:30].lower() in post_html.lower():
                    self.log("✅ Comment posted successfully!")
                    print(f"✅ Successfully commented on post by {post_data['author']}")
                    print(f"Comment: {comment_text}")
                    return True
                else:
                    self.log("⚠️ Comment may have been posted but couldn't verify")
                    print(f"⚠️ Comment submitted but verification uncertain")
                    return True

            except Exception as e:
                self.log(f"Error verifying comment: {e}")
                return True  # Assume success if we can't verify

        except Exception as e:
            self.log(f"❌ Error commenting on post: {e}")
            print(f"❌ Failed to comment on post: {e}")
            return False
    
    def request_help_for_multiple_dois(self, dois, group_id="188053074599163", extra_message=None):
        """
        Post a single help request for multiple DOIs to a Facebook group.
        Args:
            dois (list or str): List of DOIs or a single DOI string.
            group_id (str): Facebook group ID to post in.
            extra_message (str): Optional extra message to include.
        Returns:
            list: List of (doi, success) tuples (all DOIs share the same status).
        """
        if isinstance(dois, str):
            dois = [dois]
        dois = [d for d in dois if d]
        if not dois:
            self.log("❌ No valid DOIs provided for help request.")
            return [(None, False)]
        # Compose the help message
        if len(dois) == 1:
            message = (
                f"Nhờ mọi người giúp tải tài liệu sau:\n\n"
                f"https://doi.org/{dois[0]}"
                "\n\nXin chân thành cảm ơn mọi người nhiều!"
            )
        else:
            message = (
                f"Nhờ mọi người giúp tải các tài liệu sau:\n\n"
                + "\n".join([f"{i+1}. https://doi.org/{doi}" for i, doi in enumerate(dois)]) +
                "\n\nXin chân thành cảm ơn mọi người nhiều!"
            )
        if extra_message:
            message += f"\n{extra_message}"
        group_url = f"https://www.facebook.com/groups/{group_id}"
        self.log(f"Navigating to group: {group_url}")
        self.navigate_to_profile(group_url)
        time.sleep(4)
        self.log(f"Posting help request for {len(dois)} DOIs to group {group_id}")
        success = self.create_post(message)
        if success:
            self.log(f"✅ Successfully posted help request for DOIs to group {group_id}")
        else:
            self.log(f"❌ Failed to post help request for DOIs to group {group_id}")
        return [(doi, success) for doi in dois]
    
    def print_default_paths():
        """Print all default cache and download directory paths."""
        print("Default Facebook Scraper Paths:")
        print(f"  Cache directory: {_CACHE_DIR}")
        print(f"  Download folder: {_DOWNLOAD_DIR}")
        print(f"  Cache file: {CACHE_FILE}")

    def close(self):
        """Close the browser"""
        self.log("Closing browser...")
        if self.driver:
            self.driver.quit()
            self.log("Browser closed successfully")

def main():
    """Main function to handle command line arguments and execute Facebook scraper operations"""
    # Get the parent package name from the module's __name__
    parent_package = __name__.split('.')[0] if '.' in __name__ else None

    if parent_package is None:
        program_name = 'facebook'
    elif '_' in parent_package:
        # If the parent package has an underscore, strip it
        parent_package = parent_package[:parent_package.index('_')]
        program_name = f"{parent_package} facebook"

    parser = argparse.ArgumentParser(
        prog=program_name,
        description='''Facebook Scraper - Search, comment, and post on Facebook using automated browser control

Popular Facebook Groups for Scientific Paper Requests:
* Nhóm Tải Báo: 188053074599163 (default group)
* Nhóm Tải Báo (Original)
* Science Mutual Aid: 402784499466368
* Ask for PDFs from People with Institutional Access: 850609558335839
* Scientific Papers: 556282024420690
  
Note: Replace with actual group IDs. To find a group ID, visit the group page and copy the numeric ID from the URL.''',
        epilog='''
Examples:
  Load credentials
    %(prog)s --credentials credentials.json

  Search for posts:
    %(prog)s --search "python programming" --search-limit 20

  Search for posts with DOI numbers:
    %(prog)s --search "machine learning" --having-doi --search-limit 15

  Search for posts with DOI numbers and download PDFs:
    %(prog)s --search "machine learning" --having-doi --download ~/Downloads/papers --search-limit 15

  Search and comment on posts:
    %(prog)s --search "data science" --search-comment "Great insights!"

  Search in specific group:
    %(prog)s --search "machine learning" --search-in-group 188053074599163

  Search user posts:
    %(prog)s --search "tutorial" --search-in-profile user123

  Comment using file content:
    %(prog)s --search "AI" --search-comment-file comment.txt

  Get top posts from homepage:
    %(prog)s --get-posts 15

  Get top posts with DOI numbers:
    %(prog)s --get-posts 10 --having-doi

  Get top posts with DOI numbers and download PDFs:
    %(prog)s --get-posts 10 --having-doi --download ~/Downloads/papers

  Get top posts from group:
    %(prog)s --get-posts 15 --get-in-group 188053074599163

  Get top posts from user profile:
    %(prog)s --get-posts 10 --get-in-profile user123

  Post to your profile:
    %(prog)s --post-on-profile --profile-post-content "Hello World!"

  Post to your profile from file:
    %(prog)s --post-on-profile --profile-post-file post.txt

  Post to a group:
    %(prog)s --post-in-group 188053074599163 --group-post-content "Help me find this paper!"

  Post to group from file:
    %(prog)s --post-in-group 188053074599163 --group-post-file content.txt

  Run in graphic mode (non-headless):
    %(prog)s --search "python" --no-headless --verbose

  Run with logging:
    %(prog)s --search "python" --log scraper.log --verbose

  Search for papers in academic groups:
    %(prog)s --search "machine learning paper" --search-in-group 188053074599163
    %(prog)s --search "research methodology" --search-in-group 1234567890123456

  Filter for posts with DOI numbers only:
    %(prog)s --search "research paper" --having-doi --search-in-group 188053074599163

  Filter for posts with DOI numbers and download PDFs:
    %(prog)s --search "research paper" --having-doi --download ~/Downloads/papers --search-in-group 188053074599163

  Request help for DOI(s):
    %(prog)s --request-doi 10.1000/xyz123
    %(prog)s --request-doi 10.1000/xyz123,10.1000/abc456 --request-in-group 402784499466368
    %(prog)s --request-doi dois.txt --request-in-group 188053074599163
        ''',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('--verbose', '-v', action='store_true', 
                       help='Enable verbose debugging output')
    parser.add_argument('--log', '-l', type=str,
                       help='Path to log file to write output messages (in addition to screen output)')
    parser.add_argument('--no-headless', action='store_true',
                       help='Run in graphic mode (default is headless)')
    parser.add_argument('--credentials', '-c', type=str,
                       help='Path to JSON credentials file containing username and password')
    parser.add_argument('--having-doi', action='store_true',
                       help='Filter posts to only include those containing DOI numbers')
    parser.add_argument('--download', '-d', nargs='?', const=DOWNLOAD_FOLDER, type=str,
                       help=f'Download PDFs for DOI numbers found in posts to specified directory (requires --having-doi). Default: {DOWNLOAD_FOLDER}')
    parser.add_argument('--search', '-s', type=str,
                       help='Search for posts containing specific content')
    parser.add_argument('--search-limit', type=int, default=10,
                       help='Number of search results to return (default: 10)')
    parser.add_argument('--search-comment', '-sc', nargs='?', const='', type=str,
                       help='Comment text to post on searched results (if no text provided, will prompt for input)')
    parser.add_argument('--search-comment-file', '-scf', type=str,
                       help='Path to text file containing comment text for searched results')
    parser.add_argument('--search-in-group', '-sg', nargs='?', const='188053074599163', type=str,
                       help='Limit search to a specific group (provide group ID, or use default if no ID specified)')
    parser.add_argument('--search-in-profile', '-sp', type=str,
                       help='Limit search to a specific user profile (provide user ID)')
    parser.add_argument('--get-posts', '-g', type=int, metavar='LIMIT',
                       help='Retrieve specified number of posts from homepage, group, or profile')
    parser.add_argument('--get-in-group', '-gg', nargs='?', const='188053074599163', type=str,
                       help='Retrieve posts from a specific group (provide group ID, or use default if no ID specified)')
    parser.add_argument('--get-in-profile', '-gp', type=str,
                       help='Retrieve posts from a specific user profile (provide user ID)')
    parser.add_argument('--post-in-group', '-pg', nargs='?', const='188053074599163', type=str,
                       help='Post to a specific group (provide group ID, or use default if no ID specified)')
    parser.add_argument('--group-post-content', '-gpc', type=str,
                       help='Content to post in the specified group')
    parser.add_argument('--group-post-file', '-gpf', type=str,
                       help='Path to text file containing content to post in the specified group')
    parser.add_argument('--post-on-profile', '-pp', action='store_true',
                       help='Post on your own profile/timeline')
    parser.add_argument('--profile-post-content', '-ppc', type=str,
                       help='Content to post on your profile/timeline')
    parser.add_argument('--profile-post-file', '-ppf', type=str,
                       help='Path to text file containing content to post on your profile/timeline')
    parser.add_argument('--request-doi', '-rd', type=str,
                       help='Request help for DOI(s): provide a DOI, comma-separated DOIs, or a file containing DOIs (one per line)')
    parser.add_argument('--request-in-group', '-rg', nargs='?', const='188053074599163', type=str, 
                       help='Group ID to post DOI help requests in (default: 188053074599163)')
    parser.add_argument('--clear-cache', action='store_true',
                       help='Delete the default cache directory and exit')
    parser.add_argument('--print-default', action='store_true',
                       help='Print default cache and download directory paths and exit')
    args = parser.parse_args()
    
    # Handle --print-default before anything else
    if args.print_default:
        FacebookScraper.print_default_paths()
        return

    # Enforce --credentials cannot be used with other arguments except --verbose
    if args.credentials:
        # List of argument names that are allowed with --credentials
        allowed_with_credentials = {'credentials', 'verbose', 'facebook'}
        # Check if any other argument is set (not None/False/empty)
        other_args = [arg for arg in vars(args) if getattr(args, arg) not in (None, False, [], '') and arg not in allowed_with_credentials]
        if other_args:
            print("❌ Error: --credentials cannot be used with other arguments except --verbose.")
            print("   Please use --credentials alone (optionally with --verbose) to load credentials.")
            return

    # Handle --clear-cache before anything else
    if args.clear_cache:
        try:
            if os.path.exists(_CACHE_DIR):
                shutil.rmtree(_CACHE_DIR)
                print(f"✅ Cache directory deleted: {_CACHE_DIR}")
            else:
                print(f"ℹ️ Cache directory does not exist: {_CACHE_DIR}")
        except Exception as e:
            print(f"❌ Error deleting cache directory: {e}")
        return

    # Setup logging file if specified
    log_file = None
    if args.log:
        try:
            # Create log directory if it doesn't exist
            log_dir = os.path.dirname(os.path.abspath(args.log))
            if log_dir:
                os.makedirs(log_dir, exist_ok=True)
            
            log_file = open(args.log, 'a', encoding='utf-8')
            print(f"✅ Logging enabled - writing to: {args.log}")
            
            # Write session header to log file
            log_file.write(f"\n{'='*80}\n")
            log_file.write(f"Facebook Scraper Session Started: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            log_file.write(f"Arguments: {' '.join(sys.argv[1:])}\n")
            log_file.write(f"{'='*80}\n")
            log_file.flush()
            
        except Exception as e:
            print(f"❌ Error opening log file {args.log}: {e}")
            print("Continuing without logging...")
            log_file = None
    
    # Helper function to print and optionally log messages
    def print_and_log(message, is_debug=False):
        """Print message to screen and optionally write to log file"""
        # Always print to screen unless it's a debug message and verbose is disabled
        if not is_debug or args.verbose:
            print(message)
        
        # Write to log file if enabled
        if log_file:
            # Write debug messages to log only if verbose is enabled
            if not is_debug or args.verbose:
                try:
                    log_file.write(f"{message}\n")
                    log_file.flush()
                except Exception as e:
                    print(f"❌ Error writing to log file: {e}")
    
    # Validate download option
    if args.download and not args.having_doi:
        error_msg = "❌ Error: --download option requires --having-doi to be specified"
        print_and_log(error_msg)
        print_and_log("   Use both options together: --having-doi --download <directory>")
        return
    
    # Helper function to read content from file
    def read_content_from_file(file_path):
        """Read content from a text file with proper encoding handling"""
        if not file_path:
            return None
        
        try:
            if not os.path.exists(file_path):
                error_msg = f"❌ Error: File not found: {file_path}"
                print_and_log(error_msg)
                return None
            
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read().strip()
            
            if not content:
                error_msg = f"❌ Error: File is empty: {file_path}"
                print_and_log(error_msg)
                return None
            
            success_msg = f"✅ Successfully loaded content from: {file_path}"
            print_and_log(success_msg)
            preview_msg = f"Content preview: {content[:100]}{'...' if len(content) > 100 else ''}"
            print_and_log(preview_msg)
            return content
            
        except Exception as e:
            error_msg = f"❌ Error reading file {file_path}: {e}"
            print_and_log(error_msg)
            return None

    # Helper function to read DOIs from string or file
    def parse_dois(doi_arg):
        """Parse DOIs from a string (comma-separated) or file (one per line)"""
        if not doi_arg:
            return []
        if os.path.isfile(doi_arg):
            try:
                with open(doi_arg, 'r', encoding='utf-8') as f:
                    lines = [line.strip() for line in f if line.strip()]
                return lines
            except Exception as e:
                print_and_log(f"❌ Error reading DOI file {doi_arg}: {e}")
                return []
        # Otherwise, treat as comma-separated string
        return [doi.strip() for doi in doi_arg.split(',') if doi.strip()]

    # Initialize the scraper with custom logging
    class LoggedFacebookScraper(FacebookScraper):
        def log(self, message):
            """Override log method to use print_and_log"""
            print_and_log(f"[DEBUG] {message}", is_debug=True)
    
    scraper = LoggedFacebookScraper(
        USERNAME, 
        PASSWORD,
        verbose=args.verbose,
        headless=not args.no_headless
    )
    
    try:

        # Load credentials if specified
        if args.credentials:
            if not scraper.load_credentials(args.credentials):
                print_and_log("⚠️ Could not load credentials from specified file")
            else:
                print_and_log("✅ Credentials loaded successfully")
                return
        
        # Setup and login
        scraper.initialize_driver()
        scraper.login()

        # Handle DOI help request
        if args.request_doi:
            dois = parse_dois(args.request_doi)
            group_id = args.request_in_group
            if not dois:
                print_and_log("❌ No valid DOI(s) provided for --request-doi")
            else:
                print_and_log(f"🆘 Requesting help for {len(dois)} DOI(s) in group {group_id}...")
                results = scraper.request_help_for_multiple_dois(dois, group_id=group_id)
                for doi, success in results:
                    if success:
                        print_and_log(f"✅ Successfully posted help request for DOI: {doi} in group {group_id}")
                    else:
                        print_and_log(f"❌ Failed to post help request for DOI: {doi} in group {group_id}")
            # After DOI request, exit
            return
        
        # Get posts from group, profile, or homepage
        if args.get_posts:
            if args.get_in_group:
                doi_filter_msg = " with DOI numbers" if args.having_doi else ""
                download_msg = f" and downloading PDFs to {args.download}" if args.download else ""
                msg = f"📄 Retrieving {args.get_posts} posts{doi_filter_msg}{download_msg} from group {args.get_in_group}..."
                print_and_log(msg)
                group_url = f"https://www.facebook.com/groups/{args.get_in_group}/?sorting_setting=CHRONOLOGICAL"
                scraper.navigate_to_profile(group_url)
                posts = scraper.scrape_posts(args.get_posts, having_doi=args.having_doi, download=args.download)
                if posts:
                    print_and_log(f"\n🏷️ GROUP POSTS FROM: {args.get_in_group}")
                    scraper.print_posts(posts)
                else:
                    filter_msg = " with DOI numbers" if args.having_doi else ""
                    print_and_log(f"❌ No posts{filter_msg} found in the specified group")
            elif args.get_in_profile:
                doi_filter_msg = " with DOI numbers" if args.having_doi else ""
                download_msg = f" and downloading PDFs to {args.download}" if args.download else ""
                msg = f"📄 Retrieving {args.get_posts} posts{doi_filter_msg}{download_msg} from profile {args.get_in_profile}..."
                print_and_log(msg)
                profile_url = f"https://www.facebook.com/{args.get_in_profile}"
                scraper.navigate_to_profile(profile_url)
                posts = scraper.scrape_posts(args.get_posts, having_doi=args.having_doi, download=args.download)
                if posts:
                    print_and_log(f"\n🏷️ PROFILE POSTS FROM: {args.get_in_profile}")
                    scraper.print_posts(posts)
                else:
                    filter_msg = " with DOI numbers" if args.having_doi else ""
                    print_and_log(f"❌ No posts{filter_msg} found in the specified profile")
            else:
                # Default to homepage if no specific group or profile specified
                doi_filter_msg = " with DOI numbers" if args.having_doi else ""
                download_msg = f" and downloading PDFs to {args.download}" if args.download else ""
                msg = f"📄 Retrieving {args.get_posts} posts{doi_filter_msg}{download_msg} from homepage..."
                print_and_log(msg)
                scraper.driver.get("https://www.facebook.com")
                posts = scraper.scrape_posts(args.get_posts, having_doi=args.having_doi, download=args.download)
                if posts:
                    print_and_log(f"\n🏷️ HOMEPAGE POSTS")
                    scraper.print_posts(posts)
                else:
                    filter_msg = " with DOI numbers" if args.having_doi else ""
                    print_and_log(f"❌ No posts{filter_msg} found on homepage")
        
        # Search for posts containing a specific term
        if args.search:
            if args.search_comment is not None or args.search_comment_file:
                # Determine comment text source
                comment_text = None
                
                if args.search_comment_file:
                    # Load comment from file
                    comment_text = read_content_from_file(args.search_comment_file)
                    if comment_text is None:
                        print_and_log("❌ Failed to load comment from file, operation cancelled")
                    
                elif args.search_comment:
                    # Use provided comment text
                    comment_text = args.search_comment
                
                # Search and comment on posts with optional group/user filtering
                if comment_text is not None:
                    success = scraper.search_and_comment(
                        args.search, 
                        comment_text, 
                        max_posts=args.search_limit,
                        group_id=args.search_in_group,
                        user_id=args.search_in_profile
                    )
                    if success:
                        print_and_log("✅ Successfully commented on selected post!")
                    else:
                        print_and_log("❌ Failed to comment on post or operation cancelled")
            else:
                # Just search and display results with optional group/user filtering, DOI filtering, and PDF download
                search_results = scraper.search_posts(
                    args.search, 
                    max_posts=args.search_limit,
                    group_id=args.search_in_group,
                    user_id=args.search_in_profile,
                    having_doi=args.having_doi,
                    download=args.download
                )
                scraper.print_search_results(search_results, args.search)
        elif not args.get_posts:
            print_and_log("No search term provided. Use --search to find posts containing specific content.")
            if args.search_comment is not None or args.search_comment_file:
                print_and_log("Note: Comment options require --search to be specified")
            if args.search_in_group:
                print_and_log("Note: --search-in-group requires --search to be specified")
            if args.search_in_profile:
                print_and_log("Note: --search-in-profile requires --search to be specified")
            if args.having_doi:
                print_and_log("Note: --having-doi requires either --search or --get-posts to be specified")
            if args.download:
                print_and_log("Note: --download requires both --having-doi and either --search or --get-posts to be specified")

        # Handle group posting
        if args.post_in_group:
            # Determine post content source
            post_content = None
            
            if args.group_post_file:
                # Load post content from file
                post_content = read_content_from_file(args.group_post_file)
            elif args.group_post_content:
                # Use provided post content
                post_content = args.group_post_content
            
            if not post_content:
                print_and_log("❌ Error: Either --group-post-content or --group-post-file is required when using --post-in-group")
            else:
                print_and_log(f"📝 Posting to group {args.post_in_group}...")
                group_url = f"https://www.facebook.com/groups/{args.post_in_group}"
                scraper.navigate_to_profile(group_url)
                success = scraper.create_post(post_content)
                if success:
                    print_and_log(f"✅ Successfully posted to group {args.post_in_group}!")
                else:
                    print_and_log(f"❌ Failed to post to group {args.post_in_group}")

        # Handle profile posting
        if args.post_on_profile:
            # Determine post content source
            post_content = None
            
            if args.profile_post_file:
                # Load post content from file
                post_content = read_content_from_file(args.profile_post_file)
            elif args.profile_post_content:
                # Use provided post content
                post_content = args.profile_post_content
            
            if not post_content:
                print_and_log("❌ Error: Either --profile-post-content or --profile-post-file is required when using --post-on-profile")
            else:
                print_and_log("📝 Posting to your profile...")
                scraper.driver.get("https://www.facebook.com")
                success = scraper.create_post(post_content)
                if success:
                    print_and_log("✅ Successfully posted to your profile!")
                else:
                    print_and_log("❌ Failed to post to your profile")
        
    finally:
        # Clean up
        scraper.close()
        
        # Close log file if opened
        if log_file:
            try:
                log_file.write(f"\nSession ended: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                log_file.write(f"{'='*80}\n")
                log_file.close()
                print(f"✅ Log file closed: {args.log}")
            except Exception as e:
                print(f"❌ Error closing log file: {e}")

if __name__ == "__main__":
    main()
