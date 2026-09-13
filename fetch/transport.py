# -*- coding: utf-8 -*-
"""HTTP 传输层：SSL context 复用、内存缓存、令牌桶限流、统一 GET。

由 data_fetcher.py 拆分而来（对外 API 不变，实现下沉到 fetch/ 包）。
"""
import os
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional, Tuple



# 模块级 SSL context 复用：避免每次请求都重建（性能优化）
_SSL_CTX = ssl.create_default_context()



# 简易内存缓存：session 内避免重复请求同一行情/K线
_cache: Dict[str, Tuple[Any, float]] = {}
_cache_lock = threading.Lock()
_CACHE_TTL = 30  # 秒：行情缓存有效期，盘中 30s 足够刷新



def _cache_get(key: str) -> Optional[Any]:
    """从缓存读取，过期返回 None。"""
    with _cache_lock:
        item = _cache.get(key)
        if item and (time.time() - item[1]) < _CACHE_TTL:
            return item[0]
    return None



def _cache_set(key: str, value: Any) -> None:
    """写入缓存。"""
    with _cache_lock:
        _cache[key] = (value, time.time())



class _TokenBucket:
    """线程安全令牌桶限流器。

    以 rate 个/秒 的速率补充令牌，桶容量为 burst（允许的突发量）。
    每次请求前调用 acquire() 消耗一个令牌；令牌不足时按需 sleep 等待，
    避免连续快速打满东财/腾讯接口导致 IP 被限流或封禁。

    配置（环境变量）：
        FETCH_RATE_PER_SEC: 每秒允许请求数（默认 8；设为 0 关闭限流）
        FETCH_RATE_BURST:   突发容量（默认 16）
    """

    def __init__(self, rate, burst):
        self.rate = float(rate)
        self.burst = float(burst) if burst > 0 else 1.0
        self._tokens = self.burst
        self._last = time.monotonic()
        self._lock = threading.Lock()
        self.enabled = self.rate > 0

    def acquire(self, timeout=None):
        """获取一个令牌，返回实际等待秒数。rate<=0 时直接放行。

        timeout 为最长等待秒数；超时后放行（不阻塞主流程，避免死等）。
        """
        if not self.enabled:
            return 0.0
        deadline = None if timeout is None else time.monotonic() + timeout
        waited = 0.0
        while True:
            with self._lock:
                now = time.monotonic()
                elapsed = now - self._last
                self._last = now
                self._tokens = min(self.burst, self._tokens + elapsed * self.rate)
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return waited
                need = (1.0 - self._tokens) / self.rate
            if deadline is not None and time.monotonic() + need > deadline:
                return waited
            time.sleep(need)
            waited += need



# 全局限流器：默认 8 req/s、突发 16；设 FETCH_RATE_PER_SEC=0 可关闭
_RATE_LIMITER = _TokenBucket(
    float(os.environ.get("FETCH_RATE_PER_SEC", "8")),
    float(os.environ.get("FETCH_RATE_BURST", "16")),
)



_HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0 Safari/537.36"
    ),
    "Referer": "https://quote.eastmoney.com/",
}



def _http_get(url, headers=None, decode="utf-8", retries=3, timeout=8):
    """GET 请求，返回文本；失败返回 None。复用模块级 SSL context。

    每次尝试前先经令牌桶限流，避免高频请求触发接口封禁。
    """
    hd = dict(_HTTP_HEADERS)
    if headers:
        hd.update(headers)
    ctx = _SSL_CTX
    for i in range(retries):
        _RATE_LIMITER.acquire()
        try:
            req = urllib.request.Request(url, headers=hd)
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
                raw = resp.read()
            return raw.decode(decode, errors="replace")
        except Exception:
            if i < retries - 1:
                time.sleep(0.5)
    return None
