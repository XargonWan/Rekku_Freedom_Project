"""AI Personal Diary Plugin

This plugin manages Rekku's personal diary entries to maintain continuity,
coherence and memory across conversations. This is a removable plugin that
enhances the bot's memory but doesn't break core functionality when disabled.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any, List, Dict, Optional
import asyncio
import aiomysql
import threading
from contextlib import asynccontextmanager

from core.db import get_conn
from core.logging_utils import log_error, log_info, log_debug, log_warning
from core.core_initializer import register_plugin

# Global flag to track if the plugin is enabled
PLUGIN_ENABLED = True

# Diary-specific configuration
DIARY_CONFIG = {
    "max_diary_chars": {
        "openai_chatgpt": 2000,    # Conservative allocation for GPT-4
        "selenium_chatgpt": 1500,  # Browser-based, more conservative
        "google_cli": 1200,       # Google Gemini limits
        "manual": 800,            # Manual input, keep it short
        "telegram_bot": 1000,     # Telegram interface
        "discord_bot": 1000,      # Discord interface
        "webui": 800,             # Web UI
        "x": 1000                 # X/Twitter interface
    },
    "default_max_chars": 800,     # Fallback for unknown interfaces
    "min_space_threshold": 0.7,   # Include diary if using less than 70% of space
    "max_entries_per_injection": 10,  # Maximum entries to include in prompt
    "default_days": 2,            # Default days to look back for entries
    "cleanup_days": 30            # Days to keep entries before cleanup
}

def get_diary_config(interface_name: str) -> dict:
    """Get diary configuration for a specific interface."""
    return DIARY_CONFIG

def get_max_diary_chars(interface_name: str, current_prompt_length: int = 0) -> int:
    """Calculate how many characters can be allocated to diary injection."""
    max_chars = DIARY_CONFIG["max_diary_chars"].get(interface_name, DIARY_CONFIG["default_max_chars"])
    
    # If we have current prompt length, be more conservative
    if current_prompt_length > 0:
        # Reserve some space and be conservative
        available_estimate = max_chars * 0.8  # Use 80% of allocated space
        return int(min(max_chars, available_estimate))
    
    return max_chars

def should_include_diary(interface_name: str, current_prompt_length: int = 0, max_prompt_chars: int = 0) -> bool:
    """Determine if diary should be included based on available space."""
    if max_prompt_chars <= 0:
        # No prompt limit info, use conservative approach
        return True
    
    usage_ratio = current_prompt_length / max_prompt_chars
    
    # Include diary if we're using less than threshold of available space
    return usage_ratio < DIARY_CONFIG["min_space_threshold"]


@asynccontextmanager
async def get_db():
    """Context manager for MariaDB database connections."""
    conn = None
    try:
        conn = await get_conn()
        log_debug("[ai_diary] Opened database connection")
        yield conn
    except Exception as e:
        log_error(f"[ai_diary] Database error: {e}")
        raise
    finally:
        if conn:
            conn.close()
            log_debug("[ai_diary] Connection closed")


async def init_diary_table():
    """Initialize all AI diary related tables if they don't exist."""
    async with get_db() as conn:
        cursor = await conn.cursor()
        
        # Main ai_diary table
        await cursor.execute('''
            CREATE TABLE IF NOT EXISTS ai_diary (
                id INT AUTO_INCREMENT PRIMARY KEY,
                content TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                tags TEXT DEFAULT '[]',
                involved TEXT DEFAULT '[]',
                emotions TEXT DEFAULT '[]',
                interface VARCHAR(50),
                chat_id VARCHAR(255),
                thread_id VARCHAR(255),
                INDEX idx_timestamp (timestamp),
                INDEX idx_interface_chat (interface, chat_id)
            )
        ''')
        
        # Legacy memories table (moved from core)
        await cursor.execute('''
            CREATE TABLE IF NOT EXISTS memories (
                id INT AUTO_INCREMENT PRIMARY KEY,
                timestamp DATETIME NOT NULL,
                content TEXT NOT NULL,
                author VARCHAR(100),
                source VARCHAR(100),
                tags TEXT,
                scope VARCHAR(50),
                emotion VARCHAR(50),
                intensity INT,
                emotion_state VARCHAR(50)
            )
        ''')
        
        # Legacy emotion_diary table (moved from core)
        await cursor.execute('''
            CREATE TABLE IF NOT EXISTS emotion_diary (
                id VARCHAR(100) PRIMARY KEY,
                source VARCHAR(100),
                event TEXT,
                emotion VARCHAR(50),
                intensity INT,
                state VARCHAR(50),
                trigger_condition TEXT,
                decision_logic TEXT,
                next_check DATETIME
            )
        ''')
        
        await conn.commit()
        log_info("[ai_diary] AI diary tables initialized")


