"""
GDD Metadata Extraction Service
Extracts version, author, and date from GDD document chunks.
"""

import re
from typing import Any, Dict, List, Optional


def extract_metadata_from_version_table(text: str) -> Dict[str, Optional[str]]:
    """
    Extract version and author from version history table.
    Handles standard markdown tables and split-header tables (common in Marker output).

    Args:
        text: The chunk content text

    Returns:
        Dict with keys: 'version', 'author', 'date' (may be None)
    """
    metadata = {"version": None, "author": None, "date": None}

    if not text:
        return metadata

    # 1. Find the table start
    # Look for a line containing "Phiên" and "bản" (possibly split) or "Version"
    # Or just look for the first markdown table
    lines = text.split("\n")

    # Heuristic: Find a block of lines starting/ending with |
    current_block = []
    blocks = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|"):
            current_block.append(stripped)
        else:
            if current_block:
                blocks.append(current_block)
                current_block = []
    if current_block:
        blocks.append(current_block)

    # Analyze each block to see if it's a version table
    target_block = None
    for block in blocks:
        # Check if this block looks like a version table
        # Combine first 3 reviews to check for keywords
        header_text = " ".join(block[:3]).lower()
        if (
            ("phiên" in header_text and "bản" in header_text)
            or ("version" in header_text)
            or ("người" in header_text and "viết" in header_text)
            or ("author" in header_text)
        ):
            target_block = block
            break

    if not target_block:
        return metadata

    # 2. Parse the table
    # We need to identify columns.
    # Since headers might be split across rows (Row 1: Phiên, Row 3: bản), we need to merge headers.

    # Split each row into cells
    rows_cells = []
    for row in target_block:
        # Remove outer | and split by |
        # Handle escaped \| if necessary, but simple split usually works for this data
        cells = [c.strip() for c in row.strip("|").split("|")]
        rows_cells.append(cells)

    if not rows_cells:
        return metadata

    # Determine max columns
    max_cols = max(len(r) for r in rows_cells)

    # Build "Header" by combining text from matching columns in the top rows
    # We stop when we hit a row that looks like data (starts with v\d or date)
    # OR we just treat the first non-separator rows as headers

    data_start_idx = 0
    header_col_text = [""] * max_cols

    for i, cells in enumerate(rows_cells):
        is_separator = all(set(c) <= {"-", ":"}
                           and len(c) > 0 for c in cells if c)
        if is_separator:
            continue

        # Check if this row looks like data (e.g. "v1.0", date)
        "".join(cells).lower()
        is_data = False

        # Check first column for version pattern (v0.1, 1.0)
        if cells and re.match(r"^v?\d+\.\d+", cells[0], re.IGNORECASE):
            is_data = True

        if is_data:
            data_start_idx = i
            break

        # Accumulate header text
        for j, cell in enumerate(cells):
            if j < max_cols:
                header_col_text[j] += " " + cell.lower()

    # Clean header text
    header_col_text = [h.strip() for h in header_col_text]

    # Identify column indices
    version_idx = -1
    date_idx = -1
    author_idx = -1

    for i, header in enumerate(header_col_text):
        if ("phiên" in header and "bản" in header) or "version" in header:
            version_idx = i
        elif "ngày" in header or "date" in header:
            date_idx = i
        elif (
            ("người" in header and "viết" in header) or "author" in header or "người tạo" in header
        ):
            author_idx = i

    # Default to col 0 for version if not found but table looks valid
    if version_idx == -1 and (date_idx != -1 or author_idx != -1):
        version_idx = 0

    # 3. Extract data from the last row (or highest version)
    # Filter only data rows
    data_rows = rows_cells[data_start_idx:]

    valid_versions = []
    for row in data_rows:
        if not row:
            continue

        # Extract Version
        ver = None
        if version_idx != -1 and version_idx < len(row):
            v_text = row[version_idx]
            # Clean up: remove <br>, newlines
            v_text = re.sub(r"<br\s*/?>", " ", v_text, flags=re.IGNORECASE)
            v_text = v_text.strip()
            match = re.search(r"(v?\d+\.?\d*(?:\.\d+)?)",
                              v_text, re.IGNORECASE)
            if match:
                ver = match.group(1)

        if ver:
            # Extract Date
            date_val = None
            if date_idx != -1 and date_idx < len(row):
                d_text = row[date_idx]
                d_text = re.sub(r"<br\s*/?>", "", d_text, flags=re.IGNORECASE)
                # Remove spaces to join split date parts
                d_text = re.sub(r"\s+", "", d_text)
                # Match DD-MM-YYYY
                d_match = re.search(
                    r"(\d{1,2}[-/\.]\d{1,2}[-/\.]\d{4})", d_text)
                if d_match:
                    date_val = d_match.group(1).replace(".", "-")

            # Extract Author
            auth_val = None
            if author_idx != -1 and author_idx < len(row):
                a_text = row[author_idx]
                a_text = re.sub(r"<br\s*/?>", " ", a_text, flags=re.IGNORECASE)
                a_text = a_text.replace("\n", " ").strip()
                # Extract simple username
                a_match = re.search(r"([a-zA-Z0-9_]{3,30})", a_text)
                if a_match and a_match.group(1).lower() not in ["file", "tạo"]:
                    auth_val = a_match.group(1)

            # Store found data
            # Version parsing for sorting
            try:
                ver_num = float(re.sub(r"[^\d.]", "", ver))
            except (ValueError, TypeError):
                ver_num = 0.0

            valid_versions.append(
                {"version": ver, "version_num": ver_num,
                    "date": date_val, "author": auth_val}
            )

    if valid_versions:
        # Sort by version number descending
        valid_versions.sort(key=lambda x: x["version_num"], reverse=True)
        latest = valid_versions[0]
        metadata["version"] = latest["version"]
        metadata["author"] = latest["author"]
        metadata["date"] = latest["date"]

    return metadata


