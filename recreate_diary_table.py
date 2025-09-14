#!/usr/bin/env python3
"""
Recreate AI Diary Table Script (DEV ONLY)

This script drops and recreates the ai_diary table with the new personal diary structure.
Use this in development environment only!
"""

import asyncio
from plugins.ai_diary import recreate_diary_table, _run
from core.logging_utils import log_info, log_error

def recreate_table():
    """Recreate the ai_diary table for development."""
    try:
        print("🗑️  Dropping old ai_diary table...")
        print("🔄 Creating new ai_diary table with personal diary structure...")
        
        # Run the recreation
        _run(recreate_diary_table())
        
        print("✅ AI Diary table recreated successfully!")
        print("✅ Ready for personal diary entries!")
        print("💡 You can now use create_personal_diary_entry() to record Rekku's interactions.")
        
    except Exception as e:
        print(f"❌ Failed to recreate table: {e}")
        log_error(f"[recreate_diary] Failed: {e}")

if __name__ == "__main__":
    print("🔄 AI Diary Table Recreation (DEV ONLY)")
    print("=" * 45)
    print("⚠️  WARNING: This will DELETE all existing diary data!")
    print("This should only be used in development environment.")
    print()
    
    answer = input("Are you sure you want to recreate the table? (y/N): ")
    if answer.lower() in ['y', 'yes']:
        recreate_table()
    else:
        print("Operation cancelled.")
