"""Helpers for uploading PDFs to third-party services.

The upload routines are intentionally isolated from the rest of the request
flow so they can be invoked independently via CLI. Network calls and command
construction live here to keep other modules focused on discovery and download
responsibilities.
"""

import sys
import os
import argparse
import subprocess
import requests
import asyncio

from . import getpapers, libgen, nexus, scinet

ICONS = {
    'info': 'ℹ️',
    'success': '✅',
    'error': '❌',
    'warning': '⚠️',
    'upload': '📤',
    'link': '🔗',
    'check': '🔍',
    'sync': '🔄',
}

def get_files_from_args(paths, verbose=False, file_types=None):
    """
    Collect files from given paths. If file_types is specified (list of extensions, e.g. ['pdf']),
    only files with those extensions are included. Default is ['pdf'].
    """
    if file_types is None:
        file_types = ['pdf']
    file_types = [ft.lower().lstrip('.') for ft in file_types]
    files = []
    for path in paths:
        abs_path = os.path.abspath(path)
        if os.path.isdir(abs_path):
            if verbose:
                print(f"{ICONS['info']} Scanning directory: {abs_path}")
            for entry in os.listdir(abs_path):
                full_path = os.path.join(abs_path, entry)
                if os.path.isfile(full_path):
                    ext = os.path.splitext(entry)[1].lower().lstrip('.')
                    if ext in file_types:
                        files.append(os.path.abspath(full_path))
                    elif verbose:
                        print(f"{ICONS['warning']} Skipping {entry} (not in allowed types: {file_types})")
        elif os.path.isfile(abs_path):
            ext = os.path.splitext(abs_path)[1].lower().lstrip('.')
            if ext in file_types:
                files.append(abs_path)
            elif verbose:
                print(f"{ICONS['warning']} Skipping {abs_path} (not in allowed types: {file_types})")
        else:
            if verbose:
                print(f"{ICONS['warning']} Warning: {abs_path} is not a valid file or directory, skipping.")
    return files

def upload_to_tempsh(files, verbose=False):
    for file_path in files:
        file_name = os.path.basename(file_path)
        if verbose:
            print(f"{ICONS['upload']} Uploading {file_name} to temp.sh...")
        with open(file_path, "rb") as f:
            files_param = {'file': (file_name, f)}
            resp = requests.post(
                "https://temp.sh/upload",
                files=files_param
            )
        if resp.status_code == 200:
            print(f"{ICONS['success']} {file_name} uploaded to temp.sh: {ICONS['link']} {resp.text.strip()}")
        else:
            print(f"{ICONS['error']} Failed to upload {file_name} to temp.sh: {resp.text}")

def upload_to_bashupload(files, verbose=False):
    for file_path in files:
        file_name = os.path.basename(file_path)
        if verbose:
            print(f"{ICONS['upload']} Uploading {file_name} to bashupload.com...")
        with open(file_path, "rb") as f:
            files_param = {'file': (file_name, f)}
            resp = requests.post(
                "https://bashupload.com/",
                files=files_param
            )
        if resp.status_code == 200:
            print(f"{ICONS['success']} {file_name} uploaded to bashupload.com: {ICONS['link']} {resp.text.strip()}")
        else:
            print(f"{ICONS['error']} Failed to upload {file_name} to bashupload.com: {resp.text}")

def run_command(command, verbose=False):
    if verbose:
        print(f"{ICONS['info']} Executing: {' '.join(command)}")
    try:
        result = subprocess.run(command, check=True, text=True, capture_output=True)
        if verbose and result.stdout:
            print(f"{ICONS['info']} {result.stdout}")
        return result.stdout
    except subprocess.CalledProcessError as e:
        print(f"{ICONS['error']} Error executing command: {' '.join(command)}")
        if verbose:
            print(f"{ICONS['error']} Error message: {e.stderr}")
        sys.exit(1)

def upload_to_gdrive(files, remote_path=None, verbose=False):
    if verbose:
        print(f"{ICONS['info']} Note: This function requires rclone to be installed and configured with your Google account.")
        print(f"{ICONS['info']} See https://rclone.org/drive/ for setup instructions.")
    # Ensure 'getscipapers' folder exists in Google Drive root
    folder_name = "getscipapers"
    folder_path = f"gdrive:{folder_name}"
    run_command(["rclone", "mkdir", folder_path], verbose)
    for file_path in files:
        if verbose:
            print(f"{ICONS['check']} Checking if {file_path} exists...")
        if not os.path.exists(file_path):
            print(f"{ICONS['error']} Error: {file_path} does not exist")
            continue
        # Always upload directly to getscipapers folder, no subfolders
        remote = os.path.basename(file_path)
        destination = f"{folder_path}"
        if verbose:
            print(f"{ICONS['sync']} Uploading {file_path} to Google Drive folder '{folder_name}' as {remote}...")
        run_command(["rclone", "copy", file_path, destination, "--progress"], verbose)
        if verbose:
            print(f"{ICONS['success']} Upload to {destination} completed")
        # Share the link to the uploaded file, not the folder
        shareable_link = share_gdrive_item(f"{folder_name}/{remote}", verbose)
        print(f"{ICONS['success']} Upload complete!")
        print(f"{ICONS['link']} Shareable link to file: {shareable_link}")

