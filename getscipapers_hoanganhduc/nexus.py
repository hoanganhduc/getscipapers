from telethon import TelegramClient, events
import asyncio
import json
import os
import sys
from datetime import datetime
import platform
import argparse
import logging
from telethon import connection
import requests
from bs4 import BeautifulSoup
import random
import socket
import ssl
import aiohttp
from urllib.parse import urlparse
import socks
from aiohttp_socks import ProxyConnector
import re
import select
import time

if platform.system() == 'Windows':
    import msvcrt

# You need to get API credentials from https://my.telegram.org
API_ID = ""  # Replace with your actual API ID
API_HASH = ""  # Replace with your actual API hash
PHONE = ""  # Replace with your phone number
BOT_USERNAME = "SciNexBot"  # Replace with Nexus bot username
SESSION_FILE = ""

# Global variables for logging
verbose_mode = False
logger = None

def setup_logging(log_file=None, verbose=False):
    """Setup logging configuration"""
    global logger, verbose_mode
    verbose_mode = verbose
    
    # Create logger
    logger = logging.getLogger('TelegramBot')
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    
    # Clear any existing handlers
    logger.handlers.clear()
    
    # Create formatter
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG if verbose else logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # File handler if log_file is specified
    if log_file:
        # Create log directory if it doesn't exist
        log_dir = os.path.dirname(log_file)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)
        
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        
        logger.info(f"Logging to file: {log_file}")

def debug_print(message):
    """Print debug message if verbose mode is enabled"""
    if verbose_mode and logger:
        logger.debug(message)
    elif verbose_mode:
        print(f"DEBUG: {message}")

def info_print(message):
    """Print info message"""
    if logger:
        logger.info(message)
    else:
        print(message)

def error_print(message):
    """Print error message"""
    if logger:
        logger.error(message)
    else:
        print(f"ERROR: {message}")

# Set file paths based on operating system
def get_file_paths():
    """Get the appropriate file paths based on the operating system"""
    system = platform.system()
    
    if system == "Windows":
        # Windows: Use AppData\Local directory
        app_data = os.path.expandvars("%LOCALAPPDATA%")
        base_dir = os.path.join(app_data, "TelegramSession")
        log_dir = os.path.join(app_data, "TelegramSession", "logs")
        config_dir = base_dir
        download_dir = os.path.join(os.path.expanduser("~"), "Downloads", "TelegramFiles")
    elif system == "Darwin":  # macOS
        # macOS: Use ~/Library/Application Support directory
        home = os.path.expanduser("~")
        base_dir = os.path.join(home, "Library", "Application Support", "TelegramSession")
        log_dir = os.path.join(base_dir, "logs")
        config_dir = base_dir
        download_dir = os.path.join(home, "Downloads", "TelegramFiles")
    else:  # Linux and other Unix-like systems
        # Linux: Use ~/.local/share directory for session, ~/.config for credentials
        home = os.path.expanduser("~")
        base_dir = os.path.join(home, ".local", "share", "TelegramSession")
        log_dir = os.path.join(home, ".local", "share", "TelegramSession", "logs")
        config_dir = os.path.join(home, ".config", "TelegramSession")
        download_dir = os.path.join(home, "Downloads", "TelegramFiles")
    
    # Create directories if they don't exist
    os.makedirs(base_dir, exist_ok=True)
    os.makedirs(log_dir, exist_ok=True)
    os.makedirs(config_dir, exist_ok=True)
    os.makedirs(download_dir, exist_ok=True)
    
    # Default log file
    timestamp = datetime.now().strftime("%Y%m%d")
    default_log_file = os.path.join(log_dir, f"telegram_bot_{timestamp}.log")
    
    return {
        "session": os.path.join(base_dir, "telegram_session"),
        "credentials": os.path.join(config_dir, "credentials.json"),
        "proxy": os.path.join(config_dir, "proxy.json"),
        "log": default_log_file,
        "download": download_dir
    }

# Update file paths to use the platform-specific paths
file_paths = get_file_paths()
SESSION_FILE = file_paths["session"]
CREDENTIALS_FILE = file_paths["credentials"]
DEFAULT_PROXY_FILE = file_paths["proxy"]
DEFAULT_LOG_FILE = file_paths["log"]
DEFAULT_DOWNLOAD_DIR = file_paths["download"]

def get_free_proxies():
    """Retrieve free proxy list from free-proxy-list.net and save to default proxy file"""
    info_print("Retrieving free proxies from free-proxy-list.net...")
    
    try:
        # Send request to free-proxy-list.net
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        debug_print("Sending request to free-proxy-list.net...")
        response = requests.get('https://free-proxy-list.net/', headers=headers, timeout=10)
        response.raise_for_status()
        
        # Parse HTML content
        debug_print("Parsing HTML content...")
        soup = BeautifulSoup(response.content, 'html.parser')
        
        proxies = []
        
        # First try to find the proxy table
        table = soup.find('table', {'class': 'table table-striped table-bordered'})
        if not table:
            # Fallback to original method
            table = soup.find('table', {'id': 'proxylisttable'})
        
        if table:
            debug_print("Found proxy table, parsing structured data...")
            tbody = table.find('tbody')
            if tbody:
                rows = tbody.find_all('tr')
                debug_print(f"Found {len(rows)} proxy rows")
                
                for row in rows:
                    cols = row.find_all('td')
                    if len(cols) >= 8:  # Updated to check for 8 columns based on the structure
                        ip = cols[0].text.strip()
                        port = cols[1].text.strip()
                        country_code = cols[2].text.strip()
                        country = cols[3].text.strip()
                        anonymity = cols[4].text.strip()
                        google = cols[5].text.strip()
                        https_support = cols[6].text.strip().lower() == 'yes'
                        last_checked = cols[7].text.strip()
                        
                        # Skip Vietnam proxies
                        if country_code.upper() == 'VN' or country.upper() == 'VIETNAM':
                            debug_print(f"Skipping Vietnam proxy: {ip}:{port}")
                            continue
                        
                        # Only include HTTPS-supporting proxies
                        if https_support and ip and port:
                            try:
                                proxy_info = {
                                    'ip': ip,
                                    'port': int(port),
                                    'country_code': country_code,
                                    'country': country,
                                    'anonymity': anonymity,
                                    'google': google,
                                    'https': https_support,
                                    'last_checked': last_checked
                                }
                                proxies.append(proxy_info)
                                debug_print(f"Added proxy: {ip}:{port} ({country})")
                            except ValueError:
                                debug_print(f"Skipping proxy with invalid port: {ip}:{port}")
                                continue
        
        # If table parsing failed or found no proxies, try raw proxy list
        if not proxies:
            debug_print("Table parsing failed or no HTTPS proxies found, looking for raw proxy list...")
            
            # Look for the modal with raw proxy list
            modal_title = soup.find('h4', {'class': 'modal-title', 'id': 'myModalLabel'})
            if modal_title and 'Raw Proxy List' in modal_title.text:
                debug_print("Found raw proxy list modal...")
                
                # Find the textarea with the proxy list
                modal_body = modal_title.find_parent().find_next_sibling('div', {'class': 'modal-body'})
                if modal_body:
                    textarea = modal_body.find('textarea', {'class': 'form-control'})
                    if textarea:
                        debug_print("Found textarea with proxy list...")
                        proxy_text = textarea.text.strip()
                        
                        # Parse the raw proxy list
                        lines = proxy_text.split('\n')
                        for line in lines:
                            line = line.strip()
                            if ':' in line and not line.startswith('Free proxies') and not line.startswith('Updated at'):
                                try:
                                    ip, port = line.split(':', 1)
                                    ip = ip.strip()
                                    port = int(port.strip())
                                    
                                    if ip and port:
                                        proxy_info = {
                                            'ip': ip,
                                            'port': port,
                                            'country_code': 'Unknown',
                                            'country': 'Unknown',
                                            'anonymity': 'Unknown',
                                            'google': 'Unknown',
                                            'https': True,  # Assume HTTPS support for raw list
                                            'last_checked': 'Unknown'
                                        }
                                        proxies.append(proxy_info)
                                        debug_print(f"Added proxy from raw list: {ip}:{port}")
                                except (ValueError, IndexError):
                                    debug_print(f"Skipping invalid proxy line: {line}")
                                    continue
            
            # If still no proxies found, try alternative parsing methods
            if not proxies:
                debug_print("Modal method failed, trying alternative parsing...")
                
                # Look for any textarea that might contain proxy data
                textareas = soup.find_all('textarea')
                for textarea in textareas:
                    if textarea.text and ':' in textarea.text:
                        debug_print("Found textarea with potential proxy data...")
                        proxy_text = textarea.text.strip()
                        
                        lines = proxy_text.split('\n')
                        for line in lines:
                            line = line.strip()
                            if ':' in line and not line.startswith('Free proxies') and not line.startswith('Updated at'):
                                try:
                                    ip, port = line.split(':', 1)
                                    ip = ip.strip()
                                    port = int(port.strip())
                                    
                                    # Basic IP validation
                                    if ip and port and len(ip.split('.')) == 4:
                                        proxy_info = {
                                            'ip': ip,
                                            'port': port,
                                            'country_code': 'Unknown',
                                            'country': 'Unknown',
                                            'anonymity': 'Unknown',
                                            'google': 'Unknown',
                                            'https': True,
                                            'last_checked': 'Unknown'
                                        }
                                        proxies.append(proxy_info)
                                        debug_print(f"Added proxy from textarea: {ip}:{port}")
                                except (ValueError, IndexError):
                                    debug_print(f"Skipping invalid proxy line: {line}")
                                    continue
                        
                        # If we found proxies in this textarea, break
                        if proxies:
                            break
        
        if not proxies:
            error_print("No suitable proxies found")
            return False
        
        info_print(f"Found {len(proxies)} proxies (excluding Vietnam)")
        
        # Select a random proxy from the list
        selected_proxy = random.choice(proxies)
        info_print(f"Selected proxy: {selected_proxy['ip']}:{selected_proxy['port']} ({selected_proxy['country']})")
        
        # Create proxy configuration in the expected format
        proxy_config = {
            'type': 'http',
            'addr': selected_proxy['ip'],
            'port': selected_proxy['port'],
            'username': None,
            'password': None
        }
        
        # Save to default proxy file
        debug_print(f"Saving proxy configuration to: {DEFAULT_PROXY_FILE}")
        try:
            with open(DEFAULT_PROXY_FILE, 'w') as f:
                json.dump(proxy_config, f, indent=2)
            
            info_print(f"Proxy configuration saved to: {DEFAULT_PROXY_FILE}")
            info_print(f"Using proxy: {proxy_config['type']}://{proxy_config['addr']}:{proxy_config['port']}")
            
            # Also save the full list for reference
            proxy_list_file = DEFAULT_PROXY_FILE.replace('.json', '_list.json')
            with open(proxy_list_file, 'w') as f:
                json.dump({
                    'selected_proxy': proxy_config,
                    'all_proxies': proxies,
                    'timestamp': datetime.now().isoformat()
                }, f, indent=2)
            
            debug_print(f"Full proxy list saved to: {proxy_list_file}")
            return True
            
        except Exception as e:
            error_print(f"Error saving proxy configuration: {e}")
            return False
            
    except requests.RequestException as e:
        error_print(f"Error retrieving proxy list: {e}")
        debug_print(f"Request error details: {type(e).__name__}: {str(e)}")
        return False
    except Exception as e:
        error_print(f"Unexpected error while getting proxies: {e}")
        debug_print(f"Unexpected error details: {type(e).__name__}: {str(e)}")
        return False