def _run(coro):
    """Run a coroutine safely even if an event loop is already running."""
    try:
        return asyncio.run(coro)
    except RuntimeError:
        result: Any = None
        exc: Exception | None = None

        def runner() -> None:
            nonlocal result, exc
            try:
                result = asyncio.run(coro)
            except Exception as e:
                exc = e

        thread = threading.Thread(target=runner)
        thread.start()
        thread.join()
        if exc:
            raise exc
        return result


async def _execute(query: str, params: tuple = ()) -> None:
    """Execute a database query."""
    async with get_db() as conn:
        cursor = await conn.cursor()
        await cursor.execute(query, params)
        await conn.commit()


async def _fetchall(query: str, params: tuple = ()) -> List[Dict]:
    """Fetch all results from a database query."""
    async with get_db() as conn:
        cursor = await conn.cursor(aiomysql.DictCursor)
        await cursor.execute(query, params)
        return await cursor.fetchall()


def add_diary_entry(
    content: str,
    tags: List[str] = None,
    involved: List[str] = None,
    emotions: List[Dict[str, Any]] = None,
    interface: str = None,
    chat_id: str = None,
    thread_id: str = None
) -> None:
    """Add a new diary entry. Safe to call even if plugin is disabled."""
    global PLUGIN_ENABLED
    if not PLUGIN_ENABLED:
        return
        
    if not content.strip():
        return
    
    tags = tags or []
    involved = involved or []
    emotions = emotions or []
    
    # Validate emotions format
    for emotion in emotions:
        if not isinstance(emotion, dict) or 'type' not in emotion:
            log_warning(f"[ai_diary] Invalid emotion format: {emotion}")
            continue
    
    try:
        _run(_execute(
            """
            INSERT INTO ai_diary (content, tags, involved, emotions, interface, chat_id, thread_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                content,
                json.dumps(tags),
                json.dumps(involved),
                json.dumps(emotions),
                interface,
                chat_id,
                thread_id
            )
        ))
        log_debug(f"[ai_diary] Added diary entry: {content[:50]}...")
    except Exception as e:
        log_error(f"[ai_diary] Failed to add diary entry: {e}")
        # Disable plugin if database is unavailable
        PLUGIN_ENABLED = False


async def add_diary_entry_async(
    content: str,
    tags: List[str] = None,
    involved: List[str] = None,
    emotions: List[Dict[str, Any]] = None,
    interface: str = None,
    chat_id: str = None,
    thread_id: str = None
) -> None:
    """Add a new diary entry (async version). Safe to call even if plugin is disabled."""
    global PLUGIN_ENABLED
    if not PLUGIN_ENABLED:
        return
        
    if not content.strip():
        return
    
    tags = tags or []
    involved = involved or []
    emotions = emotions or []
    
    # Validate emotions format
    for emotion in emotions:
        if not isinstance(emotion, dict) or 'type' not in emotion:
            log_warning(f"[ai_diary] Invalid emotion format: {emotion}")
            continue
    
    try:
        await _execute(
            """
            INSERT INTO ai_diary (content, tags, involved, emotions, interface, chat_id, thread_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                content,
                json.dumps(tags),
                json.dumps(involved),
                json.dumps(emotions),
                interface,
                chat_id,
                thread_id
            )
        )
        log_debug(f"[ai_diary] Added diary entry: {content[:50]}...")
    except Exception as e:
        log_error(f"[ai_diary] Failed to add diary entry: {e}")
        # Disable plugin if database is unavailable
        PLUGIN_ENABLED = False


def get_recent_entries(days: int = 2, max_chars: int = None) -> List[Dict[str, Any]]:
    """Get diary entries from the last N days, optionally limited by character count. 
    Returns empty list if plugin is disabled."""
    global PLUGIN_ENABLED
    if not PLUGIN_ENABLED:
        return []
        
    try:
        cutoff_date = datetime.now() - timedelta(days=days)
        
        entries = _run(_fetchall(
            """
            SELECT id, content, timestamp, tags, involved, emotions, interface, chat_id, thread_id
            FROM ai_diary
            WHERE timestamp >= %s
            ORDER BY timestamp DESC
            """,
            (cutoff_date,)
        ))
        
        # Convert JSON fields back to objects
        for entry in entries:
            entry['tags'] = json.loads(entry.get('tags', '[]'))
            entry['involved'] = json.loads(entry.get('involved', '[]'))
            entry['emotions'] = json.loads(entry.get('emotions', '[]'))
            entry['timestamp'] = entry['timestamp'].isoformat() if entry['timestamp'] else None
        
        # If character limit specified, truncate entries
        if max_chars:
            total_chars = 0
            filtered_entries = []
            
            for entry in entries:
                entry_text = f"📅 {entry['timestamp']}\n{entry['content']}"
                if entry['tags']:
                    entry_text += f"\n#tags: {', '.join(entry['tags'])}"
                if entry['involved']:
                    entry_text += f"\n#involved: {', '.join(entry['involved'])}"
                if entry['emotions']:
                    emotion_str = ", ".join([f"{e.get('type', 'unknown')}({e.get('intensity', 0)})" for e in entry['emotions']])
                    entry_text += f"\n#emotions: {emotion_str}"
                entry_text += "\n"
                
                if total_chars + len(entry_text) > max_chars:
                    break
                
                filtered_entries.append(entry)
                total_chars += len(entry_text)
            
            return filtered_entries
        
        return entries
    
    except Exception as e:
        log_error(f"[ai_diary] Failed to get recent entries: {e}")
        # Disable plugin if database is unavailable
        PLUGIN_ENABLED = False
        return []


def get_entries_by_tags(tags: List[str], limit: int = 10) -> List[Dict[str, Any]]:
    """Get diary entries that contain any of the specified tags."""
    try:
        # Create OR conditions for tag matching
        tag_conditions = []
        params = []
        
        for tag in tags:
            tag_conditions.append("JSON_CONTAINS(tags, %s)")
            params.append(json.dumps(tag))
        
        if not tag_conditions:
            return []
        
        query = f"""
            SELECT id, content, timestamp, tags, involved, emotions, interface, chat_id, thread_id
            FROM ai_diary
            WHERE {' OR '.join(tag_conditions)}
            ORDER BY timestamp DESC
            LIMIT %s
        """
        params.append(limit)
        
        entries = _run(_fetchall(query, tuple(params)))
        
        # Convert JSON fields back to objects
        for entry in entries:
            entry['tags'] = json.loads(entry.get('tags', '[]'))
            entry['involved'] = json.loads(entry.get('involved', '[]'))
            entry['emotions'] = json.loads(entry.get('emotions', '[]'))
            entry['timestamp'] = entry['timestamp'].isoformat() if entry['timestamp'] else None
        
        return entries
    
    except Exception as e:
        log_error(f"[ai_diary] Failed to get entries by tags: {e}")
        return []


def get_entries_with_person(person: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Get diary entries that involve a specific person."""
    try:
        entries = _run(_fetchall(
            """
            SELECT id, content, timestamp, tags, involved, emotions, interface, chat_id, thread_id
            FROM ai_diary
            WHERE JSON_CONTAINS(involved, %s)
            ORDER BY timestamp DESC
            LIMIT %s
            """,
            (json.dumps(person), limit)
        ))
        
        # Convert JSON fields back to objects
        for entry in entries:
            entry['tags'] = json.loads(entry.get('tags', '[]'))
            entry['involved'] = json.loads(entry.get('involved', '[]'))
            entry['emotions'] = json.loads(entry.get('emotions', '[]'))
            entry['timestamp'] = entry['timestamp'].isoformat() if entry['timestamp'] else None
        
        return entries
    
    except Exception as e:
        log_error(f"[ai_diary] Failed to get entries with person {person}: {e}")
        return []


def format_diary_for_injection(entries: List[Dict[str, Any]]) -> str:
    """Format diary entries for static injection into prompts."""
    if not entries:
        return ""
    
    formatted_lines = ["=== Rekku's Recent Diary ==="]
    
    for entry in entries:
        timestamp = entry.get('timestamp', 'Unknown time')
        if timestamp and len(timestamp) > 19:  # Truncate ISO timestamp
            timestamp = timestamp[:19].replace('T', ' ')
        
        content = entry.get('content', '')
        tags = entry.get('tags', [])
        involved = entry.get('involved', [])
        emotions = entry.get('emotions', [])
        interface = entry.get('interface', '')
        chat_id = entry.get('chat_id', '')
        thread_id = entry.get('thread_id', '')
        
        formatted_lines.append(f"📅 {timestamp}")
        formatted_lines.append(content)
        
        if tags:
            formatted_lines.append(f"#tags: {', '.join(tags)}")
        
        if involved:
            formatted_lines.append(f"#involved: {', '.join(involved)}")
        
        if emotions:
            emotion_str = ", ".join([f"{e.get('type', 'unknown')}({e.get('intensity', 0)})" for e in emotions])
            formatted_lines.append(f"#emotions: {emotion_str}")
        
        if interface and chat_id:
            context_str = f"{interface}/{chat_id}"
            if thread_id:
                context_str += f"/{thread_id}"
            formatted_lines.append(f"#context: {context_str}")
        
        formatted_lines.append("")  # Empty line between entries
    
    formatted_lines.append("=== End Diary ===")
    return "\n".join(formatted_lines)


def cleanup_old_entries(days_to_keep: int = 30) -> int:
    """Remove diary entries older than specified days. Returns number of deleted entries.
    Returns 0 if plugin is disabled."""
    global PLUGIN_ENABLED
    if not PLUGIN_ENABLED:
        return 0
        
    try:
        cutoff_date = datetime.now() - timedelta(days=days_to_keep)
        
        # First count how many will be deleted
        count_result = _run(_fetchall(
            "SELECT COUNT(*) as count FROM ai_diary WHERE timestamp < %s",
            (cutoff_date,)
        ))
        count = count_result[0]['count'] if count_result else 0
        
        # Delete old entries
        _run(_execute(
            "DELETE FROM ai_diary WHERE timestamp < %s",
            (cutoff_date,)
        ))
        
        log_info(f"[ai_diary] Cleaned up {count} old diary entries")
        return count
    
    except Exception as e:
        log_error(f"[ai_diary] Failed to cleanup old entries: {e}")
        PLUGIN_ENABLED = False
        return 0


def is_plugin_enabled() -> bool:
    """Check if the diary plugin is currently enabled."""
    global PLUGIN_ENABLED
    return PLUGIN_ENABLED


def enable_plugin() -> bool:
    """Try to enable the plugin by testing database connectivity."""
    global PLUGIN_ENABLED
    try:
        # Test database connectivity
        _run(init_diary_table())
        PLUGIN_ENABLED = True
        log_info("[ai_diary] Plugin enabled successfully")
        return True
    except Exception as e:
        log_error(f"[ai_diary] Failed to enable plugin: {e}")
        PLUGIN_ENABLED = False
        return False


def disable_plugin() -> None:
    """Manually disable the plugin."""
    global PLUGIN_ENABLED
    PLUGIN_ENABLED = False
    log_info("[ai_diary] Plugin manually disabled")


# Initialize table on module load
try:
    _run(init_diary_table())
    log_info("[ai_diary] Plugin initialized successfully")
except Exception as e:
    log_warning(f"[ai_diary] Plugin initialization failed, disabling: {e}")
    PLUGIN_ENABLED = False

class DiaryPlugin:
    """Plugin that manages AI diary and provides static injection of recent entries."""

    def __init__(self):
        register_plugin("ai_diary", self)

    def get_supported_action_types(self):
        return ["static_inject"]

    def get_supported_actions(self):
        return {
            "static_inject": {
                "description": "Inject recent diary entries into the prompt context",
                "required_fields": [],
                "optional_fields": [],
            }
        }

    def get_static_injection(self, message=None, context_memory=None) -> dict:
        """Get recent diary entries for static injection. Returns empty dict if plugin disabled."""
        global PLUGIN_ENABLED
        if not PLUGIN_ENABLED:
            return {"diary": ""}
            
        # Get interface name from message if available
        interface_name = "manual"  # Default fallback
        if message and hasattr(message, 'interface'):
            interface_name = message.interface
        elif message and isinstance(message, dict):
            interface_name = message.get('interface', 'manual')
        
        # Get current prompt length estimate (if available)
        current_prompt_length = 0
        max_prompt_chars = 0
        
        # Try to get prompt length from context_memory or message
        if context_memory:
            # Estimate based on context memory size
            current_prompt_length = len(str(context_memory)) * 2  # Rough estimate
        
        # Try to get max prompt chars from message or use defaults
        if message and hasattr(message, 'max_prompt_chars'):
            max_prompt_chars = message.max_prompt_chars
        elif hasattr(message, 'interface'):
            # Use conservative defaults based on interface
            max_prompt_chars = {
                "openai_chatgpt": 32000,
                "selenium_chatgpt": 25000,
                "google_cli": 20000,
                "manual": 8000
            }.get(interface_name, 8000)
        
        # Check if we should include diary based on available space
        should_include = should_include_diary(interface_name, current_prompt_length, max_prompt_chars)
        max_chars = get_max_diary_chars(interface_name, current_prompt_length)
        
        if not should_include:
            return {"diary": ""}
        
        # Get recent entries with character limit
        recent_entries = get_recent_entries(days=DIARY_CONFIG["default_days"], max_chars=max_chars)
        
        if not recent_entries:
            return {"diary": ""}
        
        diary_text = format_diary_for_injection(recent_entries)
        
        return {"diary": diary_text}


# Initialize the plugin
PLUGIN_CLASS = DiaryPlugin

__all__ = [
    "add_diary_entry",
    "add_diary_entry_async",
    "get_recent_entries", 
    "get_entries_by_tags",
    "get_entries_with_person",
    "format_diary_for_injection",
    "cleanup_old_entries",
    "is_plugin_enabled",
    "enable_plugin", 
    "disable_plugin",
    "DiaryPlugin"
]
