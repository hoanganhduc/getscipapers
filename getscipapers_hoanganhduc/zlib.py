# This script provides a function to search for books in Z-library using the Zlibrary-API by Bipinkrish (https://github.com/bipinkrish/Zlibrary-API/).

from .Zlibrary import Zlibrary
import argparse
import os
import json
import platform
import sys
import threading
import getpass
import requests

def get_default_config_dir():
    system = platform.system()
    if system == "Windows":
        return os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "getscipapers", "zlib")
    elif system == "Darwin":  # macOS
        return os.path.join(os.path.expanduser("~/Library/Application Support"), "getscipapers", "zlib")
    else:  # Linux and other Unix
        return os.path.join(os.path.expanduser("~/.config"), "getscipapers", "zlib")

def get_default_download_dir():
    system = platform.system()
    if system == "Windows":
        return os.path.join(os.path.expanduser("~"), "Downloads", "getscipapers", "zlib")
    elif system == "Darwin":  # macOS
        return os.path.join(os.path.expanduser("~/Downloads"), "getscipapers", "zlib")
    else:  # Linux and other Unix
        return os.path.join(os.path.expanduser("~/Downloads"), "getscipapers", "zlib")

EMAIL = ""
PASSWORD = ""
CONFIG_DIR = get_default_config_dir()
CONFIG_FILE = os.path.join(CONFIG_DIR, "zlib_config.json")
DEFAULT_DOWNLOAD_DIR = get_default_download_dir()

def save_credentials(email=None, password=None):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    creds = {
        "zlib_email": email,
        "zlib_password": password
    }
    with open(CONFIG_FILE, "w") as f:
        json.dump(creds, f)

def load_credentials(credentials_path=None):
    """
    Load credentials from the given path or the default config file.
    Returns a list: [email, password].
    If credentials_path is specified, load from it and save to default location if different.
    If not specified but default config exists, load default config.
    If neither exists, prompt user to input and save.
    """
    # Determine which path to use
    if credentials_path is not None:
        path = credentials_path
    elif os.path.exists(CONFIG_FILE):
        path = CONFIG_FILE
    else:
        path = None

    if path and os.path.exists(path):
        with open(path, "r") as f:
            creds = json.load(f)
        # If loaded from a custom path, save to default location if different
        if credentials_path and os.path.abspath(credentials_path) != os.path.abspath(CONFIG_FILE):
            save_credentials(creds.get("zlib_email"), creds.get("zlib_password"))
        email = creds.get("zlib_email", "")
        password = creds.get("zlib_password", "")
        return [email, password]

    # If no credentials found, prompt user to input and save
    print("No credentials found. Please enter your Z-library credentials.")
    prompt_and_save_credentials()
    # After prompting, load from default config file
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            creds = json.load(f)
        return [creds.get("zlib_email", ""), creds.get("zlib_password", "")]
    return ["", ""]  # If still no credentials, return empty

def prompt_and_save_credentials():
    """
    Prompt the user to input Z-library email and password.
    If the input is different from the saved credentials, save to default config location.
    If no response after 30 seconds, quit.
    Also sets global EMAIL and PASSWORD after user input.
    """
    global EMAIL, PASSWORD
    current_creds = load_credentials()
    current_email = current_creds.get("zlib_email", "")
    current_password = current_creds.get("zlib_password", "")

    print("Enter your Z-library credentials.")

    def input_with_timeout(prompt, default, timeout=30, is_password=False):
        result = [default]
        def inner():
            try:
                if is_password:
                    val = getpass.getpass(prompt)
                else:
                    val = input(prompt)
                if val:
                    result[0] = val
            except EOFError:
                pass
        t = threading.Thread(target=inner)
        t.daemon = True
        t.start()
        t.join(timeout)
        if t.is_alive():
            print("\nNo response after 30 seconds. Quitting.")
            sys.exit(1)
        return result[0]

    email = input_with_timeout(f"Email [{current_email}]: ", current_email)
    password = input_with_timeout(
        f"Password [{'*' * len(current_password) if current_password else ''}]: ",
        current_password,
        is_password=True
    )

    EMAIL = email
    PASSWORD = password

    if email != current_email or password != current_password:
        save_credentials(email, password)
        print("Credentials saved.")
    else:
        print("Credentials unchanged.")

