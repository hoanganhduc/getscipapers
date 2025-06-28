# Python script to interact with Nexus bot on Telegram

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
import readline
import signal
from concurrent.futures import ThreadPoolExecutor, as_completed
import shutil
from datetime import timedelta
import datetime as dt  # Add this import at the top if not already present
import itertools
import getpass
from . import getpapers


if platform.system() == 'Windows':
    import msvcrt

# You need to get API credentials from https://my.telegram.org
TG_API_ID = ""  # Replace with your actual API ID
TG_API_HASH = ""  # Replace with your actual API hash
PHONE = ""  # Replace with your phone number
BOT_USERNAME = "SciNexBot"  # Replace with Nexus bot username
SESSION_FILE = ""  # Path to save the session file

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
    """Get the appropriate file paths based on the operating system, using a single config dir for all except downloads."""
    system = platform.system()
    home = os.path.expanduser("~")

    if system == "Windows":
        # Windows: Use AppData\Local\getscipapers\nexus as config dir
        config_dir = os.path.join(os.environ.get("LOCALAPPDATA", home), "getscipapers", "nexus")
    elif system == "Darwin":  # macOS
        # macOS: Use ~/Library/Application Support/getscipapers/nexus as config dir
        config_dir = os.path.join(home, "Library", "Application Support", "getscipapers", "nexus")
    else:  # Linux and other Unix-like systems
        # Linux: Use ~/.config/getscipapers/nexus as config dir
        config_dir = os.path.join(home, ".config", "getscipapers", "nexus")

    # Download dir is always ~/Downloads/getscipapers/nexus
    download_dir = os.path.join(home, "Downloads", "getscipapers", "nexus")

    # Log file in config dir/logs
    log_dir = os.path.join(config_dir, "logs")
    os.makedirs(config_dir, exist_ok=True)
    os.makedirs(log_dir, exist_ok=True)
    os.makedirs(download_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d")
    default_log_file = os.path.join(log_dir, f"telegram_bot_{timestamp}.log")

    return {
        "session": os.path.join(config_dir, "telegram_session.session"),
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
    """Retrieve free proxy list from free-proxy-list.net, test them for speed in parallel, and save to proxy list file for further checking later"""
    info_print("Retrieving free proxies from free-proxy-list.net...")
    
    # Countries that block or restrict Telegram access
    BLOCKED_COUNTRIES = {
        'VN': 'Vietnam',
        'CN': 'China', 
        'IR': 'Iran',
        'RU': 'Russia',
        'BY': 'Belarus',
        'TH': 'Thailand',
        'ID': 'Indonesia',
        'BD': 'Bangladesh',
        'PK': 'Pakistan',
        'IN': 'India',  # Some regions have restrictions
        'KZ': 'Kazakhstan',
        'UZ': 'Uzbekistan',
        'TJ': 'Tajikistan',
        'TM': 'Turkmenistan',
        'KG': 'Kyrgyzstan',
        'MY': 'Malaysia',  # Some restrictions
        'SG': 'Singapore',  # Some corporate restrictions
        'AE': 'UAE',  # Some restrictions
        'SA': 'Saudi Arabia',  # Some restrictions
        'EG': 'Egypt',  # Periodic blocks
        'TR': 'Turkey',  # Periodic blocks
        'UA': 'Ukraine'  # Due to ongoing conflict, some restrictions
    }
    
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
                        
                        # Skip proxies from countries that block Telegram
                        if country_code.upper() in BLOCKED_COUNTRIES:
                            blocked_country_name = BLOCKED_COUNTRIES[country_code.upper()]
                            debug_print(f"Skipping proxy from {blocked_country_name} (blocks Telegram): {ip}:{port}")
                            continue
                        
                        # Additional check by country name for cases where country code might be missing/wrong
                        country_upper = country.upper()
                        skip_proxy = False
                        for code, name in BLOCKED_COUNTRIES.items():
                            if name.upper() in country_upper or country_upper in name.upper():
                                debug_print(f"Skipping proxy from {name} (blocks Telegram): {ip}:{port}")
                                skip_proxy = True
                                break
                        
                        if skip_proxy:
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
                                        # For raw list, we can't filter by country since no country info is available
                                        # But we'll still add them as they might be from allowed countries
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
        
        blocked_countries_list = ", ".join(BLOCKED_COUNTRIES.values())
        info_print(f"Found {len(proxies)} proxies (excluding countries that block Telegram: {blocked_countries_list})")
        
        # Test proxy speeds in parallel
        info_print("Testing proxy speeds for internet connectivity in parallel...")
        
        # Test up to 50 random proxies to find working ones
        test_proxies = random.sample(proxies, min(50, len(proxies)))
        info_print(f"Testing {len(test_proxies)} proxies in parallel...")
        
        # Use ThreadPoolExecutor for parallel testing
        
        tested_proxies = []
        max_workers = min(20, len(test_proxies))  # Limit concurrent threads
        
        def test_single_proxy(proxy_info, index):
            """Test a single proxy and return result"""
            try:
                debug_print(f"Testing proxy {index}: {proxy_info['ip']}:{proxy_info['port']} ({proxy_info['country']})")
                speed = test_proxy_speed(proxy_info['ip'], proxy_info['port'])
                
                if speed > 0:
                    proxy_info['speed_ms'] = speed
                    info_print(f"✓ Proxy {index} works: {speed:.0f}ms ({proxy_info['country']})")
                    return proxy_info
                else:
                    debug_print(f"✗ Proxy {index} failed connectivity test")
                    return None
            except Exception as e:
                debug_print(f"✗ Proxy {index} error: {str(e)}")
                return None
        
        # Execute parallel testing
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all tasks
            future_to_proxy = {
                executor.submit(test_single_proxy, proxy_info, i + 1): proxy_info 
                for i, proxy_info in enumerate(test_proxies)
            }
            
            # Collect results as they complete
            completed_count = 0
            for future in as_completed(future_to_proxy):
                completed_count += 1
                result = future.result()
                
                if result:
                    tested_proxies.append(result)
                    debug_print(f"Added working proxy: {result['ip']}:{result['port']}")
                
                # Show progress
                if completed_count % 5 == 0 or completed_count == len(test_proxies):
                    info_print(f"Progress: {completed_count}/{len(test_proxies)} tested, {len(tested_proxies)} working")
                
                # Stop if we have found enough working proxies
                if len(tested_proxies) >= 15:  # Get a few extra in case some fail later
                    info_print("Found enough working proxies, cancelling remaining tests...")
                    # Cancel remaining futures
                    for remaining_future in future_to_proxy:
                        if not remaining_future.done():
                            remaining_future.cancel()
                    break
        
        if not tested_proxies:
            error_print("No working proxies found")
            return False
        
        # Sort by speed (fastest first) and take top 10
        tested_proxies.sort(key=lambda x: x['speed_ms'])
        top_10_proxies = tested_proxies[:10]
        
        info_print(f"Selected top {len(top_10_proxies)} fastest working proxies:")
        for i, proxy in enumerate(top_10_proxies, 1):
            info_print(f"  {i}. {proxy['ip']}:{proxy['port']} - {proxy['speed_ms']:.0f}ms ({proxy['country']})")
        
        # Save only the proxy list for later checking - DO NOT save to default proxy file
        proxy_list_file = DEFAULT_PROXY_FILE.replace('.json', '_list.json')
        debug_print(f"Saving proxy list to: {proxy_list_file}")
        
        try:
            with open(proxy_list_file, 'w') as f:
                json.dump({
                    'top_10_fastest': top_10_proxies,
                    'all_tested_proxies': tested_proxies,
                    'all_proxies': proxies,
                    'blocked_countries': BLOCKED_COUNTRIES,
                    'timestamp': datetime.now().isoformat(),
                    'note': 'Proxy list for further checking - excludes countries that block Telegram - no default proxy auto-selected',
                    'parallel_testing': True
                }, f, indent=2)
            
            info_print(f"Proxy list saved to: {proxy_list_file}")
            info_print(f"Found {len(top_10_proxies)} working proxies available for later use")
            debug_print("No default proxy configuration created - proxies saved for manual selection")
            return True
            
        except Exception as e:
            error_print(f"Error saving proxy list: {e}")
            return False
            
    except requests.RequestException as e:
        error_print(f"Error retrieving proxy list: {e}")
        debug_print(f"Request error details: {type(e).__name__}: {str(e)}")
        return False
    except Exception as e:
        error_print(f"Unexpected error while getting proxies: {e}")
        debug_print(f"Unexpected error details: {type(e).__name__}: {str(e)}")
        return False

def test_proxy_speed(ip, port, timeout=10):
    """
    Test proxy speed by making a simple HTTP request through the proxy
    
    Args:
        ip: Proxy IP address
        port: Proxy port
        timeout: Request timeout in seconds
        
    Returns:
        Response time in milliseconds (0 if failed)
    """
    try:
        proxy_url = f"http://{ip}:{port}"
        proxies = {
            'http': proxy_url,
            'https': proxy_url
        }
        
        # Test URL - use a fast, reliable endpoint
        test_urls = [
            'http://httpbin.org/ip',
            'http://icanhazip.com',
            'http://ipinfo.io/ip'
        ]
        
        for test_url in test_urls:
            try:
                debug_print(f"Testing proxy {ip}:{port} with {test_url}")
                start_time = time.time()
                
                response = requests.get(
                    test_url,
                    proxies=proxies,
                    timeout=timeout,
                    headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
                )
                
                end_time = time.time()
                
                if response.status_code == 200:
                    response_time_ms = (end_time - start_time) * 1000
                    debug_print(f"Proxy {ip}:{port} responded in {response_time_ms:.0f}ms")
                    return response_time_ms
                else:
                    debug_print(f"Proxy {ip}:{port} returned status {response.status_code}")
                    
            except requests.RequestException as e:
                debug_print(f"Proxy {ip}:{port} failed with {test_url}: {str(e)}")
                continue
        
        # If all test URLs failed
        debug_print(f"Proxy {ip}:{port} failed all connectivity tests")
        return 0
        
    except Exception as e:
        debug_print(f"Error testing proxy {ip}:{port}: {str(e)}")
        return 0

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
    """Test multiple proxies in parallel and select the first working one for Telegram"""
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
        
        # Use only the top 10 fastest proxies from the full list
        top_10_fastest = proxy_data.get('top_10_fastest', [])
        test_proxy_list = top_10_fastest if top_10_fastest else all_proxies[:10]
        
        info_print(f"Testing top {len(test_proxy_list)} fastest proxies for Telegram connectivity in parallel...")
        info_print("Will use the first working proxy found...")
        
        # Create tasks for parallel testing
        async def test_single_proxy(proxy_info, index):
            """Test a single proxy and return result with index"""
            try:
                debug_print(f"Testing proxy {index}: {proxy_info['ip']}:{proxy_info['port']} ({proxy_info['country']}) - {proxy_info.get('speed_ms', 'N/A')}ms")
                
                proxy_config = {
                    'type': 'http',
                    'addr': proxy_info['ip'],
                    'port': proxy_info['port'],
                    'username': None,
                    'password': None
                }
                
                test_result = await test_proxy_telegram_connection(proxy_config, timeout=15)
                
                if test_result['success']:
                    info_print(f"✓ Proxy {index} WORKS: {proxy_info['ip']}:{proxy_info['port']}")
                    return proxy_config, index, proxy_info
                else:
                    debug_print(f"✗ Proxy {index} failed: {test_result.get('error', 'Unknown error')}")
                    return None, index, proxy_info
                    
            except Exception as e:
                debug_print(f"✗ Proxy {index} error: {str(e)}")
                return None, index, proxy_info
        
        # Create tasks for all proxies
        tasks = [
            test_single_proxy(proxy_info, i + 1) 
            for i, proxy_info in enumerate(test_proxy_list)
        ]
        
        # Convert coroutines to tasks for proper cancellation
        actual_tasks = [asyncio.create_task(coro) for coro in tasks]
        
        # Run tasks in parallel and return when first one succeeds
        try:
            for task in asyncio.as_completed(actual_tasks):
                proxy_config, _, proxy_info = await task
                
                if proxy_config:  # Found a working proxy
                    info_print(f"Selected working proxy: {proxy_info['ip']}:{proxy_info['port']} ({proxy_info['country']})")
                    
                    # Cancel remaining tasks
                    for remaining_task in actual_tasks:
                        if not remaining_task.done():
                            remaining_task.cancel()
                    
                    # Save the working proxy configuration
                    with open(DEFAULT_PROXY_FILE, 'w') as f:
                        json.dump(proxy_config, f, indent=2)
                    
                    info_print(f"Working proxy configuration saved to: {DEFAULT_PROXY_FILE}")
                    return proxy_config
            
            # If we reach here, no working proxy was found
            error_print("No working proxies found for Telegram")
            return None
            
        except Exception as e:
            error_print(f"Error during parallel proxy testing: {e}")
            debug_print(f"Parallel testing error: {type(e).__name__}: {str(e)}")
            return None
            
    except Exception as e:
        error_print(f"Error testing proxies: {e}")
        debug_print(f"Proxy testing error: {type(e).__name__}: {str(e)}")
        return None

async def test_telegram_connection(api_id, api_hash, phone_number, session_file=SESSION_FILE, proxy=None):
    """
    Test connection to Telegram servers with comprehensive diagnostics
    
    Args:
        api_id: Your Telegram API ID
        api_hash: Your Telegram API hash
        phone_number: Your phone number (not used, kept for compatibility)
        session_file: Name of the session file
        proxy: Proxy configuration dict or file path
    """
    print("\n" + "="*70)
    print("TELEGRAM CONNECTION TEST")
    print("="*70)
    
    # Test 1: Proxy connectivity (if configured)
    if proxy:
        print("🔧 Step 1: Testing proxy configuration...")
        
        # Load proxy configuration
        proxy_config = load_proxy_config(proxy)
        if proxy_config is None:
            error_print("✗ Failed to load proxy configuration")
            return
        
        info_print(f"Using proxy: {proxy_config['type']}://{proxy_config['addr']}:{proxy_config['port']}")
        
        # Test proxy connectivity to Telegram
        proxy_test_result = await test_proxy_telegram_connection(proxy_config, timeout=15)
        
        if proxy_test_result['success']:
            print("✅ Proxy connectivity: PASSED")
            
            # Show detailed proxy test results if verbose
            if verbose_mode:
                print("   📊 Proxy Test Details:")
                tcp_results = proxy_test_result.get('tcp_connect', {})
                for endpoint, result in tcp_results.items():
                    status = "✓" if result.get('success') else "✗"
                    print(f"   {status} TCP {endpoint}: {result.get('error', 'OK')}")
                
                web_results = proxy_test_result.get('web_connectivity', {})
                for url, result in web_results.items():
                    status = "✓" if result.get('success') else "✗"
                    time_info = f" ({result.get('response_time_ms', 0)}ms)" if result.get('response_time_ms') else ""
                    print(f"   {status} WEB {url}{time_info}")
        else:
            print("❌ Proxy connectivity: FAILED")
            error_print(f"Proxy test error: {proxy_test_result.get('error', 'Unknown error')}")
            print("   Try running with --no-proxy to test direct connection")
    else:
        print("🔧 Step 1: No proxy configured - testing direct connection")
    
    print()
    
    # Test 2: Session file validation
    print("🔧 Step 2: Checking session file...")
    
    if os.path.exists(session_file):
        file_size = os.path.getsize(session_file)
        file_age = datetime.now() - datetime.fromtimestamp(os.path.getmtime(session_file))
        
        print(f"✅ Session file exists: {session_file}")
        print(f"   📏 File size: {file_size} bytes")
        print(f"   📅 Last modified: {file_age.days} days ago")
        
        if file_size < 100:
            print("   ⚠️  Warning: Session file seems unusually small")
        if file_age.days > 30:
            print("   ⚠️  Warning: Session file is quite old, may need re-authentication")
    else:
        print("❌ Session file not found")
        print(f"   Expected location: {session_file}")
        print("   Run with --create-session to create a new session")
        return
    
    print()
    
    # Test 3: Telegram client connection
    print("🔧 Step 3: Testing Telegram client connection...")
    
    # Load proxy configuration
    proxy_config = load_proxy_config(proxy) if proxy else None
    
    # Create client
    client = create_telegram_client(api_id, api_hash, session_file, proxy_config)
    
    try:
        # Test connection
        start_time = datetime.now()
        
        debug_print("Starting Telegram client for connection test...")
        await client.start()
        
        connect_time = (datetime.now() - start_time).total_seconds()
        print(f"✅ Client connection: SUCCESSFUL ({connect_time:.2f}s)")
        
        # Test authorization
        if await client.is_user_authorized():
            print("✅ User authorization: VALID")
            
            # Get user info
            try:
                me = await client.get_me()
                print(f"   👤 User: {me.first_name} {me.last_name or ''} (@{me.username or 'no_username'})")
                print(f"   📱 Phone: {me.phone or 'not_available'}")
                print(f"   🆔 User ID: {me.id}")
            except Exception as e:
                debug_print(f"Could not get user info: {e}")
                print("   ℹ️  User info: Could not retrieve")
        else:
            print("❌ User authorization: EXPIRED")
            print("   Run with --create-session to re-authenticate")
            return
        
        print()
        
        # Test 4: Bot connectivity
        print("🔧 Step 4: Testing bot connectivity...")
        
        try:
            bot_entity = await client.get_entity(BOT_USERNAME)
            print(f"✅ Bot resolution: Found @{BOT_USERNAME}")
            print(f"   🤖 Bot ID: {bot_entity.id}")
            print(f"   📝 Bot Name: {getattr(bot_entity, 'first_name', 'N/A')}")
            
            # Test sending a simple message
            print("   📤 Testing message send...")
            test_message = "/start"
            
            start_time = datetime.now()
            result = await client.send_message(BOT_USERNAME, test_message)
            send_time = (datetime.now() - start_time).total_seconds()
            
            print(f"✅ Message send: SUCCESSFUL ({send_time:.2f}s)")
            print(f"   🆔 Message ID: {result.id}")
            
            # Wait briefly for potential reply
            print("   ⏳ Waiting for bot response...")
            await asyncio.sleep(3)
            
            # Check for recent messages
            message_count = 0
            async for message in client.iter_messages(bot_entity, limit=3):
                if message.date >= result.date:
                    message_count += 1
                    if message_count == 1:
                        print(f"✅ Bot response: RECEIVED")
                        response_text = message.text[:100] + "..." if len(message.text) > 100 else message.text
                        print(f"   💬 Response: {response_text}")
                        
                        if message.reply_markup and message.reply_markup.rows:
                            button_count = sum(len(row.buttons) for row in message.reply_markup.rows)
                            print(f"   🔘 Buttons: {button_count} available")
                    break
            
            if message_count == 0:
                print("⚠️  Bot response: No immediate response (may be normal)")
            
        except Exception as e:
            print(f"❌ Bot connectivity: FAILED")
            error_print(f"Bot test error: {str(e)}")
            debug_print(f"Bot test exception: {type(e).__name__}: {str(e)}")
        
        print()
        
        # Test 5: Network performance
        print("🔧 Step 5: Network performance test...")
        
        try:
            # Test multiple small operations
            start_time = datetime.now()
            operations = 0
            
            # Get dialogs (conversations)
            async for dialog in client.iter_dialogs(limit=5):
                operations += 1
            
            performance_time = (datetime.now() - start_time).total_seconds()
            
            if performance_time < 2.0:
                print(f"✅ Network performance: EXCELLENT ({performance_time:.2f}s for {operations} ops)")
            elif performance_time < 5.0:
                print(f"✅ Network performance: GOOD ({performance_time:.2f}s for {operations} ops)")
            elif performance_time < 10.0:
                print(f"⚠️  Network performance: SLOW ({performance_time:.2f}s for {operations} ops)")
            else:
                print(f"❌ Network performance: VERY SLOW ({performance_time:.2f}s for {operations} ops)")
                
        except Exception as e:
            print(f"⚠️  Network performance: Could not test ({str(e)})")
        
    except Exception as e:
        print("❌ Client connection: FAILED")
        error_print(f"Connection test error: {str(e)}")
        debug_print(f"Connection test exception: {type(e).__name__}: {str(e)}")
        
        # Provide troubleshooting suggestions
        print("\n🔧 Troubleshooting suggestions:")
        if "proxy" in str(e).lower():
            print("   • Check proxy configuration and connectivity")
            print("   • Try with --no-proxy for direct connection")
        if "auth" in str(e).lower() or "login" in str(e).lower():
            print("   • Run with --create-session to re-authenticate")
        if "network" in str(e).lower() or "timeout" in str(e).lower():
            print("   • Check your internet connection")
            print("   • Try using a proxy with --proxy-config-file")
        
    finally:
        debug_print("Disconnecting client after connection test...")
        await client.disconnect()
    
    print()
    print("="*70)
    print("CONNECTION TEST COMPLETED")
    print("="*70)
    
async def decide_proxy_usage(api_id, api_hash, phone_number, session_file=SESSION_FILE, proxy_file=DEFAULT_PROXY_FILE):
    """
    Decide whether to use a proxy for Telegram connection.
    If connection works without proxy, return None (no proxy).
    If not, try with proxy_file and return proxy_file if it works.
    Returns:
        None if no proxy needed,
        proxy_file if proxy is needed,
        False if neither works.
    """
    info_print("Testing Telegram connection without proxy...")
    result = await test_credentials(api_id, api_hash, phone_number, session_file, proxy=None)
    if result.get("ok"):
        info_print("Direct connection to Telegram works. Proxy is not needed.")
        return None
    else:
        info_print("Direct connection failed. Trying with proxy...")
        if not os.path.exists(proxy_file):
            info_print(f"Proxy file not found: {proxy_file}")
            working_proxy = await test_and_select_working_proxy()
            if not working_proxy:
                error_print("Could not find a working proxy for Telegram")
                return False
        result_proxy = await test_credentials(api_id, api_hash, phone_number, session_file, proxy=proxy_file)
        if result_proxy.get("ok"):
            info_print("Connection via proxy works. Proxy will be used.")
            return proxy_file
        else:
            error_print("Connection failed with and without proxy.")
            return False

def create_telegram_client(api_id, api_hash, session_file=SESSION_FILE, proxy=None):
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
        return await wait_for_reply(get_bot_reply, timeout=30)
    
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

async def click_callback_button(api_id, api_hash, phone_number, bot_username, message_id, button_data, session_file=SESSION_FILE, proxy=None):
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
    client = create_telegram_client(api_id, api_hash, session_file, proxy_config)
    bot_reply = None
    
    try:
        if not os.path.exists(session_file):
            error_print(f"Session file not found: {session_file}")
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
                # Ensure both datetimes are timezone-aware for comparison
                now = dt.datetime.now(message.date.tzinfo) if message.date.tzinfo else dt.datetime.now()
                if message.date > now - timedelta(seconds=35):  # Messages from last 35 seconds
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

async def send_message_to_bot(api_id, api_hash, phone_number, bot_username, message, session_file=SESSION_FILE, proxy=None, limit=None):
    """
    Send a message from your user account to a Telegram bot and wait for its reply.

    Args:
        api_id: Your Telegram API ID (get from my.telegram.org)
        api_hash: Your Telegram API hash
        phone_number: Your phone number
        bot_username: Bot's username (e.g., 'your_bot_name')
        message: Message text to send (search query or DOI)
        session_file: Name of the session file to save/load
        proxy: Proxy configuration dict or file path (see create_telegram_client)
        limit: Maximum number of search results to fetch (default: 1 for DOI, 5 for search; can be set by user)

    Returns:
        dict: {
            "ok": True if successful, False or "error" key otherwise,
            "sent_message": {
                "message_id": int,
                "date": float (timestamp),
                "text": str
            },
            "bot_reply": {
                "message_id": int,
                "date": float (timestamp),
                "text": str,  # reply text, possibly concatenated for search
                "buttons": list of dicts with button info (text, type, callback_data/url)
            }
        }
        If an error occurs, returns {"error": "..."}.
    """
    debug_print(f"Initializing TelegramClient with session file: {session_file}")

    # Load proxy configuration
    proxy_config = load_proxy_config(proxy)
    if proxy and proxy_config is None:
        return {"error": f"Error loading proxy configuration"}

    # Create client
    client = create_telegram_client(api_id, api_hash, session_file, proxy_config)

    # Define all result markers
    result_markers = ["🔬 **", "🔖 **", "📚 **"]

    try:
        # Check if session file exists
        debug_print(f"Checking for session file: {session_file}")
        if not os.path.exists(session_file):
            error_print(f"Session file '{session_file}' not found!")
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
        # Set up handler closure for getting and setting bot_reply
        def create_setter():
            bot_reply_value = [None]

            async def new_handler(event):
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

        # Determine if message is a DOI
        is_doi = bool(re.match(r'^10\.\d+/.+', message.strip()))
        # Use user-specified limit if provided, else default logic
        if limit is not None:
            reply_limit = int(limit)
        else:
            reply_limit = 1 if is_doi else 5

        # Check if message is a command (starts with / and is not a DOI)
        is_command = message.strip().startswith("/") and not is_doi

        # Send message to the bot
        debug_print(f"Sending message to bot: '{message}'")
        result = await client.send_message(bot_username, message)
        info_print(f"Message sent successfully. Message ID: {result.id}")

        # Wait for bot reply
        bot_reply = await wait_for_reply(get_bot_reply, timeout=30)
        bot_reply = await handle_search_message(get_bot_reply, set_bot_reply)
        if bot_reply is None:
            bot_reply = await fetch_recent_messages(client, bot_entity, result)

        # If message is a command, just return the reply as is
        if is_command:
            if bot_reply:
                response = {
                    "ok": True,
                    "sent_message": {
                        "message_id": result.id,
                        "date": result.date.timestamp(),
                        "text": result.text
                    },
                    "bot_reply": bot_reply
                }
                debug_print(f"Command response prepared. Bot reply: {bot_reply.get('text', 'No text')[:50]}")
                return response
            else:
                return {"error": "No reply received from bot for command."}

        if is_doi:
            # Handle DOI: just return the first reply
            if bot_reply:
                response = {
                    "ok": True,
                    "sent_message": {
                        "message_id": result.id,
                        "date": result.date.timestamp(),
                        "text": result.text
                    },
                    "bot_reply": bot_reply
                }
                debug_print(f"DOI response prepared. Bot reply: {bot_reply.get('text', 'No text')[:50]}")
                return response
            else:
                return {"error": "No reply received from bot for DOI."}
        else:
            # Handle search (not DOI)
            bot_replies = []
            if bot_reply:
                bot_replies.append(bot_reply)
            else:
                return {"error": "No reply received from bot for search."}

            # --- Extract total number of results from Nexus reply ---
            total_results = None
            if bot_reply and isinstance(bot_reply, dict):
                text = bot_reply.get("text", "")
                match = re.search(r"__([\d,]+)\s+results__", text)
                if match:
                    total_results_str = match.group(1).replace(",", "")
                    try:
                        total_results = int(total_results_str)
                        info_print(f"Total results found in Nexus: {total_results:,}")
                    except Exception:
                        info_print(f"Total results found in Nexus: {match.group(1)}")
                else:
                    debug_print("Could not extract total results from bot reply text.")

            # Try to determine the number of current results from the text
            n_results = sum(bot_reply.get("text", "").count(marker) for marker in result_markers)
            debug_print(f"Detected {n_results} search results in bot reply text using markers {result_markers}")

            # If the number of results already exceeds the limit, stop here
            if n_results >= reply_limit:
                # Split by all markers, keep only the first <limit> results, then join back
                text = bot_reply.get("text", "")
                marker_positions = []
                for marker in result_markers:
                    idx = 0
                    while True:
                        idx = text.find(marker, idx)
                        if idx == -1:
                            break
                        marker_positions.append((idx, marker))
                        idx += len(marker)
                marker_positions.sort()
                if len(marker_positions) > reply_limit:
                    cut_idx = marker_positions[reply_limit][0]
                    concatenated_text = text[:cut_idx]
                else:
                    concatenated_text = text
                bot_reply_final = dict(bot_reply)
                bot_reply_final["text"] = concatenated_text
                response = {
                    "ok": True,
                    "sent_message": {
                        "message_id": result.id,
                        "date": result.date.timestamp(),
                        "text": result.text
                    },
                    "bot_reply": bot_reply_final
                }
                debug_print(f"Response prepared early due to enough results. Bot reply count: {len(bot_replies)}")
                return response

            # Try to fetch more results if limit not reached
            seen_search_callbacks = set()
            all_texts = [bot_reply["text"]] if bot_reply and "text" in bot_reply else []

            def count_all_markers(texts):
                return sum(sum(t.count(marker) for marker in result_markers) for t in texts)

            current_count = count_all_markers(all_texts)
            while current_count < reply_limit:
                last_reply = bot_replies[-1] if bot_replies else None
                if not last_reply or not last_reply.get("buttons"):
                    break

                # Find all callback buttons whose text contains ">" and callback_data like "/search_<number>"
                search_buttons = []
                for btn in last_reply["buttons"]:
                    btn_text = btn.get("text", "")
                    cb_data = btn.get("callback_data") or btn.get("data")
                    if cb_data and ">" in btn_text:
                        if isinstance(cb_data, bytes):
                            cb_data_str = cb_data.decode(errors="ignore")
                        else:
                            cb_data_str = str(cb_data)
                        if re.match(r"^/search_\d+$", cb_data_str):
                            search_buttons.append((btn, cb_data_str))

                found = False
                for btn, cb_data_str in search_buttons:
                    if cb_data_str not in seen_search_callbacks:
                        seen_search_callbacks.add(cb_data_str)
                        cb_data = btn.get("callback_data") or btn.get("data")
                        info_print(f"Clicking search button (text contains '>') to fetch more results: {btn.get('text', '')}")
                        try:
                            await client.disconnect()
                            click_result = await click_callback_button(
                                api_id, api_hash, phone_number, bot_username,
                                last_reply["message_id"], cb_data, session_file, proxy
                            )
                            await client.start()
                            debug_print(f"Search button {btn.get('text', '')} clicked successfully. Result: {click_result}")
                            info_print("Fetching new results...")
                            new_reply = await fetch_recent_messages(client, bot_entity, result)
                            debug_print(f"New reply fetched: {new_reply.get('text', 'No text')[:50]}...")
                            if new_reply and new_reply.get("text"):
                                all_texts.append(new_reply["text"])
                                bot_replies.append(new_reply)
                                found = True
                        except Exception as e:
                            error_print(f"Error clicking search button: {str(e)}")
                        break  # Only click one button per loop
                if not found:
                    break

                concatenated_text = "\n".join(all_texts) if all_texts else ""
                current_count = sum(concatenated_text.count(marker) for marker in result_markers)
                debug_print(f"Current total marker count: {current_count}, reply_limit: {reply_limit}")
                if current_count >= reply_limit:
                    break

            # Concatenate all texts for final bot_reply
            concatenated_text = "\n".join(all_texts) if all_texts else ""

            # If the result contains more results than the <limit>, only fetch the first <limit> number of results
            if reply_limit > 0:
                marker_positions = []
                for marker in result_markers:
                    idx = 0
                    while True:
                        idx = concatenated_text.find(marker, idx)
                        if idx == -1:
                            break
                        marker_positions.append((idx, marker))
                        idx += len(marker)
                marker_positions.sort()
                if len(marker_positions) > reply_limit:
                    cut_idx = marker_positions[reply_limit][0]
                    concatenated_text = concatenated_text[:cut_idx]
                    debug_print(f"Trimmed search results to first {reply_limit} entries.")

                # Remove "__<number> results__" from the text
                concatenated_text = re.sub(r"__[\d,]+\s+results__\s*", "", concatenated_text)

                # Remove advertising or footer lines starting with an emoji (not our result markers)
                lines = concatenated_text.splitlines()
                filtered_lines = []
                result_counter = 1
                for line in lines:
                    stripped = line.strip()
                    if any(stripped.startswith(marker[:-3]) for marker in result_markers):
                        filtered_lines.append(f"[{result_counter}] {line}")
                        result_counter += 1
                    elif re.match(r"^[^\w\s]", stripped):
                        continue
                    else:
                        filtered_lines.append(line)
                concatenated_text = "\n".join(filtered_lines)

                # Only prepend this line if the original message is not "/profile"
                concatenated_text = f"The first {reply_limit} results among {total_results} results found:\n\n" + concatenated_text

                bot_reply_final = dict(bot_replies[0])
                bot_reply_final["text"] = concatenated_text

                response = {
                    "ok": True,
                    "sent_message": {
                        "message_id": result.id,
                        "date": result.date.timestamp(),
                        "text": result.text
                    },
                    "bot_reply": bot_reply_final
                }
                debug_print(f"Response prepared successfully. Bot reply count: {len(bot_replies)}")
                info_print(response)
                return response

            # Fallback: just return the first reply if nothing else
            response = {
                "ok": True,
                "sent_message": {
                    "message_id": result.id,
                    "date": result.date.timestamp(),
                    "text": result.text
                },
                "bot_reply": bot_replies[0]
            }
            return response

    finally:
        debug_print("Disconnecting client...")
        await client.disconnect()
        debug_print("Client disconnected")

async def create_session(api_id, api_hash, phone_number, session_file=SESSION_FILE):
    """Create a new session file interactively"""
    debug_print(f"Creating new session with file: {session_file}")
    client = TelegramClient(session_file, api_id, api_hash)
    
    try:
        debug_print("Starting client for session creation...")
        await client.start(phone_number)
        info_print(f"Session created successfully! File saved as '{session_file}'")
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
        user_input = get_input_with_timeout("Do you want to request it? [y/N]: ", timeout=30, default='n')
        
        if user_input in ['y', 'yes']:
            info_print(f"User chose to request the paper - clicking button: {button_text}")
            debug_print(f"Request button click parameters - Message ID: {message_id}, Callback data: {callback_data}")
            
            # Click the callback button
            click_result = await click_callback_button(
            TG_API_ID, TG_API_HASH, PHONE, BOT_USERNAME, 
            message_id, callback_data, SESSION_FILE, proxy
            )
            
            return click_result
        else:
            info_print("User chose not to request the paper")
            return None
    else:
        # Paper is available - clean button text and ask if user wants to download
        print("\n📄 The corresponding paper is available on Nexus.")
        user_input = get_input_with_timeout("Do you want to download it? [y/N]: ", timeout=30, default='n')
        
        if user_input in ['y', 'yes']:
            info_print(f"User chose to download the paper - clicking button: {button_text}")
            debug_print(f"Download button click parameters - Message ID: {message_id}, Callback data: {callback_data}")
            
            # Click the callback button
            click_result = await click_callback_button(
            TG_API_ID, TG_API_HASH, PHONE, BOT_USERNAME, 
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
                if progress >= last_progress + 5:  # Update every 5%
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
    client = create_telegram_client(TG_API_ID, TG_API_HASH, SESSION_FILE, proxy_config)
    
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
def get_input_with_timeout(prompt, timeout=30, default='y', keep_origin=False):
    """Get user input with timeout, return default if timeout occurs"""
    
    # Check if we're prompting for a file path (contains "path" or "file")
    is_path_prompt = any(keyword in prompt.lower() for keyword in ['path', 'file'])
    
    if is_path_prompt:
        try:
            # Enable tab completion for file paths
            readline.set_completer_delims(' \t\n=')
            readline.parse_and_bind("tab: complete")
            
            # Use input() for path prompts to enable readline features
            print(prompt, end='', flush=True)
            
            
            def timeout_handler(signum, frame):
                raise TimeoutError(f"Timeout after {timeout} seconds")
            
            # Set up timeout for Unix-like systems
            if sys.platform != 'win32':
                signal.signal(signal.SIGALRM, timeout_handler)
                signal.alarm(timeout)
            
            try:
                user_input = input().strip()
                if sys.platform != 'win32':
                    signal.alarm(0)  # Cancel timeout
                return user_input if keep_origin else user_input.lower()
            except (TimeoutError, KeyboardInterrupt):
                if sys.platform != 'win32':
                    signal.alarm(0)  # Cancel timeout
                print(f"\nTimeout after {timeout} seconds, using default: {default}")
                return default
                
        except ImportError:
            # Fallback if readline is not available
            debug_print("readline not available, falling back to basic input")
    
    # Original implementation for non-path prompts or when readline is not available
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
                    user_input = ''.join(input_chars).strip()
                    return user_input if keep_origin else user_input.lower()
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
            user_input = sys.stdin.readline().strip()
            return user_input if keep_origin else user_input.lower()
        else:
            print(f"\nTimeout after {timeout} seconds, using default: {default}")
            return default

async def load_credentials_from_file(credentials_path):
    """Load API credentials from JSON file, validate, and prompt user if invalid or missing."""

    global TG_API_ID, TG_API_HASH, PHONE, BOT_USERNAME

    def prompt_for_credentials():
        print("\nPlease enter your Telegram API credentials.")
        tg_api_id = get_input_with_timeout("API ID: ", timeout=30, default="", keep_origin=True)
        if not tg_api_id:
            error_print("No API ID entered. Exiting.")
            return None
        tg_api_hash = get_input_with_timeout("API Hash: ", timeout=30, default="", keep_origin=True)
        if not tg_api_hash:
            error_print("No API Hash entered. Exiting.")
            return None
        phone = get_input_with_timeout("Phone number (with country code): ", timeout=30, default="", keep_origin=True)
        if not phone:
            error_print("No phone number entered. Exiting.")
            return None
        bot_username = get_input_with_timeout("Bot username (default: SciNexBot): ", timeout=30, default="SciNexBot", keep_origin=True)
        if not bot_username:
            bot_username = "SciNexBot"
        return {
            "tg_api_id": tg_api_id,
            "tg_api_hash": tg_api_hash,
            "phone": phone,
            "bot_username": bot_username
        }

    async def validate_and_save(creds):
        global TG_API_ID, TG_API_HASH, PHONE, BOT_USERNAME
        TG_API_ID = creds.get("tg_api_id", TG_API_ID)
        TG_API_HASH = creds.get("tg_api_hash", TG_API_HASH)
        PHONE = creds.get("phone", PHONE)
        BOT_USERNAME = creds.get("bot_username", BOT_USERNAME)
        # Validate credentials
        # Try testing credentials without proxy first
        test_result = await test_credentials(TG_API_ID, TG_API_HASH, PHONE)
        if not os.path.exists(DEFAULT_PROXY_FILE):
            info_print(f"Proxy file not found: {DEFAULT_PROXY_FILE}")
            info_print("Attempting to find a suitable free proxy...")
            working_proxy = await test_and_select_working_proxy()
            if working_proxy:
                info_print("✓ Found and configured a working proxy")
            else:
                error_print("Could not find a working proxy for Telegram")
                error_print("You can either:")
                error_print("1. Try running again (will test different proxies)")
                error_print("2. Run with --no-proxy to connect directly")
                error_print("3. Provide a custom proxy configuration file")
                return None
        if not test_result.get("ok") and os.path.exists(DEFAULT_PROXY_FILE):
            info_print("Credential test failed without proxy, retrying with proxy...")
            test_result = await test_credentials(TG_API_ID, TG_API_HASH, PHONE, proxy=DEFAULT_PROXY_FILE)
        if test_result.get("ok"):
            info_print("Credentials validated successfully.")
            # Save to default location if not already there or if different
            save_needed = True
            if os.path.exists(CREDENTIALS_FILE):
                try:
                    with open(CREDENTIALS_FILE, 'r') as f:
                        existing = json.load(f)
                    # Compare all fields
                    if (
                        str(existing.get("tg_api_id", "")) == str(TG_API_ID)
                        and str(existing.get("tg_api_hash", "")) == str(TG_API_HASH)
                        and str(existing.get("phone", "")) == str(PHONE)
                        and str(existing.get("bot_username", "")) == str(BOT_USERNAME)
                    ):
                        save_needed = False
                except Exception:
                    save_needed = True
            if save_needed:
                try:
                    with open(CREDENTIALS_FILE, 'w') as f:
                        json.dump({
                            "tg_api_id": TG_API_ID,
                            "tg_api_hash": TG_API_HASH,
                            "phone": PHONE,
                            "bot_username": BOT_USERNAME
                        }, f, indent=2)
                    info_print(f"Credentials saved to: {CREDENTIALS_FILE}")
                except Exception as e:
                    debug_print(f"Warning: Could not save credentials to default location: {e}")
            return [TG_API_ID, TG_API_HASH, PHONE, BOT_USERNAME]
        else:
            error_print(f"Credential validation failed: {test_result.get('error', 'Unknown error')}")
            return None

    debug_print(f"Loading credentials from: {credentials_path}")

    # Try credentials_path first
    creds = None
    if os.path.exists(credentials_path):
        try:
            with open(credentials_path, 'r') as f:
                creds = json.load(f)
            result = await validate_and_save(creds)
            if result:
                return result
            else:
                info_print("Credentials in file are invalid. Please re-enter.")
        except Exception as e:
            error_print(f"Error loading credentials file: {e}")
            debug_print(f"Credentials loading error: {type(e).__name__}: {str(e)}")
            creds = None

    # If not found or invalid, try default location if different
    if credentials_path != CREDENTIALS_FILE and os.path.exists(CREDENTIALS_FILE):
        try:
            with open(CREDENTIALS_FILE, 'r') as f:
                creds = json.load(f)
            result = await validate_and_save(creds)
            if result:
                return result
            else:
                info_print("Credentials in default location are invalid. Please re-enter.")
        except Exception as e:
            error_print(f"Error loading credentials file: {e}")
            debug_print(f"Credentials loading error: {type(e).__name__}: {str(e)}")
            creds = None

    # If still not found or invalid, prompt user
    for attempt in range(2):  # Allow up to 2 attempts
        creds = prompt_for_credentials()
        if not creds:
            error_print("No credentials provided. Exiting.")
            return None
        result = await validate_and_save(creds)
        if result:
            return result
        else:
            info_print("Credentials invalid. Please try again.")
    error_print("Failed to provide valid credentials after multiple attempts or timeout.")
    return None
    
async def test_credentials(api_id, api_hash, phone_number, session_file=SESSION_FILE, proxy=None):
    """
    Test if the provided Telegram API credentials are correct by attempting to connect and authorize.
    Returns a dictionary with the result.
    """
    result = {
        "ok": False,
        "error": None,
        "user": None
    }
    try:
        proxy_config = load_proxy_config(proxy) if proxy else None
        client = create_telegram_client(api_id, api_hash, session_file, proxy_config)
        await client.start(phone=phone_number if phone_number else None)
        if await client.is_user_authorized():
            me = await client.get_me()
            result["ok"] = True
            result["user"] = {
                "id": me.id,
                "first_name": me.first_name,
                "last_name": me.last_name,
                "username": me.username,
                "phone": me.phone
            }
        else:
            result["error"] = "Not authorized. Credentials may be invalid or session expired."
    except Exception as e:
        result["error"] = f"Credential test failed: {str(e)}"
    finally:
        try:
            await client.disconnect()
        except Exception:
            pass
    return result

async def setup_proxy_configuration(proxy_arg):
    """Setup proxy configuration - load existing or find new working proxy"""
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
        if proxy_config:
            info_print("✓ Proxy configuration loaded successfully")
            return proxy_file
        else:
            error_print(f"Failed to load proxy configuration from: {proxy_file}")
            return False
    else:
        info_print(f"Proxy file not found: {proxy_file}")
        info_print("Searching for a working proxy...")
        
        # Try to find a working proxy
        working_proxy = await test_and_select_working_proxy()
        if working_proxy:
            info_print("✓ Found and configured a working proxy")
            return DEFAULT_PROXY_FILE
        else:
            error_print("Could not find a working proxy for Telegram")
            error_print("You can either:")
            error_print("1. Try running again (will test different proxies)")
            error_print("2. Run with --no-proxy to connect directly")
            error_print("3. Provide a custom proxy configuration file")
            return False

async def handle_request_button(button_text, callback_data, message_id, proxy_to_use):
    """Handle request button click"""
    print(f"\n📋 The corresponding paper is not available on Nexus.")
    user_input = get_input_with_timeout("Do you want to request it? [y/N]: ", timeout=30, default='n')
    
    if user_input in ['y', 'yes']:
        info_print(f"User chose to request the paper - clicking button: {button_text}")
        
        # Click the request button
        click_result = await click_callback_button(
            TG_API_ID, TG_API_HASH, PHONE, BOT_USERNAME,
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
    
    # Try to extract file size from button text first, then from callback_data
    button_size_info = extract_file_size_from_button_text(button_text)
    callback_size_info = None
    
    # If button text doesn't contain size info, try callback_data
    if not button_size_info and callback_data:
        callback_size_info = extract_file_size_from_callback_data(callback_data)
    
    # Use whichever source provided the size info (button text takes priority)
    size_info = button_size_info or callback_size_info
    if size_info:
        source = "button text" if button_size_info else "callback data"
        print(f"📏 File size: {size_info['original_size']} {size_info['unit']} ({size_info['size_mb']:.2f} MB)")
        debug_print(f"File size extracted from {source}: {size_info['original_size']} {size_info['unit']} ({size_info['size_mb']:.2f} MB)")
    
    user_input = get_input_with_timeout("Do you want to download it? [y/N]: ", timeout=30, default='n')
    
    if user_input in ['y', 'yes']:
        info_print(f"User chose to download the paper - clicking button: {button_text}")
        
        # Click the download button
        click_result = await click_callback_button(
            TG_API_ID, TG_API_HASH, PHONE, BOT_USERNAME,
            message_id, callback_data, SESSION_FILE, proxy_to_use
        )
        
        # Add file size information to click_result if available
        if size_info:
            if 'button_info' not in click_result:
                click_result['button_info'] = {}
            click_result['button_info']['file_size_mb'] = size_info['size_mb']
            click_result['button_info']['size_unit'] = size_info['unit']
            click_result['button_info']['original_size'] = size_info['original_size']
            
            source = "button_text" if button_size_info else "callback_data"
            debug_print(f"Added file size from {source}: {size_info['original_size']} {size_info['unit']} ({size_info['size_mb']:.2f} MB)")
        
        if click_result.get("ok"):
            info_print("✓ Successfully initiated download")
            if click_result.get("bot_reply") and click_result["bot_reply"].get("text"):
                print(f"Bot response: {click_result['bot_reply']['text']}")
            
            await wait_and_download_file(click_result, proxy_to_use)
        else:
            error_print(f"✗ Failed to download the paper: {click_result.get('error', 'Unknown error')}")
    else:
        info_print("User chose not to download the paper")

def extract_file_size_from_callback_data(callback_data):
    """
    Extract file size information from callback data
    
    Args:
        callback_data: The callback data string that might contain file size info
        
    Returns:
        Dictionary with size information or None if not found
    """
    if not callback_data:
        return None
    
    # Convert bytes to string if needed
    if isinstance(callback_data, bytes):
        callback_data = callback_data.decode('utf-8', errors='ignore')
    
    callback_str = str(callback_data)
    debug_print(f"Analyzing callback_data for file size: {callback_str}")
    
    # Look for various file size patterns
    size_patterns = [
        # MB patterns
        r'(\d+(?:\.\d+)?)\s*(?:mb|MB|megabytes?)',
        # MiB patterns  
        r'(\d+(?:\.\d+)?)\s*(?:mib|MiB)',
        # KB patterns
        r'(\d+(?:\.\d+)?)\s*(?:kb|KB|kilobytes?)',
        # KiB patterns
        r'(\d+(?:\.\d+)?)\s*(?:kib|KiB)',
        # GB patterns
        r'(\d+(?:\.\d+)?)\s*(?:gb|GB|gigabytes?)',
        # GiB patterns
        r'(\d+(?:\.\d+)?)\s*(?:gib|GiB)',
        # Bytes patterns
        r'(\d+)\s*(?:bytes?|B)',
    ]
    
    for pattern in size_patterns:
        match = re.search(pattern, callback_str, re.IGNORECASE)
        if match:
            size_value = float(match.group(1))
            size_text = match.group(0).lower()
            
            # Convert to MB for standardization
            if 'mb' in size_text or 'megabyte' in size_text:
                size_mb = size_value
                unit = 'MB'
            elif 'mib' in size_text:
                size_mb = size_value * 1.048576  # 1 MiB = 1.048576 MB
                unit = 'MiB'
            elif 'gb' in size_text or 'gigabyte' in size_text:
                size_mb = size_value * 1000  # 1 GB = 1000 MB
                unit = 'GB'
            elif 'gib' in size_text:
                size_mb = size_value * 1073.741824  # 1 GiB = 1073.741824 MB
                unit = 'GiB'
            elif 'kb' in size_text or 'kilobyte' in size_text:
                size_mb = size_value / 1000  # 1000 KB = 1 MB
                unit = 'KB'
            elif 'kib' in size_text:
                size_mb = size_value / 976.5625  # 1024 KiB = 1.024 MB
                unit = 'KiB'
            elif 'byte' in size_text or size_text.endswith('b'):
                size_mb = size_value / (1024 * 1024)  # Convert bytes to MB
                unit = 'bytes'
            else:
                continue
            
            return {
                'size_mb': size_mb,
                'unit': unit,
                'original_size': size_value
            }
    
    debug_print("No file size information found in callback_data")
    return None

def extract_file_size_from_button_text(button_text):
    """
    Extract file size information from button text
    
    Args:
        button_text: The button text string that might contain file size info
        
    Returns:
        Dictionary with size information or None if not found
    """
    if not button_text:
        return None
    
    button_str = str(button_text)
    debug_print(f"Analyzing button_text for file size: {button_str}")
    
    # Look for various file size patterns in button text
    size_patterns = [
        # MB patterns with common formats like "Download (5.2 MB)" or "5.2MB"
        r'(\d+(?:\.\d+)?)\s*(?:mb|MB|megabytes?)',
        # MiB patterns  
        r'(\d+(?:\.\d+)?)\s*(?:mib|MiB)',
        # KB patterns
        r'(\d+(?:\.\d+)?)\s*(?:kb|KB|kilobytes?)',
        # KiB patterns
        r'(\d+(?:\.\d+)?)\s*(?:kib|KiB)',
        # GB patterns
        r'(\d+(?:\.\d+)?)\s*(?:gb|GB|gigabytes?)',
        # GiB patterns
        r'(\d+(?:\.\d+)?)\s*(?:gib|GiB)',
        # Bytes patterns
        r'(\d+)\s*(?:bytes?|B)',
        # Pattern for sizes in parentheses like "(5.2 MB)"
        r'\((\d+(?:\.\d+)?)\s*(?:mb|MB|megabytes?)\)',
        r'\((\d+(?:\.\d+)?)\s*(?:mib|MiB)\)',
        r'\((\d+(?:\.\d+)?)\s*(?:kb|KB|kilobytes?)\)',
        r'\((\d+(?:\.\d+)?)\s*(?:kib|KiB)\)',
        r'\((\d+(?:\.\d+)?)\s*(?:gb|GB|gigabytes?)\)',
        r'\((\d+(?:\.\d+)?)\s*(?:gib|GiB)\)',
    ]
    
    for pattern in size_patterns:
        match = re.search(pattern, button_str, re.IGNORECASE)
        if match:
            size_value = float(match.group(1))
            size_text = match.group(0).lower()
            
            # Convert to MB for standardization
            if 'mb' in size_text or 'megabyte' in size_text:
                size_mb = size_value
                unit = 'MB'
            elif 'mib' in size_text:
                size_mb = size_value * 1.048576  # 1 MiB = 1.048576 MB
                unit = 'MiB'
            elif 'gb' in size_text or 'gigabyte' in size_text:
                size_mb = size_value * 1000  # 1 GB = 1000 MB
                unit = 'GB'
            elif 'gib' in size_text:
                size_mb = size_value * 1073.741824  # 1 GiB = 1073.741824 MB
                unit = 'GiB'
            elif 'kb' in size_text or 'kilobyte' in size_text:
                size_mb = size_value / 1000  # 1000 KB = 1 MB
                unit = 'KB'
            elif 'kib' in size_text:
                size_mb = size_value / 976.5625  # 1024 KiB = 1.024 MB
                unit = 'KiB'
            elif 'byte' in size_text or size_text.endswith('b'):
                size_mb = size_value / (1024 * 1024)  # Convert bytes to MB
                unit = 'bytes'
            else:
                continue
            
            debug_print(f"Extracted file size from button text: {size_value} {unit} ({size_mb:.2f} MB)")
            return {
                'size_mb': size_mb,
                'unit': unit,
                'original_size': size_value
            }
    
    debug_print("No file size information found in button_text")
    return None

async def wait_and_download_file(click_result, proxy_to_use):
    """Wait for file upload to Telegram and download it"""
    # Extract file size information from click_result (previously parsed from callback_data)
    if verbose_mode:
        print("Clicked button result:")
        print(click_result)
    
    # First check if file size was already extracted from callback_data
    button_info = click_result.get("button_info", {})
    file_size_mb = button_info.get("file_size_mb", 0)
    
    if file_size_mb > 0:
        size_unit = button_info.get("size_unit", "MB")
        original_size = button_info.get("original_size", file_size_mb)
        if verbose_mode:
            info_print(f"Using file size from button: {original_size} {size_unit} ({file_size_mb:.2f} MB)")
    else:
        # Fallback: try to extract from bot response text
        bot_text = click_result.get("bot_reply", {}).get("text", "")
        
        # Handle MB and MiB separately since they are different units
        mb_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:mb|MB|megabytes?)', bot_text, re.IGNORECASE)
        mib_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:mib|MiB)', bot_text, re.IGNORECASE)
        
        if mb_match:
            file_size_mb = float(mb_match.group(1))
            if verbose_mode:
                info_print(f"Detected file size from bot text: {file_size_mb} MB")
        elif mib_match:
            # Convert MiB to MB: 1 MiB = 1.048576 MB
            file_size_mib = float(mib_match.group(1))
            file_size_mb = file_size_mib * 1.048576
            if verbose_mode:
                info_print(f"Detected file size from bot text: {file_size_mib} MiB ({file_size_mb:.2f} MB)")
        else:
            # Check for other size units
            kb_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:kb|KB|kilobytes?)', bot_text, re.IGNORECASE)
            kib_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:kib|KiB)', bot_text, re.IGNORECASE)
            
            if kb_match:
                file_size_mb = float(kb_match.group(1)) / 1000
                if verbose_mode:
                    info_print(f"Detected file size from bot text: {file_size_mb:.2f} MB")
            elif kib_match:
                # Convert KiB to MB: 1 KiB = 0.001024 MB
                file_size_kib = float(kib_match.group(1))
                file_size_mb = file_size_kib * 0.001024
                if verbose_mode:
                    info_print(f"Detected file size from bot text: {file_size_kib} KiB ({file_size_mb:.2f} MB)")
            else:
                # Default assumption for academic papers
                file_size_mb = 5.0
                if verbose_mode:
                    info_print("No file size detected, assuming 5 MB for academic paper")
    
    # Calculate wait time based on file size
    base_wait = 10
    size_based_wait = int(file_size_mb * 5)
    total_wait = max(base_wait, size_based_wait)
    
    info_print(f"Waiting {total_wait} seconds for file preparation...")
    
    # Wait with progress indication (only show progress in verbose mode)
    for i in range(total_wait):
        if verbose_mode and i % 5 == 0 and i > 0:
            info_print(f"Still waiting... {i}/{total_wait} seconds")
        await asyncio.sleep(1)
    
    info_print("Checking for file...")
    
    # Handle file download if the bot reply contains a file
    download_result = await handle_file_download_from_bot_reply(
        click_result.get("bot_reply"), proxy_to_use
    )
    
    if download_result and download_result.get("success"):
        info_print("✓ File downloaded successfully!")
        info_print(f"File saved to: {download_result['file_path']}")
        if verbose_mode:
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
    # Check if the button text contains a download symbol (e.g., "⬇️" or "↓" or "download")
    has_download = any(sym in button_text.lower() for sym in ["⬇️", "↓", "download"])

    if has_request:
        await handle_request_button(button_text, callback_data, message_id, proxy_to_use)
    elif has_download:
        await handle_download_button(button_text, callback_data, message_id, proxy_to_use)
    
    info_print(f"\n--- Completed processing all {len(callback_buttons)} buttons ---")

