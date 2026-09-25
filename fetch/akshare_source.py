# -*- coding: utf-8 -*-
"""AKShare 日K数据源适配器（可选依赖，惰性导入）。

设计原则（与本项目数据红线一致）：
- **零依赖核心不破坏**：本模块只有在调用时才尝试 `import akshare`；
  未安装时抛 `AkshareUnavailable`，绝不静默降级为编造数据。
- **契约一致**：输出与 `fetch/kline.py` 相同的 bar 字典约定
  （date/open/close/high/low/volume/amount/turnover），并额外带上
  `adjusted` 与 `source/provider` 溯源字段（对齐 `data_contracts` 精神）。
- **复权口径显式**：`adjust` 参数透传 akshare（""=不复权 / "qfq"=前复权 /
  "hfq"=后复权），并把口径写进每根 bar 的 `adjusted` 字段 —— 回测侧可据此
  判断是否跨除权，杜绝"拿不复权价算趋势"的隐性污染。
- 可通过 `make_provider()` 注册进 `router.ProviderRouter` 参与多源降级。

akshare 的 `stock_zh_a_hist` 返回 pandas DataFrame，中文列名：
日期/股票代码/开盘/收盘/最高/最低/成交量/成交额/振幅/涨跌幅/涨跌额/换手率。
本模块只依赖 `df.to_dict("records")` 这一个访问面，便于测试替身。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

# akshare 中文列名 → 本项目 bar 字段
_COLUMN_MAP = {
    "日期": "date",
    "开盘": "open",
    "收盘": "close",
    "最高": "high",
    "最低": "low",
    "成交量": "volume",
    "成交额": "amount",
    "换手率": "turnover",
}
_REQUIRED_SOURCE_COLUMNS = ("日期", "开盘", "收盘", "最高", "最低")

_ADJUST_LABEL = {"": "raw", "qfq": "qfq", "hfq": "hfq"}


class AkshareUnavailable(RuntimeError):
    """akshare 未安装或初始化失败（诚实失败，不做合成兜底）。"""


def _load_akshare():
    try:
        import akshare  # noqa: PLC0415 —— 刻意惰性导入，保持核心零依赖
        return akshare
    except Exception as exc:  # ImportError 及其自身的初始化异常都算不可用
        raise AkshareUnavailable(
            f"akshare 不可用（未安装或初始化失败: {exc}）；"
            "如需启用请 pip install akshare，或改用东财/腾讯/通达信数据源") from exc


def normalize_code(code: str) -> str:
    """统一 6 位数字代码；容忍 sh/sz/bj 前缀。空串 / 非数字 → ValueError。"""
    c = str(code).strip().lower()
    if not c:
        raise ValueError(f"非法股票代码: {code!r}")
    for prefix in ("sh", "sz", "bj"):
        if c.startswith(prefix):
            c = c[len(prefix):]
    c = c.zfill(6)
    if not (c.isdigit() and len(c) == 6):
        raise ValueError(f"非法股票代码: {code!r}")
    return c


def _to_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def fetch_daily_bars(code: str, start: str = "", end: str = "",
                     adjust: str = "", akshare_module=None) -> List[Dict[str, Any]]:
    """抓取个股日K并映射为本项目 bar 约定。

    参数：
        code:    6 位股票代码（容忍 sh/sz/bj 前缀）
        start/end: YYYYMMDD 或 YYYY-MM-DD，空串表示不限制
        adjust:  ""（不复权）| "qfq"（前复权）| "hfq"（后复权），透传 akshare
        akshare_module: 测试注入用；缺省时惰性导入真实 akshare

    返回：按日期升序的 bar 列表；数据缺失返回空列表（不编造）。
    缺少必需列（日期/OHLC）时抛 ValueError —— 列结构异常说明源已变化，
    静默丢列会造成下游误读。
    """
    if adjust not in _ADJUST_LABEL:
        raise ValueError(f"adjust 只支持 \"\"/\"qfq\"/\"hfq\"，收到: {adjust!r}")
    ak = akshare_module if akshare_module is not None else _load_akshare()
    symbol = normalize_code(code)
    start_y = str(start).replace("-", "") if start else ""
    end_y = str(end).replace("-", "") if end else ""
    df = ak.stock_zh_a_hist(symbol=symbol, period="daily",
                            start_date=start_y, end_date=end_y, adjust=adjust)
    if df is None:
        return []
    records = df.to_dict("records") if hasattr(df, "to_dict") else list(df)
    if not records:
        return []
    missing = [col for col in _REQUIRED_SOURCE_COLUMNS if col not in records[0]]
    if missing:
        raise ValueError(f"akshare 返回缺少必需列: {missing}（源接口可能已变更）")
    adjusted_label = _ADJUST_LABEL[adjust]
    out: List[Dict[str, Any]] = []
    for row in records:
        bar: Dict[str, Any] = {
            "date": str(row.get("日期") or ""),
            "open": _to_float(row.get("开盘")),
            "high": _to_float(row.get("最高")),
            "low": _to_float(row.get("最低")),
            "close": _to_float(row.get("收盘")),
            "volume": _to_float(row.get("成交量")),
            "amount": _to_float(row.get("成交额")),
            "turnover": _to_float(row.get("换手率")),
            "adjusted": adjusted_label,
            "source": "akshare",
            "provider": "stock_zh_a_hist",
        }
        if not bar["date"]:
            continue  # 无日期的残行不可用，丢弃（不猜日期）
        out.append(bar)
    out.sort(key=lambda b: b["date"])
    return out


def make_provider(priority: int = 60, available_fn=None):
    """注册进 router.ProviderRouter 的工厂。

    available_fn 仅供测试注入；默认按 `import akshare` 是否成功判定。
    """
    from router.provider_router import Provider, module_available

    def _available() -> bool:
        if available_fn is not None:
            return bool(available_fn())
        return module_available("akshare")

    return Provider(name="akshare_daily", priority=int(priority),
                    available=_available, fetch=fetch_daily_bars)
