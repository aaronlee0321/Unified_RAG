"""
Migration script to convert all PDFs to Markdown and re-index with custom chunking.

This script:
1. Scans the docs/ directory for all PDF files (or accepts a single file)
2. Converts each PDF to Markdown
3. Re-indexes with document-based chunking strategy
4. Preserves existing doc_ids or generates new ones

Usage:
    python -m gdd_rag_backbone.scripts.convert_and_reindex_pdfs [--docs-dir DOCS_DIR | --file FILE] [--dry-run]
"""

import argparse
import asyncio
import sys
from pathlib import Path
from typing import List, Tuple

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from gdd_rag_backbone.config import DEFAULT_DOCS_DIR
from gdd_rag_backbone.llm_providers import QwenProvider, make_llm_model_func, make_embedding_func
from gdd_rag_backbone.rag_backend.indexing import index_document
from gdd_rag_backbone.rag_backend.chunk_qa import load_doc_status


def find_pdf_files(docs_dir: Path) -> List[Path]:
    """Find all PDF files in the docs directory."""
    pdf_files = list(docs_dir.glob("*.pdf"))
    # Also check subdirectories
    pdf_files.extend(docs_dir.glob("**/*.pdf"))
    return sorted(set(pdf_files))  # Remove duplicates and sort


def generate_doc_id(pdf_path: Path, existing_doc_ids: set) -> str:
    """
    Generate a doc_id from PDF path, ensuring uniqueness.
    
    Args:
        pdf_path: Path to PDF file
        existing_doc_ids: Set of existing document IDs
    
    Returns:
        Unique document ID
    """
    # Try to use filename without extension
    base_name = pdf_path.stem
    
    # Clean up the name (remove special characters, normalize)
    doc_id = base_name.replace(" ", "_").replace("-", "_")
    doc_id = "".join(c for c in doc_id if c.isalnum() or c in "[]_")
    
    # Ensure uniqueness
    original_doc_id = doc_id
    counter = 1
    while doc_id in existing_doc_ids:
        doc_id = f"{original_doc_id}_{counter}"
        counter += 1
    
    return doc_id


async def reindex_pdf(
    pdf_path: Path,
    doc_id: str,
    provider,
    dry_run: bool = False,
) -> Tuple[bool, str]:
    """
    Re-index a single PDF file.
    
    Args:
        pdf_path: Path to PDF file
        doc_id: Document ID
        provider: LLM provider
        dry_run: If True, don't actually index
    
    Returns:
        (success, message)
    """
    try:
        if dry_run:
            return True, f"[DRY RUN] Would re-index {pdf_path.name} as {doc_id}"
        
        llm_func = make_llm_model_func(provider)
        embedding_func = make_embedding_func(provider)
        
        await index_document(
            doc_path=pdf_path,
            doc_id=doc_id,
            llm_func=llm_func,
            embedding_func=embedding_func,
            parser="docling",  # Use docling for PDF parsing
        )
        
        return True, f"✓ Re-indexed {pdf_path.name} as {doc_id}"
    
    except Exception as e:
        return False, f"✗ Failed to re-index {pdf_path.name}: {e}"