async def get_latest_messages_from_bot(api_id, api_hash, bot_username, session_file=SESSION_FILE, limit=10, proxy=None):
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
    client = create_telegram_client(api_id, api_hash, session_file, proxy_config)
    
    try:
        # Check if session file exists
        if not os.path.exists(session_file):
            error_print(f"Session file not found: {session_file}")
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

async def get_user_profile(api_id, api_hash, phone_number, bot_username, session_file=SESSION_FILE, proxy=None):
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
    output.append("\n" + "="*60)
    output.append("NEXUS USER PROFILE")
    output.append("="*60)
    
    if "error" in profile_result:
        output.append(f"❌ ERROR: {profile_result['error']}")
        error_print(profile_result['error'])
    elif profile_result.get("ok"):
        output.append("✅ SUCCESS: Profile information retrieved!")
        output.append("")
        
        profile = profile_result.get("profile", {})
        raw_response = profile.get("raw_response", "")
        
        if raw_response:
            # Parse the raw response with improved formatting
            text = raw_response.strip()
            
            # Parse user level information from the markdown formatted text
            level_pattern = r"\*\*User level:\*\*\s*`([^\s]+)\s+([^`]+)`\s+with\s+`(\d+)`\s+n-points,\s+uploaded\s+`(\d+)`\s+books and papers,\s+takes\s+`(\d+)(?:st|nd|rd|th)`\s+leaderboard position"
            level_match = re.search(level_pattern, text)
            
            if level_match:
                emoji = level_match.group(1)
                level_name = level_match.group(2)
                n_points = int(level_match.group(3))
                uploaded_count = int(level_match.group(4))
                position = int(level_match.group(5))
                
                output.append(f"🏆 User Level: {emoji} {level_name}")
                output.append(f"⭐ N-Points: {n_points:,}")
                output.append(f"📚 Contributions: {uploaded_count:,} books and papers uploaded")
                
                # Add ordinal suffix for position
                if 10 <= position % 100 <= 20:
                    suffix = "th"
                else:
                    suffix = {1: "st", 2: "nd", 3: "rd"}.get(position % 10, "th")
                output.append(f"🏅 Leaderboard Rank: #{position}{suffix}")
            
            # Parse OrcID information
            orcid_pattern = r"\*\*OrcID:\*\*\s*\[([^\]]+)\]\(([^)]+)\)"
            orcid_match = re.search(orcid_pattern, text)
            
            if orcid_match:
                link_text = orcid_match.group(1)
                link_url = orcid_match.group(2)
                
                output.append("")
                output.append("─" * 40)
                output.append("")
                
                if "Link your OrcID" in link_text:
                    output.append(f"🔗 OrcID Status: Not linked")
                    output.append(f"   Connect at: {link_url}")
                else:
                    output.append(f"🔗 OrcID: {link_text}")
                    output.append(f"   URL: {link_url}")
            
            # Add summary section if we have the main stats
            if level_match:
                output.append("")
                output.append("📊 SUMMARY")
                output.append("─" * 20)
                
                # Calculate average points per upload
                if uploaded_count > 0:
                    avg_points = round(n_points / uploaded_count, 1)
                    output.append(f"• Average points per contribution: {avg_points}")
                
                # Status messages based on level
                status_messages = {
                    "Willing Spirit": "🕊️ Active contributor, building reputation",
                    "Scholar": "📚 Experienced researcher", 
                    "Expert": "🎓 Recognized expert in the community",
                    "Master": "👑 Top-tier contributor"
                }
                
                if level_name in status_messages:
                    output.append(f"• Status: {status_messages[level_name]}")
                
                # Leaderboard context
                if position <= 10:
                    output.append(f"• 🌟 Top 10 contributor! Excellent work!")
                elif position <= 50:
                    output.append(f"• ⭐ Top 50 contributor! Great performance!")
                elif position <= 100:
                    output.append(f"• 🔥 Top 100 contributor! Keep it up!")
                else:
                    output.append(f"• 💪 Building reputation - {position}{suffix} place")
        
        # Show profile settings from buttons if available
        bot_reply = profile_result.get("bot_reply", {})
        buttons = bot_reply.get("buttons", [])
        
        if buttons:
            output.append("")
            output.append("⚙️ PROFILE SETTINGS")
            output.append("─" * 20)
            
            for button in buttons:
                button_text = button.get("text", "")
                
                if "Gaia Subscription" in button_text:
                    output.append("• 🌟 Gaia Subscription available")
                elif "profile is invisible" in button_text:
                    output.append("• 👁️ Profile visibility: Private")
                elif "interests are invisible" in button_text:
                    output.append("• 🎯 Interest visibility: Private")
                elif "Receiving daily free points" in button_text:
                    output.append("• 🎁 Daily free points: Enabled")
        
        else:
            output.append("❌ No profile information available in response")
    
    else:
        output.append("❌ FAILED: Could not retrieve profile information")
        error_print("Profile retrieval failed")
    
    output.append("="*60)
    
    # Print to console and log
    result_text = "\n".join(output)
    if logger:
        logger.info("Formatting profile result for display")
        logger.info(result_text)