def share_gdrive_item(gdrive_path, verbose=False):
    gdrive_path = gdrive_path.replace("gdrive:", "", 1)
    if verbose:
        print(f"{ICONS['info']} Preparing to share: {gdrive_path}")
    command = ["rclone", "link", f"gdrive:{gdrive_path}"]
    if verbose:
        print(f"{ICONS['link']} Creating shareable link for {gdrive_path}...")
    shareable_link = run_command(command, verbose).strip()
    return shareable_link

def upload_to_dropbox(files, remote_path=None, verbose=False):
    if verbose:
        print(f"{ICONS['info']} Note: This function requires rclone to be installed and configured with your Dropbox account.")
        print(f"{ICONS['info']} See https://rclone.org/dropbox/ for setup instructions.")
    # Ensure 'getscipapers' folder exists in Dropbox root
    folder_name = "getscipapers"
    folder_path = f"dropbox:{folder_name}"
    run_command(["rclone", "mkdir", folder_path], verbose)
    for file_path in files:
        if verbose:
            print(f"{ICONS['check']} Checking if {file_path} exists...")
        if not os.path.exists(file_path):
            print(f"{ICONS['error']} Error: {file_path} does not exist")
            continue
        # Always upload directly to getscipapers folder, no subfolders
        remote = os.path.basename(file_path)
        destination = f"{folder_path}"
        if verbose:
            print(f"{ICONS['sync']} Uploading {file_path} to Dropbox folder '{folder_name}' as {remote}...")
        run_command(["rclone", "copy", file_path, destination, "--progress"], verbose)
        if verbose:
            print(f"{ICONS['success']} Upload to {destination} completed")
        shareable_link = share_dropbox_item(f"{folder_name}/{remote}", verbose)
        print(f"{ICONS['success']} Upload complete!")
        print(f"{ICONS['link']} Shareable link: {shareable_link}")

def share_dropbox_item(dropbox_path, verbose=False):
    dropbox_path = dropbox_path.replace("dropbox:", "", 1)
    if verbose:
        print(f"{ICONS['info']} Preparing to share: {dropbox_path}")
    command = ["rclone", "link", f"dropbox:{dropbox_path}"]
    if verbose:
        print(f"{ICONS['link']} Creating shareable link for {dropbox_path}...")
    shareable_link = run_command(command, verbose).strip()
    return shareable_link

def upload_to_libgen(files, verbose=False):
    for file_path in files:
        file_name = os.path.basename(file_path)
        if verbose:
            print(f"{ICONS['upload']} Uploading {file_name} to LibGen...")
        try:
            result = libgen.upload_and_register_to_libgen(filepath=file_path, verbose=verbose)
            if result is not None and isinstance(result, str):
                print(f"{ICONS['success']} {file_name} uploaded to LibGen: {ICONS['link']} {result}")
            else:
                print(f"{ICONS['error']} Failed to upload {file_name} to LibGen: No URL returned.")
        except Exception as e:
            print(f"{ICONS['error']} Exception uploading {file_name} to LibGen: {e}")

async def upload_to_nexus_aaron(files, verbose=False):
    for file_path in files:
        file_name = os.path.basename(file_path)
        if verbose:
            print(f"{ICONS['upload']} Uploading {file_name} to nexus_aaron bot...")
        try:
            result = await nexus.simple_upload_to_nexus_aaron(file_path)
            if verbose:
                print(f"{ICONS['info']} Result from nexus_aaron: {result}")
            if result.get("ok"):
                print(f"{ICONS['success']} {file_name} uploaded to nexus_aaron: {ICONS['link']} {result.get('url', 'No URL returned')}")
            else:
                print(f"{ICONS['error']} Failed to upload {file_name} to nexus_aaron: {result.get('error', 'Unknown error')}")
        except Exception as e:
            print(f"{ICONS['error']} Exception uploading {file_name} to nexus_aaron: {e}")