async def main():
    parser = argparse.ArgumentParser(
        description="Convert all PDFs to Markdown and re-index with custom chunking"
    )
    parser.add_argument(
        "--docs-dir",
        type=Path,
        default=DEFAULT_DOCS_DIR,
        help="Directory containing PDF files (default: docs/)"
    )
    parser.add_argument(
        "--file",
        type=Path,
        help="Path to a single PDF file; if set, skips directory scan"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without actually doing it"
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip PDFs that are already indexed"
    )
    args = parser.parse_args()
    
    docs_dir = Path(args.docs_dir)
    target_file = args.file
    
    # Allow passing a PDF path via --docs-dir for backward compatibility
    if target_file is None and docs_dir.is_file() and docs_dir.suffix.lower() == ".pdf":
        target_file = docs_dir
    
    print("=" * 70)
    print("PDF TO MARKDOWN CONVERSION AND RE-INDEXING")
    print("=" * 70)
    if target_file:
        target_file = Path(target_file)
        print(f"Target file: {target_file}")
        docs_dir = target_file.parent
    else:
        print(f"Docs directory: {docs_dir}")
    print(f"Mode: {'DRY RUN' if args.dry_run else 'LIVE'}")
    print("=" * 70)
    print()
    
    # Find all PDF files
    if target_file:
        if not target_file.exists():
            print(f"ERROR: PDF file not found: {target_file}")
            return 1
        if target_file.suffix.lower() != ".pdf":
            print(f"ERROR: Provided file is not a PDF: {target_file}")
            return 1
        pdf_files = [target_file]
    else:
        if not docs_dir.exists():
            print(f"ERROR: Docs directory not found: {docs_dir}")
            return 1
        if not docs_dir.is_dir():
            print(f"ERROR: Provided docs path is not a directory: {docs_dir}")
            return 1
        print("Scanning for PDF files...")
        pdf_files = find_pdf_files(docs_dir)
    
    if not pdf_files:
        print("No PDF files found!")
        return 1
    
    print(f"Found {len(pdf_files)} PDF file(s)")
    print()
    
    # Load existing document IDs
    existing_status = load_doc_status()
    existing_doc_ids = set(existing_status.keys())
    print(f"Found {len(existing_doc_ids)} existing indexed documents")
    print()
    
    # Filter out already indexed PDFs if requested
    if args.skip_existing:
        # Try to match PDF paths to existing doc_ids
        pdf_paths_str = {str(pdf.absolute()) for pdf in pdf_files}
        existing_pdf_paths = {
            meta.get("file_path", "")
            for meta in existing_status.values()
        }
        
        # Filter out PDFs that are already indexed
        pdf_files = [
            pdf for pdf in pdf_files
            if str(pdf.absolute()) not in existing_pdf_paths
        ]
        
        if not pdf_files:
            print("All PDFs are already indexed. Use --skip-existing=false to re-index anyway.")
            return 0
        
        print(f"After filtering, {len(pdf_files)} PDF(s) need indexing")
        print()
    
    # Initialize provider
    print("Initializing LLM provider...")
    try:
        provider = QwenProvider()
        print("✓ LLM provider initialized")
    except Exception as e:
        print(f"ERROR: Could not initialize LLM provider: {e}")
        print("Please check your API key in .env file")
        return 1
    
    print()
    print("=" * 70)
    print("STARTING CONVERSION AND RE-INDEXING")
    print("=" * 70)
    print()
    
    # Process each PDF
    success_count = 0
    fail_count = 0
    
    for i, pdf_path in enumerate(pdf_files, 1):
        print(f"[{i}/{len(pdf_files)}] Processing: {pdf_path.name}")
        
        # Generate or reuse doc_id
        # Try to find existing doc_id for this PDF
        doc_id = None
        pdf_path_str = str(pdf_path.absolute())
        
        for existing_doc_id, meta in existing_status.items():
            if meta.get("file_path") == pdf_path_str:
                doc_id = existing_doc_id
                print(f"  Using existing doc_id: {doc_id}")
                break
        
        if doc_id is None:
            doc_id = generate_doc_id(pdf_path, existing_doc_ids)
            print(f"  Generated doc_id: {doc_id}")
            existing_doc_ids.add(doc_id)
        
        # Re-index the PDF
        success, message = await reindex_pdf(
            pdf_path=pdf_path,
            doc_id=doc_id,
            provider=provider,
            dry_run=args.dry_run,
        )
        
        print(f"  {message}")
        print()
        
        if success:
            success_count += 1
        else:
            fail_count += 1
    
    # Summary
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Total PDFs: {len(pdf_files)}")
    print(f"Successful: {success_count}")
    print(f"Failed: {fail_count}")
    print("=" * 70)
    
    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
