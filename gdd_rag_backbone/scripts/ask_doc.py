#!/usr/bin/env python3
"""
Lightweight CLI helper to ask questions about a single document.

The script performs three steps:
1. Loads the chunks that belong to the requested doc_id from the local KV store.
2. Ranks the chunks against the question using the configured embedding model.
3. Sends the top ranked chunks plus the question to the LLM and prints the answer.

Example:
    python gdd_rag_backbone/scripts/ask_doc.py progression_module_tank_wars_achievement_design \\
        "Summarize the achievement system goals"
"""

import argparse
from typing import List
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from gdd_rag_backbone.llm_providers import QwenProvider  # noqa: E402
from gdd_rag_backbone.rag_backend.chunk_qa import (  # noqa: E402
    ask_with_chunks,
    ask_across_docs,
    load_doc_status,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Ask a question about one or more documents")
    parser.add_argument(
        "--doc-id",
        action="append",
        dest="doc_ids",
        help="Doc ID to include (repeatable). If omitted, use positional doc_id or --all-docs.",
    )
    parser.add_argument(
        "--all-docs",
        action="store_true",
        help="Query across all indexed documents.",
    )
    parser.add_argument("doc_id", nargs="?", help="Fallback document ID when --doc-id is not used")
    parser.add_argument("question", help="Question to ask across the selected documents")
    parser.add_argument(
        "--top-k",
        type=int,
        default=4,
        help="Number of relevant chunks to send to the LLM (default: 4)",
    )
    args = parser.parse_args()

    status = load_doc_status()
    all_doc_ids = list(status.keys())

    doc_ids: List[str] = []
    if args.all_docs:
        doc_ids = all_doc_ids
    elif args.doc_ids:
        doc_ids = args.doc_ids
    elif args.doc_id:
        doc_ids = [args.doc_id]
    else:
        parser.error("Provide a doc_id, --doc-id, or --all-docs.")

    doc_ids = [doc for doc in doc_ids if doc]
    if not doc_ids:
        parser.error("No valid doc IDs were provided.")

    provider = QwenProvider()
    if len(doc_ids) == 1:
        target = doc_ids[0]
        result = ask_with_chunks(
            target,
            args.question,
            provider=provider,
            top_k=args.top_k,
        )
        print("\n" + "=" * 80)
        print(f"Doc ID: {result['doc_id']}")
        print(f"File: {result.get('file_path') or 'Unknown'}")
        print("=" * 80)
        print(result["answer"])
        print("=" * 80)
        context = result.get("context", [])
        if context:
            print("\nTop Chunks:")
            for idx, chunk in enumerate(context, start=1):
                print(f"\n[{idx}] score={chunk['score']:.3f} id={chunk['chunk_id']}")
                print(chunk["content"][:500] + ("..." if len(chunk["content"]) > 500 else ""))
        print("=" * 80)
    else:
        if args.top_k < 2:
            parser.error("For multi-doc queries, use top_k >= 2.")
        result = ask_across_docs(
            doc_ids,
            args.question,
            provider=provider,
            top_k=args.top_k,
        )
        print("\n" + "=" * 80)
        print(f"Doc IDs: {', '.join(result['doc_ids'])}")
        print("=" * 80)
        print(result["answer"])
        print("=" * 80)
        context = result.get("context", [])
        if context:
            print("\nTop Chunks (across docs):")
            for idx, chunk in enumerate(context, start=1):
                print(
                    f"\n[{idx}] doc_id={chunk['doc_id']} score={chunk['score']:.3f} chunk={chunk['chunk_id']}"
                )
                print(chunk["content"][:500] + ("..." if len(chunk["content"]) > 500 else ""))
        print("=" * 80)


if __name__ == "__main__":
    main()

