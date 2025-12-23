"""
Structured dataclasses for the GDD pipeline.
"""

from dataclasses import asdict, dataclass, field
from typing import List, Optional


@dataclass
class GddObject:
    id: str
    name: str
    category: Optional[str] = None
    description: Optional[str] = None
    size_x: Optional[float] = None
    size_y: Optional[float] = None
    size_z: Optional[float] = None
    hp: Optional[int] = None
    armor: Optional[int] = None
    speed: Optional[float] = None
    player_pass_through: Optional[bool] = None
    bullet_pass_through: Optional[bool] = None
    destructible: Optional[bool] = None
    special_rules: Optional[str] = None
    source_note: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class TankSpec:
    id: str
    name: Optional[str] = None
    class_name: Optional[str] = None
    size_x: Optional[float] = None
    size_y: Optional[float] = None
    size_z: Optional[float] = None
    hp: Optional[int] = None
    armor: Optional[int] = None
    speed: Optional[float] = None
    firepower: Optional[float] = None
    range: Optional[float] = None
    special_abilities: Optional[str] = None
    gameplay_notes: Optional[str] = None
    source_note: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class GddMap:
    id: str
    name: str
    mode: Optional[str] = None
    scene: Optional[str] = None
    size_x: Optional[float] = None
    size_y: Optional[float] = None
    player_count: Optional[int] = None
    objective_locations: Optional[str] = None
    spawn_points: Optional[int] = None
    cover_elements: Optional[str] = None
    special_features: Optional[str] = None
    gameplay_notes: Optional[str] = None
    source_note: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class GddSystem:
    id: str
    name: str
    description: Optional[str] = None
    mechanics: Optional[str] = None
    objectives: Optional[str] = None
    related_objects: List[str] = field(default_factory=list)
    interactions: List[str] = field(default_factory=list)
    source_note: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class GddInteraction:
    id: str
    summary: str
    description: Optional[str] = None
    trigger: Optional[str] = None
    effect: Optional[str] = None
    related_objects: List[str] = field(default_factory=list)
    related_systems: List[str] = field(default_factory=list)
    source_note: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class GddLogicRule:
    id: str
    statement: str
    applies_to: List[str] = field(default_factory=list)
    condition: Optional[str] = None
    result: Optional[str] = None
    priority: Optional[str] = None
    source_note: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class GddRequirement:
    id: str
    title: str
    description: str
    summary: Optional[str] = None
    category: Optional[str] = None
    priority: Optional[str] = None
    status: Optional[str] = None
    acceptance_criteria: Optional[str] = None
    related_objects: List[str] = field(default_factory=list)
    related_systems: List[str] = field(default_factory=list)
    source_note: Optional[str] = None
    # Extended structured fields
    triggers: List[str] = field(default_factory=list)
    effects: List[str] = field(default_factory=list)
    entities_involved: List[str] = field(default_factory=list)
    expected_code_anchors: List[str] = field(default_factory=list)  # e.g., ["Class.Method", "OtherClass.fn"]

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class RequirementSpec:
    """Backwards-compatible alias used by older helpers."""

    id: str
    summary: str
    category: Optional[str] = None
    details: Optional[str] = None
    priority: Optional[str] = None
    status: Optional[str] = None
    acceptance_criteria: Optional[str] = None
    source_section: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


__all__ = [
    "GddObject",
    "TankSpec",
    "GddMap",
    "GddSystem",
    "GddInteraction",
    "GddLogicRule",
    "GddRequirement",
    "RequirementSpec",
]
