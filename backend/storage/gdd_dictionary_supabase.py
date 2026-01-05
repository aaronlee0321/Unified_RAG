
# backend/storage/gdd_dictionary_supabase.py
"""
Supabase storage adapter for the Semantic Dictionary.
Responsibilities:
- upsert components
- insert aliases
- insert references
- delete references by doc_id
- list/debug
"""
import sys
from typing import List, Dict, Optional, Any

# reuse existing supabase client pattern from your repo
# (get_supabase_client, upsert, batching, service key usage etc.)
# See backend/storage/supabase_client.py in your codebase.  [2](https://unisydneyedu-my.sharepoint.com/personal/alee0103_uni_sydney_edu_au/Documents/Microsoft%20Copilot%20Chat%20Files/repomix-output-aaronlee0321-Unified_RAG.git.xml)
from backend.storage.supabase_client import get_supabase_client

def upsert_component(component_key: str, display_name_vi: str, aliases_vi: Optional[List[str]] = None) -> Dict[str, Any]:
    client = get_supabase_client(use_service_key=True)
    data = {
        "component_key": component_key,
        "display_name_vi": display_name_vi,
        "aliases_vi": aliases_vi or []
    }
    res = client.table("dictionary_components").upsert(data, on_conflict="component_key").execute()
    return res.data[0] if res.data else {}

def insert_aliases(component_key: str, aliases: List[Dict[str, str]]) -> int:
    """
    aliases: [{ "alias_vi": "...", "source": "llm|human" }]
    """
    if not aliases:
        return 0
    client = get_supabase_client(use_service_key=True)
    payload = [{"component_key": component_key, **a} for a in aliases]
    # batch insert
    res = client.table("dictionary_aliases").insert(payload).execute()
    return len(res.data or [])

def insert_references(component_key: str, refs: List[Dict[str, Any]]) -> int:
    """
    refs: [{
      "doc_id": "...",
      "section_path": "...",
      "evidence_text_vi": "...",
      "source_language": "vi|en",
      "confidence_score": 0.0
    }]
    """
    if not refs:
        return 0
    client = get_supabase_client(use_service_key=True)
    payload = [{"component_key": component_key, **r} for r in refs]
    # upsert not needed; references are append-only v1
    # insert in batches of 100 like your existing pattern  [2](https://unisydneyedu-my.sharepoint.com/personal/alee0103_uni_sydney_edu_au/Documents/Microsoft%20Copilot%20Chat%20Files/repomix-output-aaronlee0321-Unified_RAG.git.xml)
    total = 0
    batch_size = 100
    for i in range(0, len(payload), batch_size):
        res = client.table("dictionary_references").insert(payload[i:i+batch_size]).execute()
        total += len(res.data or [])
    return total

def delete_references_by_doc_id(doc_id: str) -> bool:
    client = get_supabase_client(use_service_key=True)
    client.table("dictionary_references").delete().eq("doc_id", doc_id).execute()
    return True

def list_components(limit: int = 100) -> List[Dict[str, Any]]:
    client = get_supabase_client()
    res = client.table("dictionary_components").select("*").limit(limit).execute()
    return res.data or []

def list_references(component_key: str, limit: int = 100) -> List[Dict[str, Any]]:
    client = get_supabase_client()
    res = client.table("dictionary_references").select("*") \
        .eq("component_key", component_key).limit(limit).execute()
    return res.data or []
