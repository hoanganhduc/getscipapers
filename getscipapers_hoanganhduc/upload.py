import sys
import os
import argparse
import subprocess
"""upload.py - A script to upload files to various services like temp.sh, bashupload.com, Google Drive, and Dropbox.
This script allows users to upload files or directories to specified services and provides shareable links."""

# Icons for prettier messages
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

def get_files_from_args(paths):
    files = []
    for path in paths:
        if os.path.isdir(path):
            for entry in os.listdir(path):
                full_path = os.path.join(path, entry)
                if os.path.isfile(full_path):
                    files.append(full_path)
        elif os.path.isfile(path):
            files.append(path)
        else:
            print(f"{ICONS['warning']} Warning: {path} is not a valid file or directory, skipping.")
    return files

def upload_to_tempsh(files):
    import requests
    for file_path in files:
        file_name = os.path.basename(file_path)
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

def upload_to_bashupload(files):
    import requests
    for file_path in files:
        file_name = os.path.basename(file_path)
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
    """Run a shell command and return its output"""
    if verbose:
        print(f"{ICONS['info']} Executing: {' '.join(command)}")
    try:
        result = subprocess.run(command, check=True, text=True, capture_output=True)
        if verbose and result.stdout:
            print(f"{ICONS['info']} {result.stdout}")
        return result.stdout
    except subprocess.CalledProcessError as e:
        print(f"{ICONS['error']} Error executing command: {' '.join(command)}")
        print(f"{ICONS['error']} Error message: {e.stderr}")
        sys.exit(1)

def upload_to_gdrive(files, remote_path=None, verbose=False):
    """Sync files to Google Drive using rclone and print shareable links."""
    print(f"{ICONS['info']} Note: This function requires rclone to be installed and configured with your Google account.")
    print(f"{ICONS['info']} See https://rclone.org/drive/ for setup instructions.")
    for file_path in files:
        if verbose:
            print(f"{ICONS['check']} Checking if {file_path} exists...")
        if not os.path.exists(file_path):
            print(f"{ICONS['error']} Error: {file_path} does not exist")
            continue
        # If no remote path is specified, use the basename of the local path
        if remote_path is None:
            remote = os.path.basename(file_path)
            if verbose:
                print(f"{ICONS['info']} No remote path specified, using: {remote}")
        else:
            remote = remote_path
        destination = f"gdrive:{remote}"
        print(f"{ICONS['sync']} Syncing {file_path} to Google Drive as {remote}...")
        print(f"{ICONS['warning']} Warning: Files/folders in destination that don't exist in source will be deleted.")
        run_command(["rclone", "sync", file_path, destination, "--progress"], verbose)
        if verbose:
            print(f"{ICONS['success']} Sync to {destination} completed")
        # Share the file/folder and get the link
        shareable_link = share_gdrive_item(destination, verbose)
        print(f"{ICONS['success']} Upload complete!")
        print(f"{ICONS['link']} Shareable link: {shareable_link}")

def share_gdrive_item(gdrive_path, verbose=False):
    """Share a Google Drive item and return the shareable link"""
    # Remove 'gdrive:' prefix if present
    gdrive_path = gdrive_path.replace("gdrive:", "", 1)
    if verbose:
        print(f"{ICONS['info']} Preparing to share: {gdrive_path}")
    # Create a shareable link
    command = ["rclone", "link", f"gdrive:{gdrive_path}"]
    print(f"{ICONS['link']} Creating shareable link for {gdrive_path}...")
    shareable_link = run_command(command, verbose).strip()
    return shareable_link

