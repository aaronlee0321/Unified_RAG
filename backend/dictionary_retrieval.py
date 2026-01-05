
# backend/dictionary_retrieval.py
"""
Dictionary-first semantic retrieval over GDD documents (deterministic, NO top-K).
Phases:
  1) Query Normalization (detect -> translate EN->VI, preserve technical terms)
  2) Intent Expansion (LLM; terms only; NOT dictionary keys)
  3) Seed Component Detection (embedding + alias/fuzzy + cross-encoder rerank)
  4) Deterministic Dictionary Expansion (collect ALL references)
  5) Semantic Inclusion (threshold-based, NOT top-K)
  6) Grouping & Output (component, document, section, evidence, chunks)

Notes:
- Internal canonical language is Vietnamese.
- Ranking is allowed only in Phase 3 (seed detection) and for display ordering.
- Final result set contains ALL relevant chunks (no top-K truncation).
- Logging is enabled for phase-by-phase progress.

This module expects your existing repo structure:
- backend.code_service.client (Qwen/OpenAI chat client)
- backend.gdd_hyde (translation & HYDE utilities)
- backend.storage.* (Supabase adapters)
- gdd_rag_backbone.* (LLM providers, embeddings, optional cross-encoder & vector utilities)
"""

import sys
import logging
from typing import List, Dict, Any, Tuple, Optional, Set

# --- Path bootstrap (must be BEFORE any backend.* imports) ---
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# --- Repo imports (now safe because path is set) ---
from backend.code_service import client  # Chat LLM client (Qwen/OpenAI)
from backend.storage.supabase_client import get_supabase_client
from backend.storage.gdd_dictionary_supabase import list_references, list_components, upsert_component  # noqa (for parity; only list_references used)
from backend.storage.gdd_supabase_storage import (
    load_gdd_chunks_from_supabase,
    load_gdd_vectors_from_supabase,
)
from backend.gdd_hyde import translate_query_if_needed, gdd_hyde_v1

from gdd_rag_backbone.llm_providers import QwenProvider, make_embedding_func
from gdd_rag_backbone.rag_backend.chunk_qa import (
    _normalize_vector,
    _rerank_with_cross_encoder,
)

# ----------------------------
# Logger setup (console handler)
# ----------------------------
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
if not logger.handlers:
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    fmt = logging.Formatter("[%(levelname)s] %(message)s")
    ch.setFormatter(fmt)
    logger.addHandler(ch)

# ----------------------------
# CONFIG (tune these centrally)
# ----------------------------
USE_CROSS_ENCODER = True  # can be toggled by CLI wrapper
DEBUG_LOG = False

HIGH_THRESHOLD = 0.75       # Phase 3 seed inclusion threshold
INCLUSION_THRESHOLD = 0.45  # Phase 5 semantic inclusion threshold
MAX_REF_PER_SEED = 1000     # practical cap per seed; NO top-K in final results
MAX_CHUNKS_PER_DOC_LOAD = 5000  # guard (not used directly in this module)

# ----------------------------
# Phase 2: Intent Expansion LLM prompt (VN-only terms)
# ----------------------------
INTENT_SYSTEM_PROMPT = """
Bạn là bộ mở rộng ý định cho TRUY VẤN thiết kế game.
Chỉ trả về JSON tiếng Việt với các "intent_terms" (từ/cụm liên quan),
không phải là khóa dictionary, không phải tên component key.

YÊU CẦU:
- Tất cả bằng tiếng Việt.
- Chỉ trả về những cụm từ liên quan, không bịa đặt hệ thống.

ĐỊNH DẠNG JSON:
{
  "intent_terms": ["...", "..."]
}
"""

def expand_intent_terms_vi(client_llm, query_vi: str) -> List[str]:
    """Phase 2: LLM expansion (text only, NOT keys) -> intent_terms (VI)."""
    import time, json
    t0 = time.time()
    messages = [
        {"role": "system", "content": INTENT_SYSTEM_PROMPT},
        {"role": "user", "content": f"TRUY VẤN: {query_vi}\nHãy trả về JSON intent_terms."}
    ]
    logger.info("[Phase 2] Calling LLM for intent expansion...")
    # Some SDKs may not support timeout; keep max_tokens small to avoid stalls
    resp = client_llm.chat.completions.create(
        model="qwen-plus",
        messages=messages,
        temperature=0,
        max_tokens=256,   # short JSON
        # timeout=30      # add if your SDK supports it
    )
    text = resp.choices[0].message.content
    logger.info(f"[Phase 2] LLM returned in {time.time()-t0:.1f}s")
    try:
        start = text.find("{"); end = text.rfind("}")
        data = json.loads(text[start:end+1]) if start != -1 and end != -1 else {"intent_terms": []}
        terms = [t.strip() for t in data.get("intent_terms", []) if t and t.strip()]
        logger.info(f"[Phase 2] intent_terms: {terms}")
        return terms
    except Exception as e:
        logger.warning(f"[Phase 2] Failed to parse intent JSON: {e}")
        return []

