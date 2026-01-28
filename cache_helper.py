from __future__ import annotations

import time
from typing import Any


class TTLCache:
    def __init__(self) -> None:
        self._data: dict[Any, dict[str, Any]] = {}

    def _now(self) -> float:
        return time.monotonic()

    def get(self, key: Any) -> Any | None:
        entry = self._data.get(key)
        if not entry:
            return None
        if entry["expires_at"] <= self._now():
            self._data.pop(key, None)
            return None
        return entry["value"]

    def get_with_ttl(self, key: Any) -> tuple[Any | None, float | None]:
        entry = self._data.get(key)
        if not entry:
            return None, None
        ttl = entry["expires_at"] - self._now()
        if ttl <= 0:
            self._data.pop(key, None)
            return None, None
        return entry["value"], ttl

    def set(self, key: Any, value: Any, ttl_seconds: float) -> None:
        self._data[key] = {
            "value": value,
            "expires_at": self._now() + ttl_seconds,
        }

    def delete(self, key: Any) -> None:
        self._data.pop(key, None)
