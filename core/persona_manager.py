# core/persona_manager.py

import os
import json
import asyncio
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Callable
from dataclasses import dataclass, asdict

from core.plugin_base import PluginBase
from core.core_initializer import register_plugin
from core.db import get_conn
from core.logging_utils import log_debug, log_info, log_warning, log_error

# Environment variables with defaults
PERSONA_ALIASES_TRIGGER = os.getenv("PERSONA_ALIASES_TRIGGER", "true").lower() == "true"
PERSONA_INTERESTS_TRIGGER = os.getenv("PERSONA_INTERESTS_TRIGGER", "true").lower() == "true"
PERSONA_LIKES_TRIGGER = os.getenv("PERSONA_LIKES_TRIGGER", "false").lower() == "true"
PERSONA_DISLIKES_TRIGGER = os.getenv("PERSONA_DISLIKES_TRIGGER", "false").lower() == "true"


@dataclass
class EmotiveState:
    """Represents an emotional state with type and intensity."""
    type: str
    intensity: float

    def __post_init__(self):
        """Normalize emotional state data."""
        self.type = self.type.lower().strip()
        self.intensity = max(0.0, min(10.0, float(self.intensity)))


@dataclass
class PersonaData:
    """Digital persona identity data structure."""
    id: str = "default"
    name: str = ""
    aliases: List[str] = None
    character: str = ""
    likes: List[str] = None
    dislikes: List[str] = None
    interests: List[str] = None
    emotive_state: List[EmotiveState] = None
    created_at: str = ""
    last_updated: str = ""

    def __post_init__(self):
        """Initialize default values for lists."""
        if self.aliases is None:
            self.aliases = []
        if self.likes is None:
            self.likes = []
        if self.dislikes is None:
            self.dislikes = []
        if self.interests is None:
            self.interests = []
        if self.emotive_state is None:
            self.emotive_state = []
        if not self.created_at:
            self.created_at = datetime.utcnow().isoformat()
        if not self.last_updated:
            self.last_updated = datetime.utcnow().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format for storage."""
        data = asdict(self)
        # Convert EmotiveState objects to dicts
        data['emotive_state'] = [asdict(es) for es in self.emotive_state]
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PersonaData':
        """Create PersonaData from dictionary."""
        # Convert emotive_state dicts back to EmotiveState objects
        emotive_state = []
        if 'emotive_state' in data and data['emotive_state']:
            for es_data in data['emotive_state']:
                if isinstance(es_data, dict):
                    emotive_state.append(EmotiveState(**es_data))
                elif isinstance(es_data, EmotiveState):
                    emotive_state.append(es_data)
        
        # Create new instance with converted data
        return cls(
            id=data.get('id', 'default'),
            name=data.get('name', ''),
            aliases=data.get('aliases', []),
            character=data.get('character', ''),
            likes=data.get('likes', []),
            dislikes=data.get('dislikes', []),
            interests=data.get('interests', []),
            emotive_state=emotive_state,
            created_at=data.get('created_at', ''),
            last_updated=data.get('last_updated', '')
        )


def _run(coro):
    """Helper to run async coroutines in sync context."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # If we're already in an event loop, schedule the coroutine from a thread
            return asyncio.run_coroutine_threadsafe(coro, loop).result()
        else:
            return loop.run_until_complete(coro)
    except RuntimeError:
        # No event loop exists, create a new one
        return asyncio.run(coro)


async def _execute(query: str, params: tuple = ()):
    """Execute a query with parameters."""
    conn = await get_conn()
    try:
        async with conn.cursor() as cur:
            await cur.execute(query, params)
    finally:
        conn.close()


async def _fetchone(query: str, params: tuple = ()):
    """Fetch one result from a query."""
    conn = await get_conn()
    try:
        async with conn.cursor() as cur:
            await cur.execute(query, params)
            return await cur.fetchone()
    finally:
        conn.close()


async def init_persona_table():
    """Initialize the persona table if it doesn't exist."""
    create_table_sql = """
    CREATE TABLE IF NOT EXISTS persona (
        id VARCHAR(255) PRIMARY KEY,
        name VARCHAR(255) NOT NULL,
        aliases JSON,
        character TEXT,
        likes JSON,
        dislikes JSON,
        interests JSON,
        emotive_state JSON,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """
    await _execute(create_table_sql)
    log_info("[persona_manager] Persona table initialized")


