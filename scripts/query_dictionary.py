
# scripts/query_dictionary.py
"""
Query the Semantic Dictionary from CLI and return the best-matching component + references.

Usage:
  python -m scripts.query_dictionary --q "nút kỹ năng" --limit 10
  python -m scripts.query_dictionary --key skill_button --limit 5

Search strategy:
- If --key is provided: exact lookup by component_key.
- Else: fuzzy search across display_name_vi and aliases_vi (ILIKE).
- Simple scoring: exact match > alias match > display_name partial.
"""

import sys
from pathlib import Path
import argparse
import json

# --- Bootstrap: ensure project root is importable ---
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
# ----------------------------------------------------

from backend.storage.supabase_client import get_supabase_client
from backend.storage.gdd_dictionary_supabase import list_references

def _score_match(q: str, display_name_vi: str, aliases_vi: list, component_key: str) -> float:
    """
    Very lightweight scorer:
    - exact component_key match -> 1.0
    - exact alias match -> 0.95
    - exact display_name_vi match -> 0.9
    - partial alias -> 0.75
    - partial display_name_vi -> 0.7
    """
    ql = (q or "").strip().lower()
    keyl = (component_key or "").lower()
    namel = (display_name_vi or "").strip().lower()
    aliasesl = [str(a).lower() for a in (aliases_vi or [])]

    if ql == keyl:
        return 1.0
    if ql in aliasesl:
        return 0.95
    if ql == namel:
        return 0.9
    if any(ql in a or a in ql for a in aliasesl):
        return 0.75
    if ql in namel or namel in ql:
        return 0.7
    return 0.0

def _load_candidates(client, q: str):
    """
    Load candidate components using ILIKE across display_name_vi and aliases_vi.
    We do 3 queries:
      1) exact component_key (if q is snake_case)
      2) display_name_vi ILIKE '%q%'
      3) aliases_vi contains q (array contains via jsonb like)
    """
    # 1) Try component_key exact
    comp_key_candidates = []
    try:
        res_key = client.table("dictionary_components").select("*").eq("component_key", q).execute()
        comp_key_candidates = res_key.data or []
    except Exception:
        pass

    # 2) display_name_vi ILIKE
    name_candidates = []
    try:
        res_name = client.table("dictionary_components").select("*").ilike("display_name_vi", f"%{q}%").execute()
        name_candidates = res_name.data or []
    except Exception:
        pass

    # 3) aliases_vi contains q (two ways: jsonb @> and ILIKE on aliases textified)
    alias_candidates = []
    try:
        # First try exact jsonb containment
        res_alias_exact = client.table("dictionary_components").select("*") \
            .filter("aliases_vi", "cs", json.dumps([q])) \
            .execute()
        alias_candidates = res_alias_exact.data or []
    except Exception:
        alias_candidates = []

    # Fallback for aliases: pull all and filter client-side (safe for small dictionaries)
    if not alias_candidates:
        try:
            res_all = client.table("dictionary_components").select("component_key, display_name_vi, aliases_vi").execute()
            alias_candidates = []
            for row in res_all.data or []:
                aliases = row.get("aliases_vi") or []
                if any((q.lower() in str(a).lower()) or (str(a).lower() in q.lower()) for a in aliases):
                    alias_candidates.append(row)
        except Exception:
            pass

    # Merge & deduplicate by component_key
    merged = {}
    for row in comp_key_candidates + name_candidates + alias_candidates:
        key = row.get("component_key")
        if key and key not in merged:
            merged[key] = row
    return list(merged.values())

def query_dictionary(q: str = None, key: str = None, limit: int = 10):
    client = get_supabase_client()

    # Case 1: direct key lookup
    if key:
        comp_res = client.table("dictionary_components").select("*").eq("component_key", key).limit(1).execute()
        if not comp_res.data:
            return {"status": "not_found", "message": f"Component key '{key}' not found"}
        comp = comp_res.data[0]
        refs = list_references(key, limit=limit)
        return {
            "status": "success",
            "match_type": "key",
            "component": comp,
            "references": refs
        }

    # Case 2: query string lookup
    if not q or not q.strip():
        return {"status": "error", "message": "Provide --q or --key"}

    candidates = _load_candidates(client, q.strip())
    if not candidates:
        return {"status": "not_found", "message": f"No candidates for query '{q}'"}

    # Score and pick best
    scored = []
    for c in candidates:
        score = _score_match(q, c.get("display_name_vi", ""), c.get("aliases_vi") or [], c.get("component_key", ""))
        scored.append((score, c))
    scored.sort(key=lambda x: x[0], reverse=True)
    best_score, best_comp = scored[0]

    refs = list_references(best_comp.get("component_key"), limit=limit)
    return {
        "status": "success",
        "match_type": "query",
        "query": q,
        "score": best_score,
        "component": best_comp,
        "references": refs
    }

def _print_result(result: dict):
    status = result.get("status")
    if status != "success":
        print(result)
        return

    comp = result.get("component", {})
    key = comp.get("component_key", "")
    name = comp.get("display_name_vi", "")
    aliases = comp.get("aliases_vi") or []
    score = result.get("score")
    match_type = result.get("match_type")

    print(f"== {key} :: {name} ==")
    if match_type == "query":
        print(f"Matched by query with score={score:.2f}")
    print(f"aliases_vi: {aliases}")

    refs = result.get("references") or []
    if not refs:
        print("(no references found)")
        return
    for r in refs[:10]:
        doc = r.get("doc_id", "")
        sec = r.get("section_path", "") or ""
        ev  = r.get("evidence_text_vi", "") or ""
        cs  = r.get("confidence_score", 0.0)
        print(f"- [{doc}] {sec} :: {ev} (score={cs:.2f})")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--q", help="query string (Vietnamese or English)")
    ap.add_argument("--key", help="exact component_key (snake_case)")
    ap.add_argument("--limit", type=int, default=10, help="max references to return")
    args = ap.parse_args()

    result = query_dictionary(q=args.q, key=args.key, limit=args.limit)
    _print_result(result)

if __name__ == "__main__":
    main()
