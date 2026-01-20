#!/usr/bin/env python3
"""
Script to index Tank War PDF documents into Supabase.
Indexes a few selected PDF files from the Tank War directory.
"""

import os
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    print("Warning: python-dotenv not installed, environment variables may not be loaded")

# Import with error handling
try:
    from backend.gdd_service import upload_and_index_document_bytes
except Exception as e:
    print(f"Error importing upload_and_index_document_bytes: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

def index_tank_war_documents(file_paths=None, max_files=5):
    """
    Index Tank War PDF documents into Supabase.
    
    Args:
        file_paths: Optional list of specific file paths to index. If None, selects first few files.
        max_files: Maximum number of files to index if file_paths is None
    """
    tank_war_dir = PROJECT_ROOT / "Tank War"
    
    if not tank_war_dir.exists():
        print(f"❌ Error: Tank War directory not found at {tank_war_dir}")
        return
    
    # Find all PDF files
    pdf_files = list(tank_war_dir.glob("*.pdf"))
    
    if not pdf_files:
        print(f"❌ No PDF files found in {tank_war_dir}")
        return
    
    print(f"📁 Found {len(pdf_files)} PDF files in Tank War directory")
    
    # Select files to index
    if file_paths:
        # Use specified files
        files_to_index = []
        for file_path in file_paths:
            if isinstance(file_path, str):
                file_path = Path(file_path)
            if file_path.exists() and file_path.suffix.lower() == '.pdf':
                files_to_index.append(file_path)
            else:
                print(f"⚠️  Warning: File not found or not a PDF: {file_path}")
    else:
        # Select first few files
        files_to_index = pdf_files[:max_files]
    
    if not files_to_index:
        print("❌ No valid files to index")
        return
    
    print(f"\n📚 Indexing {len(files_to_index)} PDF files:\n")
    for i, file_path in enumerate(files_to_index, 1):
        print(f"  {i}. {file_path.name}")
    
    print("\n" + "="*80)
    
    # Index each file
    success_count = 0
    failed_count = 0
    
    for i, file_path in enumerate(files_to_index, 1):
        print(f"\n[{i}/{len(files_to_index)}] Processing: {file_path.name}")
        print("-" * 80)
        
        try:
            # Read PDF file
            with open(file_path, 'rb') as f:
                pdf_bytes = f.read()
            
            print(f"✅ Read {len(pdf_bytes)} bytes from {file_path.name}")
            
            # Progress callback
            def progress_callback(step):
                print(f"  → {step}")
            
            # Index the document
            result = upload_and_index_document_bytes(
                pdf_bytes=pdf_bytes,
                original_filename=str(file_path),
                progress_cb=progress_callback
            )
            
            if result.get('status') == 'success':
                success_count += 1
                doc_id = result.get('doc_id', 'unknown')
                print(f"✅ Successfully indexed: {file_path.name} (doc_id: {doc_id})")
            else:
                failed_count += 1
                error_msg = result.get('message', 'Unknown error')
                print(f"❌ Failed to index {file_path.name}: {error_msg}")
        
        except Exception as e:
            failed_count += 1
            print(f"❌ Error indexing {file_path.name}: {str(e)}")
            import traceback
            traceback.print_exc()
    
    # Summary
    print("\n" + "="*80)
    print(f"\n📊 Summary:")
    print(f"  ✅ Successfully indexed: {success_count}")
    print(f"  ❌ Failed: {failed_count}")
    print(f"  📁 Total processed: {len(files_to_index)}")
    print("="*80)

if __name__ == "__main__":
    # Select a few files to index (you can modify this list)
    selected_files = [
        "Tank War/[Character Module] [Tank War] Garage Design - Main.pdf",
        "Tank War/[Combat Module] [Tank War] Shooting Logic.pdf",
        "Tank War/[Progression Module] [Tank War] Leaderboard System.pdf",
        "Tank War/[Tank War] User Profile Design.pdf",
        "Tank War/[World] [Tank War] Map Design - Outpost Breaker.pdf",
    ]
    
    # Convert to Path objects relative to project root
    file_paths = [PROJECT_ROOT / f for f in selected_files]
    
    # Filter to only existing files
    file_paths = [f for f in file_paths if f.exists()]
    
    if not file_paths:
        print("⚠️  None of the selected files exist. Indexing first 5 PDF files instead...")
        index_tank_war_documents(max_files=5)
    else:
        print(f"📚 Indexing {len(file_paths)} selected files...")
        index_tank_war_documents(file_paths=file_paths)
