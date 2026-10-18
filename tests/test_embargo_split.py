# -*- coding: utf-8 -*-
"""embargo 时序切分的守卫测试（对应 `COST_AUTHORITY_AND_EMBARGO_PREREG.md` §三.3）。

判据一览：
- B-0 不破坏主 pipeline：`run_real_alpha_pipeline` 不 import 本切分函数
- B-1 embargo 真的在剔除
- B-2 测试集不受影响（embargo 只动训练侧）
- B-3 越界抛 ValueError，不静默返回空训练集
- B-4 不破坏 warm-up（pre-OOS bars 仍可作因子预热）
- B-5 阳性对照：无 embargo 时训练集末尾样本的标签**确实**跨越 oos_start
- B-6 默认值不隐性变更（不传 embargo 时与改造前逐位相同）
- B-7 horizon 兜底：`max(embargo_days, horizon)`
"""
import re
from pathlib import Path

import pytest

from real_alpha_pipeline import split_chronological, embargo_cutoff

ROOT = Path(__file__).resolve().parent.parent
OOS = "2023-01-21"


def _bars(n=40, start="2023-01-01"):
    """n 个连续日历日（本模块只比较日期字符串，用日历日即可表达顺序）。"""
    import datetime as dt
    d0 = dt.date.fromisoformat(start)
    return [{"date": (d0 + dt.timedelta(days=i)).isoformat(),
             "close": 10.0 + i} for i in range(n)]


def _legacy_split(data, oos_start):
    """改造前的实现（本地复刻，用于 B-6 的逐位对照）。

    不通过 git 取历史版本 —— 那会让测试依赖仓库状态。
    """
    train, oos = {}, {}
    for code, bars in data.items():
        a = [b for b in bars if str(b["date"]) < oos_start]
        b = [x for x in bars if str(x["date"]) >= oos_start]
        if a:
            train[code] = a
        if b:
            oos[code] = b
    if not oos:
        raise ValueError("no_out_of_sample_data")
    return train, oos


# ---------------------------------------------------------------------------
# B-0 不破坏主 pipeline
# ---------------------------------------------------------------------------
def test_b0_main_pipeline_does_not_use_this_split():
    """`run_real_alpha_pipeline` 不得 import 本函数——它是纯样本外设计，
    不需要 embargo（预注册 §1b）。若哪天它开始用了，说明有人把
    「训练/测试切分」语义引入了纯 OOS pipeline，须重新评估。
    """
    text = (ROOT / "real_alpha_pipeline.py").read_text(encoding="utf-8")
    body = text.split("def run_real_alpha_pipeline", 1)[1]
    assert "split_chronological" not in body, (
        "B-0：run_real_alpha_pipeline 引用了 split_chronological。"
        "该 pipeline 是纯样本外设计（pre-OOS 仅作 warm-up），"
        "引入 train/test 切分会改变其证据链语义。"
    )


def test_b0_warm_up_comment_still_present():
    """`run_real_alpha_pipeline` 的 warm-up 逻辑不得被误删（B-4 的主防线）。"""
    text = (ROOT / "real_alpha_pipeline.py").read_text(encoding="utf-8")
    assert "warm-up" in text, "B-4：warm-up 说明不见了，因子预热逻辑可能被改动"
    assert "start_signal_date" in text, "B-4：信号起点控制不见了"


# ---------------------------------------------------------------------------
# B-1 / B-2 embargo 只动训练侧
# ---------------------------------------------------------------------------
def test_b1_embargo_actually_removes():
    data = {"600000": _bars(40)}
    t0, o0 = split_chronological(data, OOS, embargo_days=0)
    t5, o5 = split_chronological(data, OOS, embargo_days=5)
    last0 = t0["600000"][-1]["date"]
    last5 = t5["600000"][-1]["date"]
    assert last5 < last0, f"B-1：embargo 未剔除（末日 {last5} vs {last0}）"
    # 少一天都不算「5 个交易日」：差距必须 >= 5
    import datetime as dt
    gap = (dt.date.fromisoformat(last0) - dt.date.fromisoformat(last5)).days
    assert gap >= 5, f"B-1：embargo=5 但只剔了 {gap} 天"


