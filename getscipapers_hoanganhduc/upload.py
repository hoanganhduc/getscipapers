import sys
import os
import argparse
import subprocess
import requests

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

def get_files_from_args(paths, verbose=False):
    files = []
    for path in paths:
        if os.path.isdir(path):
            if verbose:
                print(f"{ICONS['info']} Scanning directory: {path}")
            for entry in os.listdir(path):
                full_path = os.path.join(path, entry)
                if os.path.isfile(full_path):
                    files.append(full_path)
        elif os.path.isfile(path):
            files.append(path)
        else:
            if verbose:
                print(f"{ICONS['warning']} Warning: {path} is not a valid file or directory, skipping.")
    return files

def upload_to_tempsh(files, verbose=False):
    import requests
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
    for file_path in files:
        if verbose:
            print(f"{ICONS['check']} Checking if {file_path} exists...")
        if not os.path.exists(file_path):
            print(f"{ICONS['error']} Error: {file_path} does not exist")
            continue
        if remote_path is None:
            remote = os.path.basename(file_path)
            if verbose:
                print(f"{ICONS['info']} No remote path specified, using: {remote}")
        else:
            remote = remote_path
        destination = f"gdrive:{remote}"
        if verbose:
            print(f"{ICONS['sync']} Syncing {file_path} to Google Drive as {remote}...")
            print(f"{ICONS['warning']} Warning: Files/folders in destination that don't exist in source will be deleted.")
        run_command(["rclone", "sync", file_path, destination, "--progress"], verbose)
        if verbose:
            print(f"{ICONS['success']} Sync to {destination} completed")
        shareable_link = share_gdrive_item(destination, verbose)
        print(f"{ICONS['success']} Upload complete!")
        print(f"{ICONS['link']} Shareable link: {shareable_link}")

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
    for file_path in files:
        if verbose:
            print(f"{ICONS['check']} Checking if {file_path} exists...")
        if not os.path.exists(file_path):
            print(f"{ICONS['error']} Error: {file_path} does not exist")
            continue
        if remote_path is None:
            remote = os.path.basename(file_path)
            if verbose:
                print(f"{ICONS['info']} No remote path specified, using: {remote}")
        else:
            remote = remote_path
        destination = f"dropbox:{remote}"
        if verbose:
            print(f"{ICONS['sync']} Syncing {file_path} to Dropbox as {remote}...")
            print(f"{ICONS['warning']} Warning: Files/folders in destination that don't exist in source will be deleted.")
        run_command(["rclone", "sync", file_path, destination, "--progress"], verbose)
        if verbose:
            print(f"{ICONS['success']} Sync to {destination} completed")
        shareable_link = share_dropbox_item(destination, verbose)
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
            result = libgen.upload_and_register_to_libgen(filepath=file_path)
            if result.get("success"):
                print(f"{ICONS['success']} {file_name} uploaded to LibGen: {ICONS['link']} {result.get('url', 'No URL returned')}")
            else:
                print(f"{ICONS['error']} Failed to upload {file_name} to LibGen: {result.get('error', 'Unknown error')}")
        except Exception as e:
            print(f"{ICONS['error']} Exception uploading {file_name} to LibGen: {e}")

def upload_to_nexus_aaron(files, verbose=False):
    for file_path in files:
        file_name = os.path.basename(file_path)
        if verbose:
            print(f"{ICONS['upload']} Uploading {file_name} to nexus_aaron bot...")
        try:
            result = nexus.simple_upload_to_nexus_aaron(file_path)
            if result.get("success"):
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
            if result.get("success"):
                print(f"{ICONS['success']} {file_name} uploaded to SciNet: {ICONS['link']} {result.get('url', 'No URL returned')}")
            else:
                print(f"{ICONS['error']} Failed to upload {file_name} to SciNet: {result.get('error', 'Unknown error')}")
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
"""
    )
    parser.add_argument(
        "paths",
        help="Comma-separated list of files or directories to upload"
    )
    parser.add_argument(
        "--service",
        nargs="+",
        required=True,
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
    files = get_files_from_args(input_paths, args.verbose)
    if not files:
        print(f"{ICONS['error']} No valid files found to upload.")
        sys.exit(1)

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
            upload_to_nexus_aaron(files, args.verbose)
        elif service == "scinet":
            upload_to_scinet(files, args.verbose)

if __name__ == "__main__":
    main()
