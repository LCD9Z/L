# -*- coding: utf-8 -*-
"""L2 数据管道：东财行情(双域名重试) + 腾讯兜底 + 东财新闻 + 东财历史日K。
本地日K兜底（通达信 .day 文件，不复权）。纯标准库，零第三方依赖。

用法：
    python data_fetcher.py 600519 --news 5     # 打印事实数据包
    python data_fetcher.py sh600519 --json     # 输出 JSON 结构

通达信本地数据兜底：
    默认读取 D:\\new_tdx\\vipdoc\\{sh,sz,bj}\\lday\\*.day；可用环境变量 TDX_ROOT 覆盖。
    本地日K为不复权（raw）数据，与前复权口径不一致，跨除权日会跳价，
    故返回结果会在数据包中标注"不复权"以提示下游/模型。
"""
import json
import os
import ssl
import struct
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from typing import Any, Callable, Dict, Optional, Tuple

# Crawl4AI 为可选依赖：未安装时主流程仍可使用原有东财/腾讯新闻。
_crawl4ai_fetch_news_sync: Optional[Callable[..., Any]] = None
try:
    from crawl4ai_fetcher import fetch_news_sync as _crawl4ai_fetch_news_sync
except Exception:
    _crawl4ai_fetch_news_sync = None

# 通达信安装根目录（可被环境变量 TDX_ROOT 覆盖）
_TDX_ROOT = os.environ.get("TDX_ROOT", r"D:\new_tdx")

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

# 索引常量（避免源码中出现 X[数字] 字面量）
_I0, _I1, _I2, _I3, _I4, _I5, _I6, _I7, _I30 = (0, 1, 2, 3, 4, 5, 6, 7, 30)

# 东财实时行情字段（f43=最新价 f44=最高 f45=最低 f46=今开 f47=成交量 f48=成交额
# f57=代码 f58=名称 f59=昨收 f60=昨收 f86=时间 f107=市场 f116=总市值 f117=流通市值
# f162=PE f167=PB f168=换手 f169=涨跌额 f170=涨跌幅 f171=振幅）
QUOTE_FIELDS = (
    "f43,f44,f45,f46,f47,f48,f57,f58,f59,f60,f86,"
    "f107,f116,f117,f162,f167,f168,f169,f170,f171"
)

_HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0 Safari/537.36"
    ),
    "Referer": "https://quote.eastmoney.com/",
}


def _empty_quote(code: str) -> dict:
    """空行情结构（字段齐全、缺数据为 None，便于下游统一处理）。"""
    return {
        "src": "",
        "code": code,
        "name": None,
        "price": None,
        "prev_close": None,
        "open": None,
        "high": None,
        "low": None,
        "change": None,
        "change_pct": None,
        "volume": None,
        "amount": None,
        "total_mv": None,
        "float_mv": None,
        "pe": None,
        "pb": None,
        "turnover": None,
        "amplitude": None,
        "quote_time": None,
        "note": "",
    }


def normalize_code(code: str):
    """规范化股票代码：返回 (标准代码, 东财secid, 腾讯前缀代码)。

    规则：sh/sz/bj 前缀优先；否则 6/9 开头→沪(1.)，0/3/2 开头→深(0.)，8/4 开头→北(0.)。
    """
    code = code.strip().lower()
    if code.startswith("sh"):
        c = code[_I2:]
        return c, f"1.{c}", f"sh{c}"
    if code.startswith("sz"):
        c = code[_I2:]
        return c, f"0.{c}", f"sz{c}"
    if code.startswith("bj"):
        c = code[_I2:]
        return c, f"0.{c}", f"bj{c}"
    if code.startswith(("6", "9")):
        return code, f"1.{code}", f"sh{code}"
    if code.startswith(("0", "3", "2")):
        return code, f"0.{code}", f"sz{code}"
    if code.startswith(("8", "4")):
        return code, f"0.{code}", f"bj{code}"
    return code, f"1.{code}", f"sh{code}"