def format_messages_result(messages_result):
    """Format the messages result in a human-readable way"""
    output = []
    output.append("\n" + "="*80)
    output.append("RECENT MESSAGES FROM BOT")
    output.append("="*80)
    
    if "error" in messages_result:
        output.append(f"❌ ERROR: {messages_result['error']}")
        error_print(messages_result['error'])
    elif messages_result.get("ok"):
        bot_username = messages_result.get("bot_username", "Unknown")
        messages_count = messages_result.get("messages_count", 0)
        messages = messages_result.get("messages", [])
        
        output.append(f"✅ SUCCESS: Retrieved {messages_count} messages from @{bot_username}")
        output.append("")
        
        if not messages:
            output.append("📭 No messages found")
        else:
            for i, msg in enumerate(messages, 1):
                output.append(f"📨 Message #{i}")
                output.append(f"   ID: {msg.get('message_id', 'N/A')}")
                output.append(f"   Date: {msg.get('date_formatted', 'N/A')}")
                
                # Message text
                text = msg.get('text', '')
                if text:
                    # Truncate long messages for display
                    display_text = text[:200] + "..." if len(text) > 200 else text
                    output.append(f"   Text: {display_text}")
                else:
                    output.append("   Text: [No text content]")
                
                # Media information
                if msg.get('has_media'):
                    media_type = msg.get('media_type', 'unknown')
                    output.append(f"   📎 Media: {media_type}")
                
                # Buttons information
                buttons = msg.get('buttons', [])
                if buttons:
                    output.append(f"   🔘 Buttons: {len(buttons)} button(s)")
                    for j, btn in enumerate(buttons[:3], 1):  # Show max 3 buttons
                        btn_text = btn.get('text', 'N/A')
                        btn_type = btn.get('type', 'unknown')
                        output.append(f"      {j}. {btn_text} ({btn_type})")
                    if len(buttons) > 3:
                        output.append(f"      ... and {len(buttons) - 3} more")
                
                # Additional info
                if msg.get('is_reply'):
                    output.append("   ↩️ Reply to previous message")
                
                if msg.get('views'):
                    output.append(f"   👁️ Views: {msg['views']:,}")
                
                if msg.get('forwards'):
                    output.append(f"   🔄 Forwards: {msg['forwards']:,}")
                
                output.append("")  # Blank line between messages
    else:
        output.append("❌ FAILED: Could not retrieve messages")
        error_print("Message retrieval failed")
    
    output.append("="*80)
    
    # Print to console and log
    result_text = "\n".join(output)
    if logger:
        logger.info("Formatting messages result for display")
        logger.info(result_text)

async def fetch_and_display_recent_messages(api_id, api_hash, bot_username, session_file=SESSION_FILE, 
                                            limit=10, proxy=None, display=True):
    """
    Fetch recent messages from a bot and optionally display them
    
    Args:
        api_id: Your Telegram API ID
        api_hash: Your Telegram API hash
        bot_username: Bot's username
        session_file: Name of the session file
        limit: Maximum number of messages to retrieve (default: 10, max: 100)
        proxy: Proxy configuration dict or file path
        display: Whether to display formatted results (default: True)
        
    Returns:
        Dictionary with success status and messages list
    """
    # Validate and clamp limit
    if limit < 1:
        limit = 1
    elif limit > 100:  # Reasonable maximum to prevent excessive API calls
        limit = 100
        info_print(f"Limit clamped to maximum of 100 messages")
    
    info_print(f"Fetching {limit} recent messages from @{bot_username}...")
    
    # Use existing function to get messages
    messages_result = await get_latest_messages_from_bot(
        api_id, api_hash, bot_username, session_file, limit, proxy
    )
    
    # Display results if requested
    if display:
        format_messages_result(messages_result)
    
    return messages_result

