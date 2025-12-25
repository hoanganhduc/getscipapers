"""Utilities for stripping pages and metadata from PDF files.

These functions back the CLI commands that sanitize PDFs before distribution.
They centralize parsing of page ranges and the details of working with
PyMuPDF so other modules can call into them without worrying about low-level
file handling.
"""

import argparse
import os
import re
import tempfile
import shutil
import glob
import fitz  # PyMuPDF

def parse_page_range(page_range_str, num_pages):
    """
    Parse a page range string like "1-3,5,7-9" into a set of zero-based page indices.
    """
    pages = set()
    for part in page_range_str.split(','):
        part = part.strip()
        if '-' in part:
            start, end = part.split('-')
            start = int(start) - 1
            end = int(end) - 1
            pages.update(range(max(start, 0), min(end + 1, num_pages)))
        else:
            idx = int(part) - 1
            if 0 <= idx < num_pages:
                pages.add(idx)
    return pages

def remove_metadata(input_pdf, output_pdf, verbose=False):
    if verbose:
        print(f"Reading input PDF: {input_pdf}")
    
    doc = fitz.open(input_pdf)
    
    if verbose:
        print("Removing metadata...")
    
    # Clear all metadata
    doc.set_metadata({})
    
    if verbose:
        print(f"Writing output PDF: {output_pdf}")
    
    doc.save(output_pdf)
    doc.close()
    
    if verbose:
        print("Done.")

def remove_repeated_images(input_pdf, output_pdf, verbose=False, page_range=None, min_pages_ratio=0.9):
    """
    Remove images that appear on most or all pages (likely watermarks).
    Args:
        input_pdf: Path to input PDF.
        output_pdf: Path to output PDF.
        verbose: Print progress.
        page_range: Optional page range string.
        min_pages_ratio: Ratio of pages an image must appear on to be considered a watermark.
    """
    doc = fitz.open(input_pdf)
    num_pages = len(doc)
    pages_to_process = set(range(num_pages))
    if page_range:
        pages_to_process = parse_page_range(page_range, num_pages)
        if verbose:
            print(f"Processing only pages: {sorted([p+1 for p in pages_to_process])}")

    # Map image xref to set of page indices where it appears
    image_xref_pages = {}
    for i in pages_to_process:
        page = doc[i]
        try:
            images = page.get_images(full=True)
        except Exception as e:
            # If getting images fails for a page, skip it with a warning
            if verbose:
                print(f"Warning: could not list images on page {i+1}: {e}")
            continue
        for img in images:
            # Ensure xref is an integer and skip invalid values
            try:
                xref = int(img[0])
            except Exception:
                continue
            image_xref_pages.setdefault(xref, set()).add(i)

    # Find images that appear on enough pages
    threshold = max(2, int(len(pages_to_process) * min_pages_ratio))
    repeated_xrefs = {xref for xref, pages in image_xref_pages.items() if len(pages) >= threshold}
    if verbose:
        print(f"Images considered as watermark (appear on >= {threshold} pages): {repeated_xrefs}")

    # Actually remove the images by replacing them with white rectangles
    for i in pages_to_process:
        page = doc[i]
        try:
            img_list = page.get_images(full=True)
        except Exception as e:
            if verbose:
                print(f"Warning: could not list images on page {i+1} for redaction: {e}")
            continue
        for img in img_list:
            try:
                xref = int(img[0])
            except Exception:
                continue
            if xref in repeated_xrefs:
                # Find all rectangles for this image on the page
                img_rects = []
                # Check if xref exists in the document before calling image info
                try:
                    if not doc.xref_exists(xref):
                        if verbose:
                            print(f"Warning: xref {xref} not found in document, skipping.")
                        continue
                except Exception as e:
                    # If xref_exists itself fails, skip this xref
                    if verbose:
                        print(f"Warning: error checking xref {xref}: {e}")
                    continue

                # Try to get image placement info using available APIs, fall back to whole page
                try:
                    get_info = getattr(page, "get_image_info", None)
                    if callable(get_info):
                        img_rects = [inst.get("bbox", page.rect) for inst in get_info(xref)]
                    else:
                        # Older/newer PyMuPDF may not provide image bbox info; fall back
                        img_rects = [page.rect]
                except Exception as e:
                    if verbose:
                        print(f"Warning: Could not get image info for xref {xref} on page {i+1}: {e}")
                    img_rects = [page.rect]

                for rect in img_rects:
                    try:
                        # Draw a white rectangle over the image; guard against drawing errors
                        page.draw_rect(rect, color=(1, 1, 1), fill=(1, 1, 1), overlay=True)
                    except Exception as e:
                        if verbose:
                            print(f"Warning: failed to draw rect on page {i+1} for xref {xref}: {e}")
                        # continue to other rects/xrefs

    if verbose:
        print("Removing metadata...")
    try:
        doc.set_metadata({})
    except Exception as e:
        if verbose:
            print(f"Warning: failed to set metadata: {e}")

    if verbose:
        print(f"Writing output PDF: {output_pdf}")
    # Try a normal save first, then retry with garbage cleanup if it fails (helps with broken xref tables).
    # If both fail, rebuild the PDF by copying pages into a new document and save that instead.
    try:
        doc.save(output_pdf)
    except Exception as e:
        if verbose:
            print(f"Warning: save failed: {e}; retrying with garbage cleanup")
        try:
            doc.save(output_pdf, garbage=4)
        except Exception as e2:
            if verbose:
                print(f"Warning: garbage cleanup save failed: {e2}; attempting to rebuild PDF by copying pages into a new document")
            try:
                new_doc = fitz.open()  # create an empty document
                new_doc.insert_pdf(doc)  # copy pages to rebuild xref table
                try:
                    new_doc.set_metadata({})
                except Exception:
                    pass
                new_doc.save(output_pdf)
                new_doc.close()
                if verbose:
                    print("Successfully rebuilt PDF and saved.")
            except Exception as e3:
                if verbose:
                    print(f"Warning: failed to rebuild and save PDF: {e3}")
                doc.close()
                raise
    finally:
        try:
            doc.close()
        except Exception:
            pass

    if verbose:
        print("Done.")

