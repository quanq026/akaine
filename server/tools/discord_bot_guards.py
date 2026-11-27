"""Bounded interaction load policy and the process-wide B30 render slot."""
from __future__ import annotations

from collections import deque
from threading import BoundedSemaphore
import time


b30_slot = BoundedSemaphore(1)


class InteractionRateLimiter:
    """Called synchronously on the bot's event loop before dispatch."""

    def __init__(self) -> None:
        self._seen: dict[tuple[int, str], float] = {}
        self._windows: dict[str, deque[float]] = {}

    def admit(self, actor: int, action: str = "interaction", *, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        delay, maximum, period = (300, 5, 60) if action == "create" else (2, 20, 1)
        key = (int(actor), action)
        if now - self._seen.get(key, float("-inf")) < delay:
            return False
        window = self._windows.setdefault(action, deque())
        while window and now - window[0] >= period:
            window.popleft()
        if len(window) >= maximum:
            return False
        if len(self._seen) >= 4096:
            stale = [key for key, value in self._seen.items() if now - value >= 300]
            for key in stale:
                del self._seen[key]
            if len(self._seen) >= 4096:
                return False
        self._seen[key] = now
        window.append(now)
        return True