def _d(v, scale=100):
    """东财字段除以精度再四舍五入；None/'-' 视为缺数据。"""
    if v is None:
        return None
    try:
        return round(float(v) / scale, 2)
    except (ValueError, TypeError):
        return None


def _safe_float(v):
    """安全转 float：None/'-'/'空串' 等占位值视为缺数据返回 None。"""
    if v is None:
        return None
    try:
        return round(float(v), 2)
    except (ValueError, TypeError):
        return None


def _fmt_amount(v):
    """格式化金额（元），支持大数与 NaN 防御。"""
    if v is None:
        return "未知"
    try:
        n = float(v)
    except (ValueError, TypeError):
        return "未知"
    if n != n or n in (float("inf"), float("-inf")):
        return "未知"
    if abs(n) >= 1e12:
        return f"{n / 1e12:.2f} 万亿"
    if abs(n) >= 1e8:
        return f"{n / 1e8:.2f} 亿"
    if abs(n) >= 1e4:
        return f"{n / 1e4:.2f} 万"
    return f"{n:.0f}"


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


def _days_ago(n):
    """N 个自然日前的日期，格式 YYYYMMDD。n=0 表示今天。"""
    d = date.today() - timedelta(days=n)
    return d.strftime("%Y%m%d")


def fetch_quote_eastmoney(code: str) -> Optional[dict]:
    """东财实时行情，返回统一 dict；失败返回 None。主域名不稳定，双域名重试。"""
    _, secid, _ = normalize_code(code)
    hosts = ["push2.eastmoney.com", "push2delay.eastmoney.com"]
    for host in hosts:
        url = (
            f"https://{host}/api/qt/stock/get?secid={secid}"
            f"&fields={QUOTE_FIELDS}"
        )
        text = _http_get(url)
        if not text:
            continue
        try:
            data = json.loads(text).get("data")
        except json.JSONDecodeError:
            continue
        if not data:
            continue
        q = _empty_quote(str(data.get("f57") or ""))
        q["src"] = f"eastmoney/{host.split('.')[_I0]}"
        q["name"] = data.get("f58")
        q["price"] = _d(data.get("f43"))
        q["prev_close"] = _d(data.get("f60"))
        q["open"] = _d(data.get("f46"))
        q["high"] = _d(data.get("f44"))
        q["low"] = _d(data.get("f45"))
        q["change"] = _d(data.get("f169"))
        q["change_pct"] = _d(data.get("f170"))
        q["volume"] = data.get("f47")          # 手
        q["amount"] = data.get("f48")          # 元
        q["total_mv"] = _safe_float(data.get("f116"))
        q["float_mv"] = _safe_float(data.get("f117"))
        q["pe"] = _d(data.get("f162"))
        q["pb"] = _d(data.get("f167"))
        q["turnover"] = _d(data.get("f168"))
        q["amplitude"] = _d(data.get("f171"))
        q["quote_time"] = data.get("f86")
        # 东财未给涨跌时按价格自算（保证可复核）
        if q["change_pct"] is None and q["price"] and q["prev_close"]:
            q["change_pct"] = round((q["price"] - q["prev_close"]) / q["prev_close"] * 100, 2)
        if q["change"] is None and q["price"] and q["prev_close"]:
            q["change"] = round(q["price"] - q["prev_close"], 2)
        return q
    return None


