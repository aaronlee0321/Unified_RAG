#!/usr/bin/env python3
"""
Update GDD metadata for already indexed documents.

This script:
1. Fetches all documents from keyword_documents table
2. For each document, gets the first 3 chunks
3. Extracts metadata (version, author, date) using regex
4. Updates the document in Supabase with extracted metadata
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.storage.keyword_storage import list_keyword_documents, update_document_metadata
from backend.storage.supabase_client import get_supabase_client
from backend.services.gdd_metadata_extractor import extract_metadata_from_chunks


def get_first_n_chunks_for_document(doc_id: str, n: int = 3):
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


def update_all_documents_metadata():
    """
    Update metadata for all documents in keyword_documents table.
    """
    print("=" * 80)
    print("GDD Metadata Update Script")
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
        return
    
    if not documents:
        print("⚠️  No documents found in database")
        return
    
    success_count = 0
    partial_count = 0
    failed_count = 0
    skipped_count = 0
    
    print("Updating metadata for each document:")
    print("-" * 80)
    
    for idx, doc in enumerate(documents, 1):
        doc_id = doc.get('doc_id', '')
        doc_name = doc.get('name', doc_id)
        
        print(f"\n[{idx}/{len(documents)}] {doc_name} ({doc_id})")
        
        # Get first 3 chunks
        chunks = get_first_n_chunks_for_document(doc_id, n=3)
        
        if not chunks:
            print("  ⚠️  No chunks found - skipping")
            skipped_count += 1
            continue
        
        # Extract metadata
        metadata = extract_metadata_from_chunks(chunks)
        
        # Determine status
        found_fields = sum(1 for v in metadata.values() if v is not None)
        
        if found_fields == 0:
            print("  ⚠️  No metadata found - updating with NULL values")
            status = 'no_metadata'
            failed_count += 1
        elif found_fields == 3:
            status = 'success'
            success_count += 1
            print(f"  ✅ All metadata found:")
        else:
            status = 'partial'
            partial_count += 1
            print(f"  ⚠️  Partial metadata found ({found_fields}/3):")
        
        # Print extracted values
        if metadata['version']:
            print(f"    Version: {metadata['version']}")
        else:
            print(f"    Version: (not found)")
        
        if metadata['author']:
            print(f"    Author: {metadata['author']}")
        else:
            print(f"    Author: (not found)")
        
        if metadata['date']:
            print(f"    Date: {metadata['date']}")
        else:
            print(f"    Date: (not found)")
        
        # Update document in Supabase
        try:
            success = update_document_metadata(
                doc_id=doc_id,
                version=metadata.get('version'),
                author=metadata.get('author'),
                date=metadata.get('date')
            )
            
            if success:
                print(f"  ✅ Updated in Supabase")
            else:
                print(f"  ❌ Failed to update in Supabase")
                failed_count += 1
        except Exception as e:
            print(f"  ❌ Error updating document: {e}")
            failed_count += 1
    
    # Summary
    print()
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Total documents: {len(documents)}")
    print(f"✅ Success (all 3 fields): {success_count}")
    print(f"⚠️  Partial (1-2 fields): {partial_count}")
    print(f"❌ Failed/No metadata: {failed_count}")
    print(f"⏭️  Skipped (no chunks): {skipped_count}")
    print()
    print("✅ Metadata update completed!")


if __name__ == '__main__':
    try:
        update_all_documents_metadata()
    except Exception as e:
        print(f"❌ Error running update: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
