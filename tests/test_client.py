import pytest

from resilient import ApiError, Client, RetryExhausted


def scripted(*responses):
    """Transport that returns scripted (status, headers, body) tuples or raises exceptions."""
    calls = []
    it = iter(responses)

    def t(method, url, headers, body):
        calls.append((method, url, dict(headers)))
        r = next(it)
        if isinstance(r, Exception):
            raise r
        return r

    t.calls = calls
    return t


def client(t, **kw):
    sleeps = []
    c = Client(t, sleep=sleeps.append, rng=lambda: 1.0, **kw)
    c.sleeps = sleeps
    return c


def test_retries_503_then_succeeds():
    t = scripted((503, {}, None), (200, {}, {"ok": 1}))
    c = client(t)
    assert c.request("GET", "/x") == {"ok": 1}
    assert len(t.calls) == 2 and len(c.sleeps) == 1


def test_retry_after_is_respected():
    t = scripted((429, {"Retry-After": "7"}, None), (200, {}, "ok"))
    c = client(t)
    c.request("GET", "/x")
    assert c.sleeps[0] >= 7


def test_4xx_is_not_retried():
    t = scripted((404, {}, "nope"))
    with pytest.raises(ApiError) as e:
        client(t).request("GET", "/x")
    assert e.value.status == 404 and len(t.calls) == 1


def test_gives_up_after_max_attempts():
    t = scripted(*[(500, {}, None)] * 3)
    with pytest.raises(RetryExhausted):
        client(t, max_attempts=3).request("GET", "/x")
    assert len(t.calls) == 3


def test_post_reuses_one_idempotency_key_across_retries():
    t = scripted((502, {}, None), (200, {}, "ok"))
    client(t).request("POST", "/pay", body={})
    keys = {c[2]["Idempotency-Key"] for c in t.calls}
    assert len(keys) == 1


def test_post_connection_error_is_retried_because_it_has_a_key():
    t = scripted(ConnectionError("reset"), (200, {}, "ok"))
    assert client(t).request("POST", "/pay") == "ok"


def test_delay_is_capped_and_jittered():
    c = Client(lambda *a: None, base=1, cap=10, rng=lambda: 0.5)
    assert c.delay(0) == 0.5
    assert c.delay(20) == 5.0  # cap 10 * 0.5


def test_pagination_yields_all_items():
    t = scripted((200, {}, {"items": [1, 2], "next_cursor": "a"}),
                 (200, {}, {"items": [3], "next_cursor": None}))
    assert list(client(t).paginate("/things")) == [1, 2, 3]
    assert t.calls[1][1] == "/things?cursor=a"
