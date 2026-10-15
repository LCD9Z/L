# -*- coding: utf-8 -*-
"""`pool_manager` 单测（HANDOVER §7 第 4 项「剩余 9 个无覆盖模块」之一）。

**为什么补它**：该模块会**直接改写** `watchlist.json` 与池状态文件
（真实路径在 `runtime.runtime_env`），一旦逻辑出错会**静默改动用户的自选股**，
而此前**零测试覆盖**。

**隔离纪律**：所有文件读写一律重定向到 `tmp_path`；任何测试都**不得**触碰
真实的 `WATCHLIST_FILE` / `POOL_STATE_FILE` / `CANDIDATE_FILE`。
"""
from __future__ import annotations

import json
from typing import Any, Dict, List

import pytest

import pool_manager as pm


# ---------------------------------------------------------------------------
# 纯函数：_extract_stage
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("logic,expect", [
    ("核心逻辑：xxx\n周期阶段：楔形下跌（量能萎缩）", "楔形下跌"),   # 中文括号
    ("周期阶段：楔形突破(量能放大)", "楔形突破"),                    # 英文括号
    ("周期阶段：均线回穿（", "均线回穿"),                            # 空内容括号
    ("无阶段标记", None),                                            # 无标记
    ("", None),                                                      # 空串
    (None, None),                                                    # None
])
def test_extract_stage(logic, expect):
    assert pm._extract_stage(logic) == expect


def test_extract_stage_without_paren_drops_last_char():
    """⚠️ **发现一个真实边界缺陷**（本轮测试暴露，尚未修）。

    `_extract_stage` 找不到括号时 `find` 返回 -1，而切片用的是
    `logic[i+len(mark) : j]` —— **负数索引是 Python 的"从末尾数"语义**，
    所以最后一个字符被**静默切掉**：

        周期阶段：楔形下跌 量能萎缩  →  "楔形下跌 量能萎"（末字符「缩」丢失）

    **影响**：仅在「核心逻辑含『周期阶段：』但**其后无任何括号**」时触发。
    本测试按 characterization 原则**锁定当前（有缺陷的）行为**——
    日后若修好，此测试会变红，届时须评估影响面后再改期望值。

    ⚠️ 已登记为待修缺陷（见 WORKLOG），本次**不修**（重算期间不改生产代码）。
    """
    assert pm._extract_stage("周期阶段：楔形下跌 量能萎缩") == "楔形下跌 量能萎"
    # 单个字符时连字符本身也被吃掉
    assert pm._extract_stage("周期阶段：楔") == ""


# ---------------------------------------------------------------------------
# 夹具：隔离文件 + 打桩打分
# ---------------------------------------------------------------------------
def _stock(code: str, score: float, stage: str = "楔形下跌",
           name: str = "") -> Dict[str, Any]:
    return {
        "股票代码": code, "股票名称": name or f"N{code}", "综合评分": score,
        "核心逻辑": f"周期阶段：{stage}（测试）", "投资建议": "观望",
    }


@pytest.fixture
def env(tmp_path, monkeypatch):
    """把三个文件常量重定向到 tmp_path，并装好可写的候补池/状态。"""
    cand = tmp_path / "candidate.json"
    state = tmp_path / "pool_state.json"
    watch = tmp_path / "watchlist.json"
    monkeypatch.setattr(pm, "CANDIDATE_FILE", str(cand))
    monkeypatch.setattr(pm, "POOL_STATE_FILE", str(state))
    monkeypatch.setattr(pm, "WATCHLIST_FILE", str(watch))

    class Env:
        def __init__(self) -> None:
            self.cand, self.state, self.watch = cand, state, watch

        def set_watch(self, items: List[Dict[str, Any]]) -> None:
            pm.load_watchlist = lambda: {"watchlist": items}  # type: ignore[assignment]

        def set_candidates(self, sectors: Dict[str, List[Dict[str, str]]],
                           cursor: Dict[str, int] | None = None) -> None:
            self.cand.write_text(json.dumps({"sectors": sectors}), encoding="utf-8")
            self.state.write_text(json.dumps({"cursor": cursor or {}}), encoding="utf-8")

        def set_scorer(self, mapping: Dict[str, Dict[str, Any]]) -> None:
            def _score(it: Dict[str, Any]) -> Dict[str, Any]:
                r = mapping.get(it["code"])
                if r is None:
                    raise RuntimeError(f"no stub for {it['code']}")
                return r
            monkeypatch.setattr(pm, "score_stock", _score)

        def read_watch(self) -> List[Dict[str, Any]]:
            return json.loads(self.watch.read_text(encoding="utf-8"))["watchlist"]

        def read_cursor(self) -> Dict[str, int]:
            return json.loads(self.state.read_text(encoding="utf-8"))["cursor"]
    return Env()


