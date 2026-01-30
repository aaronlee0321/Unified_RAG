"""
Extract all image URLs from keyword_chunks content for a given doc_id.

Uses regex to find markdown image syntax: ![](url) or ![alt](url)
(images are stored as full Supabase gdd_pdfs/.../images/... URLs in chunk content).

Usage (from project root with venv activated):
    python -m gdd_rag_backbone.scripts.extract_images_from_chunks Gamemode_Module_Tank_War_Battle_Royale_Mode_Chua_co_ten
    python -m gdd_rag_backbone.scripts.extract_images_from_chunks --doc-id Gamemode_Module_Tank_War_Battle_Royale_Mode_Chua_co_ten
"""

import argparse
import re
import sys
from pathlib import Path

# Add project root for imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Load .env (backend uses it)
try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass

# Markdown image: ![alt](url) — capture alt (optional) and url
IMAGE_PATTERN = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")


def extract_image_urls_from_text(content: str) -> list[tuple[str, str]]:
    """
    Extract (alt, url) pairs from markdown image syntax in content.
    Returns list of (alt_text, url).
    """
    if not content:
        return []
    return IMAGE_PATTERN.findall(content)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract all image URLs from keyword_chunks content for a doc_id."
    )
    parser.add_argument(
        "doc_id",
        nargs="?",
        default=None,
        help="Document ID (e.g. Gamemode_Module_Tank_War_Battle_Royale_Mode_Chua_co_ten)",
    )
    parser.add_argument(
        "--doc-id",
        dest="doc_id_flag",
        default=None,
        help="Document ID (alternative to positional)",
    )
    parser.add_argument(
        "--unique",
        action="store_true",
        help="Print each URL only once (dedupe)",
    )
    parser.add_argument(
        "-q", "--quiet",
        action="store_true",
        help="Print only URLs, one per line (no headers)",
    )
    args = parser.parse_args()

    doc_id = args.doc_id_flag or args.doc_id
    if not doc_id:
        parser.error("doc_id is required (positional or --doc-id)")

    try:
        from backend.storage.supabase_client import get_supabase_client
    except Exception as e:
        print(f"Error: Could not import Supabase client: {e}", file=sys.stderr)
        print("Ensure SUPABASE_URL and SUPABASE_KEY are set in .env", file=sys.stderr)
        sys.exit(1)

    client = get_supabase_client()
    result = client.table("keyword_chunks").select("chunk_id, section_heading, content").eq(
        "doc_id", doc_id
    ).order("chunk_index").execute()

    rows = result.data or []
    # (url, alt, section_heading, chunk_index)
    all_images: list[tuple[str, str, str, int]] = []

    for i, row in enumerate(rows):
        content = row.get("content") or ""
        section = (row.get("section_heading") or "").strip()
        chunk_id = row.get("chunk_id", "")
        for alt, url in extract_image_urls_from_text(content):
            url = url.strip()
            if url:
                all_images.append((url, alt, section, i))

    if args.unique:
        seen = set()
        unique_images = []
        for url, alt, section, idx in all_images:
            if url not in seen:
                seen.add(url)
                unique_images.append((url, alt, section, idx))
        all_images = unique_images

    if args.quiet:
        for url, _, _, _ in all_images:
            print(url)
        return

    print(f"# doc_id: {doc_id}")
    print(f"# chunks scanned: {len(rows)}")
    print(f"# images extracted: {len(all_images)}")
    if args.unique:
        print("# (unique URLs only)")
    print()

    for i, (url, alt, section, chunk_idx) in enumerate(all_images, 1):
        alt_part = f" alt={alt!r}" if alt else ""
        print(f"{i}. {url}{alt_part}")
        if section:
            print(f"   section: {section} (chunk_index ~{chunk_idx})")
        print()


if __name__ == "__main__":
    main()
