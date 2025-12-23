"""
Evaluator script for markdown chunks.

Tests retrieval and answer quality with 3 questions per markdown document.
Calculates similarity scores between expected and generated answers.
"""

import argparse
import json
import re
import time
from pathlib import Path
from typing import List, Dict, Tuple
from dataclasses import dataclass, asdict

try:
    from sentence_transformers import SentenceTransformer, util
    SIMILARITY_AVAILABLE = True
except ImportError:
    SIMILARITY_AVAILABLE = False
    print("Warning: sentence-transformers not installed. Install with: pip install sentence-transformers")

from gdd_rag_backbone.llm_providers import QwenProvider
from gdd_rag_backbone.rag_backend.markdown_chunk_qa import get_markdown_top_chunks, list_markdown_indexed_docs
from gdd_rag_backbone.config import PROJECT_ROOT

MARKDOWN_CHUNKS_DIR = PROJECT_ROOT / "rag_storage_md"


@dataclass
class QuestionAnswer:
    """A question-answer pair for evaluation"""
    doc_id: str
    question: str
    expected_answer: str  # Ground truth answer or key information


@dataclass
class EvaluationResult:
    """Result for a single question"""
    doc_id: str
    question: str
    expected_answer: str
    generated_answer: str
    retrieved_chunks: List[Dict]
    answer_similarity: float
    top_chunk_similarity: float
    llm_grade: float  # LLM-as-judge score in [0, 1]
    retrieval_time: float
    generation_time: float


@dataclass
class DocumentEvaluation:
    """Evaluation results for a single document"""
    doc_id: str
    questions: List[EvaluationResult]
    average_similarity: float
    average_top_chunk_similarity: float
    average_llm_grade: float


def _score_chunk_for_question(chunk: Dict) -> int:
    """
    Heuristic score for how good a chunk is for question generation.
    
    Higher score = more suitable (headers, tables, flows, etc.).
    """
    text = chunk.get("content", "")
    score = 0
    stripped = text.lstrip()
    # Prefer sections with headers
    if stripped.startswith("##"):
        score += 3
    # Prefer chunks with tables
    if "|" in text:
        score += 2
    # Prefer chunks that mention flows/user flows
    lowered = text.lower()
    if "userflow" in lowered or "flow" in lowered:
        score += 1
    return score


def _select_chunks_for_answer(chunks: List[Dict]) -> List[Dict]:
    """
    Heuristic to decide how many top chunks to feed into the answer prompt.

    Intuition:
    - If the top chunk score is clearly dominant and high, use only that chunk
      (avoids over-explaining with extra context).
    - If several chunks are similarly strong, include the top 2–3.
    - If all scores are mediocre, include more chunks (up to 5) to give
      the model enough context.
    """
    if not chunks:
        return []

    # Ensure scores are numeric
    scores = [float(c.get("score", 0.0) or 0.0) for c in chunks]
    s1 = scores[0]
    s2 = scores[1] if len(scores) > 1 else 0.0
    s3 = scores[2] if len(scores) > 2 else 0.0

    # Case A: very strong, clearly dominant top chunk → just top 1
    if s1 >= 0.6 and (s1 - s2) >= 0.15:
        n = 1
    # Case B: strong top chunk with close second → top 2
    elif s1 >= 0.6 and s2 >= s1 - 0.15:
        n = min(2, len(chunks))
    # Case C: moderately strong but not dominant → top 3
    elif s1 >= 0.5:
        n = min(3, len(chunks))
    # Case D: weak/flat scores → fall back to more context (up to 5)
    else:
        n = min(5, len(chunks))

    return chunks[:n]


