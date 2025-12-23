"""
GDD (Game Design Document) extraction layer.

This module provides schemas and functions for extracting structured data
from Game Design Documents, such as objects, tanks, maps, etc.
"""

from gdd_rag_backbone.gdd.schemas import (
    GddObject,
    TankSpec,
    GddMap,
    GddSystem,
    GddInteraction,
    GddRequirement,
    GddLogicRule,
    RequirementSpec,
)
from gdd_rag_backbone.gdd.extraction import (
    extract_objects,
    extract_breakable_objects,
    extract_hiding_objects,
    extract_tanks,
    extract_maps,
    extract_requirements,
    extract_all_requirements,
)
from gdd_rag_backbone.gdd.requirement_matching import (
    evaluate_requirement,
    evaluate_all_requirements,
    generate_code_queries,
    search_code_chunks,
    classify_requirement_coverage,
)
from gdd_rag_backbone.gdd.analysis import analyze_gdd
from gdd_rag_backbone.gdd.todo import generate_todo_list

__all__ = [
    "GddObject",
    "TankSpec",
    "GddMap",
    "GddSystem",
    "GddInteraction",
    "GddRequirement",
    "GddLogicRule",
    "RequirementSpec",
    "extract_objects",
    "extract_breakable_objects",
    "extract_hiding_objects",
    "extract_tanks",
    "extract_maps",
    "extract_requirements",
    "extract_all_requirements",
    "analyze_gdd",
    "generate_todo_list",
    "evaluate_requirement",
    "evaluate_all_requirements",
    "generate_code_queries",
    "search_code_chunks",
    "classify_requirement_coverage",
]