def remove_repeated_text(input_pdf, output_pdf, verbose=False, page_range=None, min_pages_ratio=0.9, min_occurrences=3, min_length=10, position_tolerance=5):
    """
    Remove repeated text fragments that contain private information about the account/institute used to download a paper.
    Only removes fragments matching known private info patterns (not all repeated text).
    """
    # Patterns for private info (account/institute download info)
    private_patterns = [
        re.compile(r"Authorized\s*licensed\s*use\s*limited\s*to:.*?Restrictions\s*apply\.", re.IGNORECASE | re.DOTALL),
        re.compile(r"Downloaded\s*on.*?from\s*IEEE\s*Xplore", re.IGNORECASE | re.DOTALL),
        re.compile(r"Downloaded\s*from\s*.+?\s*on\s*\w+\s*\d{1,2},\s*\d{4}\s*at\s*\d{2}:\d{2}:\d{2}\s*UTC", re.IGNORECASE),
        re.compile(r"Downloaded\s*from\s*.+?\s*on\s*\w+\s*\d{1,2},\s*\d{4}", re.IGNORECASE),
        re.compile(r"Downloaded\s*from\s*.*", re.IGNORECASE),
        re.compile(r"Authorized\s*licensed\s*use\s*limited\s*to:.*?downloaded.*", re.IGNORECASE | re.DOTALL),
        re.compile(r"Licensed\s+to\s+.+?\.\s+Prepared\s+on\s+\w{3}\s+\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2}\s+\w+\s+\d{4}for\s+download\s+from\s+IP\s+\d{1,3}(?:\.\d{1,3}){3}\.", re.IGNORECASE),
        re.compile(r"Licensed\s+to\s+.+?\.\s+Prepared\s+on\s+\w{3}\s+\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2}\s+\w+\s+\d{4}.*?download\s+from\s+IP\s+\d{1,3}(?:\.\d{1,3}){3}\.", re.IGNORECASE),
        re.compile(r"Downloaded\s+via\s+[A-Z][A-Za-z\s\.'&-]+\s+on\s+\w+\s+\d{1,2},?\s+\d{4}\s+at\s+\d{1,2}:\d{2}(?::\d{2})?\s*(?:\(UTC\))?\.", re.IGNORECASE),
        re.compile(r"Downloaded\s+via\s+[A-Z][A-Za-z\s\.'&-]+\s+on\s+\w+.*", re.IGNORECASE),
        re.compile(r"Downloaded\s+by\s+\[\s*\"?[^\]]+\"?\s*\]\s+on\s+\[\s*[\d/]+\s*\]\.", re.IGNORECASE),
        re.compile(
            r"by\s+([A-Z][A-Za-z&\-\s\.']+University|[A-Z][A-Za-z&\-\s\.']+UNIVERSITY|[A-Z\s]+UNIVERSITY)\s+on\s+\d{2}/\d{2}/\d{2,4}\.\s*Re-use\s+and\s+distribution\s+is\s+strictly\s+not\s+permitted,?\s*except\s+for\s+Open\s+Access\s+articles\.?",
            re.IGNORECASE
        ),
        re.compile(
            r"by\s+([A-Z][A-Za-z&\-\s\.']+University|[A-Z][A-Za-z&\-\s\.']+UNIVERSITY|[A-Z\s]+UNIVERSITY)\s+on\s+\d{2}/\d{2}/\d{2,4}\.",
            re.IGNORECASE
        ),
        re.compile(
            r"Downloaded\s+by\s+([A-Z][A-Za-z&\-\s\.']+University|[A-Z][A-Za-z&\-\s\.']+UNIVERSITY|[A-Z\s]+UNIVERSITY)[^\.]*\.",
            re.IGNORECASE
        ),
        re.compile(
            r"Downloaded\s+for\s+([A-Z][A-Za-z&\-\s\.']+University|[A-Z][A-Za-z&\-\s\.']+UNIVERSITY|[A-Z\s]+UNIVERSITY)[^\.]*\.",
            re.IGNORECASE
        ),
        re.compile(r"via\s+[A-Z][A-Za-z\s\.'&-]+\s+University\s+(?:Main\s+)?Library", re.IGNORECASE),
        re.compile(r"via\s+[A-Z][A-Za-z\s\.'&-]+\s+College\s+(?:Main\s+)?Library", re.IGNORECASE),
        re.compile(r"via\s+[A-Z][A-Za-z\s\.'&-]+\s+Libraries", re.IGNORECASE),
    ]

    if verbose:
        print(f"Reading input PDF: {input_pdf}")

    doc = fitz.open(input_pdf)
    num_pages = len(doc)
    pages_to_process = set(range(num_pages))

    if page_range:
        pages_to_process = parse_page_range(page_range, num_pages)
        if verbose:
            print(f"Processing only pages: {sorted([p+1 for p in pages_to_process])}")

    # Track text fragments by content and position
    text_positions = {}

    # Extract text with positions from each page
    for i in pages_to_process:
        page = doc[i]
        for line in page.get_text().split('\n'):
            line = line.strip()
            if len(line) >= min_length:
                # Only consider lines matching private info patterns
                if not any(pat.search(line) for pat in private_patterns):
                    continue
                rects = page.search_for(line)
                if rects is None:
                    continue
                for rect in rects:
                    position_key = (
                        round(rect.x0 / position_tolerance) * position_tolerance,
                        round(rect.y0 / position_tolerance) * position_tolerance
                    )
                    if line not in text_positions:
                        text_positions[line] = {}
                    if position_key not in text_positions[line]:
                        text_positions[line][position_key] = set()
                    text_positions[line][position_key].add(i)

    # Identify text that appears at the same position on multiple pages
    repeated_fragments = {}
    threshold_pages = max(min_occurrences, int(len(pages_to_process) * min_pages_ratio))
    for text, positions in text_positions.items():
        for pos, pages in positions.items():
            if len(pages) >= threshold_pages:
                repeated_fragments[(text, pos)] = pages

    if verbose:
        print(f"Found {len(repeated_fragments)} private info text fragments appearing at the same position on at least {threshold_pages} pages")
        for (fragment, pos), pages in list(repeated_fragments.items())[:5]:
            truncated = fragment[:50] + ('...' if len(fragment) > 50 else '')
            print(f"- '{truncated}' at position {pos} appears on {len(pages)} pages")

    # Remove repeated text fragments
    for i in pages_to_process:
        page = doc[i]
        redact_count = 0
        for (fragment, pos), pages in repeated_fragments.items():
            if i in pages:
                instances = page.search_for(fragment)
                for inst in instances:
                    instance_pos = (
                        round(inst.x0 / position_tolerance) * position_tolerance,
                        round(inst.y0 / position_tolerance) * position_tolerance
                    )
                    if instance_pos == pos:
                        annot = page.add_redact_annot(inst)
                        annot.set_colors(stroke=None, fill=(1, 1, 1))
                        annot.update()
                        redact_count += 1
        if redact_count > 0:
            page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)
            if verbose:
                print(f"Page {i+1}: Removed {redact_count} private info text instances")

    if verbose:
        print("Removing metadata...")
    doc.set_metadata({})

    if verbose:
        print(f"Writing output PDF: {output_pdf}")

    doc.save(output_pdf)
    doc.close()

    if verbose:
        print("Done.")