def generate_test_cases_from_docs(
    provider: QwenProvider,
    markdown_docs: List[Dict],
    max_questions: int = 100,
    questions_per_doc: int = 2,
) -> Dict[str, List[Dict[str, object]]]:
    """
    Generate evaluation questions automatically from markdown chunks.
    
    For each document:
      - Select informative chunks (headers, tables, flows, etc.)
      - Ask the LLM to generate ONE specific question per chunk
      - Use the chunk content as the expected answer
    
    Questions are prefixed with "In <doc_id>, ..." as requested.
    """
    questions_by_doc: Dict[str, List[Dict[str, object]]] = {
        doc["doc_id"]: [] for doc in markdown_docs
    }
    if not markdown_docs or max_questions <= 0:
        return questions_by_doc
    
    total_docs = len(markdown_docs)
    # Target: up to `questions_per_doc` per document, capped by max_questions overall
    remaining = min(max_questions, questions_per_doc * total_docs)
    
    print("\nGenerating test questions from markdown documents...")
    
    for doc in markdown_docs:
        doc_id = doc["doc_id"]
        chunks = load_document_chunks(doc_id)
        if not chunks:
            print(f"  [WARNING] No chunks found for {doc_id}, skipping question generation")
            continue
        
        # Filter chunks by length to avoid extremely short/long ones
        candidate_chunks = [
            ch for ch in chunks
            if 80 <= len(ch.get("content", "")) <= 1200
        ]
        if not candidate_chunks:
            candidate_chunks = chunks
        
        # Sort by heuristic score (best first)
        candidate_chunks.sort(key=_score_chunk_for_question, reverse=True)
        
        target_for_doc = min(questions_per_doc, remaining)
        generated_for_doc = 0
        
        for chunk in candidate_chunks:
            if generated_for_doc >= target_for_doc or remaining <= 0:
                break
            
            chunk_text = chunk.get("content", "").strip()
            if not chunk_text:
                continue
            
            # Build question-generation prompt
            q_prompt = f"""You are creating evaluation questions for a game design document.

Document ID: {doc_id}

Text:
\"\"\"{chunk_text}\"\"\"

Write ONE specific, concrete question that can be answered directly from this text.

Requirements:
- The question MUST start with: \"In {doc_id}, \".
- It must be precise and refer to concrete details (numbers, names, conditions, steps, lists, rules, etc.).
- It should be answerable using ONLY the given text.
- Do NOT include the answer.
- Output ONLY the question."""
            try:
                raw_question = provider.llm(q_prompt).strip()
            except KeyboardInterrupt:
                raise
            except Exception as e:
                print(f"  [WARNING] Question generation error for {doc_id}: {e}")
                continue
            
            # Normalize question text (ensure prefix and single line)
            question = raw_question.replace("\n", " ").strip()
            if not question.lower().startswith(f"in {doc_id.lower()},"):
                # Prepend prefix if model didn't follow instruction
                question = f"In {doc_id}, {question}"
            
            qa = {
                "question": question,
                "expected_answer": chunk_text,
                "answer_style": "concise",
            }
            questions_by_doc[doc_id].append(qa)
            generated_for_doc += 1
            remaining -= 1
        
        print(f"  - {doc_id}: generated {generated_for_doc} question(s)")
        if remaining <= 0:
            break
    
    total_generated = sum(len(v) for v in questions_by_doc.values())
    print(f"\nGenerated {total_generated} questions across {len(markdown_docs)} documents")
    return questions_by_doc


