"""
RAG Evaluation Script

This script:
1. Generates 100 test cases from your indexed documents
2. Evaluates retrieval and answer generation
3. Calculates average similarity scores
4. Saves detailed results

Usage:
    python -m gdd_rag_backbone.scripts.run_evaluation
"""

import argparse
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from gdd_rag_backbone.rag_backend.evaluator import RAGEvaluator, TestCase
from gdd_rag_backbone.rag_backend.chunk_qa import (
    load_doc_status,
    ask_across_docs,
    list_indexed_docs,
)
from gdd_rag_backbone.llm_providers.qwen_provider import QwenProvider
from gdd_rag_backbone.config import DEFAULT_OUTPUT_DIR


def create_retrieval_function(provider, all_doc_ids):
    """
    Create a retrieval function that matches the evaluator's expected signature.
    
    Args:
        provider: LLM provider
        all_doc_ids: List of all document IDs to search across
    
    Returns:
        Function(question, doc_ids) -> (retrieved_chunks, generated_answer)
    """
    def retrieval_func(question: str, doc_ids: list) -> tuple:
        """
        Retrieve chunks and generate answer for a question.
        
        Args:
            question: The question to answer
            doc_ids: Document IDs to search (can be subset of all_doc_ids)
        
        Returns:
            (retrieved_chunks, generated_answer)
        """
        # Use ask_across_docs to get answer and context
        result = ask_across_docs(
            doc_ids=doc_ids if doc_ids else all_doc_ids,
            question=question,
            provider=provider,
            top_k=6,
            per_doc_limit=2,
        )
        
        retrieved_chunks = result.get("context", [])
        generated_answer = result.get("answer", "")
        
        return retrieved_chunks, generated_answer
    
    return retrieval_func


def main():
    parser = argparse.ArgumentParser(description="Evaluate RAG system on 100 test cases")
    parser.add_argument(
        "--num-cases",
        type=int,
        default=100,
        help="Number of test cases to generate (default: 100)"
    )
    parser.add_argument(
        "--chunks-per-doc",
        type=int,
        default=None,
        help="Max chunks to sample per document (default: all available)"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR / "evaluation",
        help="Output directory for results (default: output/evaluation)"
    )
    parser.add_argument(
        "--similarity-model",
        type=str,
        default="all-MiniLM-L6-v2",
        help="Sentence transformer model for similarity (default: all-MiniLM-L6-v2)"
    )
    parser.add_argument(
        "--device",
        type=str,
        default="cpu",
        choices=["cpu", "cuda"],
        help="Device for similarity model (default: cpu)"
    )
    parser.add_argument(
        "--one-per-doc",
        action="store_true",
        help="Generate exactly 1 test case per document (ignores --num-cases)"
    )
    args = parser.parse_args()
    
    print("="*70)
    print("RAG EVALUATION SYSTEM")
    print("="*70)
    if args.one_per_doc:
        print("Mode: 1 test case per document")
    else:
        print(f"Test cases: {args.num_cases}")
    print(f"Output directory: {args.output_dir}")
    print(f"Similarity model: {args.similarity_model}")
    print("="*70)
    print()
    
    # Check for indexed documents
    print("Checking indexed documents...")
    status = load_doc_status()
    indexed_docs = [
        doc_id for doc_id, meta in status.items()
        if meta.get("chunks_count", 0) > 0
    ]
    
    if not indexed_docs:
        print("ERROR: No indexed documents found!")
        print("Please index some documents first using the indexing system.")
        return 1
    
    print(f"Found {len(indexed_docs)} indexed documents")
    for doc_id in indexed_docs[:5]:  # Show first 5
        meta = status[doc_id]
        chunks_count = meta.get("chunks_count", 0)
        file_path = meta.get("file_path", doc_id)
        print(f"  - {file_path}: {chunks_count} chunks")
    if len(indexed_docs) > 5:
        print(f"  ... and {len(indexed_docs) - 5} more")
    print()
    
    # Initialize provider
    print("Initializing LLM provider...")
    try:
        provider = QwenProvider()
        print("LLM provider initialized")
    except Exception as e:
        print(f"ERROR: Could not initialize LLM provider: {e}")
        print("Please check your API key in .env file")
        return 1
    
    # Initialize evaluator
    print("Initializing evaluator...")
    try:
        evaluator = RAGEvaluator(
            similarity_model=args.similarity_model,
            device=args.device,
        )
    except ImportError as e:
        print(f"ERROR: {e}")
        print("Install with: pip install sentence-transformers")
        return 1
    
    # Generate test cases
    print("\n" + "="*70)
    print("STEP 1: GENERATING TEST CASES")
    print("="*70)
    test_cases = evaluator.generate_test_cases(
        provider=provider,
        doc_ids=indexed_docs,
        num_cases=args.num_cases,
        chunks_per_doc=args.chunks_per_doc,
        one_per_doc=args.one_per_doc,
    )
    
    if not test_cases:
        print("ERROR: No test cases generated!")
        return 1
    
    # Create retrieval function
    retrieval_func = create_retrieval_function(provider, indexed_docs)
    
    # Run evaluation
    print("\n" + "="*70)
    print("STEP 2: RUNNING EVALUATION")
    print("="*70)
    results, summary = evaluator.evaluate_batch(
        test_cases=test_cases,
        retrieval_func=retrieval_func,
    )
    
    # Print summary
    evaluator.print_summary(summary)
    
    # Save results
    print("\n" + "="*70)
    print("STEP 3: SAVING RESULTS")
    print("="*70)
    evaluator.save_results(
        test_cases=test_cases,
        results=results,
        summary=summary,
        output_dir=args.output_dir,
    )
    
    print("\n" + "="*70)
    print("EVALUATION COMPLETE")
    print("="*70)
    print(f"\nAverage Answer Similarity: {summary.average_answer_similarity:.3f}")
    print(f"Retrieval Success Rate: {summary.retrieval_success_rate*100:.1f}%")
    print(f"\nResults saved to: {args.output_dir}")
    print("="*70)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

