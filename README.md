# api-client-resilience

A small, dependency-free API client pattern for calling a customer's or vendor's HTTP API when it is slow, rate-limited or flaky. The transport is injected, so the logic is tested without a network.

Synthetic. No real API is called.

## Behaviour

- **Retries** `429, 500, 502, 503, 504` and connection errors; **never** other 4xx (retrying a 404 or 400 cannot help).
- **Exponential backoff with full jitter**, capped. Jitter stops many clients retrying in lockstep.
- **Honours `Retry-After`** when the server asks for a longer wait.
- **POST is only retried safely:** the client adds one `Idempotency-Key` per call and reuses it on every attempt, so a retried charge or create cannot be applied twice (if the server supports the header).
- **Cursor pagination** as a generator, yielding items rather than pages.
- Raises `ApiError` for non-retryable failures and `RetryExhausted` when attempts run out.

## Run the tests

```
pip install pytest
python -m pytest -q
```

Eight tests: retry then success, `Retry-After`, no retry on 404, give-up, one key across POST retries, POST connection-error retry, capped jittered delay, pagination.

## Not done

- No circuit breaker, no per-host rate limiter, no total-time budget (only an attempt count).
- No real HTTP transport is included; plug in `requests`, `httpx` or `urllib`.
- The idempotency header name varies by provider and only helps if the server honours it.
- Timeouts belong in the transport and are not set here.

MIT licensed.
