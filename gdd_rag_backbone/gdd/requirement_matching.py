"""
Requirement → code coverage matching via lightweight RAG.

This module evaluates how well codebase implementations match GDD requirements
by using semantic search to find relevant code chunks and LLM-based classification
to determine implementation status (implemented, partially_implemented, not_implemented).
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from gdd_rag_backbone.gdd.schemas import GddRequirement
from gdd_rag_backbone.llm_providers import QwenProvider, make_llm_model_func
from gdd_rag_backbone.rag_backend.chunk_qa import get_top_chunks, load_doc_chunks

logger = logging.getLogger(__name__)
DEFAULT_REPORT_DIR = Path("reports/coverage_checks")

# In-memory cache for semantic results within a process.
# Keyed by (requirement_id, code_index_key, top_k, retrieval_version)
_SEMANTIC_CACHE: Dict[str, Dict[str, Any]] = {}


def generate_code_queries(requirement: GddRequirement) -> List[str]:
    # Prefer semantic description/summary + triggers/effects over names
    queries: List[str] = []
    for field in (
        getattr(requirement, "summary", None),
        requirement.description,
        requirement.acceptance_criteria,
        requirement.title,
    ):
        if field:
            queries.append(field)
    # Add triggers/effects as separate signals
    for trig in getattr(requirement, "triggers", []) or []:
        if trig:
            queries.append(trig)
    for eff in getattr(requirement, "effects", []) or []:
        if eff:
            queries.append(eff)
    if requirement.related_systems:
        queries.append("; ".join(requirement.related_systems))
    return [q for q in queries if q]


async def search_code_chunks(
    queries: Sequence[str],
    # Support single or multiple code indices
    code_index_id: str | Sequence[str],
    *,
    provider: Optional[QwenProvider] = None,
    top_k: int = 8,
) -> List[Dict[str, Any]]:
    if not queries:
        return []

    active_provider = provider or QwenProvider()

    # Normalize to list of code indices
    if isinstance(code_index_id, str):
        code_indices = [code_index_id]
    else:
        code_indices = list(code_index_id)

    async def _run_query(query: str) -> List[Dict[str, Any]]:
        def _load():
            # Search across all code indices
            return get_top_chunks(code_indices, query, provider=active_provider, top_k=top_k)

        return await asyncio.to_thread(_load)

    # Run all queries in parallel instead of sequentially
    query_tasks = [_run_query(query) for query in queries]
    all_query_results = await asyncio.gather(*query_tasks)

    # Merge results, keeping best score per chunk
    seen: Dict[str, Dict[str, Any]] = {}
    for query, chunks in zip(queries, all_query_results):
        for chunk in chunks:
            chunk_id = chunk["chunk_id"]
            existing = seen.get(chunk_id)
            if existing is None or chunk.get("score", 0) > existing.get("score", 0):
                seen[chunk_id] = {**chunk, "query": query}
    return sorted(seen.values(), key=lambda item: item.get("score", 0), reverse=True)


async def classify_requirement_coverage(
    requirement: GddRequirement,
    code_chunks: Sequence[Dict[str, Any]],
    llm_func,
) -> Dict[str, Any]:
    system_prompt = (
        "You are a senior gameplay engineer. Evaluate whether the provided code implements the requirement. "
        "Do NOT guess. If there is insufficient evidence, respond with 'not_implemented'."
    )

    requirement_payload = json.dumps(requirement.to_dict(), indent=2)
    if code_chunks:
        snippet_lines = []
        for idx, chunk in enumerate(code_chunks[:8]):
            snippet = chunk.get("content", "")
            snippet_lines.append(
                f"[Chunk {idx + 1}] id={chunk.get('chunk_id')} score={chunk.get('score', 0):.3f}\n{snippet[:1200]}"
            )
        code_context = "\n\n".join(snippet_lines)
    else:
        code_context = "No relevant code chunks were retrieved."

    user_prompt = f"""
Requirement:
{requirement_payload}