def remove_watermark(input_pdf, output_pdf, watermark_patterns=None, verbose=False, page_range=None):
    if watermark_patterns is None:
        watermark_patterns = [
            # IEEE Xplore style watermarks
            re.compile(r"Authorized\s*licensed\s*use\s*limited\s*to:.*?Restrictions\s*apply\.", re.IGNORECASE | re.DOTALL),
            re.compile(r"Downloaded\s*on.*?from\s*IEEE\s*Xplore", re.IGNORECASE | re.DOTALL),
            re.compile(r"Downloaded\s*from\s*.+?\s*on\s*\w+\s*\d{1,2},\s*\d{4}\s*at\s*\d{2}:\d{2}:\d{2}\s*UTC", re.IGNORECASE),
            re.compile(r"Downloaded\s*from\s*.+?\s*on\s*\w+\s*\d{1,2},\s*\d{4}", re.IGNORECASE),
            re.compile(r"Downloaded\s*from\s*.*", re.IGNORECASE),
            re.compile(r"Authorized\s*licensed\s*use\s*limited\s*to:.*?downloaded.*", re.IGNORECASE | re.DOTALL),

            # Licensed to ... Prepared on ... for download from IP ...
            re.compile(
            r"Licensed\s+to\s+.+?\.\s+Prepared\s+on\s+\w{3}\s+\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2}\s+\w+\s+\d{4}for\s+download\s+from\s+IP\s+\d{1,3}(?:\.\d{1,3}){3}\.",
            re.IGNORECASE
            ),
            re.compile(
            r"Licensed\s+to\s+.+?\.\s+Prepared\s+on\s+\w{3}\s+\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2}\s+\w+\s+\d{4}.*?download\s+from\s+IP\s+\d{1,3}(?:\.\d{1,3}){3}\.",
            re.IGNORECASE
            ),

            # Additional publisher watermarks
            re.compile(r"Downloaded\s*from\s*ScienceDirect.*", re.IGNORECASE),
            re.compile(r"©\s*\d{4}\s*Elsevier\s*Ltd\.", re.IGNORECASE),
            re.compile(r"Provided\s*by\s*.+?\s*Library", re.IGNORECASE),
            re.compile(r"Downloaded\s*on\s*.+?\s*from\s*SpringerLink", re.IGNORECASE),
            re.compile(r"Copyright\s*ACM.*For\s*personal\s*use", re.IGNORECASE | re.DOTALL),
            re.compile(r"This\s*content\s*downloaded\s*from", re.IGNORECASE),
            re.compile(r"Downloaded\s*by\s*.+?\s*at\s*", re.IGNORECASE),
            re.compile(r"Downloaded\s*from\s*Cambridge\s*Core", re.IGNORECASE),
            re.compile(r"Downloaded\s*from\s*Wiley\s*Online\s*Library", re.IGNORECASE),
            re.compile(r"For\s*Review\s*Only", re.IGNORECASE),

            # SIAM watermarks
            re.compile(r"Downloaded\s*\d{2}/\d{2}/\d{2}\s*to\s*\d+\.\d+\.\d+\.\d+.*Redistribution\s*subject\s*to\s*SIAM\s*license\s*or\s*copyright;\s*see\s*https://epubs\.siam\.org/terms-privacy", re.IGNORECASE),
            re.compile(r"Copyright.*by\s*SIAM\.\s*Unauthorized\s*reproduction\s*of\s*this\s*article\s*is\s*prohibited", re.IGNORECASE),

            # MR reference review watermark
            re.compile(r"\[\s*MR\d+.*?for\s*reviewing\s*purposes\s*only\s*\]", re.IGNORECASE),
            re.compile(r"\[\s*Review\s+Copy\s+Only\s*\]", re.IGNORECASE),

            # University download watermarks (considering all possible displaying of university names)
            re.compile(
            r"by\s+([A-Z][A-Za-z&\-\s\.']+University|[A-Z][A-Za-z&\-\s\.']+UNIVERSITY|[A-Z\s]+UNIVERSITY)\s+on\s+\d{2}/\d{2}/\d{2,4}\.\s*Re-use\s+and\s+distribution\s+is\s+strictly\s+not\s+permitted,?\s*except\s+for\s+Open\s+Access\s+articles\.?",
            re.IGNORECASE
            ),
            re.compile(
            r"by\s+([A-Z][A-Za-z&\-\s\.']+University|[A-Z][A-Za-z&\-\s\.']+UNIVERSITY|[A-Z\s]+UNIVERSITY)\s+on\s+\d{2}/\d{2}/\d{2,4}\.",
            re.IGNORECASE
            ),
            re.compile(
            r"Downloaded\s+by\s+([A-Z][A-Za-z&\-\s\.']+University|[A-Z][A-Za-z&\-\s\.']+UNIVERSITY|[A-Z\s]+UNIVERSITY)[^\.]*\.",
            re.IGNORECASE
            ),
            re.compile(
            r"Downloaded\s+for\s+([A-Z][A-Za-z&\-\s\.']+University|[A-Z][A-Za-z&\-\s\.']+UNIVERSITY|[A-Z\s]+UNIVERSITY)[^\.]*\.",
            re.IGNORECASE
            ),

            # ACS publications sharing guidelines watermark
            re.compile(r"See\s+https://pubs\.acs\.org/sharingguidelines\s+for\s+options\s+on\s+how\s+to\s+legitimately\s+share\s+published\s+articles\.", re.IGNORECASE),

            # Chemistry Europe Online Library patterns
            re.compile(r"\d+,\s*ja,\s*Downloaded\s+from\s+https://chemistry-europe\.onlinelibrary.*", re.IGNORECASE),
            re.compile(r"Downloaded\s+from\s+https://chemistry-europe\.onlinelibrary.*", re.IGNORECASE),
            # Standalone article identifier pattern (new)
            re.compile(r"\d+,\s*ja,", re.IGNORECASE),
            # General pattern for article identifiers followed by download info
            re.compile(r"\d+,\s*[a-z]{1,4},\s*Downloaded\s+from\s+.*", re.IGNORECASE),
            
            # Downloaded via INSTITUTION patterns
            re.compile(r"Downloaded\s+via\s+[A-Z][A-Za-z\s\.'&-]+\s+on\s+\w+\s+\d{1,2},?\s+\d{4}\s+at\s+\d{1,2}:\d{2}(?::\d{2})?\s*(?:\(UTC\))?\.", re.IGNORECASE),
            re.compile(r"Downloaded\s+via\s+[A-Z][A-Za-z\s\.'&-]+\s+on\s+\w+.*", re.IGNORECASE),

            # OUP Academic watermark (improved)
            re.compile(
            r"Downloaded\s+from\s+https://academic\.oup\.com/.*?by\s+.*?user\s+on\s+\d{1,2}\s+\w+\s+\d{4}",
            re.IGNORECASE
            ),
            # More general OUP pattern to catch variations
            re.compile(
            r"Downloaded\s+from\s+https://academic\.oup\.com/.*",
            re.IGNORECASE
            ),
            
            # Pattern for "Downloaded by [ "Institution"] on [Date]" format
            re.compile(r"Downloaded\s+by\s+\[\s*\"?[^\]]+\"?\s*\]\s+on\s+\[\s*[\d/]+\s*\]\.", re.IGNORECASE),
            
            # General University Library patterns
            re.compile(r"via\s+[A-Z][A-Za-z\s\.'&-]+\s+University\s+(?:Main\s+)?Library", re.IGNORECASE),
            re.compile(r"via\s+[A-Z][A-Za-z\s\.'&-]+\s+College\s+(?:Main\s+)?Library", re.IGNORECASE),
            re.compile(r"via\s+[A-Z][A-Za-z\s\.'&-]+\s+Libraries", re.IGNORECASE),
        ]
    
    # Enhanced DOI pattern to match any DOI format (with or without prefix)
    doi_pattern = re.compile(r'(?:doi:?\s*|DOI\s+|https?://(?:dx\.)?doi\.org/)?10\.\d{4,9}/[-._;()/:a-zA-Z0-9]+', re.IGNORECASE)

    if verbose:
        print(f"Reading input PDF: {input_pdf}")

    # First, remove repeated images (likely watermarks)
    with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp_img_file:
        tmp_img_pdf = tmp_img_file.name

    if verbose:
        print("Step 1: Removing repeated images (possible image watermarks)...")
    remove_repeated_images(
        input_pdf,
        tmp_img_pdf,
        verbose=verbose,
        page_range=page_range
    )

    # Next, remove repeated text patterns (likely headers, footers)
    with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp_text_file:
        tmp_text_pdf = tmp_text_file.name

    if verbose:
        print("Step 2: Removing repeated text (possible header/footer watermarks)...")
    remove_repeated_text(
        tmp_img_pdf,
        tmp_text_pdf,
        verbose=verbose,
        page_range=page_range
    )

    # Clean up the first temporary file
    try:
        os.unlink(tmp_img_pdf)
        if verbose:
            print(f"Deleted temporary file: {tmp_img_pdf}")
    except Exception as e:
        if verbose:
            print(f"Could not delete temporary file {tmp_img_pdf}: {e}")

    # Use the new temporary file for the next steps
    tmp_img_pdf = tmp_text_pdf

    doc = fitz.open(tmp_img_pdf)
    num_pages = len(doc)
    pages_to_process = set(range(num_pages))
    if page_range:
        pages_to_process = parse_page_range(page_range, num_pages)
        if verbose:
            print(f"Processing only pages: {sorted([p+1 for p in pages_to_process])}")

    total_watermarks_found = 0
    total_watermarks_redacted = 0

    for i in range(num_pages):
        if i not in pages_to_process:
            continue
        page = doc[i]
        if verbose:
            print(f"Step 3: Processing page {i+1}/{num_pages}")

        # Extract text
        text = page.get_text()

        # Search for watermark patterns
        for pattern_idx, pattern in enumerate(watermark_patterns):
            matches = list(pattern.finditer(text))
            if verbose and matches:
                print(f"  Pattern {pattern_idx+1}/{len(watermark_patterns)}: {pattern.pattern}")
                print(f"    Found {len(matches)} matches")
            for match_idx, match in enumerate(matches):
                matched_text = match.group()
                total_watermarks_found += 1

                # Skip if the text contains a DOI, unless it's from specific sources we want to remove
                if doi_pattern.search(matched_text) and not ("academic.oup.com" in matched_text or 
                                                            "aacrjournals.org" in matched_text or
                                                            "onlinelibrary.wiley.com" in matched_text):
                    if verbose:
                        print(f"    Skipping watermark containing DOI: {matched_text[:80]}{'...' if len(matched_text)>80 else ''}")
                    continue

                if verbose:
                    print(f"    Watermark match {match_idx+1}: {matched_text[:80]}{'...' if len(matched_text)>80 else ''}")

                # Search for the text on the page
                text_instances = page.search_for(matched_text)
                if verbose:
                    print(f"      Found {len(text_instances)} instance(s) on page for redaction.")

                # To avoid white boxes, use redaction with fill=None and keep_appearance=True,
                # which tries to preserve the background as much as possible.
                for inst_idx, inst in enumerate(text_instances):
                    annot = page.add_redact_annot(inst)
                    annot.set_colors(stroke=None, fill=None)
                    annot.update()
                    total_watermarks_redacted += 1
                    if verbose:
                        print(f"        Redacted instance {inst_idx+1}: {inst}")

                # Apply all redactions on the page
                if text_instances:
                    page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)
                    if verbose:
                        print(f"      Applied redactions for this match.")

    # Remove metadata
    if verbose:
        print("Step 4: Removing metadata...")
    doc.set_metadata({})

    if verbose:
        print(f"Step 5: Writing output PDF: {output_pdf}")
        print(f"Summary: {total_watermarks_found} watermark(s) found, {total_watermarks_redacted} instance(s) redacted.")

    doc.save(output_pdf)
    doc.close()

    # Clean up temporary file
    try:
        os.unlink(tmp_img_pdf)
        if verbose:
            print(f"Deleted temporary file: {tmp_img_pdf}")
    except Exception as e:
        if verbose:
            print(f"Could not delete temporary file {tmp_img_pdf}: {e}")

    if verbose:
        print("Done.")