def load_document_chunks(doc_id: str) -> List[Dict]:
    """Load chunks for a document."""
    chunks_file = MARKDOWN_CHUNKS_DIR / doc_id / f"{doc_id}_chunks.json"
    if not chunks_file.exists():
        return []
    
    try:
        with open(chunks_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return []


def generate_expected_answer_from_chunks(question: str, chunks: List[Dict]) -> str:
    """
    Generate expected answer by finding relevant chunks.
    This is a simple approach - in practice, you might want more sophisticated matching.
    """
    # For now, return a placeholder - you can enhance this to extract from chunks
    return "Answer should be derived from the document chunks."


class MarkdownEvaluator:
    """Evaluator for markdown document chunks."""
    
    def __init__(self, similarity_model: str = "all-MiniLM-L6-v2"):
        """Initialize evaluator with similarity model."""
        if not SIMILARITY_AVAILABLE:
            raise ImportError("sentence-transformers required. Install with: pip install sentence-transformers")
        
        print(f"Loading similarity model: {similarity_model}...")
        self.similarity_model = SentenceTransformer(similarity_model)
        print("[OK] Similarity model loaded")
    
    def calculate_similarity(self, text1: str, text2: str) -> float:
        """Calculate semantic similarity between two texts."""
        if not text1 or not text2:
            return 0.0

        def _normalize_for_similarity(text: str) -> str:
            # Remove markdown table artifacts and collapse whitespace.
            cleaned = re.sub(r"[|#`*_]+", " ", text)
            cleaned = re.sub(r"\s+", " ", cleaned).strip()
            return cleaned

        t1 = _normalize_for_similarity(text1)
        t2 = _normalize_for_similarity(text2)
        if not t1 or not t2:
            return 0.0

        embeddings = self.similarity_model.encode([t1, t2], convert_to_tensor=True)
        similarity = util.cos_sim(embeddings[0], embeddings[1]).item()
        return float(similarity)
    
    def grade_with_llm(
        self,
        provider: QwenProvider,
        question: str,
        expected_answer: str,
        generated_answer: str,
    ) -> float:
        """
        Use an LLM as a grader to score the generated answer in [0, 1].

        The grader sees the question, a reference answer (from the document),
        and the model's answer, and returns a single float score.
        """
        try:
            grade_prompt = f"""You are evaluating an answer for a game design document QA task.

Question:
\"\"\"{question}\"\"\"

Reference answer (from the document - may contain extra context):
\"\"\"{expected_answer}\"\"\"

Model answer to grade:
\"\"\"{generated_answer}\"\"\"

Instructions:
- Score how well the model answer matches the important facts in the reference answer.
- Ignore formatting differences and extra unimportant filler in the reference.
- Penalize hallucinations (facts not supported by the reference).
- Use a numeric score between 0.0 and 1.0:
  - 1.0 = fully correct and faithful
  - 0.7 = mostly correct but missing minor details
  - 0.4 = partially correct / incomplete
  - 0.1 = mostly incorrect or hallucinated
  - 0.0 = completely wrong or unrelated

Output:
- Respond with ONLY the numeric score as a decimal between 0.0 and 1.0.
- Do not add any explanation or extra text."""
            raw = provider.llm(grade_prompt).strip()
        except KeyboardInterrupt:
            raise
        except Exception:
            return 0.0

        # Extract first float-like number between 0 and 1 from the response
        match = re.search(r"([01](?:\.\d+)?)", raw)
        if not match:
            return 0.0
        try:
            score = float(match.group(1))
        except ValueError:
            return 0.0
        # Clamp to [0, 1]
        return max(0.0, min(1.0, score))

    def evaluate_question(
        self,
        doc_id: str,
        question: str,
        expected_answer: str,
        provider: QwenProvider,
        answer_style: str = "auto"
    ) -> EvaluationResult:
        """Evaluate a single question."""
        # Retrieve chunks
        retrieval_start = time.time()
        try:
            chunks = get_markdown_top_chunks(
                doc_ids=[doc_id],
                question=question,
                provider=provider,
                top_k=5,
                per_doc_limit=5,
            )
        except Exception as e:
            chunks = []
            print(f"  [WARNING] Retrieval error: {e}")
        
        retrieval_time = time.time() - retrieval_start
        
        # Generate answer from chunks
        generation_start = time.time()
        if chunks:
            selected_chunks = _select_chunks_for_answer(chunks)
            chunk_texts = "\n\n".join(
                f"[Chunk {i+1}]\n{chunk['content']}"
                for i, chunk in enumerate(selected_chunks)
            )

            # Determine answer style
            if answer_style == "auto":
                # Auto-detect based on expected answer length
                expected_length = len(expected_answer)
                if expected_length < 150:
                    answer_style = "concise"
                elif expected_length < 300:
                    answer_style = "moderate"
                else:
                    answer_style = "detailed"
            
            # Build prompt based on answer style
            # Strongly discourage hallucination and encourage short, grounded answers.
            base_instruction = (
                "Use ONLY information from the chunks below. "
                "If the answer is not clearly stated, say you don't know. "
                "Do NOT invent new facts. "
                "Always answer first in Vietnamese, then provide an English translation."
            )
            if answer_style == "concise":
                prompt = f"""You are a careful assistant answering questions about a game design document.

{base_instruction}

Question:
{question}

Chunks:
{chunk_texts}

Answer format:
Vietnamese:
<answer in Vietnamese>

English:
<answer in English>"""
            elif answer_style == "moderate":
                prompt = f"""You are a careful assistant answering questions about a game design document.

{base_instruction}

Question:
{question}

Chunks:
{chunk_texts}

Answer in 2–4 sentences, including key details that are explicitly stated in the chunks."""
            else:  # detailed
                prompt = f"""You are a careful assistant answering questions about a game design document.

{base_instruction}

Question:
{question}

Chunks:
{chunk_texts}

Provide a clear, comprehensive answer using only information from the chunks."""
            
            try:
                generated_answer = provider.llm(prompt)
            except KeyboardInterrupt:
                raise
            except Exception as e:
                generated_answer = f"Error generating answer: {str(e)}"
                print(f"    [WARNING] Generation error: {e}")
        else:
            generated_answer = "No relevant chunks found."
        
        generation_time = time.time() - generation_start
        
        # For similarity, prefer the Vietnamese part of the generated answer if present
        def _extract_vietnamese(text: str) -> str:
            # Look for a "Vietnamese:" block before "English:"
            match = re.search(
                r"Vietnamese:\s*(.+?)(?:English:|$)",
                text,
                flags=re.IGNORECASE | re.DOTALL,
            )
            if match:
                return match.group(1).strip()
            return text

        generated_answer_vi = _extract_vietnamese(generated_answer)

        # Calculate similarities (embedding-based)
        answer_similarity = self.calculate_similarity(
            expected_answer, generated_answer_vi
        )
        
        # Calculate similarity with top chunk
        top_chunk_similarity = 0.0
        if chunks:
            top_chunk_content = chunks[0].get("content", "")
            top_chunk_similarity = self.calculate_similarity(expected_answer, top_chunk_content)

        # LLM-as-judge grade
        llm_grade = self.grade_with_llm(
            provider=provider,
            question=question,
            expected_answer=expected_answer,
            generated_answer=generated_answer,
        )
        
        return EvaluationResult(
            doc_id=doc_id,
            question=question,
            expected_answer=expected_answer,
            generated_answer=generated_answer,
            retrieved_chunks=[{"chunk_id": c.get("chunk_id"), "score": c.get("score", 0)} for c in chunks],
            answer_similarity=answer_similarity,
            top_chunk_similarity=top_chunk_similarity,
            llm_grade=llm_grade,
            retrieval_time=retrieval_time,
            generation_time=generation_time
        )
    
    def evaluate_document(
        self,
        doc_id: str,
        questions: List[Dict],
        provider: QwenProvider
    ) -> DocumentEvaluation:
        """Evaluate all questions for a document."""
        print(f"\nEvaluating: {doc_id}")
        print(f"  Questions: {len(questions)}")
        
        results = []
        for i, qa in enumerate(questions, 1):
            print(f"  [{i}/{len(questions)}] {qa['question'][:60]}...")
            
            try:
                result = self.evaluate_question(
                    doc_id=doc_id,
                    question=qa['question'],
                    expected_answer=qa['expected_answer'],
                    provider=provider,
                    answer_style=qa.get("answer_style", "auto")
                )
                results.append(result)
                
                print(f"    Answer similarity: {result.answer_similarity:.3f}")
                print(f"    Top chunk similarity: {result.top_chunk_similarity:.3f}")
            except KeyboardInterrupt:
                print("\n[INTERRUPTED] Evaluation interrupted by user")
                raise
            except Exception as e:
                print(f"    [ERROR] Error evaluating question: {e}")
                # Create a failed result
                results.append(EvaluationResult(
                    doc_id=doc_id,
                    question=qa['question'],
                    expected_answer=qa['expected_answer'],
                    generated_answer=f"Error: {str(e)}",
                    retrieved_chunks=[],
                    answer_similarity=0.0,
                    top_chunk_similarity=0.0,
                    retrieval_time=0.0,
                    generation_time=0.0
                ))
        
        avg_sim = sum(r.answer_similarity for r in results) / len(results) if results else 0.0
        avg_top_chunk = sum(r.top_chunk_similarity for r in results) / len(results) if results else 0.0
        avg_llm = sum(r.llm_grade for r in results) / len(results) if results else 0.0
        
        return DocumentEvaluation(
            doc_id=doc_id,
            questions=results,
            average_similarity=avg_sim,
            average_top_chunk_similarity=avg_top_chunk,
            average_llm_grade=avg_llm
        )


def main():
    """Main evaluation function."""
    parser = argparse.ArgumentParser(description="Evaluate markdown chunks with questions")
    parser.add_argument(
        "--doc-id",
        type=str,
        help="Evaluate specific document (if not provided, evaluates all)"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("markdown_evaluation_results.json"),
        help="Output file for results (default: markdown_evaluation_results.json)"
    )
    args = parser.parse_args()
    
    print("=" * 70)
    print("MARKDOWN CHUNKS EVALUATION")
    print("=" * 70)
    
    # Get documents to evaluate
    markdown_docs = list_markdown_indexed_docs()
    if args.doc_id:
        markdown_docs = [doc for doc in markdown_docs if doc["doc_id"] == args.doc_id]
        if not markdown_docs:
            print(f"ERROR: Document '{args.doc_id}' not found")
            return 1
    
    if not markdown_docs:
        print("No markdown documents found to evaluate")
        return 1
    
    print(f"Documents to evaluate: {len(markdown_docs)}")
    for doc in markdown_docs:
        print(f"  - {doc['doc_id']}: {doc.get('chunks_count', 0)} chunks")
    
    # Initialize evaluator
    try:
        evaluator = MarkdownEvaluator()
    except ImportError as e:
        print(f"ERROR: {e}")
        return 1
    
    # Initialize provider
    print("\nInitializing LLM provider...")
    provider = QwenProvider()
    print("✓ Provider ready")
    
    # Generate test questions automatically (2 per document, up to 100 total)
    questions_by_doc = generate_test_cases_from_docs(
        provider=provider,
        markdown_docs=markdown_docs,
        max_questions=100,
        questions_per_doc=2,
    )
    
    # Evaluate each document
    all_results = []
    total_start = time.time()
    
    for doc in markdown_docs:
        doc_id = doc["doc_id"]
        questions = questions_by_doc.get(doc_id, [])
        
        if not questions:
            print(f"\n[WARNING] No questions generated for {doc_id}, skipping...")
            continue
        
        doc_eval = evaluator.evaluate_document(doc_id, questions, provider)
        all_results.append(doc_eval)
    
    total_time = time.time() - total_start
    
    # Calculate overall statistics
    all_question_results = []
    for doc_eval in all_results:
        all_question_results.extend(doc_eval.questions)
    
    if all_question_results:
        overall_avg_sim = sum(r.answer_similarity for r in all_question_results) / len(all_question_results)
        overall_avg_top = sum(r.top_chunk_similarity for r in all_question_results) / len(all_question_results)
        overall_avg_llm = sum(r.llm_grade for r in all_question_results) / len(all_question_results)
        high_sim_count = sum(1 for r in all_question_results if r.answer_similarity >= 0.7)
        high_sim_rate = high_sim_count / len(all_question_results)
    else:
        overall_avg_sim = 0.0
        overall_avg_top = 0.0
        overall_avg_llm = 0.0
        high_sim_rate = 0.0
    
    # Print summary
    print("\n" + "=" * 70)
    print("EVALUATION SUMMARY")
    print("=" * 70)
    print(f"Total documents: {len(all_results)}")
    print(f"Total questions: {len(all_question_results)}")
    print(f"Total time: {total_time:.2f}s")
    print()
    print("OVERALL METRICS:")
    print(f"  Average answer similarity: {overall_avg_sim:.3f}")
    print(f"  Average top chunk similarity: {overall_avg_top:.3f}")
    print(f"  Average LLM grade: {overall_avg_llm:.3f}")
    print(f"  High similarity rate (>=0.7): {high_sim_rate*100:.1f}%")
    print()
    print("PER-DOCUMENT RESULTS:")
    for doc_eval in all_results:
        print(f"  {doc_eval.doc_id}:")
        print(f"    Avg similarity: {doc_eval.average_similarity:.3f}")
        print(f"    Avg top chunk similarity: {doc_eval.average_top_chunk_similarity:.3f}")
        print(f"    Avg LLM grade: {doc_eval.average_llm_grade:.3f}")
        for i, q_result in enumerate(doc_eval.questions, 1):
            print(
                f"      Q{i}: sim={q_result.answer_similarity:.3f}, "
                f"top_chunk={q_result.top_chunk_similarity:.3f}, "
                f"llm_grade={q_result.llm_grade:.3f}"
            )
    
    # Save results
    results_dict = {
        "summary": {
            "total_documents": len(all_results),
            "total_questions": len(all_question_results),
            "overall_avg_similarity": overall_avg_sim,
            "overall_avg_top_chunk_similarity": overall_avg_top,
            "overall_avg_llm_grade": overall_avg_llm,
            "high_similarity_rate": high_sim_rate,
            "total_time": total_time,
        },
        "documents": [asdict(doc_eval) for doc_eval in all_results]
    }
    
    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(results_dict, f, ensure_ascii=False, indent=2)
    
    print(f"\n[OK] Results saved to: {args.output}")
    print("=" * 70)
    
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

