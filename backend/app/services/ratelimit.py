"""Sliding-window rate limiting, in memory and per process.

Good enough for a single API container. With several replicas each keeps its own counts,
so the effective limit is multiplied; move to Postgres or Redis before scaling out.
"""

import math
import time
from collections import defaultdict, deque

from app.errors import AppError


class RateLimiter:
    def __init__(self, name: str, limit: int, window_seconds: int) -> None:
        self.name = name
        self.limit = limit
        self.window = window_seconds
        self._events: dict[str, deque[float]] = defaultdict(deque)

    def _prune(self, key: str, now: float) -> deque[float]:
        events = self._events[key]
        while events and events[0] <= now - self.window:
            events.popleft()
        if not events:
            self._events.pop(key, None)
            return deque()
        return events

    def check(self, key: str) -> None:
        """Raise 429 if `key` already used up its allowance in the current window."""
        now = time.monotonic()
        events = self._prune(key, now)
        if len(events) >= self.limit:
            retry_after = max(1, math.ceil(events[0] + self.window - now))
            raise AppError(
                429,
                "rate_limited",
                "Too many attempts. Try again later.",
                details={"retry_after": retry_after},
                headers={"Retry-After": str(retry_after)},
            )

    def record(self, key: str) -> None:
        now = time.monotonic()
        self._prune(key, now)
        self._events[key].append(now)

    def hit(self, key: str) -> None:
        """check() then record(): for limits that count every request, not only failures."""
        self.check(key)
        self.record(key)

    def reset(self, key: str) -> None:
        self._events.pop(key, None)

    def clear(self) -> None:
        self._events.clear()


# Failed logins are counted; a success clears the per-email counter.
login_by_ip = RateLimiter("login_ip", limit=20, window_seconds=15 * 60)
login_by_email = RateLimiter("login_email", limit=5, window_seconds=15 * 60)
# Every request counts.
register_by_ip = RateLimiter("register_ip", limit=10, window_seconds=3600)
email_by_ip = RateLimiter("email_ip", limit=10, window_seconds=3600)
email_by_address = RateLimiter("email_address", limit=3, window_seconds=3600)
google_failures_by_ip = RateLimiter("google_ip", limit=20, window_seconds=15 * 60)
# Search runs trigram scans: generous for a person typing, a brake for a script.
search_by_ip = RateLimiter("search_ip", limit=120, window_seconds=60)

ALL = [login_by_ip, login_by_email, register_by_ip, email_by_ip, email_by_address, google_failures_by_ip, search_by_ip]


def reset_all() -> None:
    for limiter in ALL:
        limiter.clear()
