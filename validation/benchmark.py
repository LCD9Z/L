# -*- coding: utf-8 -*-
"""Benchmark and excess-return analytics without third-party dependencies."""
import math, statistics

def _clean_curve(curve):
    return [(str(x['date']), float(x['equity'])) for x in curve if x.get('date') is not None and x.get('equity') not in (None,0)]

def _returns(curve):
    pts=_clean_curve(curve)
    return {pts[i][0]: pts[i][1]/pts[i-1][1]-1 for i in range(1,len(pts)) if pts[i-1][1] > 0}

def benchmark_metrics(strategy_curve, benchmark_bars, annualization=252):
    """Compare strategy equity curve with benchmark close series on common dates."""
    sret=_returns(strategy_curve)
    bpts=[(str(b['date']), float(b['close'])) for b in benchmark_bars if b.get('date') is not None and b.get('close') not in (None,0)]
    bret={bpts[i][0]: bpts[i][1]/bpts[i-1][1]-1 for i in range(1,len(bpts)) if bpts[i-1][1] > 0}
    dates=sorted(set(sret)&set(bret))
    if len(dates)<2:
        return {'common_periods':len(dates),'alpha_annualized_pct':None,'beta':None,'information_ratio':None,'excess_return_pct':None}
    sr=[sret[d] for d in dates]; br=[bret[d] for d in dates]
    bm=statistics.mean(br); sm=statistics.mean(sr)
    var_b=statistics.pvariance(br) if len(br)>1 else 0
    cov=sum((x-sm)*(y-bm) for x,y in zip(sr,br, strict=True))/len(sr)
    beta=cov/var_b if var_b else None
    alpha_daily=sm-(beta*bm if beta is not None else bm)
    excess=[x-y for x,y in zip(sr,br, strict=True)]
    tracking=statistics.pstdev(excess) if len(excess)>1 else 0
    ir=statistics.mean(excess)/tracking*math.sqrt(annualization) if tracking else None
    strat_growth=math.prod(1+x for x in sr)-1
    bench_growth=math.prod(1+x for x in br)-1
    return {'common_periods':len(dates),'strategy_return_pct':round(strat_growth*100,3),'benchmark_return_pct':round(bench_growth*100,3),'excess_return_pct':round((strat_growth-bench_growth)*100,3),'alpha_annualized_pct':round(alpha_daily*annualization*100,3),'beta':round(beta,4) if beta is not None else None,'information_ratio':round(ir,4) if ir is not None else None}


# ---------------------------------------------------------------------------
# 等权全市场基准（2026-09-19 新增）
#
# 动机：本项目此前的超额一律以**沪深300**为基准，而策略池是**全市场**抽样。
# 实测（ALPHA_CAPABILITY_GAP_ANALYSIS.md §3.1）显示两者在部分窗口相差
# 11~16pp，方向为「等权全市场 > 沪深300」，即用沪深300 会**高估**策略超额。
# 因此需要第二个口径正确的基准。
# ---------------------------------------------------------------------------

def daily_returns_by_code(bars_by_code):
    """把 ``{code: [bars]}`` 归约为 ``{code: {date: 日收益}}``。

    只使用**相邻有效收盘价**：中间出现无效行（close 缺失或 <= 0）不会中断链，
    下一条有效记录相对**上一条有效收盘价**计算收益——停牌复牌日的跳空因此
    落在复牌日，而不是被静默丢弃。
    """
    out = {}
    for code, bars in (bars_by_code or {}).items():
        prev = None
        seq = {}
        for b in bars or []:
            d = b.get('date')
            if d is None:
                continue
            try:
                c = float(b.get('close'))
            except (TypeError, ValueError):
                continue
            if c <= 0:
                continue
            d = str(d)
            if prev is not None:
                seq[d] = c / prev - 1
            prev = c
        out[str(code)] = seq
    return out


def equal_weight_returns(bars_by_code, universe_snapshots, dates=None, min_members=2):
    """等权全市场基准的日收益序列（**日频再平衡**，不含交易成本）。

    口径（引用时必须随结论声明）：

    * **成分**：以 ``universe_snapshots[date]`` 的 PIT 成员为准（含退市股、
      含 ST），不使用"今天的股票池"回填历史。
    * **停牌处理**：PIT 成员当日无行情时按**收益 0** 计入（等价于指数法中的
      "按最后收盘价持有"），而不是剔出分母——剔除会系统性高估基准。
    * **分母**：只统计 ``bars_by_code`` **实际覆盖**的成员。数据未覆盖的成员
      既不计收益也不计入分母，否则覆盖缺口会被误读成"全市场不涨"。
    * **再平衡**：每日等权再平衡。这是**零成本、无换手约束**的理论构造，
      真实可实现收益低于该序列，**不得当作可交易基准**。

    ``dates=None`` 时取全部个股行情日期的并集；``min_members`` 为最小成员数，
    不足则跳过该日（返回的字典中不出现该日期，而不是补 0）。
    """
    ret = daily_returns_by_code(bars_by_code)
    covered = set(ret)
    if dates is None:
        dates = sorted({d for seq in ret.values() for d in seq})
    out = {}
    for d in dates:
        d = str(d)
        members = (universe_snapshots or {}).get(d)
        if not members:
            continue
        total = 0.0
        n = 0
        for code in members:
            code = str(code)
            if code not in covered:
                continue
            n += 1
            r = ret[code].get(d)
            if r is not None:
                total += r
        if n >= min_members:
            out[d] = total / n
    return out


def equal_weight_diagnostics(bars_by_code, universe_snapshots, dates=None):
    """等权基准的构成诊断：成员数区间与 PIT 覆盖度。

    ``universe_coverage`` = 各日 ``实际覆盖成员数 / PIT 成员数`` 的均值。
    该值显著小于 1 时，等权基准只是 PIT 池的一个**子集**，
    该限定条件必须写入结论。
    """
    ret = daily_returns_by_code(bars_by_code)
    covered = set(ret)
    if dates is None:
        dates = sorted({d for seq in ret.values() for d in seq})
    counts, ratios = [], []
    for d in dates:
        d = str(d)
        members = (universe_snapshots or {}).get(d)
        if not members:
            continue
        n = sum(1 for c in members if str(c) in covered)
        counts.append(n)
        ratios.append(n / len(members))
    if not counts:
        return {'dates': 0, 'members_min': None, 'members_max': None,
                'members_mean': None, 'universe_coverage': None}
    return {
        'dates': len(counts),
        'members_min': min(counts),
        'members_max': max(counts),
        'members_mean': round(statistics.mean(counts), 2),
        'universe_coverage': round(statistics.mean(ratios), 4),
    }
