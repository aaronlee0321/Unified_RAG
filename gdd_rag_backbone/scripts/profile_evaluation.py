"""
RAG Evaluation Profiling Script

This script runs evaluation on 5 test cases with detailed timing measurements
to identify performance bottlenecks.

Usage:
    python -m gdd_rag_backbone.scripts.profile_evaluation
"""

import argparse
import sys
import time
from pathlib import Path
from typing import Dict, List, Tuple
from dataclasses import dataclass, asdict
import json

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from gdd_rag_backbone.rag_backend.evaluator import RAGEvaluator, TestCase
from gdd_rag_backbone.rag_backend.chunk_qa import (
    load_doc_status,
    load_doc_chunks,
    get_doc_metadata,
    _embed_texts,
    _load_chunk_vectors,
    _score_chunks_hybrid_rrf,
    _rerank_with_cross_encoder,
    _filter_chunks_by_evidence,
    _select_top_chunks,
    _build_prompt,
    _normalize_vector,
)
from gdd_rag_backbone.llm_providers.qwen_provider import QwenProvider
from gdd_rag_backbone.config import DEFAULT_OUTPUT_DIR


@dataclass
class ProcessTiming:
    """Timing for a single process step"""
    process_name: str
    start_time: float
    end_time: float
    duration_ms: float
    
    def to_dict(self):
        return {
            "process": self.process_name,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_ms": round(self.duration_ms, 2),
        }


@dataclass
class QueryTiming:
    """Timing breakdown for a single query"""
    question: str
    doc_id: str
    timings: List[ProcessTiming]
    total_time_ms: float
    
    def to_dict(self):
        return {
            "question": self.question[:100] + "..." if len(self.question) > 100 else self.question,
            "doc_id": self.doc_id,
            "timings": [t.to_dict() for t in self.timings],
            "total_time_ms": round(self.total_time_ms, 2),
        }


class ProfiledRetrieval:
    """Retrieval function with detailed timing instrumentation"""
    
    def __init__(self, provider, doc_id: str):
        self.provider = provider
        self.doc_id = doc_id
        self.timings: List[ProcessTiming] = []
    
    def _time_step(self, step_name: str):
        """Context manager for timing a step"""
        class TimingContext:
            def __init__(self, profiler, name):
                self.profiler = profiler
                self.name = name
                self.start = None
            
            def __enter__(self):
                self.start = time.time()
                return self
            
            def __exit__(self, *args):
                end = time.time()
                duration_ms = (end - self.start) * 1000
                self.profiler.timings.append(ProcessTiming(
                    process_name=self.name,
                    start_time=self.start,
                    end_time=end,
                    duration_ms=duration_ms,
                ))
        
        return TimingContext(self, step_name)
    
    def retrieve(self, question: str) -> Tuple[List[Dict], str]:
        """Retrieve chunks and generate answer with detailed timing"""
        self.timings = []
        total_start = time.time()
        
        # Step 1: Load chunks
        with self._time_step("1_load_chunks"):
            chunks = load_doc_chunks(self.doc_id)
        
        if not chunks:
            return [], "No chunks found"
        
        # Step 2: Question embedding
        question_embedding = None
        with self._time_step("2_question_embedding"):
            try:
                question_embedding = _embed_texts(self.provider, [question], use_cache=True)[0]
                question_embedding = _normalize_vector(question_embedding)
            except Exception as e:
                print(f"Embedding error: {e}")
        
        # Step 3: Load document vectors
        vectors = {}
        with self._time_step("3_load_vectors"):
            vectors = _load_chunk_vectors([self.doc_id], normalize=True)
        
        # Step 4: Vector search (dense + sparse scoring)
        scored = []
        with self._time_step("4_vector_search_scoring"):
            scored = _score_chunks_hybrid_rrf(
                question_embedding=question_embedding,
                chunks=chunks,
                vectors=vectors,
                provider=self.provider,
                question_text=question,
                top_n_each=12,
            )
        
        # Step 5: Evidence filtering
        filtered = []
        with self._time_step("5_evidence_filtering"):
            filtered = _filter_chunks_by_evidence(
                question=question,
                scored_chunks=scored,
                min_evidence_score=0.15,
                keep_top_n=10,
            )
        
        # Step 6: Reranking
        reranked = []
        with self._time_step("6_reranking"):
            reranked = _rerank_with_cross_encoder(
                question=question,
                scored_chunks=filtered,
                provider=self.provider,
                top_n=min(12, len(filtered)),
            )
        
        # Step 7: Select top chunks
        top_chunks = []
        with self._time_step("7_select_top_chunks"):
            top_chunks = _select_top_chunks(
                scored=reranked,
                top_k=6,
                per_doc_limit=None,
            )
        
        # Step 8: Build prompt
        prompt = ""
        with self._time_step("8_build_prompt"):
            metadata = get_doc_metadata(self.doc_id) or {}
            top_records = [record for _, record in top_chunks]
            prompt = _build_prompt(
                metadata.get("file_path", self.doc_id),
                [r.content for r in top_records],
                question
            )
        
        # Step 9: Generate answer (LLM call)
        answer = ""
        with self._time_step("9_llm_answer_generation"):
            try:
                answer = self.provider.llm(prompt=prompt)
            except Exception as e:
                answer = f"Error: {str(e)}"
        
        total_end = time.time()
        total_time_ms = (total_end - total_start) * 1000
        
        # Create context payload
        context_payload = [
            {
                "chunk_id": record.chunk_id,
                "doc_id": record.doc_id,
                "content": record.content[:200] + "..." if len(record.content) > 200 else record.content,
                "score": score,
            }
            for score, record in top_chunks
        ]
        
        return context_payload, answer