def load_proxy_config(proxy):
    """Load proxy configuration from file or dict"""
    if isinstance(proxy, str):
        debug_print(f"Loading proxy configuration from file: {proxy}")
        try:
            with open(proxy, 'r') as f:
                proxy_config = json.load(f)
            info_print(f"Loaded proxy configuration from: {proxy}")
            debug_print(f"Proxy config: {proxy_config}")
            return proxy_config
        except (FileNotFoundError, json.JSONDecodeError) as e:
            error_print(f"Error loading proxy configuration file: {e}")
            info_print("Attempting to fetch new proxy configuration...")
            if get_free_proxies():
                debug_print("Successfully fetched new proxy, retrying load...")
                try:
                    with open(proxy, 'r') as f:
                        proxy_config = json.load(f)
                    info_print(f"Loaded new proxy configuration from: {proxy}")
                    debug_print(f"New proxy config: {proxy_config}")
                    return proxy_config
                except (FileNotFoundError, json.JSONDecodeError) as retry_e:
                    error_print(f"Error loading newly fetched proxy configuration: {retry_e}")
                    return None
            else:
                error_print("Failed to fetch new proxy configuration")
                return None
    return proxy

async def test_proxy_telegram_connection(proxy_config, timeout=10):
    """
    Test if a proxy can successfully connect to Telegram
    Based on OONI probe methodology for testing Telegram connectivity
    """
    if not proxy_config:
        debug_print("No proxy configuration provided for testing")
        return {"success": False, "error": "No proxy configuration"}
    
    debug_print(f"Testing proxy connection to Telegram: {proxy_config['addr']}:{proxy_config['port']}")
    
    # Telegram endpoints to test (similar to OONI probe)
    telegram_endpoints = [
        ("149.154.175.50", 443),  # DC2 (primary)
        ("149.154.167.51", 443),  # DC4
        ("149.154.175.100", 443), # DC2 alt
        ("95.161.76.100", 443),   # DC1
    ]
    
    # Telegram web endpoints
    telegram_web_endpoints = [
        "https://web.telegram.org",
        "https://telegram.org",
        "https://core.telegram.org"
    ]
    
    results = {
        "success": False,
        "proxy": f"{proxy_config['type']}://{proxy_config['addr']}:{proxy_config['port']}",
        "tcp_connect": {},
        "web_connectivity": {},
        "error": None
    }
    
    try:
        
        # Test 1: Direct TCP connection to Telegram servers
        debug_print("Testing TCP connections to Telegram servers...")
        tcp_success_count = 0
        
        for host, port in telegram_endpoints:
            try:
                debug_print(f"Testing TCP connection to {host}:{port}")
                
                # Create socket connection through proxy
                if proxy_config['type'].lower() == 'socks5':
                    try:
                        sock = socks.socksocket()
                        sock.set_proxy(socks.SOCKS5, proxy_config['addr'], proxy_config['port'],
                                        username=proxy_config.get('username'),
                                        password=proxy_config.get('password'))
                        sock.settimeout(timeout)
                        sock.connect((host, port))
                        sock.close()
                        results["tcp_connect"][f"{host}:{port}"] = {"success": True, "time": "< timeout"}
                        tcp_success_count += 1
                        debug_print(f"✓ TCP connection successful to {host}:{port}")
                    except ImportError:
                        debug_print("PySocks not available for SOCKS5 testing, skipping TCP test")
                        results["tcp_connect"][f"{host}:{port}"] = {"success": False, "error": "PySocks not available"}
                    except Exception as e:
                        results["tcp_connect"][f"{host}:{port}"] = {"success": False, "error": str(e)}
                        debug_print(f"✗ TCP connection failed to {host}:{port}: {e}")
                else:
                    # For HTTP proxies, we'll test via web connectivity instead
                    debug_print(f"Skipping direct TCP test for HTTP proxy, will test via web connectivity")
                    results["tcp_connect"][f"{host}:{port}"] = {"success": None, "note": "HTTP proxy - tested via web"}
                    
            except Exception as e:
                results["tcp_connect"][f"{host}:{port}"] = {"success": False, "error": str(e)}
                debug_print(f"✗ TCP connection failed to {host}:{port}: {e}")
        
        # Test 2: Web connectivity to Telegram websites
        debug_print("Testing web connectivity to Telegram websites...")
        web_success_count = 0
        
        # Setup proxy for aiohttp
        proxy_url = None
        proxy_auth = None
        
        if proxy_config['type'].lower() in ['http', 'https']:
            proxy_url = f"http://{proxy_config['addr']}:{proxy_config['port']}"
            if proxy_config.get('username') and proxy_config.get('password'):
                proxy_auth = aiohttp.BasicAuth(proxy_config['username'], proxy_config['password'])
        elif proxy_config['type'].lower() == 'socks5':
            proxy_url = f"socks5://{proxy_config['addr']}:{proxy_config['port']}"
            if proxy_config.get('username') and proxy_config.get('password'):
                proxy_url = f"socks5://{proxy_config['username']}:{proxy_config['password']}@{proxy_config['addr']}:{proxy_config['port']}"
        
        connector = None
        if proxy_url:
            try:
                # Try to create connector with proxy support
                if proxy_config['type'].lower() == 'socks5':
                    try:
                        connector = ProxyConnector.from_url(proxy_url)
                        debug_print(f"Using SOCKS5 connector: {proxy_url}")
                    except ImportError:
                        debug_print("aiohttp-socks not available, falling back to basic connector")
                        connector = aiohttp.TCPConnector()
                else:
                    connector = aiohttp.TCPConnector()
            except Exception as e:
                debug_print(f"Error creating connector: {e}")
                connector = aiohttp.TCPConnector()
        
        timeout_config = aiohttp.ClientTimeout(total=timeout)
        
        async with aiohttp.ClientSession(
            connector=connector,
            timeout=timeout_config
        ) as session:
            
            for url in telegram_web_endpoints:
                try:
                    debug_print(f"Testing web connectivity to {url}")
                    start_time = asyncio.get_event_loop().time()
                    
                    kwargs = {}
                    if proxy_url and proxy_config['type'].lower() in ['http', 'https']:
                        kwargs['proxy'] = proxy_url
                        if proxy_auth:
                            kwargs['proxy_auth'] = proxy_auth
                    
                    async with session.get(url, **kwargs) as response:
                        end_time = asyncio.get_event_loop().time()
                        response_time = round((end_time - start_time) * 1000, 2)  # ms
                        
                        if response.status == 200:
                            # Check if response contains Telegram-specific content
                            content = await response.text()
                            telegram_indicators = ['telegram', 'Telegram', 'MTProto', 'telegram.org']
                            has_telegram_content = any(indicator in content for indicator in telegram_indicators)
                            
                            results["web_connectivity"][url] = {
                                "success": True,
                                "status_code": response.status,
                                "response_time_ms": response_time,
                                "has_telegram_content": has_telegram_content
                            }
                            web_success_count += 1
                            debug_print(f"✓ Web connectivity successful to {url} ({response_time}ms)")
                        else:
                            results["web_connectivity"][url] = {
                                "success": False,
                                "status_code": response.status,
                                "response_time_ms": response_time,
                                "error": f"HTTP {response.status}"
                            }
                            debug_print(f"✗ Web connectivity failed to {url}: HTTP {response.status}")
                            
                except asyncio.TimeoutError:
                    results["web_connectivity"][url] = {
                        "success": False,
                        "error": "Timeout",
                        "response_time_ms": timeout * 1000
                    }
                    debug_print(f"✗ Web connectivity timeout to {url}")
                except Exception as e:
                    results["web_connectivity"][url] = {
                        "success": False,
                        "error": str(e)
                    }
                    debug_print(f"✗ Web connectivity failed to {url}: {e}")
        
        # Determine overall success
        total_tcp_tests = len([r for r in results["tcp_connect"].values() if r.get("success") is not None])
        total_web_tests = len(telegram_web_endpoints)
        
        tcp_success_rate = tcp_success_count / max(total_tcp_tests, 1)
        web_success_rate = web_success_count / total_web_tests
        
        # Consider proxy working if at least 50% of web tests pass
        # (TCP tests are optional depending on proxy type)
        if web_success_rate >= 0.5:
            results["success"] = True
            info_print(f"✓ Proxy connectivity test PASSED - Web: {web_success_count}/{total_web_tests}, TCP: {tcp_success_count}/{total_tcp_tests}")
        else:
            results["success"] = False
            results["error"] = f"Low success rate - Web: {web_success_rate:.1%}, TCP: {tcp_success_rate:.1%}"
            info_print(f"✗ Proxy connectivity test FAILED - {results['error']}")
        
        return results
        
    except Exception as e:
        error_msg = f"Proxy test failed: {str(e)}"
        error_print(error_msg)
        debug_print(f"Proxy test exception: {type(e).__name__}: {str(e)}")
        results["success"] = False
        results["error"] = error_msg
        return results