def test_b2_oos_untouched():
    data = {"600000": _bars(40)}
    _, o0 = split_chronological(data, OOS, embargo_days=0)
    _, o5 = split_chronological(data, OOS, embargo_days=5)
    _, o9 = split_chronological(data, OOS, embargo_days=9)
    assert o0["600000"] == o5["600000"] == o9["600000"], (
        "B-2：测试集被 embargo 改变了——embargo 只能动训练侧"
    )
    assert o0["600000"][0]["date"] == OOS


# ---------------------------------------------------------------------------
# B-3 越界可预期
# ---------------------------------------------------------------------------
def test_b3_embargo_exceeds_train_raises():
    data = {"600000": _bars(25)}          # train 只有 20 天
    with pytest.raises(ValueError, match="embargo_exceeds_train"):
        split_chronological(data, OOS, embargo_days=100)


def test_b3_no_oos_raises():
    data = {"600000": _bars(10)}          # 全在 oos_start 之前
    with pytest.raises(ValueError, match="no_out_of_sample_data"):
        split_chronological(data, OOS)


def test_b3_unsorted_raises():
    bars = _bars(40)
    bars[5], bars[6] = bars[6], bars[5]   # 破坏升序
    with pytest.raises(ValueError, match="data_not_sorted"):
        split_chronological({"600000": bars}, OOS)


def test_b3_negative_embargo_raises():
    with pytest.raises(ValueError, match="embargo_days_must_be_non_negative"):
        split_chronological({"600000": _bars(40)}, OOS, embargo_days=-1)


# ---------------------------------------------------------------------------
# B-5 阳性对照（本文件最重要的一条）
# ---------------------------------------------------------------------------
def test_b5_positive_control_labels_do_cross_without_embargo():
    """证明「无 embargo 时标签确实跨越 oos_start」——否则 embargo 在解决
    一个不存在的问题，整套改造就是空转。

    构造：40 天，oos_start = 第 21 天（2023-01-21），horizon = 5。
    无 embargo 时训练集末样本 = 2023-01-20；
    持有 5 日 ⇒ 其标签要用 2023-01-25 的收盘价才能知道，
    而 2023-01-25 >= oos_start ⇒ **标签取自测试集期间** ⇒ 泄漏成立。
    """
    import datetime as dt
    data = {"600000": _bars(40)}
    horizon = 5
    train, _ = split_chronological(data, OOS, embargo_days=0)
    last_signal = dt.date.fromisoformat(train["600000"][-1]["date"])
    label_day = last_signal + dt.timedelta(days=horizon)
    assert label_day.isoformat() >= OOS, (
        f"B-5 阳性对照失败：训练集末样本 {last_signal} + horizon {horizon} "
        f"= {label_day} 仍未跨越 {OOS} ⇒ 构造场景不成立，"
        "embargo 可能是在解决不存在的问题"
    )
    # 加了 embargo=horizon 后，同一个样本的标签必须落在 oos_start 之前
    train_e, _ = split_chronological(data, OOS, embargo_days=horizon)
    last_signal_e = dt.date.fromisoformat(train_e["600000"][-1]["date"])
    assert (last_signal_e + dt.timedelta(days=horizon)).isoformat() < OOS, (
        "B-5：加了 embargo=horizon 后标签仍跨越 oos_start ⇒ embargo 尺寸不足"
    )


# ---------------------------------------------------------------------------
# B-6 默认值不隐性变更
# ---------------------------------------------------------------------------
def test_b6_default_is_bit_identical_to_legacy():
    """不传 embargo 时，结果必须与改造前逐位相同（默认值 = 一处口径）。"""
    data = {"600000": _bars(40), "000001": _bars(30, start="2023-01-05")}
    legacy_train, legacy_oos = _legacy_split(data, OOS)
    new_train, new_oos = split_chronological(data, OOS)
    assert new_train == legacy_train, "B-6：默认行为与改造前不一致（train）"
    assert new_oos == legacy_oos, "B-6：默认行为与改造前不一致（oos）"