def search_zlibrary_books(query, limit=20, email=None, password=None, sort_by_year=True):
    """
    Search for books in Z-library using the Zlibrary-API wrapper.

    Args:
        query (str): The search query (book title, author, etc.).
        limit (int): Number of results to return.
        email (str, optional): Z-library email for login.
        password (str, optional): Z-library password for login.
        sort_by_year (bool): If True, sort results by year (descending).

    Returns:
        list: List of book results (dicts), or empty list if none found.
    """
    # Use global EMAIL/PASSWORD if not provided
    zlib_email = email if email else EMAIL
    zlib_password = password if password else PASSWORD

    # If still not set, try loading from config
    if not zlib_email or not zlib_password:
        creds = load_credentials()
        if isinstance(creds, list):
            zlib_email, zlib_password = creds if len(creds) == 2 else ("", "")
        else:
            zlib_email = zlib_email or creds.get("zlib_email", "")
            zlib_password = zlib_password or creds.get("zlib_password", "")

    # Login using credentials if available
    if zlib_email and zlib_password:
        Z = Zlibrary(email=zlib_email, password=zlib_password)
    else:
        Z = Zlibrary()  # Not logged in, limited access

    try:
        results = Z.search(message=query, limit=limit)
        books = results.get("books", [])
        if sort_by_year:
            def parse_year(book):
                try:
                    return int(book.get("year", 0))
                except Exception:
                    return 0
            books = sorted(books, key=parse_year, reverse=True)
        return books
    except Exception as e:
        print(f"Error searching Z-library: {e}")
        return []

def print_book_details(book):
    """
    Print detailed information about a book result in a human-readable format.
    """
    def format_filesize(size):
        try:
            size = int(size)
            for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
                if size < 1024:
                    return f"{size:.2f} {unit}"
                size /= 1024
            return f"{size:.2f} PB"
        except Exception:
            return str(size)

    title = book.get('title', 'N/A')
    authors = book.get('author', 'N/A')
    if isinstance(authors, list):
        authors = ', '.join(authors)
    publisher = book.get('publisher', 'N/A')
    year = book.get('year', 'N/A')
    language = book.get('language', 'N/A')
    pages = book.get('pages', 'N/A')
    extension = book.get('extension', 'N/A')
    filesize = book.get('filesize', 'N/A')
    filesize_str = format_filesize(filesize)

    print(f"📚 Title      : {title}")
    print(f"👤 Author(s)  : {authors}")
    print(f"🏢 Publisher  : {publisher}")
    print(f"📅 Year       : {year}")
    print(f"🌐 Language   : {language}")
    print(f"📄 Pages      : {pages}")
    print(f"💾 Extension  : {extension}")
    print(f"🗂️ Filesize   : {filesize_str}")
    print("-" * 60)

def get_profile(email=None, password=None):
    """
    Get the user's Z-library profile information.
    """
    zlib_email = email if email else EMAIL
    zlib_password = password if password else PASSWORD
    if not zlib_email or not zlib_password:
        creds = load_credentials()
        if isinstance(creds, list):
            zlib_email, zlib_password = creds if len(creds) == 2 else ("", "")
        else:
            zlib_email = zlib_email or creds.get("zlib_email")
            zlib_password = zlib_password or creds.get("zlib_password")
    Z = Zlibrary(email=zlib_email, password=zlib_password)
    try:
        return Z.getProfile()
    except Exception as e:
        print(f"Error getting profile: {e}")
        return {}

def get_most_popular(language=None):
    """
    Get most popular books (optionally for a specific language).
    """
    Z = Zlibrary()
    try:
        return Z.getMostPopular(switch_language=language)
    except Exception as e:
        print(f"Error getting most popular books: {e}")
        return {}

def get_recently():
    """
    Get recently added books.
    """
    Z = Zlibrary()
    try:
        return Z.getRecently()
    except Exception as e:
        print(f"Error getting recently added books: {e}")
        return {}

