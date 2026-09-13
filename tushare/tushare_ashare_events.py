# -*- coding: utf-8 -*-
"""Optional real A-share event/flow adapter for TuShare.

The adapter is deliberately thin: it does not hide provider failures and does not
invent missing fields. TUSHARE_TOKEN is required at runtime; no token is stored here.
"""
from __future__ import annotations
import os
from typing import Any, Dict


class TuShareEventProvider:
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

    def _call(self, method: str, **kwargs):
        fn = getattr(self._client(), method, None)
        if fn is None:
            raise RuntimeError(f"TuShare client does not expose {method}")
        result = fn(**kwargs)
        if result is None:
            return []
        if hasattr(result, "to_dict"):
            return result.to_dict(orient="records")
        return list(result)

    def fetch_bundle(self, ts_code: str, start_date: str | None = None,
                     end_date: str | None = None) -> Dict[str, Any]:
        base = {"ts_code": ts_code}
        if start_date: base["start_date"] = start_date
        if end_date: base["end_date"] = end_date
        calls = {
            "moneyflow": "moneyflow",
            "top_list": "top_list",
            "top_inst": "top_inst",
            "forecast": "forecast",
            "express": "express",
            "share_float": "share_float",
            "holder_trade": "stk_holdertrade",
            "repurchase": "repurchase",
        }
        out = {}
        errors = {}
        for key, method in calls.items():
            try:
                out[key] = self._call(method, **base)
            except Exception as exc:
                # One endpoint failure must not destroy all other datasets.
                out[key] = []
                errors[key] = f"{type(exc).__name__}: {exc}"
        out["provider"] = "tushare"
        out["errors"] = errors
        return out
