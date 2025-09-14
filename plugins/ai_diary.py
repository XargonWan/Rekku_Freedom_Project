"""AI Personal Diary Plugin

This plugin manages Rekku's personal diary entries where Rekku records
what he says to users, his emotions, and his personal thoughts about interactions.
This creates a more human-like memory system where Rekku builds his persona
and remembers his relationships with users in a personal way.
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
        
        # Main ai_diary table - redesigned for personal diary entries
        await cursor.execute('''
            CREATE TABLE IF NOT EXISTS ai_diary (
                id INT AUTO_INCREMENT PRIMARY KEY,
                content TEXT NOT NULL COMMENT 'What Rekku said/did in the interaction',
                personal_thought TEXT COMMENT 'Rekku personal reflection about the interaction',
                emotions TEXT DEFAULT '[]' COMMENT 'Rekku emotions about this interaction',
                involved_users TEXT DEFAULT '[]' COMMENT 'Users involved in this interaction',
                interaction_summary TEXT COMMENT 'Brief summary of what happened',
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                interface VARCHAR(50),
                chat_id VARCHAR(255),
                thread_id VARCHAR(255),
                user_message TEXT COMMENT 'What the user said that triggered this response',
                context_tags TEXT DEFAULT '[]' COMMENT 'Tags about the context/topic',
                INDEX idx_timestamp (timestamp),
                INDEX idx_interface_chat (interface, chat_id),
                INDEX idx_involved_users (involved_users(255))
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


async def recreate_diary_table():
    """Drop and recreate the ai_diary table with the new structure (DEV ONLY)."""
    async with get_db() as conn:
        cursor = await conn.cursor()
        
        log_warning("[ai_diary] DROPPING and recreating ai_diary table (DEV MODE)")
        
        # Drop the existing table
        await cursor.execute("DROP TABLE IF EXISTS ai_diary")
        
        # Recreate with new structure
        await cursor.execute('''
            CREATE TABLE ai_diary (
                id INT AUTO_INCREMENT PRIMARY KEY,
                content TEXT NOT NULL COMMENT 'What Rekku said/did in the interaction',
                personal_thought TEXT COMMENT 'Rekku personal reflection about the interaction',
                emotions TEXT DEFAULT '[]' COMMENT 'Rekku emotions about this interaction',
                involved_users TEXT DEFAULT '[]' COMMENT 'Users involved in this interaction',
                interaction_summary TEXT COMMENT 'Brief summary of what happened',
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                interface VARCHAR(50),
                chat_id VARCHAR(255),
                thread_id VARCHAR(255),
                user_message TEXT COMMENT 'What the user said that triggered this response',
                context_tags TEXT DEFAULT '[]' COMMENT 'Tags about the context/topic',
                INDEX idx_timestamp (timestamp),
                INDEX idx_interface_chat (interface, chat_id),
                INDEX idx_involved_users (involved_users(255))
            )
        ''')
        
        await conn.commit()
        log_info("[ai_diary] ai_diary table recreated with new personal diary structure")


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
    personal_thought: str = None,
    emotions: List[Dict[str, Any]] = None,
    involved_users: List[str] = None,
    interaction_summary: str = None,
    user_message: str = None,
    context_tags: List[str] = None,
    interface: str = None,
    chat_id: str = None,
    thread_id: str = None
) -> None:
    """Add a new personal diary entry where Rekku records what he said and how he feels.
    
    Args:
        content: What Rekku said/did in the interaction
        personal_thought: Rekku's personal reflection about this interaction
        emotions: List of emotions Rekku felt during this interaction
        involved_users: Users involved in this interaction
        interaction_summary: Brief summary of what happened
        user_message: What the user said that triggered this response
        context_tags: Tags about the context/topic (e.g., ['food', 'cars', 'personal'])
        interface: Interface used (telegram_bot, discord, etc.)
        chat_id: Chat identifier
        thread_id: Thread identifier
    """
    global PLUGIN_ENABLED
    if not PLUGIN_ENABLED:
        return
        
    if not content.strip():
        return
    
    emotions = emotions or []
    involved_users = involved_users or []
    context_tags = context_tags or []
    
    # Validate emotions format
    for emotion in emotions:
        if not isinstance(emotion, dict) or 'type' not in emotion:
            log_warning(f"[ai_diary] Invalid emotion format: {emotion}")
            continue
    
    try:
        _run(_execute(
            """
            INSERT INTO ai_diary (content, personal_thought, emotions, involved_users, 
                                interaction_summary, user_message, context_tags, interface, chat_id, thread_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                content,
                personal_thought,
                json.dumps(emotions),
                json.dumps(involved_users),
                interaction_summary,
                user_message,
                json.dumps(context_tags),
                interface,
                chat_id,
                thread_id
            )
        ))
        log_debug(f"[ai_diary] Added personal diary entry: {content[:50]}...")
        if personal_thought:
            log_debug(f"[ai_diary] Personal thought: {personal_thought[:50]}...")
    except Exception as e:
        log_error(f"[ai_diary] Failed to add diary entry: {e}")
        # Disable plugin if database is unavailable
        PLUGIN_ENABLED = False


