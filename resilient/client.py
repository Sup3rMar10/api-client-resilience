"""API client pattern: retries with backoff + jitter, Retry-After, safe-retry rules, pagination.

The transport is injected: transport(method, url, headers, body) -> (status, headers, body).
That keeps the logic testable without a network and usable with any HTTP library.
"""
import random
import time
import uuid

RETRYABLE = {429, 500, 502, 503, 504}
IDEMPOTENT = {"GET", "PUT", "DELETE", "HEAD"}


class ApiError(Exception):
    def __init__(self, status, body):
        super().__init__(f"HTTP {status}")
        self.status, self.body = status, body


class RetryExhausted(ApiError):
    pass


class Client:
    def __init__(self, transport, max_attempts=5, base=0.5, cap=30.0,
                 sleep=time.sleep, rng=random.random):
        self.transport, self.max_attempts = transport, max_attempts
        self.base, self.cap, self.sleep, self.rng = base, cap, sleep, rng

    def delay(self, attempt, retry_after=None):
        """Full jitter: random in [0, min(cap, base*2^attempt)]. A server Retry-After wins if longer."""
        backoff = self.rng() * min(self.cap, self.base * 2 ** attempt)
        return max(backoff, float(retry_after)) if retry_after else backoff

    def request(self, method, url, body=None, headers=None):
        headers = dict(headers or {})
        if method == "POST":
            # One key for all attempts of this call: the server can dedupe a retried POST.
            headers.setdefault("Idempotency-Key", str(uuid.uuid4()))
        safe = method in IDEMPOTENT or "Idempotency-Key" in headers
        last = None
        for attempt in range(self.max_attempts):
            try:
                status, rh, rb = self.transport(method, url, headers, body)
            except (ConnectionError, TimeoutError) as e:
                if not safe or attempt == self.max_attempts - 1:
                    raise
                self.sleep(self.delay(attempt))
                last = e
                continue
            if status < 400:
                return rb
            if status not in RETRYABLE or not safe:
                raise ApiError(status, rb)
            last = ApiError(status, rb)
            if attempt < self.max_attempts - 1:
                self.sleep(self.delay(attempt, rh.get("Retry-After")))
        raise RetryExhausted(getattr(last, "status", 0), getattr(last, "body", None))

    def paginate(self, url, cursor_param="cursor"):
        """Follow next_cursor until it is empty. Yields items, not pages."""
        cursor = None
        while True:
            u = url if cursor is None else f"{url}{'&' if '?' in url else '?'}{cursor_param}={cursor}"
            page = self.request("GET", u)
            yield from page["items"]
            cursor = page.get("next_cursor")
            if not cursor:
                return
