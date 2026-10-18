# -*- coding: utf-8 -*-
"""成本口径权威化的守卫测试（对应 `COST_AUTHORITY_AND_EMBARGO_PREREG.md` §二.4）。

判据一览：
- A-1 日期格式免疫：`20230825` / `2023-08-25` / `2023/08/25` 三种格式结果一致且为旧税率
- A-2 边界日：`2023-08-28` 当天新税率；`2023-08-25` 旧税率
- A-3 跨线净收益确实变化：修前（bug）与修后差 = 单边 0.5‰，方向为「修后更低」
- A-4 存量零影响：`tracking.db` 13 行重算 `return_pct` 与现状逐位相同
- A-5 无第三方副本：`stamp_duty_change_date` 只出现在权威源与其 import 方

**反向验证纪律**（2026-10-18 记忆）：本文件每个判据都植入过已知问题并确认会红，
且红的原因是断言本身，不是 `ImportError` / `FileNotFoundError` 之类的假红。
"""
import math
import re
import sqlite3
from pathlib import Path

import pytest

import cost_model
from backtest_engine import Costs, _stamp_rate as engine_stamp_rate, _trade_cost
from track.costs import TrackingCosts

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "tracking.db"

# 缺陷 #15 的旧实现（本地复刻，用于 A-3 的「修前」对照）。
# 不通过 git 取历史版本 —— 那会让测试依赖仓库状态。
def _legacy_string_compare(as_of: str) -> bool:
    """旧逻辑的真值表：`str(as_of) >= "2023-08-28"` 逐字符比较。"""
    return str(as_of) >= "2023-08-28"


# ---------------------------------------------------------------------------
# A-1 日期格式免疫
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("as_of", ["20230825", "2023-08-25", "2023/08/25"])
def test_a1_date_format_immunity(as_of):
    """三种格式必须一致，且都判为**旧税率**（生效日之前）。"""
    assert engine_stamp_rate(Costs(), as_of) == 0.001, (
        f"A-1：{as_of!r} 未归一化，被误判。"
        f"根因是 '-' < '0' 使无横杠日期恒过。"
    )
    assert TrackingCosts()._stamp_rate(as_of) == 0.001


def test_a1_three_formats_agree():
    """三种格式对**同一个**成本对象的结果必须逐位相同。"""
    spec = Costs()
    vals = {engine_stamp_rate(spec, d) for d in ("20230825", "2023-08-25", "2023/08/25")}
    assert len(vals) == 1, f"A-1：三种格式结果不一致 {vals}"


# ---------------------------------------------------------------------------
# A-2 边界日
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("as_of,expected", [
    ("2023-08-28", 0.0005), ("20230828", 0.0005),   # 生效日当天 → 新税率
    ("2023-08-25", 0.001), ("20230825", 0.001),     # 生效日前一天 → 旧税率
    ("2026-10-18", 0.0005),                         # 当代 → 新税率
])
def test_a2_boundary_dates(as_of, expected):
    assert engine_stamp_rate(Costs(), as_of) == expected
    assert TrackingCosts()._stamp_rate(as_of) == expected


@pytest.mark.parametrize("as_of", [None, "", "   "])
def test_a2_missing_date_falls_back_to_current(as_of):
    """未提供日期 → 现行税率（与修复前语义一致，工程收敛不改口径）。"""
    assert engine_stamp_rate(Costs(), as_of) == 0.0005
    assert TrackingCosts()._stamp_rate(as_of) == 0.0005


def test_a2_empty_change_date_means_always_current():
    """`stamp_duty_change_date` 为空 ⇒ 不启用分段，恒走现行税率。"""
    spec = Costs(stamp_duty_change_date="")
    assert engine_stamp_rate(spec, "20200103") == 0.0005


# ---------------------------------------------------------------------------
# A-3 跨线净收益确实变化（修前 vs 修后）
# ---------------------------------------------------------------------------
def test_a3_crossing_cost_changes_in_the_right_direction():
    """无横线日期传入时，修复后成本必须**更高**（旧税率 1‰ > 新税率 0.5‰）。"""
    notional = 100_000.0
    trade_date = "20230825"          # 无横线 ⇒ 唯一能触发 #15 的格式

    legacy_rate = 0.0005 if _legacy_string_compare(trade_date) else 0.001
    fixed_rate = engine_stamp_rate(Costs(), trade_date)

    assert fixed_rate == 0.001, "A-3：修复后仍判为新税率，修复未生效"
    assert legacy_rate == 0.0005, "A-3：对照组（旧实现）未复现出 bug，对照失效"

    delta = notional * (fixed_rate - legacy_rate)
    assert delta == pytest.approx(50.0), (
        f"A-3：单边成本差应为 100000×0.5‰ = 50 元，实得 {delta}"
    )

    # 方向：成本更高 ⇒ 同笔卖出的净收益更低
    gross = 110_000.0
    legacy_net = gross - _legacy_cost(gross, trade_date, legacy_rate)
    fixed_net = gross - _legacy_cost(gross, trade_date, fixed_rate)
    assert fixed_net < legacy_net, "A-3：修复后净收益反而更高，方向错误"


