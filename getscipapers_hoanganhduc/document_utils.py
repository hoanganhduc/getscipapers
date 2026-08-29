"""Shared helpers for validating downloaded document files.

Paper and book sources routinely answer a download request with an HTML
interstitial, a login form or an error page while still returning HTTP 200, so
a response body has to be inspected before it is kept as a download. Sources
such as LibGen and Z-Library also serve formats other than PDF, so validation
is driven by the extension of the target file.
"""

import os

PDF_HEADER = b"%PDF-"


def looks_like_pdf(data: bytes) -> bool:
    """
    Return True if the given bytes look like a real PDF file.

    The header is allowed to appear after a small amount of leading junk, which
    some servers prepend.
    """
    if not data:
        return False
    return PDF_HEADER in data[:1024]


def looks_like_html(data: bytes) -> bool:
    """
    Return True if the given bytes look like an HTML page rather than a document.
    """
    if not data:
        return False
    head = data[:1024].lstrip().lower()
    if head.startswith(b"<!doctype html") or head.startswith(b"<html"):
        return True
    # Interstitials and error pages sometimes open with another tag first.
    return head.startswith(b"<") and (
        b"<html" in head or b"<head" in head or b"<body" in head
    )


def content_is_valid_download(data: bytes, filepath: str) -> bool:
    """
    Return True if the downloaded bytes are acceptable for the target file.

    A file named ``.pdf`` must really be a PDF. Other extensions are used for
    the ebook formats that LibGen and Z-Library serve, so those only have to be
    non-empty and not an HTML page.
    """
    if not data:
        return False
    if os.path.splitext(filepath)[1].lower() == ".pdf":
        return looks_like_pdf(data)
    return not looks_like_html(data)


def save_document_if_valid(data: bytes, filepath: str) -> bool:
    """
    Write the downloaded bytes to filepath only when they are a valid document.

    Returns True when the file was written, and False otherwise so that the
    caller can keep trying the remaining sources instead of counting a rejected
    page as a successful download.
    """
    if not content_is_valid_download(data, filepath):
        return False
    with open(filepath, "wb") as f:
        f.write(data)
    return True


def discard_invalid_download(filepath: str) -> bool:
    """
    Check an already written download and remove it when it is not a document.

    This is the streaming counterpart of save_document_if_valid, for callers
    that write the response in chunks. Returns True when the file is kept.
    """
    try:
        with open(filepath, "rb") as f:
            head = f.read(1024)
    except OSError:
        return False
    if content_is_valid_download(head, filepath):
        return True
    try:
        os.remove(filepath)
    except OSError:
        pass
    return False