def extract_metadata_from_text(text: str) -> Dict[str, Optional[str]]:
    """
    Extract Version, Author (Người viết/Người tạo), and Date (Ngày tạo/Ngày cập nhật) from text using regex.
    Handles cases where fields may be on separate lines.

    Args:
        text: The chunk content text

    Returns:
        Dict with keys: 'version', 'author', 'date'
    """
    metadata = {"version": None, "author": None, "date": None}

    if not text:
        return metadata

    # Strategy 1: Try to extract from version history table first (most reliable)
    # This handles tables with version history where we want the latest version from the bottom row
    table_metadata = extract_metadata_from_version_table(text)
    if table_metadata["version"] or table_metadata["author"] or table_metadata["date"]:
        # Use table metadata if found, but don't override existing values
        if table_metadata["version"]:
            metadata["version"] = table_metadata["version"]
        if table_metadata["author"]:
            metadata["author"] = table_metadata["author"]
        if table_metadata["date"]:
            metadata["date"] = table_metadata["date"]

        # If we got all fields from table, return early
        if all([metadata["version"], metadata["author"], metadata["date"]]):
            return metadata

    # Strategy 2: Pattern-based extraction for non-table formats
    # If we didn't find version from table, try pattern-based extraction
    # Only look for versions in specific contexts (not random decimal numbers)
    if not metadata["version"]:
        # More specific patterns - only match versions in context
        version_patterns = [
            r"Version\s*:\s*(v?\d+\.?\d*(?:\.\d+)?)",
            r"Version\s+(v?\d+\.?\d*(?:\.\d+)?)",
            r"Phiên\s*bản\s*mới\s*nhất\s*:\s*(v?\d+\.?\d*(?:\.\d+)?)",
            r"Phiên\s*bản\s*mới\s*nhất\s+(v?\d+\.?\d*(?:\.\d+)?)",
            r"Phiên\s*bản\s*:\s*(v?\d+\.?\d*(?:\.\d+)?)",
            r"Phiên\s*bản\s+(v?\d+\.?\d*(?:\.\d+)?)",
        ]

        for pattern in version_patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            if match:
                version_str = match.group(1).strip(
                ) if match.groups() else match.group(0).strip()
                if version_str:
                    metadata["version"] = version_str
                    break

    # Pattern for Author: Vietnamese + English
    author_patterns = [
        # Vietnamese
        r"Người\s*soạn\s*:\s*([\s\S]*?)(?=\s*Ngày\s*(tạo|cập\s*nhật|khởi\s*tạo)|\s*\||\s*$)",
        r"Người\s*viết\s*:\s*([\s\S]*?)(?=\s*Ngày\s*(tạo|cập\s*nhật|khởi\s*tạo)|\s*\||\s*$)",
        r"Người\s*tạo\s*file\s*:\s*([\s\S]*?)(?=\s*Ngày\s*(tạo|cập\s*nhật|khởi\s*tạo)|\s*\||\s*$)",
        r"Người\s*tạo\s*:\s*([\s\S]*?)(?=\s*Ngày\s*(tạo|cập\s*nhật|khởi\s*tạo)|\s*\||\s*$)",
        # English: Author:, Written by:, Created by:
        r"Author\s*:\s*([\s\S]*?)(?=\s*Date\s*(:|\s)|\s*\n\n|\s*\||\s*$)",
        r"Written\s+by\s*:\s*([\s\S]*?)(?=\s*Date\s*(:|\s)|\s*\n\n|\s*\||\s*$)",
        r"Created\s+by\s*:\s*([\s\S]*?)(?=\s*Date\s*(:|\s)|\s*\n\n|\s*\||\s*$)",
    ]

    for pattern in author_patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if match:
            author_text = match.group(1).strip()

            if not author_text:
                continue

            # Extract all usernames from the author section
            # Handle multiple formats:
            # 1. List format: "- [x] phucth12\nthanhdv2\nlinhttd"
            # 2. Plain text: "phucth12\nthanhdv2\nlinhttd"
            # 3. With parentheses: "Kent (QuocTA)"

            authors = []

            # Split by newlines and process each line
            lines = author_text.split("\n")
            for line in lines:
                line = line.strip()
                if not line:
                    continue

                # Skip if it's just a checkbox marker without username
                if re.match(r"^-\s*\[[x\s]\]\s*$", line):
                    continue

                # Extract username from list item: "- [x] phucth12" -> "phucth12"
                list_match = re.search(
                    r"(?:-\s*\[[x\s]\]\s*)?([a-zA-Z0-9_]{3,30})", line)
                if list_match:
                    username = list_match.group(1).strip()
                    if username and username not in authors:
                        authors.append(username)
                    continue

                # Extract from parentheses first (preferred): "Kent (QuocTA)" -> "QuocTA"
                paren_match = re.search(r"\(([a-zA-Z0-9_]+)\)", line)
                if paren_match:
                    username = paren_match.group(1).strip()
                    if username and username not in authors:
                        authors.append(username)
                    # Also check for main name before parentheses
                    main_match = re.search(
                        r"([a-zA-Z0-9_]{3,30})(?=\s*\()", line)
                    if main_match:
                        main_username = main_match.group(1).strip()
                        if main_username and main_username not in authors:
                            authors.append(main_username)
                    continue

                # Extract plain username from line
                username_match = re.search(r"\b([a-zA-Z0-9_]{3,30})\b", line)
                if username_match:
                    username = username_match.group(1).strip()
                    if username and username not in authors:
                        authors.append(username)

            # If we found authors, join them with comma and space
            if authors:
                metadata["author"] = ", ".join(authors)
                break

    # Pattern for Date: Vietnamese + English
    date_patterns = [
        # English: Date:, Created:, Updated:
        r"Date\s*:\s*(\d{1,2}\s*[-/]\s*\d{1,2}\s*[-/]\s*\d{4})",
        r"Date\s*:\s*(\d{4}\s*[-/]\s*\d{1,2}\s*[-/]\s*\d{1,2})",
        r"Created\s*:\s*(\d{1,2}\s*[-/]\s*\d{1,2}\s*[-/]\s*\d{4})",
        r"Updated\s*:\s*(\d{1,2}\s*[-/]\s*\d{1,2}\s*[-/]\s*\d{4})",
        # Vietnamese
        r"Ngày\s*khởi\s*tạo\s*:\s*(\d{1,2}\s*-\s*\d{1,2}\s*-\s*\d{4})",
        # "Ngày tạo:" - with or without spaces, handle "09-09-2025" format
        r"Ngày\s*tạo\s*:\s*(\d{1,2}\s*-\s*\d{1,2}\s*-\s*\d{4})",
        # "Ngày tạo file:" - with or without spaces
        r"Ngày\s*tạo\s*file\s*:\s*(\d{1,2}\s*-\s*\d{1,2}\s*-\s*\d{4})",
        # "Ngày cập nhật:" - with or without spaces
        r"Ngày\s*cập\s*nhật\s*:\s*(\d{1,2}\s*-\s*\d{1,2}\s*-\s*\d{4})",
        # "Ngày khởi tạo:" - handle "21/08/2025" or "21-08-2025" format (no spaces in date)
        r"Ngày\s*khởi\s*tạo\s*:\s*(\d{1,2}[-/]\d{1,2}[-/]\d{4})",
        # "Ngày tạo:" - handle "09/09/2025" or "09-09-2025" format (no spaces in date)
        r"Ngày\s*tạo\s*:\s*(\d{1,2}[-/]\d{1,2}[-/]\d{4})",
        r"Ngày\s*tạo\s*file\s*:\s*(\d{1,2}[-/]\d{1,2}[-/]\d{4})",
        r"Ngày\s*cập\s*nhật\s*:\s*(\d{1,2}[-/]\d{1,2}[-/]\d{4})",
        # "Ngày khởi tạo:" - handle "21.08.2025" format
        r"Ngày\s*khởi\s*tạo\s*:\s*(\d{1,2}\.\d{1,2}\.\d{4})",
        # "Ngày tạo:" - handle "09.09.2025" format
        r"Ngày\s*tạo\s*:\s*(\d{1,2}\.\d{1,2}\.\d{4})",
        r"Ngày\s*tạo\s*file\s*:\s*(\d{1,2}\.\d{1,2}\.\d{4})",
        r"Ngày\s*cập\s*nhật\s*:\s*(\d{1,2}\.\d{1,2}\.\d{4})",
        # More flexible: any date format after colon
        r"Ngày\s*khởi\s*tạo\s*:\s*(\d{1,2}\s*[-/\.]\s*\d{1,2}\s*[-/\.]\s*\d{4})",
        r"Ngày\s*tạo\s*:\s*(\d{1,2}\s*[-/\.]\s*\d{1,2}\s*[-/\.]\s*\d{4})",
        r"Ngày\s*tạo\s*file\s*:\s*(\d{1,2}\s*[-/\.]\s*\d{1,2}\s*[-/\.]\s*\d{4})",
        r"Ngày\s*cập\s*nhật\s*:\s*(\d{1,2}\s*[-/\.]\s*\d{1,2}\s*[-/\.]\s*\d{4})",
    ]

    for pattern in date_patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if match:
            date_text = match.group(1).strip()
            date_text = re.sub(r"\s+", " ", date_text)
            metadata["date"] = date_text
            break

    return metadata


