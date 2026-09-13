# -*- coding: utf-8 -*-
"""Observed lifecycle evidence derived from raw TongdaXin daily bars.

This module deliberately distinguishes *observed trading history* from certified
listing/delisting lifecycle. A missing last bar can be suspension, data loss,
corporate action, or delisting; it is never inferred to mean delisting.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
import csv


@dataclass(frozen=True)
class ObservedLifecycle:
    code: str
    first_observed_date: str
    last_observed_date: str
    observed_rows: int


def load_observed_lifecycle(path: str | Path) -> list[ObservedLifecycle]:
    """Load a pre-aggregated ``code,first,last,rows`` TDX lifecycle file."""
    out: list[ObservedLifecycle] = []
    with Path(path).open("r", encoding="utf-8", newline="") as f:
        first = f.readline()
        if not first:
            return out
        cols = [x.strip() for x in first.rstrip("\n\r").split(",")]
        headered = {"code", "first_observed_date", "last_observed_date", "observed_rows"}.issubset(cols)
        if headered:
            reader = csv.DictReader(f, fieldnames=cols)
            rows = ({"code": r.get("code"), "first_observed_date": r.get("first_observed_date"),
                     "last_observed_date": r.get("last_observed_date"), "observed_rows": r.get("observed_rows")} for r in reader)
        else:
            rows = ({"code": parts[0], "first_observed_date": parts[1],
                     "last_observed_date": parts[2], "observed_rows": parts[3]}
                    for parts in csv.reader([first] + list(f)) if len(parts) >= 4)
        for row in rows:
            raw_rows = row.get("observed_rows")
            # 行数缺失或为空时跳过该行：不推断为 0（缺失数据不补造）。
            # 与非表头分支的 `len(parts) >= 4` 过滤保持一致的严格性。
            if raw_rows is None or str(raw_rows).strip() == "":
                continue
            out.append(
                ObservedLifecycle(
                    code=str(row["code"]).zfill(6),
                    first_observed_date=str(row["first_observed_date"]),
                    last_observed_date=str(row["last_observed_date"]),
                    observed_rows=int(str(raw_rows)),
                )
            )
    return out


def summarize_observed_lifecycle(
    records: Iterable[ObservedLifecycle],
    *,
    dataset_start: str,
    dataset_end: str,
) -> dict:
    """Summarize what TDX bars prove, without upgrading it to lifecycle truth."""
    rows = list(records)
    starts_at_boundary = sum(r.first_observed_date == dataset_start for r in rows)
    ends_at_boundary = sum(r.last_observed_date == dataset_end for r in rows)
    not_ending_at_boundary = [r.code for r in rows if r.last_observed_date < dataset_end]
    late_starts = [r.code for r in rows if r.first_observed_date > dataset_start]
    return {
        "evidence_type": "observed_trading_history",
        "certified_listing_delisting": False,
        "stock_codes": len(rows),
        "dataset_start": dataset_start,
        "dataset_end": dataset_end,
        "first_observed_at_dataset_start": starts_at_boundary,
        "first_observed_after_dataset_start": len(late_starts),
        "last_observed_at_dataset_end": ends_at_boundary,
        "last_observed_before_dataset_end": len(not_ending_at_boundary),
        "possible_lifecycle_gap_codes": sorted(not_ending_at_boundary),
        "warning": "last_observed_before_dataset_end is not proof of delisting; suspension/data gaps must be audited separately",
    }
