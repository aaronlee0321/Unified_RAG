#!/usr/bin/env python3
"""Evaluate extracted requirements against a code RAG index."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import List

from gdd_rag_backbone.gdd.requirement_matching import evaluate_all_requirements
from gdd_rag_backbone.gdd.schemas import GddRequirement


def _load_requirements(path: Path) -> List[GddRequirement]:
    if not path.exists():
        raise FileNotFoundError(f"Requirements file not found: {path}")
    data = json.loads(path.read_text())
    if isinstance(data, dict) and "requirements" in data:
        payload = data["requirements"]
    else:
        payload = data
    if not isinstance(payload, list):
        raise ValueError("Requirements file must be a list or contain a 'requirements' list.")
    requirements: List[GddRequirement] = []
    for item in payload:
        if isinstance(item, dict):
            requirements.append(GddRequirement(**item))
    if not requirements:
        raise ValueError("No requirements found in the provided file.")
    return requirements


async def main() -> None:
    parser = argparse.ArgumentParser(description="Match GDD requirements against code chunks.")
    parser.add_argument("doc_id", help="Document ID used during ingestion")
    parser.add_argument("code_index_id", help="Doc ID representing the code RAG index")
    parser.add_argument(
        "--requirements-file",
        required=True,
        type=Path,
        help="Path to JSON file containing requirements (combined extraction output or a requirements list).",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=8,
        help="Number of code chunks to retrieve per query (default: 8)",
    )
    args = parser.parse_args()

    requirements = _load_requirements(args.requirements_file)
    report_path = await evaluate_all_requirements(
        args.doc_id,
        args.code_index_id,
        requirements,
        top_k=args.top_k,
    )
    print(f"Coverage report written to {report_path}")


if __name__ == "__main__":
    asyncio.run(main())
