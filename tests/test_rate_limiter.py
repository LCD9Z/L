# -*- coding: utf-8 -*-
"""令牌桶限流器测试（data_fetcher._TokenBucket）。

验证：突发容量、补充速率、可关闭、线程安全、超时放行。
"""
import threading
import time

from data_fetcher import _TokenBucket


def test_burst_is_instant():
    """桶内令牌应立即可用，不产生等待。"""
    tb = _TokenBucket(rate=4, burst=4)
    t0 = time.monotonic()
    for _ in range(4):
        tb.acquire()
    assert time.monotonic() - t0 < 0.1


def test_refill_rate_is_enforced():
    """令牌耗尽后按 rate 补充：4 tokens / 4 per sec ≈ 1s。"""
    tb = _TokenBucket(rate=4, burst=4)
    for _ in range(4):
        tb.acquire()
    t0 = time.monotonic()
    for _ in range(4):
        tb.acquire()
    elapsed = time.monotonic() - t0
    assert 0.8 <= elapsed <= 1.4, f"补充速率异常: {elapsed:.2f}s"


def test_disabled_when_rate_zero():
    """rate<=0 时应关闭限流，acquire 立即返回。"""
    tb = _TokenBucket(rate=0, burst=16)
    assert tb.enabled is False
    t0 = time.monotonic()
    for _ in range(100):
        tb.acquire()
    assert time.monotonic() - t0 < 0.05


def test_thread_safety_no_token_overissue():
    """并发下不应超发令牌：40 请求 @ 20/s burst 20 应约 1s。"""
    tb = _TokenBucket(rate=20, burst=20)
    done = []

    def worker():
        for _ in range(10):
            tb.acquire()
            done.append(1)

    threads = [threading.Thread(target=worker) for _ in range(4)]
    t0 = time.monotonic()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    elapsed = time.monotonic() - t0
    assert len(done) == 40
    assert elapsed >= 0.7, f"并发下未限速: {elapsed:.2f}s"


def test_timeout_releases_without_deadlock():
    """timeout 到期应放行，不永久阻塞。"""
    tb = _TokenBucket(rate=1, burst=1)
    tb.acquire()
    t0 = time.monotonic()
    tb.acquire(timeout=0.1)
    assert time.monotonic() - t0 < 0.5


def test_default_limiter_is_configured():
    """模块级默认限流器应与环境变量配置一致（未设时默认 8 req/s）。"""
    import os
    import data_fetcher
    expected = float(os.environ.get("FETCH_RATE_PER_SEC", "8"))
    assert data_fetcher._RATE_LIMITER.rate == expected
    assert data_fetcher._RATE_LIMITER.burst >= 1
    # enabled 与 rate 必须一致：rate>0 才限流
    assert data_fetcher._RATE_LIMITER.enabled == (expected > 0)
