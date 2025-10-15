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
        # Rotation tasks per session+state key -> asyncio.Task
        self._rotation_tasks: Dict[str, asyncio.Task] = {}
        
    def set_webui(self, webui: SynthWebUIInterface) -> None:
        """Set or update the WebUI reference.
        
        Args:
            webui: The SynthWebUIInterface instance
        """
        self.webui = webui
        log_debug("[AnimationHandler] WebUI reference set")

    async def play_animation(
        self,
        state: AnimationState,
        session_id: Optional[str],
        loop: bool = True,
        context_id: Optional[str] = None
    ) -> None:
        """Play an animation for a specific state.
        
        Args:
            state: The animation state to play
            session_id: The WebUI session ID to send the animation to
            loop: Whether the animation should loop
            context_id: Optional identifier for this animation context (for tracking)
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
            
            log_debug(
                f"[AnimationHandler] Playing {state.value} animation: {selected_animation} "
                f"(loop={loop}, session={session_id}, context={context_id})"
            )
            
            # Send animation command to WebUI
            if self.webui:
                await self._send_animation_command(
                    session_id=session_id,
                    animation_file=selected_animation,
                    loop=loop,
                    state=state.value
                )
            else:
                log_warning("[AnimationHandler] WebUI not set, cannot send animation command")

            # If there are multiple animations for this state, start a background
            # rotation task that will randomly switch between them every 30-60s
            key = f"{session_id}:{state.value}"
            if len(animations) > 1:
                await self._start_rotation_task(session_id, state, context_id)
            else:
                # Ensure no leftover rotation task is running for this state
                await self._stop_rotation_task(session_id, state)

    async def stop_animation(self, context_id: str, session_id: str) -> None:
        """Stop an animation context and return to Idle if no other contexts are active.
        
        Args:
            context_id: The context identifier to stop
            session_id: The WebUI session ID
        """
        async with self._lock:
            # Mark context as inactive
            if context_id in self._active_tasks:
                self._active_tasks[context_id] = False
            
            # Check if any contexts are still active
            has_active = any(self._active_tasks.values())
            
            if not has_active:
                # Return to Idle
                log_debug(f"[AnimationHandler] No active contexts, returning to Idle (session={session_id})")
                await self.play_animation(
                    AnimationState.IDLE,
                    session_id=session_id,
                    loop=True,
                    context_id=None
                )
                # When returning to Idle, make sure other rotation tasks for the
                # previous contexts are cleaned up
                # (stop any rotation tasks for non-idle states tied to this session)
                for anim_state in self.ANIMATION_MAP.keys():
                    if anim_state != AnimationState.IDLE:
                        await self._stop_rotation_task(session_id, anim_state)
            else:
                log_debug(f"[AnimationHandler] Context {context_id} stopped but other contexts still active")

    async def transition_to(
        self,
        state: AnimationState,
        session_id: str,
        context_id: Optional[str] = None
    ) -> None:
        """Transition to a new animation state.
        
        This is a convenience method that plays the animation with looping enabled.
        
        Args:
            state: The animation state to transition to
            session_id: The WebUI session ID
            context_id: Optional context identifier
        """
        await self.play_animation(
            state=state,
            session_id=session_id,
            loop=True,
            context_id=context_id
        )

    async def _send_animation_command(
        self,
        session_id: Optional[str],
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
            
        # Build animation URL path
        animation_url = f"{self.ANIMATIONS_BASE_PATH}/{animation_file}"

        # If session_id is None, broadcast to all connected WebUI sessions
        try:
            if session_id is None:
                for sid, websocket in list(self.webui.connections.items()):
                    try:
                        await websocket.send_json({
                            "type": "animation",
                            "animation": animation_url,
                            "loop": loop,
                            "state": state
                        })
                        log_debug(f"[AnimationHandler] Broadcast animation to session {sid}: {animation_url}")
                    except Exception as exc:
                        log_warning(f"[AnimationHandler] Failed to send animation to session {sid}: {exc}")
                return

            websocket = self.webui.connections.get(session_id)
            if not websocket:
                log_warning(f"[AnimationHandler] No active websocket for session {session_id}")
                return

            await websocket.send_json({
                "type": "animation",
                "animation": animation_url,
                "loop": loop,
                "state": state
            })
            log_debug(f"[AnimationHandler] Sent animation command to session {session_id}: {animation_url}")
        except Exception as exc:
            log_warning(f"[AnimationHandler] Failed to send animation command: {exc}")

    async def _rotation_loop(self, session_id: Optional[str], state: AnimationState, context_id: Optional[str]):
        """Background loop that switches animations randomly every 30-60s."""
        key = f"{session_id}:{state.value}"
        try:
            while True:
                # Choose a random delay between 30 and 60 seconds
                delay = random.randint(30, 60)
                await asyncio.sleep(delay)

                async with self._lock:
                    # If current state changed, stop the loop
                    if self.current_state != state:
                        break
                    animations = self.ANIMATION_MAP.get(state, [])
                    if not animations or len(animations) <= 1:
                        break
                    # Pick a different animation than currently playing when possible
                    candidate = random.choice(animations)
                    if candidate == self.current_animation and len(animations) > 1:
                        # pick another one
                        choices = [a for a in animations if a != self.current_animation]
                        candidate = random.choice(choices) if choices else candidate
                    self.current_animation = candidate
                    # send new animation command (preserve loop and state)
                    await self._send_animation_command(session_id, candidate, True, state.value)
        except asyncio.CancelledError:
            # Normal cancellation path
            pass
        except Exception as exc:
            log_warning(f"[AnimationHandler] Rotation loop error for {key}: {exc}")
        finally:
            # Clean up rotation task entry
            self._rotation_tasks.pop(key, None)

    async def _start_rotation_task(self, session_id: Optional[str], state: AnimationState, context_id: Optional[str]) -> None:
        key = f"{session_id}:{state.value}"
        # Cancel existing rotation task for the same key
        await self._stop_rotation_task(session_id, state)
        # Start new rotation task
        loop = asyncio.get_running_loop()
        task = loop.create_task(self._rotation_loop(session_id, state, context_id))
        self._rotation_tasks[key] = task

    async def _stop_rotation_task(self, session_id: Optional[str], state: AnimationState) -> None:
        key = f"{session_id}:{state.value}"
        task = self._rotation_tasks.get(key)
        if task:
            try:
                task.cancel()
                await task
            except Exception:
                pass
            self._rotation_tasks.pop(key, None)

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