def upload_to_dropbox(files, remote_path=None, verbose=False):
    """Sync files to Dropbox using rclone and print shareable links."""
    print(f"{ICONS['info']} Note: This function requires rclone to be installed and configured with your Dropbox account.")
    print(f"{ICONS['info']} See https://rclone.org/dropbox/ for setup instructions.")
    for file_path in files:
        if verbose:
            print(f"{ICONS['check']} Checking if {file_path} exists...")
        if not os.path.exists(file_path):
            print(f"{ICONS['error']} Error: {file_path} does not exist")
            continue
        # If no remote path is specified, use the basename of the local path
        if remote_path is None:
            remote = os.path.basename(file_path)
            if verbose:
                print(f"{ICONS['info']} No remote path specified, using: {remote}")
        else:
            remote = remote_path
        destination = f"dropbox:{remote}"
        print(f"{ICONS['sync']} Syncing {file_path} to Dropbox as {remote}...")
        print(f"{ICONS['warning']} Warning: Files/folders in destination that don't exist in source will be deleted.")
        run_command(["rclone", "sync", file_path, destination, "--progress"], verbose)
        if verbose:
            print(f"{ICONS['success']} Sync to {destination} completed")
        # Share the file/folder and get the link
        shareable_link = share_dropbox_item(destination, verbose)
        print(f"{ICONS['success']} Upload complete!")
        print(f"{ICONS['link']} Shareable link: {shareable_link}")

def share_dropbox_item(dropbox_path, verbose=False):
    """Share a Dropbox item and return the shareable link"""
    # Remove 'dropbox:' prefix if present
    dropbox_path = dropbox_path.replace("dropbox:", "", 1)
    if verbose:
        print(f"{ICONS['info']} Preparing to share: {dropbox_path}")
    # Create a shareable link
    command = ["rclone", "link", f"dropbox:{dropbox_path}"]
    print(f"{ICONS['link']} Creating shareable link for {dropbox_path}...")
    shareable_link = run_command(command, verbose).strip()
    return shareable_link

def main():
    # Get the parent package name from the module's __name__
    parent_package = __name__.split('.')[0] if '.' in __name__ else None

    if parent_package is None:
        program_name = 'upload'
    elif '_' in parent_package:
        # If the parent package has an underscore, strip it
        parent_package = parent_package[:parent_package.index('_')]
        program_name = f"{parent_package} upload"
        
    parser = argparse.ArgumentParser(
        prog=program_name, 
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Upload files to temp.sh, bashupload.com, Google Drive, or Dropbox",
        epilog="""
Examples:
  %(prog)s myfile.txt --service temp.sh
  %(prog)s "folder1,file2.pdf" --service bashupload.com
  %(prog)s myfolder --service gdrive --remote-path backup/myfolder
  %(prog)s file.txt --service dropbox --remote-path shared/file.txt -v
"""
    )
    parser.add_argument(
        "paths",
        help="Comma-separated list of files or directories to upload"
    )
    parser.add_argument(
        "--service",
        choices=["temp.sh", "bashupload.com", "gdrive", "dropbox"],
        default="temp.sh",
        help="Choose upload service (default: temp.sh)"
    )
    parser.add_argument(
        "--remote-path",
        help="Destination path in Google Drive/Dropbox (only for gdrive/dropbox service)"
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Print detailed progress information (gdrive/dropbox only)"
    )
    args = parser.parse_args()

    if args.service in ["gdrive", "dropbox"]:
        print(f"{ICONS['info']} Note: Google Drive and Dropbox services require rclone to be installed and configured. See https://rclone.org/ for instructions.")

    input_paths = [p.strip() for p in args.paths.split(",") if p.strip()]
    files = get_files_from_args(input_paths)
    if not files:
        print(f"{ICONS['error']} No valid files found to upload.")
        sys.exit(1)

    if args.service == "temp.sh":
        upload_to_tempsh(files)
    elif args.service == "bashupload.com":
        upload_to_bashupload(files)
    elif args.service == "gdrive":
        upload_to_gdrive(files, args.remote_path, args.verbose)
    elif args.service == "dropbox":
        upload_to_dropbox(files, args.remote_path, args.verbose)

if __name__ == "__main__":
    main()