def upload_to_scinet(files, verbose=False):
    for file_path in files:
        if not file_path.lower().endswith('.pdf'):
            if verbose:
                print(f"{ICONS['warning']} Skipping non-PDF file: {os.path.basename(file_path)}")
            continue
        file_name = os.path.basename(file_path)
        if verbose:
            print(f"{ICONS['upload']} Uploading {file_name} to SciNet...")
        try:
            result = scinet.upload_pdf_to_scinet_simple(file_path)
            if isinstance(result, dict) and result.get("success"):
                print(f"{ICONS['success']} {file_name} uploaded to SciNet: {ICONS['link']} {result.get('url', 'No URL returned')}")
            elif isinstance(result, dict):
                print(f"{ICONS['error']} Failed to upload {file_name} to SciNet: {result.get('error', 'Unknown error')}")
            elif result is True:
                print(f"{ICONS['success']} {file_name} uploaded to SciNet (no URL returned).")
            else:
                print(f"{ICONS['error']} Failed to upload {file_name} to SciNet: Unexpected result type ({type(result).__name__})")
        except Exception as e:
            print(f"{ICONS['error']} Exception uploading {file_name} to SciNet: {e}")

def main():
    parent_package = __name__.split('.')[0] if '.' in __name__ else None

    if parent_package is None:
        program_name = 'upload'
    elif '_' in parent_package:
        parent_package = parent_package[:parent_package.index('_')]
        program_name = f"{parent_package} upload"
        
    parser = argparse.ArgumentParser(
        prog=program_name, 
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Upload files to temp.sh, bashupload.com, Google Drive, Dropbox, LibGen, Nexus, or SciNet",
        epilog="""
Examples:
  %(prog)s myfile.txt --service temp.sh
  %(prog)s "folder1,file2.pdf" --service bashupload.com
  %(prog)s myfolder --service gdrive --remote-path backup/myfolder
  %(prog)s file.txt --service dropbox --remote-path shared/file.txt -v
  %(prog)s paper.pdf --service libgen
  %(prog)s file.pdf --service nexus
  %(prog)s paper.pdf --service scinet
  %(prog)s file.pdf --service temp.sh,libgen
  %(prog)s file.pdf --service temp.sh libgen
  %(prog)s myfolder --file-type pdf docx --service gdrive
  %(prog)s "folder1,file2.pdf" --service temp.sh,dropbox --file-type pdf
  %(prog)s myfile.pdf --service gdrive --verbose
  %(prog)s myfile.pdf --service scinet --file-type pdf
  %(prog)s "folder1,file2.pdf" --service nexus,libgen,scinet
"""
    )
    parser.add_argument(
        "paths",
        help="Comma-separated list of files or directories to upload"
    )
    parser.add_argument(
        "--file-type",
        nargs="+",
        required=False,
        help="Only include files with these extensions (e.g. pdf, txt, docx). Default: pdf"
    )
    parser.add_argument(
        "--service",
        nargs="+",
        required=False,
        help="Choose one or more upload services (comma or space separated). Options: temp.sh, bashupload.com, gdrive, dropbox, libgen, nexus, scinet"
    )
    parser.add_argument(
        "--remote-path",
        help="Destination path in Google Drive/Dropbox (only for gdrive/dropbox service)"
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Print detailed progress information"
    )
    args = parser.parse_args()

    # Flatten and normalize service list (support comma or space separated)
    raw_services = []
    if args.service is None:
        services = ["temp.sh"]
        if args.verbose:
            print(f"{ICONS['info']} No service specified, defaulting to temp.sh")
    else:
        for s in args.service:
            raw_services.extend([x.strip() for x in s.split(",") if x.strip()])
        services = [s.lower() for s in raw_services]

    valid_services = {"temp.sh", "bashupload.com", "gdrive", "dropbox", "libgen", "nexus", "scinet"}
    for s in services:
        if s not in valid_services:
            print(f"{ICONS['error']} Invalid service: {s}")
            sys.exit(1)

    if any(s in ["gdrive", "dropbox"] for s in services) and args.verbose:
        print(f"{ICONS['info']} Note: Google Drive and Dropbox services require rclone to be installed and configured. See https://rclone.org/ for instructions.")

    input_paths = [p.strip() for p in args.paths.split(",") if p.strip()]
    files = get_files_from_args(input_paths, args.verbose, args.file_type)
    if not files:
        print(f"{ICONS['error']} No valid files found to upload.")
    for service in services:
        if service == "temp.sh":
            upload_to_tempsh(files, args.verbose)
        elif service == "bashupload.com":
            upload_to_bashupload(files, args.verbose)
        elif service == "gdrive":
            upload_to_gdrive(files, args.remote_path, args.verbose)
        elif service == "dropbox":
            upload_to_dropbox(files, args.remote_path, args.verbose)
        elif service == "libgen":
            upload_to_libgen(files, args.verbose)
        elif service == "nexus":
            asyncio.run(upload_to_nexus_aaron(files, args.verbose))
        elif service == "scinet":
            upload_to_scinet(files, args.verbose)
        elif service == "scinet":
            upload_to_scinet(files, args.verbose)

if __name__ == "__main__":
    main()
