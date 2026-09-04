import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable

from fastapi import HTTPException, Request


class SlidingWindowRateLimiter:
    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self._clock = clock
        self._requests: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str, *, limit: int, window_seconds: int) -> None:
        now = self._clock()
        cutoff = now - window_seconds
        with self._lock:
            requests = self._requests[key]
            while requests and requests[0] <= cutoff:
                requests.popleft()
            if len(requests) >= limit:
                retry_after = max(1, int(requests[0] + window_seconds - now) + 1)
                raise HTTPException(
                    status_code=429,
                    detail="Too many requests",
                    headers={"Retry-After": str(retry_after)},
                )
            requests.append(now)

    def reset(self) -> None:
        with self._lock:
            self._requests.clear()


limiter = SlidingWindowRateLimiter()


def client_key(request: Request, scope: str) -> str:
    # Do not trust forwarding headers unless a trusted proxy normalizes them.
    host = request.client.host if request.client else "unknown"
    return f"{scope}:{host}"


def enforce_rate_limit(
    request: Request, *, scope: str, limit: int, window_seconds: int
) -> None:
    limiter.check(
        client_key(request, scope), limit=limit, window_seconds=window_seconds
    )
