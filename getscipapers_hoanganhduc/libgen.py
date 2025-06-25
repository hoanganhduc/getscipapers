import requests
from bs4 import BeautifulSoup
from urllib.parse import quote_plus
import argparse
import json
import sys
import re
import os
import platform

# List of LibGen mirror domains (main alternatives)
LIBGEN_MIRRORS = [
    "libgen.gs",
    "libgen.li",
    "libgen.vg",
    "libgen.la",
    "libgen.bz",
    "libgen.gl",
]

def select_active_libgen_domain(mirrors=LIBGEN_MIRRORS, timeout=3):
    """
    Returns the first LibGen domain that responds to a simple GET request.
    Falls back to the default if none respond.
    """
    test_path = "/json.php"
    for domain in mirrors:
        url = f"https://{domain}{test_path}"
        try:
            resp = requests.get(url, timeout=timeout)
            if resp.status_code == 200:
                return domain
        except Exception:
            continue
    return mirrors[0]  # fallback

LIBGEN_DOMAIN = select_active_libgen_domain()

def get_default_download_folder():
    """
    Returns the default Downloads folder path for the current OS.
    Creates the folder if it does not exist.
    """
    home = os.path.expanduser("~")
    system = platform.system()
    if system == "Windows":
        folder = os.path.join(home, "Downloads", "getscipapers", "libgen")
    elif system == "Darwin":
        folder = os.path.join(home, "Downloads", "getscipapers", "libgen")
    else:
        # Assume Linux/Unix
        folder = os.path.join(home, "Downloads", "getscipapers", "libgen")
    os.makedirs(folder, exist_ok=True)
    return folder

DEFAULT_DOWNLOAD_DIR = get_default_download_folder()

def search_libgen_by_doi(doi, limit=10):
    """
    Search for documents on LibGen using a DOI number via the JSON API,
    and fetch additional details from the edition page.

    Args:
        doi (str): The DOI number to search for.
        limit (int): Maximum number of results to return.

    Returns:
        dict: Matching documents with extra details, or empty dict if none found.
    """
    url = f"https://{LIBGEN_DOMAIN}/json.php"
    params = {
        "object": "e",
        "doi": doi,
        "fields": "*",
        "addkeys": "*",
        "limit1": 0,
        "limit2": limit
    }
    response = requests.get(url, params=params)
    if response.status_code != 200:
        return {}

    try:
        data = response.json()
    except Exception:
        return {}

    if not isinstance(data, dict):
        return {}

    # For each LibGen ID, fetch more info from edition.php
    for libgen_id, entry in data.items():
        edition_url = f"https://{LIBGEN_DOMAIN}/edition.php?id={libgen_id}"
        try:
            resp = requests.get(edition_url, timeout=10)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                extra = {}

                # Parse <div class="col-xl-7 order-xl-2 col-12 order-2 float-left">
                info_div = soup.find("div", class_="col-xl-7 order-xl-2 col-12 order-2 float-left")
                if info_div:
                    for p in info_div.find_all("p"):
                        strong = p.find("strong")
                        if strong:
                            key = strong.get_text(strip=True).rstrip(":")
                            # Remove <strong> from p to get value
                            strong.extract()
                            value = p.get_text(strip=True)
                            # Special handling for DOI (may be in <a>)
                            if key.lower() == "doi":
                                a = p.find("a")
                                if a:
                                    value = a.get_text(strip=True)
                                    extra["doi_url"] = a.get("href")
                            extra[key.lower()] = value
                    # Try to get <span class="badge badge-primary"> for type
                    badge = info_div.find("span", class_="badge badge-primary")
                    if badge:
                        extra["type"] = badge.get_text(strip=True)

                # Parse <div class="col-12 order-7 float-left"> for files
                files_div = soup.find("div", class_="col-12 order-7 float-left")
                files = {}
                if files_div:
                    table = files_div.find("table", id="tablelibgen")
                    if table:
                        for tr in table.find_all("tr"):
                            tds = tr.find_all("td")
                            if len(tds) >= 2:
                                file_info = {}
                                # Parse size and extension
                                size_ext_html = tds[1].decode_contents()
                                # Size
                                size_match = re.search(r"<strong>Size:</strong>\s*<nobr>([^<]+)</nobr>", size_ext_html)
                                if size_match:
                                    file_info["size"] = size_match.group(1).strip()
                                # Extension
                                ext_match = re.search(r"<strong>Extension:</strong>\s*([a-zA-Z0-9]+)", size_ext_html)
                                if ext_match:
                                    file_info["extension"] = ext_match.group(1).strip()
                                # Download links and md5
                                for a in tds[1].find_all("a"):
                                    label = a.get_text(strip=True)
                                    link = a.get("href", "")
                                    if "md5=" in link:
                                        md5 = re.search(r"md5=([a-fA-F0-9]{32})", link)
                                        if md5:
                                            file_info["md5"] = md5.group(1)
                                    file_info.setdefault("mirrors", {})[label] = link
                                # Add file_info to files dict (use md5 or index as key)
                                key = file_info.get("md5") or str(len(files))
                                files[key] = file_info
                if files:
                    extra["files"] = files

                # Add cover image if present
                cover_img = soup.find("img", {"class": "cover"})
                if cover_img and cover_img.get("src"):
                    extra["coverurl"] = cover_img["src"]

                # Merge extra fields into entry
                entry.update(extra)
        except Exception:
            continue

    return data

