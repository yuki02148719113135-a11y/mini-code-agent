import time
from collections import defaultdict, deque

LIMIT_PER_MINUTE = 5  # README の「利用制限」と一致させること
_calls = defaultdict(deque)


def check(api_key: str):
    now = time.time()
    q = _calls[api_key]
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= LIMIT_PER_MINUTE:
        retry_after = int(60 - (now - q[0])) + 1
        return 429, {"Retry-After": str(retry_after)}
    q.append(now)
    return 200, {}
