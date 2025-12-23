"""
RAG Evaluation System for measuring retrieval and answer accuracy.

This module provides:
1. Test case generation from documents (reverse QA: chunk → question)
2. Similarity scoring between expected and generated answers
3. Batch evaluation on 100+ test cases
4. Detailed metrics and reporting
"""

import json
import random
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Dict, Tuple, Optional, Callable
import time

try:
    from sentence_transformers import SentenceTransformer, util
    SIMILARITY_AVAILABLE = True
except ImportError:
    SIMILARITY_AVAILABLE = False
    print("Warning: sentence-transformers not installed. Install with: pip install sentence-transformers")


@dataclass
class TestCase:
    """A single test case for evaluation"""
    test_id: int
    doc_id: str
    chunk_id: str
    source_chunk: str  # The original chunk content (ground truth answer)
    generated_question: str  # Question generated from the chunk
    expected_answer: str  # Expected answer (derived from source chunk)
    

@dataclass
class EvaluationResult:
    """Result of evaluating a single test case"""
    test_id: int
    question: str
    expected_answer: str
    generated_answer: str
    retrieved_chunks: List[Dict]
    # Similarity scores
    answer_similarity: float  # Semantic similarity between expected and generated answer
    retrieval_rank: Optional[int]  # Rank of the correct chunk in retrieved results (1-based, None if not found)
    top_chunk_similarity: float  # Similarity between expected answer and top retrieved chunk
    # Metadata
    doc_id: str
    chunk_id: str
    retrieval_time: float
    generation_time: float


@dataclass
class EvaluationSummary:
    """Summary statistics from batch evaluation"""
    total_cases: int
    evaluated: int
    failed: int
    # Average scores
    average_answer_similarity: float
    average_top_chunk_similarity: float
    average_retrieval_rank: Optional[float]  # None if no correct chunks found
    # Percentiles
    p50_answer_similarity: float
    p75_answer_similarity: float
    p90_answer_similarity: float
    # Success rates
    retrieval_success_rate: float  # % of cases where correct chunk in top 5
    high_similarity_rate: float  # % of cases with similarity > 0.7
    # Timing
    average_retrieval_time: float
    average_generation_time: float
    total_time: float


