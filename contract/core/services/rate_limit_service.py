"""A per-account request budget on the shared cache, for endpoints that start expensive work (a model call)."""
import time

from django.core.cache import cache


class RateLimited(Exception):
    def __init__(self, retry_after):
        super().__init__(f'Bạn gửi quá nhiều yêu cầu. Hãy thử lại sau {retry_after} giây.')
        self.retry_after = retry_after


def check(user, scope, per_minute):
    """Count one request of this user in the current minute; RateLimited once more than per_minute were made.
    per_minute <= 0 means no limit."""
    if per_minute <= 0:
        return
    now = time.time()
    window = int(now // 60)
    key = f'rate:{scope}:{getattr(user, "pk", None) or "anon"}:{window}'
    if cache.add(key, 1, 90):
        count = 1
    else:
        try:
            count = cache.incr(key)
        except ValueError:  # expired between add and incr
            cache.set(key, 1, 90)
            count = 1
    if count > per_minute:
        raise RateLimited(max(1, int(60 - now % 60)))