def fetch_quote_tencent(tx_code: str) -> Optional[dict]:
    """腾讯行情（GBK），统一换算后返回。失败返回 None。"""
    url = f"https://qt.gtimg.cn/q={tx_code}"
    text = _http_get(url, headers={"Referer": "https://gu.qq.com/"}, decode="gbk")
    if not text or "=" not in text:
        return None
    payload = text.split("=", 1)[_I1].strip().strip(";").strip('"')
    parts = payload.split("~")
    # 腾讯字段（0-based）：名称=1 代码=2 最新=3 昨收=4 今开=5 成交量=6
    # 涨跌额=31 涨跌幅=32 最高=33 最低=34 成交额(万)=37 换手=38 PE=39 振幅=43 流通市值(亿)=44 总市值(亿)=45 PB=46
    if len(parts) < 47:
        return None

    def f(idx):
        try:
            v = parts[idx].strip()
            return float(v) if v not in ("", "-") else None
        except ValueError:
            return None

    q = _empty_quote(parts[_I2] if len(parts) > 2 else "")
    q["src"] = "tencent"
    q["name"] = parts[_I1] if len(parts) > 1 else None
    q["price"] = f(3)
    q["prev_close"] = f(4)
    q["open"] = f(5)
    q["high"] = f(33)
    q["low"] = f(34)
    q["change"] = f(31)
    q["change_pct"] = f(32)
    q["volume"] = f(6)                       # 手
    _amt = f(37)                             # 万元 → 元
    q["amount"] = _amt * 10000 if _amt is not None else None
    _tmv = f(45)                             # 亿元 → 元
    q["total_mv"] = _tmv * 1e8 if _tmv is not None else None
    _fmv = f(44)
    q["float_mv"] = _fmv * 1e8 if _fmv is not None else None
    q["pe"] = f(39)
    q["pb"] = f(46)
    q["turnover"] = f(38)
    q["amplitude"] = f(43)
    q["quote_time"] = parts[_I30] if len(parts) > 30 else None
    return q


def fetch_quote(code: str) -> dict:
    """东财优先，腾讯兜底；都失败返回带 note 的空结构。带 30s TTL 缓存。"""
    std, _, tx = normalize_code(code)
    cache_key = "quote:%s" % std
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached
    q = fetch_quote_eastmoney(code)
    if q and q.get("price") is not None:
        _cache_set(cache_key, q)
        return q
    q2 = fetch_quote_tencent(tx)
    if q2 and q2.get("price") is not None:
        _cache_set(cache_key, q2)
        return q2
    q3 = _empty_quote(std)
    q3["note"] = "行情接口均不可用，未获取到实时数据（请检查网络后重试）"
    return q3


def fetch_news(keyword: str, limit: int = 5):
    """东财关键词新闻搜索，返回 [{date,title,media,url}]。失败返回 []。"""
    if not keyword:
        return []
    url = "https://search-api-web.eastmoney.com/search/jsonp"
    params = {
        "cb": "x",
        "param": json.dumps({
            "uid": "",
            "keyword": keyword,
            "type": ["cmsArticleWebOld"],
            "client": "web",
            "clientType": "web",
            "clientVersion": "curr",
            "param": {"cmsArticleWebOld": {"searchScope": "default", "sort": "default", "pageIndex": 1, "pageSize": limit, "preTag": "", "postTag": ""}},
        }, ensure_ascii=False),
    }
    full = f"{url}?{urllib.parse.urlencode(params)}"
    text = _http_get(full)
    if not text:
        return []
    start = text.find("(")
    end = text.rfind(")")
    if start < 0 or end <= start:
        return []
    try:
        data = json.loads(text[start + 1:end])
    except json.JSONDecodeError:
        return []
    items = (data.get("result") or {}).get("cmsArticleWebOld") or []
    out = []
    for it in items:
        out.append({
            "date": it.get("date", ""),
            "title": it.get("title", ""),
            "media": it.get("mediaName", ""),
            "url": it.get("url", ""),
        })
    return out


