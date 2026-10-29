"""In-memory token buckets for the API's rate limits."""

import math
from collections.abc import Callable, Hashable


class RateLimiter:
    """One token bucket per key: `burst` requests at once, refilled at `per_second`."""

    def __init__(
        self,
        burst: int,
        per_second: float,
        now: Callable[[], float],
        max_keys: int = 20_000,
    ):
        self.burst, self.rate, self.now, self.max_keys = float(burst), per_second, now, max_keys
        self.buckets: dict[Hashable, tuple[float, float]] = {}  # key -> (tokens, last seen)

    def take(self, key: Hashable) -> int:
        """Spend a token: 0 when allowed, else whole seconds until the next token."""
        t = self.now()
        tokens, last = self.buckets.get(key, (self.burst, t))
        tokens = min(self.burst, tokens + max(0.0, t - last) * self.rate)
        allowed = tokens >= 1
        self._store(key, tokens - 1 if allowed else tokens, t)
        return 0 if allowed else max(1, math.ceil((1 - tokens) / self.rate))

    def _store(self, key: Hashable, tokens: float, t: float) -> None:
        if key not in self.buckets and len(self.buckets) >= self.max_keys:
            self._prune(t)
        self.buckets[key] = (tokens, t)

    def _prune(self, t: float) -> None:
        # A bucket idle long enough to refill completely behaves exactly like a missing one.
        idle = self.burst / self.rate
        self.buckets = {k: v for k, v in self.buckets.items() if t - v[1] < idle}
        if len(self.buckets) >= self.max_keys:
            # Still full: keep the most limited half, so a flood of new keys cannot reset
            # the clients that are being throttled.
            emptiest = sorted(self.buckets.items(), key=lambda kv: kv[1][0])
            self.buckets = dict(emptiest[: self.max_keys // 2])
