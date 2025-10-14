"""Animation handler for VRM avatar in the SyntH Web UI.

This module provides a centralized system for managing VRM avatar animations.
Components can trigger logical animation states (Think, Write, Talk, Idle) which
are mapped to actual FBX animation files. The handler ensures smooth transitions
and automatic fallback to Idle when no animations are active.

The animation system integrates with the WebUI to send animation commands via WebSocket.
"""

from __future__ import annotations

import asyncio
import random
import time
from enum import Enum
from typing import Dict, List, Optional, TYPE_CHECKING
from pathlib import Path

from core.logging_utils import log_debug, log_info, log_warning

if TYPE_CHECKING:
    from core.webui import SynthWebUIInterface


class AnimationState(Enum):
    """Logical animation states that components can trigger."""
    IDLE = "idle"
    THINK = "think"
    WRITE = "write"
    TALK = "talk"


class AnimationHandler:
    """Manages VRM avatar animations and their lifecycle.
    
    This handler:
    - Maps logical animation states to FBX animation files
    - Tracks the current animation state
    - Sends animation commands to the WebUI via WebSocket
    - Handles automatic fallback to Idle state
    - Changes animation files randomly every 30-60 seconds for variety
    """

    # Animation mappings: logical state -> list of FBX files
    ANIMATION_MAP: Dict[AnimationState, List[str]] = {
        AnimationState.THINK: ["Thinking.fbx"],
        AnimationState.WRITE: ["Texting While Standing.fbx", "Texting.fbx"],
        AnimationState.TALK: ["talking.fbx"],
        AnimationState.IDLE: ["Idle.fbx", "Idle2.fbx", "Happy Idle.fbx"],
    }

    # Base path for animations relative to the webui static resources
    ANIMATIONS_BASE_PATH = "animations"

    def __init__(self, webui: Optional[SynthWebUIInterface] = None):
        """Initialize the animation handler.
        
        Args:
            webui: Reference to the SynthWebUIInterface for sending animation commands
        """
        self.webui = webui
        self.current_state: AnimationState = AnimationState.IDLE
        self.current_animation: Optional[str] = None
        self.current_animation_start_time: float = 0.0
        self._lock = asyncio.Lock()
        self._active_tasks: Dict[str, bool] = {}  # Track active animation contexts
        self._animation_change_task: Optional[asyncio.Task] = None
        self._is_running = False
        
    def set_webui(self, webui: SynthWebUIInterface) -> None:
        """Set or update the WebUI reference.
        
        Args:
            webui: The SynthWebUIInterface instance
        """
        self.webui = webui
        log_debug("[AnimationHandler] WebUI reference set")

    async def start(self) -> None:
        """Start the animation handler and background tasks."""
        if self._is_running:
            return
            
        self._is_running = True
        self._animation_change_task = asyncio.create_task(self._animation_change_loop())
        log_debug("[AnimationHandler] Animation handler started")

    async def stop(self) -> None:
        """Stop the animation handler and cleanup."""
        self._is_running = False
        if self._animation_change_task:
            self._animation_change_task.cancel()
            try:
                await self._animation_change_task
            except asyncio.CancelledError:
                pass
        log_debug("[AnimationHandler] Animation handler stopped")

    async def play_animation(
        self,
        state: AnimationState,
        session_id: Optional[str] = None,
        loop: bool = True,
        context_id: Optional[str] = None,
        broadcast: bool = True
    ) -> None:
        """Play an animation for a specific state.
        
        Args:
            state: The animation state to play
            session_id: The WebUI session ID to send the animation to (optional for broadcast)
            loop: Whether the animation should loop
            context_id: Optional identifier for this animation context (for tracking)
            broadcast: Whether to broadcast to all connected WebUI sessions
        """
        async with self._lock:
            # If we have a context_id, mark it as active
            if context_id:
                self._active_tasks[context_id] = True
            
            # Select animation file
            animations = self.ANIMATION_MAP.get(state, self.ANIMATION_MAP[AnimationState.IDLE])
            selected_animation = random.choice(animations)
            
            # Update internal state
            self.current_state = state
            self.current_animation = selected_animation
            self.current_animation_start_time = time.time()
            
            log_debug(
                f"[AnimationHandler] Playing {state.value} animation: {selected_animation} "
                f"(loop={loop}, session={session_id}, context={context_id}, broadcast={broadcast})"
            )
            
            # Send animation command
            if broadcast:
                await self._broadcast_animation_command(
                    animation_file=selected_animation,
                    loop=loop,
                    state=state.value
                )
            elif session_id and self.webui:
                await self._send_animation_command_to_session(
                    session_id=session_id,
                    animation_file=selected_animation,
                    loop=loop,
                    state=state.value
                )
            else:
                log_warning("[AnimationHandler] No WebUI set and broadcast=False, cannot send animation command")

    async def stop_animation(self, context_id: str, session_id: Optional[str] = None, broadcast: bool = True) -> None:
        """Stop an animation context and return to Idle if no other contexts are active.
        
        Args:
            context_id: The context identifier to stop
            session_id: Optional session ID for targeted stop
            broadcast: Whether to broadcast the stop command
        """
        async with self._lock:
            # Mark context as inactive
            if context_id in self._active_tasks:
                self._active_tasks[context_id] = False
            
            # Check if any contexts are still active
            has_active = any(self._active_tasks.values())
            
            if not has_active:
                # Return to Idle
                log_debug(f"[AnimationHandler] No active contexts, returning to Idle (session={session_id}, broadcast={broadcast})")
                await self.play_animation(
                    AnimationState.IDLE,
                    session_id=session_id,
                    loop=True,
                    context_id=None,
                    broadcast=broadcast
                )
            else:
                log_debug(f"[AnimationHandler] Context {context_id} stopped but other contexts still active")

    async def transition_to(
        self,
        state: AnimationState,
        session_id: Optional[str] = None,
        context_id: Optional[str] = None,
        broadcast: bool = True
    ) -> None:
        """Transition to a new animation state.
        
        This is a convenience method that plays the animation with looping enabled.
        
        Args:
            state: The animation state to transition to
            session_id: Optional session ID for targeted transition
            context_id: Optional context identifier
            broadcast: Whether to broadcast the transition
        """
        await self.play_animation(
            state=state,
            session_id=session_id,
            loop=True,
            context_id=context_id,
            broadcast=broadcast
        )

    async def _animation_change_loop(self) -> None:
        """Background loop that changes animation files periodically for variety."""
        while self._is_running:
            try:
                # Wait for a random time between 30-60 seconds
                wait_time = random.uniform(30.0, 60.0)
                await asyncio.sleep(wait_time)
                
                # Check if we should change the current animation
                async with self._lock:
                    if self.current_state != AnimationState.IDLE and self._active_tasks:
                        # Still have active tasks, change to a different animation in the same state
                        animations = self.ANIMATION_MAP.get(self.current_state, [])
                        if len(animations) > 1:  # Only change if there are multiple options
                            # Get available animations excluding current one
                            available_animations = [a for a in animations if a != self.current_animation]
                            if available_animations:
                                new_animation = random.choice(available_animations)
                                self.current_animation = new_animation
                                self.current_animation_start_time = time.time()
                                
                                log_debug(
                                    f"[AnimationHandler] Changing animation to {new_animation} "
                                    f"for state {self.current_state.value} (variety)"
                                )
                                
                                # Broadcast the change to all sessions
                                await self._broadcast_animation_command(
                                    animation_file=new_animation,
                                    loop=True,
                                    state=self.current_state.value
                                )
            except asyncio.CancelledError:
                break
            except Exception as exc:
                log_warning(f"[AnimationHandler] Error in animation change loop: {exc}")
                await asyncio.sleep(5.0)  # Brief pause before retrying

    async def _broadcast_animation_command(
        self,
        animation_file: str,
        loop: bool,
        state: str
    ) -> None:
        """Broadcast animation command to all connected WebUI sessions.
        
        Args:
            animation_file: The animation file name
            loop: Whether to loop the animation
            state: The logical state name
        """
        if not self.webui:
            return
            
        # Send to all connected sessions
        disconnected_sessions = []
        for session_id, websocket in self.webui.connections.items():
            try:
                await websocket.send_json({
                    "type": "animation",
                    "animation": f"{self.ANIMATIONS_BASE_PATH}/{animation_file}",
                    "loop": loop,
                    "state": state
                })
            except Exception as exc:
                log_warning(f"[AnimationHandler] Failed to send animation to session {session_id}: {exc}")
                disconnected_sessions.append(session_id)
        
        # Clean up disconnected sessions
        for session_id in disconnected_sessions:
            if session_id in self.webui.connections:
                del self.webui.connections[session_id]

    async def _send_animation_command_to_session(
        self,
        session_id: str,
        animation_file: str,
        loop: bool,
        state: str
    ) -> None:
        """Send animation command to a specific WebUI session.
        
        Args:
            session_id: The WebUI session ID
            animation_file: The animation file name
            loop: Whether to loop the animation
            state: The logical state name
        """
        if not self.webui:
            return
            
        websocket = self.webui.connections.get(session_id)
        if not websocket:
            log_warning(f"[AnimationHandler] No active websocket for session {session_id}")
            return
        
        try:
            # Build animation URL path
            animation_url = f"{self.ANIMATIONS_BASE_PATH}/{animation_file}"
            
            # Send animation command
            await websocket.send_json({
                "type": "animation",
                "animation": animation_url,
                "loop": loop,
                "state": state
            })
            
            log_debug(f"[AnimationHandler] Sent animation command to session {session_id}: {animation_url}")
        except Exception as exc:
            log_warning(f"[AnimationHandler] Failed to send animation command: {exc}")

    def get_current_state(self) -> AnimationState:
        """Get the current animation state.
        
        Returns:
            The current AnimationState
        """
        return self.current_state

    def get_current_animation(self) -> Optional[str]:
        """Get the current animation file name.
        
        Returns:
            The current animation file name or None
        """
        return self.current_animation

    def get_animation_uptime(self) -> float:
        """Get how long the current animation has been playing.
        
        Returns:
            Seconds since the current animation started
        """
        if self.current_animation_start_time > 0:
            return time.time() - self.current_animation_start_time
        return 0.0


