#!/usr/bin/env python3
"""
Test del sistema di retry senza dipendenze di configurazione.
"""

import time
from types import SimpleNamespace

# Codice copiato dalla transport_layer per test isolato
_retry_tracker = {}

def _get_retry_key(message):
    """Generate a unique key for tracking retries based on chat/thread."""
    chat_id = getattr(message, 'chat_id', None)
    thread_id = getattr(message, 'message_thread_id', None)
    return f"{chat_id}_{thread_id}"

def _should_retry(message, max_retries: int = 2) -> bool:
    """Check if we should attempt retry for this message context."""
    retry_key = _get_retry_key(message)
    current_time = time.time()
    
    # Clean up old retry entries (older than 5 minutes)
    cutoff_time = current_time - 300  # 5 minutes
    keys_to_remove = [k for k, (count, timestamp) in _retry_tracker.items() 
                      if timestamp < cutoff_time]
    for key in keys_to_remove:
        del _retry_tracker[key]
    
    # Check current retry count
    retry_count, _ = _retry_tracker.get(retry_key, (0, current_time))
    return retry_count < max_retries

def _increment_retry(message):
    """Increment retry count for this message context."""
    retry_key = _get_retry_key(message)
    current_time = time.time()
    retry_count, _ = _retry_tracker.get(retry_key, (0, current_time))
    _retry_tracker[retry_key] = (retry_count + 1, current_time)
    return retry_count + 1

if __name__ == "__main__":
    # Test the retry system
    message = SimpleNamespace()
    message.chat_id = 12345
    message.message_thread_id = None

    print('Test retry system:')
    print(f'Initial _should_retry: {_should_retry(message)}')
    print(f'After increment 1: {_increment_retry(message)}')
    print(f'Should retry after 1: {_should_retry(message)}')
    print(f'After increment 2: {_increment_retry(message)}')
    print(f'Should retry after 2: {_should_retry(message)}')
    print(f'After increment 3: {_increment_retry(message)}')
    print(f'Should retry after 3: {_should_retry(message)}')
    
    print(f'\nTracker state: {_retry_tracker}')
    
    # Test different message (different chat_id)
    message2 = SimpleNamespace()
    message2.chat_id = 67890
    message2.message_thread_id = None
    
    print(f'\nNew message _should_retry: {_should_retry(message2)}')
    print(f'Original message _should_retry: {_should_retry(message)}')
