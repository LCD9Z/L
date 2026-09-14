"""Provider adapters for evidence-first A-share corporate actions.

The adapter never treats a missing provider row as a corporate action.  TuShare
is optional and is only contacted when a token/client is explicitly supplied.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Iterable

from .corporate_actions import CorporateAction


@dataclass(frozen=True)
class CorporateActionAudit:
    provider: str
    requested_codes: int
    returned_codes: int
    event_rows: int
    missing_codes: tuple[str, ...]
    has_complete_coverage: bool
    reason: str


def _f(row: dict[str, Any], key: str) -> float:
    value = row.get(key)
    if value in (None, ""):
        return 0.0
    return float(value)


def normalize_tushare_dividend(row: dict[str, Any]) -> CorporateAction | None:
    """Normalize one TuShare ``dividend`` row.

    TuShare's stock bonus fields are reported per 10 shares, so they are
    converted to a per-share ratio.  Rows without an ex-date are retained as
    unusable rather than assigned a guessed effective date.
    """
    code = str(row.get("ts_code", ""))
    ex_date = str(row.get("ex_date", ""))
    if not code or not ex_date or ex_date in {"None", "nan"}:
        return None
    bonus_ratio = (_f(row, "stk_bo_rate") + _f(row, "stk_co_rate")) / 10.0
    cash = _f(row, "cash_div")
    rights_ratio = _f(row, "rights_ratio")
    rights_price = _f(row, "issue_price")
    if rights_ratio > 0:
        event_type = "rights_issue"
    elif bonus_ratio > 0 and cash > 0:
        event_type = "cash_bonus"
    elif bonus_ratio > 0:
        event_type = "bonus"
    elif cash > 0:
        event_type = "cash_dividend"
    else:
        event_type = "other"
    return CorporateAction(
        code=code.split(".")[0],
        ex_date=f"{ex_date[:4]}-{ex_date[4:6]}-{ex_date[6:8]}" if len(ex_date) == 8 else ex_date,
        event_type=event_type,
        cash_dividend=cash,
        bonus_ratio=bonus_ratio,
        rights_ratio=rights_ratio,
        rights_price=rights_price,
        source="tushare.dividend",
        confidence="provider_verified",
    )


class TuShareCorporateActionProvider:
    def __init__(self, token: str | None = None, client: Any = None):
        self.token = (token or os.getenv("TUSHARE_TOKEN") or "").strip()
        self._pro = client
        if self._pro is None and not self.token:
            raise RuntimeError("TUSHARE_TOKEN is not configured")

    def _client(self):
        if self._pro is None:
            try:
                import tushare as ts
            except ImportError as exc:
                raise RuntimeError("tushare package is not installed") from exc
            self._pro = ts.pro_api(self.token)
        return self._pro

    def fetch_dividends(self, ts_code: str, start_date: str | None = None,
                        end_date: str | None = None) -> list[CorporateAction]:
        kwargs: dict[str, Any] = {"ts_code": ts_code}
        if start_date:
            kwargs["start_date"] = start_date
        if end_date:
            kwargs["end_date"] = end_date
        df = self._client().dividend(**kwargs)
        records = df.to_dict(orient="records") if hasattr(df, "to_dict") else list(df)
        out = []
        for row in records:
            action = normalize_tushare_dividend(dict(row))
            if action is not None:
                out.append(action)
        return out

    def fetch_adj_factors(self, ts_code: str, start_date: str | None = None,
                          end_date: str | None = None) -> list[dict[str, Any]]:
        kwargs: dict[str, Any] = {"ts_code": ts_code}
        if start_date:
            kwargs["start_date"] = start_date
        if end_date:
            kwargs["end_date"] = end_date
        df = self._client().adj_factor(**kwargs)
        return df.to_dict(orient="records") if hasattr(df, "to_dict") else list(df)


def consolidate_actions(actions: Iterable[CorporateAction]) -> list[CorporateAction]:
    """把同一 ``(代码, 除权日)`` 的多条事件合并为一条。

    必要性：**同一除权日可能同时实施不同报告期的分红方案**。
    实测东方财富数据中，如 ``600720 20240613`` 同时实施了 2023 年报（10派2.57元）
    与 2022 年报（10派1.104元）的分红，接口返回两行。

    对价格复权而言，当日的价格影响是**合计**的现金与送转，
    因此必须合并为一条 —— 否则 :func:`corporate_actions.validate_actions`
    会按「重复事件」拒绝（该守卫用于捕捉**真正的重复加载**，不应被放宽）。

    合并规则：

    * ``cash_dividend`` / ``bonus_ratio`` / ``rights_ratio`` 求和；
    * ``rights_price`` 若多行均非零则取**加权平均**（按 rights_ratio 加权），
      仅一行非零时直接沿用；
    * ``event_type`` 按合并后的成分重新判定；
    * ``source`` / ``confidence`` 标注为合并产物，保留原始来源链。

    未发生合并的条目**原样返回**（不重建对象，避免改动其证据字段）。
    """
    groups: dict[tuple[str, str], list[CorporateAction]] = {}
    for a in actions:
        groups.setdefault((a.normalized_code(), a.ex_date), []).append(a)

    out: list[CorporateAction] = []
    for _, items in groups.items():
        if len(items) == 1:
            out.append(items[0])
            continue

        cash = sum(float(a.cash_dividend) for a in items)
        bonus = sum(float(a.bonus_ratio) for a in items)
        rights_ratio = sum(float(a.rights_ratio) for a in items)
        priced = [a for a in items if float(a.rights_ratio) > 0 and float(a.rights_price) > 0]
        if len(priced) == 1:
            rights_price = float(priced[0].rights_price)
        elif priced:
            wsum = sum(float(a.rights_ratio) for a in priced)
            rights_price = (
                sum(float(a.rights_price) * float(a.rights_ratio) for a in priced) / wsum
                if wsum > 0 else 0.0
            )
        else:
            rights_price = 0.0

        if rights_ratio > 0:
            event_type = "rights_issue"
        elif bonus > 0 and cash > 0:
            event_type = "cash_bonus"
        elif bonus > 0:
            event_type = "bonus"
        elif cash > 0:
            event_type = "cash_dividend"
        else:
            event_type = "other"

        base = items[0]
        sources = sorted({a.source for a in items})
        out.append(CorporateAction(
            code=base.normalized_code(),
            ex_date=base.ex_date,
            event_type=event_type,
            cash_dividend=cash,
            bonus_ratio=bonus,
            rights_ratio=rights_ratio,
            rights_price=rights_price,
            shares_before=base.shares_before,
            shares_after=base.shares_after,
            source="+".join(sources) if len(sources) > 1 else base.source,
            confidence="consolidated" if len(sources) > 1 else base.confidence,
        ))
    return sorted(out, key=lambda a: (a.normalized_code(), a.ex_date, a.event_type))


def audit_action_coverage(requested_codes: Iterable[str], actions: Iterable[CorporateAction]) -> CorporateActionAudit:
    requested = {str(c).zfill(6) for c in requested_codes}
    items = list(actions)
    actual = {a.normalized_code() for a in items}
    missing = tuple(sorted(requested - actual))
    return CorporateActionAudit(
        provider="normalized_corporate_actions",
        requested_codes=len(requested),
        returned_codes=len(actual),
        event_rows=len(items),
        missing_codes=missing,
        has_complete_coverage=not missing,
        reason="coverage is complete only when every requested code has a verified corporate-action history",
    )