# ----------------------------
# Helpers: component embeddings & alias matching
# ----------------------------
def _ensure_component_embedding(client_sb, provider, comp: Dict[str, Any]) -> List[float]:
    """
    If embedding missing on dictionary_components, compute and store it safely.
    - UPDATE if the row exists (no NULL issues).
    - INSERT only with a FULL row (component_key, display_name_vi, aliases_vi, embedding).
    """
    emb = comp.get("embedding")
    if emb:
        try:
            return [float(x) for x in emb]
        except Exception:
            pass  # fall through to recompute if parsing failed

    text = (comp.get("display_name_vi") or comp.get("component_key") or "") + " " + " ".join(comp.get("aliases_vi") or [])
    embedding_func = make_embedding_func(provider)
    vec = embedding_func([text])[0]

    key = comp.get("component_key")
    display = comp.get("display_name_vi") or key  # never NULL
    aliases = comp.get("aliases_vi") or []

    try:
        # UPDATE first
        upd = client_sb.table("dictionary_components").update({"embedding": vec}).eq("component_key", key).execute()
        if upd.data:
            return vec
        # INSERT full row if missing
        client_sb.table("dictionary_components").insert({
            "component_key": key,
            "display_name_vi": display,
            "aliases_vi": aliases,
            "embedding": vec
        }).execute()
        return vec
    except Exception as e:
        logger.warning(f"[Embedding] Safe write failed for {key}: {e}")
        return vec

def _alias_match_score(q_vi: str, comp: Dict[str, Any]) -> float:
    """Lexical alias/name match score (fuzzy, simple)."""
    import re
    ql = q_vi.lower()
    name = (comp.get("display_name_vi", "") or "").lower()
    aliases = [str(a).lower() for a in (comp.get("aliases_vi") or [])]
    score = 0.0
    if ql == name or ql in aliases:
        score = 0.95
    elif ql in name or name in ql:
        score = 0.8
    elif any(ql in a or a in ql for a in aliases):
        score = 0.75
    # boost for exact alias token matches
    words = re.findall(r"\w+", ql)
    if words and any(w in a for w in words for a in aliases):
        score = max(score, 0.8)
    return score

def _embedding_match_score(q_vec: List[float], comp_vec: List[float]) -> float:
    """Cosine-like similarity (dot product on normalized vectors)."""
    try:
        # Prefer pure-Python for portability if numpy missing
        return sum(float(a) * float(b) for a, b in zip(q_vec, comp_vec))
    except Exception:
        # Fallback numpy if available
        try:
            import numpy as np
            return float(np.dot(np.array(q_vec, dtype=float), np.array(comp_vec, dtype=float)))
        except Exception:
            return 0.0

# ----------------------------
# Phase 3: Seed Component Detection (ranking allowed here only)
# ----------------------------
def detect_seed_components(client_sb, provider, query_vi: str, intent_terms: List[str]) -> List[Dict[str, Any]]:
    """Returns a small seed set of components (dict rows) passing HIGH_THRESHOLD or exact alias."""
    emb_func = make_embedding_func(provider)
    q_vec = emb_func([query_vi])[0]
    try:
        q_vec = _normalize_vector(q_vec)
    except Exception:
        pass

    comps = client_sb.table("dictionary_components").select("*").execute().data or []
    scored: List[Tuple[float, Dict[str, Any]]] = []

    for c in comps:
        if not c.get("display_name_vi"):
            c["display_name_vi"] = c.get("component_key", "unnamed_component")

        comp_vec = _ensure_component_embedding(client_sb, provider, c)
        try:
            comp_vec = _normalize_vector(comp_vec)
        except Exception:
            pass

        s_emb = _embedding_match_score(q_vec, comp_vec)
        s_alias = _alias_match_score(query_vi, c)
        s_intent = max(_alias_match_score(t, c) for t in intent_terms) if intent_terms else 0.0
        raw_score = max(s_emb, s_alias, s_intent)
        scored.append((raw_score, c))

    # Optional cross-encoder rerank using short evidence snippets
    pairs = []
    for _, c in scored:
        refs = client_sb.table("dictionary_references").select("evidence_text_vi").eq("component_key", c["component_key"]).limit(3).execute().data or []
        evid_text = " ".join(r.get("evidence_text_vi", "") for r in refs) or c.get("display_name_vi", "")
        pairs.append({"content": evid_text})

    if USE_CROSS_ENCODER:
        logger.info("[Phase 3] Cross-encoder reranking...")
        try:
            reranked = _rerank_with_cross_encoder(query_vi, pairs, provider=provider, top_n=len(pairs))
            ce_map = {i: score for i, (score, _) in enumerate(reranked)}
            blended = []
            for i, (raw, c) in enumerate(scored):
                blended.append((max(raw, ce_map.get(i, 0.0))), c)
            # Sort by blended score desc (ranking still only for seeds)
            scored = sorted(blended, key=lambda x: x[0], reverse=True)
            logger.info("[Phase 3] Cross-encoder reranking complete")
        except Exception as e:
            logger.info(f"[Phase 3] Cross-encoder rerank skipped: {e}")

    # Select seeds deterministically (threshold or exact alias)
    seeds: List[Dict[str, Any]] = []
    for s, c in scored:
        if s >= HIGH_THRESHOLD:
            seeds.append(c)
        else:
            if _alias_match_score(query_vi, c) >= 0.95:
                seeds.append(c)

    # Small cap to avoid runaway (not a top-K truncation of final results)
    seeds = seeds[:50]
    logger.info(f"[Phase 3] Seeds selected: {len(seeds)} (threshold={HIGH_THRESHOLD})")
    for c in seeds:
        logger.info(f"  - {c['component_key']} :: {c.get('display_name_vi','')}")
    return seeds