def print_libgen_doi_result(result):
    """
    Pretty-print the result of a LibGen DOI search using icons.
    Only print fields that have non-empty values.
    """
    if not result:
        print("❌ No results found for the given DOI.")
        return

    # If result is a dict with numeric keys (LibGen IDs), flatten to list of entries
    if isinstance(result, dict) and all(str(k).isdigit() for k in result.keys()):
        entries = []
        for k, v in result.items():
            v = dict(v)  # copy to avoid mutating original
            v["id"] = k  # set the LibGen ID explicitly
            entries.append(v)
    elif isinstance(result, list):
        entries = result
    else:
        entries = [result]

    field_map = [
        ("📄  Title:", ["title"]),
        ("🆔  ID:", ["id", "libgen_id"]),
        ("🔗  DOI:", ["doi", "DOI"]),
        ("👨‍🔬 Authors:", ["author", "authors"]),
        ("🏢 Publisher:", ["publisher"]),
        ("📅 Year:", ["year"]),
        ("🌐 Language:", ["language"]),
        ("📄 Pages:", ["pages", "pagetotal"]),
        ("💾 Size:", ["filesize", "size"]),
        ("📚 Extension:", ["extension", "filetype"]),
        ("📝 Series:", ["series"]),
        ("🏷️  Volume:", ["volumeinfo"]),
        ("🏷️  Edition:", ["edition"]),
        ("🏷️  Identifier:", ["identifier"]),
        ("🏷️  ISBN:", ["isbn", "isbn13"]),
        ("🏷️  ISSN:", ["issn"]),
        ("🏷️  UDC:", ["udc"]),
        ("🏷️  LBC:", ["lbc"]),
        ("🏷️  Library:", ["library"]),
        ("🏷️  City:", ["city"]),
        ("🏷️  Cover URL:", ["coverurl"]),
        ("🏷️  Type:", ["type"]),
    ]

    mirror_icons = {
        "GET": "⬇️",
        "Cloudflare": "☁️",
        "IPFS": "🗂️",
        "Cloud": "☁️",
        "Main": "🌐",
        "Z-Library": "📚",
        "Libgen": "📥",
        "Library": "📚",
        "1": "1️⃣",
        "2": "2️⃣",
        "3": "3️⃣",
        "4": "4️⃣",
        "5": "5️⃣",
    }

    for entry in entries:
        for label, keys in field_map:
            value = None
            for k in keys:
                v = entry.get(k)
                if v not in (None, "", [], {}):
                    value = v
                    break
            if value not in (None, "", [], {}):
                print(f"{label:<15} {value}")
        print("🔗 Mirrors:")
        # Print download links if present in 'files'
        files = entry.get("files", {})
        if files:
            for file_id, file_info in files.items():
                ext = file_info.get("extension", "").upper()
                size = file_info.get("size", "")
                md5 = file_info.get("md5", "")
                mirrors = file_info.get("mirrors", {})
                info_str = f"    💾 [{ext}] {size}"
                if md5:
                    info_str += f" | md5: {md5}"
                print(info_str)
                for label, link in mirrors.items():
                    icon = mirror_icons.get(label, "🔸")
                    if link:
                        print(f"        {icon} {label}: {link}")
        else:
            mirrors = entry.get("mirrors", {})
            if mirrors:
                for label, link in mirrors.items():
                    icon = mirror_icons.get(label, "🔸")
                    if link:
                        print(f"    {icon} {label}: {link}")
            else:
                print("    🔸 None")
        print("-" * 40)

