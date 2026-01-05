"""
Test why AmplifyImpostor and NetworkObjectBaker aren't being detected.
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

files_to_test = [
    (r"Assets/_GameAssets/Scripts/Runtime/AmplifyImpostors/Plugins/Scripts/AmplifyImpostor.cs", "AmplifyImpostor"),
    (r"Assets/Photon/Fusion/Runtime/Fusion.Unity.cs", "NetworkObjectBaker"),
]

workspace_root = Path(r"C:\Users\CPU12391\Desktop\unified_rag_app")
gdd_root = Path(r"c:\Users\CPU12391\Desktop\GDD_RAG_Gradio\codebase_RAG\tank_online_1-dev")

for rel_path, class_name in files_to_test:
    print(f"\n{'=' * 80}")
    print(f"Testing: {rel_path}")
    print(f"Looking for: {class_name}")
    print(f"{'=' * 80}\n")
    
    # Try to find file
    workspace_file = workspace_root / rel_path
    gdd_file = gdd_root / rel_path
    
    file_path = None
    if workspace_file.exists():
        file_path = workspace_file
    elif gdd_file.exists():
        file_path = gdd_file
    
    if not file_path:
        print(f"❌ File not found")
        continue
    
    with open(file_path, 'r', encoding='utf-8') as f:
        code_text = f.read()
    
    # Find all matches
    matches = list(TYPE_DECL_PATTERN.finditer(code_text))
    print(f"Total matches found: {len(matches)}\n")
    
    # Find the specific class
    found_class = False
    for match in matches:
        kind = match.group("kind").lower()
        name = match.group("name")
        
        if name == class_name:
            found_class = True
            start = match.start()
            end = match.end()
            line_num = code_text[:start].count('\n') + 1
            
            # Get context
            context_start = max(0, start - 100)
            context_end = min(len(code_text), end + 100)
            context = code_text[context_start:context_end]
            
            # Get the actual line
            lines = code_text.split('\n')
            if line_num <= len(lines):
                actual_line = lines[line_num - 1]
            else:
                actual_line = "N/A"
            
            print(f"✅ Found {kind} {name}:")
            print(f"   Line: {line_num}")
            print(f"   Position: {start}-{end}")
            print(f"   Actual line: {repr(actual_line)}")
            print(f"   Match text: {repr(match.group(0))}")
            print(f"   Context: ...{context}...")
            
            # Check if brace matching would work
            search_start = match.end()
            brace_pos = code_text.find("{", search_start)
            
            if brace_pos == -1:
                print(f"   ⚠️  No opening brace found after match!")
            else:
                print(f"   ✓ Opening brace found at position {brace_pos}")
                
                # Try brace matching
                brace_count = 1
                pos = brace_pos + 1
                max_iterations = 1000000  # Safety limit
                iterations = 0
                
                while pos < len(code_text) and brace_count > 0 and iterations < max_iterations:
                    char = code_text[pos]
                    
                    # Handle string literals
                    if char == '"':
                        pos += 1
                        while pos < len(code_text) and code_text[pos] != '"':
                            if code_text[pos] == '\\':
                                pos += 1
                            pos += 1
                    elif char == "'":
                        pos += 1
                        while pos < len(code_text) and code_text[pos] != "'":
                            if code_text[pos] == '\\':
                                pos += 1
                            pos += 1
                    elif char == '{':
                        brace_count += 1
                    elif char == '}':
                        brace_count -= 1
                    
                    pos += 1
                    iterations += 1
                
                if brace_count == 0:
                    end_pos = pos
                    print(f"   ✓ Found matching closing brace at position {end_pos}")
                    print(f"   ✓ Class code length: {end_pos - start} chars")
                elif pos >= len(code_text):
                    print(f"   ⚠️  Reached end of file, brace_count = {brace_count}")
                else:
                    print(f"   ⚠️  Exceeded max iterations")
    
    if not found_class:
        print(f"❌ {class_name} NOT FOUND by regex!")
        
        # Try to find it manually
        if class_name in code_text:
            idx = code_text.find(f"class {class_name}")
            if idx != -1:
                line_num = code_text[:idx].count('\n') + 1
                lines = code_text.split('\n')
                if line_num <= len(lines):
                    actual_line = lines[line_num - 1]
                    print(f"\n   But found manually at line {line_num}:")
                    print(f"   {repr(actual_line)}")
                    
                    # Check why regex didn't match
                    if idx > 0:
                        char_before = code_text[idx - 1]
                        print(f"   Char before 'class': {repr(char_before)}")
                        print(f"   Is newline before? {char_before == '\n'}")
                        
                        # Check if it's at start of line
                        line_start = code_text.rfind('\n', 0, idx) + 1
                        line_prefix = code_text[line_start:idx]
                        print(f"   Line prefix: {repr(line_prefix)}")
                        
                        # Try to match just this line
                        test_match = TYPE_DECL_PATTERN.search(actual_line)
                        if test_match:
                            print(f"   ✓ Regex DOES match when tested on line alone!")
                        else:
                            print(f"   ❌ Regex does NOT match when tested on line alone")