def get_user_recommended(email=None, password=None):
    """
    Get user recommended books.
    """
    zlib_email = email if email else EMAIL
    zlib_password = password if password else PASSWORD
    if not zlib_email or not zlib_password:
        creds = load_credentials()
        if isinstance(creds, list):
            zlib_email, zlib_password = creds if len(creds) == 2 else ("", "")
        else:
            zlib_email = zlib_email or creds.get("zlib_email")
            zlib_password = zlib_password or creds.get("zlib_password")
    Z = Zlibrary(email=zlib_email, password=zlib_password)
    try:
        return Z.getUserRecommended()
    except Exception as e:
        print(f"Error getting user recommended books: {e}")
        return {}

def get_user_saved(email=None, password=None, order=None, page=None, limit=20):
    """
    Get books saved by the user.
    """
    zlib_email = email if email else EMAIL
    zlib_password = password if password else PASSWORD
    if not zlib_email or not zlib_password:
        creds = load_credentials()
        if isinstance(creds, list):
            zlib_email, zlib_password = creds if len(creds) == 2 else ("", "")
        else:
            zlib_email = zlib_email or creds.get("zlib_email")
            zlib_password = zlib_password or creds.get("zlib_password")
    Z = Zlibrary(email=zlib_email, password=zlib_password)
    try:
        return Z.getUserSaved(order=order, page=page, limit=limit)
    except Exception as e:
        print(f"Error getting user saved books: {e}")
        return {}

def get_user_downloaded(email=None, password=None, order=None, page=None, limit=None):
    """
    Get books downloaded by the user.
    """
    zlib_email = email if email else EMAIL
    zlib_password = password if password else PASSWORD
    if not zlib_email or not zlib_password:
        creds = load_credentials()
        if isinstance(creds, list):
            zlib_email, zlib_password = creds if len(creds) == 2 else ("", "")
        else:
            zlib_email = zlib_email or creds.get("zlib_email")
            zlib_password = zlib_password or creds.get("zlib_password")
    Z = Zlibrary(email=zlib_email, password=zlib_password)
    try:
        return Z.getUserDownloaded(order=order, page=page, limit=limit)
    except Exception as e:
        print(f"Error getting user downloaded books: {e}")
        return {}

def get_book_info(bookid, hashid, language=None):
    """
    Get detailed info for a book.
    """
    Z = Zlibrary()
    try:
        return Z.getBookInfo(bookid, hashid, switch_language=language)
    except Exception as e:
        print(f"Error getting book info: {e}")
        return {}

def download_book(book, email=None, password=None, download_dir=None):
    """
    Download a book using the Zlibrary API.
    """
    zlib_email = email if email else EMAIL
    zlib_password = password if password else PASSWORD
    if not zlib_email or not zlib_password:
        creds = load_credentials()
        if isinstance(creds, list):
            zlib_email, zlib_password = creds if len(creds) == 2 else ("", "")
        else:
            zlib_email = zlib_email or creds.get("zlib_email")
            zlib_password = zlib_password or creds.get("zlib_password")
    Z = Zlibrary(email=zlib_email, password=zlib_password)
    if download_dir is None:
        download_dir = DEFAULT_DOWNLOAD_DIR
    os.makedirs(download_dir, exist_ok=True)
    try:
        filename, content = Z.downloadBook(book)
        filepath = os.path.join(download_dir, filename)
        with open(filepath, "wb") as f:
            f.write(content)
        print(f"Downloaded: {filepath}")
        return filepath
    except Exception as e:
        print(f"Error downloading book: {e}")
        return None

def is_logged_in(email=None, password=None):
    """
    Check if the user is logged in.
    """
    zlib_email = email if email else EMAIL
    zlib_password = password if password else PASSWORD
    if not zlib_email or not zlib_password:
        creds = load_credentials()
        if isinstance(creds, list):
            zlib_email, zlib_password = creds if len(creds) == 2 else ("", "")
        else:
            zlib_email = zlib_email or creds.get("zlib_email")
            zlib_password = zlib_password or creds.get("zlib_password")
    Z = Zlibrary(email=zlib_email, password=zlib_password)
    try:
        return Z.isLoggedIn()
    except Exception as e:
        print(f"Error checking login status: {e}")
        return False
    