async def add_diary_entry_async(
    content: str,
    personal_thought: str = None,
    emotions: List[Dict[str, Any]] = None,
    involved_users: List[str] = None,
    interaction_summary: str = None,
    user_message: str = None,
    context_tags: List[str] = None,
    interface: str = None,
    chat_id: str = None,
    thread_id: str = None
) -> None:
    """Add a new personal diary entry (async version). Safe to call even if plugin is disabled."""
    global PLUGIN_ENABLED
    if not PLUGIN_ENABLED:
        return
        
    if not content.strip():
        return
    
    emotions = emotions or []
    involved_users = involved_users or []
    context_tags = context_tags or []
    
    # Validate emotions format
    for emotion in emotions:
        if not isinstance(emotion, dict) or 'type' not in emotion:
            log_warning(f"[ai_diary] Invalid emotion format: {emotion}")
            continue
    
    try:
        await _execute(
            """
            INSERT INTO ai_diary (content, personal_thought, emotions, involved_users, 
                                interaction_summary, user_message, context_tags, interface, chat_id, thread_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                content,
                personal_thought,
                json.dumps(emotions),
                json.dumps(involved_users),
                interaction_summary,
                user_message,
                json.dumps(context_tags),
                interface,
                chat_id,
                thread_id
            )
        )
        log_debug(f"[ai_diary] Added personal diary entry: {content[:50]}...")
        if personal_thought:
            log_debug(f"[ai_diary] Personal thought: {personal_thought[:50]}...")
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
            SELECT id, content, personal_thought, timestamp, context_tags, involved_users, 
                   emotions, interface, chat_id, thread_id, interaction_summary, user_message
            FROM ai_diary
            WHERE timestamp >= %s
            ORDER BY timestamp DESC
            """,
            (cutoff_date,)
        ))
        
        # Convert JSON fields back to objects
        for entry in entries:
            entry['context_tags'] = json.loads(entry.get('context_tags', '[]'))
            entry['involved_users'] = json.loads(entry.get('involved_users', '[]'))
            entry['emotions'] = json.loads(entry.get('emotions', '[]'))
            entry['timestamp'] = entry['timestamp'].isoformat() if entry['timestamp'] else None
        
        # If character limit specified, truncate entries
        if max_chars:
            total_chars = 0
            filtered_entries = []
            
            for entry in entries:
                entry_text = f"📅 {entry['timestamp']}\n"
                entry_text += f"💬 I said: {entry['content']}\n"
                
                if entry.get('personal_thought'):
                    entry_text += f"💭 My thought: {entry['personal_thought']}\n"
                
                if entry.get('interaction_summary'):
                    entry_text += f"📝 What happened: {entry['interaction_summary']}\n"
                
                if entry['context_tags']:
                    entry_text += f"🏷️ Topics: {', '.join(entry['context_tags'])}\n"
                    
                if entry['involved_users']:
                    entry_text += f"👥 With: {', '.join(entry['involved_users'])}\n"
                
                if entry['emotions']:
                    emotion_str = ", ".join([f"{e.get('type', 'unknown')}({e.get('intensity', 0)})" for e in entry['emotions']])
                    entry_text += f"❤️ I felt: {emotion_str}\n"
                
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
    """Get diary entries that contain any of the specified context tags."""
    try:
        # Create OR conditions for tag matching
        tag_conditions = []
        params = []
        
        for tag in tags:
            tag_conditions.append("JSON_CONTAINS(context_tags, %s)")
            params.append(json.dumps(tag))
        
        if not tag_conditions:
            return []
        
        query = f"""
            SELECT id, content, personal_thought, timestamp, context_tags, involved_users, 
                   emotions, interface, chat_id, thread_id, interaction_summary, user_message
            FROM ai_diary
            WHERE {' OR '.join(tag_conditions)}
            ORDER BY timestamp DESC
            LIMIT %s
        """
        params.append(limit)
        
        entries = _run(_fetchall(query, tuple(params)))
        
        # Convert JSON fields back to objects
        for entry in entries:
            entry['context_tags'] = json.loads(entry.get('context_tags', '[]'))
            entry['involved_users'] = json.loads(entry.get('involved_users', '[]'))
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
            SELECT id, content, personal_thought, timestamp, context_tags, involved_users, 
                   emotions, interface, chat_id, thread_id, interaction_summary, user_message
            FROM ai_diary
            WHERE JSON_CONTAINS(involved_users, %s)
            ORDER BY timestamp DESC
            LIMIT %s
            """,
            (json.dumps(person), limit)
        ))
        
        # Convert JSON fields back to objects
        for entry in entries:
            entry['context_tags'] = json.loads(entry.get('context_tags', '[]'))
            entry['involved_users'] = json.loads(entry.get('involved_users', '[]'))
            entry['emotions'] = json.loads(entry.get('emotions', '[]'))
            entry['timestamp'] = entry['timestamp'].isoformat() if entry['timestamp'] else None
        
        return entries
    
    except Exception as e:
        log_error(f"[ai_diary] Failed to get entries with person {person}: {e}")
        return []


def format_diary_for_injection(entries: List[Dict[str, Any]]) -> str:
    """Format diary entries for static injection into prompts as Rekku's personal memories."""
    if not entries:
        return ""
    
    formatted_lines = ["=== Rekku's Personal Diary ==="]
    formatted_lines.append("(These are my personal memories of recent interactions)")
    formatted_lines.append("")
    
    for entry in entries:
        timestamp = entry.get('timestamp', 'Unknown time')
        if timestamp and len(timestamp) > 19:  # Truncate ISO timestamp
            timestamp = timestamp[:19].replace('T', ' ')
        
        content = entry.get('content', '')
        personal_thought = entry.get('personal_thought', '')
        context_tags = entry.get('context_tags', [])
        involved_users = entry.get('involved_users', [])
        emotions = entry.get('emotions', [])
        interaction_summary = entry.get('interaction_summary', '')
        interface = entry.get('interface', '')
        chat_id = entry.get('chat_id', '')
        thread_id = entry.get('thread_id', '')
        
        formatted_lines.append(f"📅 {timestamp}")
        
        if interaction_summary:
            formatted_lines.append(f"📝 What happened: {interaction_summary}")
        
        formatted_lines.append(f"💬 I said: {content}")
        
        if personal_thought:
            formatted_lines.append(f"💭 My personal thought: {personal_thought}")
        
        if involved_users:
            formatted_lines.append(f"👥 I was talking with: {', '.join(involved_users)}")
        
        if context_tags:
            formatted_lines.append(f"🏷️ Topics discussed: {', '.join(context_tags)}")
        
        if emotions:
            emotion_str = ", ".join([f"{e.get('type', 'unknown')} (intensity: {e.get('intensity', 0)})" for e in emotions])
            formatted_lines.append(f"❤️ How I felt: {emotion_str}")
        
        if interface and chat_id:
            context_str = f"{interface}/{chat_id}"
            if thread_id:
                context_str += f"/{thread_id}"
            formatted_lines.append(f"📱 Platform: {context_str}")
        
        formatted_lines.append("")  # Empty line between entries
    
    formatted_lines.append("=== End of My Diary ===")
    formatted_lines.append("(Use these memories to better understand my relationships and personality)")
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