def _legacy_cost(notional, trade_date, rate):
    """只复刻「印花税」一项，用于隔离出 A-3 想验的那 0.5‰。"""
    return notional * rate


def test_a3_undashed_is_the_only_trigger():
    """证明带横线格式**本来就没 bug**——避免把 A-3 的功劳记错对象。"""
    assert _legacy_string_compare("2023-08-25") is False, (
        "带横线格式在旧实现下就正确，A-3 只对无横线格式成立"
    )


# ---------------------------------------------------------------------------
# A-4 存量零影响
# ---------------------------------------------------------------------------
def test_a4_existing_rows_unchanged():
    """`tracking.db` 存量行的 `return_pct` 在修复后必须逐位相同。

    修 #15 是**防御性修复**：存量 13 行 `rec_date` 全为 `YYYY-MM-DD`
    且均在 2026 年（远晚于 2023-08-28）⇒ 修与不修都走现行税率。

    库不存在时 **skip**（不是 fail）：这是运行产物、从未入 git，
    在别的机器上跑不代表修复有问题。
    """
    if not DB_PATH.is_file():
        pytest.skip(f"A-4：{DB_PATH.name} 不存在（运行产物，未入 git），跳过存量比对")

    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    try:
        rows = conn.execute(
            "SELECT rec_date, rec_price, close_n, return_pct FROM recommendations"
        ).fetchall()
    finally:
        conn.close()

    assert rows, "A-4：库存在但 recommendations 为空，无法比对"
    bad = []
    for rec_date, rec_price, close_n, stored in rows:
        # 用**修复后**的代码重算
        recomputed = _net_return(rec_price, close_n, as_of=rec_date)
        if recomputed != stored:
            bad.append((rec_date, stored, recomputed))
    assert not bad, (
        f"A-4：修复改变了存量数字（应为零影响）:\n  "
        + "\n  ".join(f"{d}: 库内 {s} → 重算 {r}" for d, s, r in bad[:10])
    )


def _net_return(rec_price, close_n, costs=None, as_of=None):
    """与 `track.costs.net_return_pct` 同口径（此处内联，避免依赖其签名变化）。"""
    from track.costs import net_return_pct
    return net_return_pct(rec_price, close_n, TrackingCosts(), as_of=as_of)


def test_a4_all_dates_are_post_change():
    """若这条失败，说明库里出现了跨线记录 ⇒ A-4 的前提被打破，须重新评估影响面。"""
    if not DB_PATH.is_file():
        pytest.skip(f"A-4：{DB_PATH.name} 不存在，跳过")
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    try:
        dates = [r[0] for r in conn.execute("SELECT rec_date FROM recommendations")]
    finally:
        conn.close()
    crossing = [d for d in dates if cost_model.norm_date(d) < cost_model.norm_date(cost_model.STAMP_DUTY_CHANGE_DATE)]
    assert not crossing, (
        f"A-4：出现跨生效日记录 {crossing[:5]} ⇒ 修复会改变存量，"
        "须先重估影响面再继续（见预注册 §五.4）"
    )


# ---------------------------------------------------------------------------
# A-5 无第三方副本
# ---------------------------------------------------------------------------
def test_a5_no_third_party_copy_of_stamp_logic():
    """`stamp_duty_change_date` 只允许出现在权威源与其 import 方。

    纯 Python 遍历，**不 shell out**（2026-10-17 教训：`subprocess` 调 grep
    在缺 grep.exe 的环境下会把「环境缺失」伪装成「断言失败」）。

    白名单外还有两类命中需要区别对待：
    - `tests/`：验证者不是副本，**单独由 `test_a5_no_string_compare_in_tests` 判**
      （那条只抓「字符串比较」这个真根因，不抓字段名）；
    - `scripts/run_cost_model_check.py`：**合法的对照组配置**，
      见 `test_a5_legacy_kwargs_is_a_deliberate_control`。
    """
    allowed = {
        (ROOT / "cost_model.py").resolve(),
        (ROOT / "backtest_engine.py").resolve(),
        (ROOT / "track" / "costs.py").resolve(),
        (ROOT / "scripts" / "run_cost_model_check.py").resolve(),
    }
    hits = {}
    for path in sorted(ROOT.rglob("*.py")):
        if ".git" in path.parts or "__pycache__" in path.parts:
            continue
        if "tests" in path.parts:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        n = len(re.findall(r"stamp_duty_change_date", text))
        if n:
            hits[path.resolve()] = n

    extra = {p: n for p, n in hits.items() if p not in allowed}
    assert not extra, (
        "A-5：出现了权威源之外的副本（复制一次就会独立腐化）:\n  "
        + "\n  ".join(f"{p.relative_to(ROOT)}: {n} 处" for p, n in sorted(extra.items()))
    )
    # 三个合法位置都必须命中，否则说明权威源没被接上
    missing = {p for p in allowed if p not in hits}
    assert not missing, (
        "A-5：权威源/调用方未出现该常量，接线可能断了:\n  "
        + "\n  ".join(str(p.relative_to(ROOT)) for p in sorted(missing))
    )


