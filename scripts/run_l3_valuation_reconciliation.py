# -*- coding: utf-8 -*-
"""L3 估值历史的**抽样对账**（设计文档规定的「接入前必过闸门」）。

对账对象：**baostock 回溯估值** vs **本项目 `pit_fundamentals`**。

## 口径要点（**这里最容易出错**）

| 项 | 本项目 v3 | baostock |
|---|---|---|
| 价格 | **qfq 前复权**（锚定 2026-09-11） | `adjustflag='3'` **不复权** |

→ **绝不能直接比 `pb` / `pe_ttm`**（会掺入复权因子，差异全是假信号）。
→ 改为比「**隐含分母**」：``close / pbMRQ`` ↔ 我们的 ``bps``；``close / peTTM`` ↔ 我们的 ``ttm_eps``。

## PIT 对齐检验（2026-10-12 重构）

**旧版缺陷**：把「**A 股披露日**」当作「**首次公开日**」——
对 **A+H 公司**（港股业绩公告通常早于 A 股年报 4~8 周）会把
「baostock 正确、我方偏晚」**误判成 `early`（疑似前视）**。

**新版判据**：改用 **baostock 隐含 EPS 的「切换日」** 与两个客观锚点比较 ——

| 分类 | 判据 | 含义 |
|---|---|---|
| **`impossible`** | 切换日 **< 报告期起始** | **确凿前视** —— 该期数据尚不存在（无需任何披露日数据即可判定） |
| **`earlier_than_a_share`** | 报告期起始 ≤ 切换日 < `A股披露日 - 3` | **中性** —— 可能是港股公告 / 业绩快报 / 业绩预告；**不等于前视** |
| `aligned` | 切换日 ≈ `A股披露日`（±3 交易日） | 与 A 股披露同步 |
| `late` | 切换日 > `A股披露日 + 3` | 偏晚（保守） |
| `no_match` / `no_data` | 窗口内无「引入本期 TTM」的切换 / 缺值 | 无法判定（含**小变化被阈值滤掉**） |

⚠️ **`impossible` 为何收紧到「报告期起始」而非「报告期末」**：
baostock 的隐含 EPS 有 **0.03%~0.31% 的数值漂移**，而小的真实变化可低至 **0.17%** ——
**两者量级重叠，无阈值可分辨**。若用「报告期末」，一次 0.31% 的漂移就会**伪造出
「早于报告期末」的切换**（实测 600519 的 2025-09-01）。
→ **宁可把这类归入中性的 `earlier_than_a_share`，也不做无根据的指控。**

**A+H 标注**：命中 `earlier_than_a_share` 时，额外标注该股是否在 **A+H 名单**里
（名单来源见 :func:`load_ah_codes`）——**用于解释，不用于判定**。

⚠️ **局限（如实声明）**：只在**有披露日**的 `(code, period)` 上检验；样本为**抽样**；
`earlier_than_a_share` 只是**需解释**，不是前视结论；A+H 名单用**名字匹配**，是**近似**。

⚠️ **样本量的强度边界（2026-10-14 补，主干 P010 Q3.1 评审意见）**：
本脚本是**逻辑一致性检查**，不是**统计代表性检查**。
`impossible` 是逻辑判据（切换日 < 报告期起始 = 数据来自未来）——
**不需要大样本即可证伪**：n=60 上复现 0 = 未发现逻辑矛盾。
但 n=60 **不足以发现小比例错误**（错误率 1% 时检出概率仅 ~45%）。
→ 引用结论时必须写「逻辑一致性检查通过」，**不得**写成「统计上代表性验证通过」。
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import statistics
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pit.pit_fundamentals import (  # noqa: E402
    PitFundamentals,
    load_disclosures,
    load_records,
)

ROOT = Path(__file__).resolve().parent.parent
AH_CACHE = ROOT / "reports" / "ah_codes.json"

#: 待检验的报告期（都已过披露日，且跨年报/半年报/三季报）
PERIODS = ("2023-06-30", "2023-09-30", "2023-12-31", "2024-06-30",
           "2024-09-30", "2024-12-31", "2025-06-30", "2025-09-30")
#: 「切换日 ≈ 披露日」的容忍（交易日）
ALIGN_TOL = 3
#: 「切换早于披露日」的最大可解释间隔（自然日）—— 超过即视为「本期无切换」
EARLIER_MAX = 120
#: 「该切换确实引入本期 TTM」的值校验容差（相对）
MATCH_TOL = 0.02
#: 可比性的最小分母（EPS 绝对值下限）——低于此值相对差无意义
MIN_EPS = 0.01
#: 在披露日附近搜索切换点的半窗（自然日）
SWITCH_WINDOW = 150

Row = Tuple[str, Optional[float], Optional[float], Optional[float]]  # date, close, peTTM, pbMRQ


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------
def _f(v: Any) -> Optional[float]:
    s = str(v or "").strip()
    if s == "":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _prev_day(day: str) -> str:
    return (dt.date.fromisoformat(day) - dt.timedelta(days=1)).isoformat()


def _day_diff(later: str, earlier: str) -> int:
    """``later - earlier`` 的自然日数。"""
    return (dt.date.fromisoformat(later) - dt.date.fromisoformat(earlier)).days


def _rel(a: Optional[float], b: Optional[float]) -> Optional[float]:
    if a is None or b is None or b == 0:
        return None
    return abs(a - b) / abs(b)


def _summary(vals: List[float]) -> Dict[str, Any]:
    if not vals:
        return {"n": 0}
    s = sorted(vals)
    return {
        "n": len(vals),
        "median": round(statistics.median(vals), 6),
        "p90": round(s[min(len(s) - 1, int(len(s) * 0.9))], 6),
        "max": round(s[-1], 6),
        "share_le_1pct": round(sum(1 for x in vals if x <= 0.01) / len(vals), 4),
    }


# ---------------------------------------------------------------------------
# A+H 名单（用于**解释** earlier_than_a_share，不用于判定）
# ---------------------------------------------------------------------------
def build_ah_codes(fundamentals: Path, cache: Path = AH_CACHE) -> Dict[str, Any]:
    """构造 A+H 名单（A 股 6 位代码）。

    **来源**：akshare ``stock_zh_ah_name()`` 的 **H 股名单** →
    与本地 ``fundamentals.jsonl`` 的 ``name`` 做**精确名字匹配**。

    ⚠️ 这是**近似**：改名、A/H 简称不一致会**漏**；同名不同司会**误纳**。
    故本名单**只用于解释**「为何切换早于 A 股披露日」，**不用于判定前视**。
    结果缓存到 ``cache``，供离线复跑。
    """
    if cache.exists():
        try:
            d = json.loads(cache.read_text(encoding="utf-8"))
            if d.get("codes"):
                return d
        except (json.JSONDecodeError, OSError):
            pass
    import akshare as ak  # 惰性导入：可选依赖

    hnames = {str(n).strip() for n in ak.stock_zh_ah_name()["名称"]}
    names: Dict[str, str] = {}
    for line in fundamentals.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        names.setdefault(str(r.get("code") or "").zfill(6), str(r.get("name") or "").strip())
    hit = sorted(c for c, n in names.items() if n and n in hnames)
    out = {
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "source": "akshare stock_zh_ah_name() 的 H 股名单 × fundamentals.jsonl 的 name 精确匹配",
        "h_names": len(hnames),
        "a_codes_total": len(names),
        "codes": hit,
        "caveat": "名字匹配是近似：改名/简称不一致会漏，同名不同司会误纳；只用于解释，不用于判定",
    }
    cache.parent.mkdir(parents=True, exist_ok=True)
    with cache.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(out, ensure_ascii=False, indent=2))
    return out


# ---------------------------------------------------------------------------
# 取数
# ---------------------------------------------------------------------------
def _fetch(symbol: str, start: str, end: str) -> List[Row]:
    """取 (date, close, peTTM, pbMRQ)。``adjustflag='3'`` = **不复权**。"""
    import baostock as bs

    rs = bs.query_history_k_data_plus(
        symbol, "date,close,peTTM,pbMRQ", start_date=start, end_date=end,
        frequency="d", adjustflag="3")
    if rs.error_code != "0":
        raise RuntimeError(f"{symbol}: {rs.error_code} {rs.error_msg}")
    out: List[Row] = []
    while rs.next():
        r = rs.get_row_data()
        out.append((r[0], _f(r[1]), _f(r[2]), _f(r[3])))
    return out


def _bs_symbol(code: str) -> str:
    pref = "sh" if code[0] in "569" else ("bj" if code[0] in "48" else "sz")
    return f"{pref}.{code}"


def implied_eps(close: Optional[float], pe: Optional[float]) -> Optional[float]:
    """隐含 TTM EPS = close / peTTM（peTTM ≤ 0 或缺失 → ``None``）。"""
    if close is None or pe is None or pe <= 0:
        return None
    return close / pe


def switch_dates(rows: List[Row], rel_tol: float = 0.005) -> List[Tuple[str, float]]:
    """baostock 隐含 EPS 的**切换点** ``[(date, eps)]``。

    相邻交易日隐含 EPS 相对变化 > ``rel_tol`` 即记为切换。

    ⚠️ **``rel_tol`` 的选择是在「漂移」与「小变化」之间取舍，两者量级重叠**：
    - baostock 的 ``close/peTTM`` 存在 **0.03%~0.31% 的数值漂移**（非报表变化）
    - 而**小的真实报表变化可低至 0.17%**（实测：600519 的 2025Q3，71.63 → 71.75）

    → **没有任何阈值能同时「不漏真变化」且「不误纳漂移」**。
    取 **0.5%**：**宁可漏报小变化**（记为 ``no_match``），也不把漂移当成切换
    （误纳漂移会**伪造出「早于披露日」甚至「早于报告期」的切换**）。
    """
    out: List[Tuple[str, float]] = []
    prev: Optional[float] = None
    for d, close, pe, _pb in rows:
        e = implied_eps(close, pe)
        if e is None:
            continue
        if prev is None or abs(e - prev) > abs(prev) * rel_tol:
            out.append((d, e))
        prev = e
    return out


def period_start(period: str) -> str:
    """报告期 → **该期起始日**（``2025-09-30`` → ``2025-07-01``）。

    用于 `impossible` 判定：切换日早于报告期起始 = **该期数据尚不存在**。
    """
    y, md = int(period[:4]), period[5:10]
    q_start = {"03-31": "01-01", "06-30": "04-01", "09-30": "07-01", "12-31": "10-01"}
    return f"{y}-{q_start.get(md, '01-01')}"


def prev_period(period: str) -> str:
    """报告期 → **上一个报告期**（``2025-06-30`` → ``2025-03-31``；``2025-03-31`` → 上年 ``12-31``）。

    用于**归属守卫**：某次切换必须晚于上一期的披露日，否则它属于上一期
    （实测：300727 的 2023-04-27 是 **Q1** 的切换，却被算到 H1 名下 —— 因为
    ``PERIODS`` 里没有 Q1，原先的「上一个列表项」守卫失效）。
    """
    y, md = int(period[:4]), period[5:10]
    prev_md = {"03-31": ("12-31", -1), "06-30": ("03-31", 0),
               "09-30": ("06-30", 0), "12-31": ("09-30", 0)}
    pmd, dy = prev_md.get(md, ("12-31", -1))
    return f"{y + dy}-{pmd}"


def _nearest_switch(sws: List[Tuple[str, float]], day: str) -> Optional[Tuple[str, float]]:
    """距 ``day`` 最近的切换点（限 :data:`SWITCH_WINDOW` 自然日内）。

    ⚠️ **本函数已不用于 PIT 判定** —— 它会把「下一期的切换」误配到本期
    （实测：688981 的 2023 年报切换在 2024-02-07，但离披露日 2024-03-29 更近的
    是下一期的 2024-05-10 → 会选错）。保留仅供诊断。
    """
    best: Optional[Tuple[str, float]] = None
    best_gap = SWITCH_WINDOW + 1
    for d, e in sws:
        gap = abs(_day_diff(d, day))
        if gap < best_gap:
            best, best_gap = (d, e), gap
    return best


def _last_switch_le(sws: List[Tuple[str, float]], day: str) -> Optional[Tuple[str, float]]:
    """**最后一次**日期 ≤ ``day`` 的切换点（无则 ``None``）。"""
    cands = [x for x in sws if x[0] <= day]
    return cands[-1] if cands else None


def _first_switch_gt(sws: List[Tuple[str, float]], day: str) -> Optional[Tuple[str, float]]:
    """**第一次**日期 > ``day`` 的切换点（无则 ``None``）。"""
    cands = [x for x in sws if x[0] > day]
    return cands[0] if cands else None


def _shift(day: str, days: int) -> str:
    return (dt.date.fromisoformat(day) + dt.timedelta(days=days)).isoformat()


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="L3 估值历史抽样对账（含 PIT 对齐检验）")
    ap.add_argument("--dataset", default="D:/tdx_dataset_v3")
    ap.add_argument("--codes", default="", help="逗号分隔的 6 位代码；留空则自动均匀抽样")
    ap.add_argument("--n", type=int, default=24, help="自动抽样的标的数")
    ap.add_argument("--start", default="2023-01-01")
    ap.add_argument("--end", default="2025-12-31")
    ap.add_argument("--out", default="")
    ap.add_argument("--no-ah", action="store_true", help="不加载 A+H 名单（离线/省时）")
    args = ap.parse_args(argv)

    ds = Path(args.dataset)
    recs = load_records(ds / "fundamentals.jsonl")
    disc = load_disclosures(ds / "disclosure_dates.jsonl")
    pf = PitFundamentals(recs, disc)
    print(f"基本面 {len(recs):,} 条 · 披露日 {len(disc):,} 条", flush=True)

    ah: Dict[str, Any] = {"codes": []}
    if not args.no_ah:
        try:
            ah = build_ah_codes(ds / "fundamentals.jsonl")
            print(f"A+H 名单 {len(ah['codes'])} 只（名字匹配，近似）", flush=True)
        except Exception as exc:      # 网络/依赖失败不阻塞对账，但**显式说明**
            print(f"⚠️ A+H 名单不可用（{type(exc).__name__}）—— 继续，仅少一层解释", flush=True)
    ah_set = set(ah.get("codes") or [])

    if args.codes:
        codes = [c.strip().zfill(6) for c in args.codes.split(",") if c.strip()]
    else:
        pool = sorted(p.stem for p in (ds / "stocks").glob("*.csv") if p.stem.isdigit())
        step = max(1, len(pool) // args.n)
        codes = [pool[i * step] for i in range(args.n) if i * step < len(pool)]
    print(f"抽样 {len(codes)} 只 · 窗口 {args.start}~{args.end}", flush=True)

    import baostock as bs

    bs.login()
    data: Dict[str, List[Row]] = {}
    failed: List[str] = []
    try:
        for i, c in enumerate(codes, 1):
            try:
                data[c] = _fetch(_bs_symbol(c), args.start, args.end)
            except Exception as exc:      # 单只失败不拖垮整批，但**必须记录**
                failed.append(f"{c}: {exc}")
            if i % 10 == 0:
                print(f"    ... {i}/{len(codes)}（成功 {len(data)} · 失败 {len(failed)}）", flush=True)
    finally:
        bs.logout()
    print(f"取数成功 {len(data)} 只 · 失败 {len(failed)} 只", flush=True)

    bps_rels: List[float] = []
    eps_rels: List[float] = []
    eps_signed: List[float] = []
    pit: Dict[str, int] = {"impossible": 0, "earlier_than_a_share": 0, "aligned": 0,
                           "late": 0, "no_our_event": 0, "no_match": 0, "no_data": 0}
    flags: List[Dict[str, Any]] = []

    for c, rows in data.items():
        sws = switch_dates(rows)
        # ①② bps / ttm_eps 逐点比对
        for d, close, pe, pb in rows:
            rec = pf.as_of(c, d)
            if rec is None:
                continue
            r_bps = _rel((close / pb) if (close and pb and pb > 0) else None, _f(rec.get("bps")))
            if r_bps is not None:
                bps_rels.append(r_bps)
            eps_b = implied_eps(close, pe)
            eps_o = pf.ttm_eps_as_of(c, d)
            # ⚠️ **近零分母保护**：``|eps_o|`` 极小时相对差会爆到 1e14 量级，
            # 污染中位数/P90（实测 100 只样本 max = 1.09e14）→ 一律视为不可比。
            comparable = eps_o is not None and abs(eps_o) >= MIN_EPS
            r_eps = _rel(eps_b, eps_o) if comparable else None
            if r_eps is not None:
                eps_rels.append(r_eps)
            if eps_b is not None and comparable and eps_o:
                eps_signed.append((eps_b - eps_o) / eps_o)

        # ③ PIT 对齐检验
        #   锚点 = 「**D + 容忍窗之前最后一次**切换」（结合值校验 + 归属守卫）
        for p in PERIODS:
            D = disc.get((c, p))
            if not D:
                continue
            prev_D = disc.get((c, prev_period(p)))   # 上一期的披露日（含不在 PERIODS 里的 Q1）
            o_pre = pf.ttm_eps_as_of(c, _prev_day(D))
            o_post = pf.ttm_eps_as_of(c, D)
            if o_post is None:
                pit["no_data"] += 1
                continue
            if o_pre == o_post:
                pit["no_our_event"] += 1      # 我方在该披露日未变 → 本期不改变 TTM，不作检验
                continue
            # 锚点 = 「**D + 容忍窗之前最后一次**切换」——
            #   ① 不会像「最近切换」那样被**下一期**干扰（实测 688981 会选错）；
            #   ② 不会像「按值匹配」那样被**跨年相近 TTM** 干扰（实测 000001 会选错）。
            limit = _shift(D, ALIGN_TOL)
            sw_le = _last_switch_le(sws, limit)
            sw_gt = _first_switch_gt(sws, limit)
            if sw_le is None:
                # 窗口内尚无切换：若之后不久有切换 → 偏晚；否则本期不改变 TTM
                if sw_gt is not None and _day_diff(sw_gt[0], D) <= EARLIER_MAX:
                    pit["late"] += 1
                else:
                    pit["no_match"] += 1
                continue
            swd = sw_le[0]
            gap = _day_diff(D, swd)               # >0 表示切换**早于**披露日
            # ⚠️ **归属守卫**：该切换必须**晚于上一期的披露日**，否则它属于上一期
            # （实测：600519 的 2025-08-13 是 **H1** 的切换，若不加此守卫会被
            #  归到 Q3 名下 —— 虽落在中性类，但会虚增 `earlier_than_a_share`）。
            if prev_D is not None and swd <= prev_D:
                pit["no_match"] += 1
                continue
            # ⚠️ **值校验**：该切换必须确实**引入了本期 TTM**（≈ 我方披露后的值），
            # 否则它可能是**上一期**的切换（实测：600519 的 2025-09-01 切换与 Q3 报无关，
            # 若不校验会被误判为 `impossible`）。
            r_match = _rel(sw_le[1], o_post)
            if r_match is None or r_match > MATCH_TOL:
                pit["no_match"] += 1
                continue
            if gap <= ALIGN_TOL:
                pit["aligned"] += 1
            elif swd < period_start(p):       # 切换早于**报告期起始** → 该期数据尚不存在
                pit["impossible"] += 1
                flags.append({"code": c, "period": p, "kind": "impossible",
                              "switch": swd, "period_start": period_start(p),
                              "disclose": D, "ah": c in ah_set})
            elif gap <= EARLIER_MAX:
                pit["earlier_than_a_share"] += 1
                if len(flags) < 20:
                    flags.append({"code": c, "period": p, "kind": "earlier_than_a_share",
                                  "switch": swd, "disclose": D, "gap_days": gap,
                                  "ah": c in ah_set})
            else:
                pit["no_match"] += 1              # 上次切换离得太远 → 本期无切换
    total = sum(v for k, v in pit.items() if k not in ("no_data", "no_switch"))
    ah_in_earlier = sum(1 for f in flags if f["kind"] == "earlier_than_a_share" and f["ah"])
    res: Dict[str, Any] = {
        "sample_codes": len(data),
        "failed_codes": failed,
        "window": [args.start, args.end],
        "bps_relative_diff": _summary(bps_rels),
        "eps_relative_diff": _summary(eps_rels),
        "eps_signed_diff_median": (round(statistics.median(eps_signed), 6) if eps_signed else None),
        "pit_alignment": pit,
        "pit_total": total,
        "pit_impossible": pit["impossible"],
        "pit_earlier_than_a_share": pit["earlier_than_a_share"],
        "pit_earlier_ah_hits": ah_in_earlier,
        "ah_codes_used": len(ah_set),
        "flags": flags[:20],
        "caveats": [
            "PIT 检验仅覆盖有披露日数据的 (code, period) 对；样本为抽样而非全市场",
            "impossible = 切换日早于报告期末 → 确凿前视，无需披露日数据即可判定",
            "earlier_than_a_share = 早于 A 股披露日但晚于报告期末 → 中性，"
            "可能来自港股公告/业绩快报/预告，不等于前视",
            "A+H 名单用名字匹配，是近似；只用于解释，不用于判定",
            "baostock 用不复权价、本项目 v3 用 qfq —— 故只比隐含分母，不比比率本身",
        ],
    }
    print()
    print("=" * 96)
    print(f"bps 相对差: {_summary(bps_rels)}")
    print(f"eps 相对差: {_summary(eps_rels)}（有符号中位 {res['eps_signed_diff_median']}；正=baostock 更高）")
    print(f"PIT 分布  : {pit}")
    print(f"  → 确凿前视 `impossible` = {pit['impossible']}")
    print(f"  → 早于 A 股披露 `earlier_than_a_share` = {pit['earlier_than_a_share']}"
          f"（其中 A+H 命中 {ah_in_earlier}）")
    for f in flags[:10]:
        print(f"     {f}")
    print("=" * 96)
    if args.out:
        outp = Path(args.out)
        outp.parent.mkdir(parents=True, exist_ok=True)
        with outp.open("w", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(res, ensure_ascii=False, indent=2))
        print(f"已写 {outp}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
