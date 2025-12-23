#!/usr/bin/env python3
"""
Script to process (index) all documents in the docs folder.

This script indexes all PDF documents found in the docs directory,
making them available for querying and extraction.

It automatically skips documents that have already been processed,
allowing you to resume processing after interruptions.

Usage:
    python scripts/process_all_docs.py [--parser docling|mineru] [--force]
"""
import asyncio
import json
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from gdd_rag_backbone.config import DEFAULT_DOCS_DIR, DEFAULT_WORKING_DIR
from gdd_rag_backbone.llm_providers import QwenProvider, make_llm_model_func, make_embedding_func
from gdd_rag_backbone.rag_backend import index_document


def get_doc_id(doc_path: Path) -> str:
    """Generate a clean doc_id from filename."""
    doc_id = doc_path.stem.replace(" ", "_").replace("[", "").replace("]", "").lower()
    # Remove any other special characters that might cause issues
    doc_id = "".join(c if c.isalnum() or c in "_-" else "_" for c in doc_id)
    # Remove multiple consecutive underscores
    while "__" in doc_id:
        doc_id = doc_id.replace("__", "_")
    doc_id = doc_id.strip("_")
    return doc_id


def load_processed_status() -> dict:
    """Load the document processing status from kv_store_doc_status.json."""
    status_file = DEFAULT_WORKING_DIR / "kv_store_doc_status.json"
    if status_file.exists():
        try:
            with open(status_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"⚠️  Warning: Could not load status file: {e}")
            return {}
    return {}


def get_last_processing_time(status: dict) -> tuple:
    """Get the last document processed and its timestamp."""
    last_time = None
    last_doc = None
    for doc_id, info in status.items():
        if isinstance(info, dict) and info.get("status") == "processed":
            if "updated_at" in info:
                try:
                    # Handle both with and without timezone
                    updated_str = info["updated_at"].replace("+00:00", "")
                    dt = datetime.fromisoformat(updated_str)
                    if last_time is None or dt > last_time:
                        last_time = dt
                        last_doc = doc_id
                except Exception:
                    pass
    return last_doc, last_time


async def process_document(doc_path: Path, llm_func, embedding_func, parser=None):
    """Process (index) a single document."""
    doc_id = get_doc_id(doc_path)
    
    print(f"\n{'=' * 80}")
    print(f"📄 Processing: {doc_path.name}")
    print(f"   Document ID: {doc_id}")
    print(f"{'=' * 80}")
    
    try:
        await index_document(
            doc_path=doc_path,
            doc_id=doc_id,
            llm_func=llm_func,
            embedding_func=embedding_func,
            parser=parser,
        )
        print(f"✅ Successfully indexed: {doc_path.name}")
        return True
    except Exception as e:
        print(f"❌ Error indexing {doc_path.name}: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Main function to process all PDF documents."""
    print("\n" + "=" * 80)
    print("🚀 Processing All Documents in docs/ folder")
    print("=" * 80)
    
    # Check for arguments
    parser = None
    force = "--force" in sys.argv
    
    if "--parser" in sys.argv:
        idx = sys.argv.index("--parser")
        if idx + 1 < len(sys.argv):
            parser = sys.argv[idx + 1]
            if parser not in ["docling", "mineru"]:
                print(f"❌ Invalid parser: {parser}. Must be 'docling' or 'mineru'")
                sys.exit(1)
        else:
            print("❌ --parser requires a value (docling or mineru)")
            sys.exit(1)
    
    # Load processing status
    print("\n📋 Checking processing status...")
    status = load_processed_status()
    processed_doc_ids = {
        doc_id for doc_id, info in status.items()
        if isinstance(info, dict) and info.get("status") == "processed"
    }
    
    # Show last processing info
    last_doc, last_time = get_last_processing_time(status)
    if last_doc and last_time:
        print(f"📅 Last processed document: {last_doc}")
        print(f"   Last processing time: {last_time.strftime('%Y-%m-%d %H:%M:%S')}")
    else:
        print("📅 No previous processing found")
    
    print(f"✅ Already processed: {len(processed_doc_ids)} document(s)")
    
    # Initialize provider
    print("\n🔧 Initializing LLM provider...")
    try:
        provider = QwenProvider()
        llm_func = make_llm_model_func(provider)
        embedding_func = make_embedding_func(provider)
        print("✅ Using Qwen provider")
    except ValueError as e:
        print(f"❌ Error: {e}")
        print("Please set QWEN_API_KEY or DASHSCOPE_API_KEY environment variable.")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error initializing provider: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    # Find all PDF files
    docs_dir = Path(DEFAULT_DOCS_DIR)
    pdf_files = sorted(docs_dir.glob("*.pdf"))
    
    if not pdf_files:
        print(f"\n❌ No PDF files found in {docs_dir}")
        return
    
    # Filter out already processed documents (unless --force)
    unprocessed_files = []
    skipped_files = []
    
    for pdf_file in pdf_files:
        doc_id = get_doc_id(pdf_file)
        if not force and doc_id in processed_doc_ids:
            skipped_files.append((pdf_file.name, doc_id))
        else:
            unprocessed_files.append(pdf_file)
    
    print(f"\n📚 Found {len(pdf_files)} total PDF document(s)")
    print(f"   ⏭️  Skipping {len(skipped_files)} already processed document(s)")
    print(f"   📄 Will process {len(unprocessed_files)} document(s)")
    
    if skipped_files and not force:
        print(f"\n   Skipped documents:")
        for name, doc_id in skipped_files[:5]:  # Show first 5
            print(f"      - {name}")
        if len(skipped_files) > 5:
            print(f"      ... and {len(skipped_files) - 5} more")
        print(f"\n   (Use --force to reprocess all documents)")
    
    if not unprocessed_files:
        print("\n✨ All documents have already been processed!")
        print("   Use --force to reprocess all documents.")
        return
    
    if parser:
        print(f"\n🔧 Using parser: {parser}")
    
    print(f"\n🚀 Starting processing...")
    print(f"{'=' * 80}")
    
    results = []
    
    for i, pdf_file in enumerate(unprocessed_files, 1):
        print(f"\n[{i}/{len(unprocessed_files)}]")
        success = await process_document(pdf_file, llm_func, embedding_func, parser=parser)
        results.append((pdf_file.name, success))
    
    # Summary
    print("\n" + "=" * 80)
    print("📊 PROCESSING SUMMARY")
    print("=" * 80)
    
    successful = [name for name, success in results if success]
    failed = [name for name, success in results if not success]
    
    print(f"\n✅ Successfully processed: {len(successful)}/{len(results)}")
    if successful:
        for name in successful:
            print(f"   ✓ {name}")
    
    if failed:
        print(f"\n❌ Failed: {len(failed)}/{len(results)}")
        for name in failed:
            print(f"   ✗ {name}")
    
    print(f"\n📊 Overall status:")
    print(f"   Total processed: {len(processed_doc_ids) + len(successful)}/{len(pdf_files)}")
    print(f"   Remaining: {len(pdf_files) - len(processed_doc_ids) - len(successful)}")
    
    print("\n" + "=" * 80)
    print("✨ Processing complete!")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())


