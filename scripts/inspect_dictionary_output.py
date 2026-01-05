
# scripts/inspect_dictionary_output.py
import sys
from pathlib import Path
import argparse

# --- Bootstrap: ensure project root is importable ---
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
# ----------------------------------------------------

from backend.storage.supabase_client import get_supabase_client

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--doc_id", help="Filter to this doc_id (strongly recommended)")
    ap.add_argument("--limit", type=int, default=500, help="max references to fetch")
    args = ap.parse_args()

    client = get_supabase_client()

    if args.doc_id:
        # Pull references for this doc_id FIRST (always shows matches)
        refs_res = client.table("dictionary_references") \
                         .select("*") \
                         .eq("doc_id", args.doc_id) \
                         .limit(args.limit) \
                         .execute()
        refs = refs_res.data or []
        if not refs:
            print(f"(no references found for doc_id='{args.doc_id}')")
            return

        # Group by component_key
        by_key = {}
        for r in refs:
            key = r.get("component_key")
            by_key.setdefault(key, []).append(r)

        # Fetch component names in one shot
        comps_res = client.table("dictionary_components") \
                          .select("component_key, display_name_vi") \
                          .execute()
        name_map = {c["component_key"]: c.get("display_name_vi", c["component_key"])
                    for c in (comps_res.data or [])}

        # Print
        for key, rows in sorted(by_key.items(), key=lambda kv: kv[0]):
            print(f"\n== {key} :: {name_map.get(key, key)} ==")
            for r in rows:
                sec = r.get("section_path", "") or ""
                ev  = r.get("evidence_text_vi", "") or ""
                cs  = r.get("confidence_score", 0.0)
                print(f"- {sec} :: {ev} (score={cs:.2f})")

    else:
        # Fallback: show a small global sample (without doc filter)
        comps_res = client.table("dictionary_components").select("*").limit(100).execute()
        comps = comps_res.data or []
        if not comps:
            print("(no components found)")
            return

        # For each component, print up to 10 refs (unfiltered)
        for c in comps:
            key = c.get("component_key", "")
            name = c.get("display_name_vi", key)
            refs_res = client.table("dictionary_references").select("*") \
                             .eq("component_key", key).limit(10).execute()
            refs = refs_res.data or []
            print(f"\n== {key} :: {name} ==")
            if not refs:
                print("(no references)")
                continue
            for r in refs:
                doc = r.get("doc_id", "")
                sec = r.get("section_path", "") or ""
                ev  = r.get("evidence_text_vi", "") or ""
                cs  = r.get("confidence_score", 0.0)
                print(f"- [{doc}] {sec} :: {ev} (score={cs:.2f})")

if __name__ == "__main__":
    main()
