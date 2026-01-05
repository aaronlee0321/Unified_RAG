
# gdd_dictionary/dictionary_builder.py
from typing import List, Dict, Any
import logging

from backend.storage.gdd_supabase_storage import load_gdd_chunks_from_supabase  # reuse chunk loader  
from backend.gdd_hyde import translate_query_if_needed                           # reuse EN→VI helper  
from .component_extractor import extract_components_from_chunk
from .component_normalizer import normalize_component
from backend.storage.gdd_dictionary_supabase import (
    upsert_component, insert_aliases, insert_references, delete_references_by_doc_id
)

logger = logging.getLogger(__name__)

def build_dictionary_for_doc(doc_id: str) -> Dict[str, Any]:
    """
    Orchestrates:
    - Load all chunks for one doc
    - Extract components per chunk (Vietnamese-only)
    - Normalize & deduplicate by component_key
    - Store in Supabase (components, aliases, references)
    """
    # Load chunks (no section filter; let LLM pick)
    chunks = load_gdd_chunks_from_supabase([doc_id])
    if not chunks:
        return {"status": "error", "message": f"No chunks found for doc_id={doc_id}"}
    logger.info(f"[Dictionary] Loaded {len(chunks)} chunks for {doc_id}")

    # Clean previous references for this doc (eventual consistency v1)  
    delete_references_by_doc_id(doc_id)

    # Accumulator by key
    by_key: Dict[str, Dict[str, Any]] = {}

    for ch in chunks:
        comps = extract_components_from_chunk(ch.content, ch.doc_id, section_path="")
        for raw in comps:
            norm = normalize_component(raw)
            key = norm["component_key"]
            acc = by_key.setdefault(key, {"display_name_vi": norm["display_name_vi"], "aliases_vi": set(), "evidence": []})
            for a in norm["aliases_vi"]:
                acc["aliases_vi"].add(a)
            acc["evidence"].extend(norm["evidence"])

    # Persist
    total_components = 0
    total_refs = 0
    for key, val in by_key.items():
        upsert_component(key, val["display_name_vi"], list(val["aliases_vi"]))
        total_components += 1
        if val["aliases_vi"]:
            insert_aliases(key, [{"alias_vi": a, "source": "llm"} for a in val["aliases_vi"]]) 
        if val["evidence"]:
            total_refs += insert_references(key, val["evidence"])

    return {
        "status": "success",
        "doc_id": doc_id,
        "components": total_components,
        "references": total_refs
    }
