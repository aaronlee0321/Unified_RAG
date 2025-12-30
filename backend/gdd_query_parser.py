"""
GDD Query Parser - Section Targeting
======================================
Parses @Result Screen style queries to extract section/document filters.
"""

import re
from typing import Dict, Optional, Tuple, List
from pathlib import Path

# Common English to Vietnamese section name mappings
SECTION_NAME_MAPPINGS = {
    "components": "Thànhphần",
    "component": "Thànhphần",
    "thành phần": "Thànhphần",
    "interaction": "Tươngtác",
    "interactions": "Tươngtác",
    "tương tác": "Tươngtác",
    "overview": "Tổngquan",
    "tổng quan": "Tổngquan",
    "purpose": "Mụcđích",
    "mục đích": "Mụcđích",
    "goal": "Mụctiêu",
    "mục tiêu": "Mụctiêu",
    "document goal": "Mụctiêutàiliệu",
    "mục tiêu tài liệu": "Mụctiêutàiliệu",
}


def normalize_doc_id_for_matching(doc_reference: str) -> str:
    """
    Normalize a document reference (filename or doc_id) to match the format used by generate_doc_id().
    
    This ensures that queries like "@[Asset,_UI]_[Tank_War]_In-game_GUI_Design.md" 
    or "@Asset_UI_Tank_War_Tank_Selection_Screen_Design_(Cơ_chế_chọn_tank)"
    correctly match doc_id in Supabase.
    
    Args:
        doc_reference: Document reference from query (e.g., "[Asset,_UI]_[Tank_War]_In-game_GUI_Design.md")
    
    Returns:
        Normalized doc_id for matching (e.g., "asset_ui_tank_war_in_game_gui_design")
    """
    # Remove .md extension if present
    if doc_reference.endswith('.md'):
        doc_reference = doc_reference[:-3]
    
    # Apply same normalization as generate_doc_id()
    # Keep parentheses and their contents for doc_ids like Asset_UI_Tank_War_Tank_Selection_Screen_Design_(Cơ_chế_chọn_tank)
    doc_id = doc_reference.replace(" ", "_").replace("[", "").replace("]", "")
    doc_id = doc_id.replace("-", "_").replace(",", "_")
    
    # Remove double underscores
    while "__" in doc_id:
        doc_id = doc_id.replace("__", "_")
    
    # Strip leading/trailing underscores and convert to lowercase for matching
    # Note: We keep parentheses as-is since they're part of the actual doc_id
    return doc_id.strip("_").lower()


