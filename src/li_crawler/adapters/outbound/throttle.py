"""Rate limiting adapter: random delay between requests + hourly cap."""

from __future__ import annotations

import logging
import random
import time
from collections import deque
from collections.abc import Callable

logger = logging.getLogger(__name__)

_HOUR = 3600.0


class PoliteThrottle:
    """Waits a random `min_delay..max_delay` seconds between requests and never
    exceeds `max_per_hour` requests in any sliding one-hour window."""

    def __init__(
        self,
        min_delay: float,
        max_delay: float,
        max_per_hour: int,
        *,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        rng: random.Random | None = None,
    ) -> None:
        if not 0 <= min_delay <= max_delay:
            raise ValueError("Expected 0 <= min_delay <= max_delay")
        self._min_delay = min_delay
        self._max_delay = max_delay
        self._max_per_hour = max_per_hour
        self._sleep = sleep
        self._clock = clock
        self._rng = rng or random.Random()
        self._history: deque[float] = deque()

    def wait(self) -> None:
        self._respect_hourly_cap()
        if self._history:
            delay = self._rng.uniform(self._min_delay, self._max_delay)
            remaining = delay - (self._clock() - self._history[-1])
            if remaining > 0:
                self._sleep(remaining)
        self._history.append(self._clock())

    def _respect_hourly_cap(self) -> None:
        now = self._clock()
        while self._history and now - self._history[0] >= _HOUR:
            self._history.popleft()
        if len(self._history) >= self._max_per_hour:
            pause = _HOUR - (now - self._history[0])
            logger.warning("Hourly request cap reached; pausing %.0f s", pause)
            self._sleep(pause)
            self._history.popleft()


class NoThrottle:
    def wait(self) -> None:
        return None