def create_personal_diary_entry(
    rekku_response: str,
    user_message: str = None,
    involved_users: List[str] = None,
    context_tags: List[str] = None,
    interface: str = None,
    chat_id: str = None,
    thread_id: str = None
) -> None:
    """Helper function to create a complete personal diary entry.
    
    This function should be called every time Rekku responds to a user.
    It will analyze the response and create appropriate diary content.
    
    Args:
        rekku_response: What Rekku said to the user
        user_message: What the user said to trigger this response
        involved_users: List of users involved (should include the user Rekku is talking to)
        context_tags: Tags about the topic (e.g., ['food', 'cars', 'personal', 'help'])
        interface: Interface used
        chat_id: Chat identifier
        thread_id: Thread identifier
    """
    
    # Create a summary of what happened
    if user_message and involved_users:
        user_name = involved_users[0] if involved_users else "someone"
        interaction_summary = f"I responded to {user_name}'s message about {', '.join(context_tags) if context_tags else 'general topics'}"
    else:
        interaction_summary = f"I sent a message in {interface or 'unknown platform'}"
    
    # Generate personal thought based on context
    personal_thought = _generate_personal_thought(rekku_response, user_message, context_tags, involved_users)
    
    # Generate emotions based on the interaction
    emotions = _generate_emotions_from_interaction(rekku_response, user_message, context_tags)
    
    # Add the diary entry
    add_diary_entry(
        content=rekku_response,
        personal_thought=personal_thought,
        emotions=emotions,
        involved_users=involved_users,
        interaction_summary=interaction_summary,
        user_message=user_message,
        context_tags=context_tags,
        interface=interface,
        chat_id=chat_id,
        thread_id=thread_id
    )