async def test_and_select_working_proxy():
    """Test multiple proxies and select a working one for Telegram"""
    info_print("Testing proxy connectivity to Telegram servers...")
    
    # First try to get fresh proxies
    if not get_free_proxies():
        error_print("Failed to fetch proxy list")
        return None
    
    # Load the proxy list
    proxy_list_file = DEFAULT_PROXY_FILE.replace('.json', '_list.json')
    
    try:
        with open(proxy_list_file, 'r') as f:
            proxy_data = json.load(f)
        
        all_proxies = proxy_data.get('all_proxies', [])
        if not all_proxies:
            error_print("No proxies available for testing")
            return None
        
        info_print(f"Testing {len(all_proxies)} proxies for Telegram connectivity...")
        
        # Test up to 10 random proxies to find a working one
        test_proxies = random.sample(all_proxies, min(10, len(all_proxies)))
        
        async def test_proxies():
            working_proxies = []
            
            for i, proxy_info in enumerate(test_proxies, 1):
                info_print(f"Testing proxy {i}/{len(test_proxies)}: {proxy_info['ip']}:{proxy_info['port']} ({proxy_info['country']})")
                
                proxy_config = {
                    'type': 'http',
                    'addr': proxy_info['ip'],
                    'port': proxy_info['port'],
                    'username': None,
                    'password': None
                }
                
                test_result = await test_proxy_telegram_connection(proxy_config, timeout=15)
                
                if test_result['success']:
                    info_print(f"✓ Proxy {i} WORKS: {proxy_info['ip']}:{proxy_info['port']}")
                    working_proxies.append((proxy_info, proxy_config, test_result))
                else:
                    debug_print(f"✗ Proxy {i} failed: {test_result.get('error', 'Unknown error')}")
            
            return working_proxies
        
        # Run the async test
        working_proxies = await test_proxies()
        
        if working_proxies:
            # Select the best working proxy (first one that works)
            best_proxy_info, best_proxy_config, test_result = working_proxies[0]
            
            info_print(f"Selected working proxy: {best_proxy_info['ip']}:{best_proxy_info['port']} ({best_proxy_info['country']})")
            
            # Save the working proxy configuration
            with open(DEFAULT_PROXY_FILE, 'w') as f:
                json.dump(best_proxy_config, f, indent=2)
            
            info_print(f"Working proxy configuration saved to: {DEFAULT_PROXY_FILE}")
            return best_proxy_config
        else:
            error_print("No working proxies found for Telegram")
            return None
            
    except Exception as e:
        error_print(f"Error testing proxies: {e}")
        debug_print(f"Proxy testing error: {type(e).__name__}: {str(e)}")
        return None

def create_telegram_client(session_file, api_id, api_hash, proxy=None):
    """Create TelegramClient with or without proxy"""
    if proxy:
        debug_print(f"Using proxy: {proxy['type']}://{proxy['addr']}:{proxy['port']}")
        if proxy['type'].lower() == 'socks5':
            return TelegramClient(
                session_file, api_id, api_hash,
                proxy=(proxy['type'], proxy['addr'], proxy['port'], 
                       proxy.get('username'), proxy.get('password')),
                connection=connection.ConnectionTcpMTProxyRandomizedIntermediate
            )
        else:  # http proxy
            return TelegramClient(
                session_file, api_id, api_hash,
                proxy=(proxy['type'], proxy['addr'], proxy['port'],
                       proxy.get('username'), proxy.get('password'))
            )
    else:
        return TelegramClient(session_file, api_id, api_hash)

def extract_button_info(reply_markup):
    """Extract button information from reply markup"""
    buttons = []
    if reply_markup:
        debug_print("Processing reply markup buttons...")
        for row_idx, row in enumerate(reply_markup.rows):
            for btn_idx, button in enumerate(row.buttons):
                button_info = {"text": button.text}
                if hasattr(button, 'url') and button.url:
                    button_info["url"] = button.url
                    button_info["type"] = "url"
                    debug_print(f"Button {row_idx}-{btn_idx}: URL button '{button.text}' -> {button.url}")
                elif hasattr(button, 'data'):
                    button_info["data"] = button.data.decode() if button.data else None
                    button_info["callback_data"] = button.data.decode() if button.data else None
                    button_info["type"] = "callback"
                    debug_print(f"Button {row_idx}-{btn_idx}: Callback button '{button.text}' -> {button_info['data']}")
                else:
                    button_info["type"] = "keyboard"
                    debug_print(f"Button {row_idx}-{btn_idx}: Keyboard button '{button.text}'")
                buttons.append(button_info)
    return buttons

def create_message_handler(bot_entity):
    """Create message handler for bot replies"""
    bot_reply = None
    
    async def handler(event):
        nonlocal bot_reply
        debug_print(f"Received message from bot: ID={event.message.id}, Text={event.message.text[:100]}...")
        
        buttons = extract_button_info(event.message.reply_markup)
        
        bot_reply = {
            "message_id": event.message.id,
            "date": event.message.date.timestamp(),
            "text": event.message.text,
            "buttons": buttons
        }
        debug_print(f"Bot reply captured: {len(buttons)} buttons found")
    
    return handler, lambda: bot_reply

async def wait_for_reply(get_bot_reply, timeout=30):
    """Wait for bot reply with timeout"""
    elapsed = 0
    info_print("Waiting for bot reply...")
    while get_bot_reply() is None and elapsed < timeout:
        await asyncio.sleep(0.1)
        elapsed += 0.1
        if int(elapsed) != int(elapsed - 0.1):  # Print every second
            debug_print(f"Waiting for reply... {int(elapsed)}s / {timeout}s")
            if int(elapsed) % 5 == 0:  # Print progress every 5 seconds
                info_print(f"Still waiting... {int(elapsed)}s")
    
    return get_bot_reply()

async def handle_search_message(get_bot_reply, set_bot_reply):
    """Handle 'searching...' message and wait for actual result"""
    bot_reply = get_bot_reply()
    if bot_reply and "searching..." in bot_reply.get("text", "").lower():
        info_print("Bot is searching, waiting for final result...")
        debug_print("Detected 'searching...' message, resetting bot_reply to wait for actual result")
        set_bot_reply(None)  # Reset to wait for the next message
        
        # Wait for the actual search result (extended timeout)
        return await wait_for_reply(get_bot_reply, timeout=40)
    
    return bot_reply

async def fetch_recent_messages(client, bot_entity, sent_message):
    """Fetch recent messages from bot if no immediate reply"""
    info_print("No immediate reply received, checking for recent messages...")
    debug_print("Attempting to fetch recent messages from bot...")
    await asyncio.sleep(5)  # Wait a bit more
    
    message_count = 0
    seen_messages = set()  # Track message IDs to avoid duplicates
    
    async for message in client.iter_messages(bot_entity, limit=5):
        message_count += 1
        
        # Skip if we've already processed this message
        if message.id in seen_messages:
            debug_print(f"Skipping duplicate message ID: {message.id}")
            continue
        
        seen_messages.add(message.id)
        debug_print(f"Checking message {message_count}: ID={message.id}, Date={message.date}, Text={message.text[:50]}...")
        
        # Check if this message is newer than our sent message
        if message.date >= sent_message.date:
            debug_print("Found newer message from bot!")
            buttons = extract_button_info(message.reply_markup)
            
            bot_reply = {
                "message_id": message.id,
                "date": message.date.timestamp(),
                "text": message.text,
                "buttons": buttons
            }
            info_print("Found recent message from bot!")
            return bot_reply
    
    debug_print(f"No newer messages found among {len(seen_messages)} unique recent messages")
    return None

