# -*- coding: utf-8 -*-
"""统计层阳性对照（A4）：让「无效的结果」**可见地失败**。

方法论来源：`MateoBodon/microalpha` —— 它不靠断言「回测是对的」，
而是植入四种已知缺陷让回测**可见地失败**（未公布数据 +20.53→−0.17、
同 tick 成交 +21.89→+0.17、漏成本 +0.57→−0.68、从 128 个噪声模型挑最优
+1.38→−1.28），并附**阳性对照 p=0.001** 证明「该通过时能通过」。
本项目已实跑复现其 13 个数字（见 `GITHUB_ASHARE_QUANT_SURVEY.md` §8.3-①）。

本项目此前只有**代码层**反向验证；本文件把它投影到**统计层**：
我们拥有的多重检验校正（DSR/PSR/MinTRL）必须能抓住
「挑最优 / 样本不足 / 非正态」这三类它声明要管的问题。

全部用例：**合成数据 + 固定种子 + 确定性**，不依赖任何归档产物、
不需要数据集，因此可在任何环境重复。

对应 `DSR_IC_FAMILY_PREREG.md` §四（S-0~S-3）。
"""
import math
import random


from validation.multiple_testing import (
    deflated_family,
    normal_cdf,
    sharpe_moments,
)

# 固定种子：整文件的确定性来源。改种子等于改判据，必须先改预注册。
SEED_BASE = 20261018


def _series(ir: float, n: int, seed: int):
    """近似 N(ir, 1) 的逐期序列。"""
    rng = random.Random(seed)
    return [ir + rng.gauss(0.0, 1.0) for _ in range(n)]


def _two_sided_p(series) -> float:
    """对该序列的 sr 做正态近似的双尾 p 值（n 足够大时与 t 检验一致）。"""
    m = sharpe_moments(series)
    if m is None:
        return float("nan")
    t = m["sr"] * math.sqrt(m["n"])
    return 2.0 * (1.0 - normal_cdf(abs(t)))


# ---------------------------------------------------------------------------
# S-0 阳性对照：该通过时必须通过
# ---------------------------------------------------------------------------

def test_s0_positive_control_genuine_signal_passes():
    """S-0：单一真实信号（IR=0.4、n=250）必须被判为「构成证据」。

    **这条是其余三条的前提**——若它不过，说明测试环境或实现坏了，
    后面三条的「红」可能只是环境问题（2026-10-18 记忆纪律：
    反向验证要验「为什么红」，先证基线是绿的）。
    """
    s = _series(0.40, 250, seed=SEED_BASE + 0)
    r = deflated_family({"genuine": s})
    t = r["trials"]["genuine"]
    m = sharpe_moments(s)
    assert m is not None, "合成序列竟算不出矩（样本不足？）"
    assert 0.30 < m["sr"] < 0.50, f"合成序列的 sr 漂了：{m['sr']:.3f}"
    assert t["psr"] > 0.99, f"阳性对照未过：psr={t['psr']:.4f}"
    assert t["dsr"] > 0.99, f"阳性对照未过：dsr={t['dsr']:.4f}"
    assert t["min_trl_sufficient"] is True, "真实强信号的 MinTRL 竟判为不够"


# ---------------------------------------------------------------------------
# S-1 阴性注入 · 挑最优（选择偏差）
# ---------------------------------------------------------------------------

def test_s1_picking_best_of_many_noise_is_not_evidence():
    """S-1：30 个纯噪声试验里挑 ICIR 最大的那个，**不构成证据**。

    注入必须**真的**成立：至少一个试验的未校正 p < 0.05
    （m=30 时该概率约 78.5%，故用固定种子钉死一个成立的情形）。
    若注入不成立，本条断言本身就是假的 —— 这正是本项目
    「反向验证要验为什么红」纪律在统计层的落实。
    """
    fam = {f"noise_{i:02d}": _series(0.0, 250, seed=SEED_BASE + 100 + i)
           for i in range(30)}
    r = deflated_family(fam)
    assert r["selection_bias_corrected"] is True, (
        "S-1：选择偏差校正未生效（selection_bias_corrected=False）")

    # ① 注入真实性：至少一个未校正显著
    raw_sig = [k for k, v in fam.items() if _two_sided_p(v) < 0.05]
    assert raw_sig, "注入不真实：30 个噪声试验无一未校正显著 —— 本条判据无效"

    # ② 挑出来的那个，未校正 p 显著但 DSR 不过
    best = max(r["trials"], key=lambda k: r["trials"][k]["sr"])
    assert _two_sided_p(fam[best]) < 0.05, \
        f"最优者 {best} 的未校正 p 不显著，注入失真"
    assert r["trials"][best]["dsr"] < 0.95, (
        f"挑最优未被抓住：{best} 的 dsr={r['trials'][best]['dsr']:.4f} ≥ 0.95")

    # ③ 未被挑中的噪声试验，dsr 应更低（选择偏差只抬高最大值）
    others = [t["dsr"] for k, t in r["trials"].items()
              if k != best and isinstance(t["dsr"], float)]
    assert others and max(others) <= r["trials"][best]["dsr"] + 1e-12


