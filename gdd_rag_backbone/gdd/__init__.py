"""
GDD (Game Design Document) extraction layer.

This module provides schemas and functions for extracting structured data
from Game Design Documents, such as objects, tanks, maps, etc.
"""

from gdd_rag_backbone.gdd.analysis import analyze_gdd
from gdd_rag_backbone.gdd.extraction import (
    extract_all_requirements,
    extract_breakable_objects,
    extract_hiding_objects,
    extract_maps,
    extract_objects,
    extract_requirements,
    extract_tanks,
)
from gdd_rag_backbone.gdd.requirement_matching import (
    classify_requirement_coverage,
    evaluate_all_requirements,
    evaluate_requirement,
    generate_code_queries,
    search_code_chunks,
)
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