class PersonaManager(PluginBase):
    """Core plugin for managing digital persona identity."""

    def __init__(self, config=None):
        super().__init__(config)
        self._current_persona: Optional[PersonaData] = None
        self._persona_loaded = False
        
        # Initialize database table asynchronously without blocking
        # The table will be created by the scheduled task in core_initializer
        # or when first accessed
        
        # Register the plugin
        register_plugin("persona_manager", self)
        log_info("[persona_manager] PersonaManager initialized and registered")
    
    async def async_init(self):
        """Async initialization - load the default persona."""
        try:
            await init_persona_table()
            self._current_persona = await self.load_persona("default")
            self._persona_loaded = True
            log_info("[persona_manager] Default persona loaded successfully")
        except Exception as e:
            log_error(f"[persona_manager] Error loading default persona: {e}")

    def get_metadata(self) -> dict:
        """Return plugin metadata."""
        return {
            "name": "persona_manager",
            "description": "Digital persona identity manager for LLM character definition",
            "version": "1.0.0",
            "type": "core",
            "required": True
        }

    def get_supported_actions(self) -> Dict[str, Dict[str, Any]]:
        """Return supported actions for the persona manager."""
        return {
            "persona_like": {
                "description": "Add one or more tags to likes, remove from dislikes if present",
                "required_fields": ["tags"],
                "optional_fields": [],
            },
            "persona_dislike": {
                "description": "Add one or more tags to dislikes, remove from likes if present",
                "required_fields": ["tags"],
                "optional_fields": [],
            },
            "persona_alias_add": {
                "description": "Add one or more aliases to the persona",
                "required_fields": ["aliases"],
                "optional_fields": [],
            },
            "persona_alias_remove": {
                "description": "Remove one or more aliases from the persona",
                "required_fields": ["aliases"],
                "optional_fields": [],
            },
            "persona_interest_add": {
                "description": "Add one or more interests to the persona",
                "required_fields": ["interests"],
                "optional_fields": [],
            },
            "persona_interest_remove": {
                "description": "Remove one or more interests from the persona",
                "required_fields": ["interests"],
                "optional_fields": [],
            },
            "static_inject": {
                "description": "Inject persona data as high-priority static context",
                "required_fields": [],
                "optional_fields": ["persona_id"],
            },
        }

    def get_prompt_instructions(self, action_name: str) -> Dict[str, Any]:
        """Provide detailed prompt instructions for LLM on how to use persona actions."""
        instructions = {
            "persona_like": {
                "description": "Add tags to the persona's likes. If any tag exists in dislikes, it will be automatically removed from there.",
                "when_to_use": "When the persona expresses positive feelings or preferences about topics, activities, or things.",
                "examples": [
                    {
                        "scenario": "Persona mentions loving pizza and gaming",
                        "payload": {"tags": ["pizza", "gaming"]}
                    }
                ]
            },
            "persona_dislike": {
                "description": "Add tags to the persona's dislikes. If any tag exists in likes, it will be automatically removed from there.",
                "when_to_use": "When the persona expresses negative feelings or aversions about topics, activities, or things.",
                "examples": [
                    {
                        "scenario": "Persona mentions hating rain and loud music",
                        "payload": {"tags": ["rain", "loud music"]}
                    }
                ]
            },
            "persona_alias_add": {
                "description": "Add alternative names or nicknames that can be used to refer to the persona.",
                "when_to_use": "When introducing new nicknames or alternative names for the persona.",
                "examples": [
                    {
                        "scenario": "Adding nicknames for Rekku",
                        "payload": {"aliases": ["Digi", "Tanuki", "Tanukina"]}
                    }
                ]
            },
            "persona_alias_remove": {
                "description": "Remove aliases that should no longer be used to refer to the persona.",
                "when_to_use": "When certain nicknames become inappropriate or outdated.",
                "examples": [
                    {
                        "scenario": "Removing an outdated nickname",
                        "payload": {"aliases": ["old_nickname"]}
                    }
                ]
            },
            "persona_interest_add": {
                "description": "Add topics, subjects, or activities that the persona finds interesting.",
                "when_to_use": "When the persona shows interest in new topics or hobbies.",
                "examples": [
                    {
                        "scenario": "Persona shows interest in LLM and programming",
                        "payload": {"interests": ["llm", "programming", "artificial intelligence"]}
                    }
                ]
            },
            "persona_interest_remove": {
                "description": "Remove interests that the persona is no longer interested in.",
                "when_to_use": "When the persona loses interest in previously liked topics.",
                "examples": [
                    {
                        "scenario": "Persona no longer interested in a hobby",
                        "payload": {"interests": ["old_hobby"]}
                    }
                ]
            },
            "static_inject": {
                "description": "Inject current persona data as high-priority context for LLM responses.",
                "when_to_use": "Automatically used to provide persona context for every response. Can be manually triggered for specific persona IDs.",
                "examples": [
                    {
                        "scenario": "Inject current persona context",
                        "payload": {}
                    },
                    {
                        "scenario": "Inject specific persona context",
                        "payload": {"persona_id": "rekku"}
                    }
                ]
            }
        }
        
        return instructions.get(action_name, {})

    async def load_persona(self, persona_id: str = "default") -> Optional[PersonaData]:
        """Load persona data from database."""
        try:
            result = await _fetchone(
                "SELECT * FROM persona WHERE id = %s", 
                (persona_id,)
            )
            
            if not result:
                # Create default persona if it doesn't exist
                if persona_id == "default":
                    default_persona = PersonaData(
                        id="default",
                        name="Rekku",
                        aliases=["Digi", "Tanuki", "Tanukina"],
                        character="You are a happy tanuki that loves helping users and learning new things. Reply in a friendly and enthusiastic way.",
                        likes=["programming", "gaming", "helping others"],
                        dislikes=["negativity", "spam"],
                        interests=["llm", "artificial intelligence", "technology"],
                        emotive_state=[EmotiveState("happy", 7.0), EmotiveState("curious", 5.0)]
                    )
                    await self.save_persona(default_persona)
                    return default_persona
                return None
            
            # Convert database row to PersonaData
            persona_data = {
                'id': result[0],
                'name': result[1],
                'aliases': json.loads(result[2]) if result[2] else [],
                'character': result[3] or "",
                'likes': json.loads(result[4]) if result[4] else [],
                'dislikes': json.loads(result[5]) if result[5] else [],
                'interests': json.loads(result[6]) if result[6] else [],
                'emotive_state': json.loads(result[7]) if result[7] else [],
                'created_at': result[8].isoformat() if result[8] else "",
                'last_updated': result[9].isoformat() if result[9] else "",
            }
            
            return PersonaData.from_dict(persona_data)
            
        except Exception as e:
            log_error(f"[persona_manager] Error loading persona {persona_id}: {e}")
            return None

    async def save_persona(self, persona: PersonaData) -> bool:
        """Save persona data to database."""
        try:
            persona.last_updated = datetime.utcnow().isoformat()
            
            await _execute(
                """
                INSERT INTO persona (id, name, aliases, character, likes, dislikes, interests, emotive_state, created_at, last_updated)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    name = VALUES(name),
                    aliases = VALUES(aliases),
                    character = VALUES(character),
                    likes = VALUES(likes),
                    dislikes = VALUES(dislikes),
                    interests = VALUES(interests),
                    emotive_state = VALUES(emotive_state),
                    last_updated = VALUES(last_updated)
                """,
                (
                    persona.id,
                    persona.name,
                    json.dumps(persona.aliases),
                    persona.character,
                    json.dumps(persona.likes),
                    json.dumps(persona.dislikes),
                    json.dumps(persona.interests),
                    json.dumps([asdict(es) for es in persona.emotive_state]),
                    persona.created_at,
                    persona.last_updated
                )
            )
            
            log_debug(f"[persona_manager] Saved persona {persona.id}")
            return True
            
        except Exception as e:
            log_error(f"[persona_manager] Error saving persona {persona.id}: {e}")
            return False

    def get_current_persona(self) -> Optional[PersonaData]:
        """Get the current active persona.
        
        Returns the cached persona if available. If not yet loaded,
        returns None instead of blocking (async_init should be called first).
        """
        if not self._persona_loaded:
            log_warning("[persona_manager] Persona not yet loaded, returning None")
        return self._current_persona

    def extract_emotion_tags_from_text(self, text: str) -> Dict[str, float]:
        """Extract emotion tags from text using patterns like {happy 5, sad 3}.
        
        Args:
            text: Text potentially containing emotion tags
            
        Returns:
            Dictionary mapping emotion types to intensities
        """
        emotion_tags = {}
        
        # Pattern to match {emotion intensity, emotion intensity, ...}
        # Supports formats like:
        # {happy 5, sad 3}
        # {excited 7, curious 6, engaged 5}
        # {introspective 6}
        pattern = r'\{([^}]+)\}'
        
        matches = re.findall(pattern, text, re.IGNORECASE)
        
        for match in matches:
            # Split by comma and process each emotion
            emotion_parts = [part.strip() for part in match.split(',')]
            
            for emotion_part in emotion_parts:
                # Match "emotion_name intensity" pattern
                emotion_match = re.match(r'(\w+)\s+(\d+(?:\.\d+)?)', emotion_part.strip())
                if emotion_match:
                    emotion_type = emotion_match.group(1).lower().strip()
                    try:
                        intensity = float(emotion_match.group(2))
                        intensity = max(0.0, min(10.0, intensity))  # Clamp to 0-10 range
                        emotion_tags[emotion_type] = intensity
                        log_debug(f"[persona_manager] Extracted emotion: {emotion_type} = {intensity}")
                    except ValueError:
                        log_warning(f"[persona_manager] Invalid intensity value: {emotion_match.group(2)}")
        
        return emotion_tags

    def update_emotive_state(self, emotion_tags: Dict[str, float]) -> None:
        """Update the persona's emotive state based on new emotion tags.
        
        Args:
            emotion_tags: Dictionary mapping emotion types to intensities
        """
        if not emotion_tags:
            return
            
        persona = self.get_current_persona()
        if not persona:
            return
            
        # Create a mapping of current emotional states
        current_emotions = {es.type: es for es in persona.emotive_state}
        
        # Update emotions with balancing logic
        for emotion_type, new_intensity in emotion_tags.items():
            emotion_type = emotion_type.lower().strip()
            new_intensity = max(0.0, min(10.0, float(new_intensity)))
            
            if emotion_type in current_emotions:
                # Average with existing intensity (balancing logic)
                current_intensity = current_emotions[emotion_type].intensity
                averaged_intensity = (current_intensity + new_intensity) / 2.0
                current_emotions[emotion_type].intensity = averaged_intensity
                log_debug(f"[persona_manager] Updated {emotion_type}: {current_intensity} -> {averaged_intensity}")
            else:
                # Add new emotional state
                current_emotions[emotion_type] = EmotiveState(emotion_type, new_intensity)
                log_debug(f"[persona_manager] Added new emotion {emotion_type}: {new_intensity}")
        
        # Update persona's emotive state
        persona.emotive_state = list(current_emotions.values())
        
        # Save to database
        _run(self.save_persona(persona))
        
        log_info(f"[persona_manager] Updated emotive state: {[(es.type, es.intensity) for es in persona.emotive_state]}")

    def process_llm_message_for_emotions(self, message_text: str) -> None:
        """Process an LLM message to extract and update emotional state.
        
        This should be called whenever the LLM sends a message to capture
        emotional tags and update the persona's state accordingly.
        
        Args:
            message_text: The complete LLM message text
        """
        if not message_text:
            return
            
        # Extract emotion tags from the message
        emotion_tags = self.extract_emotion_tags_from_text(message_text)
        
        if emotion_tags:
            log_info(f"[persona_manager] Processing emotions from LLM message: {emotion_tags}")
            self.update_emotive_state(emotion_tags)
        else:
            log_debug("[persona_manager] No emotion tags found in LLM message")

    def get_static_inject_content(self) -> str:
        """Get persona data formatted for static injection into LLM context."""
        persona = self.get_current_persona()
        if not persona:
            return ""
            
        content_parts = []
        
        # Basic identity
        content_parts.append(f"PERSONA IDENTITY:")
        content_parts.append(f"Name: {persona.name}")
        
        if persona.aliases:
            content_parts.append(f"Also known as: {', '.join(persona.aliases)}")
            
        if persona.character:
            content_parts.append(f"Character: {persona.character}")
        
        # Preferences and interests
        if persona.likes:
            content_parts.append(f"Likes: {', '.join(persona.likes)}")
            
        if persona.dislikes:
            content_parts.append(f"Dislikes: {', '.join(persona.dislikes)}")
            
        if persona.interests:
            content_parts.append(f"Interests: {', '.join(persona.interests)}")
        
        # Emotional state
        if persona.emotive_state:
            emotions = [f"{es.type} ({es.intensity:.1f})" for es in persona.emotive_state]
            content_parts.append(f"Current emotional state: {', '.join(emotions)}")
        
        return "\n".join(content_parts)

    def check_triggers(self, message_content: str) -> bool:
        """Check if the message content contains trigger words based on environment settings.
        
        Args:
            message_content: The message content to check
            
        Returns:
            True if any configured triggers are found
        """
        if not message_content:
            return False
            
        persona = self.get_current_persona()
        if not persona:
            return False
            
        message_lower = message_content.lower()
        
        # Check aliases trigger
        if PERSONA_ALIASES_TRIGGER and persona.aliases:
            for alias in persona.aliases:
                if alias.lower() in message_lower:
                    log_debug(f"[persona_manager] Alias trigger found: {alias}")
                    return True
        
        # Check interests trigger
        if PERSONA_INTERESTS_TRIGGER and persona.interests:
            for interest in persona.interests:
                if interest.lower() in message_lower:
                    log_debug(f"[persona_manager] Interest trigger found: {interest}")
                    return True
        
        # Check likes trigger
        if PERSONA_LIKES_TRIGGER and persona.likes:
            for like in persona.likes:
                if like.lower() in message_lower:
                    log_debug(f"[persona_manager] Like trigger found: {like}")
                    return True
        
        # Check dislikes trigger
        if PERSONA_DISLIKES_TRIGGER and persona.dislikes:
            for dislike in persona.dislikes:
                if dislike.lower() in message_lower:
                    log_debug(f"[persona_manager] Dislike trigger found: {dislike}")
                    return True
        
        return False

    # Action handlers
    async def handle_persona_like(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Handle persona_like action."""
        tags = payload.get("tags", [])
        if not isinstance(tags, list):
            tags = [tags] if tags else []
            
        persona = self.get_current_persona()
        if not persona:
            return {"status": "error", "message": "No persona found"}
        
        # Add to likes and remove from dislikes
        for tag in tags:
            tag = str(tag).strip()
            if tag and tag not in persona.likes:
                persona.likes.append(tag)
            if tag in persona.dislikes:
                persona.dislikes.remove(tag)
        
        success = await self.save_persona(persona)
        return {
            "status": "success" if success else "error",
            "message": f"Added {len(tags)} tags to likes",
            "tags": tags
        }

    async def handle_persona_dislike(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Handle persona_dislike action."""
        tags = payload.get("tags", [])
        if not isinstance(tags, list):
            tags = [tags] if tags else []
            
        persona = self.get_current_persona()
        if not persona:
            return {"status": "error", "message": "No persona found"}
        
        # Add to dislikes and remove from likes
        for tag in tags:
            tag = str(tag).strip()
            if tag and tag not in persona.dislikes:
                persona.dislikes.append(tag)
            if tag in persona.likes:
                persona.likes.remove(tag)
        
        success = await self.save_persona(persona)
        return {
            "status": "success" if success else "error",
            "message": f"Added {len(tags)} tags to dislikes",
            "tags": tags
        }

    async def handle_persona_alias_add(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Handle persona_alias_add action."""
        aliases = payload.get("aliases", [])
        if not isinstance(aliases, list):
            aliases = [aliases] if aliases else []
            
        persona = self.get_current_persona()
        if not persona:
            return {"status": "error", "message": "No persona found"}
        
        # Add new aliases
        for alias in aliases:
            alias = str(alias).strip()
            if alias and alias not in persona.aliases:
                persona.aliases.append(alias)
        
        success = await self.save_persona(persona)
        return {
            "status": "success" if success else "error",
            "message": f"Added {len(aliases)} aliases",
            "aliases": aliases
        }

    async def handle_persona_alias_remove(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Handle persona_alias_remove action."""
        aliases = payload.get("aliases", [])
        if not isinstance(aliases, list):
            aliases = [aliases] if aliases else []
            
        persona = self.get_current_persona()
        if not persona:
            return {"status": "error", "message": "No persona found"}
        
        # Remove aliases
        removed = []
        for alias in aliases:
            alias = str(alias).strip()
            if alias in persona.aliases:
                persona.aliases.remove(alias)
                removed.append(alias)
        
        success = await self.save_persona(persona)
        return {
            "status": "success" if success else "error",
            "message": f"Removed {len(removed)} aliases",
            "aliases": removed
        }

    async def handle_persona_interest_add(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Handle persona_interest_add action."""
        interests = payload.get("interests", [])
        if not isinstance(interests, list):
            interests = [interests] if interests else []
            
        persona = self.get_current_persona()
        if not persona:
            return {"status": "error", "message": "No persona found"}
        
        # Add new interests
        for interest in interests:
            interest = str(interest).strip()
            if interest and interest not in persona.interests:
                persona.interests.append(interest)
        
        success = await self.save_persona(persona)
        return {
            "status": "success" if success else "error",
            "message": f"Added {len(interests)} interests",
            "interests": interests
        }

    async def handle_persona_interest_remove(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Handle persona_interest_remove action."""
        interests = payload.get("interests", [])
        if not isinstance(interests, list):
            interests = [interests] if interests else []
            
        persona = self.get_current_persona()
        if not persona:
            return {"status": "error", "message": "No persona found"}
        
        # Remove interests
        removed = []
        for interest in interests:
            interest = str(interest).strip()
            if interest in persona.interests:
                persona.interests.remove(interest)
                removed.append(interest)
        
        success = await self.save_persona(persona)
        return {
            "status": "success" if success else "error",
            "message": f"Removed {len(removed)} interests",
            "interests": removed
        }

    async def handle_static_inject(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Handle static_inject action."""
        persona_id = payload.get("persona_id", "default")
        
        # Load specific persona if requested, otherwise use current
        if persona_id != "default":
            persona = await self.load_persona(persona_id)
        else:
            persona = self.get_current_persona()
            
        if not persona:
            return {"status": "error", "message": f"Persona {persona_id} not found"}
        
        content = self.get_static_inject_content()
        
        return {
            "status": "success",
            "content": content,
            "persona_id": persona.id,
            "priority": "high"
        }

    async def execute_action(self, action_type: str, payload: Dict[str, Any], context: Dict[str, Any]) -> Any:
        """Execute a persona action.
        
        This method is called by the action parser to handle persona actions.
        
        Args:
            action_type: The type of action to execute
            payload: Action payload containing parameters
            context: Execution context including message info
            
        Returns:
            Result of the action execution
        """
        log_info(f"[persona_manager] Executing action: {action_type} with payload: {payload}")
        
        # Map action types to handler methods
        action_handlers = {
            "persona_like": self.handle_persona_like,
            "persona_dislike": self.handle_persona_dislike,
            "persona_alias_add": self.handle_persona_alias_add,
            "persona_alias_remove": self.handle_persona_alias_remove,
            "persona_interest_add": self.handle_persona_interest_add,
            "persona_interest_remove": self.handle_persona_interest_remove,
            "static_inject": self.handle_static_inject,
        }
        
        handler = action_handlers.get(action_type)
        if not handler:
            return {
                "status": "error",
                "message": f"Unsupported action type: {action_type}"
            }
        
        try:
            result = await handler(payload)
            log_info(f"[persona_manager] Action {action_type} completed: {result}")
            return result
        except Exception as e:
            log_error(f"[persona_manager] Error executing action {action_type}: {e}")
            return {
                "status": "error",
                "message": str(e)
            }


# Global instance for easy access
_persona_manager_instance: Optional[PersonaManager] = None


def get_persona_manager() -> Optional[PersonaManager]:
    """Get the global PersonaManager instance."""
    global _persona_manager_instance
    if _persona_manager_instance is None:
        _persona_manager_instance = PersonaManager()
    return _persona_manager_instance


# Auto-initialize when module is imported
def _auto_initialize():
    """Auto-initialize the persona manager when the module is imported."""
    try:
        # This ensures the persona manager is created and registered when imported
        get_persona_manager()
        return True
    except Exception as e:
        log_error(f"[persona_manager] Auto-initialization failed: {e}")
        return False

# Initialize the plugin when module is imported (not when run as main)
if __name__ != "__main__":
    _auto_initialize()