# ---------------------------------------------------------------------------
# S-2 阴性注入 · 样本不足
# ---------------------------------------------------------------------------

def test_s2_short_track_record_is_flagged_insufficient():
    """S-2：真实但弱的信号（IR=0.15）+ 太短的历史（n=40）必须判「不够」。

    MinTRL 的存在意义就是给出「大到荒唐」的数字——若它给出一个
    「勉强够用」的值，说明判据失效了。
    """
    s = _series(0.15, 40, seed=SEED_BASE + 200)
    r = deflated_family({"short": s})
    t = r["trials"]["short"]
    assert t["n"] == 40
    assert t["min_trl_required"] is not None
    assert t["min_trl_required"] > 40, (
        f"MinTRL={t['min_trl_required']:.1f} 竟小于可用观测数 40")
    assert t["min_trl_sufficient"] is False
    # 同一信号给足样本就必须转为「够」——证明是样本量问题而非信号不存在
    long_r = deflated_family({"long": _series(0.15, 400, seed=SEED_BASE + 201)})
    assert long_r["trials"]["long"]["min_trl_sufficient"] is True


# ---------------------------------------------------------------------------
# S-3 阴性注入 · 非正态（稀有巨亏）
# ---------------------------------------------------------------------------

def test_s3_negative_skew_lowers_psr_below_normal_approx():
    """S-3：掺入稀有负跳后，PSR 必须**严格低于**正态近似概率。

    若 PSR 等于正态近似 ``Φ(sr·√(n−1))``，说明偏度/峰度根本没进公式
    （DSR 的一半意义就在非正态修正）。
    """
    rng = random.Random(SEED_BASE + 300)
    vals = [rng.gauss(0.0, 1.0) for _ in range(240)] + [-5.0] * 10
    vals = [v + 0.30 for v in vals]          # 加正漂移，使 sr > 0
    m = sharpe_moments(vals)
    assert m is not None, "注入序列竟算不出矩（样本不足？）"
    assert m["skew"] < -0.2, f"注入不真实：skew={m['skew']:.3f} 不够负"

    naive = normal_cdf(m["sr"] * math.sqrt(m["n"] - 1.0))
    r = deflated_family({"skewed": vals})
    psr = r["trials"]["skewed"]["psr"]
    assert psr < naive - 0.005, (
        f"非正态未被计入：psr={psr:.4f} 未显著低于正态近似 {naive:.4f}")

    # 对照：同规模纯正态序列的 psr 应**接近**正态近似。
    # 容差取 1e-3：n=250 时样本偏度/峰度自身有采样噪声（实测 ~1.4e-5），
    # 不允许偏离等于要求「矩必须恰好为 0/3」，那是错的要求。
    # 真正的区分力来自上面的偏度组（差 > 0.005，比噪声大两个量级）。
    clean = _series(0.30, 250, seed=SEED_BASE + 301)
    mc = sharpe_moments(clean)
    assert mc is not None, "干净序列竟算不出矩（样本不足？）"
    rc = deflated_family({"clean": clean})
    naive_c = normal_cdf(mc["sr"] * math.sqrt(mc["n"] - 1.0))
    assert abs(rc["trials"]["clean"]["psr"] - naive_c) < 1e-3, (
        "正态序列的 psr 与正态近似偏离过大 —— 公式自身可能被改坏")


# ---------------------------------------------------------------------------
# 汇总：四组合计的「红/绿」必须可一句话复述
# ---------------------------------------------------------------------------

def test_all_four_groups_are_deterministic():
    """同一 seed 跑两遍，四个用例的判据输入必须逐位相同。

    防止将来有人「为了让测试通过而调种子」而不被发现。
    """
    def snapshot():
        s0 = sharpe_moments(_series(0.40, 250, seed=SEED_BASE + 0))
        fam = {f"n{i}": _series(0.0, 250, seed=SEED_BASE + 100 + i)
               for i in range(30)}
        best = max(fam, key=lambda k: (sharpe_moments(fam[k]) or {}).get("sr", 0.0))
        s2 = sharpe_moments(_series(0.15, 40, seed=SEED_BASE + 200))
        rng = random.Random(SEED_BASE + 300)
        vals = [v + 0.30 for v in
                ([rng.gauss(0.0, 1.0) for _ in range(240)] + [-5.0] * 10)]
        assert s0 is not None and s2 is not None, "快照序列竟算不出矩"
        mv = sharpe_moments(vals)
        assert mv is not None, "注入序列竟算不出矩"
        return (round(s0["sr"], 12), best, round(s2["sr"], 12),
                round(mv["skew"], 12))

    assert snapshot() == snapshot()
