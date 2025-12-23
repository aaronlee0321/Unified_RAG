"""
Structured extraction utilities built on stored RAG chunks.

This module provides functions to extract structured data from Game Design Documents
using RAG-based retrieval and LLM-based extraction. It supports extraction of:
- Game objects (tanks, props, environmental elements)
- Maps and levels
- Gameplay systems
- Logic rules and interactions
- Requirements and specifications
"""

from __future__ import annotations

# Standard library imports
import asyncio
import json
from dataclasses import MISSING, fields
from functools import lru_cache
from typing import Any, Dict, List, Optional, Sequence, Tuple, Type, TypeVar

# Project imports
from gdd_rag_backbone.gdd.schemas import (
    GddInteraction,
    GddLogicRule,
    GddMap,
    GddObject,
    GddRequirement,
    GddSystem,
    RequirementSpec,
    TankSpec,
)
from gdd_rag_backbone.llm_providers import QwenProvider
from gdd_rag_backbone.rag_backend.chunk_qa import get_top_chunks

T = TypeVar("T")


@lru_cache(maxsize=1)
def _provider_bundle() -> Dict[str, QwenProvider]:
    return {"provider": QwenProvider()}


async def _retrieve_context(doc_ids: Sequence[str], query: str, top_k: int) -> Tuple[str, QwenProvider]:
    bundle = _provider_bundle()
    provider = bundle["provider"]

    def _load() -> List[Dict[str, Any]]:
        return get_top_chunks(doc_ids, query, provider=provider, top_k=top_k)

    chunks = await asyncio.to_thread(_load)
    context = "\n\n".join(chunk["content"] for chunk in chunks)
    return context, provider


async def _call_llm(
    prompt: str,
    system_prompt: str,
    *,
    llm_func=None,
    temperature: float = 0.1,
) -> str:
    if llm_func is not None:
        return await llm_func(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=temperature,
        )

    provider = _provider_bundle()["provider"]

    def _run() -> str:
        return provider.llm(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=temperature,
        )

    return await asyncio.to_thread(_run)


def _strip_code_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        if lines[-1].strip() == "```":
            return "\n".join(lines[1:-1])
        return "\n".join(lines[1:])
    return text


def _parse_json_array(response_text: str) -> List[dict]:
    cleaned = _strip_code_fences(response_text)
    data = json.loads(cleaned)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return [data]
    raise ValueError("LLM response is not a JSON array")


def _coerce_dataclass(cls: Type[T], raw: Dict[str, Any]) -> T:
    kwargs: Dict[str, Any] = {}
    for field in fields(cls):
        value = raw.get(field.name)
        if field.name == "id":
            value = value or raw.get("name") or raw.get("title") or raw.get("summary")
            if not value:
                value = f"{cls.__name__}_{abs(hash(str(raw))) % 10_000}"
        elif field.name == "name" and value in (None, ""):
            value = raw.get("name") or raw.get("title") or raw.get("summary") or "unknown"
        elif field.name == "title" and value in (None, ""):
            value = raw.get("title") or raw.get("name") or raw.get("summary") or "Untitled"

        if value is None and field.default_factory is not MISSING:  # type: ignore[attr-defined]
            continue  # Use dataclass default factory
        if value is None and field.default is not MISSING:
            continue  # Use dataclass default
        kwargs[field.name] = value
    return cls(**kwargs)  # type: ignore[arg-type]


async def _extract_list(
    doc_id: str,
    *,
    query: str,
    system_prompt: str,
    template: str,
    model: Type[T],
    llm_func=None,
    top_k: int = 6,
    temperature: float = 0.1,
) -> List[T]:
    context, _ = await _retrieve_context([doc_id], query, top_k)
    if not context.strip():
        raise ValueError("No relevant context retrieved for extraction. Re-index the document.")
    prompt = template.replace("{{CONTEXT}}", context)
    response_text = await _call_llm(prompt, system_prompt, llm_func=llm_func, temperature=temperature)
    try:
        payload = _parse_json_array(response_text)
    except json.JSONDecodeError as exc:  # pragma: no cover - defensive
        raise ValueError(f"Extraction response was not valid JSON: {exc}") from exc
    results: List[T] = []
    for item in payload:
        if isinstance(item, dict):
            results.append(_coerce_dataclass(model, item))
    return results


