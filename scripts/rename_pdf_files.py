"""
Rename PDF files to remove special characters for Supabase Storage compatibility.

This script sanitizes filenames by:
- Removing square brackets [ ]
- Removing commas ,
- Replacing spaces with underscores
- Removing multiple consecutive underscores
"""

import os
from pathlib import Path
import sys

def sanitize_filename(filename: str) -> str:
    """
    Convert filename to storage-safe format.
    
    Args:
        filename: Original filename (including extension)
    
    Returns:
        Sanitized filename
    """
    # Split name and extension
    name_parts = filename.rsplit('.', 1)
    name = name_parts[0]
    ext = name_parts[1] if len(name_parts) > 1 else ''
    
    # Remove special characters
    name = name.replace('[', '').replace(']', '').replace(',', '')
    
    # Replace spaces with underscores
    name = name.replace(' ', '_')
    
    # Remove multiple underscores
    while '__' in name:
        name = name.replace('__', '_')
    
    # Remove leading/trailing underscores
    name = name.strip('_')
    
    # Reconstruct filename with extension
    if ext:
        return f"{name}.{ext}"
    return name


def rename_files_in_directory(directory: str, dry_run: bool = True):
    """
    Rename all files in a directory to be storage-safe.
    
    Args:
        directory: Path to directory containing files to rename
        dry_run: If True, only show what would be renamed without actually renaming
    """
    dir_path = Path(directory)
    
    if not dir_path.exists():
        print(f"❌ Error: Directory not found: {directory}")
        return
    
    if not dir_path.is_dir():
        print(f"❌ Error: Path is not a directory: {directory}")
        return
    
    print(f"📁 Scanning directory: {dir_path}")
    print(f"Mode: {'DRY RUN (no changes will be made)' if dry_run else 'LIVE (files will be renamed)'}")
    print("="*80)
    
    # Find all files
    files = [f for f in dir_path.iterdir() if f.is_file()]
    
    if not files:
        print("No files found in directory")
        return
    
    renamed_count = 0
    skipped_count = 0
    error_count = 0
    
    for file_path in files:
        original_name = file_path.name
        sanitized_name = sanitize_filename(original_name)
        
        # Check if name needs changing
        if original_name == sanitized_name:
            print(f"✓ SKIP: {original_name} (already clean)")
            skipped_count += 1
            continue
        
        new_path = file_path.parent / sanitized_name
        
        # Check if target already exists
        if new_path.exists():
            print(f"⚠️  CONFLICT: {original_name}")
            print(f"   Would rename to: {sanitized_name}")
            print(f"   But target already exists!")
            error_count += 1
            continue
        
        print(f"\n📝 RENAME:")
        print(f"   FROM: {original_name}")
        print(f"   TO:   {sanitized_name}")
        
        if not dry_run:
            try:
                file_path.rename(new_path)
                print(f"   ✅ Successfully renamed")
                renamed_count += 1
            except Exception as e:
                print(f"   ❌ Error: {e}")
                error_count += 1
        else:
            renamed_count += 1
    
    # Summary
    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    print(f"Total files found:    {len(files)}")
    print(f"Files to rename:      {renamed_count}")
    print(f"Files skipped (OK):   {skipped_count}")
    print(f"Errors/conflicts:     {error_count}")
    print("="*80)
    
    if dry_run and renamed_count > 0:
        print("\n⚠️  This was a DRY RUN - no files were actually renamed.")
        print("To actually rename files, run with --live flag:")
        print(f"   python {Path(__file__).name} --live")


if __name__ == "__main__":
    # Target directory
    TARGET_DIR = r"c:\Users\CPU12391\Desktop\AI_Agent\docs"
    
    # Check for --live flag
    dry_run = True
    if len(sys.argv) > 1 and sys.argv[1] == '--live':
        dry_run = False
        print("⚠️  LIVE MODE - Files will be renamed!")
        response = input("Are you sure? Type 'yes' to continue: ")
        if response.lower() != 'yes':
            print("Cancelled.")
            sys.exit(0)
    
    rename_files_in_directory(TARGET_DIR, dry_run=dry_run)