def parse_section_targets(query: str) -> Tuple[str, Dict]:
    """
    Parse section targeting syntax from query.
    
    Examples:
    - "@Result Screen" -> filters by section_path containing "Result Screen"
    - "@Garage UI" -> filters by section_path containing "Garage UI"
    - "@[Asset][UI Tank War]" -> filters by doc_id or section_path
    
    Args:
        query: User query string
    
    Returns:
        (cleaned_query, filters_dict)
        filters_dict contains:
        - section_path_filter: Optional section path to filter by
        - doc_id_filter: Optional doc_id to filter by
        - content_type_filter: Optional content type to filter by
    """
    # Pattern to match @... tokens
    # For sections: @6. Notes, @4. Thànhphần, @Notes, @Result Screen
    # For doc_ids: @[Asset,_UI]_[Tank_War]_filename.md or @Asset_UI_Tank_War_Tank_Selection_Screen_Design_(Cơ_chế_chọn_tank)
    
    # IMPORTANT: There's always a space after @<section> or @<file> before the question
    # Format: "@6. Notes extract this" or "@Thànhphần what are the components"
    # Strategy: Match @ followed by text, stopping at the space before the question or next @
    
    # Pattern explanation:
    # @                     - literal @
    # (                     - start capture group
    #   \d+\.\s*\S+         - number + dot + space + word (e.g., "6. Notes")
    #   |                   - OR
    #   [^\s@]+             - one or more non-whitespace, non-@ characters (handles parentheses, underscores, etc.)
    #   (?:\s+[^\s@]+)?     - optionally followed by space and more non-whitespace, non-@ characters (for "Result Screen")
    # )                     - end capture group
    # (?=\s|@|$)            - lookahead: followed by space, @, or end of string
    
    # This pattern handles:
    # - @6. Notes (numbered section)
    # - @Result Screen (section with space)
    # - @Asset_UI_Tank_War_Tank_Selection_Screen_Design_(Cơ_chế_chọn_tank) (doc_id with parentheses)
    # - @[Asset,_UI]_[Tank_War]_filename.md (doc_id with brackets)
    
    pattern = r'@(\d+\.\s*[^\s@]+|[^\s@]+(?:\s+[^\s@]+)?)(?=\s|@|$)'
    matches = re.findall(pattern, query)
    
    if not matches:
        return query, {}
    
    filters = {}
    cleaned_query = query
    
    for match in matches:
        # Remove @match from query (handle multiple @ tokens correctly)
        # Replace only the first occurrence to avoid removing later @ tokens
        cleaned_query = cleaned_query.replace(f'@{match}', '', 1).strip()
        
        # Try to match to section_path or doc_id
        # NOTE: Content type filtering removed - @ syntax now only supports sections
        
        # Check if it looks like a doc_id pattern (contains brackets, multiple underscores, parentheses, or .md)
        # Be more strict: require brackets OR multiple underscores OR parentheses OR .md extension
        is_doc_id = (
            '[' in match or  # Brackets indicate doc_id like [Asset,_UI]
            match.count('_') >= 2 or  # Multiple underscores indicate doc_id
            '(' in match or  # Parentheses indicate doc_id like Asset_UI_Tank_War_Tank_Selection_Screen_Design_(Cơ_chế_chọn_tank)
            '.md' in match.lower()  # File extension
        )
        
        if is_doc_id:
            # Likely a doc_id or document reference
            # Normalize using the same logic as generate_doc_id() for accurate matching
            normalized = normalize_doc_id_for_matching(match)
            filters['doc_id_filter'] = normalized
        else:
            # Likely a section name (e.g., "Result Screen", "Garage UI", "Thànhphần", "4. Thànhphần", "6. Notes")
            # This will be used to filter by section_path or numbered_header
            filters['section_path_filter'] = match
    
    # Clean up extra spaces
    cleaned_query = ' '.join(cleaned_query.split())
    
    return cleaned_query, filters


def extract_numbered_section_from_query(query: str) -> Optional[str]:
    """
    Extract numbered section reference from query.
    
    Examples:
    - "section 4.1" -> "4.1"
    - "4. GiaodiệnTankGarage" -> "4. GiaodiệnTankGarage"
    - "7.3 Tankhạngnặng" -> "7.3 Tankhạngnặng"
    
    Args:
        query: User query string
    
    Returns:
        Numbered section string if found, None otherwise
    """
    # Pattern: number followed by dot and optional space, then text
    patterns = [
        r'(\d+\.\d+[\.\d]*\s*[^\s]+)',  # 4.1 Text, 7.3 Text
        r'(\d+\.\s*[^\s]+)',  # 4. Text, 1. Text
        r'section\s+(\d+\.\d+[\.\d]*)',  # section 4.1
        r'section\s+(\d+)',  # section 4
    ]
    
    for pattern in patterns:
        match = re.search(pattern, query, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    
    return None


def map_english_to_vietnamese_section(query: str) -> Optional[str]:
    """
    Map common English section terms to Vietnamese section names.
    This helps when users query in English but documents use Vietnamese section names.
    
    Examples:
    - "what are the components" -> "Thànhphần"
    - "show me interactions" -> "Tươngtác"
    - "components" -> "Thànhphần"
    
    Note: This does NOT translate the entire query, only maps section names for filtering.
    The actual search query remains in the original language for embedding.
    
    Args:
        query: User query string
    
    Returns:
        Vietnamese section name if found, None otherwise
    """
    query_lower = query.lower()
    
    # Check for exact matches or partial matches
    for english_term, vietnamese_name in SECTION_NAME_MAPPINGS.items():
        if english_term in query_lower:
            return vietnamese_name
    
    return None
