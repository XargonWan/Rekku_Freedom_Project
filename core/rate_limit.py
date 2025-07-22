import time
from collections import defaultdict, deque
from core.config import OWNER_ID


class _RateLimiter:
    def __init__(self):
        self.records = defaultdict(deque)

    def is_allowed(self, key: str, user_id: int, max_messages: int, window_seconds: int, owner_fraction: float, consume: bool = True) -> bool:
        now = time.time()
        dq = self.records[(key, user_id)]
        while dq and now - dq[0] > window_seconds:
            dq.popleft()

        quota_owner = int(max_messages * owner_fraction)
        quota_other = max_messages - quota_owner
        quota = quota_owner if user_id == OWNER_ID else quota_other

        if len(dq) < quota:
            if consume:
                dq.append(now)
            return True
        return False


_limiter = _RateLimiter()


def is_allowed(key: str, user_id: int, max_messages: int, window_seconds: int, owner_fraction: float, consume: bool = True) -> bool:
    """Check if a message from ``user_id`` is allowed."""
    return _limiter.is_allowed(key, user_id, max_messages, window_seconds, owner_fraction, consume)