def _scored(score: float, stage: str = "楔形突破") -> Dict[str, Any]:
    return {"综合评分": score, "核心逻辑": f"周期阶段：{stage}（测试）"}


# ---------------------------------------------------------------------------
# update_watchlist：淘汰判定
# ---------------------------------------------------------------------------
def test_no_removal_candidates_returns_empty(env):
    env.set_watch([{"code": "600001", "name": "A", "note": "核心"}])
    # 分数达标 → 不淘汰
    assert pm.update_watchlist([_stock("600001", 9.0)]) == ([], [])


def test_fetch_failure_is_skipped(env):
    s = _stock("600001", 1.0)
    s["投资建议"] = "取数失败"
    env.set_watch([{"code": "600001", "name": "A", "note": ""}])
    assert pm.update_watchlist([s]) == ([], [])


def test_core_stock_is_protected(env):
    """note 含「核心」的股票即使破位低分**也不淘汰**。"""
    env.set_watch([{"code": "600001", "name": "A", "note": "核心·半导体"}])
    assert pm.update_watchlist([_stock("600001", 1.0)]) == ([], [])


def test_non_watchlist_stock_is_not_removed_but_triggers_flow(env):
    """不在 watchlist 中的股票无 note → sector 为空 → 不受板块限制。"""
    env.set_watch([])
    env.set_candidates({}, {})
    removed, added = pm.update_watchlist([_stock("600001", 1.0)])
    assert [r[1] for r in removed] == ["600001"]
    assert added == []          # 候补池为空 ⇒ 补不进


def test_at_most_one_removal_per_sector(env):
    """每板块每天最多淘汰 1 只（防止板块被清空）。"""
    env.set_watch([
        {"code": "600001", "name": "A", "note": "半导体·x"},
        {"code": "600002", "name": "B", "note": "半导体·y"},
        {"code": "600003", "name": "C", "note": "医药·z"},
    ])
    env.set_candidates({}, {})
    removed, _ = pm.update_watchlist([
        _stock("600001", 1.0), _stock("600002", 0.5), _stock("600003", 0.1),
    ])
    codes = {r[1] for r in removed}
    assert "600003" in codes                       # 医药板块可淘汰
    assert len({"600001", "600002"} & codes) == 1  # 半导体只淘汰 1 只（分低者 600002）


def test_removal_capped_at_pool_replace_max(env):
    """每日淘汰上限 `_POOL_REPLACE_MAX`（6）。"""
    env.set_watch([{"code": f"6{i:05d}", "name": f"N{i}", "note": ""} for i in range(10)])
    env.set_candidates({}, {})
    removed, _ = pm.update_watchlist([_stock(f"6{i:05d}", 0.1 * i) for i in range(10)])
    assert len(removed) == pm._POOL_REPLACE_MAX


def test_lowest_score_removed_first(env):
    env.set_watch([
        {"code": "600001", "name": "A", "note": ""},
        {"code": "600002", "name": "B", "note": ""},
    ])
    env.set_candidates({}, {})
    removed, _ = pm.update_watchlist([_stock("600001", 2.0), _stock("600002", 1.0)])
    assert removed[0][1] == "600002"   # 分低者先淘汰


# ---------------------------------------------------------------------------
# update_watchlist：候补补充
# ---------------------------------------------------------------------------
def test_candidate_file_missing_returns_empty(env):
    """候补池文件缺失 → 直接返回空（不淘汰、不写文件）。"""
    env.set_watch([{"code": "600001", "name": "A", "note": ""}])
    removed, added = pm.update_watchlist([_stock("600001", 1.0)])
    assert (removed, added) == ([], [])
    assert not env.watch.exists()


def test_added_requires_min_score(env):
    """候补综合评分 < `_POOL_MIN_SCORE`(5.0) 不入池。"""
    env.set_watch([{"code": "600001", "name": "A", "note": ""}])
    env.set_candidates({"半导体": [{"code": "300001", "name": "C1"}]}, {})
    env.set_scorer({"300001": _scored(4.9)})
    removed, added = pm.update_watchlist([_stock("600001", 1.0)])
    assert len(removed) == 1 and added == []