# ----------------------------
# Phase 4: Deterministic Dictionary Expansion (NO ranking)
# ----------------------------
def expand_dictionary(client_sb, seeds: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    For each seed:
      - Lookup ALL references (doc_id, section_path, evidence_text_vi)
      - Deterministically collect target (doc_id, section_path) pairs.
    """
    expansion: Dict[str, Dict[str, Any]] = {}  # component_key -> {...}
    for c in seeds:
        key = c["component_key"]
        display = c.get("display_name_vi", key)
        refs = client_sb.table("dictionary_references").select("*").eq("component_key", key).limit(MAX_REF_PER_SEED).execute().data or []
        targets: Set[Tuple[str, str]] = set()
        for r in refs:
            doc_id = r.get("doc_id", "")
            sec = r.get("section_path", "") or ""
            targets.add((doc_id, sec))
        expansion[key] = {
            "display_name_vi": display,
            "references": refs,
            "targets": targets
        }
    total_refs = sum(len(v["references"]) for v in expansion.values())
    total_targets = sum(len(v["targets"]) for v in expansion.values())
    logger.info(f"[Phase 4] Expansion: components={len(expansion)}, references={total_refs}, targets={total_targets}")
    return expansion

# ----------------------------
# Phase 5: Semantic Inclusion (threshold-based, NOT top-K)
# ----------------------------
def include_chunks_for_targets(provider, expansion: Dict[str, Dict[str, Any]], intent_terms: List[str]) -> Dict[str, Any]:
    """
    Load ALL chunks in referenced docs; include chunks that satisfy ANY rule:
      - chunk belongs to a referenced section_path
      - chunk content contains any dictionary alias
      - embedding similarity >= INCLUSION_THRESHOLD (query/intent vs precomputed chunk vector)
      - chunk shares the same section_path
      - chunk is part of a table under the same header (content_type='table')
    Returns: component_key -> {component, references:[ {document, section, evidence, chunks:[...] } ] }
    """
    provider_obj = QwenProvider()
    emb_func = make_embedding_func(provider_obj)
    results: Dict[str, Any] = {}

    for key, info in expansion.items():
        display = info["display_name_vi"]
        targets = list(info["targets"])
        refs = info["references"]
        if not targets:
            results[key] = {"component": display, "references": []}
            continue

        # group targets by doc_id
        by_doc: Dict[str, Set[str]] = {}
        for doc_id, sec in targets:
            by_doc.setdefault(doc_id, set()).add(sec)

        component_groups: List[Dict[str, Any]] = []

        for doc_id, sec_set in by_doc.items():
            # Load ALL chunks and vectors for this doc_id
            chunks = load_gdd_chunks_from_supabase([doc_id])
            doc_vectors = load_gdd_vectors_from_supabase([doc_id], normalize=True)  # {chunk_id: vector}
            if not chunks:
                continue

            accepted_sections = {s.strip() for s in sec_set if s}

            client_sb = get_supabase_client()
            comp_row = client_sb.table("dictionary_components").select("aliases_vi").eq("component_key", key).limit(1).execute().data
            aliases = (comp_row[0].get("aliases_vi") if comp_row else []) or []
            aliases_lower = [str(a).lower() for a in aliases]

            intent_bag = " ".join(intent_terms) if intent_terms else display
            q_vec = emb_func([intent_bag])[0]
            try:
                q_vec = _normalize_vector(q_vec)
            except Exception:
                pass

            included: List[Dict[str, Any]] = []
            for ch in chunks:
                content = ch.content or ""

                # fetch section_path & content_type for chunk
                try:
                    meta = client_sb.table("gdd_chunks").select("section_path, content_type").eq("chunk_id", ch.chunk_id).limit(1).execute().data or []
                    section_path = (meta[0].get("section_path") if meta else "") or ""./
                    content_type = (meta[0].get("content_type") if meta else "") or ""
                except Exception:
                    section_path = ""
                    content_type = ""

                belongs_section = (section_path.strip() in accepted_sections) if section_path else False
                contains_alias = any(a in content.lower() for a in aliases_lower) if aliases_lower else False
                same_section = belongs_section
                table_under_header = (content_type.lower() == "table" and belongs_section)

                sim_ok = False
                vec = doc_vectors.get(ch.chunk_id)
                if vec:
                    sim = _embedding_match_score(q_vec, vec)
                    sim_ok = sim >= INCLUSION_THRESHOLD

                if belongs_section or contains_alias or same_section or table_under_header or sim_ok:
                    included.append({
                        "chunk_id": ch.chunk_id,
                        "doc_id": doc_id,
                        "section_path": section_path,
                        "content": content
                    })

            # group by section with evidence
            ref_for_doc = [r for r in refs if r.get("doc_id") == doc_id]
            groups_by_section: Dict[str, Dict[str, Any]] = {}
            for r in ref_for_doc:
                sec = r.get("section_path", "") or "Unknown"
                groups_by_section.setdefault(sec, {"document": doc_id, "section": sec, "evidence": r.get("evidence_text_vi",""), "chunks": []})

            for inc in included:
                sec = inc.get("section_path") or "Unknown"
                groups_by_section.setdefault(sec, {"document": doc_id, "section": sec, "evidence": "", "chunks": []})
                groups_by_section[sec]["chunks"].append(inc)

            component_groups.extend(list(groups_by_section.values()))

        results[key] = {
            "component": display,
            "references": component_groups
        }

    total_groups = sum(len(v["references"]) for v in results.values())
    total_chunks = sum(sum(len(g["chunks"]) for g in v["references"]) for v in results.values())
    logger.info(f"[Phase 5] Final groups={total_groups}, final chunks={total_chunks}")
    return results

# ----------------------------
# Entry point: run all phases
# ----------------------------
def dictionary_semantic_retrieval(query_text: str, restrict_doc_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Full pipeline:
      P1: normalize (to VI)
      P2: LLM expand (terms only)
      P3: seed detection (embedding+alias+cross-encoder)
      P4: dict expansion (ALL references)
      P5: inclusion (threshold rules, NO top-K)
      P6: grouping (component/document/section)
    """
    client_sb = get_supabase_client()
    provider = QwenProvider()

    # Phase 1: Normalize
    query_vi, detected_lang, _ = translate_query_if_needed(query_text)
    logger.info(f"[Phase 1] detected_lang={detected_lang}, query_vi={query_vi}")

    # Phase 2: Intent expansion (terms only; NOT keys)
    intent_terms = expand_intent_terms_vi(client_llm=client, query_vi=query_vi)

    # Phase 3: Seeds (ranking allowed here only)
    seeds = detect_seed_components(client_sb, provider, query_vi, intent_terms)
    if not seeds:
        # Fallback: return closest candidates (ask user to confirm before expanding)
        comps = client_sb.table("dictionary_components").select("*").execute().data or []
        return {
            "status": "no_seeds",
            "message": "Không tìm thấy seed đủ mạnh. Vui lòng xác nhận thành phần gần nhất.",
            "closest_components": [c.get("display_name_vi", c.get("component_key","")) for c in comps[:10]]
        }

    # Phase 4: Expansion (deterministic, no ranking)
    expansion = expand_dictionary(client_sb, seeds)

    # Phase 5: Inclusion
    results = include_chunks_for_targets(provider, expansion, intent_terms)

    # Phase 6: Optional doc filter at UX layer (deterministic post-filter; no ranking change)
    if restrict_doc_id:
        for key in list(results.keys()):
            refs = results[key]["references"]
            results[key]["references"] = [r for r in refs if r.get("document") == restrict_doc_id]

    return {
        "status": "success",
        "normalized_query_vi": query_vi,
        "intent_terms": intent_terms,
        "seeds": [s.get("display_name_vi", s.get("component_key","")) for s in seeds],
        "results": results
    }
