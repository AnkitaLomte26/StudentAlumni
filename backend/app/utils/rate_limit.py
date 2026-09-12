"""Bounded, process-local fixed-window limits for the single-worker deployment."""
from collections import OrderedDict
from threading import Lock
from time import monotonic
from math import ceil

class RateLimiter:
    def __init__(self):
        self.buckets = OrderedDict()
        self.lock = Lock()

    def clear(self):
        with self.lock:
            self.buckets.clear()

    def check(self, key, limit, seconds=60):
        stamp = monotonic()
        with self.lock:
            expired = [k for k, (_, until) in self.buckets.items() if until <= stamp]
            for k in expired:
                del self.buckets[k]
            count, until = self.buckets.get(key, (0, stamp + seconds))
            if count >= limit or (key not in self.buckets and len(self.buckets) >= 10000):
                return max(1, ceil(until - stamp))
            self.buckets[key] = (count + 1, until)
        return 0

limiter = RateLimiter()

