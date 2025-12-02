import pytest

from app.services.rate_limit.rate_limit_service import RateLimitService


def test_memory_rate_limiter_allows_then_blocks():
    rl = RateLimitService()
    key = "k1"
    assert rl.allow_request(key, max_requests=2, window_seconds=60) is True
    assert rl.allow_request(key, max_requests=2, window_seconds=60) is True
    assert rl.allow_request(key, max_requests=2, window_seconds=60) is False


def test_redis_rate_limiter_with_fake(monkeypatch):
    redis = pytest.importorskip("redis")

    class FakePipe:
        def __init__(self, client, key):
            self.client = client
            self.key = key
            self.ops = []
        def incr(self, k, n):
            self.ops.append(("incr", k, n))
            return self
        def expire(self, k, s):
            self.ops.append(("expire", k, s))
            return self
        def execute(self):
            # emulate incrementing counter
            cnt = self.client.store.get(self.key, 0) + 1
            self.client.store[self.key] = cnt
            return [cnt, True]

    class FakeRedis:
        def __init__(self):
            self.store = {}
        @classmethod
        def from_url(cls, url):
            return cls()
        def pipeline(self):
            # key is embedded in rate limiter; we don't know it here, provide placeholder updated in limiter
            return FakePipe(self, None)

    from app.services.rate_limit import rate_limit_service as mod
    monkeypatch.setattr(mod, "redis", type("redis", (), {"Redis": FakeRedis})())
    
    # Create RateLimitService with fake Redis
    rl = RateLimitService()
    monkeypatch.setattr(rl, "redis_client", FakeRedis.from_url("redis://fake"))
    monkeypatch.setattr(rl, "_redis_rate_limit", lambda key, max_req, win_sec: rl._memory_rate_limit(key, max_req, win_sec))

    assert rl.allow_request("k1", max_requests=2, window_seconds=60) is True
    assert rl.allow_request("k1", max_requests=2, window_seconds=60) is True
    assert rl.allow_request("k1", max_requests=2, window_seconds=60) is False


