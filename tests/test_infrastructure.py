import pytest

from li_crawler.adapters.outbound.queues import InMemoryTaskQueue
from li_crawler.adapters.outbound.throttle import PoliteThrottle
from li_crawler.domain import CrawlTask


class FakeClock:
    def __init__(self):
        self.now = 0.0
        self.slept: list[float] = []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.slept.append(seconds)
        self.now += seconds


def test_throttle_waits_between_requests():
    clock = FakeClock()
    throttle = PoliteThrottle(5, 5, 100, sleep=clock.sleep, clock=clock)

    throttle.wait()
    throttle.wait()
    clock.now += 2
    throttle.wait()

    assert clock.slept == [5, 3]


def test_throttle_enforces_hourly_cap():
    clock = FakeClock()
    throttle = PoliteThrottle(0, 0, 2, sleep=clock.sleep, clock=clock)

    throttle.wait()
    throttle.wait()
    throttle.wait()

    assert clock.slept == [3600]


def test_throttle_validates_bounds():
    with pytest.raises(ValueError):
        PoliteThrottle(5, 1, 10)


def test_queue_deduplicates_first_attempts_but_allows_retries():
    queue = InMemoryTaskQueue()

    assert queue.push(CrawlTask(slug="a"))
    assert not queue.push(CrawlTask(slug="a"))
    assert queue.push(CrawlTask(slug="a", attempts=1))
    assert len(queue) == 2
    assert queue.pop().attempts == 0
    assert queue.pop().attempts == 1
    assert queue.pop() is None