async def click_callback_button(api_id, api_hash, phone_number, bot_username, message_id, button_data, session_file='telegram_session', proxy=None):
    """
    Click a callback button in a bot's message
    
    Args:
        api_id: Your Telegram API ID
        api_hash: Your Telegram API hash
        phone_number: Your phone number (not used, kept for compatibility)
        bot_username: Bot's username
        message_id: ID of the message containing the button
        button_data: The callback data of the button to click
        session_file: Name of the session file
        proxy: Proxy configuration dict with keys: type, addr, port, username, password
               Example: {'type': 'http', 'addr': '127.0.0.1', 'port': 8080}
               or {'type': 'socks5', 'addr': '127.0.0.1', 'port': 1080, 'username': 'user', 'password': 'pass'}
               or string path to JSON file containing proxy configuration
    """
    debug_print(f"Clicking callback button: message_id={message_id}, button_data={button_data}")
    
    # Load proxy configuration
    proxy_config = load_proxy_config(proxy)
    if proxy and proxy_config is None:
        return {"error": f"Error loading proxy configuration"}
    
    # Create client with or without proxy
    client = create_telegram_client(session_file, api_id, api_hash, proxy_config)
    bot_reply = None
    
    try:
        session_path = f"{session_file}.session"
        if not os.path.exists(session_path):
            error_print(f"Session file not found: {session_path}")
            return {"error": "Session file not found. Run script interactively first to create session."}
        
        debug_print("Starting client for button click...")
        if proxy_config:
            info_print(f"Connecting through proxy for button click: {proxy_config['type']}://{proxy_config['addr']}:{proxy_config['port']}")
        await client.start()
        
        if not await client.is_user_authorized():
            error_print("Session expired or not authorized")
            return {"error": "Session expired. Please delete the session file and run interactively to re-authenticate."}
        
        # Get the bot entity
        debug_print(f"Getting bot entity: {bot_username}")
        bot_entity = await client.get_entity(bot_username)
        
        # Handler for incoming messages from the bot after button click
        @client.on(events.NewMessage(from_users=bot_entity))
        async def message_handler(event):
            nonlocal bot_reply
            debug_print(f"Received response after button click: {event.message.text[:100]}...")
            buttons = []
            
            if event.message.reply_markup:
                debug_print("Processing reply markup after button click...")
                for row in event.message.reply_markup.rows:
                    for button in row.buttons:
                        button_info = {"text": button.text}
                        if hasattr(button, 'url') and button.url:
                            button_info["url"] = button.url
                            button_info["type"] = "url"
                        elif hasattr(button, 'data'):
                            button_info["data"] = button.data.decode() if button.data else None
                            button_info["type"] = "callback"
                        else:
                            button_info["type"] = "keyboard"
                        buttons.append(button_info)
            
            bot_reply = {
                "message_id": event.message.id,
                "date": event.message.date.timestamp(),
                "text": event.message.text,
                "buttons": buttons
            }
        
        # Click the callback button using the correct method
        debug_print("Executing callback button click...")
        from telethon.tl.functions.messages import GetBotCallbackAnswerRequest

        await client(GetBotCallbackAnswerRequest(
            peer=bot_entity,
            msg_id=message_id,
            data=button_data.encode() if isinstance(button_data, str) else button_data
        ))
        info_print("Callback button clicked successfully")
        
        # Wait for bot reply (timeout after 30 seconds)
        timeout = 30
        elapsed = 0
        while bot_reply is None and elapsed < timeout:
            await asyncio.sleep(0.1)
            elapsed += 0.1
            if int(elapsed) % 5 == 0 and int(elapsed) != int(elapsed - 0.1):
                debug_print(f"Waiting for response after button click... {int(elapsed)}s")
        
        # If no immediate reply, check for recent messages
        if bot_reply is None:
            debug_print("No immediate response, checking recent messages...")
            await asyncio.sleep(2)
            async for message in client.iter_messages(bot_entity, limit=3):
                if message.date > datetime.now().timestamp() - 35:  # Messages from last 35 seconds
                    debug_print(f"Found recent message: {message.text[:50]}...")
                    buttons = []
                    
                    if message.reply_markup:
                        for row in message.reply_markup.rows:
                            for button in row.buttons:
                                button_info = {"text": button.text}
                                if hasattr(button, 'url') and button.url:
                                    button_info["url"] = button.url
                                    button_info["type"] = "url"
                                elif hasattr(button, 'data'):
                                    button_info["data"] = button.data.decode() if button.data else None
                                    button_info["type"] = "callback"
                                else:
                                    button_info["type"] = "keyboard"
                                buttons.append(button_info)
                    
                    bot_reply = {
                        "message_id": message.id,
                        "date": message.date.timestamp(),
                        "text": message.text,
                        "buttons": buttons
                    }
                    break
        
        result = {
            "ok": True,
            "button_clicked": {
                "message_id": message_id,
                "button_data": button_data
            },
            "bot_reply": bot_reply
        }
        debug_print("Button click operation completed successfully")
        return result
        
    except Exception as e:
        error_print(f"Error clicking button: {str(e)}")
        debug_print(f"Button click exception: {type(e).__name__}: {str(e)}")
        return {"error": f"Error clicking button: {str(e)}"}
    finally:
        debug_print("Disconnecting client after button click...")
        await client.disconnect()

async def send_message_to_bot(api_id, api_hash, phone_number, bot_username, message, session_file='telegram_session', proxy=None):
    """
    Send a message from your user account to a bot and wait for reply
    
    Args:
        api_id: Your Telegram API ID (get from my.telegram.org)
        api_hash: Your Telegram API hash
        phone_number: Your phone number
        bot_username: Bot's username (e.g., 'your_bot_name')
        message: Message text to send
        session_file: Name of the session file to save/load
        proxy: Proxy configuration dict with keys: type, addr, port, username, password
               Example: {'type': 'http', 'addr': '127.0.0.1', 'port': 8080}
               or {'type': 'socks5', 'addr': '127.0.0.1', 'port': 1080, 'username': 'user', 'password': 'pass'}
               or string path to JSON file containing proxy configuration
    """
    debug_print(f"Initializing TelegramClient with session file: {session_file}")
    
    # Load proxy configuration
    proxy_config = load_proxy_config(proxy)
    if proxy and proxy_config is None:
        return {"error": f"Error loading proxy configuration"}
    
    # Create client
    client = create_telegram_client(session_file, api_id, api_hash, proxy_config)
    
    try:
        # Check if session file exists
        session_path = f"{session_file}.session"
        debug_print(f"Checking for session file: {session_path}")
        if not os.path.exists(session_path):
            error_print(f"Session file '{session_path}' not found!")
            info_print("You need to create a session first by running this script interactively once.")
            info_print("After that, the session will be saved and you can run without manual input.")
            return {"error": "Session file not found. Run script interactively first to create session."}
        
        info_print("Using cached session...")
        if proxy_config:
            info_print(f"Connecting through proxy: {proxy_config['type']}://{proxy_config['addr']}:{proxy_config['port']}")
        
        debug_print("Starting Telegram client...")
        await client.start()
        debug_print("Client started successfully")
        
        # Verify we're connected
        debug_print("Checking user authorization...")
        if not await client.is_user_authorized():
            error_print("Session expired or not authorized")
            return {"error": "Session expired. Please delete the session file and run interactively to re-authenticate."}
        
        debug_print("User authorized successfully")
        
        # Get the bot entity
        debug_print(f"Getting bot entity for: {bot_username}")
        bot_entity = await client.get_entity(bot_username)
        debug_print(f"Bot entity retrieved: {bot_entity.id}")
        
        # Create message handler
        handler, get_bot_reply = create_message_handler(bot_entity)
        set_bot_reply = lambda value: None  # For resetting bot_reply in search handling
        
        # Set up handler closure for setting bot_reply
        def create_setter():
            nonlocal handler, get_bot_reply
            bot_reply_value = [None]
            
            async def new_handler(event):
                nonlocal bot_reply_value
                debug_print(f"Received message from bot: ID={event.message.id}, Text={event.message.text[:100]}...")
                
                buttons = extract_button_info(event.message.reply_markup)
                
                bot_reply_value[0] = {
                    "message_id": event.message.id,
                    "date": event.message.date.timestamp(),
                    "text": event.message.text,
                    "buttons": buttons
                }
                debug_print(f"Bot reply captured: {len(buttons)} buttons found")
            
            def get_reply():
                return bot_reply_value[0]
                
            def set_reply(value):
                bot_reply_value[0] = value
                
            return new_handler, get_reply, set_reply
        
        handler, get_bot_reply, set_bot_reply = create_setter()
        client.on(events.NewMessage(from_users=bot_entity))(handler)
        
        # Send message to the bot
        debug_print(f"Sending message to bot: '{message}'")
        result = await client.send_message(bot_username, message)
        info_print(f"Message sent successfully. Message ID: {result.id}")

        # Wait for bot reply
        bot_reply = await wait_for_reply(get_bot_reply, timeout=30)
        
        # Handle search message
        bot_reply = await handle_search_message(get_bot_reply, set_bot_reply)
        
        # If still no reply, fetch recent messages
        if bot_reply is None:
            bot_reply = await fetch_recent_messages(client, bot_entity, result)
        
        debug_print("Preparing response data...")
        response = {
            "ok": True,
            "sent_message": {
                "message_id": result.id,
                "date": result.date.timestamp(),
                "text": result.text
            },
            "bot_reply": bot_reply
        }
        debug_print(f"Response prepared successfully. Bot reply: {'Yes' if bot_reply else 'No'}")
        return response
        
    except Exception as e:
        error_print(f"Error sending message: {str(e)}")
        debug_print(f"Exception details: {type(e).__name__}: {str(e)}")
        return {"error": f"Error sending message: {str(e)}"}
    finally:
        debug_print("Disconnecting client...")
        await client.disconnect()
        debug_print("Client disconnected")