def interactive_login_search_download(query=None, download_dir=None, limit=20, sort_by_year=True):
    """
    Login, search, print results, and allow user to select (single or range) books to download.
    Optionally takes a search query, a download directory, a limit on number of results, and sort_by_year.
    """
    # Ensure credentials are loaded or prompt user
    creds = load_credentials()
    if isinstance(creds, list):
        email, password = creds if len(creds) == 2 else ("", "")
    else:
        email = creds.get("zlib_email", "")
        password = creds.get("zlib_password", "")
    if not email or not password:
        prompt_and_save_credentials()
        creds = load_credentials()
        if isinstance(creds, list):
            email, password = creds if len(creds) == 2 else ("", "")
        else:
            email = creds.get("zlib_email", "")
            password = creds.get("zlib_password", "")

    # Login and show profile info
    Z = Zlibrary(email=email, password=password)
    if not Z.isLoggedIn():
        print("Login failed. Please check your credentials.")
        return
    profile = Z.getProfile()
    print("Logged in as:", profile.get("email", email))

    # Prompt for search query if not provided
    if query is None:
        query = input("Enter search query: ").strip()
    if not query:
        print("No query entered.")
        return

    # Search books
    try:
        results = Z.search(message=query, limit=limit)
        books = results.get("books", [])
        if sort_by_year:
            def parse_year(book):
                try:
                    return int(book.get("year", 0))
                except Exception:
                    return 0
            books = sorted(books, key=parse_year, reverse=True)
    except Exception as e:
        print(f"Error searching: {e}")
        return

    if not books:
        print("No books found.")
        return

    # Print search results with index and details
    print("\nSearch Results:")
    for idx, book in enumerate(books, 1):
        print(f"🔢 {idx:2d}.")
        print_book_details(book)

    # Prompt user for selection (single or range)
    selection = input(
        "\nEnter the number(s) of the book(s) to download (e.g. 1,3-5): "
    ).replace(" ", "")
    if not selection:
        print("No selection made.")
        return

    # Parse selection (supports comma-separated and ranges)
    indices = set()
    for part in selection.split(","):
        if "-" in part:
            start, end = part.split("-")
            indices.update(range(int(start), int(end) + 1))
        elif part.isdigit():
            indices.add(int(part))
    indices = sorted(i for i in indices if 1 <= i <= len(books))
    if not indices:
        print("No valid selection.")
        return

    # Check downloads left
    try:
        downloads_left = Z.getDownloadsLeft()
    except Exception:
        downloads_left = None

    if downloads_left is not None and len(indices) > downloads_left:
        print(
            f"Warning: You selected {len(indices)} books, but only have {downloads_left} downloads left."
            " Some books may not be downloaded."
        )

    # Download selected books
    for count, i in enumerate(indices, 1):
        if downloads_left is not None and count > downloads_left:
            print("Reached download limit. Skipping remaining books.")
            break
        book = books[i - 1]
        print(f"\nDownloading: {book.get('title', 'N/A')}")
        filepath = download_book(book, email=email, password=password, download_dir=download_dir)
        if filepath:
            print(f"Saved to: {filepath}")
        else:
            print("Download failed.")