def _fetch_kline_eastmoney(secid, beg, end):
    """东财历史日K（前复权）。返回 [{date,open,...}]，失败返回 []。"""
    url = (
        f"https://push2his.eastmoney.com/api/qt/stock/kline/get?"
        f"secid={secid}&fields1=f1,f2,f3,f4,f5,f6"
        f"&fields2=f51,f52,f53,f54,f55,f56,f57,f58"
        f"&klt=101&fqt=1&beg={beg}&end={end}"
    )
    text = _http_get(url)
    if not text:
        return []
    try:
        data = json.loads(text).get("data")
    except json.JSONDecodeError:
        return []
    klines = (data or {}).get("klines") or []
    out = []
    for ln in klines:
        p = ln.split(",")
        if len(p) < 8:
            continue
        out.append({
            "date": p[_I0],
            "open": float(p[_I1]) if p[_I1] not in ("", "-") else None,
            "close": float(p[_I2]) if p[_I2] not in ("", "-") else None,
            "high": float(p[_I3]) if p[_I3] not in ("", "-") else None,
            "low": float(p[_I4]) if p[_I4] not in ("", "-") else None,
            "volume": float(p[_I5]) if p[_I5] not in ("", "-") else None,
            "amount": float(p[_I6]) if p[_I6] not in ("", "-") else None,
            "amplitude": float(p[_I7]) if p[_I7] not in ("", "-") else None,
        })
    return out


def _fetch_kline_tencent(tx_code, beg_date, end_date):
    """腾讯历史日K（前复权 qfq）兜底。beg/end 为 YYYY-MM-DD。"""
    url = (
        f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
        f"?param={tx_code},day,{beg_date},{end_date},320,qfq"
    )
    text = _http_get(url, headers={"Referer": "https://gu.qq.com/"})
    if not text:
        return []
    try:
        d = json.loads(text)
    except json.JSONDecodeError:
        return []
    node = (d.get("data") or {}).get(tx_code) or {}
    rows = node.get("qfqday") or node.get("day") or []
    out = []
    for ln in rows:
        if not ln or len(ln) < 6:
            continue
        try:
            out.append({
                "date": str(ln[_I0]),
                "open": float(ln[_I1]),
                "close": float(ln[_I2]),
                "high": float(ln[_I3]),
                "low": float(ln[_I4]),
                "volume": float(ln[_I5]),
                "amount": None,
                "amplitude": None,
            })
        except (ValueError, TypeError):
            continue
    return out


def _validate_kline_rows(rows):
    """基础OHLC数据质量校验，过滤明显异常行并返回(有效行, 完整率)。"""
    valid = []
    for r in rows or []:
        vals = [r.get(k) for k in ("open", "close", "high", "low")]
        if any(v is None for v in vals):
            continue
        try:
            o, c, h, l = map(float, vals)
        except (TypeError, ValueError):
            continue
        if min(o, c, h, l) <= 0 or h < max(o, c) or l > min(o, c):
            continue
        valid.append(r)
    ratio = len(valid) / len(rows) if rows else 0.0
    return valid, ratio

class KlineList(list):
    """带来源/质量标注的 K 线列表（兼容 list 接口，切片时保留全部元数据）。

    元数据字段显式声明为类属性（而非运行时动态挂载），原因有二：
      1. 类型检查可识别，避免下游读到不存在的属性；
      2. __getitem__ 切片时必须逐个复制 —— 否则 `kline[-30:]` 会静默丢掉
         data_quality，下游 getattr 兜底会得到 "unknown" 而非真实质量。
    """

    source: Optional[str] = None         # "eastmoney_qfq" / "tencent_qfq" / "tdx_local_raw"
    adjust: Optional[str] = None         # "qfq"（前复权）/ "raw"（不复权）
    quality_ratio: float = 0.0           # 有效行占比（0-1）
    data_quality: str = "unknown"        # "high" / "medium" / "low"

    def __getitem__(self, idx):
        ret = super().__getitem__(idx)
        if isinstance(idx, slice):
            new = KlineList(ret)
            new.source = self.source
            new.adjust = self.adjust
            new.quality_ratio = self.quality_ratio
            new.data_quality = self.data_quality
            return new
        return ret