async def fetch_nexus_aaron_messages(api_id, api_hash, phone_number, session_file=SESSION_FILE, 
                                    limit=10, proxy=None, display=True):
    """
    Fetch recent messages from the @nexus_aaron bot specifically
    
    Args:
        api_id: Your Telegram API ID
        api_hash: Your Telegram API hash
        phone_number: Your phone number (not used, kept for compatibility)
        session_file: Name of the session file
        limit: Maximum number of messages to retrieve (default: 10, max: 100)
        proxy: Proxy configuration dict or file path
        display: Whether to display formatted results (default: True)
        
    Returns:
        Dictionary with success status and messages list from @nexus_aaron
    """
    nexus_aaron_username = "nexus_aaron"
    
    info_print(f"Fetching {limit} recent messages from @{nexus_aaron_username}...")
    debug_print(f"Specialized function for Nexus Aaron bot messages")
    
    # Use existing function to get messages from nexus_aaron
    messages_result = await get_latest_messages_from_bot(
        api_id, api_hash, nexus_aaron_username, session_file, limit, proxy
    )
    
    # Display results if requested with specialized formatting for nexus_aaron
    if display and messages_result.get("ok"):
        format_nexus_aaron_messages(messages_result)
    elif display:
        format_messages_result(messages_result)
    
    return messages_result

def format_nexus_aaron_messages(messages_result):
    """Format nexus_aaron messages with specialized formatting for research requests"""
    output = []
    output.append("\n" + "="*80)
    output.append("RECENT MESSAGES FROM @nexus_aaron")
    output.append("="*80)
    
    if "error" in messages_result:
        output.append(f"❌ ERROR: {messages_result['error']}")
        error_print(messages_result['error'])
    elif messages_result.get("ok"):
        bot_username = messages_result.get("bot_username", "Unknown")
        messages_count = messages_result.get("messages_count", 0)
        messages = messages_result.get("messages", [])
        
        output.append(f"✅ SUCCESS: Retrieved {messages_count} messages from @{bot_username}")
        output.append("")
        
        if not messages:
            output.append("📭 No messages found")
        else:
            # Categorize messages
            requests = []
            uploads = []
            other = []
            
            for msg in messages:
                text = msg.get('text', '')
                if text.startswith('#request'):
                    requests.append(msg)
                elif '#voting' in text and msg.get('has_media'):
                    uploads.append(msg)
                else:
                    other.append(msg)
            
            # Display statistics
            output.append(f"📊 MESSAGE BREAKDOWN:")
            output.append(f"   📋 Research Requests: {len(requests)}")
            output.append(f"   📄 Document Uploads: {len(uploads)}")
            output.append(f"   💬 Other Messages: {len(other)}")
            output.append("")
            
            # Display research requests
            if requests:
                output.append("📋 RESEARCH REQUESTS:")
                output.append("─" * 50)
                for i, msg in enumerate(requests, 1):
                    request_info = parse_nexus_aaron_request(msg.get('text', ''))
                    
                    output.append(f"[{i}] ⭐ Request Point: {request_info['request_count']}")
                    output.append(f"   🕐 Time: {msg.get('date_formatted', 'N/A')}")
                    output.append(f"   📊 Type: {request_info['pub_type']}")
                    
                    if request_info['doi']:
                        output.append(f"   🔗 DOI: {request_info['doi']}")
                        
                        # Extract publisher name from DOI
                        publisher_name = get_publisher_name_from_doi(request_info['doi'])
                        if publisher_name:
                            output.append(f"   📖 Publisher: {publisher_name}")
                        elif request_info['publisher_code']:
                            output.append(f"   📖 Publisher Code: {request_info['publisher_code']}")
                    elif request_info['publisher_code']:
                        output.append(f"   📖 Publisher Code: {request_info['publisher_code']}")
                    
                    if request_info['libstc_link']:
                        output.append(f"   🌐 LibSTC: {request_info['libstc_link']}")
                    
                    if request_info['worldcat_link']:
                        output.append(f"   📚 WorldCat: {request_info['worldcat_link']}")
                    
                    output.append(f"   🆔 Message ID: {msg.get('message_id', 'N/A')}")
                    output.append("")
            
            # Display document uploads
            if uploads:
                output.append("📄 DOCUMENT UPLOADS:")
                output.append("─" * 50)
                for i, msg in enumerate(uploads, 1):
                    upload_info = parse_nexus_aaron_upload(msg.get('text', ''))
                    
                    output.append(f"#{i} {upload_info['title']}")
                    output.append(f"   🕐 Time: {msg.get('date_formatted', 'N/A')}")
                    output.append(f"   📊 Type: {upload_info['pub_type']}")
                    
                    if upload_info['author']:
                        output.append(f"   ✍️ Author: {upload_info['author']}")
                    
                    if upload_info['year']:
                        output.append(f"   📅 Year: {upload_info['year']}")
                    
                    if upload_info['pages']:
                        output.append(f"   📄 Pages: {upload_info['pages']}")
                    
                    if upload_info['doi']:
                        output.append(f"   🔗 DOI: {upload_info['doi']}")
                        
                        # Extract publisher name from DOI
                        publisher_name = get_publisher_name_from_doi(upload_info['doi'])
                        if publisher_name:
                            output.append(f"   📖 Publisher: {publisher_name}")
                    
                    if upload_info['worldcat_link']:
                        output.append(f"   📚 WorldCat: {upload_info['worldcat_link']}")
                    
                    if upload_info['isbn']:
                        output.append(f"   📖 ISBN: {upload_info['isbn']}")
                    
                    voting_status = "✅ Available for voting" if msg.get('buttons') else "❌ No voting available"
                    output.append(f"   🗳️ Status: {voting_status}")
                    output.append(f"   🆔 Message ID: {msg.get('message_id', 'N/A')}")
                    output.append("")
            
            # Display other messages
            if other:
                output.append("💬 OTHER MESSAGES:")
                output.append("─" * 50)
                for i, msg in enumerate(other, 1):
                    text = msg.get('text', '')
                    display_text = text[:100] + "..." if len(text) > 100 else text
                    
                    output.append(f"#{i} {display_text}")
                    output.append(f"   🕐 Time: {msg.get('date_formatted', 'N/A')}")
                    output.append(f"   🆔 Message ID: {msg.get('message_id', 'N/A')}")
                    
                    if msg.get('has_media'):
                        output.append(f"   📎 Media: {msg.get('media_type', 'unknown')}")
                    
                    if msg.get('buttons'):
                        output.append(f"   🔘 Buttons: {len(msg['buttons'])}")
                    
                    output.append("")
    else:
        output.append("❌ FAILED: Could not retrieve messages")
        error_print("Messages retrieval failed")
    
    output.append("="*80)
    
    # Print to console and log
    result_text = "\n".join(output)
    if logger:
        logger.info("Formatting nexus_aaron messages for display")
        logger.info(result_text)

