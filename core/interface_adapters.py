# core/interface_adapters.py

"""
Adapters to help existing interfaces migrate to the new abstract system.
"""

from typing import Dict, Any, Optional, Callable, Union
from core.abstract_context import AbstractContext, AbstractUser, AbstractMessage, AbstractChat
from core.interfaces_registry import get_interface_registry
from core.logging_utils import log_debug, log_warning

def register_interface_with_trainer(interface_name: str, interface_instance: Any, trainer_id: Optional[int] = None):
    """Helper to register an interface and optionally set its trainer ID."""
    registry = get_interface_registry()
    registry.register_interface(interface_name, interface_instance)
    
    if trainer_id:
        registry.set_trainer_id(interface_name, trainer_id)
        log_debug(f"[interface_adapters] Registered {interface_name} with trainer ID {trainer_id}")
    else:
        log_debug(f"[interface_adapters] Registered {interface_name} without trainer ID")

def create_telegram_adapter():
    """Create an adapter for Telegram that converts to AbstractContext."""
    def telegram_to_abstract(update, context_types) -> AbstractContext:
        """Convert Telegram update/context to AbstractContext."""
        from core.abstract_context import create_context_from_telegram
        return create_context_from_telegram(update, context_types)
    
    return telegram_to_abstract

def create_discord_adapter():
    """Create an adapter for Discord that converts to AbstractContext."""
    def discord_to_abstract(message) -> AbstractContext:
        """Convert Discord message to AbstractContext."""
        user = AbstractUser(
            id=message.author.id,
            username=message.author.name,
            interface_name='discord'
        )
        
        abstract_message = AbstractMessage(
            id=message.id,
            text=message.content,
            user=user,
            chat_id=message.channel.id,
            interface_name='discord',
            raw_data={'discord_message': message}
        )
        
        chat = AbstractChat(
            id=message.channel.id,
            name=getattr(message.channel, 'name', None),
            type='guild' if hasattr(message, 'guild') and message.guild else 'dm',
            interface_name='discord'
        )
        
        return AbstractContext('discord', user, abstract_message, chat)
    
    return discord_to_abstract

def create_reddit_adapter():
    """Create an adapter for Reddit that converts to AbstractContext."""
    def reddit_to_abstract(submission_or_comment) -> AbstractContext:
        """Convert Reddit submission/comment to AbstractContext."""
        # Handle both submissions and comments
        if hasattr(submission_or_comment, 'submission'):
            # This is a comment
            item = submission_or_comment
            chat_id = item.submission.id
        else:
            # This is a submission
            item = submission_or_comment
            chat_id = item.id
        
        user = AbstractUser(
            id=item.author.id if item.author else 'deleted',
            username=item.author.name if item.author else 'deleted',
            interface_name='reddit'
        )
        
        abstract_message = AbstractMessage(
            id=item.id,
            text=getattr(item, 'body', None) or getattr(item, 'title', ''),
            user=user,
            chat_id=chat_id,
            interface_name='reddit',
            raw_data={'reddit_item': item}
        )
        
        chat = AbstractChat(
            id=chat_id,
            name=getattr(item, 'subreddit', {}).get('display_name', 'unknown'),
            type='submission' if hasattr(item, 'title') else 'comment',
            interface_name='reddit'
        )
        
        return AbstractContext('reddit', user, abstract_message, chat)
    
    return reddit_to_abstract

def create_x_adapter():
    """Create an adapter for X (Twitter) that converts to AbstractContext."""
    def x_to_abstract(tweet_data) -> AbstractContext:
        """Convert X/Twitter data to AbstractContext."""
        user = AbstractUser(
            id=tweet_data.get('author_id'),
            username=tweet_data.get('username'),
            interface_name='x'
        )
        
        abstract_message = AbstractMessage(
            id=tweet_data.get('id'),
            text=tweet_data.get('text'),
            user=user,
            chat_id=tweet_data.get('conversation_id', tweet_data.get('id')),
            interface_name='x',
            raw_data={'x_tweet': tweet_data}
        )
        
        chat = AbstractChat(
            id=tweet_data.get('conversation_id', tweet_data.get('id')),
            type='tweet',
            interface_name='x'
        )
        
        return AbstractContext('x', user, abstract_message, chat)
    
    return x_to_abstract

def create_generic_reply_function(interface_name: str, send_function: Callable):
    """Create a generic reply function for any interface."""
    async def generic_reply(message: str, **kwargs):
        """Generic reply function that delegates to the interface-specific sender."""
        try:
            await send_function(message, **kwargs)
        except Exception as e:
            log_warning(f"[interface_adapters] Failed to send reply via {interface_name}: {e}")
    
    return generic_reply
