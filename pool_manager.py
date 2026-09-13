# -*- coding: utf-8 -*-
"""每日选股 · 股票池自动维护（方案A）。

由 daily_stock_pick.py 拆分而来（1.0）。

规则：淘汰「楔形下跌 + 综合评分低于阈值 + 非核心关注股」，
并从候补池按「阶段优先级 + 评分」轮询抽样补充；
每板块每天最多淘汰 1 只，避免板块被清空；用户标注「核心」的股票受保护。
"""
import json

from runtime.runtime_env import (
    CANDIDATE_FILE,
    POOL_STATE_FILE,
    WATCHLIST_FILE,
    load_watchlist,
    log,
)
from stock_scoring import score_stock
from typing import Any, Dict, List, Tuple

# 股票池自动维护（方案A：淘汰破位低分 + 候补池早期阶段优先补充）
_POOL_REPLACE_MAX = 6          # 每日最多自动淘汰只数
_POOL_SAMPLE_PER_SECTOR = 2    # 每板块轮询抽样数
_POOL_MIN_SCORE = 5.0          # 候选入池最低评分
_POOL_REMOVE_SCORE = 3.5       # 淘汰阈值（楔形下跌且低于此分）
_STAGE_PRIORITY = {1: 2, 2: 0, 3: 1, 4: 3, 5: 4, 6: 5}  # 阶段优先入池：楔形突破>均线回穿>反转扩展


def _extract_stage(logic):
    """从核心逻辑提取周期阶段名，如 '楔形下跌'。无则返回 None。"""
    if not logic:
        return None
    mark = "周期阶段："
    i = logic.find(mark)
    if i < 0:
        return None
    j = logic.find("（", i)
    if j < 0:
        j = logic.find("(", i)
    return logic[i + len(mark):j].strip()


def update_watchlist(stocks, dry=False):
    """方案A：每日自动维护股票池——淘汰破位低分股，从候补池按早期阶段优先补充。

    返回 (removed, added)，removed/added 每项为 (code, name)。
    """
    cfg = load_watchlist()
    watch = cfg["watchlist"]
    watch_codes = {w["code"] for w in watch}

    # 1) 淘汰判定：楔形下跌 + 综合评分 < 阈值 + 非核心关注股
    candidates = []
    for s in stocks:
        if s.get("投资建议") == "取数失败":
            continue
        if _extract_stage(s.get("核心逻辑") or "") != "楔形下跌":
            continue
        if s.get("综合评分") >= _POOL_REMOVE_SCORE:
            continue
        code = s.get("股票代码")
        w = next((x for x in watch if x["code"] == code), None)
        if w and ("核心" in (w.get("note") or "")):
            continue  # 保护用户核心关注股
        candidates.append((s.get("综合评分") or 0, code, s.get("股票名称") or code))
    candidates.sort(key=lambda x: x[0])
    to_remove: List[Tuple[float, str, str]] = []
    removed_sectors = set()
    for comp, code, name in candidates:
        if len(to_remove) >= _POOL_REPLACE_MAX:
            break
        w = next((x for x in watch if x["code"] == code), None)
        sector = (w.get("note") or "").split("·")[0] if w and "·" in (w.get("note") or "") else ""
        if sector and sector in removed_sectors:
            continue  # 每板块每天最多淘汰 1 只，避免板块被清空
        to_remove.append((comp, code, name))
        if sector:
            removed_sectors.add(sector)

    if not to_remove:
        return ([], [])

    # 2) 从候补池轮询抽样打分
    try:
        with open(CANDIDATE_FILE, "r", encoding="utf-8") as f:
            pool = json.load(f)
    except OSError:
        log("候补池缺失 %s，跳过池子维护" % CANDIDATE_FILE)
        return ([], [])
    state = {}
    try:
        with open(POOL_STATE_FILE, "r", encoding="utf-8") as f:
            state = json.load(f)
    except OSError:
        state = {}
    cursor = dict(state.get("cursor", {}))

    sample: List[Tuple[str, Dict[str, Any]]] = []
    for sector, items in pool.get("sectors", {}).items():
        if not items:
            continue
        pos = int(cursor.get(sector, 0))
        picked: List[Dict[str, Any]] = []
        n = len(items)
        for _ in range(n):
            it = items[pos % n]
            pos += 1
            if it["code"] in watch_codes:
                continue
            if it["code"] in {x["code"] for x in picked}:
                continue
            picked.append(it)
            if len(picked) >= _POOL_SAMPLE_PER_SECTOR:
                break
        cursor[sector] = pos
        sample.extend((sector, it) for it in picked)

    # 3) 候补打分，按阶段优先级 + 评分排序
    _stage_num = {name: num for num, name in {
        1: "反转扩展", 2: "楔形突破", 3: "均线回穿",
        4: "底部+突破", 5: "衰竭扩展", 6: "楔形下跌"}.items()}
    scored = []
    for sector, it in sample:
        try:
            r = score_stock({"code": it["code"], "name": it["name"], "note": "候选·" + sector})
            stage = _extract_stage(r.get("核心逻辑") or "")
            stage_no = _stage_num.get(stage, 9)
            comp = float(r.get("综合评分") or 0)
            scored.append((_STAGE_PRIORITY.get(stage_no, 9), -comp, it["code"], it["name"], sector, comp))
        except Exception as e:
            log("候选打分失败 %s %s: %s" % (it["code"], it["name"], e))
    scored.sort(key=lambda x: (x[0], x[1]))

    added: List[Tuple[str, str]] = []
    for _prio, _neg, code, name, _sector, comp in scored:
        if len(added) >= len(to_remove):
            break
        if comp < _POOL_MIN_SCORE:
            continue
        added.append((code, name))

    if dry:
        log("【池子维护·预览】将淘汰 %d 只: %s" % (len(to_remove), ", ".join("%s(%s)" % (c[2], c[1]) for c in to_remove)))
        log("【池子维护·预览】将加入 %d 只: %s" % (len(added), ", ".join("%s(%s)" % (a[1], a[0]) for a in added)))
        return (to_remove, added)

    # 4) 非 dry：实际更新 watchlist.json + cursor
    removed_codes = {c[1] for c in to_remove}
    new_watch = [w for w in watch if w["code"] not in removed_codes]
    new_codes = {w["code"] for w in new_watch}
    for code, name in added:
        if code in new_codes:
            continue
        new_watch.append({"code": code, "name": name, "note": "候补入池·自动"})
        new_codes.add(code)
    cfg["watchlist"] = new_watch
    with open(WATCHLIST_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    state["cursor"] = cursor
    with open(POOL_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    log("池子维护：淘汰 %d 只(%s)，加入 %d 只(%s)，现池 %d 只" % (
        len(to_remove), ",".join(c[1] for c in to_remove),
        len(added), ",".join(a[0] for a in added), len(new_watch)))
    return (to_remove, added)