async def extract_objects(
    doc_id: str,
    category: Optional[str] = None,
    *,
    llm_func=None,
) -> List[GddObject]:
    query = (
        "List every game object, prop, or environmental element, including its category "
        "(BR/BO/DE/GR/HI/OP/TA), dimensions, health, interaction rules, and notes."
    )
    system_prompt = (
        "You convert Game Design Documents into structured technical data. "
        "Return ONLY JSON describing each object."
    )
    template = """
Extract all game objects from this context. Use null for missing values.

Each object must match:
{
  "id": "...",
  "name": "...",
  "category": "BR/BO/DE/GR/HI/OP/TA",
  "description": "...",
  "size_x": null,
  "size_y": null,
  "size_z": null,
  "hp": null,
  "armor": null,
  "speed": null,
  "player_pass_through": null,
  "bullet_pass_through": null,
  "destructible": null,
  "special_rules": null,
  "source_note": "Section or page reference"
}

CONTEXT:
{{CONTEXT}}
"""
    objects = await _extract_list(
        doc_id,
        query=query,
        system_prompt=system_prompt,
        template=template,
        model=GddObject,
        llm_func=llm_func,
        top_k=8,
    )
    if category:
        objects = [obj for obj in objects if (obj.category or "").upper() == category.upper()]
    return objects


async def extract_breakable_objects(doc_id: str, *, llm_func=None) -> List[GddObject]:
    """Compatibility wrapper for BR objects."""
    return await extract_objects(doc_id, category="BR", llm_func=llm_func)


async def extract_hiding_objects(doc_id: str, *, llm_func=None) -> List[GddObject]:
    """Compatibility wrapper for HI objects."""
    return await extract_objects(doc_id, category="HI", llm_func=llm_func)


async def extract_tanks(doc_id: str, *, llm_func=None) -> List[TankSpec]:
    query = "Extract every vehicle or tank specification, including stats and gameplay notes."
    system_prompt = (
        "You extract tank specifications from GDDs. Return ONLY JSON arrays of tank entries."
    )
    template = """
List every tank or vehicle mentioned in the context. Use null for missing values.
Each tank entry must include:
{
  "id": "...",
  "name": "...",
  "class_name": "Heavy/Light/Medium/etc.",
  "size_x": null,
  "size_y": null,
  "size_z": null,
  "hp": null,
  "armor": null,
  "speed": null,
  "firepower": null,
  "range": null,
  "special_abilities": null,
  "gameplay_notes": null,
  "source_note": "Section reference"
}

CONTEXT:
{{CONTEXT}}
"""
    return await _extract_list(
        doc_id,
        query=query,
        system_prompt=system_prompt,
        template=template,
        model=TankSpec,
        llm_func=llm_func,
        top_k=6,
    )


async def extract_maps(doc_id: str, *, llm_func=None) -> List[GddMap]:
    query = "Extract every map or level description including mode, scene, size, objectives, and notes."
    system_prompt = "Return ONLY JSON arrays describing gameplay maps."
    template = """
Capture every map specification in this context.
Each map entry must include:
{
  "id": "...",
  "name": "...",
  "mode": "...",
  "scene": "...",
  "size_x": null,
  "size_y": null,
  "player_count": null,
  "objective_locations": null,
  "spawn_points": null,
  "cover_elements": null,
  "special_features": null,
  "gameplay_notes": null,
  "source_note": "Section reference"
}

CONTEXT:
{{CONTEXT}}
"""
    return await _extract_list(
        doc_id,
        query=query,
        system_prompt=system_prompt,
        template=template,
        model=GddMap,
        llm_func=llm_func,
    )


async def extract_systems(doc_id: str, *, llm_func=None) -> List[GddSystem]:
    query = "List all gameplay systems or subsystems, their descriptions, mechanics, and relationships."
    system_prompt = "Return ONLY JSON arrays describing each gameplay system."
    template = """
Extract every gameplay system mentioned in the context.
Each entry must include:
{
  "id": "...",
  "name": "...",
  "description": "...",
  "mechanics": "...",
  "objectives": "...",
  "related_objects": [],
  "interactions": [],
  "source_note": "Section reference"
}

CONTEXT:
{{CONTEXT}}
"""
    return await _extract_list(
        doc_id,
        query=query,
        system_prompt=system_prompt,
        template=template,
        model=GddSystem,
        llm_func=llm_func,
        top_k=8,
    )


