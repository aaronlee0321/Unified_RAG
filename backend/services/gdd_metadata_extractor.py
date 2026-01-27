"""
GDD Metadata Extraction Service
Extracts version, author, and date from GDD document chunks.
"""

import re
from typing import Dict, Optional, List, Any


def extract_metadata_from_text(text: str) -> Dict[str, Optional[str]]:
    """
    Extract Version, Author (Người viết/Người tạo), and Date (Ngày tạo/Ngày cập nhật) from text using regex.
    Handles cases where fields may be on separate lines.
    
    Args:
        text: The chunk content text
        
    Returns:
        Dict with keys: 'version', 'author', 'date'
    """
    metadata = {
        'version': None,
        'author': None,
        'date': None
    }
    
    if not text:
        return metadata
    
    # Pattern for Version: "Version: v1.1", "Phiên bản: v1.1", or "Phiên bản mới nhất: v1.1"
    # Handle cases with/without spaces: "Phiên bản:" or "Phiênbản:"
    # Handle newlines between label and colon: "Phiênbản\n\n:v1.1"
    version_patterns = [
        r'Version\s*:\s*(v?\d+\.?\d*(?:\.\d+)?)',
        r'Version\s+(v?\d+\.?\d*(?:\.\d+)?)',
        # "Phiên bản mới nhất:" - newest version
        r'Phiên\s*bản\s*mới\s*nhất\s*:\s*(v?\d+\.?\d*(?:\.\d+)?)',
        r'Phiên\s*bản\s*mới\s*nhất\s+(v?\d+\.?\d*(?:\.\d+)?)',
        # Make space optional between "Phiên" and "bản", and handle newlines before colon
        r'Phiên\s*bản\s*:\s*(v?\d+\.?\d*(?:\.\d+)?)',
        r'Phiên\s*bản\s+(v?\d+\.?\d*(?:\.\d+)?)',
    ]
    
    for pattern in version_patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if match:
            metadata['version'] = match.group(1).strip()
            break
    
    # Pattern for Author: "Người viết:", "Người tạo:", "Người tạo file:", or "Người soạn:"
    # Handle cases with/without spaces: "Người viết:" or "Ngườiviết:"
    # Extract ALL authors from the content between author title and date title
    # Handles list format: "- [x] phucth12\nthanhdv2\nlinhttd"
    author_patterns = [
        # "Người soạn:" - capture everything until date title (with or without spaces)
        r'Người\s*soạn\s*:\s*([\s\S]*?)(?=\s*Ngày\s*(tạo|cập\s*nhật|khởi\s*tạo)|\s*\||\s*$)',
        # "Người viết:" - capture everything until date title (with or without spaces)
        r'Người\s*viết\s*:\s*([\s\S]*?)(?=\s*Ngày\s*(tạo|cập\s*nhật|khởi\s*tạo)|\s*\||\s*$)',
        # "Người tạo file:" - capture everything until date title
        r'Người\s*tạo\s*file\s*:\s*([\s\S]*?)(?=\s*Ngày\s*(tạo|cập\s*nhật|khởi\s*tạo)|\s*\||\s*$)',
        # "Người tạo:" - capture everything until date title
        r'Người\s*tạo\s*:\s*([\s\S]*?)(?=\s*Ngày\s*(tạo|cập\s*nhật|khởi\s*tạo)|\s*\||\s*$)',
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
            lines = author_text.split('\n')
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                # Skip if it's just a checkbox marker without username
                if re.match(r'^-\s*\[[x\s]\]\s*$', line):
                    continue
                
                # Extract username from list item: "- [x] phucth12" -> "phucth12"
                list_match = re.search(r'(?:-\s*\[[x\s]\]\s*)?([a-zA-Z0-9_]{3,30})', line)
                if list_match:
                    username = list_match.group(1).strip()
                    if username and username not in authors:
                        authors.append(username)
                    continue
                
                # Extract from parentheses first (preferred): "Kent (QuocTA)" -> "QuocTA"
                paren_match = re.search(r'\(([a-zA-Z0-9_]+)\)', line)
                if paren_match:
                    username = paren_match.group(1).strip()
                    if username and username not in authors:
                        authors.append(username)
                    # Also check for main name before parentheses
                    main_match = re.search(r'([a-zA-Z0-9_]{3,30})(?=\s*\()', line)
                    if main_match:
                        main_username = main_match.group(1).strip()
                        if main_username and main_username not in authors:
                            authors.append(main_username)
                    continue
                
                # Extract plain username from line
                username_match = re.search(r'\b([a-zA-Z0-9_]{3,30})\b', line)
                if username_match:
                    username = username_match.group(1).strip()
                    if username and username not in authors:
                        authors.append(username)
            
            # If we found authors, join them with comma and space
            if authors:
                metadata['author'] = ', '.join(authors)
                break
    
    # Pattern for Date: "Ngày tạo:", "Ngày tạo file:", "Ngày cập nhật:", or "Ngày khởi tạo:"
    # Handle cases with/without spaces: "Ngày tạo:" or "Ngàytạo:"
    # Handle newlines between label and colon: "Ngàytạo\n\n:07-09-2025"
    date_patterns = [
        # "Ngày khởi tạo:" - with or without spaces, handle "21 - 08 - 2025" format
        r'Ngày\s*khởi\s*tạo\s*:\s*(\d{1,2}\s*-\s*\d{1,2}\s*-\s*\d{4})',
        # "Ngày tạo:" - with or without spaces, handle "09-09-2025" format
        r'Ngày\s*tạo\s*:\s*(\d{1,2}\s*-\s*\d{1,2}\s*-\s*\d{4})',
        # "Ngày tạo file:" - with or without spaces
        r'Ngày\s*tạo\s*file\s*:\s*(\d{1,2}\s*-\s*\d{1,2}\s*-\s*\d{4})',
        # "Ngày cập nhật:" - with or without spaces
        r'Ngày\s*cập\s*nhật\s*:\s*(\d{1,2}\s*-\s*\d{1,2}\s*-\s*\d{4})',
        # "Ngày khởi tạo:" - handle "21/08/2025" or "21-08-2025" format (no spaces in date)
        r'Ngày\s*khởi\s*tạo\s*:\s*(\d{1,2}[-/]\d{1,2}[-/]\d{4})',
        # "Ngày tạo:" - handle "09/09/2025" or "09-09-2025" format (no spaces in date)
        r'Ngày\s*tạo\s*:\s*(\d{1,2}[-/]\d{1,2}[-/]\d{4})',
        r'Ngày\s*tạo\s*file\s*:\s*(\d{1,2}[-/]\d{1,2}[-/]\d{4})',
        r'Ngày\s*cập\s*nhật\s*:\s*(\d{1,2}[-/]\d{1,2}[-/]\d{4})',
        # "Ngày khởi tạo:" - handle "21.08.2025" format
        r'Ngày\s*khởi\s*tạo\s*:\s*(\d{1,2}\.\d{1,2}\.\d{4})',
        # "Ngày tạo:" - handle "09.09.2025" format
        r'Ngày\s*tạo\s*:\s*(\d{1,2}\.\d{1,2}\.\d{4})',
        r'Ngày\s*tạo\s*file\s*:\s*(\d{1,2}\.\d{1,2}\.\d{4})',
        r'Ngày\s*cập\s*nhật\s*:\s*(\d{1,2}\.\d{1,2}\.\d{4})',
        # More flexible: any date format after colon
        r'Ngày\s*khởi\s*tạo\s*:\s*(\d{1,2}\s*[-/\.]\s*\d{1,2}\s*[-/\.]\s*\d{4})',
        r'Ngày\s*tạo\s*:\s*(\d{1,2}\s*[-/\.]\s*\d{1,2}\s*[-/\.]\s*\d{4})',
        r'Ngày\s*tạo\s*file\s*:\s*(\d{1,2}\s*[-/\.]\s*\d{1,2}\s*[-/\.]\s*\d{4})',
        r'Ngày\s*cập\s*nhật\s*:\s*(\d{1,2}\s*[-/\.]\s*\d{1,2}\s*[-/\.]\s*\d{4})',
    ]
    
    for pattern in date_patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if match:
            date_text = match.group(1).strip()
            date_text = re.sub(r'\s+', ' ', date_text)
            metadata['date'] = date_text
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
    metadata = {
        'version': None,
        'author': None,
        'date': None
    }
    
    if not chunks:
        return metadata
    
    # Strategy 1: Combine all chunks first for context-aware extraction
    combined_content = ' '.join([chunk.get('content', '').strip() for chunk in chunks])
    if combined_content:
        combined_metadata = extract_metadata_from_text(combined_content)
        metadata.update(combined_metadata)
    
    # Strategy 2: Try each chunk individually and handle cross-chunk splits
    for chunk_idx, chunk in enumerate(chunks):
        chunk_content = chunk.get('content', '')
        if not chunk_content:
            continue
        
        # Fill in missing fields
        chunk_metadata = extract_metadata_from_text(chunk_content)
        
        if not metadata['version'] and chunk_metadata['version']:
            metadata['version'] = chunk_metadata['version']
        
        if not metadata['author'] and chunk_metadata['author']:
            metadata['author'] = chunk_metadata['author']
        
        if not metadata['date'] and chunk_metadata['date']:
            metadata['date'] = chunk_metadata['date']
        
        # Handle cross-chunk splits
        if chunk_idx < len(chunks) - 1:
            next_chunk = chunks[chunk_idx + 1]
            next_chunk_content = next_chunk.get('content', '')
            
            # Check for author split (handle both with/without spaces)
            if not metadata['author']:
                chunk_end = chunk_content.rstrip()[-100:] if len(chunk_content) > 100 else chunk_content.rstrip()
                if re.search(r'Người\s*(tạo|viết)(\s*file)?\s*:\s*$', chunk_end, re.IGNORECASE | re.MULTILINE):
                    # Combine chunks to extract all authors
                    combined = chunk_content.rstrip() + '\n' + next_chunk_content.lstrip()
                    combined_metadata = extract_metadata_from_text(combined)
                    if combined_metadata['author']:
                        metadata['author'] = combined_metadata['author']
            
            # Check for date split (handle both with/without spaces)
            if not metadata['date']:
                chunk_end = chunk_content.rstrip()[-100:] if len(chunk_content) > 100 else chunk_content.rstrip()
                if re.search(r'Ngày\s*(tạo|cập\s*nhật)(\s*file)?\s*:\s*$', chunk_end, re.IGNORECASE | re.MULTILINE):
                    next_start = next_chunk_content[:200].strip()
                    date_match = re.search(r'^(\d{1,2}\s*[-/\.]\s*\d{1,2}\s*[-/\.]\s*\d{4})', next_start, re.IGNORECASE | re.MULTILINE)
                    if date_match:
                        date_text = date_match.group(1).strip()
                        date_text = re.sub(r'\s+', ' ', date_text)
                        metadata['date'] = date_text
                    else:
                        combined = chunk_content.rstrip() + '\n' + next_chunk_content.lstrip()
                        combined_metadata = extract_metadata_from_text(combined)
                        if combined_metadata['date']:
                            metadata['date'] = combined_metadata['date']
        
        # If all fields found, we can stop early
        if all([metadata['version'], metadata['author'], metadata['date']]):
            break
    
    return metadata
