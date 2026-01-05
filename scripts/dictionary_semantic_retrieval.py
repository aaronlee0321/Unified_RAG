
# scripts/dictionary_semantic_retrieval.py
import sys
from pathlib import Path
import argparse
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.dictionary_retrieval import dictionary_semantic_retrieval

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--q", required=True, help="Natural query (EN or VI)")
    ap.add_argument("--doc_id", help="Restrict output to this document (optional)")
    args = ap.parse_args()

    result = dictionary_semantic_retrieval(args.q, restrict_doc_id=args.doc_id)

    # Pretty print: component -> document -> section
    if result.get("status") != "success":
        print(result)
        return

    print(f"\n[Normalized VI] {result['normalized_query_vi']}")
    print(f"[Intent terms] {result['intent_terms']}")
    print(f"[Seeds] {result['seeds']}\n")

    for key, comp in result["results"].items():
        print(f"== {key} :: {comp['component']} ==")
        for group in comp["references"]:
            doc = group.get("document", "")
            sec = group.get("section", "")
            evidence = group.get("evidence", "")
            print(f"- [{doc}] {sec} :: {evidence}")
            # Show chunk ids only (content is large)
            for ch in group.get("chunks", []):
                print(f"  • chunk_id={ch['chunk_id']} section={ch['section_path']}")
        print()

if __name__ == "__main__":
    main()
