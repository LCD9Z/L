# -*- coding: utf-8 -*-
"""跨年代方向验证 · 判定汇总（H-CD）

按 `CROSS_DECADE_PREREG.md` §四 的**事前固定标准**出判定表。

用法：
    python scripts/summarize_cross_decade.py
    python scripts/summarize_cross_decade.py --out reports/cross_decade/VERDICT.json

设计原则（对应预注册）：
- **主口径 = P2（median）**，P1/P3 并列报告（不得只报有利的）
- 「方向一致」= `sign(IC) == DIRECTIONS[f]`（不看显著性与否）
- 截面不足 `min_cross_section` 的窗口标 INCONCLUSIVE，**不计入分母**
- 判定口径写死在 `judge()` 里，与预注册逐条对应，禁止临时调整
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

FACTORS = ["ret20", "vol20", "amihud20", "loga20", "maxret20"]
DIRECTIONS = {"ret20": -1, "vol20": -1, "amihud20": 1, "loga20": -1,
              "maxret20": -1}
GATES = ["abs", "median", "none"]
#: 预注册 §二 的 5 个窗口 + §附录补充的标定参照窗 R
WINDOWS = [("W1", "2003-2007"), ("W2", "2008-2012"), ("W3", "2013-2017"),
           ("W4", "2018-2022"), ("W5", "2023-2026"), ("R", "2021-08~2026-09")]
MAIN_GATE = "median"


def load(tag: str, d: str = "reports/cross_decade"):
    p = os.path.join(d, f"{tag}.json")
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def consistency(data, gate: str, factor: str):
    """返回 (IC, t, 方向是否与冻结一致, 是否有有效值)。"""
    if data is None:
        return None, None, None, False
    g = (data.get("ic_by_gate") or {}).get(gate)
    if not g:
        return None, None, None, False
    v = ((g.get("ic") or {}).get("adj_factor") or {}).get(factor)
    if not v or v.get("ic_mean") is None:
        return None, None, None, False
    ic = v["ic_mean"]
    return ic, v.get("t"), (1 if ic > 0 else -1) == DIRECTIONS[factor], True


def judge(rows):
    """按预注册 §四 判定。

    rows: [(tag, label, data)]，已过滤掉 INCONCLUSIVE 的窗口。

    判定表（主口径 P2）：
      方向稳健     : 5 因子中 ≥4 个在 ≥4 个窗口与冻结方向一致
      部分稳健     : 满足条件的因子为 3 个
      方向区间特定 : ≤2 个因子满足
    """
    n_win = len(rows)
    if n_win == 0:
        return {"verdict": "INCONCLUSIVE", "reason": "无有效窗口",
                "n_windows": 0, "per_factor": {}}
    per: Dict[str, Dict[str, Any]] = {}
    for f in FACTORS:
        n_ok = sum(1 for _tag, _lab, d in rows
                   if consistency(d, MAIN_GATE, f)[2] is True)
        per[f] = {"一致窗口数": n_ok, "总窗口数": n_win,
                  "一致": n_ok >= max(4, n_win) if n_win >= 4 else None}
    n_good = sum(1 for f in FACTORS
                 if n_win >= 4 and per[f]["一致窗口数"] >= 4)
    if n_win < 4:
        verdict = "INCONCLUSIVE"
        reason = f"有效窗口仅 {n_win} 个，不足 4 个，无法判定"
    elif n_good >= 4:
        verdict = "方向稳健"
        reason = f"{n_good}/5 个因子在 ≥4 个窗口方向一致"
    elif n_good == 3:
        verdict = "部分稳健"
        reason = "3/5 个因子在 ≥4 个窗口方向一致"
    else:
        verdict = "方向区间特定"
        reason = (f"仅 {n_good}/5 个因子在 ≥4 个窗口方向一致 → "
                  "现结论必须加限定「仅适用于 2021-08 之后」")
    return {"verdict": verdict, "reason": reason, "n_windows": n_win,
            "n_factors_consistent": n_good, "per_factor": per}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="reports/cross_decade")
    ap.add_argument("--min-cross-section", type=int, default=200)
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    print("=" * 78)
    print("跨年代方向验证 · 判定（H-CD）  主口径 = P2 median")
    print("=" * 78)

    # --- 各窗口 × 各口径的期数（先看可行性） ---
    print("\n【一】各窗口 × 口径的可行期数（截面 < %d 的口径不可判）"
          % args.min_cross_section)
    print("-" * 78)
    hdr = f"{'窗口':<6}{'区间':<18}" + "".join(f"{g:>16}" for g in GATES)
    print(hdr)
    loaded = {}
    for tag, label in WINDOWS:
        d = load(tag, args.dir)
        loaded[tag] = d
        cells = []
        for g in GATES:
            if d is None:
                cells.append("(未跑)")
                continue
            v = (d.get("ic_by_gate") or {}).get(g)
            if not v:
                cells.append("(无此口径)")
                continue
            n = v.get("cross_sections") or 0
            mark = "" if n > 0 else " ✗"      # 0 期 = 该口径完全不可行
            cells.append(f"{n}期/{v.get('avg_cross_section')}{mark}")
        print(f"{tag:<6}{label:<18}" + "".join(f"{c:>16}" for c in cells))

    # --- 逐窗口 × 逐因子 明细（主口径） ---
    print(f"\n【二】主口径 P2（{MAIN_GATE}）逐因子 IC/t × 各窗口")
    print("-" * 78)
    print(f"{'因子':<10}{'冻结':>5}" + "".join(f"{w:>13}" for w, _ in WINDOWS))
    for f in FACTORS:
        row = f"{f:<10}{DIRECTIONS[f]:>+5}"
        for tag, _l in WINDOWS:
            ic, _t, ok, has = consistency(loaded.get(tag), MAIN_GATE, f)
            if not has:
                row += f"{'n/a':>13}"
            else:
                row += f"{ic:+.4f}{'✓' if ok else '✗':>7}"
        print(row)

    # --- 判定 ---
    # ⚠️ 判据说明（2026-10-11 修正）：
    # `min_cross_section` 是**单期**截面的下限，脚本在计算时已按它过滤
    # （`if len(sel) < min_cross_section: continue`）。
    # 因此输出里的 `cross_sections` 是**通过筛选的期数**，不是截面数。
    # 一个口径「完全不可行」当且仅当 **没有一期**达标（期数 == 0）。
    #
    # 早期版本误把「期数」当成「截面数」去比 200，导致 W1（116 期）
    # 被错误标成 INCONCLUSIVE。已修正。
    #
    # 期数本身作为**辅助信息**输出（t 检验需要足够期数），
    # 但不改变预注册 §四 的判定表。
    valid = []
    incon = []
    for tag, label in WINDOWS:
        d = loaded.get(tag)
        v = (d.get("ic_by_gate") or {}).get(MAIN_GATE) if d else None
        n = (v or {}).get("cross_sections") or 0
        if d is None or n == 0:
            incon.append((tag, label, n))
        else:
            valid.append((tag, label, d))

    print(f"\n【三】判定（预注册 §四，主口径 {MAIN_GATE}）")
    print("-" * 78)
    if incon:
        print("标 INCONCLUSIVE（该口径无任何一期达标，不可判）：")
        for tag, label, n in incon:
            print(f"  {tag} {label}：{n} 期")
    print("有效窗口期数（辅助参考，t 检验需足够期数）：")
    for tag, label, d in valid:
        v = d["ic_by_gate"][MAIN_GATE]
        print(f"  {tag} {label}：{v['cross_sections']} 期，"
              f"平均截面 {v['avg_cross_section']}")
    res = judge(valid)
    print(f"\n有效窗口：{[t for t, _l, _d in valid]}")
    for f in FACTORS:
        p = res["per_factor"][f]
        print(f"  {f:<10} 一致窗口 {p['一致窗口数']}/{p['总窗口数']}"
              f"  {'✓' if p['一致窗口数'] >= 4 else '✗'}")
    print(f"\n>>> 判定：{res['verdict']}")
    print(f"    {res['reason']}")

    # --- 与历史结论对照 ---
    print("\n【四】与历史结论对照（tdx_ic_full.json，2021-08~2026-09 全量）")
    print("-" * 78)
    hist = os.path.join(args.dir, "..", "tdx_ic_full.json")
    if os.path.exists(hist):
        # 变量名避让：本函数他处以 f 作因子名（str），同名复用会被 mypy 判冲突。
        with open(hist, encoding="utf-8") as _fh:
            h = json.load(_fh)
        for f_ in FACTORS:
            v = h["ic"]["adj_factor"][f_]
            print(f"  {f_:<10} IC {v['ic_mean']:+.6f}  t {v['t']:+.2f}")
        print("  → 参照窗 R 应接近上述数值；偏差大说明实现有误（§二 标定锚）")
    else:
        print(f"  （{hist} 不存在，跳过）")

    if args.out:
        payload = {"verdict": res, "windows_valid": [t for t, _l, _d in valid],
                   "windows_inconclusive": [
                       {"tag": t, "label": l, "cross_sections": n}
                       for t, l, n in incon],
                   "main_gate": MAIN_GATE, "min_cross_section": args.min_cross_section}
        with open(args.out, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=1)
        print(f"\n已写入: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