def create_profiled_retrieval_function(provider, doc_id: str):
    """Create a profiled retrieval function for a specific document"""
    profiler = ProfiledRetrieval(provider, doc_id)
    
    def retrieval_func(question: str, doc_ids: list) -> tuple:
        """Retrieve chunks and generate answer with profiling"""
        if not doc_ids:
            raise ValueError("doc_ids must be provided")
        
        # Use the profiled retrieval
        retrieved_chunks, generated_answer = profiler.retrieve(question)
        
        return retrieved_chunks, generated_answer
    
    return retrieval_func, profiler


def main():
    parser = argparse.ArgumentParser(description="Profile RAG evaluation with 5 test cases")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR / "evaluation" / "profile",
        help="Output directory for profiling results"
    )
    parser.add_argument(
        "--similarity-model",
        type=str,
        default="all-MiniLM-L6-v2",
        help="Sentence transformer model for similarity"
    )
    args = parser.parse_args()
    
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print("="*70)
    print("RAG EVALUATION PROFILING")
    print("="*70)
    print("Running evaluation on 5 test cases with detailed timing")
    print(f"Output directory: {output_dir}")
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
        return 1
    
    print(f"✓ Found {len(indexed_docs)} indexed documents")
    print()
    
    # Initialize provider
    print("Initializing LLM provider...")
    try:
        provider = QwenProvider()
        print("✓ LLM provider initialized")
    except Exception as e:
        print(f"ERROR: Could not initialize LLM provider: {e}")
        return 1
    
    # Initialize evaluator
    print("Initializing evaluator...")
    try:
        evaluator = RAGEvaluator(
            similarity_model=args.similarity_model,
            device="cpu",
        )
        print("✓ Evaluator initialized")
    except ImportError as e:
        print(f"ERROR: {e}")
        print("Install with: pip install sentence-transformers")
        return 1
    
    # Generate 5 test cases (1 per document, but limit to 5)
    print("\n" + "="*70)
    print("STEP 1: GENERATING 5 TEST CASES")
    print("="*70)
    test_docs = indexed_docs[:5]  # Use first 5 documents
    test_cases = evaluator.generate_test_cases(
        provider=provider,
        doc_ids=test_docs,
        num_cases=5,
        one_per_doc=True,
    )
    
    if not test_cases:
        print("ERROR: No test cases generated!")
        return 1
    
    print(f"✓ Generated {len(test_cases)} test cases")
    print()
    
    # Run profiled evaluation
    print("="*70)
    print("STEP 2: RUNNING PROFILED EVALUATION")
    print("="*70)
    
    all_query_timings: List[QueryTiming] = []
    results = []
    
    for i, test_case in enumerate(test_cases):
        print(f"\n[{i+1}/{len(test_cases)}] Evaluating: {test_case.generated_question[:60]}...")
        print(f"  Document: {test_case.doc_id}")
        
        # Create profiled retrieval function
        retrieval_func, profiler = create_profiled_retrieval_function(
            provider, test_case.doc_id
        )
        
        # Evaluate single test case
        start_time = time.time()
        result = evaluator.evaluate_single(test_case, retrieval_func)
        end_time = time.time()
        
        # Get timing from profiler
        total_time_ms = (end_time - start_time) * 1000
        
        query_timing = QueryTiming(
            question=test_case.generated_question,
            doc_id=test_case.doc_id,
            timings=profiler.timings,
            total_time_ms=total_time_ms,
        )
        all_query_timings.append(query_timing)
        results.append(result)
        
        # Print timing summary for this query
        print(f"  Total time: {total_time_ms:.2f}ms")
        print("  Process breakdown:")
        for timing in profiler.timings:
            pct = (timing.duration_ms / total_time_ms * 100) if total_time_ms > 0 else 0
            print(f"    {timing.process_name}: {timing.duration_ms:.2f}ms ({pct:.1f}%)")
    
    # Calculate summary statistics
    print("\n" + "="*70)
    print("STEP 3: TIMING ANALYSIS")
    print("="*70)
    
    # Aggregate timings by process
    process_totals: Dict[str, List[float]] = {}
    for query_timing in all_query_timings:
        for timing in query_timing.timings:
            if timing.process_name not in process_totals:
                process_totals[timing.process_name] = []
            process_totals[timing.process_name].append(timing.duration_ms)
    
    # Calculate averages
    process_averages = {
        name: sum(times) / len(times)
        for name, times in process_totals.items()
    }
    
    # Sort by average time (descending)
    sorted_processes = sorted(
        process_averages.items(),
        key=lambda x: x[1],
        reverse=True
    )
    
    total_avg = sum(query_timing.total_time_ms for query_timing in all_query_timings) / len(all_query_timings)
    
    print(f"\nAverage total time per query: {total_avg:.2f}ms")
    print("\nProcess timing breakdown (sorted by average time):")
    print("-" * 70)
    print(f"{'Process':<30} {'Avg Time (ms)':<15} {'% of Total':<15} {'Calls':<10}")
    print("-" * 70)
    
    for process_name, avg_time in sorted_processes:
        pct = (avg_time / total_avg * 100) if total_avg > 0 else 0
        call_count = len(process_totals[process_name])
        print(f"{process_name:<30} {avg_time:>12.2f}ms {pct:>13.1f}% {call_count:>10}")
    
    # Identify bottleneck
    if sorted_processes:
        bottleneck_name, bottleneck_time = sorted_processes[0]
        bottleneck_pct = (bottleneck_time / total_avg * 100) if total_avg > 0 else 0
        print("\n" + "="*70)
        print(f"🔴 BOTTLENECK IDENTIFIED: {bottleneck_name}")
        print(f"   Average time: {bottleneck_time:.2f}ms ({bottleneck_pct:.1f}% of total)")
        print("="*70)
    
    # Save detailed results
    print("\n" + "="*70)
    print("STEP 4: SAVING RESULTS")
    print("="*70)
    
    # Save timing data
    timing_data = {
        "summary": {
            "total_queries": len(all_query_timings),
            "average_total_time_ms": total_avg,
            "process_averages": process_averages,
            "bottleneck": {
                "process": sorted_processes[0][0] if sorted_processes else None,
                "avg_time_ms": sorted_processes[0][1] if sorted_processes else 0,
                "percentage": (sorted_processes[0][1] / total_avg * 100) if sorted_processes and total_avg > 0 else 0,
            }
        },
        "query_timings": [qt.to_dict() for qt in all_query_timings],
    }
    
    timing_file = output_dir / "profiling_timings.json"
    with open(timing_file, 'w', encoding='utf-8') as f:
        json.dump(timing_data, f, indent=2, ensure_ascii=False)
    
    print(f"✓ Saved timing data to: {timing_file}")
    
    # Save evaluation results
    from gdd_rag_backbone.rag_backend.evaluator import EvaluationSummary
    summary = evaluator._calculate_summary(results, sum(qt.total_time_ms / 1000 for qt in all_query_timings))
    
    results_file = output_dir / "profiling_results.json"
    results_data = {
        "test_cases": [asdict(tc) for tc in test_cases],
        "results": [asdict(r) for r in results],
        "summary": asdict(summary),
    }
    
    with open(results_file, 'w', encoding='utf-8') as f:
        json.dump(results_data, f, indent=2, ensure_ascii=False)
    
    print(f"✓ Saved evaluation results to: {results_file}")
    
    print("\n" + "="*70)
    print("PROFILING COMPLETE")
    print("="*70)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

