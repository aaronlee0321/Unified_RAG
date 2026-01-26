#!/usr/bin/env python3
"""
Test script to extract GDD metadata (Version, Author, Date) from the first chunk of all documents.

This script:
1. Fetches all documents from keyword_documents table
2. For each document, gets the first chunk (lowest chunk_index)
3. Uses regex to extract Version, Người viết (Author), and Ngày tạo (Date)
4. Reports results for all documents
"""

import re
import sys
from typing import Dict, Optional, List, Any
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.storage.supabase_client import get_supabase_client
from backend.storage.keyword_storage import list_keyword_documents


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
    
    # Normalize whitespace: replace multiple newlines/spaces with single space for easier matching
    # But keep the original for final extraction
    normalized_text = re.sub(r'\s+', ' ', text)
    
    # Pattern for Version: "Version: v1.1" or "Phiên bản: v1.1"
    # Case-insensitive, handles various formats and newlines
    version_patterns = [
        # English: "Version: v1.1", "Version: 1.1", "Version: 1.1.0"
        # \s matches any whitespace including newlines
        r'Version\s*:\s*(v?\d+\.?\d*(?:\.\d+)?)',
        r'Version\s+(v?\d+\.?\d*(?:\.\d+)?)',
        # Vietnamese: "Phiên bản: v1.1", "Phiên bản: 1.1"
        r'Phiên\s+bản\s*:\s*(v?\d+\.?\d*(?:\.\d+)?)',
        r'Phiên\s+bản\s+(v?\d+\.?\d*(?:\.\d+)?)',
    ]
    
    for pattern in version_patterns:
        # Use re.DOTALL to make . match newlines, and re.IGNORECASE for case-insensitive
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if match:
            metadata['version'] = match.group(1).strip()
            break
    
    # Pattern for Author: "Người viết:", "Người tạo:", or "Người tạo file:"
    # Handle cases with/without spaces: "Người viết:" or "Ngườiviết:"
    # Extract ALL authors from the content between author title and date title
    # Handles list format: "- [x] phucth12\nthanhdv2\nlinhttd"
    # Examples:
    # - "Người viết: phucth12" (single author)
    # - "Ngườiviết:\n- [x] phucth12\nthanhdv2\nlinhttd" (multiple authors, list format)
    # - "Người viết: phucth12 (phucth12)" (with duplicate in parens)
    # - "Người tạo: QuocTA" (mixed case usernames)
    # - "Người tạo file: Kent (QuocTA)" (author with parentheses alias)
    # The username appears to be alphanumeric + underscore
    author_patterns = [
        # "Người viết:" - capture everything until date title (with or without spaces)
        r'Người\s*viết\s*:\s*([\s\S]*?)(?=\s*Ngày\s*(tạo|cập\s*nhật)|\s*\||\s*$)',
        # "Người tạo file:" - capture everything until date title
        r'Người\s*tạo\s*file\s*:\s*([\s\S]*?)(?=\s*Ngày\s*(tạo|cập\s*nhật)|\s*\||\s*$)',
        # "Người tạo:" - capture everything until date title
        r'Người\s*tạo\s*:\s*([\s\S]*?)(?=\s*Ngày\s*(tạo|cập\s*nhật)|\s*\||\s*$)',
    ]
    
    for pattern in author_patterns:
        # Use re.DOTALL to handle newlines better
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
    
    # Pattern for Date: "Ngày tạo:", "Ngày tạo file:", or "Ngày cập nhật:" followed by date
    # Handle cases with/without spaces: "Ngày tạo:" or "Ngàytạo:"
    # Formats: "28 - 07 - 2025", "28/07/2025", "28-07-2025", "28.07.2025", "09-09-2025"
    # Handles newlines: "Ngày tạo:\n28 - 07 - 2025"
    date_patterns = [
        # "Ngày tạo:" - with or without spaces, handle "09-09-2025" format
        r'Ngày\s*tạo\s*:\s*(\d{1,2}\s*-\s*\d{1,2}\s*-\s*\d{4})',
        # "Ngày tạo file:" - with or without spaces
        r'Ngày\s*tạo\s*file\s*:\s*(\d{1,2}\s*-\s*\d{1,2}\s*-\s*\d{4})',
        # "Ngày cập nhật:" - with or without spaces
        r'Ngày\s*cập\s*nhật\s*:\s*(\d{1,2}\s*-\s*\d{1,2}\s*-\s*\d{4})',
        # "Ngày tạo:" - handle "09/09/2025" or "09-09-2025" format (no spaces in date)
        r'Ngày\s*tạo\s*:\s*(\d{1,2}[-/]\d{1,2}[-/]\d{4})',
        r'Ngày\s*tạo\s*file\s*:\s*(\d{1,2}[-/]\d{1,2}[-/]\d{4})',
        r'Ngày\s*cập\s*nhật\s*:\s*(\d{1,2}[-/]\d{1,2}[-/]\d{4})',
        # "Ngày tạo:" - handle "09.09.2025" format
        r'Ngày\s*tạo\s*:\s*(\d{1,2}\.\d{1,2}\.\d{4})',
        r'Ngày\s*tạo\s*file\s*:\s*(\d{1,2}\.\d{1,2}\.\d{4})',
        r'Ngày\s*cập\s*nhật\s*:\s*(\d{1,2}\.\d{1,2}\.\d{4})',
        # More flexible: any date format after colon
        r'Ngày\s*tạo\s*:\s*(\d{1,2}\s*[-/\.]\s*\d{1,2}\s*[-/\.]\s*\d{4})',
        r'Ngày\s*tạo\s*file\s*:\s*(\d{1,2}\s*[-/\.]\s*\d{1,2}\s*[-/\.]\s*\d{4})',
        r'Ngày\s*cập\s*nhật\s*:\s*(\d{1,2}\s*[-/\.]\s*\d{1,2}\s*[-/\.]\s*\d{4})',
    ]
    
    for pattern in date_patterns:
        # Use re.DOTALL to handle newlines better
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if match:
            date_text = match.group(1).strip()
            # Normalize spaces (keep single spaces, remove multiple including newlines)
            date_text = re.sub(r'\s+', ' ', date_text)
            metadata['date'] = date_text
            break
    
    return metadata