Candidate Code:
{code_context}

Classify the implementation status. Possible statuses: "implemented", "partially_implemented", "not_implemented".
Provide specific evidence (file path and short reason) when available.

Return ONLY JSON:
{{
  "requirement_id": "{requirement.id}",
  "status": "implemented/partially_implemented/not_implemented",
  "evidence": [
    {{
      "file": "path/to/file.ext",
      "reason": "How this code satisfies or fails the requirement"
    }}
  ]
}}
"""

    response = await llm_func(prompt=user_prompt, system_prompt=system_prompt, temperature=0.1)
    text = response.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(
            lines[1:-1]) if lines[-1].strip() == "```" else "\n".join(lines[1:])

    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return {
            "requirement_id": requirement.id,
            "status": "error",
            "evidence": [
                {
                    "file": None,
                    "reason": "LLM response could not be parsed",
                }
            ],
        }
    payload.setdefault("requirement_id", requirement.id)
    payload.setdefault("evidence", [])
    return payload


def fast_symbol_coverage(
    requirement: GddRequirement, symbol_index: Dict[str, list]
) -> Dict[str, Any]:
    """
    Cheap O(1) symbol lookup. Does NOT call LLM.
    requirement may optionally include:
      - expected_symbol (Class.Method)
      - or expected_class + expected_method
    """
    expected_symbol = getattr(requirement, "expected_symbol", None)
    expected_class = getattr(requirement, "expected_class", None)
    expected_method = getattr(requirement, "expected_method", None)

    used_symbol = None
    if not symbol_index:
        return {
            "requirement_id": requirement.id,
            "status": "unknown",
            "coverage_type": "fast",
            "used_symbol": used_symbol,
            "matches": [],
        }

    candidates = []
    if expected_symbol:
        candidates.append(expected_symbol)
    if expected_class and expected_method:
        candidates.append(f"{expected_class}.{expected_method}")
    anchors = getattr(requirement, "expected_code_anchors", []) or []
    candidates.extend(anchors)

    for symbol in candidates:
        locations = symbol_index.get(symbol, [])
        if locations:
            return {
                "requirement_id": requirement.id,
                "status": "implemented",
                "coverage_type": "fast",
                "used_symbol": symbol,
                "matches": locations,
            }

    return {
        "requirement_id": requirement.id,
        "status": "not_implemented",
        "coverage_type": "fast",
        "used_symbol": None,
        "matches": [],
    }


def semantic_retrieve_candidates(
    requirement: GddRequirement,
    code_index_id: str | Sequence[str],
    provider: QwenProvider,
    top_k: int = 12,
) -> List[Dict[str, Any]]:
    """
    Retrieve candidate code chunks via vector search using requirement summary/description.
    """
    query = requirement.description or requirement.title
    if not query:
        return []
    try:
        return get_top_chunks(
            [code_index_id] if isinstance(
                code_index_id, str) else code_index_id,
            query,
            provider=provider,
            top_k=top_k,
        )
    except Exception:
        return []


async def llm_semantic_judgement(
    requirement: GddRequirement, candidate: Dict[str, Any], llm_model, timeout: float = 25.0
) -> Dict[str, Any]:
    """
    Use LLM to classify how well a code chunk implements the requirement.
    Reduced timeout from 30s to 25s to prevent hanging.
    """
    system_prompt = (
        "You are a senior gameplay engineer. "
        "Determine whether this code implements the described requirement. "
        "Classify as 'implemented', 'partially_implemented', or 'not_related'. "
        "Keep reasoning to one short sentence."
    )
    # Truncate code content to prevent overly long prompts
    code_content = candidate.get("content", "")
    if len(code_content) > 2000:
        code_content = code_content[:2000] + "... [truncated]"

    user_prompt = f"""
Requirement:
{requirement.description or requirement.title}

Code:
{code_content}