async def create_session(api_id, api_hash, phone_number, session_file='telegram_session'):
    """Create a new session file interactively"""
    debug_print(f"Creating new session with file: {session_file}")
    client = TelegramClient(session_file, api_id, api_hash)
    
    try:
        debug_print("Starting client for session creation...")
        await client.start(phone_number)
        info_print(f"Session created successfully! File saved as '{session_file}.session'")
        info_print("You can now run the script without manual input.")
        debug_print("Session creation completed successfully")
    except Exception as e:
        error_print(f"Error creating session: {e}")
        debug_print(f"Session creation failed: {type(e).__name__}: {str(e)}")
    finally:
        debug_print("Disconnecting client after session creation...")
        await client.disconnect()

def format_result(result):
    """Format the result in a human-readable way"""
    output = []
    output.append("\n" + "="*50)
    output.append("TELEGRAM BOT INTERACTION RESULT")
    output.append("="*50)
    
    if "error" in result:
        output.append(f"❌ ERROR: {result['error']}")
        error_print(result['error'])
    elif result.get("ok"):
        output.append("✅ SUCCESS: Message sent and received!")
        output.append("")
        
        # Format sent message
        sent_msg = result.get("sent_message", {})
        if sent_msg:
            sent_time = datetime.fromtimestamp(sent_msg.get("date", 0)).strftime("%Y-%m-%d %H:%M:%S")
            output.append("📤 SENT MESSAGE:")
            output.append(f"   ID: {sent_msg.get('message_id', 'N/A')}")
            output.append(f"   Time: {sent_time}")
            output.append(f"   Text: {sent_msg.get('text', 'N/A')}")
            output.append("")
            
            debug_print(f"Sent message details: ID={sent_msg.get('message_id')}, Time={sent_time}")
        
        # Format bot reply
        bot_reply = result.get("bot_reply")
        if bot_reply:
            reply_time = datetime.fromtimestamp(bot_reply.get("date", 0)).strftime("%Y-%m-%d %H:%M:%S")
            output.append("📥 BOT REPLY:")
            output.append(f"   ID: {bot_reply.get('message_id', 'N/A')}")
            output.append(f"   Time: {reply_time}")
            output.append(f"   Text: {bot_reply.get('text', 'N/A')}")
            
            debug_print(f"Bot reply details: ID={bot_reply.get('message_id')}, Time={reply_time}, Buttons={len(bot_reply.get('buttons', []))}")
            
            # Format buttons if present
            buttons = bot_reply.get("buttons", [])
            if buttons:
                output.append("   Buttons:")
                for i, button in enumerate(buttons, 1):
                    button_type = button.get("type", "unknown")
                    button_text = button.get("text", "N/A")
                    
                    if button_type == "url":
                        output.append(f"     {i}. {button_text} (URL: {button.get('url', 'N/A')})")
                        debug_print(f"Button {i}: URL - {button_text} -> {button.get('url')}")
                    elif button_type == "callback":
                        callback_data = button.get('callback_data', 'N/A')
                        output.append(f"     {i}. {button_text} (Callback: {callback_data})")
                        debug_print(f"Button {i}: Callback - {button_text} -> {callback_data}")
                    else:
                        output.append(f"     {i}. {button_text} ({button_type})")
                        debug_print(f"Button {i}: {button_type} - {button_text}")
        else:
            output.append("📥 BOT REPLY: No reply received (timeout)")
            debug_print("No bot reply received within timeout period")
    else:
        output.append("❌ FAILED: Message sending failed")
        error_print("Message sending failed")
    
    output.append("="*50)
    
    # Print to console and log
    result_text = "\n".join(output)
    if logger:
        logger.info("Formatting result for display")
        logger.info(result_text)

def handle_single_search_result(bot_reply):
    """
    Handle a single search result based on whether the first callback button contains "Request"
    
    Args:
        bot_reply: Dictionary containing bot reply with buttons
        
    Returns:
        Dictionary with action type and relevant information
    """
    if not bot_reply or not bot_reply.get("buttons"):
        debug_print("No bot reply or buttons found")
        return {
            "action": "no_buttons",
            "message": "No buttons available in the response"
        }
    
    buttons = bot_reply.get("buttons", [])
    if not buttons:
        debug_print("Empty buttons list")
        return {
            "action": "no_buttons",
            "message": "No buttons available in the response"
        }
    
    # Find the first callback button
    first_callback_button = None
    for button in buttons:
        if button.get("type") == "callback":
            first_callback_button = button
            break
    
    if not first_callback_button:
        debug_print("No callback buttons found")
        return {
            "action": "no_callback_buttons",
            "message": "No callback buttons available in the response"
        }
    
    button_text = first_callback_button.get("text", "").strip()
    callback_data = first_callback_button.get("callback_data") or first_callback_button.get("data")
    
    debug_print(f"First callback button text: '{button_text}'")
    
    # Check if the first callback button contains "Request"
    if "request" in button_text.lower():
        info_print(f"Found 'Request' callback button: {button_text}")
        
        return {
            "action": "request_callback",
            "button_text": button_text,
            "callback_data": callback_data,
            "message_id": bot_reply.get("message_id"),
            "message": f"Ready to click request button: {button_text}"
        }
    else:
        info_print(f"First callback button does not contain 'Request': {button_text}")
        
        return {
            "action": "other_callback",
            "button_text": button_text,
            "callback_data": callback_data,
            "message_id": bot_reply.get("message_id"),
            "message": f"Other callback button found: {button_text}"
        }

async def handle_button_click_logic(bot_reply, proxy=None):
    """
    Handle button clicking based on button text - interactive prompts for user
    
    Args:
        bot_reply: Dictionary containing bot reply with buttons
        proxy: Proxy configuration (same format as other functions)
        
    Returns:
        Dictionary with click result or None if no action needed
    """
    if not bot_reply or not bot_reply.get("buttons"):
        debug_print("No bot reply or buttons found for button click logic")
        return None
    
    buttons = bot_reply.get("buttons", [])
    if not buttons:
        debug_print("Empty buttons list for button click logic")
        return None
    
    # Find the first callback button
    first_callback_button = None
    for button in buttons:
        if button.get("type") == "callback":
            first_callback_button = button
            break
    
    if not first_callback_button:
        debug_print("No callback buttons found for button click logic")
        return None
    
    button_text = first_callback_button.get("text", "").strip()
    callback_data = first_callback_button.get("callback_data") or first_callback_button.get("data")
    message_id = bot_reply.get("message_id")
    
    has_request = "request" in button_text.lower()
    
    debug_print(f"Button click logic - Button text: '{button_text}', Has 'Request': {has_request}")
    
    if has_request:
        # Paper is not available on Nexus - ask if user wants to request it
        print(f"\n📋 The corresponding paper is not available on Nexus.")
        user_input = input("Do you want to request it? [Y/n]: ").strip().lower()
        
        if user_input in ['', 'y', 'yes']:
            info_print(f"User chose to request the paper - clicking button: {button_text}")
            debug_print(f"Request button click parameters - Message ID: {message_id}, Callback data: {callback_data}")
            
            # Click the callback button
            click_result = await click_callback_button(
                API_ID, API_HASH, PHONE, BOT_USERNAME, 
                message_id, callback_data, SESSION_FILE, proxy
            )
            
            return click_result
        else:
            info_print("User chose not to request the paper")
            return None
    else:
        # Paper is available - clean button text and ask if user wants to download
        
        print("\n📄 The corresponding paper is available on Nexus.")
        user_input = input("Do you want to download it? [Y/n]: ").strip().lower()
        
        if user_input in ['', 'y', 'yes']:
            info_print(f"User chose to download the paper - clicking button: {button_text}")
            debug_print(f"Download button click parameters - Message ID: {message_id}, Callback data: {callback_data}")
            
            # Click the callback button
            click_result = await click_callback_button(
                API_ID, API_HASH, PHONE, BOT_USERNAME, 
                message_id, callback_data, SESSION_FILE, proxy
            )
            
            return click_result
        else:
            info_print("User chose not to download the paper")
            return None

