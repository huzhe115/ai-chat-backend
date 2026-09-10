from app import redis_client as rc


async def test_redis_circuit_breaker_skips_after_failure(monkeypatch):
    """第一次失败真试,之后 30 秒内直接跳过,不再碰网络。"""
    rc.redis_client._down_until = 0.0  # 复位,别受其他测试影响
    calls = 0

    async def boom(key):
        nonlocal calls
        calls += 1
        raise OSError("redis down")

    monkeypatch.setattr(rc.redis_client._client, "get", boom)

    assert await rc.redis_client.get("k") is None  # 这次真试,失败后熔断
    assert await rc.redis_client.get("k") is None  # 这次被跳过
    assert calls == 1

    rc.redis_client._down_until = 0.0  # 复位,别影响其他测试
