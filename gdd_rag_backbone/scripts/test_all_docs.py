#!/usr/bin/env python3
"""
Test script to index and query all documents in the docs folder.
"""
import asyncio
import sys
from pathlib import Path

if "pytest" in sys.modules:  # pragma: no cover - integration script
    import pytest

    pytest.skip("Integration script skipped during test suite", allow_module_level=True)

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from gdd_rag_backbone.config import DEFAULT_DOCS_DIR
from gdd_rag_backbone.llm_providers import QwenProvider, make_llm_model_func, make_embedding_func
from gdd_rag_backbone.rag_backend import index_document, ask_question
from gdd_rag_backbone.gdd import extract_tanks, extract_maps


async def test_document(doc_path: Path):
    """Test indexing and querying a single document."""
    doc_id = doc_path.stem.replace(" ", "_").replace("[", "").replace("]", "").lower()
    
    print("\n" + "=" * 80)
    print(f"📄 Testing: {doc_path.name}")
    print(f"   Document ID: {doc_id}")
    print("=" * 80)
    
    # Initialize provider
    try:
        provider = QwenProvider()
        llm_func = make_llm_model_func(provider)
        embedding_func = make_embedding_func(provider)
    except Exception as e:
        print(f"❌ Error initializing provider: {e}")
        return False
    
    # Index document
    try:
        print(f"\n🔍 Indexing document...")
        await index_document(
            doc_path=doc_path,
            doc_id=doc_id,
            llm_func=llm_func,
            embedding_func=embedding_func,
        )
        print(f"✅ Document indexed successfully!")
    except Exception as e:
        print(f"❌ Error indexing: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # Test queries
    print(f"\n📝 Running test queries...")
    test_queries = [
        "What is this document about?",
        "List the main topics or sections in this document.",
    ]
    
    for query in test_queries:
        try:
            print(f"\n   Q: {query}")
            answer = await ask_question(doc_id, query, debug=False)
            print(f"   A: {answer[:200]}..." if len(answer) > 200 else f"   A: {answer}")
        except Exception as e:
            print(f"   ❌ Error: {e}")
    
    # Try extraction (if relevant)
    try:
        print(f"\n📊 Extracting structured data...")
        maps = await extract_maps(doc_id, llm_func=llm_func)
        if maps:
            print(f"   Found {len(maps)} map(s):")
            for map_spec in maps[:3]:  # Show first 3
                print(f"     - {map_spec.name}")
    except Exception as e:
        print(f"   (No maps found or extraction error: {e})")
    
    try:
        tanks = await extract_tanks(doc_id, llm_func=llm_func)
        if tanks:
            print(f"   Found {len(tanks)} tank(s):")
            for tank in tanks[:3]:  # Show first 3
                print(f"     - {tank.name} ({tank.class_name})")
    except Exception as e:
        print(f"   (No tanks found or extraction error: {e})")
    
    return True


async def main():
    """Main function to test all PDF documents."""
    print("\n" + "=" * 80)
    print("🚀 Testing All Documents in docs/ folder")
    print("=" * 80)
    
    docs_dir = Path(DEFAULT_DOCS_DIR)
    pdf_files = sorted(docs_dir.glob("*.pdf"))
    
    if not pdf_files:
        print("❌ No PDF files found in docs/ directory")
        return
    
    print(f"\n📚 Found {len(pdf_files)} PDF document(s):")
    for i, pdf in enumerate(pdf_files, 1):
        print(f"   {i}. {pdf.name}")
    
    results = []
    
    for pdf_file in pdf_files:
        try:
            success = await test_document(pdf_file)
            results.append((pdf_file.name, success))
        except Exception as e:
            print(f"\n❌ Fatal error with {pdf_file.name}: {e}")
            results.append((pdf_file.name, False))
    
    # Summary
    print("\n" + "=" * 80)
    print("📊 SUMMARY")
    print("=" * 80)
    
    successful = [name for name, success in results if success]
    failed = [name for name, success in results if not success]
    
    if successful:
        print(f"\n✅ Successfully processed ({len(successful)}):")
        for name in successful:
            print(f"   ✓ {name}")
    
    if failed:
        print(f"\n❌ Failed ({len(failed)}):")
        for name in failed:
            print(f"   ✗ {name}")
    
    print("\n" + "=" * 80)
    print()


if __name__ == "__main__":
    asyncio.run(main())

