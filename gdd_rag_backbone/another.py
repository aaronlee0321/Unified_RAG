"""
CLI to describe a source file (C# or Python) using the existing RAG pipeline.

Flow:
- Index the given file as a document (chunks + embeddings).
- Ask the RAG engine to produce a detailed, code-aware description.

Examples:
    # With indexing (default):
    python -m gdd_rag_backbone.another ./path/to/file.cs --doc-id my_code
    
    # Direct summarization without indexing:
    python -m gdd_rag_backbone.another ./path/to/file.cs --skip-index
    
    # Use existing index if available, otherwise direct summarization:
    python -m gdd_rag_backbone.another ./path/to/file.cs --doc-id my_code --skip-index
"""

from __future__ import annotations

import argparse
import asyncio
import math
import tempfile
import html
from pathlib import Path
from typing import Iterable

from gdd_rag_backbone.llm_providers import QwenProvider, make_llm_model_func, make_embedding_func
# Lazy imports for RAG functionality (only needed when indexing)


DEFAULT_QUESTION = (
    "Provide a detailed, section-by-section explanation of this source file. "
    "List each class and function/method, explain its purpose, inputs, outputs, side effects, "
    "stateful behavior, external dependencies, error handling, and any notable algorithms. "
    "Highlight how control flows between functions and how data is passed around. "
    "Keep the description grounded strictly in the code; avoid speculation."
)