def download_libgen_paper_by_doi(doi, dest_folder=None, preferred_exts=None, verbose=False):
    """
    Download the first available file for a given DOI from LibGen.

    Args:
        doi (str): The DOI number to search and download.
        dest_folder (str): Folder to save the downloaded file. If None, uses default.
        preferred_exts (list): List of preferred file extensions (e.g., ["pdf", "epub"]).
        verbose (bool): If True, print debug information.

    Returns:
        bool: True if download succeeded, False otherwise.
    """

    if dest_folder is None:
        dest_folder = DEFAULT_DOWNLOAD_DIR

    result = search_libgen_by_doi(doi, limit=1)
    if not result:
        if verbose:
            print("No result found for DOI:", doi)
        print("\nDownload Summary:")
        print("❌ Failed downloads:")
        print(f"  ❌ DOI: {doi} (No result found)")
        return False

    # Flatten result to first entry
    if isinstance(result, dict) and result:
        entry = next(iter(result.values()))
    else:
        if verbose:
            print("Unexpected result format.")
        print("\nDownload Summary:")
        print("❌ Failed downloads:")
        print(f"  ❌ DOI: {doi} (Unexpected result format)")
        return False

    files = entry.get("files", {})
    if not files:
        if verbose:
            print("No downloadable files found for DOI:", doi)
        print("\nDownload Summary:")
        print("❌ Failed downloads:")
        print(f"  ❌ DOI: {doi} (No downloadable files found)")
        return False

    # Select file by preferred extension
    file_info = None
    if preferred_exts:
        for ext in preferred_exts:
            for f in files.values():
                if f.get("extension", "").lower() == ext.lower():
                    file_info = f
                    break
            if file_info:
                break
    if not file_info:
        # Fallback: pick the first file
        file_info = next(iter(files.values()))

    mirrors = file_info.get("mirrors", {})
    # Try to pick a direct GET or Main mirror first, then others
    mirror_order = ["GET", "Main"]
    tried_labels = set()
    urls_to_try = []
    for label in mirror_order:
        if label in mirrors:
            urls_to_try.append((label, mirrors[label]))
            tried_labels.add(label)
    # Add any other mirrors not already tried
    for label, url in mirrors.items():
        if label not in tried_labels:
            urls_to_try.append((label, url))

    if not urls_to_try:
        if verbose:
            print("No download URL found for DOI:", doi)
        print("\nDownload Summary:")
        print("❌ Failed downloads:")
        print(f"  ❌ DOI: {doi} (No download URL found)")
        return False

    filename = entry.get("title", "libgen_paper")
    ext = file_info.get("extension", "pdf")
    safe_filename = re.sub(r"[\\/*?\"<>|]", "_", filename)
    out_path = os.path.join(dest_folder, f"{safe_filename}.{ext}")

    successes = []
    failures = []

    for label, download_url in urls_to_try:
        if verbose:
            print(f"Trying mirror '{label}': {download_url}")
            print(f"Saving to: {out_path}")
        try:
            # If the URL is of the form /ads.php?md5=...&downloadname=...
            if download_url.startswith("/ads.php?md5="):
                ads_url = f"https://{LIBGEN_DOMAIN}{download_url}"
                if verbose:
                    print(f"Following ads.php URL: {ads_url}")
                ads_resp = requests.get(ads_url, timeout=30)
                if ads_resp.status_code == 200:
                    soup = BeautifulSoup(ads_resp.text, "html.parser")
                    # Find the first <a> tag whose href contains "get.php?md5="
                    get_link = None
                    for a in soup.find_all("a", href=True):
                        href = a["href"]
                        if "get.php?md5=" in href:
                            # Make absolute URL if needed
                            if href.startswith("http"):
                                get_link = href
                            else:
                                get_link = f"https://{LIBGEN_DOMAIN}/" + href.lstrip("/")
                            break
                    if get_link:
                        if verbose:
                            print(f"Found get.php download link: {get_link}")
                        download_url = get_link
                    else:
                        if verbose:
                            print("No get.php download link found on ads.php page.")
                        failures.append((label, "No get.php link"))
                        continue
                else:
                    if verbose:
                        print(f"Failed to fetch ads.php page, status: {ads_resp.status_code}")
                    failures.append((label, f"ads.php status {ads_resp.status_code}"))
                    continue

            with requests.get(download_url, stream=True, timeout=30) as r:
                r.raise_for_status()
                with open(out_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
            if verbose:
                print(f"Download completed from mirror '{label}'.")
            successes.append((label, out_path))
            break  # Stop after first successful download
        except Exception as e:
            if verbose:
                print(f"Download failed from mirror '{label}': {e}")
            failures.append((label, str(e)))
            # Try next mirror

    # Print summary
    print("\nDownload Summary:")
    if successes:
        print("✅ Successful downloads:")
        for label, path in successes:
            print(f"  ✅ Mirror '{label}': {path}")
    else:
        print("No successful downloads.")

    if failures:
        print("❌ Failed downloads:")
        for label, reason in failures:
            print(f"  ❌ Mirror '{label}': {reason}")
    else:
        print("No failed downloads.")

    return bool(successes)

def search_libgen_by_query(
    query,
    limit=10,
    object_type="f",
    curtab="f",
    verbose=False,
    sort_by_year=True,
    order_desc=True,
):
    """
    Search for documents on LibGen using a query string by parsing the HTML results.

    Args:
        query (str): The search query.
        limit (int): Maximum number of results to return.
        object_type (str): The object type parameter for LibGen (default "f").
        curtab (str): The curtab parameter for LibGen (default "f").
        verbose (bool): If True, print debug information.
        sort_by_year (bool): If True, sort results by year.
        order_desc (bool): If True, sort descending (newest first).

    Returns:
        list: List of matching documents (dicts), or empty list if none found.
    """

    results = []
    seen_ids = set()
    page = 1
    while len(results) < limit:
        url = (
            f"https://{LIBGEN_DOMAIN}/index.php?&req={quote_plus(query)}"
            f"&object={object_type}&curtab={curtab}&page={page}"
        )
        if sort_by_year:
            url += f"&order=year&ordermode={'desc' if order_desc else 'asc'}"
        if verbose:
            print(f"[DEBUG] Fetching URL: {url}")
        response = requests.get(url, allow_redirects=True)
        if response.status_code != 200:
            if verbose:
                print(f"[DEBUG] Failed to fetch page {page}, status code: {response.status_code}")
            break

        soup = BeautifulSoup(response.text, "html.parser")
        table = None
        for t in soup.find_all("table"):
            header = t.find("tr")
            if header and len(header.find_all("th")) >= 8:
                table = t
                break
        if not table:
            if verbose:
                print(f"[DEBUG] No suitable table found on page {page}")
            break

        rows = table.find_all("tr")[1:]  # skip header row
        if verbose:
            print(f"[DEBUG] Found {len(rows)} rows in table on page {page}")
        found_new = False
        for idx, row in enumerate(rows):
            cols = row.find_all("td")
            if len(cols) < 9:
                if verbose:
                    print(f"[DEBUG] Row {idx} skipped, not enough columns ({len(cols)})")
                continue

            title_col = cols[0]
            # --- Custom title extraction logic ---
            a_tags = title_col.find_all("a")
            title = ""
            doi = ""
            libgen_id = ""
            found_title = False
            for i, a in enumerate(a_tags):
                next_sibling = a.next_sibling
                while next_sibling and (str(next_sibling).strip() == "" or str(next_sibling).strip() == "<i></i>"):
                    if str(next_sibling).strip() == "<i></i>":
                        title = a.get_text(strip=True)
                        found_title = True
                        break
                    next_sibling = next_sibling.next_sibling
                if found_title:
                    break
            if not found_title:
                brs = title_col.find_all("br")
                if len(brs) >= 1:
                    after_b = brs[0].find_next("a")
                    if after_b:
                        title = after_b.get_text(strip=True)
            # DOI extraction from <i><font color="green">DOI: ...</font></a></i>
            doi = ""
            for i_tag in title_col.find_all("i"):
                font_tag = i_tag.find("font", color="green")
                if font_tag and "DOI:" in font_tag.get_text():
                    doi_text = font_tag.get_text()
                    doi = doi_text.replace("DOI:", "").strip()
                    break
            # libgen_id extraction
            for a in a_tags:
                href = a.get("href", "")
                if "edition.php?id=" in href:
                    if not libgen_id:
                        libgen_id = href.split("id=")[-1]

            authors = cols[1].get_text(strip=True)
            publisher = cols[2].get_text(strip=True)
            year = cols[3].get_text(strip=True)
            language = cols[4].get_text(strip=True)
            pages = cols[5].get_text(strip=True)
            size = cols[6].get_text(strip=True)
            extension = cols[7].get_text(strip=True)

            mirrors_col = cols[8]
            mirrors = {}
            for a in mirrors_col.find_all("a"):
                label = a.get_text(strip=True)
                link = a.get("href", "")
                mirrors[label] = link

            unique_key = libgen_id or (title + "|" + authors)
            if unique_key in seen_ids:
                if verbose:
                    print(f"[DEBUG] Duplicate entry skipped: {unique_key}")
                continue
            seen_ids.add(unique_key)
            found_new = True

            entry = {
                "id": libgen_id,
                "title": title,
                "doi": doi,
                "authors": authors,
                "publisher": publisher,
                "year": year,
                "language": language,
                "pages": pages,
                "size": size,
                "extension": extension,
                "mirrors": mirrors
            }
            if verbose:
                print(f"[DEBUG] Added entry: {entry}")
            results.append(entry)
            if len(results) >= limit:
                break

        if not found_new or len(rows) == 0:
            if verbose:
                print(f"[DEBUG] No new results found on page {page}, stopping.")
            break  # No more new results/pages
        page += 1

    if sort_by_year:
        def year_key(entry):
            try:
                return int(entry.get("year", 0))
            except Exception:
                return 0
        results = sorted(results, key=year_key, reverse=order_desc)

    if verbose:
        print(f"[DEBUG] Returning {len(results[:limit])} results")
    return results[:limit]

def print_libgen_query_results(results):
    """
    Pretty-print the results of a LibGen query search using icons and numbering.
    """
    if not results:
        print("❌ No results found for the given query.")
        return

    for idx, entry in enumerate(results, 1):
        print(f"#{idx} 📄 Title:      {entry.get('title', 'N/A')}")
        print("   🆔 ID:         ", entry.get("id", "N/A"))
        print("   🔗 DOI:        ", entry.get("doi", "N/A"))
        print("   👨‍🔬 Authors:   ", entry.get("authors", "N/A"))
        print("   🏢 Publisher:   ", entry.get("publisher", "N/A"))
        print("   📅 Year:       ", entry.get("year", "N/A"))
        print("   🌐 Language:   ", entry.get("language", "N/A"))
        print("   📄 Pages:      ", entry.get("pages", "N/A"))
        print("   💾 Size:       ", entry.get("size", "N/A"))
        print("   📚 Extension:  ", entry.get("extension", "N/A"))
        print("   🔗 Mirrors:")
        mirrors = entry.get("mirrors", {})
        if mirrors:
            for label, link in mirrors.items():
                print(f"      🔸 {label}: {link}")
        else:
            print("      🔸 None")
        print("-" * 50)

def interactive_libgen_download(query, limit=10, preferred_exts=None, dest_folder=None, verbose=False):
    """
    Search LibGen for a query, print results, and interactively ask user which to download.
    User can select a single index or a range (e.g., 2-4).
    Tries all available mirrors for each selected result until download succeeds or all fail.
    At the end, prints a summary of successful and failed downloads.
    If verbose is False, only the summary is printed.
    """
    if dest_folder is None:
        dest_folder = DEFAULT_DOWNLOAD_DIR

    results = search_libgen_by_query(query, limit=limit, verbose=verbose)
    if not results:
        print("❌ No results found for the given query.")
        return

    print_libgen_query_results(results)
    print("Enter the number(s) of the result(s) to download (e.g., 1 or 2-4): ", end="")
    selection = input().strip()
    if not selection:
        print("No selection made. Exiting.")
        return

    indices = []
    if "-" in selection:
        try:
            start, end = map(int, selection.split("-"))
            indices = list(range(start, end + 1))
        except Exception:
            print("Invalid range input.")
            return
    else:
        try:
            indices = [int(selection)]
        except Exception:
            print("Invalid input.")
            return

    def resolve_libgen_download_url(download_url):
        # Handles /ads.php?md5=... and returns the final get.php?md5=... link
        if download_url.startswith("/ads.php?md5="):
            ads_url = f"https://{LIBGEN_DOMAIN}{download_url}"
            try:
                ads_resp = requests.get(ads_url, timeout=30)
                if ads_resp.status_code == 200:
                    soup = BeautifulSoup(ads_resp.text, "html.parser")
                    for a in soup.find_all("a", href=True):
                        href = a["href"]
                        if "get.php?md5=" in href:
                            if href.startswith("http"):
                                return href
                            else:
                                return f"https://{LIBGEN_DOMAIN}/" + href.lstrip("/")
                return None
            except Exception:
                return None
        return download_url

    successes = []
    failures = []

    for idx in indices:
        if 1 <= idx <= len(results):
            entry = results[idx - 1]
            mirrors = entry.get("mirrors", {})
            if not mirrors:
                if verbose:
                    print(f"Result #{idx} has no download mirrors, skipping.")
                failures.append((idx, entry.get("title", "N/A"), "No mirrors"))
                continue

            # Try to select preferred extension if specified
            ext_ok = True
            if preferred_exts:
                ext = entry.get("extension", "").lower()
                ext_ok = ext in [e.lower() for e in preferred_exts]
            if not ext_ok:
                if verbose:
                    print(f"Result #{idx} extension '{entry.get('extension', '')}' not in preferred_exts, skipping.")
                failures.append((idx, entry.get("title", "N/A"), "Extension not preferred"))
                continue

            # Try all mirrors one by one
            mirror_labels = ["GET", "Main"] + [label for label in mirrors if label not in ("GET", "Main")]
            download_success = False
            for label in mirror_labels:
                download_url = mirrors.get(label)
                if not download_url:
                    continue

                resolved_url = resolve_libgen_download_url(download_url)
                if not resolved_url:
                    if verbose:
                        print(f"Mirror '{label}': could not resolve download URL, trying next mirror.")
                    continue

                filename = entry.get("title", "libgen_paper")
                ext = entry.get("extension", "pdf")
                safe_filename = re.sub(r"[\\/*?\"<>|]", "_", filename)
                out_path = os.path.join(dest_folder, f"{safe_filename}.{ext}")

                if verbose:
                    print(f"Downloading result #{idx}: {entry.get('title', 'N/A')}")
                    print(f"From: {resolved_url}")
                    print(f"Saving to: {out_path}")

                try:
                    with requests.get(resolved_url, stream=True, timeout=30) as r:
                        r.raise_for_status()
                        with open(out_path, "wb") as f:
                            for chunk in r.iter_content(chunk_size=8192):
                                if chunk:
                                    f.write(chunk)
                    if verbose:
                        print(f"✅ Downloaded to: {out_path}")
                    successes.append((idx, entry.get("title", "N/A"), out_path))
                    download_success = True
                    break  # Stop after first successful download
                except Exception as e:
                    if verbose:
                        print(f"❌ Failed to download from mirror '{label}': {e}")
                    continue

            if not download_success:
                if verbose:
                    print(f"❌ All mirrors failed for result #{idx}.")
                failures.append((idx, entry.get("title", "N/A"), "All mirrors failed"))
        else:
            if verbose:
                print(f"Index {idx} is out of range.")
            failures.append((idx, "N/A", "Index out of range"))

    # Print summary
    print("\nDownload Summary:")
    if successes:
        print("✅ Successful downloads:")
        for idx, title, path in successes:
            print(f"  ✅ #{idx}: {title} -> {path}")
    else:
        print("No successful downloads.")

    if failures:
        print("❌ Failed downloads:")
        for idx, title, reason in failures:
            print(f"  ❌ #{idx}: {title} ({reason})")
    else:
        print("No failed downloads.")

def main():
    # Get the parent package name from the module's __name__
    parent_package = __name__.split('.')[0] if '.' in __name__ else None

    if parent_package is None:
        program_name = 'libgen'
    elif '_' in parent_package:
        # If the parent package has an underscore, strip it
        parent_package = parent_package[:parent_package.index('_')]
        program_name = f"{parent_package} libgen"
        
    parser = argparse.ArgumentParser(
        prog=program_name,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="LibGen search utility",
        epilog="""
Examples:
  Search for a book:
    %(prog)s --search "deep learning" --limit 5

  Search by DOI and print result:
    %(prog)s --check-doi 10.1007/978-3-030-14665-2

  Search and interactively download:
    %(prog)s --search "artificial intelligence" --download

  Download by DOI to a specific folder:
    %(prog)s --check-doi 10.1007/978-3-030-14665-2 --download "C:/Papers"
"""
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--search", type=str, help="Search LibGen by query string")
    group.add_argument("--check-doi", type=str, help="Search LibGen by DOI")
    parser.add_argument("--limit", type=int, default=10, help="Maximum number of results to return (default: 10)")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose/debug output")
    parser.add_argument(
        "--download",
        nargs="?",
        const=True,
        default=False,
        metavar="DOWNLOAD_DIR",
        help="Download after search (interactive for --search, auto for --check-doi). Optionally specify download directory."
    )
    args = parser.parse_args()

    # Determine download directory if --download is used
    download_dir = None
    if args.download:
        if isinstance(args.download, str):
            download_dir = args.download
        else:
            download_dir = None  # Use default

    if args.search:
        results = search_libgen_by_query(args.search, limit=args.limit, verbose=args.verbose)
        print_libgen_query_results(results)
        if args.download and results:
            interactive_libgen_download(
                args.search,
                limit=args.limit,
                dest_folder=download_dir,
                verbose=args.verbose
            )
    elif args.check_doi:
        result = search_libgen_by_doi(args.check_doi, limit=args.limit)
        print_libgen_doi_result(result)
        if args.download and result:
            out_path = download_libgen_paper_by_doi(
                args.check_doi,
                dest_folder=download_dir,
                verbose=args.verbose
            )
            if out_path:
                print(f"✅ Downloaded to: {out_path}")
            else:
                print("❌ Download failed or no file found.")

if __name__ == "__main__":
    main()