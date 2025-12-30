"""
Index specific documents that are failing.

This script indexes the remaining 3 documents that have encoding issues.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv()

from backend.storage.gdd_supabase_storage import index_gdd_chunks_to_supabase
from gdd_rag_backbone.llm_providers import QwenProvider
from gdd_rag_backbone.markdown_chunking import MarkdownChunker
from gdd_rag_backbone.scripts.chunk_markdown_files import generate_doc_id
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Set UTF-8 encoding for console output
import sys
import io
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
if sys.stderr.encoding != 'utf-8':
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')


def index_document(md_file: Path):
    """Index a single markdown file."""
    try:
        logger.info(f"\n{'='*60}")
        logger.info(f"Indexing: {md_file.name}")
        
        # Read markdown
        markdown_content = md_file.read_text(encoding='utf-8')
        doc_id = generate_doc_id(md_file)
        logger.info(f"Doc ID: {doc_id}")
        
        # Chunk
        chunker = MarkdownChunker()
        chunks = chunker.chunk_document(
            markdown_content=markdown_content,
            doc_id=doc_id,
            filename=md_file.name,
        )
        logger.info(f"Created {len(chunks)} chunks")
        
        # Convert to dicts
        chunks_dicts = []
        for chunk in chunks:
            # Make chunk_id globally unique by prepending doc_id
            raw_chunk_id = chunk.chunk_id
            full_chunk_id = f"{doc_id}_{raw_chunk_id}"
            
            chunk_dict = {
                'chunk_id': full_chunk_id,  # Use full format for global uniqueness
                'content': chunk.content,
                'doc_id': chunk.doc_id,
                'metadata': chunk.metadata,
            }
            chunks_dicts.append(chunk_dict)
        
        # Generate PDF filename
        pdf_filename = md_file.name.replace('.md', '.pdf')
        pdf_filename = pdf_filename.replace('[', '').replace(']', '')
        pdf_filename = pdf_filename.replace('(', '').replace(')', '')
        pdf_filename = pdf_filename.replace(',', '')
        pdf_filename = pdf_filename.replace(' ', '_')
        while '__' in pdf_filename:
            pdf_filename = pdf_filename.replace('__', '_')
        pdf_filename = pdf_filename.strip('_')
        
        # Index
        provider = QwenProvider()
        index_gdd_chunks_to_supabase(
            doc_id=doc_id,
            chunks=chunks_dicts,
            provider=provider,
            markdown_content=markdown_content,
            pdf_storage_path=pdf_filename
        )
        logger.info(f"✅ Successfully indexed {md_file.name}")
        return True
        
    except Exception as e:
        logger.error(f"❌ Error indexing {md_file.name}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False


def main():
    markdown_dir = PROJECT_ROOT / "gdd_data" / "markdown"
    
    target_files = [
        "[Progression Module] [Tank Wars] Tổng Quan Artifact System.md",
        "[Progression Module] [Tank War] Onboarding Design (Chưa xong).md",
        "[Combat Module] [Tank War] Hệ Thống Auto Focus.md",
    ]
    
    logger.info("="*80)
    logger.info("INDEXING SPECIFIC DOCUMENTS")
    logger.info("="*80)
    
    success_count = 0
    for filename in target_files:
        md_file = markdown_dir / filename
        if md_file.exists():
            if index_document(md_file):
                success_count += 1
        else:
            logger.warning(f"File not found: {md_file}")
    
    logger.info(f"\n✅ Indexed {success_count}/{len(target_files)} documents")


if __name__ == "__main__":
    main()