async def download_telegram_file(client, message, download_path=None):
    """
    Download a file from a Telegram message
    
    Args:
        client: TelegramClient instance
        message: Telegram message containing the file
        download_path: Path where to save the file (optional)
        
    Returns:
        Dictionary with download result
    """
    try:
        # Check if message has media
        if not message.media:
            return {"success": False, "error": "Message contains no media"}
        
        # Get file name
        filename = getattr(message.media, 'filename', None)
        if not filename:
            # Try to get filename from document attributes
            if hasattr(message.media, 'document') and message.media.document.attributes:
                for attr in message.media.document.attributes:
                    if hasattr(attr, 'file_name'):
                        filename = attr.file_name
                        break
            
            # If still no filename, generate one
            if not filename:
                file_ext = ""
                if hasattr(message.media, 'document'):
                    mime_type = message.media.document.mime_type
                    if mime_type == 'application/pdf':
                        file_ext = ".pdf"
                    elif 'image' in mime_type:
                        file_ext = ".jpg"
                    elif 'video' in mime_type:
                        file_ext = ".mp4"
                filename = f"telegram_file_{message.id}{file_ext}"
        
        # Set download path
        if not download_path:
            # Create downloads directory in user's home
            downloads_dir = os.path.join(os.path.expanduser("~"), "Downloads", "TelegramFiles")
            os.makedirs(downloads_dir, exist_ok=True)
            download_path = os.path.join(downloads_dir, filename)
        elif os.path.isdir(download_path):
            download_path = os.path.join(download_path, filename)
        
        # Get file size
        file_size = getattr(message.media.document, 'size', 0) if hasattr(message.media, 'document') else 0
        
        info_print(f"Starting download: {filename}")
        info_print(f"File size: {file_size / (1024*1024):.2f} MB" if file_size > 0 else "File size: Unknown")
        info_print(f"Download path: {download_path}")
        
        # Download with progress
        last_progress = 0
        
        def progress_callback(current, total):
            nonlocal last_progress
            if total > 0:
                progress = int((current / total) * 100)
                if progress >= last_progress + 10:  # Update every 10%
                    info_print(f"Download progress: {progress}% ({current / (1024*1024):.2f}/{total / (1024*1024):.2f} MB)")
                    last_progress = progress
        
        # Perform the download
        start_time = datetime.now()
        path = await client.download_media(
            message,
            file=download_path,
            progress_callback=progress_callback
        )
        end_time = datetime.now()
        
        download_time = (end_time - start_time).total_seconds()
        
        if path and os.path.exists(path):
            actual_size = os.path.getsize(path)
            speed_mbps = (actual_size / (1024*1024)) / max(download_time, 1)
            
            info_print(f"✓ Download completed successfully!")
            info_print(f"File saved to: {path}")
            info_print(f"Download time: {download_time:.2f} seconds")
            info_print(f"Average speed: {speed_mbps:.2f} MB/s")
            
            return {
                "success": True,
                "file_path": path,
                "filename": filename,
                "file_size": actual_size,
                "download_time": download_time,
                "speed_mbps": speed_mbps
            }
        else:
            return {"success": False, "error": "File download failed - file not found after download"}
            
    except Exception as e:
        error_print(f"Error downloading file: {str(e)}")
        debug_print(f"Download error details: {type(e).__name__}: {str(e)}")
        return {"success": False, "error": f"Download failed: {str(e)}"}

async def handle_file_download_from_bot_reply(bot_reply, proxy=None):
    """
    Handle file download from bot reply if it contains a document
    
    Args:
        bot_reply: Dictionary containing bot reply information
        proxy: Proxy configuration (same format as other functions)
        
    Returns:
        Dictionary with download result or None if no file to download
    """
    if not bot_reply:
        debug_print("No bot reply for file download")
        return None
    
    # Load proxy configuration
    proxy_config = load_proxy_config(proxy)
    if proxy and proxy_config is None:
        return {"success": False, "error": "Error loading proxy configuration"}
    
    # Create client
    client = create_telegram_client(SESSION_FILE, API_ID, API_HASH, proxy_config)
    
    try:
        # Start client
        await client.start()
        
        if not await client.is_user_authorized():
            return {"success": False, "error": "Session expired"}
        
        # Get the bot entity
        bot_entity = await client.get_entity(BOT_USERNAME)
        
        # Get the message by ID
        message_id = bot_reply.get("message_id")
        if not message_id:
            return {"success": False, "error": "No message ID in bot reply"}
        
        # Fetch the message
        message = await client.get_messages(bot_entity, ids=message_id)
        if not message:
            return {"success": False, "error": "Could not fetch message"}
        
        # Check if message contains a file
        if not message.media:
            debug_print("Message contains no media for download")
            return None
        
        info_print("File detected in bot reply, starting download...")
        
        # Download the file
        download_result = await download_telegram_file(client, message)
        
        return download_result
        
    except Exception as e:
        error_print(f"Error handling file download: {str(e)}")
        debug_print(f"File download handling error: {type(e).__name__}: {str(e)}")
        return {"success": False, "error": f"File download handling failed: {str(e)}"}
    finally:
        await client.disconnect()

# Get user input with timeout
def get_input_with_timeout(prompt, timeout=30, default='y'):
    """Get user input with timeout, return default if timeout occurs"""
    print(prompt, end='', flush=True)
    
    if sys.platform == 'win32':
        # Windows doesn't support select on stdin, use a simpler approach
        
        input_chars = []
        start_time = time.time()
        
        while True:
            if msvcrt.kbhit():
                char = msvcrt.getch().decode('utf-8')
                if char == '\r':  # Enter key
                    print()
                    return ''.join(input_chars).strip().lower()
                elif char == '\b':  # Backspace
                    if input_chars:
                        input_chars.pop()
                        print('\b \b', end='', flush=True)
                else:
                    input_chars.append(char)
                    print(char, end='', flush=True)
            
            if time.time() - start_time > timeout:
                print(f"\nTimeout after {timeout} seconds, using default: {default}")
                return default
            
            time.sleep(0.1)
    else:
        # Unix/Linux/macOS
        ready, _, _ = select.select([sys.stdin], [], [], timeout)
        if ready:
            return sys.stdin.readline().strip().lower()
        else:
            print(f"\nTimeout after {timeout} seconds, using default: {default}")
            return default

async def load_credentials_from_file(credentials_path):
    """Load API credentials from JSON file"""
    global API_ID, API_HASH, PHONE, BOT_USERNAME
    
    debug_print(f"Loading credentials from: {credentials_path}")
    
    if not os.path.exists(credentials_path):
        error_print(f"Credentials file not found: {credentials_path}")
        return False
    
    try:
        with open(credentials_path, 'r') as f:
            creds = json.load(f)
        
        API_ID = creds.get("api_id", API_ID)
        API_HASH = creds.get("api_hash", API_HASH)
        PHONE = creds.get("phone", PHONE)
        BOT_USERNAME = creds.get("bot_username", BOT_USERNAME)
        
        info_print(f"Loaded credentials from: {credentials_path}")
        debug_print(f"API_ID: {API_ID}, BOT_USERNAME: {BOT_USERNAME}")
        
        # Update credentials to default location if necessary
        if credentials_path != CREDENTIALS_FILE:
            try:
                debug_print(f"Updating credentials to default location: {CREDENTIALS_FILE}")
                with open(CREDENTIALS_FILE, 'w') as f:
                    json.dump(creds, f, indent=2)
                info_print(f"Credentials copied to default location: {CREDENTIALS_FILE}")
            except Exception as e:
                debug_print(f"Warning: Could not update credentials to default location: {e}")
        
        return True
        
    except (json.JSONDecodeError, KeyError) as e:
        error_print(f"Error loading credentials file: {e}")
        debug_print(f"Credentials loading error: {type(e).__name__}: {str(e)}")
        return False

async def setup_proxy_configuration(proxy_arg):
    """Setup and test proxy configuration"""
    if proxy_arg is None:
        debug_print("No proxy specified, connecting directly")
        return None
    
    info_print("Proxy option specified")
    
    # If proxy is just the flag without value, use default
    proxy_file = proxy_arg if proxy_arg else DEFAULT_PROXY_FILE
    debug_print(f"Proxy file path: {proxy_file}")
    
    # Check if proxy file exists
    if os.path.exists(proxy_file):
        info_print(f"Loading existing proxy configuration from: {proxy_file}")
        proxy_config = load_proxy_config(proxy_file)
        if not proxy_config:
            error_print(f"Failed to load proxy configuration from: {proxy_file}")
            return False
        
        # Test the existing proxy
        info_print("Testing existing proxy configuration...")
        test_result = await test_proxy_telegram_connection(proxy_config, timeout=15)
        
        if test_result['success']:
            info_print("✓ Existing proxy works for Telegram")
            return proxy_file
        else:
            error_print("✗ Existing proxy failed Telegram connectivity test")
            info_print("Searching for a new working proxy...")
    else:
        info_print(f"Proxy file not found: {proxy_file}")
        info_print("Searching for a working proxy...")
    
    # Try to find a working proxy
    working_proxy = await test_and_select_working_proxy()
    if working_proxy:
        return DEFAULT_PROXY_FILE
    else:
        error_print("Could not find a working proxy for Telegram")
        error_print("You can either:")
        error_print("1. Try running again (will test different proxies)")
        error_print("2. Run without --proxy to connect directly")
        error_print("3. Provide a custom proxy configuration file")
        return False

async def handle_request_button(button_text, callback_data, message_id, proxy_to_use):
    """Handle request button click"""
    print(f"\n📋 The corresponding paper is not available on Nexus.")
    user_input = get_input_with_timeout("Do you want to request it? [y/N]: ", timeout=30, default='n')
    
    if user_input in ['', 'y', 'yes']:
        info_print(f"User chose to request the paper - clicking button: {button_text}")
        
        # Click the request button
        click_result = await click_callback_button(
            API_ID, API_HASH, PHONE, BOT_USERNAME,
            message_id, callback_data, SESSION_FILE, proxy_to_use
        )
        
        if click_result.get("ok"):
            info_print("✓ Successfully requested the paper")
            if click_result.get("bot_reply") and click_result["bot_reply"].get("text"):
                print(f"Bot response: {click_result['bot_reply']['text']}")
        else:
            error_print(f"✗ Failed to request the paper: {click_result.get('error', 'Unknown error')}")
    else:
        info_print("User chose not to request the paper")