# Global animation handler instance
_animation_handler: Optional[AnimationHandler] = None


def get_animation_handler() -> AnimationHandler:
    """Get the global animation handler instance.
    
    Returns:
        The AnimationHandler instance
    """
    global _animation_handler
    if _animation_handler is None:
        _animation_handler = AnimationHandler()
    return _animation_handler


def set_animation_handler(handler: AnimationHandler) -> None:
    """Set the global animation handler instance.
    
    Args:
        handler: The AnimationHandler instance to set
    """
    global _animation_handler
    _animation_handler = handler


async def start_global_animation_handler() -> None:
    """Start the global animation handler."""
    handler = get_animation_handler()
    await handler.start()


async def stop_global_animation_handler() -> None:
    """Stop the global animation handler."""
    handler = get_animation_handler()
    await handler.stop()


import asyncio
import random
from enum import Enum
from typing import Dict, List, Optional, TYPE_CHECKING
from pathlib import Path

from core.logging_utils import log_debug, log_info, log_warning

if TYPE_CHECKING:
    from core.webui import SynthWebUIInterface


class AnimationState(Enum):
    """Logical animation states that components can trigger."""
    IDLE = "idle"
    THINK = "think"
    WRITE = "write"
    TALK = "talk"


class AnimationHandler:
    """Manages VRM avatar animations and their lifecycle.
    
    This handler:
    - Maps logical animation states to FBX files
    - Tracks the current animation state
    - Sends animation commands to the WebUI via WebSocket
    - Handles automatic fallback to Idle state
    - Supports random selection from multiple animation files
    """

    # Animation mappings: logical state -> list of FBX files
    ANIMATION_MAP: Dict[AnimationState, List[str]] = {
        AnimationState.THINK: ["Thinking.fbx"],
        AnimationState.WRITE: ["Texting While Standing.fbx", "Texting.fbx"],
        AnimationState.TALK: ["talking.fbx"],
        AnimationState.IDLE: ["Idle.fbx", "Idle2.fbx", "Happy Idle.fbx"],
    }

    # Base path for animations relative to the webui static resources
    ANIMATIONS_BASE_PATH = "animations"

    def __init__(self, webui: Optional[SynthWebUIInterface] = None):
        """Initialize the animation handler.
        
        Args:
            webui: Reference to the SynthWebUIInterface for sending animation commands
        """
        self.webui = webui
        self.current_state: AnimationState = AnimationState.IDLE
        self.current_animation: Optional[str] = None
        self._lock = asyncio.Lock()
        self._active_tasks: Dict[str, bool] = {}  # Track active animation contexts
        
    def set_webui(self, webui: SynthWebUIInterface) -> None:
        """Set or update the WebUI reference.
        
        Args:
            webui: The SynthWebUIInterface instance
        """
        self.webui = webui
        log_debug("[AnimationHandler] WebUI reference set")

    async def _send_animation_command(
        self,
        session_id: str,
        animation_file: str,
        loop: bool,
        state: str
    ) -> None:
        """Send animation command to the WebUI via WebSocket.
        
        Args:
            session_id: The WebUI session ID
            animation_file: The animation file name
            loop: Whether to loop the animation
            state: The logical state name
        """
        if not self.webui:
            return
            
        websocket = self.webui.connections.get(session_id)
        if not websocket:
            log_warning(f"[AnimationHandler] No active websocket for session {session_id}")
            return
        
        try:
            # Build animation URL path
            animation_url = f"{self.ANIMATIONS_BASE_PATH}/{animation_file}"
            
            # Send animation command
            await websocket.send_json({
                "type": "animation",
                "animation": animation_url,
                "loop": loop,
                "state": state
            })
            
            log_debug(f"[AnimationHandler] Sent animation command to session {session_id}: {animation_url}")
        except Exception as exc:
            log_warning(f"[AnimationHandler] Failed to send animation command: {exc}")

    def get_current_state(self) -> AnimationState:
        """Get the current animation state.
        
        Returns:
            The current AnimationState
        """
        return self.current_state

    def get_current_animation(self) -> Optional[str]:
        """Get the current animation file name.
        
        Returns:
            The current animation file name or None
        """
        return self.current_animation


# Global animation handler instance
_animation_handler: Optional[AnimationHandler] = None


def get_animation_handler() -> AnimationHandler:
    """Get the global animation handler instance.
    
    Returns:
        The AnimationHandler instance
    """
    global _animation_handler
    if _animation_handler is None:
        _animation_handler = AnimationHandler()
    return _animation_handler


def set_animation_handler(handler: AnimationHandler) -> None:
    """Set the global animation handler instance.
    
    Args:
        handler: The AnimationHandler instance to set
    """
    global _animation_handler
    _animation_handler = handler
