#!/usr/bin/env python3
"""
Bulk verification helper:

1. Ensures every PDF inside docs/ is indexed (or re-indexed if requested)
2. Asks a short list of sanity questions against each doc via chunk-level QA
3. Saves the answers + retrieved chunks into reports/bulk_checks/<timestamp>.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from gdd_rag_backbone.config import DEFAULT_DOCS_DIR
from gdd_rag_backbone.llm_providers import (
    QwenProvider,
    make_embedding_func,
    make_llm_model_func,
)
from gdd_rag_backbone.rag_backend import indexing
from gdd_rag_backbone.rag_backend.chunk_qa import (
    ask_with_chunks,
    get_doc_metadata,
    load_doc_status,
)


REPORT_DIR = Path("reports") / "bulk_checks"
REPORT_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_QUESTIONS = [
    "Give a two-sentence summary of this document.",
    "List the main gameplay goals described.",
    "Are there any open questions or TODOs noted?",
]


def _make_doc_id(pdf_path: Path) -> str:
    doc_id = pdf_path.stem.replace(" ", "_").replace("[", "").replace("]", "")
    cleaned = "".join(c if c.isalnum() or c in "_-" else "_" for c in doc_id)
    while "__" in cleaned:
        cleaned = cleaned.replace("__", "_")
    return cleaned.strip("_") or "gdd_doc"


async def _maybe_index_doc(
    pdf_path: Path,
    doc_id: str,
    *,
    llm_func,
    embedding_func,
    force: bool = False,
) -> str:
    status = load_doc_status()
    needs_index = force or doc_id not in status
    if not needs_index:
        return "skipped"

    await indexing.index_document(
        doc_path=pdf_path,
        doc_id=doc_id,
        llm_func=llm_func,
        embedding_func=embedding_func,
    )
    return "indexed"


def _gather_pdf_docs(selected_ids: Optional[List[str]] = None) -> Dict[str, Path]:
    pdfs = sorted(DEFAULT_DOCS_DIR.glob("*.pdf"))
    mapping: Dict[str, Path] = {}
    for pdf in pdfs:
        doc_id = _make_doc_id(pdf)
        mapping[doc_id] = pdf

    if selected_ids:
        return {doc_id: mapping[doc_id] for doc_id in selected_ids if doc_id in mapping}
    return mapping


def _load_questions(args: argparse.Namespace) -> List[str]:
    if args.questions_file:
        path = Path(args.questions_file)
        data = json.loads(path.read_text())
        if isinstance(data, list):
            return [str(item) for item in data if str(item).strip()]
        raise ValueError(f"Questions file {path} is not a JSON list.")
    if args.question:
        return [q.strip() for q in args.question if q.strip()]
    return DEFAULT_QUESTIONS


async def main() -> None:
    parser = argparse.ArgumentParser(description="Bulk doc verification pipeline")
    parser.add_argument(
        "--doc-id",
        action="append",
        help="Doc IDs to process (default: all PDFs under docs/)",
    )
    parser.add_argument(
        "--force-reindex",
        action="store_true",
        help="Force re-indexing even if status already exists",
    )
    parser.add_argument(
        "--question",
        action="append",
        help="Ad-hoc question (can be repeated). Overrides default list if provided.",
    )
    parser.add_argument(
        "--questions-file",
        type=str,
        help="Path to JSON array of questions to ask each GDD.",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=4,
        help="Number of relevant chunks used for each QA request (default: 4)",
    )
    args = parser.parse_args()

    doc_map = _gather_pdf_docs(args.doc_id)
    if not doc_map:
        raise SystemExit("No documents found inside docs/.")

    provider = QwenProvider()
    llm_func = make_llm_model_func(provider)
    embedding_func = make_embedding_func(provider)
    questions = _load_questions(args)

    report: Dict[str, Dict[str, object]] = {}
    for doc_id, pdf_path in doc_map.items():
        print(f"\n=== Processing {doc_id} ({pdf_path.name}) ===")
        try:
            state = await _maybe_index_doc(
                pdf_path,
                doc_id,
                llm_func=llm_func,
                embedding_func=embedding_func,
                force=args.force_reindex,
            )
            print(f"Index status: {state}")
        except Exception as exc:  # pylint: disable=broad-except
            print(f"Failed indexing {doc_id}: {exc}")
            report[doc_id] = {
                "status": "index_failed",
                "error": str(exc),
                "results": [],
            }
            continue

        answers = []
        for question in questions:
            try:
                result = ask_with_chunks(
                    doc_id,
                    question,
                    provider=provider,
                    top_k=args.top_k,
                )
                answers.append(result)
            except Exception as exc:  # pylint: disable=broad-except
                answers.append(
                    {
                        "question": question,
                        "error": str(exc),
                    }
                )
        metadata = get_doc_metadata(doc_id) or {}
        report[doc_id] = {
            "status": "ok",
            "file": metadata.get("file_path") or pdf_path.name,
            "last_updated": metadata.get("updated_at"),
            "qa_results": answers,
        }

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    report_path = REPORT_DIR / f"bulk_report_{timestamp}.json"
    report_path.write_text(json.dumps(report, indent=2))
    print(f"\nReport saved to {report_path}")


if __name__ == "__main__":
    asyncio.run(main())


