"""
Script to chunk markdown files using the new document-based chunking strategy.

This script processes markdown files and saves chunks to rag_storage_md/.
"""

import argparse
import json
from pathlib import Path
from typing import List

from gdd_rag_backbone.markdown_chunking import MarkdownChunker


def find_markdown_files(directory: Path) -> List[Path]:
    """
    Find all markdown files in directory.
    
    Args:
        directory: Directory to search
    
    Returns:
        List of markdown file paths
    """
    markdown_files = list(directory.glob("*.md"))
    return sorted(markdown_files)


def save_chunks(chunks: List, doc_id: str, output_dir: Path) -> None:
    """
    Save chunks to JSON files.
    
    Args:
        chunks: List of MarkdownChunk objects
        doc_id: Document ID
        output_dir: Output directory for chunks
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Save chunks as JSON
    chunks_data = []
    for chunk in chunks:
        chunk_dict = {
            "chunk_id": chunk.chunk_id,
            "doc_id": chunk.doc_id,
            "content": chunk.content,
            "metadata": chunk.metadata,
            "parent_header": chunk.parent_header,
            "part_number": chunk.part_number,
            "token_count": chunk.token_count
        }
        chunks_data.append(chunk_dict)
    
    # Save to JSON file
    chunks_file = output_dir / f"{doc_id}_chunks.json"
    with open(chunks_file, 'w', encoding='utf-8') as f:
        json.dump(chunks_data, f, ensure_ascii=False, indent=2)
    
    print(f"  ✓ Saved {len(chunks)} chunks to {chunks_file}")


def generate_doc_id(filename: Path) -> str:
    """
    Generate document ID from filename.
    
    Args:
        filename: Markdown file path
    
    Returns:
        Document ID (sanitized filename without extension)
    """
    # Remove extension and sanitize
    doc_id = filename.stem
    # Replace spaces and special chars with underscores
    doc_id = doc_id.replace(" ", "_").replace("[", "").replace("]", "")
    doc_id = doc_id.replace("-", "_").replace(",", "_")
    # Remove multiple underscores
    while "__" in doc_id:
        doc_id = doc_id.replace("__", "_")
    return doc_id.strip("_")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Chunk markdown files using document-based chunking strategy"
    )
    parser.add_argument(
        "--markdown-dir",
        type=Path,
        default=Path("PDFtoMarkdown/markdown"),
        help="Directory containing markdown files (default: PDFtoMarkdown/markdown)"
    )
    parser.add_argument(
        "--file",
        type=Path,
        help="Path to a single markdown file; if set, skips directory scan"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("rag_storage_md"),
        help="Output directory for chunks (default: rag_storage_md)"
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=800,
        help="Target chunk size in tokens (default: 800)"
    )
    parser.add_argument(
        "--chunk-overlap",
        type=int,
        default=80,
        help="Chunk overlap in tokens (default: 80)"
    )
    parser.add_argument(
        "--max-chunk-size",
        type=int,
        default=1000,
        help="Maximum chunk size before forcing split (default: 1000)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without actually doing it"
    )
    args = parser.parse_args()
    
    # Determine files to process
    if args.file:
        target_file = Path(args.file)
        if not target_file.exists():
            print(f"ERROR: Markdown file not found: {target_file}")
            return 1
        if target_file.suffix.lower() != ".md":
            print(f"ERROR: Provided file is not a markdown file: {target_file}")
            return 1
        markdown_files = [target_file]
        markdown_dir = target_file.parent
    else:
        markdown_dir = Path(args.markdown_dir)
        if not markdown_dir.exists():
            print(f"ERROR: Markdown directory not found: {markdown_dir}")
            return 1
        if not markdown_dir.is_dir():
            print(f"ERROR: Provided path is not a directory: {markdown_dir}")
            return 1
        print(f"Scanning for markdown files in {markdown_dir}...")
        markdown_files = find_markdown_files(markdown_dir)
    
    if not markdown_files:
        print("No markdown files found!")
        return 1
    
    print("=" * 70)
    print("MARKDOWN CHUNKING")
    print("=" * 70)
    if args.file:
        print(f"Target file: {args.file}")
    else:
        print(f"Markdown directory: {markdown_dir}")
    print(f"Output directory: {args.output_dir}")
    print(f"Chunk size: {args.chunk_size} tokens")
    print(f"Chunk overlap: {args.chunk_overlap} tokens")
    print(f"Max chunk size: {args.max_chunk_size} tokens")
    print(f"Mode: {'DRY RUN' if args.dry_run else 'LIVE'}")
    print("=" * 70)
    print()
    
    print(f"Found {len(markdown_files)} markdown file(s)")
    print()
    
    # Initialize chunker
    chunker = MarkdownChunker(
        chunk_size_tokens=args.chunk_size,
        chunk_overlap_tokens=args.chunk_overlap,
        max_chunk_size=args.max_chunk_size
    )
    
    # Process each file
    total_chunks = 0
    for i, md_file in enumerate(markdown_files, 1):
        print(f"[{i}/{len(markdown_files)}] Processing: {md_file.name}")
        
        if args.dry_run:
            print(f"  [DRY RUN] Would chunk: {md_file}")
            continue
        
        # Read markdown content
        try:
            with open(md_file, 'r', encoding='utf-8') as f:
                markdown_content = f.read()
        except Exception as e:
            print(f"  ✗ ERROR reading file: {e}")
            continue
        
        # Generate doc_id
        doc_id = generate_doc_id(md_file)
        
        # Chunk document
        try:
            chunks = chunker.chunk_document(
                markdown_content=markdown_content,
                doc_id=doc_id,
                filename=str(md_file)
            )
            
            print(f"  ✓ Generated {len(chunks)} chunks")
            
            # Show chunk statistics
            if chunks:
                token_counts = [c.token_count for c in chunks]
                avg_tokens = sum(token_counts) / len(token_counts)
                max_tokens = max(token_counts)
                min_tokens = min(token_counts)
                print(f"  Token stats: avg={avg_tokens:.0f}, min={min_tokens}, max={max_tokens}")
            
            # Save chunks
            output_dir = args.output_dir / doc_id
            save_chunks(chunks, doc_id, output_dir)
            
            total_chunks += len(chunks)
            
        except Exception as e:
            print(f"  ✗ ERROR chunking: {e}")
            import traceback
            traceback.print_exc()
            continue
        
        print()
    
    print("=" * 70)
    print(f"COMPLETE: Processed {len(markdown_files)} file(s), generated {total_chunks} total chunks")
    print("=" * 70)
    
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

