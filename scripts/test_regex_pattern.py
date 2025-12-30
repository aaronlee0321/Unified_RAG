"""
Test the regex pattern to see why NamingConventionScanner isn't being found.
"""

import re
from pathlib import Path

# Pattern from reindex_complete_codebase.py
TYPE_DECL_PATTERN = re.compile(
    r'^[ \t]*(?:\[[^\]]+\]\s*)*'  # Optional whitespace and attributes at line start
    r'(?:public|private|protected|internal|abstract|sealed|static|partial)?\s*'
    r'(?P<kind>class|struct|interface|enum)\s+'
    r'(?P<name>\w+)',
    re.MULTILINE | re.IGNORECASE
)

# Read the file
file_path = r"c:\Users\CPU12391\Desktop\GDD_RAG_Gradio\codebase_RAG\tank_online_1-dev\Assets\_GameModules\Editor\NamingConventionScanner.cs"

with open(file_path, 'r', encoding='utf-8') as f:
    code_text = f.read()

print("Testing regex pattern...")
print("=" * 80)

matches = list(TYPE_DECL_PATTERN.finditer(code_text))

print(f"Found {len(matches)} matches:\n")

for i, match in enumerate(matches, 1):
    kind = match.group("kind")
    name = match.group("name")
    start = match.start()
    end = match.end()
    
    # Get context around the match
    context_start = max(0, start - 50)
    context_end = min(len(code_text), end + 50)
    context = code_text[context_start:context_end]
    
    # Get line number
    line_num = code_text[:start].count('\n') + 1
    
    print(f"Match {i}:")
    print(f"  Line: {line_num}")
    print(f"  Kind: {kind}")
    print(f"  Name: {name}")
    print(f"  Position: {start}-{end}")
    print(f"  Char before: {repr(code_text[start-1] if start > 0 else 'N/A')}")
    print(f"  Context: ...{context}...")
    print()





