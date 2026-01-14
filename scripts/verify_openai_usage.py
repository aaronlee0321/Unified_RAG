"""
Verification script to check that all AI calls are using OpenAI instead of Qwen.
This script scans the codebase and reports any Qwen usage.
"""
import os
import re
from pathlib import Path

# Files to check (excluding gdd_rag_backbone which may still use Qwen)
CHECK_PATHS = [
    'app.py',
    'backend/services',
    'backend/gdd_hyde.py',
    'backend/code_service.py',
    'backend/gdd_service.py',
]

# Patterns to look for
QWEN_PATTERNS = [
    r'QwenProvider\(',
    r'from.*QwenProvider',
    r'import.*QwenProvider',
    r'qwen-plus',
    r'qwen-flash',
    r'qwen-max',
    r'QWEN_API_KEY.*or.*OPENAI_API_KEY',  # Wrong priority
    r'DASHSCOPE_API_KEY.*or.*OPENAI_API_KEY',  # Wrong priority
]

OPENAI_GOOD_PATTERNS = [
    r'OPENAI_API_KEY.*or.*QWEN_API_KEY',  # Correct priority
    r'SimpleLLMProvider',
    r'gpt-4o-mini',
    r'gpt-4o',
    r'gpt-3.5-turbo',
]

def check_file(file_path: Path):
    """Check a single file for Qwen usage"""
    issues = []
    good_finds = []
    
    try:
        content = file_path.read_text(encoding='utf-8')
        lines = content.split('\n')
        
        for i, line in enumerate(lines, 1):
            # Check for Qwen usage
            for pattern in QWEN_PATTERNS:
                if re.search(pattern, line, re.IGNORECASE):
                    # Skip if it's commented out
                    stripped = line.strip()
                    if stripped.startswith('#') or 'COMMENTED OUT' in line.upper():
                        continue
                    issues.append((i, line.strip(), pattern))
            
            # Check for good OpenAI usage
            for pattern in OPENAI_GOOD_PATTERNS:
                if re.search(pattern, line, re.IGNORECASE):
                    good_finds.append((i, line.strip(), pattern))
        
    except Exception as e:
        return None, None, str(e)
    
    return issues, good_finds, None

def main():
    """Main verification function"""
    print("=" * 70)
    print("OpenAI Usage Verification")
    print("=" * 70)
    print()
    
    project_root = Path(__file__).resolve().parent.parent
    all_issues = []
    all_good = []
    
    for check_path in CHECK_PATHS:
        path = project_root / check_path
        
        if path.is_file():
            files = [path]
        elif path.is_dir():
            files = list(path.rglob('*.py'))
        else:
            continue
        
        for file_path in files:
            # Skip __pycache__ and venv
            if '__pycache__' in str(file_path) or 'venv' in str(file_path):
                continue
            
            issues, good_finds, error = check_file(file_path)
            
            if error:
                print(f"❌ Error checking {file_path.relative_to(project_root)}: {error}")
                continue
            
            if issues:
                all_issues.append((file_path.relative_to(project_root), issues))
            
            if good_finds:
                all_good.append((file_path.relative_to(project_root), good_finds))
    
    # Report results
    print("🔍 Checking for Qwen usage...")
    print()
    
    if all_issues:
        print("⚠️  Found potential Qwen usage (may be commented out):")
        print()
        for file_path, issues in all_issues:
            print(f"  📄 {file_path}")
            for line_num, line, pattern in issues[:3]:  # Show first 3
                print(f"     Line {line_num}: {line[:80]}")
            if len(issues) > 3:
                print(f"     ... and {len(issues) - 3} more")
            print()
    else:
        print("✅ No active Qwen usage found!")
        print()
    
    print("✅ Checking for OpenAI usage...")
    print()
    
    if all_good:
        print("✅ Found OpenAI usage:")
        print()
        for file_path, good_finds in all_good:
            print(f"  📄 {file_path}")
            # Count unique patterns
            patterns_found = set([p for _, _, p in good_finds])
            for pattern in patterns_found:
                count = len([g for g in good_finds if g[2] == pattern])
                print(f"     • {pattern}: {count} occurrence(s)")
            print()
    
    # Summary
    print("=" * 70)
    if all_issues:
        print("⚠️  Summary: Some Qwen references found (check if commented out)")
    else:
        print("✅ Summary: All AI calls appear to be using OpenAI!")
    print("=" * 70)
    
    return len(all_issues) == 0

if __name__ == '__main__':
    success = main()
    exit(0 if success else 1)