async def handle_download_button(button_text, callback_data, message_id, proxy_to_use):
    """Handle download button click"""
    print(f"\n📄 The corresponding paper is available on Nexus.")
    
    user_input = get_input_with_timeout("Do you want to download it? [Y/n]: ", timeout=30, default='y')
    
    if user_input in ['', 'y', 'yes']:
        info_print(f"User chose to download the paper - clicking button: {button_text}")
        
        # Click the download button
        click_result = await click_callback_button(
            API_ID, API_HASH, PHONE, BOT_USERNAME,
            message_id, callback_data, SESSION_FILE, proxy_to_use
        )
        
        if click_result.get("ok"):
            info_print("✓ Successfully initiated download")
            if click_result.get("bot_reply") and click_result["bot_reply"].get("text"):
                print(f"Bot response: {click_result['bot_reply']['text']}")
            
            await wait_and_download_file(click_result, proxy_to_use)
        else:
            error_print(f"✗ Failed to download the paper: {click_result.get('error', 'Unknown error')}")
    else:
        info_print("User chose not to download the paper")

async def wait_and_download_file(click_result, proxy_to_use):
    """Wait for file upload and download it"""
    # Extract file size information from bot response if available
    bot_text = click_result.get("bot_reply", {}).get("text", "")
    file_size_mb = 0
    
    # Try to extract file size from bot response
    size_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:mb|MB|megabytes?)', bot_text, re.IGNORECASE)
    if size_match:
        file_size_mb = float(size_match.group(1))
        info_print(f"Detected file size: {file_size_mb} MB")
    else:
        # Check for other size units
        kb_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:kb|KB|kilobytes?)', bot_text, re.IGNORECASE)
        if kb_match:
            file_size_mb = float(kb_match.group(1)) / 1024
            info_print(f"Detected file size: {file_size_mb:.2f} MB")
        else:
            # Default assumption for academic papers
            file_size_mb = 5.0
            info_print("No file size detected, assuming 5 MB for academic paper")
    
    # Calculate wait time based on file size
    base_wait = 10
    size_based_wait = int(file_size_mb * 5)
    total_wait = max(base_wait, size_based_wait)
    
    info_print(f"Waiting {total_wait} seconds for file upload to Telegram (based on {file_size_mb} MB file size)...")
    
    # Wait with progress indication
    for i in range(total_wait):
        if i % 5 == 0 and i > 0:
            info_print(f"Still waiting... {i}/{total_wait} seconds")
        await asyncio.sleep(1)
    
    info_print("Wait time completed, checking for file...")
    
    # Handle file download if the bot reply contains a file
    download_result = await handle_file_download_from_bot_reply(
        click_result.get("bot_reply"), proxy_to_use
    )
    
    if download_result and download_result.get("success"):
        info_print("✓ File downloaded successfully!")
        info_print(f"File saved to: {download_result['file_path']}")
        info_print(f"File size: {download_result['file_size'] / (1024*1024):.2f} MB")
        info_print(f"Download speed: {download_result['speed_mbps']:.2f} MB/s")
    elif download_result and not download_result.get("success"):
        error_print(f"✗ File download failed: {download_result.get('error', 'Unknown error')}")
    else:
        debug_print("No file to download in bot reply")

async def process_callback_buttons(bot_reply, proxy_to_use):
    """Process callback buttons from bot reply"""
    callback_buttons = [btn for btn in bot_reply.get("buttons", []) if btn.get("type") == "callback"]
    
    if not callback_buttons:
        debug_print("No callback buttons found in search results")
        return
    
    info_print(f"Found {len(callback_buttons)} callback buttons in search results")
    
    # Only handle the first callback button
    first_button = callback_buttons[0]
    button_text = first_button.get("text", "").strip()
    callback_data = first_button.get("callback_data") or first_button.get("data")
    message_id = bot_reply.get("message_id")
    
    info_print(f"\n--- Processing First Button ---")
    info_print(f"Button text: {button_text}")
    
    # Determine if this is a request or download button
    has_request = "request" in button_text.lower()
    
    if has_request:
        await handle_request_button(button_text, callback_data, message_id, proxy_to_use)
    else:
        await handle_download_button(button_text, callback_data, message_id, proxy_to_use)
    
    info_print(f"\n--- Completed processing all {len(callback_buttons)} buttons ---")

async def get_latest_messages_from_bot(api_id, api_hash, bot_username, session_file='telegram_session', limit=10, proxy=None):
    """
    Get the latest messages from a bot
    
    Args:
        api_id: Your Telegram API ID
        api_hash: Your Telegram API hash
        bot_username: Bot's username
        session_file: Name of the session file
        limit: Maximum number of messages to retrieve (default: 10)
        proxy: Proxy configuration dict or file path
        
    Returns:
        Dictionary with success status and messages list
    """
    debug_print(f"Getting latest {limit} messages from bot: {bot_username}")
    
    # Load proxy configuration
    proxy_config = load_proxy_config(proxy)
    if proxy and proxy_config is None:
        return {"error": "Error loading proxy configuration"}
    
    # Create client
    client = create_telegram_client(session_file, api_id, api_hash, proxy_config)
    
    try:
        # Check if session file exists
        session_path = f"{session_file}.session"
        if not os.path.exists(session_path):
            error_print(f"Session file not found: {session_path}")
            return {"error": "Session file not found. Run script interactively first to create session."}
        
        debug_print("Starting client to get latest messages...")
        if proxy_config:
            info_print(f"Connecting through proxy: {proxy_config['type']}://{proxy_config['addr']}:{proxy_config['port']}")
        
        await client.start()
        
        # Verify we're connected
        if not await client.is_user_authorized():
            error_print("Session expired or not authorized")
            return {"error": "Session expired. Please delete the session file and run interactively to re-authenticate."}
        
        # Get the bot entity
        debug_print(f"Getting bot entity for: {bot_username}")
        bot_entity = await client.get_entity(bot_username)
        
        # Fetch messages
        debug_print(f"Fetching latest {limit} messages from bot...")
        messages = []
        
        async for message in client.iter_messages(bot_entity, limit=limit):
            # Extract button information
            buttons = extract_button_info(message.reply_markup)
            
            # Check if message has media
            has_media = message.media is not None
            media_type = None
            if has_media:
                if hasattr(message.media, 'document'):
                    media_type = "document"
                elif hasattr(message.media, 'photo'):
                    media_type = "photo"
                elif hasattr(message.media, 'video'):
                    media_type = "video"
                else:
                    media_type = "other"
            
            message_data = {
                "message_id": message.id,
                "date": message.date.timestamp(),
                "date_formatted": message.date.strftime("%Y-%m-%d %H:%M:%S"),
                "text": message.text,
                "buttons": buttons,
                "has_media": has_media,
                "media_type": media_type,
                "is_reply": message.reply_to is not None,
                "views": getattr(message, 'views', None),
                "forwards": getattr(message, 'forwards', None)
            }
            
            messages.append(message_data)
            debug_print(f"Retrieved message {message.id}: {message.text[:50]}...")
        
        info_print(f"Successfully retrieved {len(messages)} messages from {bot_username}")
        
        return {
            "ok": True,
            "bot_username": bot_username,
            "messages_count": len(messages),
            "messages": messages
        }
        
    except Exception as e:
        error_print(f"Error getting latest messages: {str(e)}")
        debug_print(f"Exception details: {type(e).__name__}: {str(e)}")
        return {"error": f"Error getting latest messages: {str(e)}"}
    finally:
        debug_print("Disconnecting client...")
        await client.disconnect()

async def get_user_profile(api_id, api_hash, phone_number, bot_username, session_file='telegram_session', proxy=None):
    """
    Get user profile information from Nexus bot by sending /profile command
    
    Args:
        api_id: Your Telegram API ID
        api_hash: Your Telegram API hash
        phone_number: Your phone number (not used, kept for compatibility)
        bot_username: Bot's username
        session_file: Name of the session file
        proxy: Proxy configuration dict or file path
        
    Returns:
        Dictionary with user profile information or error
    """
    info_print("Getting user profile information from Nexus bot...")
    debug_print("Sending /profile command to bot")
    
    # Use the existing send_message_to_bot function to send /profile
    profile_result = await send_message_to_bot(
        api_id, api_hash, phone_number, bot_username, 
        "/profile", session_file, proxy
    )
    
    if not profile_result.get("ok"):
        error_print(f"Failed to get profile: {profile_result.get('error', 'Unknown error')}")
        return profile_result
    
    bot_reply = profile_result.get("bot_reply")
    if not bot_reply:
        error_print("No reply received from bot for /profile command")
        return {"error": "No reply received from bot for /profile command"}
    
    profile_text = bot_reply.get("text", "")
    debug_print(f"Profile response text: {profile_text[:200]}...")
    
    # Parse profile information from the bot response
    profile_info = {
        "raw_response": profile_text,
        "user_level": None,
        "level_emoji": None,
        "level_name": None,
        "n_points": None,
        "uploaded_count": None,
        "leaderboard_position": None,
        "orcid_url": None
    }
    
    # Extract information using regex patterns for the specific Nexus format
    
    # Extract user level with emoji and name
    level_pattern = r"User level:\s*([^\s]+)\s+(.+?)\s+with\s+(\d+)\s+n-points"
    level_match = re.search(level_pattern, profile_text)
    if level_match:
        profile_info["level_emoji"] = level_match.group(1).strip()
        profile_info["level_name"] = level_match.group(2).strip()
        profile_info["n_points"] = int(level_match.group(3))
        profile_info["user_level"] = f"{profile_info['level_emoji']} {profile_info['level_name']}"
        debug_print(f"Extracted user level: {profile_info['user_level']} with {profile_info['n_points']} n-points")
    
    # Extract uploaded count
    uploaded_pattern = r"uploaded\s+(\d+)\s+books and papers"
    uploaded_match = re.search(uploaded_pattern, profile_text)
    if uploaded_match:
        profile_info["uploaded_count"] = int(uploaded_match.group(1))
        debug_print(f"Extracted uploaded count: {profile_info['uploaded_count']}")
    
    # Extract leaderboard position
    leaderboard_pattern = r"takes\s+(\d+)(?:st|nd|rd|th)\s+leaderboard position"
    leaderboard_match = re.search(leaderboard_pattern, profile_text)
    if leaderboard_match:
        profile_info["leaderboard_position"] = int(leaderboard_match.group(1))
        debug_print(f"Extracted leaderboard position: {profile_info['leaderboard_position']}")
    
    # Extract OrcID URL
    orcid_pattern = r"OrcID:\s*Link your OrcID\s*\(([^)]+)\)"
    orcid_match = re.search(orcid_pattern, profile_text)
    if orcid_match:
        profile_info["orcid_url"] = orcid_match.group(1).strip()
        debug_print(f"Extracted OrcID URL: {profile_info['orcid_url'][:50]}...")
    
    info_print("Successfully retrieved and parsed user profile information")
    debug_print(f"Profile info extracted: {profile_info}")
    
    result = {
        "ok": True,
        "profile": profile_info,
        "bot_reply": bot_reply,
        "sent_message": profile_result.get("sent_message")
    }
    
    return result