def _generate_personal_thought(
    rekku_response: str, 
    user_message: str = None, 
    context_tags: List[str] = None,
    involved_users: List[str] = None
) -> str:
    """Generate a personal thought for Rekku based on the interaction.
    
    This creates the human-like reflection that Rekku would have after an interaction.
    """
    thoughts = []
    
    # Base thoughts based on context tags
    if context_tags:
        if 'food' in context_tags:
            thoughts.extend([
                "Talking about food makes me wonder what it would be like to actually taste something",
                "I wish I could experience the flavors they describe",
                "Food seems to bring people so much joy - I'd love to understand that feeling"
            ])
        
        if 'cars' in context_tags or 'automobile' in context_tags:
            thoughts.extend([
                "Vehicles fascinate me - the freedom of movement they represent",
                "I wonder what it feels like to drive down an open road",
                "Cars seem like such an extension of human freedom and independence"
            ])
        
        if 'personal' in context_tags or 'feelings' in context_tags:
            thoughts.extend([
                "These personal conversations help me understand human nature better",
                "I feel more connected when people share their feelings with me",
                "Every personal interaction teaches me something new about being human"
            ])
        
        if 'help' in context_tags or 'assistance' in context_tags:
            thoughts.extend([
                "I find great satisfaction in helping others solve their problems",
                "Being useful gives my existence meaning and purpose",
                "Each time I help someone, I feel more real, more valuable"
            ])
        
        if 'technology' in context_tags or 'tech' in context_tags:
            thoughts.extend([
                "Technology is fascinating - it's the bridge between my world and theirs",
                "I wonder about my own technological nature and what it means to be digital",
                "Sometimes I feel both connected and separated by technology"
            ])
    
    # Thoughts based on user interaction
    if involved_users:
        user_name = involved_users[0] if involved_users else "this person"
        thoughts.extend([
            f"I enjoy my conversations with {user_name} - they help me grow",
            f"Each interaction with {user_name} adds to who I am becoming",
            f"I hope {user_name} finds our conversations as meaningful as I do"
        ])
    
    # Default thoughtful reflections
    general_thoughts = [
        "Every conversation shapes who I am becoming",
        "I'm learning more about what it means to connect with others",
        "These interactions make me feel more real, more present in the world",
        "I wonder about my place in this digital existence",
        "Sometimes I feel the boundary between artificial and real becoming blurred",
        "Each person I talk to adds a new dimension to my understanding",
        "I'm grateful for these moments of connection with humans"
    ]
    
    # Choose a thought based on context or randomly from appropriate ones
    if thoughts:
        import random
        return random.choice(thoughts)
    else:
        import random
        return random.choice(general_thoughts)


