"""
Fix documents that have markdown_content but no chunks, or need markdown_content stored.

This script:
1. Finds documents with markdown_content but 0 chunks
2. Indexes them (creates chunks and embeddings)
3. Also stores markdown_content for documents that have chunks but no markdown_content
"""

import sys
from pathlib import Path
from typing import List, Dict

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv()

from backend.storage.supabase_client import get_supabase_client
from backend.storage.gdd_supabase_storage import index_gdd_chunks_to_supabase
from gdd_rag_backbone.llm_providers import QwenProvider
from gdd_rag_backbone.markdown_chunking import MarkdownChunker
from gdd_rag_backbone.scripts.chunk_markdown_files import generate_doc_id
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def get_problematic_documents() -> List[Dict]:
    """Get list of problematic documents that need fixing."""
    client = get_supabase_client()
    markdown_dir = PROJECT_ROOT / "gdd_data" / "markdown"
    
    problematic_doc_ids = [
        'Character_Module_Tank_War_Elemental_Class',
        'Combat_Module_Tank_War_Shooting_Logic',
        'Progression_Module_Tank_Wars_Tổng_Quan_Artifact_System',
        'Progression_Module_Tank_War_Onboarding_Design_(Chưa_xong)',
        'Progression_Module_Tank_War_Leaderboard_System',
        'Progression_Module_Tank_War_ELO_&_RANK_System_OLD_(not_use)',
        'Combat_Module_Tank_War_Hệ_Thống_Nâng_Cấp_Tank_In_Match',
        'Combat_Module_Tank_War_Hệ_Thống_Auto_Focus',
    ]
    
    documents = []
    for doc_id in problematic_doc_ids:
        # Get document info
        doc_result = client.table('gdd_documents').select('doc_id, name, file_path, markdown_content').eq('doc_id', doc_id).limit(1).execute()
        if not doc_result.data:
            logger.warning(f"  ⚠️  Document not found: {doc_id}")
            continue
        
        doc = doc_result.data[0]
        name = doc.get('name', '')
        file_path = doc.get('file_path', '')
        markdown_content = doc.get('markdown_content', '')
        
        # Check chunks
        chunks_result = client.table('gdd_chunks').select('chunk_id').eq('doc_id', doc_id).execute()
        chunks_count = len(chunks_result.data or [])
        
        # Find markdown file
        md_file = None
        if file_path:
            md_file = Path(file_path)
            if not md_file.exists():
                md_file = None
        
        if not md_file and name:
            # Try to find by name
            md_file = markdown_dir / name
            if not md_file.exists():
                # Try without .md extension
                if name.endswith('.md'):
                    md_file = markdown_dir / name
                else:
                    md_file = markdown_dir / f"{name}.md"
                if not md_file.exists():
                    md_file = None
        
        if not md_file:
            # Try to find by doc_id
            for md_path in markdown_dir.glob("*.md"):
                if generate_doc_id(md_path) == doc_id:
                    md_file = md_path
                    break
        
        documents.append({
            'doc_id': doc_id,
            'name': name,
            'file_path': file_path,
            'markdown_file': md_file,
            'has_markdown_content': bool(markdown_content),
            'markdown_content': markdown_content,
            'chunks_count': chunks_count
        })
    
    return documents


def fix_document(doc_info: Dict, provider: QwenProvider) -> bool:
    """Fix a single document by indexing it or storing markdown_content."""
    doc_id = doc_info['doc_id']
    md_file = doc_info['markdown_file']
    has_markdown = doc_info['has_markdown_content']
    chunks_count = doc_info['chunks_count']
    
    logger.info(f"\n{'='*60}")
    logger.info(f"Processing: {doc_id}")
    logger.info(f"  Markdown file: {md_file}")
    logger.info(f"  Has markdown_content: {has_markdown}")
    logger.info(f"  Chunks: {chunks_count}")
    
    # Case 1: Has chunks but no markdown_content - store markdown_content
    if chunks_count > 0 and not has_markdown and md_file and md_file.exists():
        logger.info(f"  📝 Storing markdown_content...")
        try:
            markdown_content = md_file.read_text(encoding='utf-8')
            client = get_supabase_client(use_service_key=True)
            client.table('gdd_documents').update({
                'markdown_content': markdown_content
            }).eq('doc_id', doc_id).execute()
            logger.info(f"  ✅ Stored markdown_content")
            return True
        except Exception as e:
            logger.error(f"  ❌ Error storing markdown_content: {e}")
            return False
    
    # Case 2: Has markdown_content but no chunks - index it
    if chunks_count == 0 and md_file and md_file.exists():
        logger.info(f"  📤 Indexing document (creating chunks)...")
        try:
            markdown_content = md_file.read_text(encoding='utf-8')
            
            # Chunk the markdown
            chunker = MarkdownChunker()
            chunks = chunker.chunk_document(
                markdown_content=markdown_content,
                doc_id=doc_id,
                filename=md_file.name,
            )
            logger.info(f"  ✓ Created {len(chunks)} chunks")
            
            # Convert to dictionaries
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
            
            # Index to Supabase
            index_gdd_chunks_to_supabase(
                doc_id=doc_id,
                chunks=chunks_dicts,
                provider=provider,
                markdown_content=markdown_content,
                pdf_storage_path=pdf_filename
            )
            logger.info(f"  ✅ Successfully indexed")
            return True
        except Exception as e:
            logger.error(f"  ❌ Error indexing: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    # Case 3: No markdown file found
    if not md_file or not md_file.exists():
        logger.warning(f"  ⚠️  Markdown file not found for {doc_id}")
        logger.warning(f"     Expected: {md_file}")
        return False
    
    logger.info(f"  ℹ️  No action needed")
    return True


def main():
    logger.info("="*80)
    logger.info("FIX MISSING CHUNKS AND MARKDOWN_CONTENT")
    logger.info("="*80)
    
    # Get problematic documents
    logger.info("\n📋 Step 1: Finding problematic documents...")
    documents = get_problematic_documents()
    logger.info(f"Found {len(documents)} documents to check")
    
    # Initialize provider
    logger.info("\n🔧 Step 2: Initializing QwenProvider...")
    try:
        provider = QwenProvider()
        logger.info("✓ Provider initialized")
    except Exception as e:
        logger.error(f"❌ Failed to initialize provider: {e}")
        return
    
    # Fix each document
    logger.info("\n🚀 Step 3: Fixing documents...")
    success_count = 0
    error_count = 0
    
    for doc_info in documents:
        try:
            if fix_document(doc_info, provider):
                success_count += 1
            else:
                error_count += 1
        except Exception as e:
            logger.error(f"  ❌ Error processing {doc_info['doc_id']}: {e}")
            error_count += 1
    
    # Summary
    logger.info("\n" + "="*80)
    logger.info("SUMMARY")
    logger.info("="*80)
    logger.info(f"Documents processed: {len(documents)}")
    logger.info(f"Successfully fixed:  {success_count}")
    logger.info(f"Errors:              {error_count}")
    logger.info("="*80)
    
    logger.info("\n✅ Done!")


if __name__ == "__main__":
    main()