def main():
    global EMAIL, PASSWORD, CONFIG_DIR, CONFIG_FILE, DEFAULT_DOWNLOAD_DIR
    
    # Get the parent package name from the module's __name__
    parent_package = __name__.split('.')[0] if '.' in __name__ else None

    if parent_package is None:
        program_name = 'zlib'
    elif '_' in parent_package:
        # If the parent package has an underscore, strip it
        parent_package = parent_package[:parent_package.index('_')]
        program_name = f"{parent_package} zlib"
        
    parser = argparse.ArgumentParser(
        prog=program_name,
        description="Search and download books from Z-library.",
        epilog="""Examples:
  %(prog)s --search "deep learning"
  %(prog)s --search "tolkien" --search-limit 5
  %(prog)s --search "python" --download
  %(prog)s --search "data science" --download "C:\Books"
  %(prog)s --user-info
  %(prog)s --recent
  %(prog)s --popular --popular-language en
""",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('--search', type=str, help='Search query (book title, author, etc.)')
    parser.add_argument('--search-limit', type=int, help='Number of results to return (only with --search)')
    parser.add_argument('--credentials', type=str, metavar='CREDENTIALS', help='Path to Z-library credentials JSON file')
    parser.add_argument('--clear-credentials', action='store_true', help='Clear saved Z-library credentials')
    parser.add_argument('--download', nargs='?', const=DEFAULT_DOWNLOAD_DIR, default=None, metavar='DOWNLOAD_DIR', help='Download directory for selected books (optional, uses default if not specified)')
    parser.add_argument('--user-info', action='store_true', help='Show Z-library user profile information')
    parser.add_argument('--recent', action='store_true', help='List recently added books')
    parser.add_argument('--popular', action='store_true', help='List most popular books')
    parser.add_argument('--popular-language', type=str, metavar='LANG', help='Language code for most popular books (optional)')
    args = parser.parse_args()

    # Prevent using --credentials and --clear-credentials at the same time
    if args.credentials and args.clear_credentials:
        print("Error: --credentials and --clear-credentials cannot be used at the same time.")
        return

    if args.credentials:
        EMAIL, PASSWORD = load_credentials(args.credentials)
    elif os.path.exists(CONFIG_FILE):
        EMAIL, PASSWORD = load_credentials()
        
    if is_logged_in(email=EMAIL, password=PASSWORD):
        print(f"Already logged in as: {EMAIL}")
    else:
        print("Not logged in. Some features may not work without login.")

    if args.user_info:
        profile = get_profile(email=EMAIL, password=PASSWORD)
        if profile.get("success", False):
            user = profile.get("user") if isinstance(profile, dict) and "user" in profile else profile
            if not user:
                print("Could not retrieve user profile.")
                return
            print("User Profile:")
            ICONS = {
                "email": "📧",
                "name": "👤",
                "id": "🆔",
                "downloads_today": "⬇️",
                "downloads_limit": "📥",
                "confirmed": "✅",
                "isPremium": "💎",
                "kindle_email": "📨",
                "remix_userkey": "🔑",
                "donations_active": "💰",
                "donations_expire": "⏳",
            }
            for k, v in user.items():
                key = k.replace("_", " ").capitalize()
                icon = ICONS.get(k, "•")
                if isinstance(v, list):
                    v = ', '.join(str(i) for i in v)
                print(f"  {icon} {key}: {v}")
        else:
            print("Could not retrieve user profile.")
        return

    if args.recent:
        results = get_recently()
        books = results.get("books", []) if isinstance(results, dict) else results
        if not books:
            print("No recently added books found.")
            return
        print("\nRecently Added Books:")
        for idx, book in enumerate(books, 1):
            print(f"🔢 {idx:2d}.")
            print_book_details(book)
        return

    if args.popular:
        results = get_most_popular(language=args.popular_language)
        books = results.get("books", []) if isinstance(results, dict) else results
        if not books:
            print("No popular books found.")
            return
        print("\nMost Popular Books:")
        for idx, book in enumerate(books, 1):
            print(f"🔢 {idx:2d}.")
            print_book_details(book)
        return

    if not args.search:
        print("No search query provided. Use --search.")
        return

    if args.search and args.download:
        interactive_login_search_download(
            query=args.search,
            download_dir=args.download,
            limit=args.search_limit if args.search_limit is not None else 20
        )
        return

    if args.search and not args.download:
        search_limit = args.search_limit if args.search_limit is not None else 20
        results = search_zlibrary_books(
            args.search,
            limit=search_limit,
            email=EMAIL,
            password=PASSWORD
        )
        if not results:
            print("No books found.")
            return
        print("\nSearch Results:")
        for idx, book in enumerate(results, 1):
            print(f"🔢 {idx:2d}.")
            print_book_details(book)

if __name__ == "__main__":
    main()