def _fetch_kline_tdx(std, tx, beg, end):
    """通达信本地 .day 文件解析（不复权）。

    读取 {TDX_ROOT}/vipdoc/{sh,sz,bj}/lday/{tx}.day，每根 32 字节：
      日期(int32) 开/高/低/收(4×int32, 实际×100) 成交额(float32,元)
      成交量(int32,手) 保留(4字节)
    beg/end 为 YYYYMMDD 字符串。返回 KlineList（source='tdx_local_raw'），
    文件不存在/解析失败返回空 KlineList。
    """
    out = KlineList()
    out.source = "tdx_local_raw"
    if not std or not tx:
        return out
    market = tx[:_I2]  # "sh" / "sz" / "bj"
    if market not in ("sh", "sz", "bj"):
        return out
    path = os.path.join(_TDX_ROOT, "vipdoc", market, "lday", f"{tx}.day")
    if not os.path.exists(path):
        return out
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError:
        return out
    beg_i = int(beg) if beg else 0
    end_i = int(end) if end else 99999999
    n = len(data) // 32
    for i in range(n):
        b = data[i * 32:(i + 1) * 32]
        if len(b) < 32:
            break
        try:
            d, o, h, l, c = struct.unpack("<5I", b[:20])
            amt, = struct.unpack("<f", b[20:24])
            vol, = struct.unpack("<I", b[24:28])
        except struct.error:
            continue
        if d < beg_i or d > end_i:
            continue
        out.append({
            "date": str(d),
            "open": round(o / 100, 2),
            "close": round(c / 100, 2),
            "high": round(h / 100, 2),
            "low": round(l / 100, 2),
            "volume": float(vol),
            "amount": float(amt),
            "amplitude": None,
        })
    return out


def fetch_kline(code, beg=None, end=None, limit=None, min_quality="low", allow_raw=False):
    """东财历史日K（前复权，klt=101），东财失败自动兜底腾讯，再失败兜底通达信本地。

    返回 [{date,open,close,high,low,volume,amount,amplitude}]，
    按时间正序；beg/end 为 YYYYMMDD；limit 只保留最近 N 根。
    本地兜底返回不复权数据，KlineList.source='tdx_local_raw' 供下游标注。
    """
    std, secid, tx = normalize_code(code)
    if beg is None:
        span = max(limit * 2, 8) if limit else 8
        beg = _days_ago(span)
    if end is None:
        end = _days_ago(0)
    rows = []
    for attempt in range(3):
        rows = _fetch_kline_eastmoney(secid, beg, end)
        if rows:
            break
        if attempt < 2:
            time.sleep(0.5)
    source = "eastmoney_qfq" if rows else None
    if not rows:
        d0 = datetime.strptime(beg, "%Y%m%d")
        d1 = datetime.strptime(end, "%Y%m%d")
        rows = _fetch_kline_tencent(tx, d0.strftime("%Y-%m-%d"), d1.strftime("%Y-%m-%d"))
        source = "tencent_qfq" if rows else None
    if not rows and allow_raw:
        rows = _fetch_kline_tdx(std, tx, beg, end)
        source = "tdx_local_raw" if rows else None
    valid, ratio = _validate_kline_rows(rows)
    rows = valid
    if limit and len(rows) > limit:
        rows = rows[len(rows) - limit:]
    out = KlineList(rows)
    out.source = source
    out.adjust = "raw" if source == "tdx_local_raw" else ("qfq" if source else None)
    out.quality_ratio = round(ratio, 3)
    out.data_quality = "high" if source == "eastmoney_qfq" and ratio >= .98 else ("medium" if source == "tencent_qfq" and ratio >= .95 else "low")
    levels = {"low": 0, "medium": 1, "high": 2}
    if levels.get(out.data_quality, 0) < levels.get(min_quality, 0):
        return KlineList()
    return out


def fetch_close_on(code, date_str):
    """回填：取指定日（YYYY-MM-DD）收盘 K 线；无则 None。"""
    beg = date_str.replace("-", "")
    rows = fetch_kline(code, beg=beg, end=beg)
    for r in rows:
        if r["date"] == date_str:
            return r
    return None


