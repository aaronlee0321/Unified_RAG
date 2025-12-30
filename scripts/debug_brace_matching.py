"""
Debug why the main class NamingConventionScanner isn't being found.
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

print("Testing brace matching for each class...")
print("=" * 80)

matches = list(TYPE_DECL_PATTERN.finditer(code_text))

for i, match in enumerate(matches, 1):
    kind = match.group("kind").lower()
    name = match.group("name")
    start_pos = match.start()
    search_start = match.end()
    
    print(f"\n{i}. {kind} {name}")
    print(f"   Start position: {start_pos}")
    print(f"   Match end: {search_start}")
    
    # Find opening brace
    brace_pos = code_text.find("{", search_start)
    semicolon_pos = code_text.find(";", search_start)
    
    print(f"   Opening brace at: {brace_pos}")
    print(f"   Semicolon at: {semicolon_pos}")
    
    if brace_pos == -1:
        print(f"   ❌ No opening brace found!")
        continue
    
    # Find matching closing brace
    brace_count = 1
    pos = brace_pos + 1
    iterations = 0
    max_iterations = len(code_text)  # Safety limit
    
    while pos < len(code_text) and brace_count > 0 and iterations < max_iterations:
        char = code_text[pos]
        if char == '{':
            brace_count += 1
        elif char == '}':
            brace_count -= 1
        elif char == '"' or char == "'":
            # Skip string literals
            quote_char = char
            pos += 1
            while pos < len(code_text) and code_text[pos] != quote_char:
                if code_text[pos] == '\\':
                    pos += 1
                pos += 1
        pos += 1
        iterations += 1
    
    if brace_count == 0:
        end_pos = pos
        class_code = code_text[start_pos:end_pos]
        print(f"   ✅ Found matching closing brace at: {end_pos}")
        print(f"   Class code length: {len(class_code)} chars")
        print(f"   Iterations: {iterations}")
        print(f"   First 100 chars: {class_code[:100]}...")
        print(f"   Last 100 chars: ...{class_code[-100:]}")
    else:
        print(f"   ❌ Failed to find matching closing brace!")
        print(f"   Final brace count: {brace_count}")
        print(f"   Reached end of file: {pos >= len(code_text)}")
        print(f"   Iterations: {iterations}")





