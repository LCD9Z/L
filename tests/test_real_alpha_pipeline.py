# -*- coding: utf-8 -*-
import csv,json,hashlib
from pathlib import Path
from real_alpha_pipeline import load_certified_csv, run_real_alpha_pipeline

def _make(path, code, n=300, base=10):
    rows=[]
    for i in range(n):
        # ISO-like monotonic synthetic dates; sufficient for loader test only.
        d=f"2024-{(i//28)+1:02d}-{(i%28)+1:02d}" if i<336 else f"2025-01-{(i-336)%28+1:02d}"
        px=base+i*0.01
        rows.append({"date":d,"open":px,"close":px*1.001,"high":px*1.01,"low":px*.99,"volume":2e8,"amount":2e9})
    with open(path,"w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=rows[0].keys());w.writeheader();w.writerows(rows)
    h=hashlib.sha256(Path(path).read_bytes()).hexdigest()
    meta={"strict":True,"sha256":h,"rows":len(rows)}
    Path(path).with_suffix(".metadata.json").write_text(json.dumps(meta),encoding="utf-8")

def test_certified_loader_rejects_tamper(tmp_path):
    p=tmp_path/"x.csv";_make(p,"x",20)
    assert len(load_certified_csv(p))==20
    with open(p,"a",encoding="utf-8") as f:f.write("\\n")
    try: load_certified_csv(p)
    except ValueError as e: assert "sha256" in str(e)
    else: assert False

def test_pipeline_requires_enough_oos(tmp_path):
    s=tmp_path/"s.csv";b=tmp_path/"b.csv";_make(s,"s",100);_make(b,"b",100,3000)
    r=run_real_alpha_pipeline({"600000":str(s)},str(b),"2024-02-01",min_periods=252)
    assert r["verdict"]=="INCONCLUSIVE"


# ---------------------------------------------------------------------------
# 守卫：加载器必须透传「打分路径依赖的字段」
#
# 2026-09-26 实测缺陷：`load_certified_csv` 的字段白名单漏掉了 `turnover`，
# 而 `walk_forward.score_history` 的换手率分项（−5 ~ +10）依赖它 ——
# 结果该分项**静默失效**（恒为 0）：
#   阈值 70 的过线率实测只有 6.65%，恢复字段后为 18.71%（近 3 倍）。
# 即策略长期在**远窄于设计意图**的候选池里选股。
#
# 这类缺陷的要害是**不报错**：CSV 有值、打分函数有逻辑、中间少了一环，
# 一切看起来正常。故用断言把「加载器字段集合」与「打分依赖集合」绑起来。
# ---------------------------------------------------------------------------

# score_history / 回测路径实际读取的字段
SCORING_REQUIRED_FIELDS = {
    "date", "open", "high", "low", "close", "volume", "amount",
    "turnover",          # 换手率分项（−5 ~ +10）—— 曾因漏透传而静默失效
    "is_st",             # 涨跌停幅度派生（主板 ST 为 5%）
    "limit_ratio",       # 涨跌停判定
}


def _write_strict_dataset(tmp_path, turnover_value="2.5"):
    """造一份最小但通过 strict 校验的数据集（含 metadata.sha256）。"""
    import csv as _csv
    import hashlib
    import json as _json

    p = tmp_path / "000001.csv"
    with p.open("w", encoding="utf-8", newline="\n") as fh:
        w = _csv.writer(fh)
        w.writerow(["date", "open", "high", "low", "close", "volume", "amount",
                    "turnover", "is_st", "st_basis", "source", "name",
                    "limit_ratio", "limit_basis"])
        for i in range(5):
            w.writerow([f"2024-01-0{i + 1}", "10", "11", "9", "10.5", "1000",
                        "1000000", turnover_value, "0", "", "t", "测试", "0.1", ""])
    mp = tmp_path / "000001.metadata.json"
    mp.write_text(_json.dumps({
        "strict": True,
        "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
        "rows": 5, "code": "000001",
    }), encoding="utf-8")
    return p, mp


def test_loader_passes_through_all_scoring_fields(tmp_path):
    """⚠️ 核心守卫：打分路径需要的字段一个都不能少。"""
    p, mp = _write_strict_dataset(tmp_path)
    bars = load_certified_csv(p, mp)
    missing = SCORING_REQUIRED_FIELDS - set(bars[0].keys())
    assert missing == set(), (
        f"加载器丢弃了打分路径依赖的字段: {sorted(missing)} —— "
        "这些字段缺失不会报错，只会让对应分项静默失效"
    )


def test_loader_carries_turnover_value(tmp_path):
    """turnover 不仅要在键里，值也要正确透传（曾因漏字段而恒为 None）。"""
    p, mp = _write_strict_dataset(tmp_path, turnover_value="2.5")
    bars = load_certified_csv(p, mp)
    assert bars[0]["turnover"] == "2.5"


def test_score_history_uses_turnover_when_present():
    """带 turnover 时打分应与不带时不同 —— 证明该分项真的生效。"""
    from walk_forward import score_history

    def mk(turn):
        out = []
        for i in range(40):
            bar = {"date": f"2024-01-{i + 1:02d}", "open": 10.0, "high": 11.0,
                   "low": 9.5, "close": 10.0 + i * 0.02, "volume": 1000.0,
                   "amount": 1e6}
            if turn is not None:
                bar["turnover"] = turn
            out.append(bar)
        return out

    s_with = score_history(mk(3.0))["score"]
    s_without = score_history(mk(None))["score"]
    assert s_with != s_without, "turnover 分项未生效（曾被静默禁用）"