def test_a5_legacy_kwargs_is_a_deliberate_control():
    """`run_cost_model_check.LEGACY_COSTS_KWARGS` 是**故意关闭分段**的对照组。

    它把 `stamp_duty_change_date` 设为 `"0001-01-01"`，使任何交易日都
    `>=` 生效日 ⇒ 恒走现行税率，用来复现「修正前的成本模型」。
    这是**配置**，不是逻辑副本；但它依赖哨兵值，故在此钉住行为。
    """
    import importlib.util
    path = ROOT / "scripts" / "run_cost_model_check.py"
    if not path.is_file():
        pytest.skip("A-5：run_cost_model_check.py 不存在")
    spec = importlib.util.spec_from_file_location("_rcmc", path)
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception as exc:  # 依赖缺失等
        pytest.skip(f"A-5：无法加载 run_cost_model_check（{exc}）")

    kwargs = getattr(mod, "LEGACY_COSTS_KWARGS", None)
    assert kwargs, "A-5：LEGACY_COSTS_KWARGS 不见了，对照组失效"
    sentinel = kwargs.get("stamp_duty_change_date")
    assert sentinel == "0001-01-01", f"A-5：哨兵值被改为 {sentinel!r}，对照组语义已变"
    # 哨兵值必须真的关闭分段
    spec_obj = Costs(stamp_duty_change_date=sentinel, transfer_fee_rate=0.0)
    for d in ("20050103", "20230825", "20230101"):
        assert engine_stamp_rate(spec_obj, d) == 0.0005, (
            f"A-5：哨兵 {sentinel} 未能关闭分段（{d}），对照组已失效"
        )


def test_a5_no_string_compare_in_tests():
    """tests/ 里不许再出现**字符串比较日期**这个真根因。

    字段名出现在测试里是合法的（测试就要引用被控常量）；
    但 `str(x) >= "2023-08-28"` 这种**逐字符比日期**的写法必须绝迹。

    用 **AST** 而非正则：天然跳过注释与 docstring（正则会把
    `test_track_costs.py` 里解释根因的文字也当成违规——那是**假红**），
    且能精确豁免「故意复刻旧逻辑的对照组」。
    """
    import ast

    # 故意保留的旧逻辑复刻（A-3 的对照组），见 _legacy_string_compare
    allowed_funcs = {"_legacy_string_compare"}
    date_str = re.compile(r"^\d{4}-\d{2}-\d{2}$")

    offenders = []
    for path in sorted((ROOT / "tests").rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
        except (OSError, SyntaxError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef) or node.name in allowed_funcs:
                continue
            for sub in ast.walk(node):
                if not isinstance(sub, ast.Compare):
                    continue
                # 左操作数必须是 str(...) 调用
                if not (isinstance(sub.left, ast.Call)
                        and isinstance(sub.left.func, ast.Name)
                        and sub.left.func.id == "str"):
                    continue
                # 至少一个比较对象是日期样式字符串常量
                has_date = any(
                    isinstance(c, ast.Constant) and isinstance(c.value, str)
                    and date_str.match(c.value)
                    for c in sub.comparators
                )
                if has_date:
                    offenders.append(f"{path.relative_to(ROOT)}:{sub.lineno}")

    assert not offenders, (
        "A-5：测试里仍有字符串比较日期的写法（缺陷 #15 的根因）:\n  "
        + "\n  ".join(offenders)
    )


def test_a5_engine_and_track_share_one_truth():
    """两个调用方对同一日期必须给出同一个税率（否则「权威」名不副实）。"""
    for d in ("20230825", "2023-08-25", "2023-08-28", "20230828", "2026-01-01"):
        a = engine_stamp_rate(Costs(), d)
        b = TrackingCosts()._stamp_rate(d)
        assert a == b, f"A-5：{d} 引擎 {a} vs 跟踪 {b}，两份实现已漂移"


def test_a5_trade_cost_delegates_to_authority():
    """`_trade_cost` 的印花税部分必须等于 `cost_model` 的权威计算结果。"""
    spec = Costs()
    notional = 123_456.0
    for d in ("20230825", "20230828"):
        total = _trade_cost(notional, "sell", spec, d)
        expected = (max(spec.min_commission, notional * spec.commission_rate)
                    + notional * cost_model.stamp_rate(spec, d)
                    + notional * spec.transfer_fee_rate)
        assert total == pytest.approx(expected), f"A-5：{d} 计费与权威口径不符"
    # 买入无印花税
    buy = _trade_cost(notional, "buy", spec, "20230825")
    assert buy == pytest.approx(
        max(spec.min_commission, notional * spec.commission_rate)
        + notional * spec.transfer_fee_rate
    )


def test_a5_norm_date_handles_none_and_empty():
    """`norm_date` 对空值返回 None（不返回字符串 "None"）。"""
    assert cost_model.norm_date(None) is None
    assert cost_model.norm_date("") is None
    assert cost_model.norm_date("   ") is None
    assert cost_model.norm_date("2023-08-25") == "20230825"
    assert cost_model.norm_date("2023/08/25") == "20230825"
