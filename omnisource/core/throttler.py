# path: omnisource/core/throttler.py
from __future__ import annotations

import asyncio
import time
from collections import deque, defaultdict
from dataclasses import dataclass
from typing import Dict


@dataclass
class RateLimit:
    rps: float  # requests per second
    rpm: float  # requests per minute


DEFAULT_LIMITS: Dict[str, RateLimit] = {
    "yandex.com": RateLimit(rps=0.5, rpm=20),
    "duckduckgo.com": RateLimit(rps=1.0, rpm=30),
    "reddit.com": RateLimit(rps=0.3, rpm=10),
    "*": RateLimit(rps=2.0, rpm=60),
}


class GlobalThrottler:
    """Singleton throttler for domain-based rate limiting."""

    _instance: GlobalThrottler | None = None

    def __new__(cls) -> GlobalThrottler:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init()
        return cls._instance

    def _init(self) -> None:
        self._locks: Dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._request_times: Dict[str, deque[float]] = defaultdict(deque)

    def _get_limit(self, domain: str) -> RateLimit:
        for key in DEFAULT_LIMITS:
            if key != "*" and key in domain:
                return DEFAULT_LIMITS[key]
        return DEFAULT_LIMITS["*"]

    async def acquire(self, domain: str) -> None:
        """Block until request is allowed for this domain."""
        lock = self._locks[domain]

        async with lock:
            now = time.time()
            limit = self._get_limit(domain)
            times = self._request_times[domain]

            # Clean old entries (older than 60 seconds)
            while times and now - times[0] > 60:
                times.popleft()

            # Enforce RPM
            if len(times) >= limit.rpm:
                sleep_time = 60 - (now - times[0])
                await asyncio.sleep(max(sleep_time, 0))

            # Enforce RPS
            if times:
                delta = now - times[-1]
                min_interval = 1.0 / limit.rps if limit.rps > 0 else 0
                if delta < min_interval:
                    await asyncio.sleep(min_interval - delta)

            times.append(time.time())