async def extract_logic_rules(doc_id: str, *, llm_func=None) -> List[GddInteraction]:
    query = "Identify every explicit rule, trigger, condition, or interaction described in the GDD."
    system_prompt = "Return ONLY JSON arrays describing each gameplay rule or interaction."
    template = """
List every rule/interaction described in the context. Use null for missing values.
Format each entry as:
{
  "id": "...",
  "summary": "...",
  "description": "...",
  "trigger": "...",
  "effect": "...",
  "related_objects": [],
  "related_systems": [],
  "source_note": "Section reference"
}

CONTEXT:
{{CONTEXT}}
"""
    return await _extract_list(
        doc_id,
        query=query,
        system_prompt=system_prompt,
        template=template,
        model=GddInteraction,
        llm_func=llm_func,
        top_k=8,
    )


async def extract_requirements(doc_id: str, *, llm_func=None) -> List[RequirementSpec]:
    combined = await extract_all_requirements(doc_id, llm_func=llm_func)
    requirements: List[RequirementSpec] = []
    for item in combined.get("requirements", []):
        requirements.append(
            RequirementSpec(
                id=item.get("id", ""),
                summary=item.get("title", ""),
                category=item.get("category"),
                details=item.get("description"),
                priority=item.get("priority"),
                status=item.get("status"),
                acceptance_criteria=item.get("acceptance_criteria"),
                source_section=item.get("source_note"),
            )
        )
    return requirements


MASTER_EXTRACTION_TEMPLATE = """
Extract ALL objects, systems, logic rules, and requirements from this GDD context.
Return ONLY JSON following this schema:
{
  "objects": [ ... ],
  "systems": [ ... ],
  "logic_rules": [ ... ],
  "requirements": [ ... ]
}

Objects schema:
{
  "id": "...",
  "name": "...",
  "category": "BR/BO/DE/GR/HI/OP/TA",
  "description": "...",
  "size_x": null,
  "size_y": null,
  "size_z": null,
  "hp": null,
  "armor": null,
  "speed": null,
  "player_pass_through": null,
  "bullet_pass_through": null,
  "destructible": null,
  "special_rules": null,
  "source_note": "..."
}

Systems schema:
{
  "id": "...",
  "name": "...",
  "description": "...",
  "mechanics": "...",
  "objectives": "...",
  "related_objects": [],
  "interactions": [],
  "source_note": "..."
}

Logic rules schema:
{
  "id": "...",
  "summary": "...",
  "description": "...",
  "trigger": "...",
  "effect": "...",
  "related_objects": [],
  "related_systems": [],
  "source_note": "..."
}

Requirements schema:
{
  "id": "...",
  "title": "...",
  "description": "...",
  "category": "progression/monetization/combat/ui/tech",
  "priority": "high/medium/low",
  "status": "proposed/in-progress/complete",
  "acceptance_criteria": "...",
  "related_objects": [],
  "related_systems": [],
  "source_note": "..."
}

Do NOT invent facts. Use null for missing values.

CONTEXT:
{{CONTEXT}}
"""


async def extract_all_requirements(
    doc_id: str,
    *,
    llm_func=None,
    top_k: int = 10,
) -> Dict[str, List[dict]]:
    query = (
        "Extract ALL objects, systems, rules, and requirements described in this document."
    )
    context, _ = await _retrieve_context([doc_id], query, top_k)
    if not context.strip():
        raise ValueError("No context available for combined extraction.")
    system_prompt = (
        "You convert Game Design Documents into structured technical data. "
        "Return ONLY JSON. Do NOT invent anything. Use null for missing values."
    )
    prompt = MASTER_EXTRACTION_TEMPLATE.replace("{{CONTEXT}}", context)
    response_text = await _call_llm(prompt, system_prompt, llm_func=llm_func, temperature=0.05)
    cleaned = _strip_code_fences(response_text)
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError as exc:  # pragma: no cover - defensive
        raise ValueError(f"Combined extraction response was not JSON: {exc}") from exc

    objects = [
        _coerce_dataclass(GddObject, item).to_dict()
        for item in payload.get("objects", [])
        if isinstance(item, dict)
    ]
    systems = [
        _coerce_dataclass(GddSystem, item).to_dict()
        for item in payload.get("systems", [])
        if isinstance(item, dict)
    ]
    logic_rules = [
        _coerce_dataclass(GddInteraction, item).to_dict()
        for item in payload.get("logic_rules", [])
        if isinstance(item, dict)
    ]
    requirements = [
        _coerce_dataclass(GddRequirement, item).to_dict()
        for item in payload.get("requirements", [])
        if isinstance(item, dict)
    ]
    return {
        "objects": objects,
        "systems": systems,
        "logic_rules": logic_rules,
        "requirements": requirements,
    }

