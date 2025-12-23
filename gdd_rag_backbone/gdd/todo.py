"""
Developer to-do generation from structured requirements.

This module converts extracted GDD requirements into actionable developer tasks
using LLM-based generation. Tasks include implementation details, priorities,
and related objects.
"""

from __future__ import annotations

# Standard library imports
import json
from typing import Any, Dict, List

# Project imports
from gdd_rag_backbone.llm_providers import QwenProvider, make_llm_model_func

SYSTEM_PROMPT = (
    "You are a senior technical game designer. Given structured GDD requirements, "
    "produce developer to-do items. Each task must include: title, description, "
    "related_objects, priority, and implementation_notes. Return ONLY JSON."
)


async def generate_todo_list(requirements_json: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Convert extracted requirements into actionable developer tasks."""
    requirements = requirements_json.get("requirements") if requirements_json else None
    if not requirements:
        return []

    provider = QwenProvider()
    llm_func = make_llm_model_func(provider)

    user_prompt = (
        "Generate a detailed developer to-do list based on these structured requirements:\n\n"
        f"{json.dumps(requirements, indent=2)}\n\n"
        "Return ONLY a JSON array of tasks where each task has: \n"
        "title, description, related_objects (list of strings), priority (high/medium/low), "
        "and implementation_notes."
    )

    response = await llm_func(prompt=user_prompt, system_prompt=SYSTEM_PROMPT, temperature=0.2)
    text = response.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1]) if lines[-1].strip() == "```" else "\n".join(lines[1:])

    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return []

    if isinstance(payload, dict):
        payload = [payload]
    if not isinstance(payload, list):
        return []
    cleaned: List[Dict[str, Any]] = []
    for item in payload:
        if isinstance(item, dict):
            cleaned.append(item)
    return cleaned

