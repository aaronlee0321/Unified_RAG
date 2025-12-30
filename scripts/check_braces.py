"""Check brace counts in the file."""

file_path = r"c:\Users\CPU12391\Desktop\GDD_RAG_Gradio\codebase_RAG\tank_online_1-dev\Assets\_GameModules\Editor\NamingConventionScanner.cs"

with open(file_path, 'r', encoding='utf-8') as f:
    code = f.read()

open_braces = code.count('{')
close_braces = code.count('}')
print(f"Total {{: {open_braces}")
print(f"Total }}: {close_braces}")
print(f"Difference: {open_braces - close_braces}")

# Check if file ends properly
print(f"\nLast 100 chars:")
print(repr(code[-100:]))