def test_added_count_never_exceeds_removed(env):
    env.set_watch([{"code": "600001", "name": "A", "note": ""}])
    env.set_candidates({"半导体": [{"code": f"30000{i}", "name": f"C{i}"} for i in range(5)]}, {})
    env.set_scorer({f"30000{i}": _scored(9.0) for i in range(5)})
    removed, added = pm.update_watchlist([_stock("600001", 1.0)])
    assert len(added) <= len(removed) == 1


def test_already_in_watchlist_is_not_sampled(env):
    """候补池中已在 watchlist 的股票跳过。"""
    env.set_watch([
        {"code": "600001", "name": "A", "note": ""},
        {"code": "300001", "name": "C1", "note": ""},
    ])
    env.set_candidates({"半导体": [{"code": "300001", "name": "C1"}]}, {})
    env.set_scorer({"300001": _scored(9.0)})
    _, added = pm.update_watchlist([_stock("600001", 1.0)])
    assert added == []


def test_stage_priority_orders_candidates(env):
    """阶段优先级：楔形突破(2) > 均线回穿(3) > 反转扩展(1) —— 高分但阶段劣后者靠后。"""
    env.set_watch([{"code": "600001", "name": "A", "note": ""}])
    env.set_candidates({"S": [
        {"code": "300001", "name": "反转扩展股"},   # 反转扩展，分 9.9
        {"code": "300002", "name": "楔形突破股"},   # 楔形突破，分 1.0
    ]}, {})
    env.set_scorer({
        "300001": _scored(9.9, stage="反转扩展"),
        "300002": _scored(5.1, stage="楔形突破"),   # 分低但阶段优先
    })
    _, added = pm.update_watchlist([_stock("600001", 1.0)])
    assert [a[0] for a in added] == ["300002"]


# ---------------------------------------------------------------------------
# 写文件行为（dry vs 真实）
# ---------------------------------------------------------------------------
def test_dry_run_does_not_write_files(env):
    env.set_watch([{"code": "600001", "name": "A", "note": ""}])
    env.set_candidates({"半导体": [{"code": "300001", "name": "C1"}]}, {})
    env.set_scorer({"300001": _scored(9.0)})
    removed, added = pm.update_watchlist([_stock("600001", 1.0)], dry=True)
    assert len(removed) == 1 and len(added) == 1
    assert not env.watch.exists(), "dry 模式不得写 watchlist.json"
    assert env.read_cursor() == {}, "dry 模式不得推进 cursor"


def test_real_run_writes_watchlist_and_advances_cursor(env):
    env.set_watch([{"code": "600001", "name": "A", "note": ""}])
    env.set_candidates({"半导体": [
        {"code": "300001", "name": "C1"}, {"code": "300002", "name": "C2"},
    ]}, {})
    env.set_scorer({"300001": _scored(9.0), "300002": _scored(8.0)})
    removed, added = pm.update_watchlist([_stock("600001", 1.0)], dry=False)

    assert [r[1] for r in removed] == ["600001"]
    assert [a[0] for a in added] == ["300001"]
    codes = {w["code"] for w in env.read_watch()}
    assert "600001" not in codes and "300001" in codes
    # cursor 推进到抽样的末位：每板块抽样数 `_POOL_SAMPLE_PER_SECTOR`(2)
    assert env.read_cursor()["半导体"] == pm._POOL_SAMPLE_PER_SECTOR, \
        "cursor 须推进到轮询抽样末位"


def test_real_run_persists_and_reuses_cursor(env):
    """第二次调用从上次 cursor 继续（轮询，不重复取同一只）。"""
    env.set_watch([{"code": "600001", "name": "A", "note": ""}])
    env.set_candidates({"半导体": [
        {"code": "300001", "name": "C1"}, {"code": "300002", "name": "C2"},
    ]}, {})
    env.set_scorer({"300001": _scored(9.0), "300002": _scored(8.0)})
    pm.update_watchlist([_stock("600001", 1.0)])          # 取走 300001
    # 300001 已入池 → 第二次跳过它，应取 300002
    env.set_watch([
        {"code": "600002", "name": "B", "note": ""},
        {"code": "300001", "name": "C1", "note": "候补入池·自动"},
    ])
    _, added = pm.update_watchlist([_stock("600002", 1.0)])
    assert [a[0] for a in added] == ["300002"]