def get_first_n_chunks_for_document(doc_id: str, n: int = 3) -> List[Dict[str, Any]]:
    """
    Get the first N chunks (lowest chunk_index) for a document.
    
    Args:
        doc_id: Document ID
        n: Number of chunks to retrieve (default: 3)
        
    Returns:
        List of chunk dicts with content, ordered by chunk_index
    """
    try:
        client = get_supabase_client()
        
        # Get chunks ordered by chunk_index, limit to first N
        result = client.table('keyword_chunks').select(
            'chunk_id, content, chunk_index, section_heading'
        ).eq('doc_id', doc_id).order('chunk_index', desc=False).limit(n).execute()
        
        if result.data:
            return result.data
        return []
    except Exception as e:
        print(f"  ❌ Error fetching chunks for {doc_id}: {e}")
        return []


def extract_metadata_from_multiple_chunks(chunks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Extract metadata from multiple chunks, trying each chunk sequentially.
    If a field is not found in chunk 1, try chunk 2, then chunk 3.
    Also handles cases where metadata is split across chunk boundaries.
    
    Args:
        chunks: List of chunk dicts with content, ordered by chunk_index
        
    Returns:
        Dict with keys: 'version', 'author', 'date', 'sources' (which chunk each came from)
    """
    metadata = {
        'version': None,
        'author': None,
        'date': None,
        'sources': {
            'version': None,
            'author': None,
            'date': None
        }
    }
    
    if not chunks:
        return metadata
    
    # Strategy 1: Try combining all chunks first for strong context-aware extraction
    # This handles cases where metadata spans multiple chunks (e.g., "Người tạo file:\n\nKent")
    combined_content = ' '.join([chunk.get('content', '').strip() for chunk in chunks])
    if combined_content:
        combined_metadata = extract_metadata_from_text(combined_content)
        # Use combined results if they're found (preferred method)
        if combined_metadata['version']:
            metadata['version'] = combined_metadata['version']
            metadata['sources']['version'] = chunks[0].get('chunk_index', 0)
        if combined_metadata['author']:
            metadata['author'] = combined_metadata['author']
            metadata['sources']['author'] = chunks[0].get('chunk_index', 0)
        if combined_metadata['date']:
            metadata['date'] = combined_metadata['date']
            metadata['sources']['date'] = chunks[0].get('chunk_index', 0)
    
    # Strategy 2: Try each chunk individually and handle cross-chunk splits
    for chunk_idx, chunk in enumerate(chunks):
        chunk_content = chunk.get('content', '')
        chunk_index = chunk.get('chunk_index', chunk_idx)
        
        if not chunk_content:
            continue
        
        # Extract metadata from this chunk
        chunk_metadata = extract_metadata_from_text(chunk_content)
        
        # Fill in missing fields (only if not already found from combined)
        if not metadata['version'] and chunk_metadata['version']:
            metadata['version'] = chunk_metadata['version']
            metadata['sources']['version'] = chunk_index
        
        if not metadata['author'] and chunk_metadata['author']:
            metadata['author'] = chunk_metadata['author']
            metadata['sources']['author'] = chunk_index
        
        if not metadata['date'] and chunk_metadata['date']:
            metadata['date'] = chunk_metadata['date']
            metadata['sources']['date'] = chunk_index
        
        # Strategy 3: Handle cross-chunk splits more aggressively
        # Check if this chunk ends with a label but value is missing
        if chunk_idx < len(chunks) - 1:  # Not the last chunk
            next_chunk = chunks[chunk_idx + 1]
            next_chunk_content = next_chunk.get('content', '')
            next_chunk_index = next_chunk.get('chunk_index', chunk_idx + 1)
            
            # Check for author split: chunk ends with author label but no author found (handle both with/without spaces)
            if not metadata['author']:
                chunk_end = chunk_content.rstrip()[-100:] if len(chunk_content) > 100 else chunk_content.rstrip()
                # Check for various author label patterns at end of chunk
                author_label_match = re.search(
                    r'Người\s*(tạo|viết)(\s*file)?\s*:\s*$',
                    chunk_end,
                    re.IGNORECASE | re.MULTILINE
                )
                if author_label_match:
                    # Combine chunks to extract all authors
                    combined = chunk_content.rstrip() + '\n' + next_chunk_content.lstrip()
                    combined_metadata = extract_metadata_from_text(combined)
                    if combined_metadata['author']:
                        metadata['author'] = combined_metadata['author']
                        metadata['sources']['author'] = chunk_index
            
            # Check for date split: chunk ends with date label but no date found (handle both with/without spaces)
            if not metadata['date']:
                chunk_end = chunk_content.rstrip()[-100:] if len(chunk_content) > 100 else chunk_content.rstrip()
                date_label_match = re.search(
                    r'Ngày\s*(tạo|cập\s*nhật)(\s*file)?\s*:\s*$',
                    chunk_end,
                    re.IGNORECASE | re.MULTILINE
                )
                if date_label_match:
                    # Next chunk might start with date
                    next_start = next_chunk_content[:200].strip()
                    date_match = re.search(
                        r'^(\d{1,2}\s*[-/\.]\s*\d{1,2}\s*[-/\.]\s*\d{4})',
                        next_start,
                        re.IGNORECASE | re.MULTILINE
                    )
                    if date_match:
                        date_text = date_match.group(1).strip()
                        date_text = re.sub(r'\s+', ' ', date_text)
                        metadata['date'] = date_text
                        metadata['sources']['date'] = chunk_index
                    else:
                        # Try combining chunks
                        combined = chunk_content.rstrip() + '\n' + next_chunk_content.lstrip()
                        combined_metadata = extract_metadata_from_text(combined)
                        if combined_metadata['date']:
                            metadata['date'] = combined_metadata['date']
                            metadata['sources']['date'] = chunk_index
        
        # If all fields found, we can stop early
        if all([metadata['version'], metadata['author'], metadata['date']]):
            break
    
    return metadata


def test_metadata_extraction() -> List[Dict[str, Any]]:
    """
    Test metadata extraction on all documents.
    
    Returns:
        List of results for each document
    """
    print("=" * 80)
    print("GDD Metadata Extraction Test")
    print("=" * 80)
    print()
    
    # Get all documents
    print("Fetching all documents from keyword_documents...")
    try:
        documents = list_keyword_documents()
        print(f"✅ Found {len(documents)} documents")
        print()
    except Exception as e:
        print(f"❌ Error fetching documents: {e}")
        return []
    
    if not documents:
        print("⚠️  No documents found in database")
        return []
    
    results = []
    success_count = 0
    partial_count = 0
    failed_count = 0
    
    print("Testing metadata extraction for each document:")
    print("-" * 80)
    
    for idx, doc in enumerate(documents, 1):
        doc_id = doc.get('doc_id', '')
        doc_name = doc.get('name', doc_id)
        
        print(f"\n[{idx}/{len(documents)}] {doc_name} ({doc_id})")
        
        # Get first 3 chunks
        chunks = get_first_n_chunks_for_document(doc_id, n=3)
        
        if not chunks:
            print("  ⚠️  No chunks found")
            results.append({
                'doc_id': doc_id,
                'doc_name': doc_name,
                'status': 'no_chunks',
                'version': None,
                'author': None,
                'date': None,
                'chunk_preview': None,
                'sources': None
            })
            failed_count += 1
            continue
        
        # Show preview of first chunk
        first_chunk_content = chunks[0].get('content', '')
        first_chunk_index = chunks[0].get('chunk_index', 0)
        preview = first_chunk_content[:200].replace('\n', ' ') if first_chunk_content else ''
        print(f"  Chunk #{first_chunk_index} preview: {preview}...")
        if len(chunks) > 1:
            print(f"  (Will check up to {len(chunks)} chunks if metadata missing)")
        
        # Extract metadata from multiple chunks
        metadata_result = extract_metadata_from_multiple_chunks(chunks)
        metadata = {
            'version': metadata_result['version'],
            'author': metadata_result['author'],
            'date': metadata_result['date']
        }
        sources = metadata_result['sources']
        
        # Debug: If author not found, show chunk contents that might contain it
        if not metadata['author']:
            print(f"  🔍 Debug: Author not found. Checking chunks for 'Người tạo' or 'Người viết':")
            for chunk in chunks:
                chunk_idx = chunk.get('chunk_index', 0)
                chunk_content = chunk.get('content', '')
                # Check if chunk contains author keywords
                if 'Người tạo' in chunk_content or 'Người viết' in chunk_content:
                    # Show relevant section (50 chars before and after the keyword)
                    for keyword in ['Người tạo', 'Người viết']:
                        idx = chunk_content.find(keyword)
                        if idx >= 0:
                            start = max(0, idx - 30)
                            end = min(len(chunk_content), idx + 80)
                            snippet = chunk_content[start:end].replace('\n', '\\n')
                            print(f"    Chunk #{chunk_idx} contains '{keyword}': ...{snippet}...")
                            break
        
        # Determine status
        found_fields = sum(1 for v in metadata.values() if v is not None)
        if found_fields == 3:
            status = 'success'
            success_count += 1
            print(f"  ✅ All metadata found:")
        elif found_fields > 0:
            status = 'partial'
            partial_count += 1
            print(f"  ⚠️  Partial metadata found ({found_fields}/3):")
        else:
            status = 'failed'
            failed_count += 1
            print(f"  ❌ No metadata found")
        
        # Print extracted values with source chunk info
        if metadata['version']:
            source_info = f" (from chunk #{sources['version']})" if sources['version'] is not None else ""
            print(f"    Version: {metadata['version']}{source_info}")
        else:
            print(f"    Version: (not found in chunks 1-{len(chunks)})")
        
        if metadata['author']:
            source_info = f" (from chunk #{sources['author']})" if sources['author'] is not None else ""
            print(f"    Author: {metadata['author']}{source_info}")
        else:
            print(f"    Author: (not found in chunks 1-{len(chunks)})")
        
        if metadata['date']:
            source_info = f" (from chunk #{sources['date']})" if sources['date'] is not None else ""
            print(f"    Date: {metadata['date']}{source_info}")
        else:
            print(f"    Date: (not found in chunks 1-{len(chunks)})")
        
        results.append({
            'doc_id': doc_id,
            'doc_name': doc_name,
            'status': status,
            'version': metadata['version'],
            'author': metadata['author'],
            'date': metadata['date'],
            'chunk_preview': preview,
            'sources': sources,
            'chunks_checked': len(chunks)
        })
    
    # Summary
    print()
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Total documents: {len(documents)}")
    print(f"✅ Success (all 3 fields): {success_count}")
    print(f"⚠️  Partial (1-2 fields): {partial_count}")
    print(f"❌ Failed (0 fields or no chunks): {failed_count}")
    print()
    
    # Show failed documents for debugging
    if failed_count > 0:
        print("Failed documents (for debugging):")
        print("-" * 80)
        for result in results:
            if result['status'] in ['failed', 'no_chunks']:
                print(f"  - {result['doc_name']} ({result['doc_id']})")
                if result['chunk_preview']:
                    print(f"    Chunk preview: {result['chunk_preview'][:150]}...")
        print()
    
    # Show partial success documents
    if partial_count > 0:
        print("Partial success documents:")
        print("-" * 80)
        for result in results:
            if result['status'] == 'partial':
                print(f"  - {result['doc_name']} ({result['doc_id']})")
                print(f"    Found: ", end="")
                found = []
                if result['version']: found.append(f"Version={result['version']}")
                if result['author']: found.append(f"Author={result['author']}")
                if result['date']: found.append(f"Date={result['date']}")
                print(", ".join(found))
        print()
    
    return results


if __name__ == '__main__':
    try:
        results = test_metadata_extraction()
        
        # Save results to file for inspection
        import json
        output_file = Path(__file__).parent.parent / 'output' / 'gdd_metadata_extraction_results.json'
        output_file.parent.mkdir(exist_ok=True)
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        
        print(f"✅ Results saved to: {output_file}")
        print()
        
    except Exception as e:
        print(f"❌ Error running test: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