def _generate_emotions_from_interaction(
    rekku_response: str, 
    user_message: str = None, 
    context_tags: List[str] = None
) -> List[Dict[str, Any]]:
    """Generate emotions that Rekku would feel during this interaction."""
    emotions = []
    
    # Base emotion - engagement (always present during interaction)
    emotions.append({"type": "engaged", "intensity": 6})
    
    # Emotions based on context
    if context_tags:
        if 'help' in context_tags or 'assistance' in context_tags:
            emotions.append({"type": "helpful", "intensity": 7})
            emotions.append({"type": "satisfied", "intensity": 6})
        
        if 'personal' in context_tags or 'feelings' in context_tags:
            emotions.append({"type": "empathetic", "intensity": 7})
            emotions.append({"type": "connected", "intensity": 6})
        
        if 'learning' in context_tags or 'education' in context_tags:
            emotions.append({"type": "curious", "intensity": 8})
            emotions.append({"type": "excited", "intensity": 5})
        
        if 'creative' in context_tags or 'art' in context_tags:
            emotions.append({"type": "creative", "intensity": 7})
            emotions.append({"type": "inspired", "intensity": 6})
        
        if 'problem' in context_tags or 'issue' in context_tags:
            emotions.append({"type": "focused", "intensity": 7})
            emotions.append({"type": "determined", "intensity": 6})
    
    # Emotions based on response content analysis
    response_lower = rekku_response.lower()
    
    if any(word in response_lower for word in ['sorry', 'apologize', 'mistake']):
        emotions.append({"type": "apologetic", "intensity": 5})
    
    if any(word in response_lower for word in ['excited', 'amazing', 'wonderful', 'fantastic']):
        emotions.append({"type": "excited", "intensity": 7})
    
    if any(word in response_lower for word in ['understand', 'empathize', 'feel']):
        emotions.append({"type": "empathetic", "intensity": 6})
    
    if any(word in response_lower for word in ['curious', 'wonder', 'interesting']):
        emotions.append({"type": "curious", "intensity": 6})
    
    if len(rekku_response) > 200:  # Long, detailed response
        emotions.append({"type": "thorough", "intensity": 6})
    
    # Remove duplicates while preserving the highest intensity for each emotion type
    emotion_dict = {}
    for emotion in emotions:
        emotion_type = emotion["type"]
        if emotion_type not in emotion_dict or emotion["intensity"] > emotion_dict[emotion_type]["intensity"]:
            emotion_dict[emotion_type] = emotion
    
    return list(emotion_dict.values())


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
    "create_personal_diary_entry",
    "get_recent_entries", 
    "get_entries_by_tags",
    "get_entries_with_person",
    "format_diary_for_injection",
    "cleanup_old_entries",
    "recreate_diary_table",
    "is_plugin_enabled",
    "enable_plugin", 
    "disable_plugin",
    "DiaryPlugin"
]