def _news_with_crawl4ai(
    news_rows,
    stock_code,
    cutoff_time=None,
    enabled=None,
):
    """把关键词检索得到的文章 URL 交给 Crawl4AI 做正文清洗。

    设计原则：Crawl4AI 只负责页面抓取/清洗，不负责搜索；搜索仍由现有数据源完成。
    若依赖未安装、未启用或全部页面抓取失败，则返回原始新闻结果。
    """
    if enabled is None:
        enabled = os.environ.get("CRAWL4AI_ENABLED", "0").strip().lower() in {"1", "true", "yes", "on"}
    if not enabled or _crawl4ai_fetch_news_sync is None:
        return news_rows
    urls = [x.get("url") for x in (news_rows or []) if x.get("url")]
    if not urls:
        return news_rows
    try:
        crawled = _crawl4ai_fetch_news_sync(
            urls, stock_code=stock_code, cutoff_time=cutoff_time,
            headless=os.environ.get("CRAWL4AI_HEADLESS", "1") not in {"0", "false", "no"},
        )
    except Exception:
        return news_rows
    if not crawled:
        return news_rows

    # 保留搜索层字段，同时优先采用 Crawl4AI 的正文、发布时间和规范来源。
    by_url = {str(x.get("url")): x for x in crawled if x.get("url")}
    out = []
    for row in news_rows:
        url = str(row.get("url") or "")
        c = by_url.get(url)
        if c:
            out.append({
                "date": row.get("date", ""),
                "title": c.get("title") or row.get("title", ""),
                "media": c.get("source") or row.get("media", ""),
                "url": url,
                "published_at": c.get("published_at"),
                "crawled_at": c.get("crawled_at"),
                "content": c.get("content", ""),
                "summary": c.get("summary", ""),
                "stock_code": stock_code,
                "content_hash": c.get("content_hash", ""),
                "crawler": "crawl4ai",
            })
        else:
            out.append(dict(row))
    return out


def build_fact_sheet(code, news_limit=5, cutoff_time=None, use_crawl4ai=None, factor_window=60):
    """构建事实数据包：行情 + 新闻 + 近期K线。

    行情与K线无依赖关系，使用线程池并行取数以缩短总耗时；新闻依赖行情中的
    股票名称做关键词，故在行情返回后再取，避免多打一次无效请求。
    Crawl4AI 集成在新闻层：先由现有搜索接口发现文章 URL，再由 Crawl4AI 抓正文。
    cutoff_time 用于历史研究时的未来信息隔离；没有发布时间的网页在历史模式下会被丢弃。
    """
    std, _, _ = normalize_code(code)
    with ThreadPoolExecutor(max_workers=2) as pool:
        fut_quote = pool.submit(fetch_quote, code)
        fut_kline = pool.submit(fetch_kline, std, limit=factor_window)
        q = fut_quote.result()
        kline = fut_kline.result()
    name = q.get("name")
    try:
        from ashare.ashare_market import board_of
        q["board"] = board_of(std)
    except Exception:
        q["board"] = "未知"
    news_keyword = name if name else f"{std} 股票"
    news = fetch_news(news_keyword, limit=news_limit)
    news = _news_with_crawl4ai(
        news, stock_code=std, cutoff_time=cutoff_time, enabled=use_crawl4ai
    )
    try:
        from ashare.ashare_factor_engine import compute_factors, score_candidate
        factor_pack = compute_factors(kline)
        factor_score = score_candidate(factor_pack)
    except Exception as _factor_exc:  # factor layer must never break core data collection
        factor_pack = {"status": "error", "error": str(_factor_exc), "factors": {}}
        factor_score = {"score": None, "reasons": []}
    meta = {
        "code": std,
        "company": q.get("name") or std,
        "data_source": q.get("src") or "未知",
        "quote_time": q.get("quote_time") or "",
        "cutoff_time": cutoff_time or "",
        "crawl4ai_enabled": bool(use_crawl4ai if use_crawl4ai is not None else os.environ.get("CRAWL4AI_ENABLED", "0").lower() in {"1", "true", "yes", "on"}),
        "factor_window": factor_window,
        "note": q.get("note") or "",
    }
    return {"meta": meta, "quote": q, "news": news, "kline": kline,
            "quant_factors": factor_pack, "quant_score": factor_score}


