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
        for img in page.get_images(full=True):
            xref = img[0]
            image_xref_pages.setdefault(xref, set()).add(i)

    # Find images that appear on enough pages
    threshold = max(2, int(len(pages_to_process) * min_pages_ratio))
    repeated_xrefs = {xref for xref, pages in image_xref_pages.items() if len(pages) >= threshold}
    if verbose:
        print(f"Images considered as watermark (appear on >= {threshold} pages): {repeated_xrefs}")

    # Actually remove the images by replacing them with white rectangles
    for i in pages_to_process:
        page = doc[i]
        img_list = page.get_images(full=True)
        for img in img_list:
            xref = img[0]
            if xref in repeated_xrefs:
                # Find all rectangles for this image on the page
                img_rects = []
                # Use get_image_info if available, else fallback to guessing
                try:
                    img_rects = [inst["bbox"] for inst in page.get_image_info(xref)]
                except Exception:
                    # Fallback: use the whole page (not ideal)
                    img_rects = [page.rect]
                for rect in img_rects:
                    # Draw a white rectangle over the image
                    page.draw_rect(rect, color=(1, 1, 1), fill=(1, 1, 1), overlay=True)
    if verbose:
        print("Removing metadata...")
    doc.set_metadata({})
    if verbose:
        print(f"Writing output PDF: {output_pdf}")
    doc.save(output_pdf)
    doc.close()
    if verbose:
        print("Done.")

def remove_repeated_text(input_pdf, output_pdf, verbose=False, page_range=None, min_pages_ratio=0.9, min_occurrences=3, min_length=10, position_tolerance=5):
    """
    Remove text patterns that appear at the same position on multiple pages (likely headers, footers, watermarks).
    
    Args:
        input_pdf: Path to input PDF
        output_pdf: Path to output PDF
        verbose: Print progress information
        page_range: Optional page range string (e.g. "1-5,7,9-12")
        min_pages_ratio: Ratio of pages a text must appear on to be considered for removal
        min_occurrences: Minimum number of occurrences across all pages
        min_length: Minimum length of text to consider (to avoid removing short common words)
        position_tolerance: Tolerance in points for position matching
    """
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
    # Format: {text: {position_key: set(page_indices)}}
    text_positions = {}
    
    # Extract text with positions from each page
    for i in pages_to_process:
        page = doc[i]
        
        # Extract potential repeating text (longer than min_length)
        words = page.get_text("words")
        for line in page.get_text().split('\n'):
            line = line.strip()
            if len(line) >= min_length:
                # Find position of this line
                rects = page.search_for(line)
                for rect in rects:
                    # Create position key (rounded to handle small differences)
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
    repeated_fragments = {}  # {(text, position): set(pages)}
    
    threshold_pages = max(min_occurrences, int(len(pages_to_process) * min_pages_ratio))
    
    for text, positions in text_positions.items():
        for pos, pages in positions.items():
            if len(pages) >= threshold_pages:
                repeated_fragments[(text, pos)] = pages
    
    if verbose:
        print(f"Found {len(repeated_fragments)} text fragments appearing at the same position on at least {threshold_pages} pages")
        for (fragment, pos), pages in list(repeated_fragments.items())[:5]:
            truncated = fragment[:50] + ('...' if len(fragment) > 50 else '')
            print(f"- '{truncated}' at position {pos} appears on {len(pages)} pages")
    
    # Remove repeated text fragments
    for i in pages_to_process:
        page = doc[i]
        redact_count = 0
        
        # Process each repeated fragment
        for (fragment, pos), pages in repeated_fragments.items():
            if i in pages:
                # Search for this text on the page
                instances = page.search_for(fragment)
                
                # Only redact instances that match the position (with tolerance)
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
        
        # Apply all redactions at once
        if redact_count > 0:
            page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)
            if verbose:
                print(f"Page {i+1}: Removed {redact_count} text instances")
    
    # Remove metadata
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

    remove_repeated_images(
        input_pdf,
        tmp_img_pdf,
        verbose=verbose,
        page_range=page_range
    )

    # Next, remove repeated text patterns (likely headers, footers)
    with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp_text_file:
        tmp_text_pdf = tmp_text_file.name

    remove_repeated_text(
        tmp_img_pdf,
        tmp_text_pdf,
        verbose=verbose,
        page_range=page_range
    )

    # Clean up the first temporary file
    try:
        os.unlink(tmp_img_pdf)
    except Exception:
        pass

    # Use the new temporary file for the next steps
    tmp_img_pdf = tmp_text_pdf

    doc = fitz.open(tmp_img_pdf)
    num_pages = len(doc)
    pages_to_process = set(range(num_pages))
    if page_range:
        pages_to_process = parse_page_range(page_range, num_pages)
        if verbose:
            print(f"Processing only pages: {sorted([p+1 for p in pages_to_process])}")

    for i in range(num_pages):
        if i not in pages_to_process:
            continue
        page = doc[i]
        if verbose:
            print(f"Processing page {i+1}/{num_pages}")
        
        # Extract text
        text = page.get_text()
        
        # Search for watermark patterns
        for pattern in watermark_patterns:
            for match in pattern.finditer(text):
                matched_text = match.group()
                
                # Skip if the text contains a DOI, unless it's from specific sources we want to remove
                if doi_pattern.search(matched_text) and not ("academic.oup.com" in matched_text or 
                                                            "aacrjournals.org" in matched_text or
                                                            "onlinelibrary.wiley.com" in matched_text):
                    if verbose:
                        print(f"Skipping watermark containing DOI: {matched_text}")
                    continue
                
                if verbose:
                    print(f"Found watermark: {matched_text}")
                
                # Search for the text on the page
                text_instances = page.search_for(matched_text)
                
                # To avoid white boxes, use redaction with fill=None and keep_appearance=True,
                # which tries to preserve the background as much as possible.
                for inst in text_instances:
                    annot = page.add_redact_annot(inst)
                    annot.set_colors(stroke=None, fill=None)
                    annot.update()
                
                # Apply all redactions on the page
                page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)
    
    # Remove metadata
    if verbose:
        print("Removing metadata...")
    doc.set_metadata({})
    
    if verbose:
        print(f"Writing output PDF: {output_pdf}")
    
    doc.save(output_pdf)
    doc.close()

    # Clean up temporary file
    try:
        os.unlink(tmp_img_pdf)
    except Exception:
        pass

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