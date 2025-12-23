#!/usr/bin/env python3
"""
Utility script to index a source code repository as a single RAG document.

The script performs three steps:
1. Scan a source directory for text-based code files (C#, shaders, JSON, etc.).
2. Emit a flattened plain-text snapshot that preserves file boundaries.
3. Index the generated snapshot via the existing RAG pipeline so it can be queried
   like any other document (e.g., for requirement/code coverage matching).
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Iterator, List, Sequence, Set

# Ensure project root is on PYTHONPATH when executed directly
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from gdd_rag_backbone.config import DEFAULT_DOCS_DIR
from gdd_rag_backbone.llm_providers import (
    QwenProvider,
    make_embedding_func,
    make_llm_model_func,
)
from gdd_rag_backbone.rag_backend import index_document


DEFAULT_INCLUDE_EXTS: Sequence[str] = (
    ".cs",
    ".shader",
    ".compute",
    ".cginc",
    ".hlsl",
    ".uxml",
    ".uss",
    ".asmdef",
    ".json",
    ".txt",
)

DEFAULT_EXCLUDE_DIRS: Set[str] = {
    ".git",
    ".idea",
    ".vscode",
    ".vs",
    ".svn",
    "Library",
    "Logs",
    "Temp",
    "Build",
    "Builds",
    "obj",
    "DerivedDataCache",
    "__pycache__",
}


def _parse_list(value: str | Sequence[str], *, lower: bool = True) -> List[str]:
    if isinstance(value, str):
        items = [item.strip() for item in value.split(",")]
    else:
        items = list(value)
    normalized = [item for item in items if item]
    if lower:
        normalized = [item.lower() for item in normalized]
    return normalized


def _should_skip(path: Path, *, root: Path, exclude_dirs: Set[str]) -> bool:
    rel_parts = path.relative_to(root).parts[:-1]  # omit the filename itself
    for part in rel_parts:
        if part.lower() in exclude_dirs:
            return True
    return False


def iter_code_files(
    root: Path,
    include_exts: Iterable[str],
    exclude_dirs: Set[str],
) -> Iterator[Path]:
    include_set = {ext.lower() for ext in include_exts}
    for file_path in sorted(root.rglob("*")):
        if not file_path.is_file():
            continue
        if include_set and file_path.suffix.lower() not in include_set:
            continue
        if _should_skip(file_path, root=root, exclude_dirs=exclude_dirs):
            continue
        yield file_path


def render_snapshot(
    source_dir: Path,
    code_files: Sequence[Path],
    output_path: Path,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).isoformat()
    header = [
        f"# Code Snapshot for {source_dir.name}",
        f"Source: {source_dir}",
        f"Generated: {timestamp}",
        f"Total files: {len(code_files)}",
        "",
        "Each section below mirrors a file from the source tree.",
        "Lines are captured verbatim to help semantic retrieval.",
    ]
    with output_path.open("w", encoding="utf-8") as handle:
        handle.write("\n".join(header))
        for idx, file_path in enumerate(code_files, 1):
            rel_path = file_path.relative_to(source_dir).as_posix()
            handle.write("\n\n")
            handle.write(f"===== FILE {idx}/{len(code_files)}: {rel_path} =====\n")
            try:
                content = file_path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
            handle.write(content.rstrip())
            handle.write("\n")


async def index_code_snapshot(snapshot_path: Path, doc_id: str) -> None:
    provider = QwenProvider()
    llm_func = make_llm_model_func(provider)
    embedding_func = make_embedding_func(provider)
    await index_document(
        doc_path=snapshot_path,
        doc_id=doc_id,
        llm_func=llm_func,
        embedding_func=embedding_func,
    )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Index a source codebase into the RAG store.")
    parser.add_argument(
        "--source",
        type=Path,
        required=True,
        help="Absolute path to the root of the code repository to ingest.",
    )
    parser.add_argument(
        "--doc-id",
        type=str,
        default="codebase",
        help="Document ID to use for the indexed snapshot (default: codebase).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional explicit snapshot path. Defaults to docs/{doc_id}_codebase.txt",
    )
    parser.add_argument(
        "--include-ext",
        default=",".join(DEFAULT_INCLUDE_EXTS),
        help="Comma-separated list of file extensions to include.",
    )
    parser.add_argument(
        "--exclude-dirs",
        default=",".join(sorted(DEFAULT_EXCLUDE_DIRS)),
        help="Comma-separated list of directory names to skip anywhere in the tree.",
    )
    return parser


async def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()

    source_dir = args.source.expanduser().resolve()
    if not source_dir.exists():
        parser.error(f"Source directory not found: {source_dir}")

    include_exts = _parse_list(args.include_ext)
    exclude_dirs = set(_parse_list(args.exclude_dirs))

    code_files = list(iter_code_files(source_dir, include_exts, exclude_dirs))
    if not code_files:
        parser.error("No code files found with the provided filters.")

    snapshot_path = args.output
    if snapshot_path is None:
        snapshot_name = f"{args.doc_id}_codebase.txt"
        snapshot_path = DEFAULT_DOCS_DIR / snapshot_name
    snapshot_path = snapshot_path.expanduser().resolve()

    print(f"📁 Source directory: {source_dir}")
    print(f"🗂️  Files captured: {len(code_files)}")
    print(f"📝 Snapshot path: {snapshot_path}")
    print(f"🆔 Document ID: {args.doc_id}")

    render_snapshot(source_dir, code_files, snapshot_path)
    print("✅ Snapshot written. Starting indexing...")

    await index_code_snapshot(snapshot_path, args.doc_id)
    print("🎉 Codebase indexed successfully!")


if __name__ == "__main__":
    asyncio.run(main())