Respond ONLY JSON:
{{
  "classification": "implemented|partially_implemented|not_related",
  "reason": "one sentence"
}}
"""
    try:
        resp_text = await asyncio.wait_for(
            llm_model(prompt=user_prompt,
                      system_prompt=system_prompt, temperature=0.1),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        return {
            "candidate": candidate,
            "classification": "not_related",
            "reason": "LLM timeout (exceeded 25s)",
        }
    except Exception as e:
        # Catch any other LLM errors and continue
        return {
            "candidate": candidate,
            "classification": "not_related",
            "reason": f"LLM error: {str(e)[:50]}",
        }
    text = resp_text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(
            lines[1:-1]) if lines[-1].strip() == "```" else "\n".join(lines[1:])
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        payload = {"classification": "not_related",
                   "reason": "Could not parse LLM response"}
    return {
        "candidate": candidate,
        "classification": payload.get("classification", "not_related"),
        "reason": payload.get("reason", "No reason provided"),
    }


async def semantic_coverage(
    requirement: GddRequirement,
    code_index_id: str | Sequence[str],
    provider: QwenProvider,
    llm_model,
    top_k: int = 12,
) -> Dict[str, Any]:
    # Cache key
    code_key = code_index_id if isinstance(
        code_index_id, str) else "_".join(code_index_id)
    cache_key = f"{requirement.id}::{code_key}::top{top_k}"
    cached = _SEMANTIC_CACHE.get(cache_key)
    if cached:
        return cached

    candidates = semantic_retrieve_candidates(
        requirement, code_index_id, provider, top_k=top_k)
    if not candidates:
        result = {
            "requirement_id": requirement.id,
            "status": "not_implemented",
            "coverage_type": "semantic",
            "best_match": None,
            "reason": "No candidates retrieved",
            "retrieved_chunks": [],
        }
        _SEMANTIC_CACHE[cache_key] = result
        return result

    # Evaluate candidates sequentially with early exit optimization
    # If we find an "implemented" match, we can stop early
    judgements: List[Dict[str, Any]] = []
    for idx, cand in enumerate(candidates):
        try:
            judgement = await llm_semantic_judgement(requirement, cand, llm_model)
            judgements.append(judgement)

            # Early exit: if we found a clear "implemented" match, stop evaluating
            if judgement.get("classification") == "implemented":
                logger.info(
                    f"[Semantic] Found implemented match for requirement {requirement.id} at candidate {idx + 1}/{len(candidates)}"
                )
                break
        except Exception as e:
            # Log but continue with next candidate
            logger.warning(
                f"[Semantic] Error evaluating candidate {idx + 1} for requirement {requirement.id}: {e}"
            )
            judgements.append(
                {
                    "candidate": cand,
                    "classification": "not_related",
                    "reason": f"Evaluation error: {str(e)[:50]}",
                }
            )

    status = "not_implemented"
    best_match = None
    for j in judgements:
        if j["classification"] == "implemented":
            status = "implemented"
            best_match = j
            break
        if j["classification"] == "partially_implemented" and status != "implemented":
            status = "partially_implemented"
            best_match = j

    result = {
        "requirement_id": requirement.id,
        "status": status,
        "coverage_type": "semantic",
        "best_match": best_match,
        "retrieved_chunks": candidates,
        "reason": best_match["reason"] if best_match else "No matching candidates",
    }
    _SEMANTIC_CACHE[cache_key] = result
    return result


def build_symbol_index(code_index_id: str | Sequence[str]) -> Dict[str, list]:
    """
    Build a lightweight symbol index from code chunks:
    - Detect 'class X' lines and subsequent 'def y' lines -> 'X.y'
    - Detect standalone 'def func' -> 'func'
    """
    if isinstance(code_index_id, str):
        code_ids = [code_index_id]
    else:
        code_ids = list(code_index_id)

    index: Dict[str, list] = {}

    for code_id in code_ids:
        for chunk in load_doc_chunks(code_id):
            lines = chunk.content.splitlines()
            current_class = None
            for line in lines:
                stripped = line.strip()
                if stripped.startswith("class "):
                    parts = stripped.split()
                    if len(parts) >= 2:
                        name = parts[1].split("(")[0].strip().strip(":")
                        current_class = name or current_class
                if stripped.startswith("def "):
                    fn = stripped[4:].split("(")[0].strip().strip(":")
                    if fn:
                        if current_class:
                            symbol = f"{current_class}.{fn}"
                            index.setdefault(symbol, []).append(
                                {"chunk_id": chunk.chunk_id,
                                    "doc_id": chunk.doc_id}
                            )
                        symbol = fn
                        index.setdefault(symbol, []).append(
                            {"chunk_id": chunk.chunk_id, "doc_id": chunk.doc_id}
                        )
    return index


async def evaluate_requirement(
    requirement: GddRequirement,
    # Support single or multiple code indices
    code_index_id: str | Sequence[str],
    *,
    provider: Optional[QwenProvider] = None,
    llm_func=None,
    top_k: int = 8,
    symbol_index: Optional[Dict[str, list]] = None,
) -> Dict[str, Any]:
    active_provider = provider or QwenProvider()
    symbol_index = symbol_index or {}

    # 1) Fast symbol coverage
    fast_result = fast_symbol_coverage(requirement, symbol_index)
    if fast_result["status"] == "implemented":
        return fast_result

    # 2) Semantic fallback
    llm_model = llm_func or make_llm_model_func(active_provider)
    semantic_result = await semantic_coverage(
        requirement,
        code_index_id,
        provider=active_provider,
        llm_model=llm_model,
        top_k=max(top_k, 10),  # ensure we fetch enough for semantic
    )
    return semantic_result


async def evaluate_all_requirements(
    doc_id: str,
    # Support single or multiple code indices
    code_index_id: str | Sequence[str],
    requirements: Sequence[GddRequirement],
    *,
    output_dir: Optional[Path] = None,
    provider: Optional[QwenProvider] = None,
    top_k: int = 8,
    symbol_index: Optional[Dict[str, list]] = None,
) -> Path:
    if not requirements:
        raise ValueError("No requirements provided for coverage evaluation.")

    out_dir = output_dir or DEFAULT_REPORT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    # Create a safe filename from code_index_id (handle both str and list)
    if isinstance(code_index_id, str):
        code_id_str = code_index_id
    else:
        # Use first 3 indices for filename
        code_id_str = "_".join(code_index_id[:3])
    report_path = out_dir / f"{doc_id}_{code_id_str}_coverage.json"

    active_provider = provider or QwenProvider()
    llm = make_llm_model_func(active_provider)
    # Build symbol index once if not provided
    symbol_index = symbol_index or build_symbol_index(code_index_id)

    results: List[Dict[str, Any]] = []
    total = len(requirements)
    for idx, requirement in enumerate(requirements, 1):
        try:
            logger.info(
                f"[Coverage] Evaluating requirement {idx}/{total}: {requirement.id} - {requirement.title[:50]}"
            )
            result = await evaluate_requirement(
                requirement,
                code_index_id,
                provider=active_provider,
                llm_func=llm,
                top_k=top_k,
                symbol_index=symbol_index,
            )
            results.append(result)
            status = result.get("status", "unknown")
            logger.info(
                f"[Coverage] Requirement {idx}/{total} completed: {status}")
        except Exception as e:
            logger.error(
                f"[Coverage] Error evaluating requirement {idx}/{total} ({requirement.id}): {e}",
                exc_info=True,
            )
            # Add error result so evaluation can continue
            results.append(
                {
                    "requirement_id": requirement.id,
                    "status": "error",
                    "coverage_type": "error",
                    "reason": f"Evaluation error: {str(e)[:100]}",
                }
            )

    report_payload = {
        "doc_id": doc_id,
        "code_index_id": code_index_id,
        "results": results,
    }
    report_path.write_text(json.dumps(
        report_payload, indent=2, ensure_ascii=False))
    return report_path