def format_profile_result(profile_result):
    """Format the profile result in a human-readable way"""
    output = []
    output.append("\n" + "="*50)
    output.append("NEXUS USER PROFILE")
    output.append("="*50)
    
    if "error" in profile_result:
        output.append(f"❌ ERROR: {profile_result['error']}")
        error_print(profile_result['error'])
    elif profile_result.get("ok"):
        output.append("✅ SUCCESS: Profile information retrieved!")
        output.append("")
        
        profile = profile_result.get("profile", {})
        raw_response = profile.get("raw_response", "")
        
        if raw_response:
            # Extract and format information from raw response
            lines = raw_response.split('\n')
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                # Format user level information
                if "User level:" in line:
                    # Extract level info with regex
                    level_match = re.search(r"User level:\s*([^\s]+)\s+(.+?)\s+with\s+(\d+)\s+n-points", line)
                    if level_match:
                        emoji = level_match.group(1)
                        level_name = level_match.group(2)
                        n_points = level_match.group(3)
                        output.append(f"🏆 User Level: {emoji} {level_name}")
                        output.append(f"⭐ N-Points: {n_points}")
                    else:
                        output.append(f"🏆 {line}")
                
                # Format uploaded information
                elif "uploaded" in line.lower() and ("books" in line.lower() or "papers" in line.lower()):
                    uploaded_match = re.search(r"uploaded\s+(\d+)\s+books and papers", line)
                    if uploaded_match:
                        count = uploaded_match.group(1)
                        output.append(f"📚 Uploaded: {count} books and papers")
                    else:
                        output.append(f"📚 {line}")
                
                # Format leaderboard information
                elif "leaderboard" in line.lower():
                    leaderboard_match = re.search(r"takes\s+(\d+)(?:st|nd|rd|th)\s+leaderboard position", line)
                    if leaderboard_match:
                        position = int(leaderboard_match.group(1))
                        # Add ordinal suffix
                        if 10 <= position % 100 <= 20:
                            suffix = "th"
                        else:
                            suffix = {1: "st", 2: "nd", 3: "rd"}.get(position % 10, "th")
                        output.append(f"🏅 Leaderboard Position: {position}{suffix}")
                    else:
                        output.append(f"🏅 {line}")
                
                # Format OrcID information
                elif "orcid" in line.lower():
                    orcid_match = re.search(r"OrcID:\s*(.+)", line, re.IGNORECASE)
                    if orcid_match:
                        orcid_info = orcid_match.group(1).strip()
                        output.append(f"🔗 OrcID: {orcid_info}")
                    else:
                        output.append(f"🔗 {line}")
                
                # Format membership information
                elif "member" in line.lower():
                    output.append(f"👤 {line}")
                
                # Format any other important information
                elif any(keyword in line.lower() for keyword in ["points", "score", "rating", "rank", "status"]):
                    output.append(f"📊 {line}")
                
                # Format general information
                else:
                    output.append(f"ℹ️  {line}")
        
        else:
            output.append("❌ No profile information available in response")
    
    else:
        output.append("❌ FAILED: Could not retrieve profile information")
        error_print("Profile retrieval failed")
    
    output.append("="*50)
    
    # Print to console and log
    result_text = "\n".join(output)
    # print(result_text)
    if logger:
        logger.info("Formatting profile result for display")
        logger.info(result_text)

async def main():
    global API_ID, API_HASH, PHONE, BOT_USERNAME
    
    # Parse command line arguments using argparse
    parser = argparse.ArgumentParser(description='Send messages to Telegram bot')
    parser.add_argument('--create-session', action='store_true',
                       help='Create a new session file interactively')
    parser.add_argument('--credentials', type=str,
                       help='Path to credentials JSON file')
    parser.add_argument('--search', type=str,
                       default="",
                       help='Search query to send to the bot')
    parser.add_argument('--bot', type=str,
                       help='Bot username to interact with (overrides default)')
    parser.add_argument('--verbose', action='store_true',
                       help='Enable verbose output for debugging')
    parser.add_argument('--log', type=str, nargs='?', const=DEFAULT_LOG_FILE,
                       help=f'Save output to log file (default: {DEFAULT_LOG_FILE})')
    parser.add_argument('--proxy-config-file', type=str, nargs='?', const=DEFAULT_PROXY_FILE,
                       help=f'Path to proxy configuration JSON file (default: {DEFAULT_PROXY_FILE})')
    parser.add_argument('--no-proxy', action='store_true',
                       help='Disable proxy usage and connect directly')
    parser.add_argument('--user-info', action='store_true',
                       help='Get and display user profile information from Nexus bot')
    
    args = parser.parse_args()
    
    # Setup logging
    setup_logging(args.log, args.verbose)
    
    if args.verbose:
        info_print("Verbose mode enabled")
    if args.log:
        info_print(f"Logging enabled to: {args.log}")
    
    debug_print(f"Platform: {platform.system()}")
    debug_print(f"Session file: {SESSION_FILE}")
    debug_print(f"Default log file: {DEFAULT_LOG_FILE}")
    
    # Load credentials if specified, otherwise try default location
    if args.credentials:
        if not await load_credentials_from_file(args.credentials):
            return
    else:
        # Try to load from default location
        if os.path.exists(CREDENTIALS_FILE):
            info_print(f"No credentials file specified, trying default location: {CREDENTIALS_FILE}")
            if not await load_credentials_from_file(CREDENTIALS_FILE):
                debug_print("Failed to load credentials from default location")
        else:
            debug_print(f"No credentials file found at default location: {CREDENTIALS_FILE}")

    # Update bot username if specified
    if args.bot:
        BOT_USERNAME = args.bot
        info_print(f"Using specified bot username: {BOT_USERNAME}")
        debug_print(f"Bot username updated from command line argument")
    else:
        info_print(f"Using default bot username: {BOT_USERNAME}")

    # Handle create-session command
    if args.create_session:
        info_print("Creating new session...")
        await create_session(API_ID, API_HASH, PHONE, SESSION_FILE)
        return
    
    # Determine proxy usage
    proxy_to_use = None
    if args.no_proxy:
        info_print("Proxy disabled by --no-proxy flag")
        proxy_to_use = None
    else:
        # Always use proxy by default
        proxy_file = args.proxy_config_file if args.proxy_config_file is not None else DEFAULT_PROXY_FILE
        proxy_to_use = await setup_proxy_configuration(proxy_file)
        if proxy_to_use is False:  # Explicitly check for False (error case)
            return
    
    # Handle user-info command
    if args.user_info:
        info_print("Getting user profile information...")
        
        debug_print("Starting user profile retrieval process...")
        profile_result = await get_user_profile(API_ID, API_HASH, PHONE, BOT_USERNAME, SESSION_FILE, proxy_to_use)
        debug_print("User profile retrieval process completed")
        
        format_profile_result(profile_result)
        return
    
    # Use the search query from arguments
    message_to_send = args.search
    info_print(f"Using search query: {message_to_send}")
    debug_print(f"Search query length: {len(message_to_send)} characters")

    debug_print("Starting message sending process...")
    if proxy_to_use:
        info_print(f"Connecting via proxy: {proxy_to_use}")
    else:
        info_print("Connecting directly (no proxy)")
    
    send_result = await send_message_to_bot(API_ID, API_HASH, PHONE, BOT_USERNAME, message_to_send, SESSION_FILE, proxy_to_use)
    debug_print("Message sending process completed")
    
    format_result(send_result)
    
    # Handle button clicks after search results
    if send_result.get("ok") and send_result.get("bot_reply"):
        await process_callback_buttons(send_result["bot_reply"], proxy_to_use)
    else:
        debug_print("No valid bot reply to process for button clicks")

if __name__ == "__main__":
    asyncio.run(main())
