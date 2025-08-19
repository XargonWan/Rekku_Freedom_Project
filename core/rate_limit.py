import time
from collections import defaultdict, deque
from core.config import TELEGRAM_TRAINER_ID


class _RateLimiter:
    def __init__(self):
        self.records = defaultdict(deque)

    def is_allowed(self, key: str, user_id: int, max_messages: int, window_seconds: int, trainer_fraction: float, consume: bool = True) -> bool:
        now = time.time()
        dq = self.records[(key, user_id)]
        while dq and now - dq[0] > window_seconds:
            dq.popleft()

        quota_trainer = int(max_messages * trainer_fraction)
        quota_other = max_messages - quota_trainer
        quota = quota_trainer if user_id == TELEGRAM_TRAINER_ID else quota_other

        if len(dq) < quota:
            if consume:
                dq.append(now)
            return True
        return False


_limiter = _RateLimiter()


def is_allowed(key: str, user_id: int, max_messages: int, window_seconds: int, trainer_fraction: float, consume: bool = True) -> bool:
    """Check if a message from ``user_id`` is allowed."""
    return _limiter.is_allowed(key, user_id, max_messages, window_seconds, trainer_fraction, consume)

