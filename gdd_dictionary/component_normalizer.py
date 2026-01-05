
# gdd_dictionary/component_normalizer.py
import re
from typing import Dict, Any

def to_snake_case_english_key(vietnamese_name: str) -> str:
    # keep internal stability with English snake_case key; v1: transliterate basic latin only
    # minimal heuristic: strip diacritics & non-word; then snake_case
    s = vietnamese_name.lower()
    s = re.sub(r"[^a-z0-9\s]", "", s)        # crude removal; v2 can add transliteration
    s = re.sub(r"\s+", "_", s).strip("_")
    return s or "unnamed_component"

def normalize_component(raw_component: Dict[str, Any]) -> Dict[str, Any]:
    display = (raw_component.get("display_name_vi") or "").strip()
    key = to_snake_case_english_key(display)
    aliases = [a.strip() for a in (raw_component.get("aliases_vi") or []) if a and a.strip()]
    evidence = [e for e in (raw_component.get("evidence") or []) if (e.get("evidence_text_vi") or "").strip()]
    return {
        "component_key": key,
        "display_name_vi": display or key,
        "aliases_vi": aliases,
        "evidence": evidence,
    }