def extract_metadata_from_chunks(chunks: List[Dict[str, Any]]) -> Dict[str, Optional[str]]:
    """
    Extract metadata from a list of chunks (typically first 3 chunks).
    Handles cases where metadata is split across chunk boundaries.

    Args:
        chunks: List of chunk dicts with 'content' and optionally 'chunk_index'

    Returns:
        Dict with keys: 'version', 'author', 'date'
    """
    metadata = {"version": None, "author": None, "date": None}

    if not chunks:
        return metadata

    # Strategy 1: Try version table extraction first (most reliable for new format)
    # Combine all chunks with newlines to preserve table structure
    combined_content = "\n".join(
        [chunk.get("content", "").strip() for chunk in chunks])
    if combined_content:
        # Try version table extraction first - this should find the latest version
        table_metadata = extract_metadata_from_version_table(combined_content)
        if table_metadata["version"] or table_metadata["author"] or table_metadata["date"]:
            # Table extraction found something - use it (it already picks the latest version)
            if table_metadata["version"]:
                metadata["version"] = table_metadata["version"]
            if table_metadata["author"]:
                metadata["author"] = table_metadata["author"]
            if table_metadata["date"]:
                metadata["date"] = table_metadata["date"]

            # If we got all fields from table, return early
            if all([metadata["version"], metadata["author"], metadata["date"]]):
                return metadata

        # Fall back to pattern-based extraction (which also finds latest version)
        combined_metadata = extract_metadata_from_text(combined_content)
        # Only update if we don't already have values from table
        if not metadata["version"] and combined_metadata["version"]:
            metadata["version"] = combined_metadata["version"]
        if not metadata["author"] and combined_metadata["author"]:
            metadata["author"] = combined_metadata["author"]
        if not metadata["date"] and combined_metadata["date"]:
            metadata["date"] = combined_metadata["date"]

    # Strategy 2: Try each chunk individually and handle cross-chunk splits
    # Only do this if we haven't found all metadata yet
    # This is a fallback for cases where table extraction didn't work
    if not all([metadata["version"], metadata["author"], metadata["date"]]):
        for chunk_idx, chunk in enumerate(chunks):
            chunk_content = chunk.get("content", "")
            if not chunk_content:
                continue

            # Fill in missing fields
            chunk_metadata = extract_metadata_from_text(chunk_content)

            if not metadata["version"] and chunk_metadata["version"]:
                metadata["version"] = chunk_metadata["version"]

            if not metadata["author"] and chunk_metadata["author"]:
                metadata["author"] = chunk_metadata["author"]

            if not metadata["date"] and chunk_metadata["date"]:
                metadata["date"] = chunk_metadata["date"]

            # Handle cross-chunk splits
            if chunk_idx < len(chunks) - 1:
                next_chunk = chunks[chunk_idx + 1]
                next_chunk_content = next_chunk.get("content", "")

                # Check for author split (handle both with/without spaces)
                if not metadata["author"]:
                    chunk_end = (
                        chunk_content.rstrip()[-100:]
                        if len(chunk_content) > 100
                        else chunk_content.rstrip()
                    )
                    if re.search(
                        r"Người\s*(tạo|viết)(\s*file)?\s*:\s*$",
                        chunk_end,
                        re.IGNORECASE | re.MULTILINE,
                    ):
                        # Combine chunks to extract all authors
                        combined = chunk_content.rstrip() + "\n" + next_chunk_content.lstrip()
                        combined_metadata = extract_metadata_from_text(
                            combined)
                        if combined_metadata["author"]:
                            metadata["author"] = combined_metadata["author"]

                # Check for date split (handle both with/without spaces)
                if not metadata["date"]:
                    chunk_end = (
                        chunk_content.rstrip()[-100:]
                        if len(chunk_content) > 100
                        else chunk_content.rstrip()
                    )
                    if re.search(
                        r"Ngày\s*(tạo|cập\s*nhật)(\s*file)?\s*:\s*$",
                        chunk_end,
                        re.IGNORECASE | re.MULTILINE,
                    ):
                        next_start = next_chunk_content[:200].strip()
                        date_match = re.search(
                            r"^(\d{1,2}\s*[-/\.]\s*\d{1,2}\s*[-/\.]\s*\d{4})",
                            next_start,
                            re.IGNORECASE | re.MULTILINE,
                        )
                        if date_match:
                            date_text = date_match.group(1).strip()
                            date_text = re.sub(r"\s+", " ", date_text)
                            metadata["date"] = date_text
                        else:
                            combined = chunk_content.rstrip() + "\n" + next_chunk_content.lstrip()
                            combined_metadata = extract_metadata_from_text(
                                combined)
                            if combined_metadata["date"]:
                                metadata["date"] = combined_metadata["date"]

            # If all fields found, we can stop early
            if all([metadata["version"], metadata["author"], metadata["date"]]):
                break

    return metadata
