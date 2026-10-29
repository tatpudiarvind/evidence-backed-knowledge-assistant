"""Rate limits counted in the API process's memory (Phase 5).

Each limiter lets a key make a set number of requests within any sliding window. The counts
reset when the API restarts, and separate API processes would each keep their own, which suits
this local app's single process.
"""

import math
import threading
import time
from collections import OrderedDict, deque
from collections.abc import Callable
from dataclasses import dataclass

from app.core.config import Settings

# Beyond this many keys the least recently seen are forgotten, so memory use stays bounded.
MAX_TRACKED_KEYS = 10_000

Clock = Callable[[], float]


@dataclass(frozen=True)
class RateLimit:
    max_requests: int
    window_seconds: int


class SlidingWindowLimiter:
    """Allows each key at most `max_requests` requests within any `window_seconds`.

    Refused requests aren't counted, so a client that waits as long as advised gets through.
    """

    def __init__(
        self,
        limit: RateLimit,
        *,
        clock: Clock = time.monotonic,
        max_keys: int = MAX_TRACKED_KEYS,
    ) -> None:
        self.limit = limit
        self._clock = clock
        self._max_keys = max_keys
        self._times: OrderedDict[str, deque[float]] = OrderedDict()
        self._lock = threading.Lock()

    def acquire(self, key: str) -> int | None:
        """Counts a request for `key` if it's allowed and returns None; otherwise returns the
        whole seconds until it would be allowed."""
        now = self._clock()
        with self._lock:
            times = self._times.get(key)
            if times is None:
                times = self._times[key] = deque()
                if len(self._times) > self._max_keys:
                    self._times.popitem(last=False)
            else:
                self._times.move_to_end(key)
            while times and times[0] <= now - self.limit.window_seconds:
                times.popleft()
            if len(times) >= self.limit.max_requests:
                return max(1, math.ceil(times[0] + self.limit.window_seconds - now))
            times.append(now)
            return None


class RateLimits:
    """The API's rate limits, as its settings configure them."""

    def __init__(self, settings: Settings, *, clock: Clock = time.monotonic) -> None:
        self.enabled = settings.rate_limits_enabled
        self.sign_in = SlidingWindowLimiter(
            RateLimit(settings.sign_in_attempts_per_minute, 60), clock=clock
        )
        self.registration = SlidingWindowLimiter(
            RateLimit(settings.registration_attempts_per_hour, 3600), clock=clock
        )
        self.questions = SlidingWindowLimiter(
            RateLimit(settings.questions_per_minute, 60), clock=clock
        )


def format_wait(seconds: int) -> str:
    """Seconds under a minute, otherwise whole minutes rounded up: "1 second", "2 minutes"."""
    if seconds < 60:
        return f"{seconds} second{'' if seconds == 1 else 's'}"
    minutes = math.ceil(seconds / 60)
    return f"{minutes} minute{'' if minutes == 1 else 's'}"
