"""
Script to evaluate manual test cases from a text file.
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import List, Optional, Dict
from dataclasses import asdict

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from gdd_rag_backbone.rag_backend.evaluator import RAGEvaluator, TestCase
from gdd_rag_backbone.rag_backend.chunk_qa import (
    load_doc_status,
    ask_across_docs,
    load_doc_chunks,
)
from gdd_rag_backbone.llm_providers.qwen_provider import QwenProvider
from gdd_rag_backbone.config import DEFAULT_OUTPUT_DIR


def normalize_doc_id(doc_id: str) -> str:
    """Normalize doc_id to match storage format."""
    # Replace spaces with underscores, handle brackets
    # [Asset,UI][Tank_War]Garage_Design-UI_UX -> [Asset,_UI]_[Tank_War]_Garage_Design_-_UI_UX
    # Try to match common patterns
    doc_id = doc_id.strip()
    # Common transformations
    doc_id = doc_id.replace(" ", "_")
    # Handle cases like [Asset,UI] -> [Asset,_UI]
    doc_id = re.sub(r'\[([^,]+),([^\]]+)\]', r'[\1,_\2]', doc_id)
    return doc_id


def find_matching_doc_id(manual_doc_id: str, available_doc_ids: List[str]) -> Optional[str]:
    """Find matching doc_id from available documents."""
    # Normalize both for comparison - handle the specific format differences
    def normalize_for_match(text: str) -> str:
        # Convert to lowercase
        text = text.lower()
        # Handle brackets: [Asset,UI] -> asset_ui, [Asset,_UI] -> asset_ui
        # First extract content from brackets and normalize
        def process_bracket(match):
            content = match.group(1)
            # Split by comma, space, or underscore and join with underscore
            parts = re.split(r'[,\s_]+', content)
            return '_'.join(p for p in parts if p)
        
        # Replace brackets with normalized content
        text = re.sub(r'\[([^\]]+)\]', process_bracket, text)
        # Normalize spaces, underscores, hyphens to single underscore
        text = re.sub(r'[\s_-]+', '_', text)
        # Remove any remaining brackets but keep underscores
        text = re.sub(r'[^\w_]', '', text)
        # Normalize multiple underscores to single
        text = re.sub(r'_+', '_', text)
        return text.strip('_')
    
    manual_normalized = normalize_for_match(manual_doc_id)
    
    # Try exact match first
    for doc_id in available_doc_ids:
        if normalize_for_match(doc_id) == manual_normalized:
            return doc_id
    
    # Try partial matching - extract key words
    manual_words = set(re.findall(r'\w+', manual_normalized))
    if not manual_words:
        return None
    
    best_match = None
    best_score = 0
    
    for doc_id in available_doc_ids:
        doc_id_normalized = normalize_for_match(doc_id)
        doc_id_words = set(re.findall(r'\w+', doc_id_normalized))
        
        # Calculate overlap
        overlap = len(manual_words & doc_id_words)
        total_words = len(manual_words)
        
        # Require at least 50% word overlap (lowered threshold)
        if overlap > best_score and overlap >= max(1, total_words * 0.5):
            best_score = overlap
            best_match = doc_id
    
    return best_match


def find_best_chunk(doc_id: str, expected_answer: str) -> tuple:
    """Find chunk that best matches the expected answer."""
    chunks = load_doc_chunks(doc_id)
    
    if not chunks:
        return None, None
    
    # Find chunk with highest word overlap
    answer_words = set(re.findall(r'\w+', expected_answer.lower()))
    best_chunk = None
    best_score = 0
    
    for chunk in chunks:
        chunk_words = set(re.findall(r'\w+', chunk.content.lower()))
        overlap = len(answer_words & chunk_words)
        if overlap > best_score:
            best_score = overlap
            best_chunk = chunk
    
    if best_chunk:
        return best_chunk.chunk_id, best_chunk.content
    return chunks[0].chunk_id, chunks[0].content


def parse_manual_test_cases(txt_file: Path) -> List[dict]:
    """Parse manual test cases from text file."""
    content = txt_file.read_text(encoding="utf-8")
    
    # Split by separator lines
    sections = re.split(r'={10,}', content)
    
    test_cases = []
    for section in sections:
        section = section.strip()
        if not section or "DOC_ID:" not in section:
            continue
        
        # Extract DOC_ID
        doc_id_match = re.search(r'DOC_ID:\s*(.+?)(?=\n|$)', section, re.MULTILINE)
        # Extract QUESTION
        question_match = re.search(r'QUESTION:\s*(.+?)(?=\nANSWER:|$)', section, re.DOTALL)
        # Extract ANSWER
        answer_match = re.search(r'ANSWER:\s*(.+?)(?=\n==========|$)', section, re.DOTALL)
        
        if doc_id_match and question_match and answer_match:
            doc_id = doc_id_match.group(1).strip()
            question = question_match.group(1).strip()
            answer = answer_match.group(1).strip()
            
            test_cases.append({
                "doc_id": doc_id,
                "question": question,
                "answer": answer,
            })
    
    return test_cases


def convert_to_test_cases(manual_cases: List[dict], available_doc_ids: List[str]) -> List[TestCase]:
    """Convert manual test cases to TestCase objects."""
    test_cases = []
    
    for i, case in enumerate(manual_cases):
        manual_doc_id = case["doc_id"]
        question = case["question"]
        expected_answer = case["answer"]
        
        # Find matching doc_id
        doc_id = find_matching_doc_id(manual_doc_id, available_doc_ids)
        if not doc_id:
            print(f"Warning: Could not find doc_id for '{manual_doc_id}', skipping...")
            continue
        
        # Find best matching chunk
        chunk_id, source_chunk = find_best_chunk(doc_id, expected_answer)
        
        test_case = TestCase(
            test_id=i + 1,
            doc_id=doc_id,
            chunk_id=chunk_id,
            source_chunk=source_chunk,
            generated_question=question,
            expected_answer=expected_answer,
        )
        test_cases.append(test_case)
    
    return test_cases


def create_retrieval_function(provider, all_doc_ids):
    """Create retrieval function."""
    def retrieval_func(question: str, doc_ids: list) -> tuple:
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


def merge_summaries(summary1_path: Path, summary2_path: Path, output_path: Path):
    """Merge two evaluation summaries."""
    with open(summary1_path, 'r', encoding='utf-8') as f:
        summary1 = json.load(f)
    
    with open(summary2_path, 'r', encoding='utf-8') as f:
        summary2 = json.load(f)
    
    # Merge statistics
    total_cases = summary1["total_cases"] + summary2["total_cases"]
    evaluated = summary1["evaluated"] + summary2["evaluated"]
    failed = summary1["failed"] + summary2["failed"]
    
    # Weighted averages
    weight1 = summary1["evaluated"] if summary1["evaluated"] > 0 else 0
    weight2 = summary2["evaluated"] if summary2["evaluated"] > 0 else 0
    total_weight = weight1 + weight2
    
    if total_weight > 0:
        avg_answer_sim = (
            (summary1["average_answer_similarity"] * weight1 + 
             summary2["average_answer_similarity"] * weight2) / total_weight
        )
        avg_top_chunk_sim = (
            (summary1["average_top_chunk_similarity"] * weight1 + 
             summary2["average_top_chunk_similarity"] * weight2) / total_weight
        )
    else:
        avg_answer_sim = 0.0
        avg_top_chunk_sim = 0.0
    
    # Average retrieval rank (if both have it)
    if summary1.get("average_retrieval_rank") is not None and summary2.get("average_retrieval_rank") is not None:
        avg_retrieval_rank = (
            (summary1["average_retrieval_rank"] * weight1 + 
             summary2["average_retrieval_rank"] * weight2) / total_weight
        )
    else:
        avg_retrieval_rank = summary1.get("average_retrieval_rank") if summary1.get("average_retrieval_rank") is not None else summary2.get("average_retrieval_rank")
    
    # Combined success rates
    retrieval_success1 = summary1["retrieval_success_rate"] * summary1["evaluated"]
    retrieval_success2 = summary2["retrieval_success_rate"] * summary2["evaluated"]
    retrieval_success_rate = (retrieval_success1 + retrieval_success2) / evaluated if evaluated > 0 else 0.0
    
    high_sim1 = summary1["high_similarity_rate"] * summary1["evaluated"]
    high_sim2 = summary2["high_similarity_rate"] * summary2["evaluated"]
    high_similarity_rate = (high_sim1 + high_sim2) / evaluated if evaluated > 0 else 0.0
    
    # Average times
    avg_retrieval_time = (
        (summary1["average_retrieval_time"] * weight1 + 
         summary2["average_retrieval_time"] * weight2) / total_weight
        if total_weight > 0 else 0.0
    )
    
    total_time = summary1["total_time"] + summary2["total_time"]
    
    # Percentiles - simple average for now
    p50 = (summary1["p50_answer_similarity"] + summary2["p50_answer_similarity"]) / 2
    p75 = (summary1["p75_answer_similarity"] + summary2["p75_answer_similarity"]) / 2
    p90 = (summary1["p90_answer_similarity"] + summary2["p90_answer_similarity"]) / 2
    
    merged = {
        "total_cases": total_cases,
        "evaluated": evaluated,
        "failed": failed,
        "average_answer_similarity": avg_answer_sim,
        "average_top_chunk_similarity": avg_top_chunk_sim,
        "average_retrieval_rank": avg_retrieval_rank,
        "p50_answer_similarity": p50,
        "p75_answer_similarity": p75,
        "p90_answer_similarity": p90,
        "retrieval_success_rate": retrieval_success_rate,
        "high_similarity_rate": high_similarity_rate,
        "average_retrieval_time": avg_retrieval_time,
        "average_generation_time": 0.0,
        "total_time": total_time,
        "test_set_1": {
            "total_cases": summary1["total_cases"],
            "evaluated": summary1["evaluated"],
            "average_answer_similarity": summary1["average_answer_similarity"],
            "retrieval_success_rate": summary1["retrieval_success_rate"],
        },
        "test_set_2": {
            "total_cases": summary2["total_cases"],
            "evaluated": summary2["evaluated"],
            "average_answer_similarity": summary2["average_answer_similarity"],
            "retrieval_success_rate": summary2["retrieval_success_rate"],
        },
    }
    
    output_path.write_text(
        json.dumps(merged, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )
    print(f"Merged summary saved to {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Evaluate manual test cases")
    parser.add_argument(
        "--input-file",
        type=Path,
        default=Path(r"C:\Users\CPU12391\Downloads\tank_war_100_questions.txt"),
        help="Path to manual test cases text file"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR / "evaluation",
        help="Output directory"
    )
    parser.add_argument(
        "--similarity-model",
        type=str,
        default="all-MiniLM-L6-v2",
        help="Similarity model"
    )
    args = parser.parse_args()
    
    print("="*70)
    print("MANUAL TEST CASE EVALUATION")
    print("="*70)
    
    # Parse manual test cases
    print(f"\nParsing manual test cases from {args.input_file}...")
    manual_cases = parse_manual_test_cases(args.input_file)
    print(f"Found {len(manual_cases)} test cases")
    
    # Get available doc IDs
    status = load_doc_status()
    available_doc_ids = [doc_id for doc_id, meta in status.items() if meta.get("chunks_count", 0) > 0]
    print(f"Found {len(available_doc_ids)} indexed documents")
    
    # Convert to TestCase objects
    print("\nConverting to TestCase format and matching documents...")
    print(f"Sample manual doc_ids: {[c['doc_id'] for c in manual_cases[:3]]}")
    print(f"Sample available doc_ids: {available_doc_ids[:5]}")
    test_cases = convert_to_test_cases(manual_cases, available_doc_ids)
    print(f"Converted {len(test_cases)} test cases")
    
    if not test_cases:
        print("ERROR: No test cases could be converted!")
        return 1
    
    # Save test cases
    test_cases_path = args.output_dir / "test_cases_2.json"
    args.output_dir.mkdir(parents=True, exist_ok=True)
    test_cases_data = [{
        "test_id": tc.test_id,
        "doc_id": tc.doc_id,
        "chunk_id": tc.chunk_id,
        "source_chunk": tc.source_chunk,
        "generated_question": tc.generated_question,
        "expected_answer": tc.expected_answer,
    } for tc in test_cases]
    test_cases_path.write_text(
        json.dumps(test_cases_data, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )
    print(f"Saved test cases to {test_cases_path}")
    
    # Initialize provider
    print("\nInitializing LLM provider...")
    try:
        provider = QwenProvider()
        print("LLM provider initialized")
    except Exception as e:
        print(f"ERROR: {e}")
        return 1
    
    # Initialize evaluator
    print("Initializing evaluator...")
    try:
        evaluator = RAGEvaluator(similarity_model=args.similarity_model)
    except ImportError as e:
        print(f"ERROR: {e}")
        return 1
    
    # Create retrieval function
    retrieval_func = create_retrieval_function(provider, available_doc_ids)
    
    # Run evaluation
    print("\n" + "="*70)
    print("RUNNING EVALUATION")
    print("="*70)
    results, summary = evaluator.evaluate_batch(
        test_cases=test_cases,
        retrieval_func=retrieval_func,
    )
    
    # Print summary
    evaluator.print_summary(summary)
    
    # Save results
    results_path = args.output_dir / "evaluation_results_2_before.json"
    results_data = [{
        "test_id": r.test_id,
        "question": r.question,
        "expected_answer": r.expected_answer,
        "generated_answer": r.generated_answer,
        "retrieved_chunks": r.retrieved_chunks,
        "answer_similarity": r.answer_similarity,
        "retrieval_rank": r.retrieval_rank,
        "top_chunk_similarity": r.top_chunk_similarity,
        "doc_id": r.doc_id,
        "chunk_id": r.chunk_id,
        "retrieval_time": r.retrieval_time,
        "generation_time": r.generation_time,
    } for r in results]
    results_path.write_text(
        json.dumps(results_data, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )
    print(f"\nResults saved to {results_path}")
    
    # Save summary
    summary_path = args.output_dir / "evaluation_summary_2_before.json"
    summary_data = {
        "total_cases": summary.total_cases,
        "evaluated": summary.evaluated,
        "failed": summary.failed,
        "average_answer_similarity": summary.average_answer_similarity,
        "average_top_chunk_similarity": summary.average_top_chunk_similarity,
        "average_retrieval_rank": summary.average_retrieval_rank,
        "p50_answer_similarity": summary.p50_answer_similarity,
        "p75_answer_similarity": summary.p75_answer_similarity,
        "p90_answer_similarity": summary.p90_answer_similarity,
        "retrieval_success_rate": summary.retrieval_success_rate,
        "high_similarity_rate": summary.high_similarity_rate,
        "average_retrieval_time": summary.average_retrieval_time,
        "average_generation_time": summary.average_generation_time,
        "total_time": summary.total_time,
    }
    summary_path.write_text(
        json.dumps(summary_data, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )
    print(f"Summary saved to {summary_path}")
    
    # Merge with existing summary
    existing_summary_path = args.output_dir / "evaluation_summary_before.json"
    if existing_summary_path.exists():
        print("\nMerging with existing summary...")
        merge_summaries(existing_summary_path, summary_path, existing_summary_path)
        print(f"Merged summary updated in {existing_summary_path}")
    else:
        print(f"\n⚠ Existing summary not found at {existing_summary_path}")
        print("  Creating new merged summary...")
        merge_summaries(summary_path, summary_path, existing_summary_path)
    
    print("\n" + "="*70)
    print("EVALUATION COMPLETE")
    print("="*70)
    print(f"\nTest Set 2 Results:")
    print(f"  Average Answer Similarity: {summary.average_answer_similarity:.3f}")
    print(f"  Retrieval Success Rate: {summary.retrieval_success_rate*100:.1f}%")
    print(f"\nResults saved to: {args.output_dir}")
    print("="*70)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

