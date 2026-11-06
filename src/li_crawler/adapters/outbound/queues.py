"""Task queue adapters: in-memory (default) and Redis (for distributed workers)."""

from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING

from li_crawler.domain import CrawlTask

if TYPE_CHECKING:
    from redis import Redis


class InMemoryTaskQueue:
    def __init__(self) -> None:
        self._tasks: deque[CrawlTask] = deque()
        self._seen: set[str] = set()

    def push(self, task: CrawlTask) -> bool:
        if task.attempts == 0:
            if task.slug in self._seen:
                return False
            self._seen.add(task.slug)
        self._tasks.append(task)
        return True

    def pop(self) -> CrawlTask | None:
        return self._tasks.popleft() if self._tasks else None

    def __len__(self) -> int:
        return len(self._tasks)


class RedisTaskQueue:
    """FIFO list of JSON tasks plus a SET for de-duplication.

    Several crawler processes can share one Redis and consume the same queue.
    """

    def __init__(self, client: Redis, namespace: str = "li_crawler") -> None:
        self._redis = client
        self._queue_key = f"{namespace}:tasks"
        self._seen_key = f"{namespace}:seen"

    @classmethod
    def from_url(cls, url: str, namespace: str = "li_crawler") -> RedisTaskQueue:
        from redis import Redis  # optional dependency

        return cls(Redis.from_url(url, decode_responses=True), namespace)

    def push(self, task: CrawlTask) -> bool:
        if task.attempts == 0 and not self._redis.sadd(self._seen_key, task.slug):
            return False
        self._redis.rpush(self._queue_key, task.model_dump_json())
        return True

    def pop(self) -> CrawlTask | None:
        raw = self._redis.lpop(self._queue_key)
        return CrawlTask.model_validate_json(raw) if raw else None

    def __len__(self) -> int:
        return int(self._redis.llen(self._queue_key))
