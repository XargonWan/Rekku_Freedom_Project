import os
import asyncio
from datetime import datetime
from types import SimpleNamespace

try:
    from dotenv import load_dotenv
except Exception:
    def load_dotenv(*args, **kwargs):
        return False

load_dotenv()

try:
    import asyncpraw
except Exception:  # pragma: no cover - library missing in env
    asyncpraw = None  # type: ignore

from core.logging_utils import log_debug, log_warning, log_error
from core.transport_layer import universal_send
from core.interfaces import register_interface
import core.plugin_instance as plugin_instance


class RedditInterface:
    """Minimal Reddit interface using asyncpraw."""

    def __init__(self):
        if asyncpraw is None:
            raise RuntimeError("asyncpraw not available")

        token = os.getenv("TOKEN")
        self.reddit = asyncpraw.Reddit(
            client_id=os.getenv("REDDIT_CLIENT_ID"),
            client_secret=os.getenv("REDDIT_CLIENT_SECRET"),
            user_agent=os.getenv("REDDIT_USER_AGENT", "rekku-agent"),
            username=os.getenv("REDDIT_USERNAME"),
            password=os.getenv("REDDIT_PASSWORD"),
            refresh_token=token,
        )
        self._running = False

    # --- interface metadata -------------------------------------------------
    @staticmethod
    def get_interface_id() -> str:
        return "reddit"

    @staticmethod
    def get_supported_action_types() -> list[str]:
        return ["message"]

    @staticmethod
    def get_action_types() -> list[str]:
        """Return action types supported by this interface."""
        return ["message_reddit"]

    @staticmethod
    def get_supported_actions() -> dict:
        return {
            "message_reddit": {
                "description": "Send a message or reply on Reddit.",
                "usage": {
                    "type": "message_reddit",
                    "interface": "reddit",
                    "payload": {"text": "...", "target": "<username>", "reply_to": "<comment_or_message_id>"},
                },
            }
        }

    # --- public API ---------------------------------------------------------
    async def start(self):
        """Begin listening for inbox events."""
        if self._running:
            return
        self._running = True
        asyncio.create_task(self._listen_inbox())
        register_interface("reddit", self)
        from core.core_initializer import core_initializer
        core_initializer.register_interface("reddit")
        log_debug("[reddit_interface] Listening started")

    async def read_feed(self, limit: int = 10):
        front = self.reddit.front
        posts = []
        async for post in front.hot(limit=limit):
            posts.append(post)
        return posts

    async def search(self, query: str, limit: int = 10):
        sub = await self.reddit.subreddit("all")
        results = []
        async for item in sub.search(query, limit=limit):
            results.append(item)
        return results

    async def read_dms(self, limit: int = 10):
        messages = []
        async for msg in self.reddit.inbox.messages(limit=limit):
            messages.append(msg)
        return messages

    async def send_dm(self, username: str, text: str):
        redditor = await self.reddit.redditor(username)
        await redditor.message("message", text)

    async def reply(self, parent_id: str, text: str):
        try:
            comment = await self.reddit.comment(parent_id)
            await comment.reply(text)
        except Exception:
            try:
                message = await self.reddit.inbox.message(parent_id)
                await message.reply(text)
            except Exception as e:
                log_error(f"[reddit_interface] Reply failed: {e}")

    async def follow_subreddit(self, name: str):
        sub = await self.reddit.subreddit(name)
        await sub.subscribe()

    async def unfollow_subreddit(self, name: str):
        sub = await self.reddit.subreddit(name)
        await sub.unsubscribe()

    async def follow_user(self, name: str):
        user = await self.reddit.redditor(name)
        await user.friend()

    async def unfollow_user(self, name: str):
        user = await self.reddit.redditor(name)
        await user.unfriend()

    async def send_message(self, payload: dict, original_message: object | None = None):
        text = payload.get("text", "")
        target = payload.get("target")
        reply_to = payload.get("reply_to")
        await universal_send(self._reddit_send, target, text=text, reply_to=reply_to)

    async def _reddit_send(self, target: str, text: str, reply_to: str | None = None):
        if reply_to:
            try:
                comment = await self.reddit.comment(reply_to)
                await comment.reply(text)
                return
            except Exception:
                try:
                    message = await self.reddit.inbox.message(reply_to)
                    await message.reply(text)
                    return
                except Exception as e:
                    log_warning(f"[reddit_interface] Reply attempt failed: {e}")
        await self.send_dm(target, text)

    # --- internal helpers ---------------------------------------------------
    async def _listen_inbox(self):
        if asyncpraw is None:
            return
        try:
            async for item in self.reddit.inbox.stream(skip_existing=True):
                wrapper = self._wrap_item(item)
                if wrapper:
                    await plugin_instance.handle_incoming_message(self, wrapper, {})
        except Exception as e:
            log_error(f"[reddit_interface] Inbox listener stopped: {e}")
            self._running = False

    def _wrap_item(self, item):
        if asyncpraw is None:
            return None
        author = getattr(item, "author", None)
        author_name = author.name if author else "unknown"
        chat = SimpleNamespace(id=author_name, type="private")
        if isinstance(item, asyncpraw.models.Message):
            return SimpleNamespace(
                chat_id=author_name,
                message_id=item.id,
                text=getattr(item, "body", ""),
                date=datetime.fromtimestamp(item.created_utc),
                from_user=SimpleNamespace(id=author_name, full_name=author_name, username=author_name),
                reply_to_message=None,
                chat=chat,
            )
        if isinstance(item, asyncpraw.models.Comment):
            chat = SimpleNamespace(id=item.subreddit.display_name, type="public")
            return SimpleNamespace(
                chat_id=author_name,
                message_id=item.id,
                text=getattr(item, "body", ""),
                date=datetime.fromtimestamp(item.created_utc),
                from_user=SimpleNamespace(id=author_name, full_name=author_name, username=author_name),
                reply_to_message=None,
                chat=chat,
            )
        return None

    @staticmethod
    def get_interface_instructions():
        return (
            "REDDIT INTERFACE INSTRUCTIONS:\n"
            "- Use usernames as targets when sending direct messages.\n"
            "- Provide reply_to when replying to comments or messages.\n"
            "- Text is plain Markdown.\n"
        )


__all__ = ["RedditInterface"]