async def describe_code_file(
    file_path: Path,
    doc_id: str,
    *,
    question: str = DEFAULT_QUESTION,
    mode: str = "mix",
    skip_index: bool = False,
    parser: str | None = None,
) -> str:
    """Index the file (unless skipped) and run a RAG query to describe it."""
    provider = QwenProvider()
    llm_func = make_llm_model_func(provider)
    embedding_func = make_embedding_func(provider)

    print(f"[another] starting describe for '{file_path}' (doc_id='{doc_id}', mode='{mode}', skip_index={skip_index})", flush=True)

    # For code/text files, bypass external parsers and index plain text chunks.
    cleanup_path: Path | None = None
    chosen_parser = parser
    file_for_index = file_path

    code_suffixes = {".cs", ".py", ".txt", ".md"}
    if file_path.suffix.lower() in code_suffixes:
        chosen_parser = "plain_text"
        code_text = file_path.read_text(encoding="utf-8", errors="ignore")
        
        # Check if file is small enough to use directly without chunking
        # For very small files, chunking by words breaks code structure
        # The plain_text parser can handle files directly, so only chunk if really large
        word_count = len(code_text.split())
        
        if word_count < 5000:  # For files under ~5000 words, use original structure
            # Use original file directly - preserve code structure
            # Just ensure it has .txt extension for plain_text parser
            tmp = Path(tempfile.gettempdir()) / f"{file_path.stem}_{doc_id}_plain.txt"
            tmp.write_text(code_text, encoding="utf-8")
            file_for_index = tmp
            cleanup_path = tmp
            print(f"[another] using original file structure for code: {file_for_index} (parser={chosen_parser}, {word_count} words)", flush=True)
        else:
            # For larger files, chunk by lines to preserve some structure
            def chunk_by_lines(text: str, lines_per_chunk: int = 200) -> Iterable[str]:
                lines = text.splitlines(keepends=True)
                total = len(lines)
                for i in range(0, total, lines_per_chunk):
                    chunk = "".join(lines[i : i + lines_per_chunk])
                    if chunk.strip():  # Only yield non-empty chunks
                        yield chunk

            chunks = list(chunk_by_lines(code_text, lines_per_chunk=200))
            # Write chunks separated by double newlines
            tmp = Path(tempfile.gettempdir()) / f"{file_path.stem}_{doc_id}_plain.txt"
            tmp.write_text("\n\n".join(chunks), encoding="utf-8")
            file_for_index = tmp
            cleanup_path = tmp
            print(f"[another] using line-based chunking for code: {file_for_index} (parser={chosen_parser}, {len(chunks)} chunks)", flush=True)

    if not skip_index:
        # Lazy import RAG functionality only when needed
        from gdd_rag_backbone.rag_backend.indexing import index_document
        from gdd_rag_backbone.rag_backend.query_engine import ask_question
        
        print("[another] indexing document (chunk + embed)...", flush=True)
        await index_document(
            file_for_index,
            doc_id,
            llm_func=llm_func,
            embedding_func=embedding_func,
            parser=chosen_parser,
            parse_method="auto",
        )
        print("[another] indexing complete.", flush=True)
        
        print("[another] querying RAG for description...", flush=True)
        # Ask for a detailed explanation grounded in retrieved chunks
        response = await ask_question(doc_id, question, mode=mode)
        print("[another] query complete.", flush=True)
    else:
        # Check if document is already indexed (lazy import)
        response = None
        try:
            from gdd_rag_backbone.rag_backend.indexing import get_rag_instance_for_doc
            from gdd_rag_backbone.rag_backend.query_engine import ask_question
            
            rag_instance = get_rag_instance_for_doc(doc_id)
            if rag_instance is not None:
                print("[another] skip_index enabled; using existing index.", flush=True)
                print("[another] querying RAG for description...", flush=True)
                response = await ask_question(doc_id, question, mode=mode)
                print("[another] query complete.", flush=True)
        except (ImportError, Exception):
            # Fall through to direct summarization
            pass
        
        # Direct summarization without indexing (if RAG wasn't used)
        if response is None:
            print("[another] skip_index enabled but document not indexed.", flush=True)
            print("[another] using direct LLM summarization (no RAG)...", flush=True)
            
            # Read the file content - use the original code_text if available, otherwise read from file
            # We already read code_text earlier for code files, so reuse it
            if 'code_text' not in locals() or not code_text:
                if file_for_index and file_for_index != file_path and file_for_index.exists():
                    code_text = file_for_index.read_text(encoding="utf-8", errors="ignore")
                elif file_path.suffix.lower() in {".cs", ".py", ".txt", ".md"}:
                    code_text = file_path.read_text(encoding="utf-8", errors="ignore")
                else:
                    # For other file types, try to read as text
                    try:
                        code_text = file_path.read_text(encoding="utf-8", errors="ignore")
                    except Exception as e:
                        raise ValueError(f"Cannot read file as text: {e}")
            
            # Build prompt for direct summarization
            system_prompt = (
                "You are an expert code analyst. Provide detailed, accurate explanations "
                "of source code based strictly on the provided code content."
            )
            
            # For very long files, we might need to chunk, but let's try direct first
            # Most LLMs can handle reasonably sized files (up to ~100k tokens)
            prompt = f"{question}\n\nCode:\n{code_text}"
            
            print("[another] sending to LLM for direct summarization...", flush=True)
            # llm_func is already async, so await it directly
            response = await llm_func(
                prompt=prompt,
                system_prompt=system_prompt,
                temperature=0.3,
            )
            print("[another] summarization complete.", flush=True)

    if cleanup_path and cleanup_path.exists():
        try:
            cleanup_path.unlink()
            print(f"[another] cleaned temp file: {cleanup_path}", flush=True)
        except OSError:
            pass
    return response


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Describe a code file via RAG.")
    parser.add_argument("file", type=Path, help="Path to the .cs or .py file to describe")
    parser.add_argument(
        "--doc-id",
        type=str,
        default=None,
        help="Document ID to use for indexing/querying (default: filename stem)",
    )
    parser.add_argument(
        "--question",
        type=str,
        default=DEFAULT_QUESTION,
        help="Custom question/prompt for the description",
    )
    parser.add_argument(
        "--mode",
        type=str,
        default="mix",
        help='RAG query mode (default: "mix"; see raganything modes)',
    )
    parser.add_argument(
        "--parser",
        type=str,
        default=None,
        help='Parser to use (default auto: uses docling for code/text wrapper)',
    )
    parser.add_argument(
        "--skip-index",
        action="store_true",
        help="Skip indexing. If document is already indexed, uses RAG. Otherwise, uses direct LLM summarization.",
    )
    parser.add_argument(
        "--enable-index",
        action="store_true",
        help="Enable indexing (opposite of --skip-index). By default, indexing is skipped.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    file_path: Path = args.file
    if not file_path.exists():
        raise SystemExit(f"File not found: {file_path}")
    if file_path.suffix not in {".cs", ".py"}:
        raise SystemExit("Only .cs or .py files are supported")

    doc_id = args.doc_id or file_path.stem

    # By default, skip indexing unless --enable-index is explicitly set
    # If --enable-index is set, skip_index = False
    # If --skip-index is set, skip_index = True  
    # Otherwise (default), skip_index = True
    skip_index = not args.enable_index  # Default: True (skip indexing)

    result = asyncio.run(
        describe_code_file(
            file_path,
            doc_id,
            question=args.question,
            mode=args.mode,
            skip_index=skip_index,
            parser=args.parser,
        )
    )
    print("\n=== RAG Description ===\n")
    print(result)


if __name__ == "__main__":
    main()

