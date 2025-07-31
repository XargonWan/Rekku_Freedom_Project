"""X (Twitter) interface.

This module provides a minimal interface for posting messages and retrieving
public posts from the X platform using :mod:`snscrape`.  It mirrors the
``TelegramInterface`` API so it can be plugged into the existing action system.
"""

from __future__ import annotations

import os
import asyncio
from typing import Any, Dict, List

import snscrape.modules.twitter as sntwitter

from core.logging_utils import log_info, log_debug
from core.interfaces import register_interface


class XInterface:
    """Interface wrapper for the X (Twitter) platform."""

    def __init__(self) -> None:
        self.username = os.environ.get("X_USERNAME")
        if self.username:
            log_debug(f"[x_interface] Using username: {self.username}")
        else:
            log_debug("[x_interface] X_USERNAME not set; timeline features disabled")

    @staticmethod
    def get_interface_id() -> str:
        """Return the unique identifier for this interface."""
        return "x"

    @staticmethod
    def get_supported_action_types() -> List[str]:
        """Return action types supported by this interface."""
        return ["message", "x_timeline_read", "x_search"]

    @staticmethod
    def get_supported_actions() -> dict[str, str]:
        """Return a compact description of supported actions."""
        return {
            "message": "Post a message on X. Optionally set 'target_user' to mention someone. Use: interface: x",
            "x_timeline_read": "Read the latest posts from the authenticated user's timeline. Use: interface: x",
            "x_search": "Search public posts on X using a query string. Use: interface: x",
        }

    async def send_message(self, payload: Dict[str, Any], original_message: Any | None = None) -> None:
        """Format and log a message post."""

        text = payload.get("text", "")
        target_user = payload.get("target_user")

        if target_user:
            text = f"@{target_user} {text}"

        if not text:
            return

        log_info(f"[x_interface] Message posted: {text}")

    async def _read_timeline(self) -> List[str]:
        """Fetch the latest five posts from ``X_USERNAME`` via snscrape."""

        if not self.username:
            log_info("[x_interface] X_USERNAME not configured; cannot read timeline")
            return []

        def fetch() -> List[str]:
            tweets = []
            for idx, tweet in enumerate(sntwitter.TwitterUserScraper(self.username).get_items()):
                if idx >= 5:
                    break
                tweets.append(tweet.content)
            return tweets

        tweets = await asyncio.to_thread(fetch)
        for t in tweets:
            log_info(f"[x_interface] {t}")
        return tweets

    async def _search(self, query: str) -> List[str]:
        """Search public posts using snscrape."""

        if not query:
            return []

        def fetch() -> List[str]:
            results = []
            for idx, tweet in enumerate(sntwitter.TwitterSearchScraper(query).get_items()):
                if idx >= 5:
                    break
                results.append(tweet.content)
            return results

        results = await asyncio.to_thread(fetch)
        for r in results:
            log_info(f"[x_interface] {r}")
        return results

    async def execute_action(self, action: dict, context: dict, bot: Any, original_message: dict):
        """Execute actions using this interface."""

        action_type = action.get("type")
        payload = action.get("payload", {})

        if action_type == "message":
            await self.send_message(payload, original_message)
        elif action_type == "x_timeline_read":
            return await self._read_timeline()
        elif action_type == "x_search":
            query = payload.get("query", "")
            return await self._search(query)
        else:
            log_info(f"[x_interface] Unsupported action type: {action_type}")

    @staticmethod
    def get_interface_instructions() -> str:
        """Return specific usage instructions for the X interface."""
        return (
            "Use interface: x to post or retrieve data from X. For direct messages or mentions, set 'target_user'."
        )


# Expose class for dynamic loading and register interface
INTERFACE_CLASS = XInterface
register_interface("x", XInterface())
