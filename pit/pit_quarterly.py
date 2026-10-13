# -*- coding: utf-8 -*-
r"""单季口径派生：把「年初至今累计」还原成「单季」。

## 为什么需要

2026-09-30 专家圆桌审查中，**财报研究员**指出：

> 「一家公司 Q1 净利同比 **+50%**（基数低），到 Q3 **累计**同比只剩 **+8%** ——
> 因为 Q2、Q3 单季已经在恶化。系统在 Q3 看到的是『还在增长』，
> 而季度跟踪**最看重的恰恰是单季边际变化**：**累计同比会把拐点往后拖 2-3 个季度**。」

数据源 `fundamentals.jsonl` 的 `net_profit` / `revenue` / `eps` / `roe_pct`
**全部是年初至今累计值**，故上述滞后是结构性的。

## 派生规则（事前固定）

```
Q1 单季 = Q1 累计
Q2 单季 = H1 累计  − Q1 累计
Q3 单季 = Q3 累计  − H1 累计
Q4 单季 = 年报累计 − Q3 累计
```

**同比** = 单季 / **去年同期单季** − 1；**环比** = 单季 / 上一季单季 − 1。

## ⚠️ 诚实原则（承接项目信条「缺失即缺失」）

**基数 ≤ 0 时（亏损/扭亏场景）不硬算增速** —— 负基数下的百分比变化无经济含义
（−1 → +1 会算出 −200%，纯属误导）。此时：
- `*_q_qoq_pct` / `*_q_yoy_pct` 置 ``None``
- 同时给出 ``flags``，标明原因（``negative_base`` / ``missing_base`` / ``missing_prev``）

这与项目既有的「负 EPS 不出 `pe_ttm`」是同一原则。

## PIT

本模块**只做口径换算，不判定可用时点** —— 可用时点仍由
`pit.pit_fundamentals.resolve_availability` 决定（披露日 / +45 天 / 法定截止日）。
两者职责分离，不得混用。
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Tuple

from data_contracts import to_float_or_none as _num  # noqa: F401 — 唯一标准实现（CODE_REDUNDANCY_AUDIT P1）

# 单季字段映射：累计字段名 → 单季字段名
_FLOW_FIELDS = ("net_profit", "revenue")
_PER_SHARE_FIELDS = ("eps", "ocf_per_share")
# 单季化后**不**做差分的字段（比率类无「累计」概念）
_RATIO_FIELDS = ("roe_pct", "gross_margin_pct", "bps")

# 报告期 → (财年内的第几季, 该季之前的累计报告期)
_QUARTER_SEQ = {
    "03-31": (1, None),
    "06-30": (2, "03-31"),
    "09-30": (3, "06-30"),
    "12-31": (4, "09-30"),
}


def _period_key(report_period: str) -> Optional[Tuple[int, str]]:
    """``'2016-03-31'`` → ``(2016, '03-31')``；格式不符返回 ``None``。"""
    s = str(report_period or "")
    if len(s) < 10 or s[4] != "-":
        return None
    year, md = s[:4], s[5:10]
    if not year.isdigit() or md not in _QUARTER_SEQ:
        return None
    return int(year), md


def _growth(cur: Optional[float], base: Optional[float]) -> Tuple[Optional[float], Optional[str]]:
    """增速 + 拒绝原因。**基数 ≤ 0 不硬算**。"""
    if cur is None or base is None:
        return None, "missing_value"
    if base <= 0:
        return None, "negative_base"
    return (cur / base - 1.0) * 100.0, None


def derive_quarterly(
    records: Iterable[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    r"""把累计口径记录派生成**含单季值**的记录。

    :param records: 每行含 ``code`` / ``report_period`` / 累计字段。
    :return: 与输入等长的新列表（顺序按 ``code``, ``report_period`` 升序），
        每行在原始字段之外增加：

        * ``<field>_q``：单季值（``net_profit`` / ``revenue`` / ``eps`` / ``ocf_per_share``）
        * ``<field>_q_yoy_pct``：**单季**同比（%）
        * ``<field>_q_qoq_pct``：**单季**环比（%）

        ⚠️ **命名必须带 ``_q_`` 中缀**：数据源本来就有 ``net_profit_yoy_pct`` /
        ``revenue_yoy_pct``，那是**累计**同比。若派生值也用 ``<field>_yoy_pct``，
        会**静默覆盖源字段**，且名字无法区分两种口径 —— 属"不报错的失效"。
        * ``quarter``：财年第几季（1~4）
        * ``flags``：无法计算时的原因列表（``negative_base`` / ``missing_*`` / ``not_quarter_end``）

    **缺失即缺失**：无法差分（缺上一累计期）时 ``<field>_q`` 为 ``None``，不猜。
    """
    by_code: Dict[str, List[Dict[str, Any]]] = {}
    for r in records:
        code = str(r.get("code") or "")
        pk = _period_key(str(r.get("report_period") or ""))
        if not code or pk is None:
            continue
        by_code.setdefault(code, []).append(r)

    out: List[Dict[str, Any]] = []
    for code in sorted(by_code):
        rows = sorted(by_code[code], key=lambda x: str(x.get("report_period")))
        # 索引：(年, 月日) → 记录，便于找「上一累计期」与「去年同期单季」
        index: Dict[Tuple[int, str], Dict[str, Any]] = {}
        for r in rows:
            pk = _period_key(str(r.get("report_period") or ""))
            if pk:
                index[pk] = r

        # 第一遍：算单季值
        quarterly: Dict[Tuple[int, str], Dict[str, Optional[float]]] = {}
        for r in rows:
            pk = _period_key(str(r.get("report_period") or ""))
            if pk is None:
                continue
            year, md = pk
            q, prev_md = _QUARTER_SEQ[md]
            flags: List[str] = []
            qvals: Dict[str, Optional[float]] = {}
            for f in _FLOW_FIELDS + _PER_SHARE_FIELDS:
                cur = _num(r.get(f))
                if q == 1:
                    qvals[f] = cur                      # Q1 单季 = Q1 累计
                    if cur is None:
                        flags.append(f"missing_{f}")
                else:
                    prev = index.get((year, prev_md or ""))
                    base = _num(prev.get(f)) if prev else None
                    if cur is None or base is None:
                        qvals[f] = None
                        flags.append(f"missing_{f}")
                    else:
                        qvals[f] = cur - base           # 相邻累计差分
            quarterly[pk] = qvals
            r["_q"] = qvals
            r["_quarter"] = q
            r["_flags"] = flags

        # 第二遍：算同比 / 环比（需要全部单季值已就位）
        for r in rows:
            pk = _period_key(str(r.get("report_period") or ""))
            if pk is None:
                continue
            year, md = pk
            q, prev_md = _QUARTER_SEQ[md]
            cur_q = quarterly.get(pk, {})
            prev_q = (quarterly.get((year, prev_md)) if prev_md else None) or {}
            yoy_q = quarterly.get((year - 1, md), {}) or {}
            flags = list(r.get("_flags") or [])
            if prev_md is not None and not prev_q:
                flags.append("missing_prev_quarter")
            if not yoy_q:
                flags.append("missing_last_year_quarter")

            rec = {k: v for k, v in r.items() if not k.startswith("_")}
            rec["quarter"] = q
            for f in _FLOW_FIELDS + _PER_SHARE_FIELDS:
                rec[f"{f}_q"] = cur_q.get(f)
                g, why = _growth(cur_q.get(f), prev_q.get(f))
                rec[f"{f}_q_qoq_pct"] = g
                if why == "negative_base":
                    flags.append(f"{f}_q_qoq_negative_base")
                g2, why2 = _growth(cur_q.get(f), yoy_q.get(f))
                rec[f"{f}_q_yoy_pct"] = g2
                if why2 == "negative_base":
                    flags.append(f"{f}_q_yoy_negative_base")
            # 比率类字段原样保留（无「累计」概念），但标注单季序号
            for f in _RATIO_FIELDS:
                if f in rec:
                    rec[f] = _num(rec.get(f))
            rec["flags"] = sorted(set(flags))
            out.append(rec)

    out.sort(key=lambda x: (str(x.get("code")), str(x.get("report_period"))))
    return out


def load_quarterly(path: str) -> List[Dict[str, Any]]:
    """从 ``fundamentals.jsonl`` 读取并派生单季口径。"""
    import json as _json
    from pathlib import Path as _Path

    records: List[Dict[str, Any]] = []
    with _Path(path).open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(_json.loads(line))
            except _json.JSONDecodeError:
                continue
    return derive_quarterly(records)