class RAGEvaluator:
    """
    Evaluator for RAG systems that:
    1. Generates test cases from documents (chunk → question)
    2. Evaluates retrieval accuracy
    3. Evaluates answer generation quality using semantic similarity
    """
    
    def __init__(
        self,
        similarity_model: str = "all-MiniLM-L6-v2",
        device: str = "cpu",
    ):
        """
        Initialize evaluator.
        
        Args:
            similarity_model: Sentence transformer model for similarity
            device: Device to run model on ('cpu' or 'cuda')
        """
        if not SIMILARITY_AVAILABLE:
            raise ImportError(
                "sentence-transformers is required. Install with: pip install sentence-transformers"
            )
        
        print(f"Loading similarity model: {similarity_model}...")
        self.similarity_model = SentenceTransformer(similarity_model, device=device)
        print("✓ Similarity model loaded")
    
    def calculate_similarity(
        self,
        text1: str,
        text2: str,
    ) -> float:
        """
        Calculate semantic similarity between two texts using cosine similarity.
        
        How it works:
        1. Both texts are embedded into dense vectors using sentence transformers
        2. Cosine similarity is computed between the embeddings
        3. Returns a score between -1 and 1 (typically 0-1 for text)
        
        Interpretation:
        - 0.9-1.0: Very similar/identical meaning
        - 0.7-0.9: Similar meaning, some differences
        - 0.5-0.7: Somewhat related
        - 0.3-0.5: Weakly related
        - 0.0-0.3: Unrelated
        """
        if not text1 or not text2:
            return 0.0
        
        embeddings = self.similarity_model.encode([text1, text2], convert_to_tensor=True)
        similarity = util.cos_sim(embeddings[0], embeddings[1]).item()
        return float(similarity)
    
    def generate_question_from_chunk(
        self,
        provider,
        chunk_content: str,
        doc_context: Optional[str] = None,
    ) -> str:
        """
        Generate a question that should retrieve this chunk.
        Uses reverse QA: given an answer (chunk), generate a question.
        """
        # Truncate chunk if too long
        chunk_preview = chunk_content[:800] + "..." if len(chunk_content) > 800 else chunk_content
        
        prompt = f"""Given the following information from a Game Design Document, generate a clear, specific question that someone might ask to retrieve this information.

Information:
{chunk_preview}

Generate a question that would naturally lead to this information being retrieved and answered. The question should be:
- Specific and clear
- Natural (how a person would ask it)
- Focused on the key information in the text
- Not too generic or vague

Question:"""
        
        try:
            question = provider.llm(prompt=prompt, max_tokens=100)
            return question.strip().strip('"').strip("'")
        except Exception as e:
            print(f"Error generating question: {e}")
            # Fallback: create a simple question
            first_sentence = chunk_content.split('.')[0] if '.' in chunk_content else chunk_content[:100]
            return f"What is {first_sentence[:50]}?"
    
    def extract_answer_from_chunk(
        self,
        chunk_content: str,
    ) -> str:
        """
        Extract a concise answer from chunk content.
        This becomes the 'expected answer' for evaluation.
        """
        # Take first 2-3 sentences as the answer
        sentences = chunk_content.split('. ')
        if len(sentences) >= 3:
            answer = '. '.join(sentences[:3]) + '.'
        elif len(sentences) >= 2:
            answer = '. '.join(sentences[:2]) + '.'
        else:
            answer = chunk_content[:300]  # Fallback to first 300 chars
        
        return answer.strip()
    
    def validate_question(self, question: str) -> Dict[str, any]:
        """
        Validate if question is specific enough for RAG retrieval.
        
        Checks:
        - Has specific entity/system name (e.g., "Tank", "Garage", "Artifact")
        - Asks for measurable/concrete information
        - Not too generic (e.g., "What is this about?")
        - Has sufficient length and structure
        
        Returns:
            Dictionary with validation results:
            - has_entity: bool - Contains game-specific terms
            - is_specific: bool - Not overly generic
            - is_measurable: bool - Asks for concrete information
            - has_structure: bool - Well-formed question
            - validation_score: float (0-1) - Overall quality score
            - issues: List[str] - Any problems found
        """
        issues = []
        
        # Check length
        if len(question) < 10:
            issues.append("Question too short (< 10 characters)")
        if len(question) > 500:
            issues.append("Question too long (> 500 characters)")
        
        # Check for question marks or keywords
        has_structure = (
            '?' in question or
            any(q in question.lower() for q in ['what', 'how', 'why', 'when', 'where', 'which', 'who', 'describe', 'explain'])
        )
        if not has_structure:
            issues.append("Missing question structure (no '?' or question words)")
        
        # Check for game-specific entities/systems
        game_entities = [
            'tank', 'garage', 'artifact', 'skill', 'damage', 'hp', 'health',
            'map', 'mode', 'match', 'player', 'enemy', 'weapon', 'armor',
            'outpost', 'base', 'team', 'multiplayer', 'character', 'upgrade',
            'level', 'experience', 'ui', 'gui', 'screen', 'menu', 'button',
            'element', 'fire', 'water', 'earth', 'wind', 'stat', 'attribute'
        ]
        question_lower = question.lower()
        has_entity = any(entity in question_lower for entity in game_entities)
        
        if not has_entity:
            issues.append("No specific game entities/systems mentioned")
        
        # Check if too generic
        generic_questions = [
            'what is this',
            'tell me about',
            'what does this do',
            'explain this',
            'what is it',
            'describe this document',
            'what is in',
        ]
        is_specific = not any(generic in question_lower for generic in generic_questions)
        
        if not is_specific:
            issues.append("Question too generic - needs specific entity or system")
        
        # Check for measurable/concrete information requests
        measurable_keywords = [
            'how much', 'how many', 'what value', 'what number', 'how long',
            'damage', 'hp', 'health', 'speed', 'range', 'cooldown', 'cost',
            'price', 'time', 'duration', 'size', 'level', 'tier', 'rank',
            'stat', 'attribute', 'bonus', 'penalty', 'effect', 'requirement'
        ]
        is_measurable = any(keyword in question_lower for keyword in measurable_keywords)
        
        # Calculate validation score
        score = 0.0
        if has_structure:
            score += 0.25
        if has_entity:
            score += 0.35
        if is_specific:
            score += 0.25
        if is_measurable:
            score += 0.15
        
        # Bonus for good length
        if 20 <= len(question) <= 200:
            score += 0.1
        
        # Cap at 1.0
        score = min(1.0, score)
        
        return {
            "has_entity": has_entity,
            "is_specific": is_specific,
            "is_measurable": is_measurable,
            "has_structure": has_structure,
            "validation_score": score,
            "issues": issues,
        }
    
    def generate_test_cases(
        self,
        provider,
        doc_ids: List[str],
        num_cases: int = 100,
        chunks_per_doc: Optional[int] = None,
        one_per_doc: bool = False,
    ) -> List[TestCase]:
        """
        Generate test cases by:
        1. Loading chunks from documents
        2. For each chunk, generating a question
        3. Extracting expected answer from chunk
        
        Args:
            provider: LLM provider for question generation
            doc_ids: List of document IDs to sample from
            num_cases: Number of test cases to generate (ignored if one_per_doc=True)
            chunks_per_doc: Max chunks to sample per document (None = all)
            one_per_doc: If True, generate exactly 1 test case per document
        """
        from gdd_rag_backbone.rag_backend.chunk_qa import load_doc_chunks
        
        if one_per_doc:
            print(f"Generating 1 test case per document from {len(doc_ids)} documents...")
            
            # Collect exactly one chunk per document
            all_chunks = []
            for doc_id in doc_ids:
                chunks = load_doc_chunks(doc_id)
                if chunks:
                    # Filter out very short chunks
                    valid_chunks = [chunk for chunk in chunks if len(chunk.content.strip()) > 50]
                    if valid_chunks:
                        # Sample exactly 1 chunk per document
                        selected_chunk = random.sample(valid_chunks, 1)[0]
                        all_chunks.append((doc_id, selected_chunk))
            
            if not all_chunks:
                print("ERROR: No valid chunks found in any document!")
                return []
            
            print(f"Found {len(all_chunks)} documents with valid chunks")
            sampled = all_chunks
            num_cases = len(all_chunks)
        else:
            print(f"Generating {num_cases} test cases from {len(doc_ids)} documents...")
            
            # Collect all chunks
            all_chunks = []
            for doc_id in doc_ids:
                chunks = load_doc_chunks(doc_id)
                if chunks_per_doc:
                    chunks = random.sample(chunks, min(chunks_per_doc, len(chunks)))
                for chunk in chunks:
                    if len(chunk.content.strip()) > 50:  # Skip very short chunks
                        all_chunks.append((doc_id, chunk))
            
            if len(all_chunks) < num_cases:
                print(f"Warning: Only {len(all_chunks)} chunks available, generating {len(all_chunks)} test cases")
                num_cases = len(all_chunks)
            
            # Sample chunks
            sampled = random.sample(all_chunks, num_cases)
        
        test_cases = []
        for i, (doc_id, chunk) in enumerate(sampled):
            print(f"Generating test case {i+1}/{num_cases}...", end='\r')
            
            # Generate question from chunk
            question = self.generate_question_from_chunk(provider, chunk.content)
            
            # Extract expected answer
            expected_answer = self.extract_answer_from_chunk(chunk.content)
            
            test_case = TestCase(
                test_id=i + 1,
                doc_id=doc_id,
                chunk_id=chunk.chunk_id,
                source_chunk=chunk.content,
                generated_question=question,
                expected_answer=expected_answer,
            )
            test_cases.append(test_case)
        
        if one_per_doc:
            print(f"\n✓ Generated {len(test_cases)} test cases (1 per document)")
        else:
            print(f"\n✓ Generated {len(test_cases)} test cases")
        return test_cases
    
    def evaluate_single(
        self,
        test_case: TestCase,
        retrieval_func: Callable[[str, List[str]], Tuple[List[Dict], str]],
    ) -> EvaluationResult:
        """
        Evaluate a single test case.
        
        Args:
            test_case: The test case to evaluate
            retrieval_func: Function(question, doc_ids) -> (retrieved_chunks, generated_answer)
        """
        start_time = time.time()
        
        # Run retrieval and generation
        try:
            retrieved_chunks, generated_answer = retrieval_func(
                test_case.generated_question,
                [test_case.doc_id]
            )
        except Exception as e:
            print(f"Error evaluating test case {test_case.test_id}: {e}")
            return EvaluationResult(
                test_id=test_case.test_id,
                question=test_case.generated_question,
                expected_answer=test_case.expected_answer,
                generated_answer=f"Error: {str(e)}",
                retrieved_chunks=[],
                answer_similarity=0.0,
                retrieval_rank=None,
                top_chunk_similarity=0.0,
                doc_id=test_case.doc_id,
                chunk_id=test_case.chunk_id,
                retrieval_time=0.0,
                generation_time=0.0,
            )
        
        retrieval_time = time.time() - start_time
        
        # Calculate similarities
        answer_similarity = self.calculate_similarity(
            test_case.expected_answer,
            generated_answer,
        )
        
        # Find rank of correct chunk
        retrieval_rank = None
        for i, chunk in enumerate(retrieved_chunks[:10]):  # Check top 10
            if chunk.get("chunk_id") == test_case.chunk_id:
                retrieval_rank = i + 1  # 1-based
                break
        
        # Similarity between expected answer and top retrieved chunk
        top_chunk_similarity = 0.0
        if retrieved_chunks:
            top_chunk_content = retrieved_chunks[0].get("content", "")
            top_chunk_similarity = self.calculate_similarity(
                test_case.expected_answer,
                top_chunk_content[:500],  # Compare with first 500 chars
            )
        
        return EvaluationResult(
            test_id=test_case.test_id,
            question=test_case.generated_question,
            expected_answer=test_case.expected_answer,
            generated_answer=generated_answer,
            retrieved_chunks=retrieved_chunks,
            answer_similarity=answer_similarity,
            retrieval_rank=retrieval_rank,
            top_chunk_similarity=top_chunk_similarity,
            doc_id=test_case.doc_id,
            chunk_id=test_case.chunk_id,
            retrieval_time=retrieval_time,
            generation_time=0.0,  # Could be separated if needed
        )
    
    def evaluate_batch(
        self,
        test_cases: List[TestCase],
        retrieval_func: Callable[[str, List[str]], Tuple[List[Dict], str]],
    ) -> Tuple[List[EvaluationResult], EvaluationSummary]:
        """
        Evaluate a batch of test cases.
        
        Returns:
            (results, summary)
        """
        print(f"\nEvaluating {len(test_cases)} test cases...")
        start_time = time.time()
        
        results = []
        for i, test_case in enumerate(test_cases):
            print(f"Evaluating {i+1}/{len(test_cases)}: {test_case.generated_question[:60]}...", end='\r')
            result = self.evaluate_single(test_case, retrieval_func)
            results.append(result)
        
        total_time = time.time() - start_time
        print(f"\n✓ Evaluation complete in {total_time:.1f}s")
        
        # Calculate summary
        summary = self._calculate_summary(results, total_time)
        
        return results, summary
    
    def _calculate_summary(
        self,
        results: List[EvaluationResult],
        total_time: float,
    ) -> EvaluationSummary:
        """Calculate summary statistics"""
        if not results:
            return EvaluationSummary(
                total_cases=0,
                evaluated=0,
                failed=0,
                average_answer_similarity=0.0,
                average_top_chunk_similarity=0.0,
                average_retrieval_rank=None,
                p50_answer_similarity=0.0,
                p75_answer_similarity=0.0,
                p90_answer_similarity=0.0,
                retrieval_success_rate=0.0,
                high_similarity_rate=0.0,
                average_retrieval_time=0.0,
                average_generation_time=0.0,
                total_time=total_time,
            )
        
        # Filter out errors
        valid_results = [r for r in results if r.answer_similarity >= 0]
        
        answer_similarities = [r.answer_similarity for r in valid_results]
        top_chunk_similarities = [r.top_chunk_similarity for r in valid_results]
        retrieval_ranks = [r.retrieval_rank for r in valid_results if r.retrieval_rank is not None]
        retrieval_times = [r.retrieval_time for r in valid_results]
        
        # Calculate averages
        avg_answer_sim = sum(answer_similarities) / len(answer_similarities) if answer_similarities else 0.0
        avg_top_chunk_sim = sum(top_chunk_similarities) / len(top_chunk_similarities) if top_chunk_similarities else 0.0
        avg_retrieval_rank = sum(retrieval_ranks) / len(retrieval_ranks) if retrieval_ranks else None
        avg_retrieval_time = sum(retrieval_times) / len(retrieval_times) if retrieval_times else 0.0
        
        # Percentiles
        sorted_sims = sorted(answer_similarities, reverse=True)
        p50 = sorted_sims[len(sorted_sims) // 2] if sorted_sims else 0.0
        p75 = sorted_sims[int(len(sorted_sims) * 0.75)] if sorted_sims else 0.0
        p90 = sorted_sims[int(len(sorted_sims) * 0.90)] if sorted_sims else 0.0
        
        # Success rates
        retrieval_success = sum(1 for r in valid_results if r.retrieval_rank is not None and r.retrieval_rank <= 5)
        retrieval_success_rate = retrieval_success / len(valid_results) if valid_results else 0.0
        
        high_similarity = sum(1 for s in answer_similarities if s >= 0.7)
        high_similarity_rate = high_similarity / len(answer_similarities) if answer_similarities else 0.0
        
        return EvaluationSummary(
            total_cases=len(results),
            evaluated=len(valid_results),
            failed=len(results) - len(valid_results),
            average_answer_similarity=avg_answer_sim,
            average_top_chunk_similarity=avg_top_chunk_sim,
            average_retrieval_rank=avg_retrieval_rank,
            p50_answer_similarity=p50,
            p75_answer_similarity=p75,
            p90_answer_similarity=p90,
            retrieval_success_rate=retrieval_success_rate,
            high_similarity_rate=high_similarity_rate,
            average_retrieval_time=avg_retrieval_time,
            average_generation_time=0.0,
            total_time=total_time,
        )
    
    def save_results(
        self,
        test_cases: List[TestCase],
        results: List[EvaluationResult],
        summary: EvaluationSummary,
        output_dir: Path,
    ):
        """Save evaluation results to JSON files"""
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Save test cases
        test_cases_path = output_dir / "test_cases.json"
        test_cases_data = [asdict(tc) for tc in test_cases]
        test_cases_path.write_text(
            json.dumps(test_cases_data, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
        
        # Save results
        results_path = output_dir / "evaluation_results.json"
        results_data = [asdict(r) for r in results]
        results_path.write_text(
            json.dumps(results_data, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
        
        # Save summary
        summary_path = output_dir / "evaluation_summary.json"
        summary_data = asdict(summary)
        summary_path.write_text(
            json.dumps(summary_data, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
        
        print(f"\n✓ Results saved to {output_dir}")
        print(f"  - Test cases: {test_cases_path}")
        print(f"  - Results: {results_path}")
        print(f"  - Summary: {summary_path}")
    
    def print_summary(self, summary: EvaluationSummary):
        """Print evaluation summary in a readable format"""
        print("\n" + "="*70)
        print("EVALUATION SUMMARY")
        print("="*70)
        print(f"Total test cases: {summary.total_cases}")
        print(f"Successfully evaluated: {summary.evaluated}")
        print(f"Failed: {summary.failed}")
        print()
        print("ANSWER SIMILARITY (Expected vs Generated Answer):")
        print(f"  Average: {summary.average_answer_similarity:.3f}")
        print(f"  Median (P50): {summary.p50_answer_similarity:.3f}")
        print(f"  P75: {summary.p75_answer_similarity:.3f}")
        print(f"  P90: {summary.p90_answer_similarity:.3f}")
        print(f"  High similarity (>0.7): {summary.high_similarity_rate*100:.1f}%")
        print()
        print("RETRIEVAL ACCURACY:")
        print(f"  Average top chunk similarity: {summary.average_top_chunk_similarity:.3f}")
        if summary.average_retrieval_rank:
            print(f"  Average rank of correct chunk: {summary.average_retrieval_rank:.1f}")
        print(f"  Success rate (correct chunk in top 5): {summary.retrieval_success_rate*100:.1f}%")
        print()
        print("PERFORMANCE:")
        print(f"  Average retrieval time: {summary.average_retrieval_time:.2f}s")
        print(f"  Total evaluation time: {summary.total_time:.1f}s")
        print("="*70)




