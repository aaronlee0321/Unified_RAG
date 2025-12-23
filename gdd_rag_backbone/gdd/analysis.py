"""
High-level GDD analysis helpers.

This module provides functions for generating comprehensive analysis and summaries
of Game Design Documents using RAG-based retrieval and LLM generation.
"""

from __future__ import annotations

# Standard library imports
import asyncio
from typing import Optional

# Project imports
from gdd_rag_backbone.llm_providers import QwenProvider, make_llm_model_func
from gdd_rag_backbone.rag_backend.chunk_qa import get_top_chunks

ANALYSIS_QUERY = (
    "Produce a comprehensive understanding of this game: genre, core loop, "
    "major systems, player interactions, key objects/entities, maps/modes, and special mechanics."
)

SYSTEM_PROMPT = (
    "You are a professional game designer. Using ONLY the retrieved context, "
    "generate a deep understanding of this game's design: genre, core gameplay loop, "
    "main systems and subsystems, player interactions, key objects/entities, maps and modes, "
    "and special mechanics. Do NOT invent details. If unsure, say 'unknown'."
)


async def analyze_gdd(doc_id: str, *, provider: Optional[QwenProvider] = None, top_k: int = 8) -> str:
    """Return a narrative summary describing the provided GDD."""
    active_provider = provider or QwenProvider()
    llm_func = make_llm_model_func(active_provider)

    def _load_chunks():
        return get_top_chunks([doc_id], ANALYSIS_QUERY, provider=active_provider, top_k=top_k)

    chunks = await asyncio.to_thread(_load_chunks)
    if not chunks:
        raise ValueError(
            f"No indexed chunks found for '{doc_id}'. Please run the ingestion pipeline first."
        )

    context = "\n\n".join(chunk["content"] for chunk in chunks)
    prompt = (
        "Using ONLY the following context, provide the requested analysis.\n\n"
        f"Context:\n{context}\n\nAnswer:"
    )
    response = await llm_func(prompt=prompt, system_prompt=SYSTEM_PROMPT, temperature=0.3)
    return response.strip()