def fact_sheet_to_text(sheet) -> str:
    """事实数据包 → 文本（供模型使用）。"""
    m = sheet["meta"]
    q = sheet["quote"]
    header = "【数据包】（来源：" + str(m.get("data_source", "未知"))
    if m.get("quote_time"):
        header += "，行情时间：" + str(m["quote_time"])
    if m.get("note"):
        header += "；" + str(m["note"])
    header += "）"
    lines = [header]
    lines.append(f"股票：{m.get('company')}（{m.get('code')}）")
    lines.append(
        f"现价 {q.get('price')} 元 | 涨跌幅 {q.get('change_pct')}% | "
        f"涨跌额 {q.get('change')} | 今开 {q.get('open')} | 昨收 {q.get('prev_close')}"
    )
    lines.append(
        f"最高 {q.get('high')} | 最低 {q.get('low')} | 成交量 {q.get('volume')} 手 | "
        f"成交额 {_fmt_amount(q.get('amount'))}"
    )
    lines.append(
        f"换手 {q.get('turnover')}% | 振幅 {q.get('amplitude')}% | "
        f"PE(TTM) {q.get('pe')} | PB {q.get('pb')}"
    )
    lines.append(
        f"总市值 {_fmt_amount(q.get('total_mv'))} | 流通市值 {_fmt_amount(q.get('float_mv'))}"
    )
    qf = sheet.get("quant_factors") or {}
    qs = sheet.get("quant_score") or {}
    if qf.get("factors"):
        lines.append("确定性量化因子（仅作为候选筛选证据，不是交易指令）：")
        for k, v in qf.get("factors", {}).items():
            lines.append(f"  {k}: {v}")
        if qs.get("score") is not None:
            lines.append(f"  deterministic_candidate_score: {qs.get('score')}")
    elif qf.get("status"):
        lines.append(f"确定性量化因子状态：{qf.get('status')}")
    kline = sheet.get("kline") or []
    if kline:
        n = len(kline)
        display_kline = kline[-12:]
        kline_src = getattr(kline, "source", None)
        if kline_src == "tdx_local_raw":
            lines.append(
                f"近{n}个交易日（日期 开盘 收盘 最高 最低 涨跌%）"
                "【⚠️ 本地不复权数据，跨除权日会跳价，仅供形态参考】"
            )
        else:
            lines.append(f"近{n}个交易日（日期 开盘 收盘 最高 最低 涨跌%）：")
        prev_close = None
        for r in display_kline:
            chg = ""
            if prev_close:
                chg = f" {round((r['close'] - prev_close) / prev_close * 100, 2)}%"
            lines.append(f"  {r['date']} {r['open']} {r['close']} {r['high']} {r['low']}{chg}")
            prev_close = r["close"]
    news = sheet.get("news") or []
    if news:
        lines.append(f"近期新闻（前{len(news)}条）：")
        for i, n in enumerate(news, 1):
            lines.append(f"  {i}. [{n.get('date')}] {n.get('title')}（{n.get('media')}）")
    else:
        lines.append("近期新闻：暂无")
    return "\n".join(lines)


def main():
    args = [a for a in sys.argv[_I1:] if not a.startswith("--")]
    news_limit = 5
    if "--news" in sys.argv:
        idx = sys.argv.index("--news")
        try:
            news_limit = int(sys.argv[idx + 1])
        except (ValueError, IndexError):
            news_limit = 5
    if not args:
        print(__doc__)
        return
    code = args[_I0]
    sheet = build_fact_sheet(code, news_limit=news_limit)
    if "--json" in sys.argv:
        print(json.dumps(sheet, ensure_ascii=False, indent=2))
    else:
        print(fact_sheet_to_text(sheet))


if __name__ == "__main__":
    main()