def remove_watermark_inplace(input_pdf, verbose=False, page_range=None):
    """
    Remove watermarks from a PDF file in-place.
    """
    with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp_file:
        temp_output = tmp_file.name

    remove_watermark(
        input_pdf,
        temp_output,
        verbose=verbose,
        page_range=page_range
    )

    shutil.move(temp_output, input_pdf)

def collect_pdf_files(input_arg):
    # If it's a directory, recursively find all PDFs
    if os.path.isdir(input_arg):
        pdfs = []
        for root, _, files in os.walk(input_arg):
            for f in files:
                if f.lower().endswith('.pdf'):
                    pdfs.append(os.path.join(root, f))
        return pdfs
    # If it's a file, just return it
    elif os.path.isfile(input_arg) and input_arg.lower().endswith('.pdf'):
        return [input_arg]
    # If it's a list (comma or space separated), split and collect
    else:
        # Try comma or space split
        parts = re.split(r'[,\s]+', input_arg.strip())
        pdfs = []
        for part in parts:
            if not part:
                continue
            if os.path.isdir(part):
                pdfs.extend(collect_pdf_files(part))
            elif os.path.isfile(part) and part.lower().endswith('.pdf'):
                pdfs.append(part)
        return pdfs

def main():
    parent_package = __name__.split('.')[0] if '.' in __name__ else None

    if parent_package is None:
        program_name = 'remove_metadata'
    elif '_' in parent_package:
        parent_package = parent_package[:parent_package.index('_')]
        program_name = f"{parent_package} remove_metadata"

    parser = argparse.ArgumentParser(
        prog=program_name,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Remove metadata and watermarks from PDF(s) while preserving clickable URLs and selectable text.",
        epilog="""
Examples:
  %(prog)s input.pdf
  %(prog)s input1.pdf,input2.pdf
  %(prog)s input1.pdf input2.pdf
  %(prog)s folder_with_pdfs/
  %(prog)s input.pdf --inplace
  %(prog)s folder_with_pdfs/ -v -p "1-3,5,7-9"
"""
    )
    parser.add_argument("input_pdf", help="Input PDF file, comma/space-separated list, or folder")
    parser.add_argument(
        "-i", "--inplace", action="store_true", help="Overwrite the input PDF file(s)"
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Print progress details"
    )
    parser.add_argument(
        "-p", "--watermark-pages", type=str, default=None,
        help="Page range to remove watermarks, e.g. '1-3,5,7-9' (1-based)"
    )
    args, extra = parser.parse_known_args()

    # Support space-separated files as extra arguments
    input_args = [args.input_pdf] + extra
    pdf_files = []
    for arg in input_args:
        pdf_files.extend(collect_pdf_files(arg))

    if not pdf_files:
        print("No PDF files found to process.")
        return

    for pdf_path in pdf_files:
        print(f"Processing file: {pdf_path}")
        try:
            with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp_file:
                temp_output = tmp_file.name

            remove_watermark(
                pdf_path,
                temp_output,
                verbose=args.verbose,
                page_range=args.watermark_pages
            )

            if args.inplace:
                shutil.move(temp_output, pdf_path)
                output_pdf = pdf_path
            else:
                base, ext = os.path.splitext(pdf_path)
                output_pdf = f"{base}_no_metadata{ext}"
                shutil.move(temp_output, output_pdf)

            print(f"Successfully processed PDF. Output saved to: {output_pdf}")
        except Exception as e:
            if 'temp_output' in locals():
                try:
                    os.unlink(temp_output)
                except:
                    pass
            print(f"Failed to process PDF {pdf_path}: {e}")

if __name__ == "__main__":
    main()