def test_b6_legacy_raises_same_error_on_empty_oos():
    data = {"600000": _bars(10)}
    with pytest.raises(ValueError, match="no_out_of_sample_data"):
        _legacy_split(data, OOS)
    with pytest.raises(ValueError, match="no_out_of_sample_data"):
        split_chronological(data, OOS)


# ---------------------------------------------------------------------------
# B-7 horizon 兜底
# ---------------------------------------------------------------------------
def test_b7_horizon_takes_max():
    data = {"600000": _bars(40)}
    t2, _ = split_chronological(data, OOS, embargo_days=2)
    t2h5, _ = split_chronological(data, OOS, embargo_days=2, horizon=5)
    t5, _ = split_chronological(data, OOS, embargo_days=5)
    assert t2h5 == t5, "B-7：embargo_days=2 + horizon=5 应等价于 embargo=5（取大者）"
    assert t2h5 != t2, "B-7：horizon 未起作用"


def test_b7_horizon_larger_than_embargo_is_enforced():
    data = {"600000": _bars(40)}
    _, o = split_chronological(data, OOS, embargo_days=1, horizon=7)
    t, _ = split_chronological(data, OOS, embargo_days=7, horizon=1)
    assert t == split_chronological(data, OOS, embargo_days=7)[0]


# ---------------------------------------------------------------------------
# embargo_cutoff 留痕辅助
# ---------------------------------------------------------------------------
def test_embargo_cutoff_reports_earliest():
    data = {"a": _bars(40, start="2023-01-01"),
            "b": _bars(40, start="2023-01-03")}   # b 的 oos 位置更晚
    cut = embargo_cutoff(data, OOS, embargo_days=5)
    assert cut is not None
    import datetime as dt
    assert dt.date.fromisoformat(cut) < dt.date.fromisoformat(OOS)


def test_embargo_cutoff_zero_returns_none():
    assert embargo_cutoff({"a": _bars(40)}, OOS, embargo_days=0) is None


def test_embargo_cutoff_insufficient_returns_none():
    """训练集天数 < embargo_days 时返回 None（无法给出有效截止日）。

    注意构造：4 天全部早于 oos_start ⇒ i_oos=4，cut=4-5=-1 ⇒ None。
    （用 10 天 + embargo 5 是**够**的，剩 5 天——那正是本测试最初写错的地方。）
    """
    assert embargo_cutoff({"a": _bars(4)}, OOS, embargo_days=5) is None
    assert embargo_cutoff({"a": _bars(5)}, OOS, embargo_days=5) is None
    # 6 天扣 5 剩 1 天 ⇒ 有效
    assert embargo_cutoff({"a": _bars(6)}, OOS, embargo_days=5) is not None


# ---------------------------------------------------------------------------
# 元判据：源码里不许再出现「无 embargo 的紧邻切分」
# ---------------------------------------------------------------------------
def test_no_adjacent_split_left_in_source():
    """源码里不得再出现 `date] < oos_start` 这种不带 embargo 的紧邻切分写法。

    用 AST 而非正则：跳过注释与 docstring（正则会把解释性文字当违规 = 假红）。
    """
    import ast
    offenders = []
    for path in sorted(ROOT.rglob("*.py")):
        if ".git" in path.parts or "__pycache__" in path.parts or "tests" in path.parts:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
        except (OSError, SyntaxError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ListComp):
                continue
            # 形如 [b for b in bars if str(b["date"]) < oos_start]
            src = ast.dump(node)
            if 'Str' in src or 'Constant' in src:
                if 'Lt' in src and 'oos_start' in src and 'Sub' in src:
                    offenders.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    assert not offenders, (
        "源码里仍有不带 embargo 的紧邻切分:\n  " + "\n  ".join(offenders)
    )