def get_publisher_name_from_doi(doi):
    """
    Extract publisher name from DOI using Crossref API
    
    Args:
        doi: DOI string (e.g., "10.1038/nature12373")
        
    Returns:
        Publisher name string or None if not found
    """
    if not doi or not isinstance(doi, str):
        return None
    
    # Extract publisher prefix from DOI (part between 10. and /)
    doi_match = re.match(r'^10\.(\d+)/', doi.strip())
    if not doi_match:
        debug_print(f"Invalid DOI format for publisher extraction: {doi}")
        return None
    
    publisher_prefix = doi_match.group(1)
    debug_print(f"Extracted publisher prefix from DOI {doi}: {publisher_prefix}")
    
    try:
        # Query Crossref API for publisher information
        # Use the DOI to get work information which includes publisher
        crossref_url = f"https://api.crossref.org/works/{doi}"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (compatible; TelegramBot/1.0; mailto:your-email@example.com)'
        }
        
        debug_print(f"Querying Crossref API for DOI: {doi}")
        response = requests.get(crossref_url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            
            # Extract publisher name from the response
            work = data.get('message', {})
            publisher = work.get('publisher')
            
            if publisher:
                debug_print(f"Found publisher name for DOI {doi}: {publisher}")
                return publisher
            else:
                debug_print(f"No publisher information found in Crossref response for DOI {doi}")
                
                # Fallback: try to get institution/organization info
                institution = work.get('institution')
                if institution and isinstance(institution, list) and len(institution) > 0:
                    inst_name = institution[0].get('name')
                    if inst_name:
                        debug_print(f"Found institution name as fallback for DOI {doi}: {inst_name}")
                        return inst_name
        
        elif response.status_code == 404:
            debug_print(f"DOI not found in Crossref database: {doi}")
            return None
        else:
            debug_print(f"Crossref API error for DOI {doi}: HTTP {response.status_code}")
            return None
            
    except requests.RequestException as e:
        debug_print(f"Error querying Crossref API for DOI {doi}: {str(e)}")
        return None
    except Exception as e:
        debug_print(f"Unexpected error getting publisher name for DOI {doi}: {str(e)}")
        return None
    
    return None

def parse_nexus_aaron_request(text):
    """
    Parse a nexus_aaron request message to extract structured information
    
    Args:
        text: The raw message text from nexus_aaron
        
    Returns:
        Dictionary with parsed information
    """
    
    request_info = {
        'request_count': 'Unknown',
        'pub_type': 'Unknown',
        'doi': None,
        'publisher_code': None,
        'libstc_link': None,
        'worldcat_link': None,
        'raw_text': text
    }
    
    if not text:
        return request_info
    
    # Extract request count: #request (X)
    request_match = re.search(r'#request \((\d+)\)', text)
    if request_match:
        request_info['request_count'] = request_match.group(1)
    
    # Determine publication type by emoji
    if '🔬' in text:
        request_info['pub_type'] = 'Research Paper'
    elif '📚' in text:
        request_info['pub_type'] = 'Book'
    elif '📖' in text:
        request_info['pub_type'] = 'Book Chapter'
    else:
        request_info['pub_type'] = 'Unknown'
    
    # Extract DOI
    doi_match = re.search(r'(10\.\d+/[^\s\]]+)', text)
    if doi_match:
        request_info['doi'] = doi_match.group(1)
    
    # Extract publisher code (e.g., #p_1177)
    publisher_match = re.search(r'#p_(\d+)', text)
    if publisher_match:
        request_info['publisher_code'] = f"p_{publisher_match.group(1)}"
    
    # Extract LibSTC link
    libstc_match = re.search(r'\[🔬\]\((https://libstc\.cc/[^)]+)\)', text)
    if not libstc_match:
        libstc_match = re.search(r'\[📚\]\((https://libstc\.cc/[^)]+)\)', text)
    if libstc_match:
        request_info['libstc_link'] = libstc_match.group(1)
    
    # Extract WorldCat link
    worldcat_match = re.search(r'\[worldcat\]\((https://search\.worldcat\.org/[^)]+)\)', text)
    if worldcat_match:
        request_info['worldcat_link'] = worldcat_match.group(1)
    
    return request_info

def parse_nexus_aaron_upload(text):
    """
    Parse a nexus_aaron upload/voting message to extract structured information
    
    Args:
        text: The raw message text from nexus_aaron upload
        
    Returns:
        Dictionary with parsed upload information
    """
    
    upload_info = {
        'title': 'Unknown',
        'author': None,
        'year': None,
        'pages': None,
        'pub_type': 'Unknown',
        'doi': None,
        'worldcat_link': None,
        'isbn': None,
        'libstc_link': None,
        'raw_text': text
    }
    
    if not text:
        return upload_info
    
    # Determine publication type by emoji
    if '🔬' in text:
        upload_info['pub_type'] = 'Research Paper'
    elif '📚' in text:
        upload_info['pub_type'] = 'Book'
    elif '📖' in text:
        upload_info['pub_type'] = 'Book Chapter'
    else:
        upload_info['pub_type'] = 'Unknown'
    
    # Extract title from **title** format
    title_match = re.search(r'\*\*([^*]+)\*\*', text)
    if title_match:
        upload_info['title'] = title_match.group(1).strip()
    
    # Extract year from (YYYY) or (YYYY-MM) format
    year_match = re.search(r'\((\d{4})(?:-\d{2})?\)', text)
    if year_match:
        upload_info['year'] = year_match.group(1)
    
    # Extract author name (appears after title and before year)
    # Pattern: **Title** (year) \nAuthor pp. pages
    author_match = re.search(r'\*\*[^*]+\*\*[^\\n]*\\n([^\\n]+?)(?:\s+pp\.\s+\d+)?', text)
    if author_match:
        upload_info['author'] = author_match.group(1).strip()
    
    # Extract pages
    pages_match = re.search(r'pp\.\s+(\d+)', text)
    if pages_match:
        upload_info['pages'] = pages_match.group(1)
    
    # Extract DOI
    doi_match = re.search(r'(10\.\d+/[^\s\]]+)', text)
    if doi_match:
        upload_info['doi'] = doi_match.group(1)
    
    # Extract WorldCat link and ISBN
    worldcat_match = re.search(r'\[isbn:(\d+)\]\((https://search\.worldcat\.org/[^)]+)\)', text)
    if worldcat_match:
        upload_info['isbn'] = worldcat_match.group(1)
        upload_info['worldcat_link'] = worldcat_match.group(2)
    
    # Extract LibSTC link
    libstc_match = re.search(r'\[🔬\]\((https://libstc\.cc/[^)]+)\)', text)
    if not libstc_match:
        libstc_match = re.search(r'\[📚\]\((https://libstc\.cc/[^)]+)\)', text)
    if libstc_match:
        upload_info['libstc_link'] = libstc_match.group(1)
    
    return upload_info

async def upload_file_to_bot(api_id, api_hash, phone_number, bot_username, file_path, message="", session_file=SESSION_FILE, proxy=None):
    """
    Upload a file to a Telegram bot with optional message
    
    Args:
        api_id: Your Telegram API ID
        api_hash: Your Telegram API hash
        phone_number: Your phone number (not used, kept for compatibility)
        bot_username: Bot's username
        file_path: Path to the file to upload
        message: Optional message to send with the file (default: "")
        session_file: Name of the session file
        proxy: Proxy configuration dict or file path
        
    Returns:
        Dictionary with upload result and bot reply
    """
    debug_print(f"Uploading file to bot: {file_path}")
    
    # Validate file exists
    if not os.path.exists(file_path):
        error_print(f"File not found: {file_path}")
        return {"error": f"File not found: {file_path}"}
    
    # Get file info
    file_size = os.path.getsize(file_path)
    file_name = os.path.basename(file_path)
    file_size_mb = file_size / (1024 * 1024)
    
    info_print(f"Preparing to upload: {file_name}")
    info_print(f"File size: {file_size_mb:.2f} MB")
    
    # Load proxy configuration
    proxy_config = load_proxy_config(proxy)
    if proxy and proxy_config is None:
        return {"error": "Error loading proxy configuration"}
    
    # Create client
    client = create_telegram_client(api_id, api_hash, session_file, proxy_config)
    
    try:
        # Check if session file exists
        if not os.path.exists(session_file):
            error_print(f"Session file not found: {session_file}")
            return {"error": "Session file not found. Run script interactively first to create session."}
        
        debug_print("Starting client for file upload...")
        if proxy_config:
            info_print(f"Connecting through proxy: {proxy_config['type']}://{proxy_config['addr']}:{proxy_config['port']}")
        
        await client.start()
        
        # Verify we're connected
        if not await client.is_user_authorized():
            error_print("Session expired or not authorized")
            return {"error": "Session expired. Please delete the session file and run interactively to re-authenticate."}
        
        debug_print("User authorized successfully")
        
        # Get the bot entity
        debug_print(f"Getting bot entity for: {bot_username}")
        bot_entity = await client.get_entity(bot_username)
        debug_print(f"Bot entity retrieved: {bot_entity.id}")
        
        # Create message handler for bot responses
        handler, get_bot_reply = create_message_handler(bot_entity)
        client.on(events.NewMessage(from_users=bot_entity))(handler)
        
        # Upload progress callback
        last_progress = 0
        
        def progress_callback(current, total):
            nonlocal last_progress
            if total > 0:
                progress = int((current / total) * 100)
                if progress >= last_progress + 10:  # Update every 10%
                    info_print(f"Upload progress: {progress}% ({current / (1024*1024):.2f}/{total / (1024*1024):.2f} MB)")
                    last_progress = progress
        
        # Send file with optional message
        debug_print(f"Starting file upload: {file_path}")
        start_time = datetime.now()
        
        result = await client.send_file(
            bot_username,
            file_path,
            caption=message if message else None,
            progress_callback=progress_callback
        )
        
        end_time = datetime.now()
        upload_time = (end_time - start_time).total_seconds()
        upload_speed_mbps = file_size_mb / max(upload_time, 1)
        
        info_print(f"✓ File uploaded successfully!")
        info_print(f"Upload time: {upload_time:.2f} seconds")
        info_print(f"Upload speed: {upload_speed_mbps:.2f} MB/s")
        info_print(f"Message ID: {result.id}")
        
        # Wait for bot reply
        bot_reply = await wait_for_reply(get_bot_reply, timeout=30)
        
        # If no immediate reply, fetch recent messages
        if bot_reply is None:
            bot_reply = await fetch_recent_messages(client, bot_entity, result)
        
        response = {
            "ok": True,
            "uploaded_file": {
                "file_path": file_path,
                "file_name": file_name,
                "file_size": file_size,
                "file_size_mb": file_size_mb,
                "upload_time": upload_time,
                "upload_speed_mbps": upload_speed_mbps,
                "message_id": result.id,
                "date": result.date.timestamp(),
                "caption": message if message else None
            },
            "bot_reply": bot_reply
        }
        
        debug_print("File upload operation completed successfully")
        return response
        
    except Exception as e:
        error_print(f"Error uploading file: {str(e)}")
        debug_print(f"File upload exception: {type(e).__name__}: {str(e)}")
        return {"error": f"Error uploading file: {str(e)}"}
    finally:
        debug_print("Disconnecting client after file upload...")
        await client.disconnect()

def format_upload_result(upload_result):
    """Format the upload result in a human-readable way"""
    output = []
    output.append("\n" + "="*60)
    output.append("FILE UPLOAD RESULT")
    output.append("="*60)
    
    if "error" in upload_result:
        output.append(f"❌ ERROR: {upload_result['error']}")
        error_print(upload_result['error'])
    elif upload_result.get("ok"):
        output.append("✅ SUCCESS: File uploaded successfully!")
        output.append("")
        
        # Format uploaded file info
        file_info = upload_result.get("uploaded_file", {})
        if file_info:
            upload_time = datetime.fromtimestamp(file_info.get("date", 0)).strftime("%Y-%m-%d %H:%M:%S")
            output.append("📤 UPLOADED FILE:")
            output.append(f"   📁 Name: {file_info.get('file_name', 'N/A')}")
            output.append(f"   📏 Size: {file_info.get('file_size_mb', 0):.2f} MB")
            output.append(f"   ⏱️ Upload Time: {file_info.get('upload_time', 0):.2f} seconds")
            output.append(f"   🚀 Speed: {file_info.get('upload_speed_mbps', 0):.2f} MB/s")
            output.append(f"   🆔 Message ID: {file_info.get('message_id', 'N/A')}")
            output.append(f"   📅 Time: {upload_time}")
            
            caption = file_info.get('caption')
            if caption:
                output.append(f"   💬 Caption: {caption}")
            
            debug_print(f"Upload details: {file_info.get('file_name')} - {file_info.get('file_size_mb', 0):.2f} MB in {file_info.get('upload_time', 0):.2f}s")
        
        # Format bot reply
        bot_reply = upload_result.get("bot_reply")
        if bot_reply:
            reply_time = datetime.fromtimestamp(bot_reply.get("date", 0)).strftime("%Y-%m-%d %H:%M:%S")
            output.append("")
            output.append("📥 BOT REPLY:")
            output.append(f"   🆔 ID: {bot_reply.get('message_id', 'N/A')}")
            output.append(f"   📅 Time: {reply_time}")
            output.append(f"   💬 Text: {bot_reply.get('text', 'N/A')}")
            
            # Format buttons if present
            buttons = bot_reply.get("buttons", [])
            if buttons:
                output.append("   🔘 Buttons:")
                for i, button in enumerate(buttons, 1):
                    button_type = button.get("type", "unknown")
                    button_text = button.get("text", "N/A")
                    
                    if button_type == "url":
                        output.append(f"     {i}. {button_text} (URL: {button.get('url', 'N/A')})")
                    elif button_type == "callback":
                        callback_data = button.get('callback_data', 'N/A')
                        output.append(f"     {i}. {button_text} (Callback: {callback_data})")
                    else:
                        output.append(f"     {i}. {button_text} ({button_type})")
            
            debug_print(f"Bot reply: {len(buttons)} buttons, {len(bot_reply.get('text', ''))} chars")
        else:
            output.append("")
            output.append("📥 BOT REPLY: No reply received (timeout)")
            debug_print("No bot reply received for file upload")
    else:
        output.append("❌ FAILED: File upload failed")
        error_print("File upload failed")
    
    output.append("="*60)
    
    # Print to console and log
    result_text = "\n".join(output)
    if logger:
        logger.info("Formatting upload result for display")
        logger.info(result_text)

async def upload_file_to_nexus_aaron(api_id, api_hash, phone_number, file_path, message="", session_file=SESSION_FILE, proxy=None):
    """
    Upload a file to the @nexus_aaron bot specifically
    
    Args:
        api_id: Your Telegram API ID
        api_hash: Your Telegram API hash
        phone_number: Your phone number (not used, kept for compatibility)
        file_path: Path to the file to upload
        message: Optional message to send with the file (default: "")
        session_file: Name of the session file
        proxy: Proxy configuration dict or file path
        
    Returns:
        Dictionary with upload result and bot reply from @nexus_aaron
    """
    nexus_aaron_username = "nexus_aaron"
    
    info_print(f"Uploading file to @{nexus_aaron_username}...")
    debug_print(f"File path: {file_path}")
    
    # Use the existing upload_file_to_bot function with nexus_aaron as target
    upload_result = await upload_file_to_bot(
        api_id, api_hash, phone_number, nexus_aaron_username, 
        file_path, message, session_file, proxy
    )
    
    if upload_result.get("ok"):
        info_print(f"✓ Successfully uploaded file to @{nexus_aaron_username}")
        
        # Add nexus_aaron specific information to the result
        upload_result["target_bot"] = nexus_aaron_username
        upload_result["upload_type"] = "nexus_aaron_contribution"
        
        # Parse bot reply for nexus_aaron specific content
        bot_reply = upload_result.get("bot_reply")
        if bot_reply and bot_reply.get("text"):
            reply_text = bot_reply["text"]
            
            # Check for common nexus_aaron responses
            if "thank you" in reply_text.lower() or "received" in reply_text.lower():
                upload_result["status"] = "received"
                info_print("File was received by nexus_aaron")
            elif "voting" in reply_text.lower():
                upload_result["status"] = "pending_voting"
                info_print("File is pending community voting")
            elif "error" in reply_text.lower() or "problem" in reply_text.lower():
                upload_result["status"] = "error"
                info_print("nexus_aaron reported an issue with the file")
            else:
                upload_result["status"] = "uploaded"
        
        debug_print(f"Upload to nexus_aaron completed with status: {upload_result.get('status', 'unknown')}")
    else:
        error_print(f"✗ Failed to upload file to @{nexus_aaron_username}: {upload_result.get('error', 'Unknown error')}")
    
    return upload_result

async def simple_upload_to_nexus_aaron(file_path, verbose=False):
    """
    Upload a file to the @nexus_aaron bot with minimal input.
    If the file is a PDF, try to extract the DOI using getpapers.
    Args:
        file_path (str): Path to the file to upload.
        verbose (bool): If True, enable verbose output.
    Returns:
        dict: Upload result.
    """
    # Optionally enable verbose mode and logging
    if verbose:
        setup_logging(DEFAULT_LOG_FILE, verbose=True)
        info_print("Verbose mode enabled for simple upload.")

    # Load credentials from default location
    if not os.path.exists(CREDENTIALS_FILE):
        error_print("Credentials file not found. Please run the script interactively to set up credentials.")
        return {"error": "Credentials file not found."}
    creds = None
    try:
        with open(CREDENTIALS_FILE, "r") as f:
            creds = json.load(f)
    except Exception as e:
        error_print(f"Failed to load credentials: {e}")
        return {"error": f"Failed to load credentials: {e}"}
    api_id = creds.get("tg_api_id")
    api_hash = creds.get("tg_api_hash")
    phone = creds.get("phone")
    # Use default session file and proxy if available
    session_file = SESSION_FILE
    proxy = await decide_proxy_usage(TG_API_ID, TG_API_HASH, PHONE, SESSION_FILE, DEFAULT_PROXY_FILE)

    # If file is a PDF, try to extract DOI for caption
    caption = ""
    if file_path.lower().endswith(".pdf"):
        try:
            doi = getpapers.extract_dois_from_pdf(file_path)
            if doi:
                caption = f"DOI: {doi}"
                info_print(f"Extracted DOI from PDF: {doi}")
        except Exception as e:
            debug_print(f"Could not extract DOI from PDF: {e}")

    # Call upload_file_to_nexus_aaron
    result = await upload_file_to_nexus_aaron(
        api_id, api_hash, phone, file_path, caption, session_file, proxy
    )
    if verbose:
        format_nexus_aaron_upload_result(result)
    return result

def format_nexus_aaron_upload_result(upload_result):
    """Format the nexus_aaron upload result with specialized formatting"""
    output = []
    output.append("\n" + "="*70)
    output.append("NEXUS AARON FILE UPLOAD RESULT")
    output.append("="*70)
    
    if "error" in upload_result:
        output.append(f"❌ ERROR: {upload_result['error']}")
        error_print(upload_result['error'])
    elif upload_result.get("ok"):
        target_bot = upload_result.get("target_bot", "nexus_aaron")
        upload_status = upload_result.get("status", "uploaded")
        
        output.append(f"✅ SUCCESS: File uploaded to @{target_bot}!")
        
        # Status-specific messages
        status_messages = {
            "received": "📨 File received and being processed",
            "pending_voting": "🗳️ File is pending for voting",
            "error": "⚠️ nexus_aaron reported an issue",
            "uploaded": "📤 File uploaded successfully"
        }
        
        if upload_status in status_messages:
            output.append(f"📊 Status: {status_messages[upload_status]}")
        
        output.append("")
        
        # Format uploaded file info
        file_info = upload_result.get("uploaded_file", {})
        if file_info:
            upload_time = datetime.fromtimestamp(file_info.get("date", 0)).strftime("%Y-%m-%d %H:%M:%S")
            output.append("📤 UPLOADED FILE:")
            output.append(f"   📁 Name: {file_info.get('file_name', 'N/A')}")
            output.append(f"   📏 Size: {file_info.get('file_size_mb', 0):.2f} MB")
            output.append(f"   ⏱️ Upload Time: {file_info.get('upload_time', 0):.2f} seconds")
            output.append(f"   🚀 Speed: {file_info.get('upload_speed_mbps', 0):.2f} MB/s")
            output.append(f"   🆔 Message ID: {file_info.get('message_id', 'N/A')}")
            output.append(f"   📅 Time: {upload_time}")
            
            caption = file_info.get('caption')
            if caption:
                output.append(f"   💬 Caption: {caption}")
        
    else:
        output.append("❌ FAILED: File upload to nexus_aaron failed")
        error_print("nexus_aaron upload failed")
    
    output.append("="*70)
    
    # Print to console and log
    result_text = "\n".join(output)
    if logger:
        logger.info("Formatting nexus_aaron upload result for display")
        logger.info(result_text)

async def list_and_reply_to_nexus_aaron_message(api_id, api_hash, phone_number, session_file=SESSION_FILE, limit=10, proxy=None):
    """
    List recent research request messages from @nexus_aaron, allow user to select one, and upload a file as reply
    
    Args:
        api_id: Your Telegram API ID
        api_hash: Your Telegram API hash
        phone_number: Your phone number (not used, kept for compatibility)
        session_file: Name of the session file
        limit: Maximum number of messages to retrieve (default: 10, max: 50)
        proxy: Proxy configuration dict or file path
        
    Returns:
        Dictionary with operation result
    """
    nexus_aaron_username = "nexus_aaron"
    
    # Validate and clamp limit
    if limit < 1:
        limit = 1
    elif limit > 50:
        limit = 50
        info_print("Message limit adjusted to maximum of 50 for better interaction")
    
    info_print(f"Fetching up to {limit} recent messages from @{nexus_aaron_username} to find research requests...")
    
    # Get more messages than requested to filter for research requests only
    # We'll fetch up to 3x the limit to ensure we get enough research requests
    fetch_limit = min(limit * 3, 100)  # Cap at 100 to avoid excessive API calls
    
    # Use existing function to get messages
    messages_result = await get_latest_messages_from_bot(
        api_id, api_hash, nexus_aaron_username, session_file, fetch_limit, proxy
    )
    
    if not messages_result.get("ok"):
        error_print(f"Failed to fetch messages: {messages_result.get('error', 'Unknown error')}")
        return messages_result
    
    all_messages = messages_result.get("messages", [])
    if not all_messages:
        info_print("No messages found")
        return {"error": "No messages found in the bot"}
    
    # Filter for research request messages only
    research_requests = []
    for msg in all_messages:
        text = msg.get('text', '')
        if text.startswith('#request'):
            research_requests.append(msg)
            if len(research_requests) >= limit:
                break
    
    if not research_requests:
        info_print("No research request messages found")
        return {"error": "No research request messages found in recent messages"}
    
    # Display research request messages for user selection
    print("\n" + "="*80)
    print("RESEARCH REQUESTS FROM @nexus_aaron - SELECT ONE TO REPLY")
    print("="*80)
    print(f"Found {len(research_requests)} recent research request messages. Select one to reply to:\n")
    
    for i, msg in enumerate(research_requests, 1):
        # Parse request information
        request_info = parse_nexus_aaron_request(msg.get('text', ''))
        
        print(f"[{i}] Message ID: {msg['message_id']}")
        print(f"    📅 Date: {msg['date_formatted']}")
        print(f"    ⭐ Request Point: {request_info['request_count']}")
        print(f"    📄 Type: {request_info['pub_type']}")
        
        if request_info['doi']:
            print(f"    🔗 DOI: {request_info['doi']}")
        
        if request_info['publisher_code']:
            print(f"    📖 Publisher: {request_info['publisher_code']}")
        
        if request_info['libstc_link']:
            print(f"    🔬 LibSTC: {request_info['libstc_link']}")
        
        if request_info['worldcat_link']:
            print(f"    📚 WorldCat: {request_info['worldcat_link']}")
        
        # Additional message information
        if msg.get('has_media'):
            media_type = msg.get('media_type', 'unknown')
            print(f"    📎 Media: {media_type}")
        
        if msg.get('buttons'):
            print(f"    🔘 Interactive elements: {len(msg['buttons'])} button(s)")
        
        # Additional stats
        stats = []
        if msg.get('views'):
            stats.append(f"👁️ {msg['views']:,} views")
        if msg.get('forwards'):
            stats.append(f"🔄 {msg['forwards']:,} forwards")
        if msg.get('is_reply'):
            stats.append("↩️ Reply")
        if stats:
            print(f"    📊 Stats: {' | '.join(stats)}")
        
        print("    " + "─" * 76)
        print()
    
    # Get user selection
    while True:
        try:
            selection = get_input_with_timeout(
                f"Select a research request to reply to (1-{len(research_requests)}) or 'q' to quit: ", 
                timeout=60, 
                default='q'
            )
            
            if selection.lower() == 'q':
                info_print("Operation cancelled by user")
                return {"ok": True, "cancelled": True, "message": "Operation cancelled by user"}
            
            selected_index = int(selection) - 1
            if 0 <= selected_index < len(research_requests):
                selected_message = research_requests[selected_index]
                break
            else:
                print(f"Invalid selection. Please choose a number between 1 and {len(research_requests)}")
        except ValueError:
            print("Invalid input. Please enter a number or 'q' to quit")
    
    print(f"\n✓ Selected message {selected_message['message_id']} from {selected_message['date_formatted']}")
    
    # Show selected message details with enhanced formatting
    request_info = parse_nexus_aaron_request(selected_message.get('text', ''))
    print(f"📋 Selected Research Request [{selected_index+1}]")
    print(f"📄 Publication Type: {request_info['pub_type']}")
    if request_info['doi']:
        print(f"🔗 DOI: {request_info['doi']}")
    
    # Get file path for upload
    while True:
        file_path = get_input_with_timeout(
            "Enter the full path to the file you want to upload as reply (or 'q' to quit): ",
            timeout=120,
            default='q',
            keep_origin=True
        )
        
        if file_path.lower() == 'q':
            info_print("File upload cancelled by user")
            return {"ok": True, "cancelled": True, "message": "File upload cancelled by user"}
        
        # Expand user path and resolve relative paths
        file_path = os.path.expanduser(file_path.strip().strip('"\''))
        file_path = os.path.abspath(file_path)
        
        if os.path.exists(file_path) and os.path.isfile(file_path):
            break
        else:
            print(f"File not found: {file_path}")
            print("Please enter a valid file path or 'q' to quit")
    
    # Get file info
    file_size = os.path.getsize(file_path)
    file_size_mb = file_size / (1024 * 1024)
    file_name = os.path.basename(file_path)
    
    print(f"\n📁 File selected: {file_name}")
    print(f"📏 Size: {file_size_mb:.2f} MB")
    
    # Validate file size
    if file_size_mb > 2000:  # 2GB Telegram limit
        error_print(f"File is too large ({file_size_mb:.2f} MB). Telegram limit is 2GB.")
        return {"error": f"File too large: {file_size_mb:.2f} MB exceeds 2GB limit"}
    
    if file_size_mb > 50:  # Warn for large files
        print(f"⚠️ Large file ({file_size_mb:.2f} MB) may take time to upload")
    
    # Get optional caption for the file
    caption = get_input_with_timeout(
        "Enter an optional caption for the file (or press Enter for no caption): ",
        timeout=60,
        default='',
        keep_origin=True
    )
    
    if caption.strip():
        print(f"📝 Caption: {caption}")
    
    # Confirm upload
    confirm = get_input_with_timeout(
        f"Confirm upload '{file_name}' as reply to request [{selected_index+1}] (message {selected_message['message_id']})? [y/N]: ",
        timeout=30,
        default='n'
    )
    
    if confirm.lower() not in ['y', 'yes']:
        info_print("Upload cancelled by user")
        return {"ok": True, "cancelled": True, "message": "Upload cancelled by user"}
    
    # Now perform the actual reply upload using existing proxy and client setup logic
    proxy_config = load_proxy_config(proxy)
    if proxy and proxy_config is None:
        return {"error": "Error loading proxy configuration"}
    
    client = create_telegram_client(api_id, api_hash, session_file, proxy_config)
    
    try:
        # Check if session file exists
        if not os.path.exists(session_file):
            error_print(f"Session file not found: {session_file}")
            return {"error": "Session file not found. Run script interactively first to create session."}
        
        debug_print("Starting client for reply upload...")
        if proxy_config:
            info_print(f"Connecting through proxy: {proxy_config['type']}://{proxy_config['addr']}:{proxy_config['port']}")
        
        await client.start()
        
        # Verify we're connected
        if not await client.is_user_authorized():
            error_print("Session expired or not authorized")
            return {"error": "Session expired. Please delete the session file and run interactively to re-authenticate."}
        
        # Get the bot entity
        debug_print(f"Getting bot entity for: {nexus_aaron_username}")
        bot_entity = await client.get_entity(nexus_aaron_username)
        
        # Get the specific message to reply to
        target_message = await client.get_messages(bot_entity, ids=selected_message['message_id'])
        if not target_message:
            return {"error": f"Could not fetch target message {selected_message['message_id']}"}
        
        # Create message handler for bot responses
        handler, get_bot_reply = create_message_handler(bot_entity)
        client.on(events.NewMessage(from_users=bot_entity))(handler)
        
        # Upload progress callback
        last_progress = 0
        
        def progress_callback(current, total):
            nonlocal last_progress
            if total > 0:
                progress = int((current / total) * 100)
                if progress >= last_progress + 10:  # Update every 10%
                    info_print(f"Upload progress: {progress}% ({current / (1024*1024):.2f}/{total / (1024*1024):.2f} MB)")
                    last_progress = progress
        
        # Send file as reply
        info_print(f"Uploading '{file_name}' as reply to request [{selected_index+1}] (message {selected_message['message_id']})...")
        start_time = datetime.now()
        
        result = await client.send_file(
            bot_entity,
            file_path,
            caption=caption if caption.strip() else None,
            reply_to=target_message,  # Reply to the selected message
            progress_callback=progress_callback
        )
        
        end_time = datetime.now()
        upload_time = (end_time - start_time).total_seconds()
        upload_speed_mbps = file_size_mb / max(upload_time, 1)
        
        info_print(f"✓ File uploaded successfully as reply!")
        info_print(f"Upload time: {upload_time:.2f} seconds")
        info_print(f"Upload speed: {upload_speed_mbps:.2f} MB/s")
        info_print(f"Reply message ID: {result.id}")
        
        response = {
            "ok": True,
            "selected_message": {
                "message_id": selected_message['message_id'],
                "date": selected_message['date_formatted'],
                "request_count": request_info['request_count'],
                "text": selected_message['text'][:200] + "..." if len(selected_message.get('text', '')) > 200 else selected_message.get('text', '')
            },
            "uploaded_file": {
                "file_path": file_path,
                "file_name": file_name,
                "file_size": file_size,
                "file_size_mb": file_size_mb,
                "upload_time": upload_time,
                "upload_speed_mbps": upload_speed_mbps,
                "reply_message_id": result.id,
                "date": result.date.timestamp(),
                "caption": caption if caption.strip() else None
            }
        }
        
        debug_print("Message reply with file upload completed successfully")
        return response
        
    except Exception as e:
        error_print(f"Error in reply upload operation: {str(e)}")
        debug_print(f"Reply upload exception: {type(e).__name__}: {str(e)}")
        return {"error": f"Error in reply upload operation: {str(e)}"}
    finally:
        debug_print("Disconnecting client after reply upload operation...")
        await client.disconnect()

def format_list_and_reply_result(result):
    """Format the list and reply result in a human-readable way"""
    output = []
    output.append("\n" + "="*70)
    output.append("NEXUS AARON MESSAGE REPLY RESULT")
    output.append("="*70)
    
    if "error" in result:
        output.append(f"❌ ERROR: {result['error']}")
        error_print(result['error'])
    elif result.get("cancelled"):
        output.append(f"⚠️ CANCELLED: {result.get('message', 'Operation cancelled')}")
        info_print(result.get('message', 'Operation cancelled'))
    elif result.get("ok"):
        output.append("✅ SUCCESS: File uploaded as reply successfully!")
        output.append("")
        
        # Format selected message info
        selected_msg = result.get("selected_message", {})
        if selected_msg:
            output.append("📨 REPLIED TO MESSAGE:")
            output.append(f"   🆔 Message ID: {selected_msg.get('message_id', 'N/A')}")
            output.append(f"   📅 Date: {selected_msg.get('date', 'N/A')}")
            output.append(f"   💬 Content: {selected_msg.get('text', 'N/A')}")
            output.append("")
        
        # Format uploaded file info
        file_info = result.get("uploaded_file", {})
        if file_info:
            upload_time = datetime.fromtimestamp(file_info.get("date", 0)).strftime("%Y-%m-%d %H:%M:%S")
            output.append("📤 UPLOADED FILE REPLY:")
            output.append(f"   📁 Name: {file_info.get('file_name', 'N/A')}")
            output.append(f"   📏 Size: {file_info.get('file_size_mb', 0):.2f} MB")
            output.append(f"   ⏱️ Upload Time: {file_info.get('upload_time', 0):.2f} seconds")
            output.append(f"   🚀 Speed: {file_info.get('upload_speed_mbps', 0):.2f} MB/s")
            output.append(f"   🆔 Reply Message ID: {file_info.get('reply_message_id', 'N/A')}")
            output.append(f"   📅 Time: {upload_time}")
            
            caption = file_info.get('caption')
            if caption:
                output.append(f"   💬 Caption: {caption}")
    else:
        output.append("❌ FAILED: Operation failed")
        error_print("List and reply operation failed")
    
    output.append("="*70)
    
    # Print to console and log
    result_text = "\n".join(output)
    print(result_text)
    if logger:
        logger.info("Formatting list and reply result for display")
        logger.info(result_text)

async def check_doi_availability_on_nexus(api_id, api_hash, phone_number, bot_username, doi, session_file=SESSION_FILE, proxy=None, download=False):
    """
    Check if a DOI is available on Nexus by sending it to the bot and analyzing the response
    
    Args:
        api_id: Your Telegram API ID
        api_hash: Your Telegram API hash
        phone_number: Your phone number (not used, kept for compatibility)
        bot_username: Bot's username
        doi: DOI number to check (e.g., "10.1038/nature12373")
        session_file: Name of the session file
        proxy: Proxy configuration dict or file path
        download: If True, automatically download the paper if available (default: False)
        
    Returns:
        Dictionary with availability status and details, including download result if applicable
    """
    info_print(f"Checking DOI availability on Nexus: {doi}")
    debug_print(f"DOI to check: {doi}")
    if download:
        info_print("Auto-download enabled - will download paper if available")
    
    # Validate DOI format
    if not doi or not isinstance(doi, str):
        return {"error": "Invalid DOI: DOI must be a non-empty string"}
    
    # Clean and validate DOI format
    doi = doi.strip()
    if not re.match(r'^10\.\d+/.+', doi):
        return {"error": f"Invalid DOI format: {doi}. DOI should start with '10.' followed by digits and a slash"}
    
    # Send DOI to the bot
    debug_print(f"Sending DOI query to {bot_username}: {doi}")
    
    try:
        send_result = await send_message_to_bot(
            api_id, api_hash, phone_number, bot_username, 
            doi, session_file, proxy
        )
        
        if not send_result.get("ok"):
            error_print(f"Failed to send DOI query: {send_result.get('error', 'Unknown error')}")
            return {"error": f"Failed to send DOI query: {send_result.get('error', 'Unknown error')}"}
        
        bot_reply = send_result.get("bot_reply")
        if not bot_reply:
            error_print("No reply received from bot for DOI query")
            return {"error": "No reply received from bot for DOI query"}
        
        reply_text = bot_reply.get("text", "").lower()
        buttons = bot_reply.get("buttons", [])
        
        debug_print(f"Bot reply text (first 200 chars): {reply_text[:200]}...")
        debug_print(f"Number of buttons in reply: {len(buttons)}")
        
        # Analyze the response to determine availability
        availability_result = {
            "doi": doi,
            "available": False,
            "status": "unknown",
            "details": {},
            "raw_response": bot_reply.get("text", ""),
            "buttons": buttons,
            "message_id": bot_reply.get("message_id"),
            "download_requested": download
        }
        
        # Check for common "not found" or "no results" indicators
        not_found_indicators = [
            "no results found",
            "not found",
            "no matches",
            "nothing found",
            "0 results",
            "no books or papers found",
            "search returned no results"
        ]
        
        if any(indicator in reply_text for indicator in not_found_indicators):
            availability_result["status"] = "not_found"
            availability_result["available"] = False
            availability_result["details"]["reason"] = "DOI not found in Nexus database"
            info_print(f"DOI {doi} is NOT available on Nexus (not found)")
            debug_print("DOI marked as not found based on reply text indicators")
            return availability_result
        
        # Check for error messages
        error_indicators = [
            "error",
            "invalid",
            "malformed",
            "cannot process",
            "failed to search"
        ]
        
        if any(indicator in reply_text for indicator in error_indicators):
            availability_result["status"] = "error"
            availability_result["available"] = False
            availability_result["details"]["reason"] = "Error processing DOI query"
            error_print(f"Error processing DOI {doi}")
            debug_print("DOI query resulted in error based on reply text")
            return availability_result
        
        # If we have buttons, analyze them to determine availability
        if buttons:
            debug_print("Analyzing buttons to determine DOI availability...")
            
            # Look for callback buttons (these typically indicate results)
            callback_buttons = [btn for btn in buttons if btn.get("type") == "callback"]
            
            if callback_buttons:
                first_button = callback_buttons[0]
                button_text = first_button.get("text", "").lower()
                
                debug_print(f"First callback button text: '{button_text}'")
                
                # Check if button indicates availability
                if "request" in button_text:
                    # Paper is not available, needs to be requested
                    availability_result["status"] = "not_available_requestable"
                    availability_result["available"] = False
                    availability_result["details"]["reason"] = "Paper not available but can be requested"
                    availability_result["details"]["request_button"] = {
                        "text": first_button.get("text"),
                        "callback_data": first_button.get("callback_data") or first_button.get("data"),
                        "message_id": bot_reply.get("message_id")
                    }
                    info_print(f"DOI {doi} is NOT available on Nexus but can be requested")
                    debug_print("DOI can be requested based on button analysis")
                    
                elif any(word in button_text for word in ["download", "get", "pdf", "file"]):
                    # Paper is available for download
                    availability_result["status"] = "available"
                    availability_result["available"] = True
                    availability_result["details"]["reason"] = "Paper is available for download"
                    
                    # Try to extract file size information
                    button_size_info = extract_file_size_from_button_text(first_button.get("text", ""))
                    callback_size_info = extract_file_size_from_callback_data(first_button.get("callback_data") or first_button.get("data"))
                    
                    size_info = button_size_info or callback_size_info
                    if size_info:
                        availability_result["details"]["file_size_mb"] = size_info["size_mb"]
                        availability_result["details"]["file_size_unit"] = size_info["unit"]
                        availability_result["details"]["file_size_original"] = size_info["original_size"]
                        debug_print(f"Extracted file size: {size_info['original_size']} {size_info['unit']} ({size_info['size_mb']:.2f} MB)")
                    
                    availability_result["details"]["download_button"] = {
                        "text": first_button.get("text"),
                        "callback_data": first_button.get("callback_data") or first_button.get("data"),
                        "message_id": bot_reply.get("message_id")
                    }
                    info_print(f"DOI {doi} is AVAILABLE on Nexus for download")
                    debug_print("DOI is available for download based on button analysis")
                    
                    # Auto-download if requested
                    if download:
                        info_print(f"Auto-downloading paper for DOI: {doi}")
                        debug_print("Starting automatic download process...")
                        
                        try:
                            # Click the download button using existing function
                            button_callback_data = first_button.get("callback_data") or first_button.get("data")
                            message_id = bot_reply.get("message_id")
                            
                            debug_print(f"Clicking download button - Message ID: {message_id}, Callback: {button_callback_data}")
                            
                            click_result = await click_callback_button(
                                api_id, api_hash, phone_number, bot_username,
                                message_id, button_callback_data, session_file, proxy
                            )
                            
                            if click_result.get("ok"):
                                info_print("✓ Download button clicked successfully")
                                
                                # Wait for file and download using existing function
                                debug_print("Waiting for file preparation and download...")
                                
                                # Calculate wait time based on file size if available
                                file_size_mb = size_info.get("size_mb", 5.0) if size_info else 5.0
                                base_wait = 10
                                size_based_wait = int(file_size_mb * 3)  # 3 seconds per MB
                                total_wait = max(base_wait, size_based_wait)
                                
                                info_print(f"Waiting {total_wait} seconds for file preparation...")
                                await asyncio.sleep(total_wait)
                                
                                # Handle file download from bot reply
                                download_result = await handle_file_download_from_bot_reply(
                                    click_result.get("bot_reply"), proxy
                                )
                                
                                if download_result and download_result.get("success"):
                                    availability_result["download_result"] = {
                                        "success": True,
                                        "file_path": download_result["file_path"],
                                        "file_name": download_result["filename"],
                                        "file_size": download_result["file_size"],
                                        "file_size_mb": download_result["file_size"] / (1024*1024),
                                        "download_time": download_result["download_time"],
                                        "speed_mbps": download_result["speed_mbps"]
                                    }
                                    info_print(f"✓ Auto-download completed successfully!")
                                    info_print(f"File saved to: {download_result['file_path']}")
                                    debug_print(f"Download stats - Size: {download_result['file_size'] / (1024*1024):.2f} MB, Speed: {download_result['speed_mbps']:.2f} MB/s")
                                
                                elif download_result and not download_result.get("success"):
                                    availability_result["download_result"] = {
                                        "success": False,
                                        "error": download_result.get("error", "Unknown download error")
                                    }
                                    error_print(f"✗ Auto-download failed: {download_result.get('error', 'Unknown error')}")
                                    debug_print("File download from bot reply failed")
                                
                                else:
                                    # No file in bot reply, this might be normal for some responses
                                    availability_result["download_result"] = {
                                        "success": False,
                                        "error": "No file received from bot after clicking download button"
                                    }
                                    info_print("⚠️ No file received after clicking download button (may be normal depending on bot response)")
                                    debug_print("No file detected in bot reply after download button click")
                            
                            else:
                                availability_result["download_result"] = {
                                    "success": False,
                                    "error": f"Failed to click download button: {click_result.get('error', 'Unknown error')}"
                                }
                                error_print(f"✗ Failed to click download button: {click_result.get('error', 'Unknown error')}")
                                debug_print("Download button click failed")
                        
                        except Exception as download_error:
                            availability_result["download_result"] = {
                                "success": False,
                                "error": f"Auto-download error: {str(download_error)}"
                            }
                            error_print(f"✗ Auto-download error: {str(download_error)}")
                            debug_print(f"Auto-download exception: {type(download_error).__name__}: {str(download_error)}")
                    
                else:
                    # Unknown button type, but presence suggests some result
                    availability_result["status"] = "found_unknown"
                    availability_result["available"] = None  # Uncertain
                    availability_result["details"]["reason"] = "DOI found but availability status unclear"
                    availability_result["details"]["first_button"] = {
                        "text": first_button.get("text"),
                        "callback_data": first_button.get("callback_data") or first_button.get("data"),
                        "message_id": bot_reply.get("message_id")
                    }
                    info_print(f"DOI {doi} found but availability status unclear")
                    debug_print("DOI found but button type unclear")
            
            else:
                # Has buttons but no callback buttons (might be URL buttons)
                url_buttons = [btn for btn in buttons if btn.get("type") == "url"]
                if url_buttons:
                    availability_result["status"] = "found_external_links"
                    availability_result["available"] = False
                    availability_result["details"]["reason"] = "DOI found with external links but not directly available"
                    availability_result["details"]["external_links"] = [
                        {"text": btn.get("text"), "url": btn.get("url")} 
                        for btn in url_buttons
                    ]
                    info_print(f"DOI {doi} found with external links but not available on Nexus")
                    debug_print("DOI found with external URL buttons")
                else:
                    # Unknown button types
                    availability_result["status"] = "found_unknown_buttons"
                    availability_result["available"] = None
                    availability_result["details"]["reason"] = "DOI found with unknown button types"
                    info_print(f"DOI {doi} found but button types unclear")
                    debug_print("DOI found with unknown button types")
        
        else:
            # No buttons in response
            if len(reply_text.strip()) > 10:  # Substantial text response
                availability_result["status"] = "found_text_only"
                availability_result["available"] = None
                availability_result["details"]["reason"] = "DOI found with text response but no interactive elements"
                info_print(f"DOI {doi} found with text response but no buttons")
                debug_print("DOI query returned text but no buttons")
            else:
                availability_result["status"] = "minimal_response"
                availability_result["available"] = False
                availability_result["details"]["reason"] = "Minimal response received"
                info_print(f"DOI {doi} query returned minimal response")
                debug_print("DOI query returned minimal response")
        
        # Add search metadata
        availability_result["search_metadata"] = {
            "query_sent": doi,
            "response_length": len(reply_text),
            "button_count": len(buttons),
            "callback_button_count": len([btn for btn in buttons if btn.get("type") == "callback"]),
            "url_button_count": len([btn for btn in buttons if btn.get("type") == "url"]),
            "timestamp": datetime.now().isoformat()
        }
        
        debug_print(f"DOI availability check completed. Status: {availability_result['status']}, Available: {availability_result['available']}")
        if download and availability_result.get("download_result"):
            download_success = availability_result["download_result"].get("success", False)
            debug_print(f"Auto-download completed. Success: {download_success}")
        
        return availability_result
        
    except Exception as e:
        error_print(f"Error checking DOI availability: {str(e)}")
        debug_print(f"DOI availability check exception: {type(e).__name__}: {str(e)}")
        return {"error": f"Error checking DOI availability: {str(e)}"}

def format_doi_availability_result(availability_result):
    """Format the DOI availability result in a human-readable way"""
    output = []
    output.append("\n" + "="*70)
    output.append("DOI AVAILABILITY CHECK RESULT")
    output.append("="*70)
    
    if "error" in availability_result:
        output.append(f"❌ ERROR: {availability_result['error']}")
        error_print(availability_result['error'])
    else:
        doi = availability_result.get("doi", "Unknown")
        status = availability_result.get("status", "unknown")
        available = availability_result.get("available")
        details = availability_result.get("details", {})
        download_result = availability_result.get("download_result")
        
        output.append(f"🔍 DOI: {doi}")
        output.append("")
        
        # Status-specific formatting
        if status == "available":
            output.append("✅ STATUS: AVAILABLE on Nexus")
            output.append("📄 The paper is available for download")
            
            # File size information
            if details.get("file_size_mb"):
                size_unit = details.get("file_size_unit", "MB")
                original_size = details.get("file_size_original", details["file_size_mb"])
                output.append(f"📏 File Size: {original_size} {size_unit} ({details['file_size_mb']:.2f} MB)")
            
            # Download button info
            download_btn = details.get("download_button", {})
            if download_btn:
                output.append(f"🔘 Download Button: '{download_btn.get('text', 'N/A')}'")
                output.append(f"🆔 Message ID: {download_btn.get('message_id', 'N/A')}")
            
            # Show download result if auto-download was attempted
            if download_result:
                output.append("")
                if download_result.get("success"):
                    output.append("✅ AUTO-DOWNLOAD: SUCCESSFUL")
                    output.append(f"📁 File saved to: {download_result.get('file_path', 'N/A')}")
                    output.append(f"📋 File name: {download_result.get('file_name', 'N/A')}")
                    if download_result.get('file_size_mb'):
                        output.append(f"📏 Downloaded size: {download_result['file_size_mb']:.2f} MB")
                    if download_result.get('download_time'):
                        output.append(f"⏱️ Download time: {download_result['download_time']:.2f} seconds")
                    if download_result.get('speed_mbps'):
                        output.append(f"🚀 Download speed: {download_result['speed_mbps']:.2f} MB/s")
                else:
                    output.append("❌ AUTO-DOWNLOAD: FAILED")
                    error_msg = download_result.get('error', 'Unknown download error')
                    output.append(f"⚠️ Error: {error_msg}")
        
        elif status == "not_available_requestable":
            output.append("❌ STATUS: NOT AVAILABLE on Nexus")
            output.append("📋 The paper can be requested from the community")
            
            # Request button info
            request_btn = details.get("request_button", {})
            if request_btn:
                output.append(f"🔘 Request Button: '{request_btn.get('text', 'N/A')}'")
                output.append(f"🆔 Message ID: {request_btn.get('message_id', 'N/A')}")
        
        elif status == "not_found":
            output.append("❌ STATUS: NOT FOUND")
            output.append("🔍 The DOI was not found in the Nexus database")
        
        elif status == "found_external_links":
            output.append("⚠️ STATUS: FOUND with External Links")
            output.append("🔗 DOI found but only external links available")
            
            external_links = details.get("external_links", [])
            if external_links:
                output.append("🌐 External Links:")
                for i, link in enumerate(external_links, 1):
                    output.append(f"   {i}. {link.get('text', 'N/A')}: {link.get('url', 'N/A')}")
        
        elif status == "error":
            output.append("❌ STATUS: ERROR")
            output.append("⚠️ Error processing the DOI query")
        
        else:
            # Unknown or unclear status
            status_display = status.replace("_", " ").title()
            output.append(f"⚠️ STATUS: {status_display}")
            if available is True:
                output.append("✅ Appears to be available")
            elif available is False:
                output.append("❌ Appears to be unavailable")
            else:
                output.append("❓ Availability unclear")
        
        # Reason
        reason = details.get("reason")
        if reason:
            output.append(f"💭 Details: {reason}")
        
        output.append("")
        
        # Search metadata
        metadata = availability_result.get("search_metadata", {})
        if metadata:
            output.append("📊 SEARCH DETAILS:")
            output.append(f"   📝 Response Length: {metadata.get('response_length', 0)} characters")
            output.append(f"   🔘 Total Buttons: {metadata.get('button_count', 0)}")
            if metadata.get('callback_button_count', 0) > 0:
                output.append(f"   ⚡ Callback Buttons: {metadata.get('callback_button_count', 0)}")
            if metadata.get('url_button_count', 0) > 0:
                output.append(f"   🔗 URL Buttons: {metadata.get('url_button_count', 0)}")
            if metadata.get('timestamp'):
                output.append(f"   🕐 Checked: {metadata.get('timestamp', 'Unknown')}")
        
        # Auto-download status summary
        if availability_result.get("download_requested"):
            if not download_result:
                output.append("")
                output.append("ℹ️ Auto-download was requested but no download occurred (paper may not be available)")
    
    output.append("="*70)
    
    # Print to console and log
    result_text = "\n".join(output)
    if logger:
        logger.info("Formatting DOI availability result for display")
        logger.info(result_text)

async def batch_check_doi_availability(api_id, api_hash, phone_number, bot_username, doi_list, session_file=SESSION_FILE, proxy=None, delay=2, download=False):
    """
    Check availability of multiple DOIs on Nexus with rate limiting and optional auto-download
    
    Args:
        api_id: Your Telegram API ID
        api_hash: Your Telegram API hash
        phone_number: Your phone number (not used, kept for compatibility)
        bot_username: Bot's username
        doi_list: List of DOI strings to check
        session_file: Name of the session file
        proxy: Proxy configuration dict or file path
        delay: Delay in seconds between requests to avoid rate limiting (default: 2)
        download: If True, automatically download papers that are available (default: False)
        
    Returns:
        Dictionary with batch results including download information
    """
    if not doi_list or not isinstance(doi_list, list):
        return {"error": "DOI list must be a non-empty list"}
    
    info_print(f"Starting batch DOI availability check for {len(doi_list)} DOIs")
    if download:
        info_print("Auto-download enabled - will download available papers")
    debug_print(f"Delay between requests: {delay} seconds")
    
    batch_results = {
        "total_dois": len(doi_list),
        "processed": 0,
        "available": 0,
        "not_available": 0,
        "requestable": 0,
        "not_found": 0,
        "errors": 0,
        "downloaded": 0,
        "download_errors": 0,
        "results": [],
        "downloads": [],
        "summary": {},
        "download_enabled": download,
        "started_at": datetime.now().isoformat()
    }
    
    try:
        for i, doi in enumerate(doi_list, 1):
            info_print(f"Checking DOI {i}/{len(doi_list)}: {doi}")
            
            # Check individual DOI with download option
            result = await check_doi_availability_on_nexus(
                api_id, api_hash, phone_number, bot_username, 
                doi, session_file, proxy, download=download
            )
            
            # Add to batch results
            batch_results["results"].append(result)
            batch_results["processed"] += 1
            
            # Update counters based on result
            if "error" in result:
                batch_results["errors"] += 1
                debug_print(f"DOI {doi} resulted in error: {result['error']}")
            else:
                status = result.get("status", "unknown")
                available = result.get("available")
                
                if status == "available":
                    batch_results["available"] += 1
                    
                    # Check if download was attempted and track results
                    if download:
                        download_result = result.get("download_result")
                        if download_result:
                            if download_result.get("success"):
                                batch_results["downloaded"] += 1
                                batch_results["downloads"].append({
                                    "doi": doi,
                                    "success": True,
                                    "file_path": download_result.get("file_path"),
                                    "file_name": download_result.get("file_name"),
                                    "file_size_mb": download_result.get("file_size_mb"),
                                    "download_time": download_result.get("download_time"),
                                    "speed_mbps": download_result.get("speed_mbps")
                                })
                                info_print(f"✓ Downloaded paper for DOI {doi}")
                            else:
                                batch_results["download_errors"] += 1
                                batch_results["downloads"].append({
                                    "doi": doi,
                                    "success": False,
                                    "error": download_result.get("error", "Unknown download error")
                                })
                                info_print(f"✗ Failed to download paper for DOI {doi}")
                        else:
                            # Available but no download attempted (shouldn't happen if download=True)
                            debug_print(f"DOI {doi} available but no download result found")
                            
                elif status == "not_available_requestable":
                    batch_results["requestable"] += 1
                    batch_results["not_available"] += 1
                elif status == "not_found":
                    batch_results["not_found"] += 1
                    batch_results["not_available"] += 1
                else:
                    batch_results["not_available"] += 1
                
                debug_print(f"DOI {doi} status: {status}, available: {available}")
            
            # Rate limiting delay (except for last request)
            if i < len(doi_list):
                debug_print(f"Waiting {delay} seconds before next request...")
                await asyncio.sleep(delay)
        
        # Generate summary
        batch_results["completed_at"] = datetime.now().isoformat()
        batch_results["summary"] = {
            "available_count": batch_results["available"],
            "requestable_count": batch_results["requestable"],
            "not_found_count": batch_results["not_found"],
            "error_count": batch_results["errors"],
            "success_rate": round((batch_results["processed"] - batch_results["errors"]) / batch_results["total_dois"] * 100, 2),
            "availability_rate": round(batch_results["available"] / batch_results["total_dois"] * 100, 2) if batch_results["total_dois"] > 0 else 0
        }
        
        # Add download summary if download was enabled
        if download:
            batch_results["summary"]["downloaded_count"] = batch_results["downloaded"]
            batch_results["summary"]["download_errors_count"] = batch_results["download_errors"]
            batch_results["summary"]["download_success_rate"] = round(batch_results["downloaded"] / batch_results["available"] * 100, 2) if batch_results["available"] > 0 else 0
            
            # Calculate total download statistics
            successful_downloads = [d for d in batch_results["downloads"] if d.get("success")]
            if successful_downloads:
                total_size_mb = sum(d.get("file_size_mb", 0) for d in successful_downloads)
                total_time = sum(d.get("download_time", 0) for d in successful_downloads)
                avg_speed = sum(d.get("speed_mbps", 0) for d in successful_downloads) / len(successful_downloads)
                
                batch_results["summary"]["total_downloaded_mb"] = round(total_size_mb, 2)
                batch_results["summary"]["total_download_time"] = round(total_time, 2)
                batch_results["summary"]["average_download_speed_mbps"] = round(avg_speed, 2)
        
        info_print(f"Batch DOI check completed: {batch_results['available']} available, {batch_results['requestable']} requestable, {batch_results['not_found']} not found, {batch_results['errors']} errors")
        if download:
            info_print(f"Download results: {batch_results['downloaded']} successful, {batch_results['download_errors']} failed")
        
        return batch_results
        
    except Exception as e:
        error_print(f"Error in batch DOI availability check: {str(e)}")
        debug_print(f"Batch check exception: {type(e).__name__}: {str(e)}")
        batch_results["error"] = f"Batch processing error: {str(e)}"
        batch_results["completed_at"] = datetime.now().isoformat()
        return batch_results

def format_batch_doi_results(batch_results):
    """Format the batch DOI results in a human-readable way"""
    output = []
    output.append("\n" + "="*80)
    output.append("BATCH DOI AVAILABILITY CHECK RESULTS")
    output.append("="*80)
    
    if "error" in batch_results:
        output.append(f"❌ BATCH ERROR: {batch_results['error']}")
        error_print(batch_results['error'])
        return "\n".join(output)
    
    # Summary statistics
    total = batch_results.get("total_dois", 0)
    processed = batch_results.get("processed", 0)
    available = batch_results.get("available", 0)
    requestable = batch_results.get("requestable", 0)
    not_found = batch_results.get("not_found", 0)
    errors = batch_results.get("errors", 0)
    download_enabled = batch_results.get("download_enabled", False)
    
    output.append(f"📊 SUMMARY: Processed {processed}/{total} DOIs")
    if download_enabled:
        downloaded = batch_results.get("downloaded", 0)
        download_errors = batch_results.get("download_errors", 0)
        output.append(f"📥 Download Mode: ENABLED ({downloaded} successful, {download_errors} failed)")
    output.append("")
    
    output.append(f"✅ Available on Nexus: {available} ({available/total*100:.1f}%)" if total > 0 else "✅ Available on Nexus: 0")
    output.append(f"📋 Requestable: {requestable} ({requestable/total*100:.1f}%)" if total > 0 else "📋 Requestable: 0")
    output.append(f"❌ Not Found: {not_found} ({not_found/total*100:.1f}%)" if total > 0 else "❌ Not Found: 0")
    output.append(f"⚠️ Errors: {errors} ({errors/total*100:.1f}%)" if total > 0 else "⚠️ Errors: 0")
    
    summary = batch_results.get("summary", {})
    if summary:
        output.append("")
        output.append(f"📈 Success Rate: {summary.get('success_rate', 0):.1f}%")
        output.append(f"📊 Availability Rate: {summary.get('availability_rate', 0):.1f}%")
        
        # Download statistics
        if download_enabled and summary.get("downloaded_count", 0) > 0:
            output.append(f"📥 Download Success Rate: {summary.get('download_success_rate', 0):.1f}%")
            output.append(f"💾 Total Downloaded: {summary.get('total_downloaded_mb', 0):.2f} MB")
            output.append(f"⏱️ Total Download Time: {summary.get('total_download_time', 0):.1f} seconds")
            output.append(f"🚀 Average Download Speed: {summary.get('average_download_speed_mbps', 0):.2f} MB/s")
    
    # Timing information
    started_at = batch_results.get("started_at")
    completed_at = batch_results.get("completed_at")
    if started_at and completed_at:
        try:
            start_time = datetime.fromisoformat(started_at)
            end_time = datetime.fromisoformat(completed_at)
            duration = (end_time - start_time).total_seconds()
            output.append(f"⏱️ Total Time: {duration:.1f} seconds")
            if processed > 0:
                output.append(f"🚀 Average Time per DOI: {duration/processed:.1f} seconds")
        except:
            debug_print("Could not calculate timing information")
    
    # Download details section
    if download_enabled:
        downloads = batch_results.get("downloads", [])
        successful_downloads = [d for d in downloads if d.get("success")]
        failed_downloads = [d for d in downloads if not d.get("success")]
        
        if successful_downloads:
            output.append("")
            output.append("📥 SUCCESSFUL DOWNLOADS:")
            output.append("─" * 50)
            for i, download in enumerate(successful_downloads, 1):
                output.append(f"{i:2d}. ✅ {download.get('doi', 'Unknown DOI')}")
                output.append(f"    📁 File: {download.get('file_name', 'N/A')}")
                output.append(f"    📏 Size: {download.get('file_size_mb', 0):.2f} MB")
                output.append(f"    ⏱️ Time: {download.get('download_time', 0):.2f}s")
                output.append(f"    🚀 Speed: {download.get('speed_mbps', 0):.2f} MB/s")
                output.append(f"    💾 Path: {download.get('file_path', 'N/A')}")
                output.append("")
        
        if failed_downloads:
            output.append("")
            output.append("❌ FAILED DOWNLOADS:")
            output.append("─" * 50)
            for i, download in enumerate(failed_downloads, 1):
                output.append(f"{i:2d}. ❌ {download.get('doi', 'Unknown DOI')}")
                output.append(f"    ⚠️ Error: {download.get('error', 'Unknown error')}")
                output.append("")
    
    output.append("")
    output.append("📋 DETAILED RESULTS:")
    output.append("─" * 80)
    
    # Individual results
    results = batch_results.get("results", [])
    for i, result in enumerate(results, 1):
        if "error" in result:
            output.append(f"{i:2d}. ❌ ERROR: {result.get('doi', 'Unknown DOI')}")
            output.append(f"    {result['error']}")
        else:
            doi = result.get("doi", "Unknown")
            status = result.get("status", "unknown")
            available = result.get("available")
            
            # Status emoji and text
            if status == "available":
                status_emoji = "✅"
                status_text = "AVAILABLE"
                
                # Add download status if enabled
                if download_enabled:
                    download_result = result.get("download_result")
                    if download_result and download_result.get("success"):
                        status_text += " + DOWNLOADED"
                    elif download_result and not download_result.get("success"):
                        status_text += " + DOWNLOAD FAILED"
                        
            elif status == "not_available_requestable":
                status_emoji = "📋"
                status_text = "REQUESTABLE"
            elif status == "not_found":
                status_emoji = "❌"
                status_text = "NOT FOUND"
            else:
                status_emoji = "⚠️"
                status_text = status.replace("_", " ").upper()
            
            output.append(f"{i:2d}. {status_emoji} {status_text}: {doi}")
            
            # Additional details
            details = result.get("details", {})
            if details.get("file_size_mb"):
                size_unit = details.get("file_size_unit", "MB")
                original_size = details.get("file_size_original", details["file_size_mb"])
                output.append(f"    📏 Size: {original_size} {size_unit}")
            
            # Download details
            if download_enabled and result.get("download_result"):
                download_result = result["download_result"]
                if download_result.get("success"):
                    output.append(f"    📥 Downloaded: {download_result.get('file_name', 'N/A')}")
                    output.append(f"    💾 Saved to: {download_result.get('file_path', 'N/A')}")
                else:
                    output.append(f"    ❌ Download failed: {download_result.get('error', 'Unknown error')}")
            
            reason = details.get("reason")
            if reason and len(reason) < 100:  # Only show short reasons
                output.append(f"    💭 {reason}")
        
        output.append("")
    
    output.append("="*80)
    
    # Print to console and log
    result_text = "\n".join(output)
    if logger:
        logger.info("Formatting batch DOI results for display")
        logger.info(result_text)

async def download_from_nexus_bot(doi, download_dir=None, bot_username=None):
    """
    Download a paper from Nexus based on DOI
    
    Args:
        doi: DOI string to search and download (e.g., "10.1038/nature12373")
        download_dir: Target directory to save the file (optional, uses default if None)
        bot_username: Bot username to use (optional, uses global BOT_USERNAME if None)
        
    Returns:
        Dictionary with download result and file information
    """
    if not doi or not isinstance(doi, str):
        return {"success": False, "error": "Invalid DOI: DOI must be a non-empty string"}
    
    # Clean and validate DOI format
    doi = doi.strip()
    if not re.match(r'^10\.\d+/.+', doi):
        return {"success": False, "error": f"Invalid DOI format: {doi}. DOI should start with '10.' followed by digits and a slash"}
    
    # Use global bot username if not specified
    target_bot = bot_username or BOT_USERNAME
    
    info_print(f"Downloading from Nexus - DOI: {doi}")
    debug_print(f"Target bot: {target_bot}")
    debug_print(f"Download directory: {download_dir or 'default'}")
    
    try:
        # Step 1: Check DOI availability with auto-download enabled
        info_print("Step 1: Checking DOI availability on Nexus...")
        
        # Load proxy configuration if available
        proxy_to_use = None
        if os.path.exists(DEFAULT_PROXY_FILE):
            proxy_to_use = DEFAULT_PROXY_FILE
            debug_print(f"Using proxy configuration: {DEFAULT_PROXY_FILE}")
        
        availability_result = await check_doi_availability_on_nexus(
            TG_API_ID, TG_API_HASH, PHONE, target_bot, 
            doi, SESSION_FILE, proxy_to_use, download=True
        )
        
        if "error" in availability_result:
            error_print(f"DOI availability check failed: {availability_result['error']}")
            return {
                "success": False,
                "error": f"DOI availability check failed: {availability_result['error']}",
                "doi": doi
            }
        
        # Step 2: Analyze availability result
        status = availability_result.get("status", "unknown")
        available = availability_result.get("available", False)
        
        debug_print(f"DOI status: {status}, Available: {available}")
        
        if not available:
            if status == "not_available_requestable":
                info_print("Paper is not available on Nexus but can be requested")
                return {
                    "success": False,
                    "error": "Paper not available on Nexus - can be requested from community",
                    "doi": doi,
                    "status": "requestable",
                    "request_info": availability_result.get("details", {}).get("request_button")
                }
            elif status == "not_found":
                info_print("DOI not found in Nexus database")
                return {
                    "success": False,
                    "error": "DOI not found in Nexus database",
                    "doi": doi,
                    "status": "not_found"
                }
            else:
                info_print(f"Paper not available - status: {status}")
                return {
                    "success": False,
                    "error": f"Paper not available - status: {status}",
                    "doi": doi,
                    "status": status
                }
        
        # Step 3: Check if auto-download was successful
        download_result = availability_result.get("download_result")
        
        if not download_result:
            error_print("Paper is available but no download was attempted")
            return {
                "success": False,
                "error": "Paper is available but download was not attempted",
                "doi": doi,
                "status": "available_no_download"
            }
        
        if not download_result.get("success"):
            error_print(f"Download failed: {download_result.get('error', 'Unknown download error')}")
            return {
                "success": False,
                "error": f"Download failed: {download_result.get('error', 'Unknown download error')}",
                "doi": doi,
                "status": "download_failed"
            }
        
        # Step 4: Get downloaded file information
        downloaded_file_path = download_result.get("file_path")
        file_name = download_result.get("file_name") or download_result.get("filename")
        file_size = download_result.get("file_size", 0)
        file_size_mb = file_size / (1024 * 1024) if file_size else 0
        
        if not downloaded_file_path or not os.path.exists(downloaded_file_path):
            error_print("Downloaded file not found on disk")
            return {
                "success": False,
                "error": "Downloaded file not found on disk",
                "doi": doi,
                "status": "file_missing"
            }
        
        info_print(f"✓ File downloaded successfully: {file_name}")
        info_print(f"File size: {file_size_mb:.2f} MB")
        debug_print(f"Downloaded to: {downloaded_file_path}")
        
        # Step 5: Move file to specified directory if requested
        final_file_path = downloaded_file_path
        
        if download_dir:
            # Expand and create target directory
            target_dir = os.path.expanduser(download_dir.strip())
            target_dir = os.path.abspath(target_dir)
            
            debug_print(f"Target directory specified: {target_dir}")
            
            try:
                os.makedirs(target_dir, exist_ok=True)
                debug_print(f"Target directory created/verified: {target_dir}")
                
                # Generate target file path
                target_file_path = os.path.join(target_dir, file_name)
                
                # Handle file name conflicts
                if os.path.exists(target_file_path):
                    base_name, ext = os.path.splitext(file_name)
                    counter = 1
                    while os.path.exists(target_file_path):
                        new_name = f"{base_name}_{counter}{ext}"
                        target_file_path = os.path.join(target_dir, new_name)
                        counter += 1
                    
                    info_print(f"File name conflict resolved: {os.path.basename(target_file_path)}")
                    debug_print(f"Original file exists, using: {target_file_path}")
                
                # Move file to target directory
                debug_print(f"Moving file from {downloaded_file_path} to {target_file_path}")
                
                shutil.move(downloaded_file_path, target_file_path)
                
                final_file_path = target_file_path
                info_print(f"✓ File moved to: {target_file_path}")
                debug_print("File move operation completed successfully")
                
            except Exception as move_error:
                error_print(f"Warning: Could not move file to specified directory: {str(move_error)}")
                debug_print(f"File move exception: {type(move_error).__name__}: {str(move_error)}")
                info_print(f"File remains at: {downloaded_file_path}")
                # Don't fail the entire operation, just use original location
        
        # Step 6: Return success result
        result = {
            "success": True,
            "doi": doi,
            "file_path": final_file_path,
            "file_name": os.path.basename(final_file_path),
            "file_size": file_size,
            "file_size_mb": file_size_mb,
            "download_time": download_result.get("download_time", 0),
            "speed_mbps": download_result.get("speed_mbps", 0),
            "original_download_path": downloaded_file_path,
            "moved_to_target_dir": download_dir is not None and final_file_path != downloaded_file_path,
            "target_directory": download_dir,
            "status": "downloaded"
        }
        
        # Add file size information from availability check if available
        details = availability_result.get("details", {})
        if details.get("file_size_mb"):
            result["expected_file_size_mb"] = details["file_size_mb"]
            result["file_size_unit"] = details.get("file_size_unit", "MB")
        
        info_print(f"✓ Download completed successfully!")
        info_print(f"Final location: {final_file_path}")
        debug_print(f"Download result: {result}")
        
        return result
        
    except Exception as e:
        error_print(f"Error in download_from_nexus: {str(e)}")
        debug_print(f"Download function exception: {type(e).__name__}: {str(e)}")
        
        return {
            "success": False,
            "error": f"Download operation failed: {str(e)}",
            "doi": doi,
            "status": "error"
        }

def format_download_from_nexus_bot_result(download_result):
    """Format the download result in a human-readable way"""
    output = []
    output.append("\n" + "="*70)
    output.append("NEXUS DOWNLOAD RESULT")
    output.append("="*70)
    
    if not download_result.get("success"):
        doi = download_result.get("doi", "Unknown")
        error_msg = download_result.get("error", "Unknown error")
        status = download_result.get("status", "unknown")
        
        output.append(f"❌ DOWNLOAD FAILED: {doi}")
        output.append(f"⚠️ Error: {error_msg}")
        output.append(f"📊 Status: {status}")
        
        # Provide specific guidance based on status
        if status == "requestable":
            output.append("")
            output.append("💡 SUGGESTION:")
            output.append("   The paper is not available on Nexus but can be requested.")
            output.append("   Use the request feature to ask the community to upload it.")
            
            request_info = download_result.get("request_info")
            if request_info:
                output.append(f"   Request button: '{request_info.get('text', 'N/A')}'")
                
        elif status == "not_found":
            output.append("")
            output.append("💡 SUGGESTION:")
            output.append("   The DOI was not found in the Nexus database.")
            output.append("   Please verify the DOI is correct or try a different search.")
            
        elif status == "download_failed":
            output.append("")
            output.append("💡 SUGGESTION:")
            output.append("   The paper is available but download failed.")
            output.append("   Try running the download again or check your connection.")
        
        error_print(f"Download failed for DOI {doi}: {error_msg}")
    else:
        doi = download_result.get("doi", "Unknown")
        file_path = download_result.get("file_path", "N/A")
        file_name = download_result.get("file_name", "N/A")
        file_size_mb = download_result.get("file_size_mb", 0)
        download_time = download_result.get("download_time", 0)
        speed_mbps = download_result.get("speed_mbps", 0)
        
        output.append(f"✅ DOWNLOAD SUCCESSFUL: {doi}")
        output.append("")
        output.append("📄 FILE INFORMATION:")
        output.append(f"   📁 File Name: {file_name}")
        output.append(f"   📏 File Size: {file_size_mb:.2f} MB")
        output.append(f"   💾 Location: {file_path}")
        
        # File movement information
        if download_result.get("moved_to_target_dir"):
            original_path = download_result.get("original_download_path", "N/A")
            target_dir = download_result.get("target_directory", "N/A")
            output.append("")
            output.append("📦 FILE MOVEMENT:")
            output.append(f"   📤 From: {original_path}")
            output.append(f"   📥 To: {target_dir}")
            output.append("   ✅ Successfully moved to target directory")
        
        info_print(f"✓ Successfully downloaded paper for DOI {doi}")
        info_print(f"File saved to: {file_path}")
    
    output.append("="*70)
    
    # Print to console and log
    result_text = "\n".join(output)
    if logger:
        logger.info("Formatting download result for display")
        logger.info(result_text)

async def request_paper_by_doi(api_id, api_hash, phone_number, bot_username, doi, session_file=SESSION_FILE, proxy=None):
    """
    Request a paper from Nexus by DOI.
    This will send the DOI to the bot, detect if a request is needed, and click the request button if available.

    Args:
        api_id: Telegram API ID
        api_hash: Telegram API hash
        phone_number: Your phone number (not used, kept for compatibility)
        bot_username: Bot's username
        doi: DOI string to request (e.g., "10.1038/nature12373")
        session_file: Session file name
        proxy: Proxy configuration dict or file path

    Returns:
        dict: {
            "ok": True if request sent, False or "error" otherwise,
            "doi": <doi>,
            "request_sent": True/False,
            "details": ...,
        }
    """
    info_print(f"Requesting paper by DOI: {doi}")
    # Step 1: Send DOI to the bot and get reply
    send_result = await send_message_to_bot(
        api_id, api_hash, phone_number, bot_username, doi, session_file, proxy
    )
    if not send_result.get("ok"):
        return {"error": f"Failed to send DOI to bot: {send_result.get('error', 'Unknown error')}", "doi": doi}

    bot_reply = send_result.get("bot_reply")
    if not bot_reply or not bot_reply.get("buttons"):
        return {"error": "No reply or no buttons found in bot response", "doi": doi}

    # Step 2: Find the request button
    request_button = None
    for btn in bot_reply.get("buttons", []):
        if btn.get("type") == "callback" and "request" in btn.get("text", "").lower():
            request_button = btn
            break

    if not request_button:
        return {"ok": False, "doi": doi, "request_sent": False, "details": "No request button found. Paper may already be available or not requestable."}

    # Step 3: Click the request button
    message_id = bot_reply.get("message_id")
    callback_data = request_button.get("callback_data") or request_button.get("data")
    click_result = await click_callback_button(
        api_id, api_hash, phone_number, bot_username, message_id, callback_data, session_file, proxy
    )

    if click_result.get("ok"):
        info_print("Paper request sent successfully.")
        return {
            "ok": True,
            "doi": doi,
            "request_sent": True,
            "details": click_result
        }
    else:
        return {
            "ok": False,
            "doi": doi,
            "request_sent": False,
            "details": click_result.get("error", "Unknown error")
        }

async def batch_request_papers_by_doi(api_id, api_hash, phone_number, bot_username, doi_list, session_file=SESSION_FILE, proxy=None, delay=2):
    """
    Request multiple papers from Nexus by DOI.
    For each DOI, sends the DOI to the bot, detects if a request is needed, and clicks the request button if available.

    Args:
        api_id: Telegram API ID
        api_hash: Telegram API hash
        phone_number: Your phone number (not used, kept for compatibility)
        bot_username: Bot's username
        doi_list: List of DOI strings to request
        session_file: Session file name
        proxy: Proxy configuration dict or file path
        delay: Delay in seconds between requests (default: 2)

    Returns:
        dict: {
            "total": int,
            "requested": int,
            "skipped": int,
            "errors": int,
            "results": list of per-DOI results
        }
    """
    if not doi_list or not isinstance(doi_list, list):
        return {"error": "DOI list must be a non-empty list"}

    info_print(f"Starting batch paper request for {len(doi_list)} DOIs")
    results = []
    requested = 0
    skipped = 0
    errors = 0

    for i, doi in enumerate(doi_list, 1):
        info_print(f"Requesting DOI {i}/{len(doi_list)}: {doi}")
        try:
            result = await request_paper_by_doi(
                api_id, api_hash, phone_number, bot_username, doi, session_file, proxy
            )
            results.append(result)
            if result.get("ok"):
                requested += 1
                info_print(f"✓ Requested paper for DOI: {doi}")
            elif result.get("request_sent") is False:
                skipped += 1
                info_print(f"Skipped DOI (no request needed or possible): {doi}")
            else:
                errors += 1
                error_print(f"Error requesting DOI {doi}: {result.get('error', result.get('details', 'Unknown error'))}")
        except Exception as e:
            errors += 1
            error_print(f"Exception requesting DOI {doi}: {str(e)}")
            results.append({"doi": doi, "error": str(e)})
        if i < len(doi_list):
            await asyncio.sleep(delay)

    summary = {
        "total": len(doi_list),
        "requested": requested,
        "skipped": skipped,
        "errors": errors,
        "results": results
    }
    info_print(f"Batch request completed: {requested} requested, {skipped} skipped, {errors} errors")
    return summary

def print_default_paths():
    """Print all default file and directory paths used by the script."""
    print("\n" + "="*50)
    print("DEFAULT FILE AND DIRECTORY PATHS")
    print("="*50)
    print(f"Session file:         {SESSION_FILE}")
    print(f"Credentials file:     {CREDENTIALS_FILE}")
    print(f"Proxy config file:    {DEFAULT_PROXY_FILE}")
    print(f"Proxy list file:      {DEFAULT_PROXY_FILE.replace('.json', '_list.json')}")
    print(f"Log file:             {DEFAULT_LOG_FILE}")
    print(f"Download directory:   {DEFAULT_DOWNLOAD_DIR}")
    print("="*50 + "\n")

async def main():
    global TG_API_ID, TG_API_HASH, PHONE, BOT_USERNAME

    # Get the parent package name from the module's __name__
    parent_package = __name__.split('.')[0] if '.' in __name__ else None

    if parent_package is None:
        program_name = 'nexus'
    elif '_' in parent_package:
        # If the parent package has an underscore, strip it
        parent_package = parent_package[:parent_package.index('_')]
        program_name = f"{parent_package} nexus"

    # Parse command line arguments using argparse
    parser = argparse.ArgumentParser(
        prog=program_name,
        description='Interact with Telegram bots, especially Nexus scientific paper bot',
        epilog='''
Examples:
  %(prog)s --search "artificial intelligence"
    Search for papers on artificial intelligence
  
  %(prog)s --check-doi 10.1038/nature12373
    Check if a specific DOI is available on Nexus
  
  %(prog)s --check-doi 10.1038/nature12373 --download
    Check DOI availability and auto-download if available
  
  %(prog)s --check-doi dois.txt --download
    Check multiple DOIs from file and download available papers

  %(prog)s --check-doi "10.1038/nature12373,10.1126/science.abc123"
    Check multiple DOIs by comma-separated list

  %(prog)s --check-doi "10.1038/nature12373 10.1126/science.abc123"
    Check multiple DOIs by space-separated list
  
  %(prog)s --user-info
    Get your Nexus user profile information
  
  %(prog)s --fetch-nexus-aaron 20
    Fetch 20 recent messages from @nexus_aaron bot
  
  %(prog)s --upload-to-nexus-aaron paper.pdf --upload-message "New research paper"
    Upload a file to @nexus_aaron with optional message
  
  %(prog)s --solve-requests 5
    Help solve research requests from @nexus_aaron
  
  %(prog)s --create-session
    Create new Telegram session interactively
  
  %(prog)s --test-connection --proxy proxy.json
    Test connection with proxy configuration
  
  %(prog)s --clear-proxy --clear-credentials
    Clean up configuration files

  %(prog)s --request-doi 10.1038/nature12373
    Request a paper by DOI if not available

  %(prog)s --request-doi "10.1038/nature12373,10.1126/science.abc123"
    Request multiple papers by comma-separated DOIs

  %(prog)s --request-doi "10.1038/nature12373 10.1126/science.abc123"
    Request multiple papers by space-separated DOIs

  %(prog)s --request-doi dois.txt
    Request papers by DOIs listed in a file (one per line)
        ''',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('--create-session', action='store_true',
                       help='Create a new session file interactively')
    parser.add_argument('--credentials', type=str,
                       help='Path to credentials JSON file containing API credentials. '
                            'Example file content: {"tg_api_id": "12345678", "tg_api_hash": "abcd1234efgh5678", '
                            '"phone": "+1234567890", "bot_username": "SciNexBot"}')
    parser.add_argument('--search', type=str,
                       default="",
                       help='Search query to send to the bot')
    parser.add_argument('--search-limit', type=int, default=None,
                       help='Limit the number of search results returned when using --search')
    parser.add_argument('--bot', type=str,
                       help='Bot username to interact with (overrides default)')
    parser.add_argument('--verbose', action='store_true',
                       help='Enable verbose output for debugging')
    parser.add_argument('--log', type=str, nargs='?', const=DEFAULT_LOG_FILE,
                       help=f'Save output to log file (default: {DEFAULT_LOG_FILE})')
    parser.add_argument('--proxy', type=str, nargs='?', const=DEFAULT_PROXY_FILE,
                       help=f'Path to proxy configuration JSON file (default: {DEFAULT_PROXY_FILE}). '
                            'Example file content: {"type": "http", "addr": "127.0.0.1", "port": 8080} '
                            'or {"type": "socks5", "addr": "127.0.0.1", "port": 1080, "username": "user", "password": "pass"}')
    parser.add_argument('--no-proxy', action='store_true',
                       help='Disable proxy usage and connect directly')
    parser.add_argument('--user-info', action='store_true',
                       help='Get and display user profile information from Nexus bot')
    parser.add_argument('--clear-proxy', action='store_true',
                       help='Clear proxy configuration files (delete default proxy files)')
    parser.add_argument('--clear-credentials', action='store_true',
                       help='Clear credentials configuration file (delete default credentials file)')
    parser.add_argument('--fetch-nexus-aaron', type=int, nargs='?', const=10, metavar='LIMIT',
                       help='Fetch recent messages from @nexus_aaron bot (default: 10, max: 100)')
    parser.add_argument('--test-connection', action='store_true',
                       help='Test connection to Telegram servers and proxy (if configured)')
    parser.add_argument('--upload-to-nexus-aaron', type=str, metavar='FILE_PATH',
                       help='Upload a file to @nexus_aaron bot')
    parser.add_argument('--upload-message', type=str, default="",
                       help='Optional message to send with the uploaded file (use with --upload-to-nexus-aaron)')
    parser.add_argument('--solve-requests', type=int, nargs='?', const=10, metavar='LIMIT',
                       help='Reply to research requests from @nexus_aaron bot (default: 10, max: 50)')
    parser.add_argument('--check-doi', type=str, metavar='DOI_OR_LIST_OR_FILE',
                       help='Check if a paper with the specified DOI(s) is available on Nexus. '
                            'Accepts a single DOI, a comma/space separated list, or a file path (one DOI per line).')
    parser.add_argument('--batch-delay', type=float, default=2.0, metavar='SECONDS',
                       help='Delay between batch DOI checks to avoid rate limiting (default: 2.0 seconds)')
    parser.add_argument('--download', action='store_true',
                       help='Automatically download papers if available (use with --check-doi)')
    parser.add_argument('--request-doi', type=str, metavar='DOI_OR_LIST_OR_FILE',
                       help='Request a paper by DOI, a comma/space separated list of DOIs, or a file containing DOIs (one per line)')
    parser.add_argument(
        "--print-default",
        action="store_true",
        help="Print all default paths and configuration file locations used by the script"
    )
    args = parser.parse_args()

    # Argument conflict checks
    if args.proxy and args.no_proxy:
        error_print("--proxy and --no-proxy cannot be specified at the same time.")
        return
    if args.proxy and args.clear_proxy:
        error_print("--proxy and --clear-proxy cannot be specified at the same time.")
        return

    # Setup logging
    setup_logging(args.log, args.verbose)
    
    if args.verbose:
        info_print("Verbose mode enabled")
    if args.log:
        info_print(f"Logging enabled to: {args.log}")
    
    debug_print(f"Platform: {platform.system()}")
    debug_print(f"Session file: {SESSION_FILE}")
    debug_print(f"Default log file: {DEFAULT_LOG_FILE}")

    # Handle --print-default before anything else
    if args.print_default:
        print_default_paths()
        sys.exit(0)
    
    # Handle clear-proxy and clear-credentials commands
    if args.clear_proxy or args.clear_credentials:
        # Only allow these options if no other actionable arguments are specified
        actionable_args = [
            args.create_session, args.search, args.user_info, args.check_doi, args.request_doi,
            args.fetch_nexus_aaron, args.upload_to_nexus_aaron, args.solve_requests,
            args.test_connection
        ]
        if any(actionable_args):
            error_print("--clear-proxy and --clear-credentials can only be used alone or together, not with other options.")
            return

        if args.clear_proxy:
            info_print("Clearing proxy configuration files...")
            proxy_files_to_clear = [
                DEFAULT_PROXY_FILE,
                DEFAULT_PROXY_FILE.replace('.json', '_list.json')
            ]
            cleared_count = 0
            for proxy_file in proxy_files_to_clear:
                if os.path.exists(proxy_file):
                    try:
                        os.remove(proxy_file)
                        info_print(f"✓ Removed proxy file: {proxy_file}")
                        cleared_count += 1
                    except Exception as e:
                        error_print(f"✗ Failed to remove proxy file {proxy_file}: {e}")
                else:
                    debug_print(f"Proxy file does not exist: {proxy_file}")
            if cleared_count > 0:
                info_print(f"Successfully cleared {cleared_count} proxy configuration files")
            else:
                info_print("No proxy configuration files found to clear")

        if args.clear_credentials:
            info_print("Clearing credentials configuration file...")
            if os.path.exists(CREDENTIALS_FILE):
                try:
                    os.remove(CREDENTIALS_FILE)
                    info_print(f"✓ Removed credentials file: {CREDENTIALS_FILE}")
                    info_print("Credentials cleared successfully")
                except Exception as e:
                    error_print(f"✗ Failed to remove credentials file: {e}")
            else:
                info_print("No credentials file found to clear")
        return
    
    # Load credentials if specified, otherwise try default location
    if args.credentials:
        if not await load_credentials_from_file(args.credentials):
            return
        # Quit after loading credentials if no other actionable argument is specified
        actionable_args = [
            args.create_session, args.search, args.user_info, args.check_doi, args.request_doi,
            args.fetch_nexus_aaron, args.upload_to_nexus_aaron, args.solve_requests,
            args.test_connection, args.clear_proxy, args.clear_credentials
        ]
        if not any(actionable_args):
            info_print("Credentials loaded successfully.")
            return
    else:
        # Try to load from default location
        if os.path.exists(CREDENTIALS_FILE):
            info_print(f"No credentials file for `nexus` module specified, trying default location: {CREDENTIALS_FILE}")
            if not await load_credentials_from_file(CREDENTIALS_FILE):
                debug_print("Failed to load credentials from default location")
            else:
                # Quit after loading credentials if no other actionable argument is specified
                actionable_args = [
                    args.create_session, args.search, args.user_info, args.check_doi, args.request_doi,
                    args.fetch_nexus_aaron, args.upload_to_nexus_aaron, args.solve_requests,
                    args.test_connection, args.clear_proxy, args.clear_credentials
                ]
                if not any(actionable_args):
                    info_print("Credentials loaded successfully.")
                    return
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
        await create_session(TG_API_ID, TG_API_HASH, PHONE, SESSION_FILE)
        return
    
    # Determine proxy usage
    proxy_to_use = None
    if args.no_proxy:
        info_print("Proxy disabled by --no-proxy flag")
        proxy_to_use = None
    elif args.proxy:
        # Use the proxy config file specified by --proxy
        proxy_to_use = args.proxy
        info_print(f"Using proxy configuration file specified by --proxy: {proxy_to_use}")
    else:
        # Decide whether to use proxy
        proxy_to_use = await decide_proxy_usage(TG_API_ID, TG_API_HASH, PHONE, SESSION_FILE, DEFAULT_PROXY_FILE)
        if proxy_to_use is False:  # Explicitly check for False (error case)
            return
    
    # Handle test-connection command
    if args.test_connection:
        info_print("Testing connection to Telegram servers...")
        await test_telegram_connection(TG_API_ID, TG_API_HASH, PHONE, SESSION_FILE, proxy_to_use)
        return

    # Handle request-doi command (updated to support single DOI, list, or file)
    if args.request_doi:
        input_value = args.request_doi.strip()
        doi_list = []

        # Check if input is a file path
        if os.path.isfile(input_value):
            info_print(f"Reading DOIs from file: {input_value}")
            try:
                doi_list = getpapers.extract_dois_from_file(input_value)
                if not doi_list:
                    info_print(f"No valid DOIs found in file: {input_value}")
            except Exception as e:
                error_print(f"Failed to extract DOIs from file: {e}")
                return
        else:
            # Use extract_dois_from_text for comma/space separated input
            info_print(f"Extracting DOIs from input: {input_value}")
            doi_list = getpapers.extract_dois_from_text(input_value)
            if not doi_list:
                info_print(f"No valid DOIs found in input: {input_value}")

        if not doi_list:
            error_print("No valid DOIs provided for --request-doi")
            return

        if len(doi_list) == 1:
            info_print(f"Requesting paper by DOI: {doi_list[0]}")
            request_result = await request_paper_by_doi(
                TG_API_ID, TG_API_HASH, PHONE, BOT_USERNAME, doi_list[0], SESSION_FILE, proxy_to_use
            )
            if request_result.get("ok"):
                info_print(f"✓ Paper request sent for DOI {doi_list[0]}")
                print("Request details:")
                print(request_result.get("details"))
            else:
                error_print(f"✗ Failed to request paper: {request_result.get('details', request_result.get('error', 'Unknown error'))}")
        else:
            info_print(f"Requesting papers for {len(doi_list)} DOIs...")
            batch_result = await batch_request_papers_by_doi(
                TG_API_ID, TG_API_HASH, PHONE, BOT_USERNAME, doi_list, SESSION_FILE, proxy_to_use
            )
            print("\nBatch request summary:")
            print(f"  Total: {batch_result.get('total', 0)}")
            print(f"  Requested: {batch_result.get('requested', 0)}")
            print(f"  Skipped: {batch_result.get('skipped', 0)}")
            print(f"  Errors: {batch_result.get('errors', 0)}")
            for res in batch_result.get("results", []):
                doi = res.get("doi", "Unknown")
                if res.get("ok"):
                    print(f"  ✓ Requested: {doi}")
                elif res.get("request_sent") is False:
                    print(f"  - Skipped (no request needed): {doi}")
                else:
                    print(f"  ✗ Error: {doi} - {res.get('error', res.get('details', 'Unknown error'))}")
        return

    # Handle check-doi command (now supports single DOI, list, or file)
    if args.check_doi:
        input_value = args.check_doi.strip()
        doi_list = []

        # Check if input is a file path
        if os.path.isfile(input_value):
            info_print(f"Reading DOIs from file: {input_value}")
            try:
                doi_list = getpapers.extract_dois_from_file(input_value)
                if not doi_list:
                    info_print(f"No valid DOIs found in file: {input_value}. Either the DOI is invaild or it cannot be verified on Crossref.")
            except Exception as e:
                error_print(f"Failed to extract DOIs from file: {e}")
            return
        else:
            # Use extract_dois_from_text for comma/space separated input
            info_print(f"Extracting DOIs from input: {input_value}")
            doi_list = getpapers.extract_dois_from_text(input_value)
            if not doi_list:
                info_print(f"No valid DOIs found in input: {input_value}")

        if not doi_list:
            error_print("No valid DOIs provided for --check-doi")
            return

        download_enabled = args.download
        if download_enabled:
            info_print("Auto-download enabled - will download paper(s) if available")

        # If only one DOI, do single check
        if len(doi_list) == 1:
            info_print(f"Checking DOI availability: {doi_list[0]}")
            debug_print(f"DOI to check: {doi_list[0]}")
            debug_print(f"Download enabled: {download_enabled}")
            availability_result = await check_doi_availability_on_nexus(
                TG_API_ID, TG_API_HASH, PHONE, BOT_USERNAME, doi_list[0], SESSION_FILE, proxy_to_use, download=download_enabled
            )
            format_doi_availability_result(availability_result)
            if "error" not in availability_result:
                status = availability_result.get("status", "unknown")
                if status == "available":
                    info_print("✓ DOI check completed - Paper is available on Nexus")
                    if download_enabled:
                        download_result = availability_result.get("download_result")
                        if download_result and download_result.get("success"):
                            info_print("✓ Paper downloaded successfully")
                        elif download_result and not download_result.get("success"):
                            error_print(f"✗ Download failed: {download_result.get('error', 'Unknown error')}")
                        elif download_enabled:
                            info_print("ℹ️ Download was requested but no download occurred")
                elif status == "not_available_requestable":
                    info_print("✓ DOI check completed - Paper can be requested from Nexus")
                elif status == "not_found":
                    info_print("✓ DOI check completed - Paper not found in Nexus database")
                else:
                    info_print(f"✓ DOI check completed - Status: {status}")
            else:
                error_print(f"✗ DOI check failed: {availability_result.get('error', 'Unknown error')}")
            return
        else:
            # Batch check
            info_print(f"Batch checking {len(doi_list)} DOIs...")
            batch_delay = args.batch_delay
            if batch_delay < 0.5:
                batch_delay = 0.5
                info_print("Batch delay adjusted to minimum of 0.5 seconds")
            elif batch_delay > 10:
                batch_delay = 10
                info_print("Batch delay adjusted to maximum of 10 seconds")
            info_print(f"Using batch delay of {batch_delay} seconds between requests")
            debug_print(f"Download enabled for batch: {download_enabled}")
            batch_result = await batch_check_doi_availability(
                TG_API_ID, TG_API_HASH, PHONE, BOT_USERNAME, doi_list,
                SESSION_FILE, proxy_to_use, batch_delay, download=download_enabled
            )
            format_batch_doi_results(batch_result)
            if "error" not in batch_result:
                summary = batch_result.get("summary", {})
                available_count = batch_result.get("available", 0)
                total_dois = batch_result.get("total_dois", 0)
                info_print(f"✓ Batch DOI check completed: {available_count}/{total_dois} papers available on Nexus")
                info_print(f"Success rate: {summary.get('success_rate', 0):.1f}%")
                if download_enabled:
                    downloaded_count = batch_result.get("downloaded", 0)
                    download_errors = batch_result.get("download_errors", 0)
                    info_print(f"Download results: {downloaded_count} successful, {download_errors} failed")
                    if downloaded_count > 0:
                        total_downloaded_mb = summary.get("total_downloaded_mb", 0)
                        info_print(f"Total downloaded: {total_downloaded_mb:.2f} MB")
            else:
                error_print(f"✗ Batch DOI check failed: {batch_result.get('error', 'Unknown error')}")
            return

    # Validate --download flag usage
    if args.download:
        info_print("⚠️ Warning: --download flag is only effective when used with --check-doi")
        debug_print("Download flag specified but no compatible command found")
    
    # Handle fetch-nexus-aaron command
    if args.fetch_nexus_aaron is not None:
        info_print("Fetching messages from @nexus_aaron...")
        
        # Validate and clamp limit
        limit = args.fetch_nexus_aaron
        if limit < 1:
            limit = 1
            info_print("Message limit adjusted to minimum of 1")
        elif limit > 100:
            limit = 100
            info_print("Message limit adjusted to maximum of 100")
        
        debug_print(f"Fetching {limit} messages from @nexus_aaron")
        messages_result = await fetch_nexus_aaron_messages(
            TG_API_ID, TG_API_HASH, PHONE, SESSION_FILE, limit, proxy_to_use, display=True
        )
        
        if messages_result.get("ok"):
            info_print(f"Successfully fetched {messages_result.get('messages_count', 0)} messages from @nexus_aaron")
        else:
            error_print(f"Failed to fetch messages from @nexus_aaron: {messages_result.get('error', 'Unknown error')}")
        
        return
    
    # Handle upload-to-nexus-aaron command
    if args.upload_to_nexus_aaron:
        info_print("Uploading file to @nexus_aaron...")
        
        file_path = args.upload_to_nexus_aaron
        upload_message = args.upload_message
        
        debug_print(f"File to upload: {file_path}")
        debug_print(f"Upload message: '{upload_message}'")
        
        # Validate file exists
        if not os.path.exists(file_path):
            error_print(f"File not found: {file_path}")
            return
        
        # Get file info for validation
        file_size = os.path.getsize(file_path)
        file_size_mb = file_size / (1024 * 1024)
        file_name = os.path.basename(file_path)
        
        info_print(f"File: {file_name}")
        info_print(f"Size: {file_size_mb:.2f} MB")
        
        # Warn for large files (Telegram has limits)
        if file_size_mb > 2000:  # 2GB limit
            error_print(f"File is too large ({file_size_mb:.2f} MB). Telegram limit is 2GB.")
            return
        elif file_size_mb > 50:  # Warn for files over 50MB
            info_print(f"Warning: Large file ({file_size_mb:.2f} MB) may take time to upload")
        
        # Perform the upload
        upload_result = await upload_file_to_nexus_aaron(
            TG_API_ID, TG_API_HASH, PHONE, file_path, upload_message, SESSION_FILE, proxy_to_use
        )
        
        # Display results with specialized formatting
        format_nexus_aaron_upload_result(upload_result)
        
        if upload_result.get("ok"):
            info_print("✓ File upload to @nexus_aaron completed successfully")
        else:
            error_print(f"✗ File upload to @nexus_aaron failed: {upload_result.get('error', 'Unknown error')}")
        
        return
    
    # Handle solve-requests command
    if args.solve_requests is not None:
        info_print("Solving research requests from @nexus_aaron...")
        
        # Validate and clamp limit
        limit = args.solve_requests
        if limit < 1:
            limit = 1
            info_print("Request limit adjusted to minimum of 1")
        elif limit > 50:
            limit = 50
            info_print("Request limit adjusted to maximum of 50")
        
        debug_print(f"Processing up to {limit} research requests from @nexus_aaron")
        
        # Use the existing function to handle request solving
        solve_result = await list_and_reply_to_nexus_aaron_message(
            TG_API_ID, TG_API_HASH, PHONE, SESSION_FILE, limit, proxy_to_use
        )
        
        # Display results with specialized formatting
        format_list_and_reply_result(solve_result)
        
        if solve_result.get("ok") and not solve_result.get("cancelled"):
            info_print("✓ Request solving completed successfully")
        elif solve_result.get("cancelled"):
            info_print("Request solving cancelled by user")
        else:
            error_print(f"✗ Request solving failed: {solve_result.get('error', 'Unknown error')}")
        
        return
    
    # Handle user-info command
    if args.user_info:
        info_print("Getting user profile information...")
        
        debug_print("Starting user profile retrieval process...")
        profile_result = await get_user_profile(TG_API_ID, TG_API_HASH, PHONE, BOT_USERNAME, SESSION_FILE, proxy_to_use)
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

    # Pass search-limit to send_message_to_bot if specified
    search_limit = args.search_limit if args.search_limit is not None else None
    send_result = await send_message_to_bot(
        TG_API_ID, TG_API_HASH, PHONE, BOT_USERNAME, message_to_send, SESSION_FILE, proxy_to_use, limit=search_limit
    )
    debug_print("Message sending process completed")
    
    format_result(send_result)
    
    # Handle button clicks after search results
    if send_result.get("ok") and send_result.get("bot_reply"):
        await process_callback_buttons(send_result["bot_reply"], proxy_to_use)
    else:
        debug_print("No valid bot reply to process for button clicks")

if __name__ == "__main__":
    asyncio.run(main())