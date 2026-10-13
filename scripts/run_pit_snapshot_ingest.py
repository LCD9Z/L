# -*- coding: utf-8 -*-
"""PIT 快照采集：L1 上市/退市日（baostock）+ L2 申万行业变迁史（申万官网 xls）。

对应 ``PIT_SNAPSHOT_DESIGN.md`` 的 **P0**（L1）与 **P1**（L2）。

用法::

    python scripts/run_pit_snapshot_ingest.py --dataset l1_stock_basic --reconcile D:/tdx_dataset_v3
    python scripts/run_pit_snapshot_ingest.py --dataset l2_sw_industry --reconcile D:/tdx_dataset_v3
    python scripts/run_pit_snapshot_ingest.py --all

设计纪律（照 ``PIT_SNAPSHOT_DESIGN.md``）：

* **只追加** —— 已落盘日期不覆盖（``--force`` 需留痕）
* **失败即报** —— 自检不过 → 非零退出码，**不得静默通过**
* **阈值事前固定** —— 见 :data:`SELF_CHECK`
* **原始层保留原字节** —— 二进制源（xls）不转 JSONL，否则日后无法用官方文件复核

> ⚠️ 可选依赖（**惰性导入**，与本项目 pytdx/akshare 同约定）：
> ``baostock``（L1）· ``xlrd``（L2，仅支持 .xls，正好是申万给的格式）。
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import socket
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pit.baostock_guard import assert_not_truncated, suspect_truncation  # noqa: E402
from pit.pit_snapshot_store import (  # noqa: E402
    DATASET_REGISTRY,
    OverwriteRefusedError,
    PitSnapshotStore,
    dataset_meta,
    make_run_id,
    now_cst,
    sha256_of_file,
)

# --- 源定义 ---
L1_DATASET = "l1_stock_basic"
L2_DATASET = "l2_sw_industry"
L3_DATASET = "l3_valuation"

SW_URL = "https://www.swsresearch.com/swindex/pdf/SwClass2021/StockClassifyUse_stock.xls"
SW_UA = "Mozilla/5.0 (compatible; ai-stock-god-pit/1.0)"

#: 自检阈值 —— **事前固定**，不得依据结果调整。
SELF_CHECK: Dict[str, Dict[str, float]] = {
    L1_DATASET: {
        "min_rows": 4000.0,        # 股票总数下限（实测 5561）
        "max_missing_rate": 0.01,  # 关键字段缺失率上限
        "max_delist_share": 0.15,  # 退市占比上限（实测 337/5561 ≈ 6.1%）
    },
    L2_DATASET: {
        "min_rows": 10000.0,       # 记录数下限（实测 12925）
        "min_stocks": 5000.0,      # 覆盖股票数下限（实测 5930）
        "max_missing_rate": 0.01,
    },
    L3_DATASET: {
        # 行数取决于 `--universe` 与 `--limit`，故下限只用于拦「整体抓取失败」。
        "min_rows": 1000.0,
        # `close` 是估值比率的分母：缺了该行无意义（实测 baostock 停牌日仍给 close）。
        "max_missing_rate": 0.02,
    },
}


# ===========================================================================
# L1 · baostock 上市日/退市日
# ===========================================================================
def _fetch_l1() -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """返回 (规范化前的记录, 原始行)。"""
    try:
        import baostock as bs  # 惰性导入：可选依赖
    except ImportError as exc:  # pragma: no cover - 环境相关
        raise RuntimeError("未安装 baostock（可选依赖）。安装: pip install baostock") from exc

    lg = bs.login()
    if lg.error_code != "0":
        raise RuntimeError(f"baostock 登录失败: {lg.error_code} {lg.error_msg}")
    try:
        rs = bs.query_stock_basic()
        if rs.error_code != "0":
            raise RuntimeError(f"baostock 查询失败: {rs.error_code} {rs.error_msg}")
        api_rows: List[Dict[str, Any]] = []
        while rs.next():
            api_rows.append(dict(zip(rs.fields, rs.get_row_data(), strict=False)))
    finally:
        bs.logout()

    # ⚠️ 防 baostock 客户端**分页静默截断**：某页恰好 2000 行时客户端会去取下一页，
    # 若该请求失败则 `next()` 直接返回 False 且不抛异常 → 调用方看到「干净地结束在 2000 行」。
    # 宁可失败，也不可把残缺快照写进 raw/ 与 normalized/。详见 `pit/baostock_guard.py`。
    assert_not_truncated(len(api_rows), "baostock query_stock_basic()")

    return _split_l1(api_rows)


def _split_l1(
    api_rows: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """把 baostock 全量结果拆成 ``(股票记录, 未过滤原始行)``。

    ⚠️ **返回的原始行必须是「未过滤全量」**，不得只返回 ``type == "1"`` 的子集。

    ``raw/`` 层的用途是**日后复核「过滤本身是否正确」**（例如某年是否漏判了
    指数/可转债的 ``type``、板块代码是否变化）。若 raw 存的是过滤后数据，
    raw 就退化成 ``normalized/`` 的副本，复核能力归零。

    2026-10-11 的 L1 raw 曾由旧版脚本写入**过滤后**数据
    （磁盘 5,561 行 vs 全量 8,992 行）—— 本函数 + ``tests/test_pit_snapshot_scripts.py``
    的守卫防止其复发。**纯函数、无 I/O**，故守卫测试不依赖网络。
    """
    recs: List[Dict[str, Any]] = []
    for r in api_rows:
        if str(r.get("type", "")).strip() != "1":
            continue  # 2=指数 · 4=可转债 · 5=ETF —— 不剔除会让退市统计混入指数
        code6 = str(r.get("code", "")).strip().split(".")[-1]
        recs.append(
            {
                "code": code6,
                "code_name": str(r.get("code_name", "")).strip(),
                "ipo_date": str(r.get("ipoDate", "")).strip(),
                "out_date": str(r.get("outDate", "")).strip(),
                "status": str(r.get("status", "")).strip(),
            }
        )
    return recs, list(api_rows)


def _normalize_l1(recs: List[Dict[str, Any]], run_id: str, as_of: str) -> List[Dict[str, str]]:
    """``effective_date`` 取上市日（该股事实起点）。"""
    return [
        {
            "code": r["code"],
            "code_name": r["code_name"],
            "ipo_date": r["ipo_date"],
            "out_date": r["out_date"],
            "status": r["status"],
            "is_delisted": "1" if r["out_date"] else "0",
            "effective_date": r["ipo_date"],
            "as_of": as_of,
            "ingest_run_id": run_id,
        }
        for r in recs
    ]


def _reconcile_l1(store: PitSnapshotStore, dataset_dir: str, ingest_date: str) -> Dict[str, Any]:
    """与本地数据集交叉核对：本地缺了哪些**已退市**股票（= 幸存者偏差量化）。

    ⚠️ 关键：必须按**退市类型**拆开报 —— A 股「退市」有两类，经济含义完全不同：
    真实退市/退市整理（价值大幅损失）vs 吸收合并/重组（换股，价值延续）。
    只报「缺 N 只」会**严重高估**幸存者偏差。
    """
    stocks_dir = os.path.join(dataset_dir, "stocks")
    if not os.path.isdir(stocks_dir):
        return {"error": f"目录不存在: {stocks_dir}"}

    local = {f[:-4] for f in os.listdir(stocks_dir) if f.endswith(".csv") and f[:-4].isdigit()}
    rows = store.records_as_of(L1_DATASET, ingest_date)
    all_codes = {r["code"] for r in rows}
    delisted = {r["code"] for r in rows if r["is_delisted"] == "1"}
    listed = all_codes - delisted

    out_date = {r["code"]: r["out_date"] for r in rows}
    name = {r["code"]: r["code_name"] for r in rows}
    missing = sorted(delisted - local)

    # 启发式：名称含「退」= 真实退市/退市整理；否则多为吸收合并/重组/更名
    def _is_true_delist(c: str) -> bool:
        return "退" in name.get(c, "")

    missing_true = [c for c in missing if _is_true_delist(c)]
    missing_merge = [c for c in missing if not _is_true_delist(c)]

    by_year: Dict[str, int] = {}
    for c in missing:
        y = out_date.get(c, "")[:4]
        by_year[y] = by_year.get(y, 0) + 1

    # 退市潮年份（2020-2024）单独报 —— 这是「近年结论是否受影响」的直接答案
    wave = [c for c in delisted if "2020" <= out_date.get(c, "")[:4] <= "2024"]
    wave_cov = [c for c in wave if c in local]

    return {
        "dataset_dir": dataset_dir,
        "local_total": len(local),
        "src_total": len(all_codes),
        "src_listed": len(listed),
        "src_delisted": len(delisted),
        "local_covers_delisted": len(delisted & local),
        "local_missing_delisted": len(missing),
        "delisted_coverage_pct": round(len(delisted & local) / len(delisted) * 100, 2) if delisted else None,
        "local_only_not_in_src": len(local - all_codes),
        "missing_by_year": dict(sorted(by_year.items())),
        "missing_true_delist": len(missing_true),
        "missing_true_delist_codes": sorted(missing_true),
        "missing_merge_or_restructure": len(missing_merge),
        "wave_2020_2024_src": len(wave),
        "wave_2020_2024_covered": len(wave_cov),
        "wave_2020_2024_coverage_pct": round(len(wave_cov) / len(wave) * 100, 2) if wave else None,
    }


# ===========================================================================
# L2 · 申万行业变迁史
# ===========================================================================
def _download_sw(url: str = SW_URL) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": SW_UA})
    with urllib.request.urlopen(req, timeout=120) as resp:  # noqa: S310 - 官方 https 端点
        return resp.read()


def _parse_sw_xls(data: bytes) -> List[Dict[str, str]]:
    """解析申万 xls。日期是 Excel 序列号（XL_CELL_DATE），**必须转换**，否则得到 33331 这类浮点。"""
    import xlrd  # 惰性导入：可选依赖

    book = xlrd.open_workbook(file_contents=data)
    sh = book.sheet_by_index(0)
    header = [str(sh.cell_value(0, c)).strip() for c in range(sh.ncols)]
    need = {"股票代码", "计入日期", "行业代码", "更新日期"}
    missing = need - set(header)
    if missing:
        raise RuntimeError(f"申万表结构变了，缺列 {sorted(missing)}；实际列={header}")
    idx = {name: header.index(name) for name in need}

    def _cell(r: int, c: int) -> str:
        t = sh.cell_type(r, c)
        v = sh.cell_value(r, c)
        if t == xlrd.XL_CELL_DATE:  # 3
            return xlrd.xldate_as_datetime(v, book.datemode).strftime("%Y-%m-%d %H:%M:%S")
        if t == xlrd.XL_CELL_NUMBER:
            return str(int(v)) if float(v).is_integer() else str(v)
        return str(v).strip()

    return [{k: _cell(r, c) for k, c in idx.items()} for r in range(1, sh.nrows)]


def _normalize_l2(recs: List[Dict[str, str]], run_id: str, as_of: str) -> List[Dict[str, str]]:
    """``effective_date`` 取「计入日期」**截断到日**（原值带时间，日频口径无需时分秒）。

    行业代码为 6 位层级码（2 位一级 + 2 位二级 + 2 位三级），
    按申万约定派生 ``industry_l1`` / ``industry_l2``（**仅代码，无中文名** ——
    申万官方只发布代码，名称表未公开发布）。
    """
    rows: List[Dict[str, str]] = []
    for r in recs:
        code = str(r["股票代码"]).strip().zfill(6)
        ind = str(r["行业代码"]).strip()
        eff_raw = str(r["计入日期"]).strip()
        rows.append(
            {
                "code": code,
                "industry_code": ind,
                "industry_l1": ind[:2] + "0000" if len(ind) >= 2 else "",
                "industry_l2": ind[:4] + "00" if len(ind) >= 4 else "",
                "update_ts": str(r["更新日期"]).strip(),
                "effective_date": eff_raw[:10],
                "as_of": as_of,
                "ingest_run_id": run_id,
            }
        )
    return rows


def _reconcile_l2(store: PitSnapshotStore, dataset_dir: str, ingest_date: str) -> Dict[str, Any]:
    """L2 对账：覆盖率 + **PIT 完整性**（任一日每股恰一个行业）。"""
    rows = store.records_as_of(L2_DATASET, ingest_date)
    codes = {r["code"] for r in rows}
    res: Dict[str, Any] = {
        "n_rows": len(rows),
        "n_stocks": len(codes),
        "n_industry_codes": len({r["industry_code"] for r in rows}),
        "n_l1_codes": len({r["industry_l1"] for r in rows}),
        "effective_date_min": min((r["effective_date"] for r in rows), default=""),
        "effective_date_max": max((r["effective_date"] for r in rows), default=""),
    }

    stocks_dir = os.path.join(dataset_dir, "stocks")
    if os.path.isdir(stocks_dir):
        local = {f[:-4] for f in os.listdir(stocks_dir) if f.endswith(".csv") and f[:-4].isdigit()}
        res["local_total"] = len(local)
        res["local_covered"] = len(local & codes)
        res["local_coverage_pct"] = round(len(local & codes) / len(local) * 100, 2) if local else None
        res["local_not_in_src_sample"] = sorted(local - codes)[:10]
        res["src_not_in_local"] = len(codes - local)

    # PIT 完整性：抽查若干日期，看「该日有多少股票**已有**行业归属」
    #
    # ⚠️ 首版这里统计的是「记录数 > 1 的股票数」，**指标是错的** ——
    # 一股多行（历次行业调整）是本数据的**正常结构**，不是缺陷。
    # 真正有意义的检查是：某日有多少股票**尚无**任何 ≤ 该日的归属记录
    # （= 当时还没上市 / 还没被分类），以及该日是否有股票**缺失**归属。
    probes = ["2010-01-04", "2015-01-05", "2020-01-02", "2024-01-02", "2026-09-01"]
    total = len(codes)
    pit: Dict[str, Any] = {}
    for d in probes:
        assigned = {r["code"] for r in rows if r["effective_date"] <= d}
        pit[d] = {
            "assigned": len(assigned),
            "not_yet_assigned": total - len(assigned),
            "assigned_pct": round(len(assigned) / total * 100, 2) if total else None,
        }
    res["pit_probe"] = pit
    return res


# ===========================================================================
# L3 · baostock 日频估值历史（**不复权**）
# ===========================================================================
L3_FIELDS = "date,code,close,peTTM,pbMRQ,psTTM,pcfNcfTTM,turn,tradestatus,isST"

#: 单只标的抓取的重试参数。**瞬时网络错误必会命中** —— 2026-10-12 的全市场回填中，
#: 一只 sz.001206 的 ``10002007 网络接收错误`` 直接终止了整轮 6 小时任务，
#: 前 31 分钟抓到的 456 只全部锁死在 raw 里、到不了规范化步骤。
#: 重试是**幂等只读**查询，无副作用；退避 2/5/10 秒，重试前重新登录
#: （WinError 10054 之后会话可能已死）。
_L3_FETCH_ATTEMPTS: int = 3
_L3_FETCH_BACKOFF: Tuple[float, ...] = (2.0, 5.0, 10.0)

#: baostock socket 默认超时（秒）。**挂起不抛异常，重试拦不住** ——
#: 2026-10-13 实测：回填进程对 baostock（114.94.20.42:10030）的连接
#: Established 但服务端无响应，进程卡死 2 小时（CPU 6%），既无 error_code
#: 也无异常 → 重试逻辑完全绕过，只能人工杀进程。
#: 设默认超时后，挂起会抛 ``socket.timeout`` → 落入
#: :func:`_query_with_retry` 的既有「异常折算一次失败」通道 → 重试/重登/跳过。
#: 120s 对 2,533 行的正常查询（实测数秒）留足余量。
_L3_SOCKET_TIMEOUT_S: float = 120.0

#: 6 位代码 → baostock 市场前缀。**不认识的号段直接抛错，不猜**
#: （猜错会静默取到别的标的 —— 与本项目反复出现的「对象标识」问题同类）。
#:
#: ⚠️ 2026-10-13 实测（baostock 0.9.3 · query_history_k_data_plus）：
#: 该端点**只接受 sh./sz. 前缀** —— ``bj.830799`` / ``bj.920000`` 均报
#: ``10004011 股票代码未标识sh或sz``；北交所号段（4xx/8xx/920xxx）以 sh./sz.
#: 前缀查询均为 ``error_code=0`` 的**空响应**（源无该段数据）。
#: → 北交所代码**不可猜前缀**：4/8 段显式抛错（由 ``_fetch_l3`` 记入零数据清单）；
#:   920 段走 sh. 前缀（合法符号）收空响应，同样记零数据 —— 两者都不静默。
_PREFIX_BY_FIRST = {"6": "sh", "5": "sh", "9": "sh",
                    "0": "sz", "2": "sz", "3": "sz"}
#: 北交所号段（源不覆盖，显式拒绝而非猜前缀）
_BJ_SEGMENTS = ("4", "8")


def bs_symbol(code: str) -> str:
    """``600519`` → ``sh.600519``。未知/北交所号段抛错。

    北交所 4xx/8xx 显式抛错的原因见 ``_PREFIX_BY_FIRST`` 注释：baostock 本端点
    拒绝 ``bj.`` 前缀（10004011），猜 sh./sz. 前缀只会得到空响应 —— 抛错让
    调用方把它记入**零数据清单**（显式）而非混入抓取失败（每次 resume 重试）。
    """
    c = str(code).zfill(6)
    if c[0] in _BJ_SEGMENTS:
        raise ValueError(
            f"北交所号段 {code!r}：baostock query_history_k_data_plus 无覆盖"
            "（bj. 前缀实测拒绝 10004011；sh./sz. 前缀为 success 空响应）—— 记入零数据清单，不猜前缀"
        )
    pref = _PREFIX_BY_FIRST.get(c[0])
    if pref is None:
        raise ValueError(f"未知号段，无法确定市场前缀: {code!r}")
    return f"{pref}.{c}"


def _universe_codes(dataset_dir: str, limit: int = 0) -> List[str]:
    """从本地数据集目录取股票代码（6 位，升序）。"""
    d = Path(dataset_dir) / "stocks"
    if not d.is_dir():
        raise RuntimeError(f"数据集目录不存在: {d}")
    codes = sorted(p.stem for p in d.glob("*.csv") if p.stem.isdigit())
    return codes[:limit] if limit > 0 else codes


# ===========================================================================
# L3 · 零数据代码边车清单（2026-10-13 收官审计引入）
# ===========================================================================
def zero_data_sidecar_path(meta_dir: Path, ingest_date: str) -> Path:
    """零数据代码边车清单路径：``meta/l3_zero_data_codes_<ingest_date>.txt``。

    **语义**：清单内的代码 = **已由人工核实的「查询成功但 0 行」**代码
    （baostock success 空响应，如北交所 920 段源不覆盖），**不是失败**
    （失败在 ``metrics.failed_codes``，两回事，绝不混淆）。
    """
    return meta_dir / f"l3_zero_data_codes_{ingest_date}.txt"


def read_zero_data_codes(path: Path) -> set:
    """读边车清单（``#`` 注释行与空行跳过）。文件不存在 ⇒ 空集。"""
    if not path.exists():
        return set()
    out: set = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            out.add(line)
    return out


def filter_resume_codes(
    codes: List[str], done: set, zero_known: set
) -> tuple[List[str], List[str]]:
    """``--resume`` 代码筛选（**纯函数**）：保留未采且未记零数据的，
    返回 ``(待采, 被边车排除的零数据代码)``。

    ⚠️ 边车排除**不是静默跳过**：调用方必须显式打印被排除的数量
    （2026-10-13 教训：281 只零数据代码永不落 raw，不排除则每次
    ``--resume`` 都重试它们，且只剩它们时 ``min_rows`` 会假性 FAIL）。
    """
    excluded = [c for c in codes if c in zero_known]
    kept = [c for c in codes if c not in done and c not in zero_known]
    return kept, excluded


def _query_with_retry(query_fn, relogin_fn, attempts: int, backoff: Tuple[float, ...]):
    """对**只读**查询做有限重试。**纯逻辑、无 I/O**，便于不连网单测。

    约定 ``query_fn()`` 返回 ``(ok, payload, err_text)``；``relogin_fn()``
    在两次尝试之间调用（会话可能已死）。query_fn 自身抛异常也按「失败一次」处理
    （网络层异常不会都变成 baostock 的 error_code，WinError 10054 就是先抛后报）。

    全部失败抛 :class:`RuntimeError` —— **由调用方决定跳过哪一只标的**，
    不让一只标的的失败杀死整轮回填。
    """
    last = ""
    for i in range(attempts):
        try:
            ok, payload, err = query_fn()
        except Exception as exc:  # noqa: BLE001 - 网络层异常一律折算成一次失败
            ok, payload, err = False, None, f"{type(exc).__name__}: {exc}"
        if ok:
            return payload
        last = err
        if i + 1 < attempts:
            if backoff:
                time.sleep(backoff[min(i, len(backoff) - 1)])
            relogin_fn()
    raise RuntimeError(f"重试 {attempts} 次仍失败: {last}")


def _fetch_one_l3(symbol: str, start: str, end: str) -> List[Dict[str, Any]]:
    """单只标的的日频估值原始行（**调用方须已登录**）。

    ``adjustflag='3'`` = **不复权** —— 与 ``peTTM``/``pbMRQ`` 的口径一致
    （估值比率的分母是**未复权**的收盘价；用复权价会引入系统性偏差）。

    瞬时网络错误**重试**（默认 3 次，退避 2/5/10s，重试前重新登录）；
    持续失败才抛 :class:`RuntimeError`，由 :func:`_fetch_l3` 跳过该只并续跑。
    """
    import baostock as bs  # 惰性导入：可选依赖

    def _query():
        rs = bs.query_history_k_data_plus(
            symbol, L3_FIELDS, start_date=start, end_date=end,
            frequency="d", adjustflag="3",
        )
        if rs.error_code != "0":
            return False, None, f"{rs.error_code} {rs.error_msg}"
        out: List[Dict[str, Any]] = []
        while rs.next():
            out.append(dict(zip(rs.fields, rs.get_row_data(), strict=False)))
        return True, out, ""

    def _relogin() -> None:
        # 重登录失败**不抛** —— 交给下一次 query 的 error_code 呈现，
        # 保持「一次尝试 = 一次 query」的简单语义。
        try:
            bs.logout()
        except Exception:  # noqa: BLE001 - 会话已死时 logout 自身会抛
            pass
        try:
            bs.login()
        except Exception:  # noqa: BLE001 - 登录异常由下一次 query 暴露
            pass

    return _query_with_retry(_query, _relogin, _L3_FETCH_ATTEMPTS, _L3_FETCH_BACKOFF)


def _fetch_l3(codes: List[str], start: str, end: str,
              progress_every: int = 200,
              flush_path: Optional[Path] = None,
              flush_every: int = 100
              ) -> Tuple[List[Dict[str, Any]], int, List[str], List[str], List[str], List[str], List[str]]:
    """批量取日频估值。

    返回 ``(原始行, 原始行数, 疑似截断且重取一致, 重取发现真截断, 抓取失败已跳过,
    查询成功但 0 行, 其中号段不被源接受的 10004011 形态)``。

    ⚠️ **增量落盘（``flush_path``）**：全市场回填需 1~3 小时，若只在**全部完成后**
    才写盘，一次崩溃就**全部白费**，``--resume`` 也无从续起（它读的就是那个文件）。
    → 每 ``flush_every`` 只**追加**一次到 ``flush_path``，使进程可被中断并续跑。

    ⚠️ **单只失败不中止整轮**：重试后仍失败的标的记入返回的 ``failed`` 并**跳过**
    （2026-10-12 实测教训：一只 sz.001206 的瞬时网络错误让 31 分钟的 456 只成果
    全部锁死在 raw 里、整轮到不了规范化步骤）。跳过的标的由 ``--resume`` 续跑补采，
    并在自检里以 WARN 显式呈现（**绝不静默**）。

    ⚠️ **分页截断的处理**：``query_history_k_data_plus`` 的页长 = 2000
    （见 :mod:`pit.baostock_guard`）。**单只标的**行数恰为 2000 整数倍时，
    既可能是「该标的在该窗口恰好这么多天」，也可能是**下一页请求失败的静默截断**。
    → 对该标的**重取一次**：
      * 两次行数**不同** ⇒ 真截断（取较大者，并记入「真截断」清单）
      * 两次**相同**   ⇒ 记为「疑似但稳定」（合法，但须人工确认，在自检里报出）
    """
    import baostock as bs  # 惰性导入：可选依赖

    # 挂起防护必须在**任何网络调用之前**设置（见 _L3_SOCKET_TIMEOUT_S 注释）。
    # 默认超时对进程内后续新建 socket 全局生效；baostock 每次查询新建连接。
    socket.setdefaulttimeout(_L3_SOCKET_TIMEOUT_S)

    lg = bs.login()
    if lg.error_code != "0":
        raise RuntimeError(f"baostock 登录失败: {lg.error_code} {lg.error_msg}")

    raw: List[Dict[str, Any]] = []
    pending: List[Dict[str, Any]] = []          # 待增量落盘的行
    suspect_stable: List[str] = []
    real_truncated: List[str] = []
    failed: List[str] = []
    # 零数据两种形态（P010 评审 Q1.3：**分开记账**）：
    #   empty_response      —— 源接受查询但无数据（sh./sz.920xxx → err=0, 0 行）；
    #   prefix_rejected     —— 源根本不接受该符号格式（bj. 前缀 → 10004011）。
    # 两者混记会把「格式错误」误当成「覆盖差」。两者都记入 zero_data（边车清单
    # 按 code 粒度服务 resume，不分辨形态），但 metrics 分列。
    zero_data: List[str] = []
    zero_data_prefix_rejected: List[str] = []

    def _flush() -> None:
        if flush_path is None or not pending:
            return
        flush_path.parent.mkdir(parents=True, exist_ok=True)
        with flush_path.open("a", encoding="utf-8", newline="\n") as fh:
            for r in pending:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        pending.clear()

    try:
        for i, code in enumerate(codes, 1):
            try:
                sym = bs_symbol(code)
            except ValueError as exc:
                # 号段本端点无覆盖（北交所 4/8 段；baostock 只认 sh./sz. 前缀，
                # bj. 前缀报 10004011「股票代码未标识sh或sz」）→ 记零数据（显式），
                # **不混入 failed**（failed 语义是网络失败，会被 --resume 无限重试）
                zero_data.append(code)
                zero_data_prefix_rejected.append(code)
                print(f"      ⓘ 跳过 {code}（号段不被源接受 10004011 形态，非失败）: {exc}", flush=True)
                continue
            try:
                rows = _fetch_one_l3(sym, start, end)
            except RuntimeError as exc:
                failed.append(f"{code}: {exc}")
                print(f"      !! 跳过 {sym}（重试 {_L3_FETCH_ATTEMPTS} 次仍失败，不影响本轮其余标的）: {exc}",
                      flush=True)
                continue
            if not rows:
                # ⚠️ 成功但 0 行 ≠ 失败：baostock 对源不覆盖的代码（如北交所 920 段）
                # 返回 error_code=0 空响应该。**记账但不当失败** —— 混入 failed 会让
                # 运维反复重试注定为空的代码；不记账则它们永远不进 raw、
                # 每次 --resume 重试、只剩它们时 min_rows 假 FAIL（2026-10-13 实测）。
                zero_data.append(code)
                continue
            if suspect_truncation(len(rows)):
                again = _fetch_one_l3(sym, start, end)
                if len(again) != len(rows):
                    real_truncated.append(f"{code}:{len(rows)}→{len(again)}")
                    rows = again if len(again) > len(rows) else rows
                else:
                    suspect_stable.append(f"{code}:{len(rows)}")
            raw.extend(rows)
            pending.extend(rows)
            if progress_every and i % progress_every == 0:
                print(f"      ... {i}/{len(codes)} 只（累计 {len(raw):,} 行）", flush=True)
            if flush_every and i % flush_every == 0:
                _flush()
        _flush()
    finally:
        _flush()
        bs.logout()
    return raw, len(raw), suspect_stable, real_truncated, failed, zero_data, zero_data_prefix_rejected


def _num_or_blank(v: Any) -> str:
    """原样透传为字符串（空即空）。**不做类型兜底、不插补**。"""
    return str(v).strip() if v is not None else ""


def _normalize_l3(recs: List[Dict[str, Any]], run_id: str, as_of: str) -> List[Dict[str, str]]:
    """``effective_date`` 取交易日（该行事实发生的日期）。"""
    out: List[Dict[str, str]] = []
    for r in recs:
        day = _num_or_blank(r.get("date"))
        if not day:
            continue  # 无日期 → 无法定位 PIT 生效点，**丢弃而非猜**
        sym = _num_or_blank(r.get("code"))
        code = sym.split(".")[-1].zfill(6) if sym else ""
        out.append({
            "code": code,
            "close": _num_or_blank(r.get("close")),
            "pe_ttm": _num_or_blank(r.get("peTTM")),
            "pb_mrq": _num_or_blank(r.get("pbMRQ")),
            "ps_ttm": _num_or_blank(r.get("psTTM")),
            "pcf_ncf_ttm": _num_or_blank(r.get("pcfNcfTTM")),
            "turnover": _num_or_blank(r.get("turn")),
            "trade_status": _num_or_blank(r.get("tradestatus")),
            "is_st": _num_or_blank(r.get("isST")),
            "effective_date": day,
            "as_of": as_of,
            "ingest_run_id": run_id,
        })
    return out


# ===========================================================================
# 层间一致性：原始层 ↔ 规范层（2026-10-12 崩溃事故的后续补丁）
#
# 事故：整轮回填崩在**采集阶段**，raw 落了 456 只、norm 一只未写
# （规范化只在整轮采集结束后才做）。若此后只按 --resume 续跑，
# 这 456 只**永远不会**进入规范层 —— 消费方读 norm 即**静默缺 8% 的股票**。
# → 三个函数把该缺口显式化并可幂等补齐。
# ===========================================================================
def _norm_codes(norm_path: Path) -> set:
    """规范层 CSV 中已出现的 code 集合（**流式**读：全市场约 1,400 万行也不吃内存）。"""
    if not norm_path.exists():
        return set()
    out: set = set()
    with norm_path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.reader(fh)
        next(reader, None)  # 表头
        for row in reader:
            if row:
                out.add(row[0])
    return out


def _layer_gap(store: PitSnapshotStore, source: str, endpoint: str,
               ingest_date: str, dataset: str) -> Dict[str, Any]:
    """原始层 vs 规范层的**代码覆盖差**（双向）。

    * ``in_raw_not_norm``：只在 raw 有（崩溃续跑的后遗症：raw 有、norm 无）；
    * ``in_norm_not_raw``：只在 norm 有（** orphan 残留** —— 「半个 code」失败形态：
      某 code 一半行在旧 norm、一半待补建时，行数可能相等而 code 集合不等）。

    ⚠️ 2026-10-13 主干 P010 评审 Q3.2 建议：补建后须断言**两个方向**的 code 集合
    一致，只查一个方向会漏掉 orphan（P010：『行数相等但 code 集合不等是可能的失败形态』）。
    """
    raw_codes = store.read_raw_keys(source, endpoint, ingest_date)
    norm_codes = _norm_codes(store.norm_path(dataset, ingest_date))
    return {
        "raw_codes": len(raw_codes),
        "norm_codes": len(norm_codes),
        "in_raw_not_norm": sorted(raw_codes - norm_codes),
        "in_norm_not_raw": sorted(norm_codes - raw_codes),
    }


def _rebuild_norm_l3(store: PitSnapshotStore, source: str, endpoint: str,
                     ingest_date: str, run_id: str, as_of: str) -> Dict[str, Any]:
    """从**原始层**补建规范层缺失的标的（**幂等**，按 code 粒度；不重新抓取）。

    ⚠️ **按 code 粒度**的隐含前提：一个 code 在 norm 里出现 ⇒ 其**全窗口**已在。
    该前提成立是因为 raw 的 flush 只在**完整 code** 边界发生（``_fetch_l3``）。
    若历史上曾有「半个 code」落进 norm（如 2026-10-12 混入的 5 只短窗口冒烟数据），
    本函数**不会**发现 —— 那种残留须先清除，不能留着让补建「看起来完成了」。
    """
    raw_path = store.raw_path(source, endpoint, ingest_date, ".jsonl")
    if not raw_path.exists():
        raise SystemExit(f"原始层不存在，无从补建: {raw_path}")
    norm_path = store.norm_path(L3_DATASET, ingest_date)
    have = _norm_codes(norm_path)

    appended_codes: List[str] = []
    appended_rows = 0
    pending: List[Dict[str, str]] = []

    def _flush_norm() -> None:
        nonlocal appended_rows
        if not pending:
            return
        if norm_path.exists():
            store.append_normalized(L3_DATASET, ingest_date, pending)
        else:
            store.write_normalized(L3_DATASET, ingest_date, pending)
        appended_rows += len(pending)
        pending.clear()

    cur_code: Optional[str] = None
    cur_rows: List[Dict[str, Any]] = []
    n_raw_rows = 0
    with raw_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue  # 坏行跳过（与 read_raw_keys 同约定）
            n_raw_rows += 1
            code = str(rec.get("code", "")).split(".")[-1]
            if code != cur_code:
                if cur_code is not None and cur_code not in have:
                    pending.extend(_normalize_l3(cur_rows, run_id, as_of))
                    appended_codes.append(cur_code)
                    if len(appended_codes) % 50 == 0:
                        _flush_norm()
                cur_code, cur_rows = code, []
            cur_rows.append(rec)
    if cur_code is not None and cur_code not in have:
        pending.extend(_normalize_l3(cur_rows, run_id, as_of))
        appended_codes.append(cur_code)
    _flush_norm()

    return {
        "raw_path": str(raw_path),
        "norm_path": str(norm_path),
        "raw_rows": n_raw_rows,
        "norm_codes_before": len(have),
        "appended_codes": len(appended_codes),
        "appended_rows": appended_rows,
        "appended_code_list_head": appended_codes[:20],
    }


# ===========================================================================
# 通用自检
# ===========================================================================
def _self_check(
    rows: List[Dict[str, str]], dataset: str, raw_rows: Optional[int] = None
) -> Tuple[List[str], Dict[str, Any]]:
    problems: List[str] = []
    cfg = SELF_CHECK[dataset]
    meta = dataset_meta(dataset)
    n = len(rows)

    if n < cfg["min_rows"]:
        problems.append(f"FAIL 行数 {n} < 下限 {cfg['min_rows']:.0f}（源可能变更或抓取不完整）")

    dup = PitSnapshotStore.check_unique_key(rows, meta["unique_key"])
    if dup:
        problems.append(
            f"FAIL 复合主键 {'+'.join(meta['unique_key'])} 重复 {len(dup)} 个，例: {dup[:5]}"
        )

    for f in ("code", "effective_date", "as_of"):
        rate = PitSnapshotStore.check_missing_rate(rows, f)
        if rate > cfg["max_missing_rate"]:
            problems.append(f"WARN 字段 {f} 缺失率 {rate:.2%} > 上限 {cfg['max_missing_rate']:.2%}")

    metrics: Dict[str, Any] = {"n_rows": n, "n_unique_codes": len({r["code"] for r in rows})}

    # ⚠️ raw 层必须是**未过滤**的源响应。
    # baostock 的 query_stock_basic 全量含 指数(2)/可转债(4)/ETF(5)，股票(type=1)仅约 62%
    # → L1 的 raw 行数应**显著多于**规范层行数。若 ≤，即说明 raw 被过滤了
    #   （2026-10-11 实际发生过：raw 5,561 = 规范层 5,561，属 stale 缺陷）。
    if raw_rows is not None:
        metrics["raw_rows"] = raw_rows
        if dataset == L1_DATASET and raw_rows <= n:
            problems.append(
                f"WARN L1 raw 层 {raw_rows} 行 ≤ 规范层 {n} 行 —— raw 疑似被过滤"
                "（应为源响应全量，含指数/可转债/ETF）"
            )

    if dataset == L1_DATASET:
        n_del = sum(1 for r in rows if r["is_delisted"] == "1")
        share = n_del / n if n else 0.0
        if share > cfg["max_delist_share"]:
            problems.append(f"WARN 退市占比 {share:.2%} > 上限 {cfg['max_delist_share']:.2%}")
        metrics.update({"n_delisted": n_del, "delist_share": round(share, 6)})

    if dataset == L2_DATASET:
        n_stk = len({r["code"] for r in rows})
        if n_stk < cfg["min_stocks"]:
            problems.append(f"FAIL 覆盖股票数 {n_stk} < 下限 {cfg['min_stocks']:.0f}")
        metrics["n_stocks"] = n_stk

    if dataset == L3_DATASET:
        metrics["n_stocks"] = len({r["code"] for r in rows})

    return problems, metrics


def _ingest_one(dataset: str, args: argparse.Namespace) -> int:
    store = PitSnapshotStore(args.root)
    meta = dataset_meta(dataset)
    ts = now_cst()
    ingest_date = args.date or ts.strftime("%Y-%m-%d")
    run_id = make_run_id(ts)
    as_of = ts.isoformat(timespec="seconds")

    print(f"\n########## {dataset} ##########", flush=True)
    blob: Optional[bytes] = None
    suspect_stable: List[str] = []
    real_trunc: List[str] = []
    zero_data: List[str] = []      # L3：查询成功但 0 行（源无覆盖，非失败）
    zero_data_prefix_rejected: List[str] = []  # L3：其中 10004011 形态（号段不被源接受）
    done: set = set()
    raw_flushed = False       # L3 专用：原始层是否已由 `_fetch_l3` 增量写入
    if dataset == L1_DATASET:
        source, endpoint, suffix = "baostock", "query_stock_basic", ".jsonl"
        print("[1/5] 采集 baostock:query_stock_basic ...", flush=True)
        recs, raw_rows = _fetch_l1()
        print(f"      股票 {len(recs)} 只（含已退市）", flush=True)
        print("[2/5] 规范化（双时间轴）...", flush=True)
        rows = _normalize_l1(recs, run_id, as_of)
    elif dataset == L2_DATASET:
        source, endpoint, suffix = "swsresearch", "StockClassifyUse_stock", ".xls"
        print("[1/5] 下载申万行业变迁史 xls ...", flush=True)
        blob = _download_sw()
        print(f"      {len(blob):,} 字节（头 4 字节: {blob[:4].hex()}）", flush=True)
        print("[2/5] 解析 + 规范化（双时间轴）...", flush=True)
        recs2 = _parse_sw_xls(blob)
        rows = _normalize_l2(recs2, run_id, as_of)
        raw_rows = recs2
        print(f"      记录 {len(rows)} 行 · 股票 {len({r['code'] for r in rows})} 只", flush=True)
    elif dataset == L3_DATASET:
        source, endpoint, suffix = "baostock", "query_history_k_data_plus", ".jsonl"
        if args.rebuild_norm:
            # 从原始层补建规范层缺失的标的（**幂等**）—— 不重新抓取。
            # 场景：整轮回填崩在采集阶段（raw 已落 N 只、norm 未写），
            # 此后只按 --resume 续跑会让这 N 只**永远**进不了规范层。
            print("[1/5] 跳过采集（--rebuild-norm：仅从 raw 补建 norm）...", flush=True)
            info = _rebuild_norm_l3(store, source, endpoint, ingest_date, run_id, as_of)
            print(f"      raw {info['raw_rows']:,} 行 · 补建前 norm {info['norm_codes_before']} 只"
                  f" → 补建 {info['appended_codes']} 只 / {info['appended_rows']:,} 行", flush=True)
            gap = _layer_gap(store, source, endpoint, ingest_date, L3_DATASET)
            # P010 Q3.2：双向断言 —— norm 多出 raw 的 code（orphan 残留）同样不闭合
            gap_open = gap["in_raw_not_norm"] + gap["in_norm_not_raw"]
            print(f"      层间缺口: raw {gap['raw_codes']} 只 vs norm {gap['norm_codes']} 只"
                  f" → raw 缺 {len(gap['in_raw_not_norm'])} 只 · norm 多 {len(gap['in_norm_not_raw'])} 只",
                  flush=True)
            store.log_ingest({
                "ts": as_of,
                "ingest_run_id": run_id,
                "dataset": dataset,
                "source": source,
                "endpoint": endpoint,
                "ingest_date": ingest_date,
                "pit_mode": meta["pit_mode"],
                "action": "rebuild-norm",
                "status": "OK" if not gap_open else "WARN",
                "problems": ([] if not gap_open else
                             [f"WARN 层间缺口仍存 {len(gap_open)} 只"]),
                "metrics": {**info, "layer_gap_in_norm_not_raw": len(gap["in_norm_not_raw"])},
            })
            if gap_open:
                print(f"      ❌ 层间缺口未闭合（raw 缺 {len(gap['in_raw_not_norm'])} · "
                      f"norm 多 {len(gap['in_norm_not_raw'])}）→ 非零退出"
                      "（须人工排查半个 code / orphan 残留）", flush=True)
                return 2
            print("      ✅ 层间缺口闭合（code 集合双向一致）", flush=True)
            return 0
        if not args.universe:
            raise SystemExit("L3 需要 --universe <数据集目录>（如 D:/tdx_dataset_v3）")
        if not (args.start and args.end):
            raise SystemExit("L3 需要 --start 与 --end（YYYY-MM-DD）")
        codes = _universe_codes(args.universe, args.limit)
        raw_target = store.raw_path(source, endpoint, ingest_date, suffix)
        if raw_target.exists() and not args.resume:
            raise OverwriteRefusedError(
                f"原始层已存在（拒绝覆盖，L3 请用 --resume 续跑）: {raw_target}"
            )
        if args.resume:
            # ⚠️ 长期回填必须能**断点续传**（baostock 时变/挂起，一轮跑不完）
            done = store.read_raw_keys(source, endpoint, ingest_date)
            # 零数据边车：已核实的「查询成功但 0 行」代码排除重试
            # （否则每次 --resume 都重试它们；只剩它们时 min_rows 假 FAIL）
            zero_known = read_zero_data_codes(
                zero_data_sidecar_path(store.meta_dir, ingest_date))
            before = len(codes)
            codes, excluded_zero = filter_resume_codes(codes, done, zero_known)
            print(f"      --resume：已完成 {len(done)} 只 → 待采 {len(codes)}/{before} 只", flush=True)
            if excluded_zero:
                print(f"      ⓘ 排除边车清单内已知零数据代码 {len(excluded_zero)} 只"
                      f"（查询成功但源无覆盖，非失败；清单 {zero_data_sidecar_path(store.meta_dir, ingest_date)}）: "
                      f"{excluded_zero[:10]}{'…' if len(excluded_zero) > 10 else ''}", flush=True)
            if not codes:
                print("      全部已完成，无新任务", flush=True)
                return 0
        print(f"[1/5] 采集 baostock:query_history_k_data_plus"
              f"（{len(codes)} 只 · {args.start}~{args.end} · 不复权）...", flush=True)
        raw_rows, n_raw, suspect_stable, real_trunc, failed, zero_data, zero_data_prefix_rejected = _fetch_l3(
            codes, args.start, args.end, flush_path=raw_target, flush_every=args.flush_every
        )
        raw_flushed = True        # 原始层已由 `_fetch_l3` **增量**写入
        print(f"      原始 {n_raw:,} 行", flush=True)
        if zero_data:
            print(f"      ⓘ 零数据代码 {len(zero_data)} 只（源无覆盖，**非失败**；其中"
                  f"号段不被源接受的 10004011 形态 {len(zero_data_prefix_rejected)} 只）: "
                  f"{zero_data[:10]}{'…' if len(zero_data) > 10 else ''}", flush=True)
            if args.record_zero_data:
                # 显式 opt-in：经人工核实后把零数据代码记入边车清单（默认关闭 ——
                # 防止把一次瞬时空响应误永久记为「无数据」，那是静默缺口）。
                zpath = zero_data_sidecar_path(store.meta_dir, ingest_date)
                zpath.parent.mkdir(parents=True, exist_ok=True)
                known = read_zero_data_codes(zpath)
                fresh = [c for c in zero_data if c not in known]
                if fresh:
                    with zpath.open("a", encoding="utf-8") as fh:
                        fh.write("# 追加于 " + as_of + "（--record-zero-data，经人工核实）\n")
                        for c in fresh:
                            fh.write(c + "\n")
                print(f"      ⓘ --record-zero-data：{len(fresh)} 只新零数据代码已记入 {zpath}"
                      f"（原有 {len(known)} 只；移除清单条目即恢复对该代码的重试）", flush=True)
        if failed:
            print(f"      ⚠️ 抓取失败 {len(failed)} 只（已跳过；--resume 续跑可补采）:", flush=True)
            for f_ in failed[:20]:
                print(f"        - {f_}", flush=True)
            if len(failed) > 20:
                print(f"        ... 另 {len(failed) - 20} 只（全量见 metrics.failed_codes）", flush=True)
        print("[2/5] 规范化（双时间轴）...", flush=True)
        rows = _normalize_l3(raw_rows, run_id, as_of)
        print(f"      规范 {len(rows):,} 行 · 标的 {len({r['code'] for r in rows}):,} 只", flush=True)
    else:  # pragma: no cover - argparse choices 已限制
        raise SystemExit(f"未实现的数据集: {dataset}")

    print("[3/5] 自检（阈值事前固定）...", flush=True)
    problems, metrics = _self_check(rows, dataset, len(raw_rows))
    if dataset == L3_DATASET:
        metrics["n_suspect_stable"] = len(suspect_stable)
        metrics["n_real_truncated"] = len(real_trunc)
        metrics["n_zero_data_codes"] = len(zero_data)
        metrics["n_zero_data_prefix_rejected"] = len(zero_data_prefix_rejected)
        if zero_data:
            metrics["zero_data_codes"] = zero_data
        if zero_data_prefix_rejected:
            metrics["zero_data_prefix_rejected"] = zero_data_prefix_rejected
        if real_trunc:
            problems.append(
                f"FAIL 重取发现**真截断** {len(real_trunc)} 只（两次行数不同），"
                f"例: {real_trunc[:5]}"
            )
        if suspect_stable:
            problems.append(
                f"WARN 行数恰为 2000 整数倍且重取一致 {len(suspect_stable)} 只"
                f"（合法但**须人工确认**）: {suspect_stable[:5]}"
            )
        if failed:
            metrics["n_failed_codes"] = len(failed)
            metrics["failed_codes"] = failed
            problems.append(
                f"WARN 抓取失败 {len(failed)} 只已跳过（--resume 续跑可补采）: {failed[:5]}"
            )
    for p in problems:
        print(f"      {p}", flush=True)
    fails = [p for p in problems if p.startswith("FAIL")]
    print(f"      指标: {json.dumps(metrics, ensure_ascii=False)}", flush=True)

    print("[4/5] 落盘（只追加）...", flush=True)
    # ⚠️ 必须区分「实际写入」与「因已存在而跳过」—— 否则日志里两条 sha 相同的记录
    # 无法分辨哪条真写了（2026-10-11 的 22:44 / 22:45 两条即为此情形）。
    action = "write"
    try:
        if raw_flushed:
            # L3：原始层已由 `_fetch_l3` **增量**写入（可中断续跑）→ 只处理规范层
            raw_path = raw_target
            norm_p = (store.append_normalized(dataset, ingest_date, rows)
                      if done else store.write_normalized(dataset, ingest_date, rows))
        elif args.resume and done:
            # 续跑：向已存在的 raw / norm **追加**（只追加、不覆盖）
            raw_path = store.append_raw_lines(source, endpoint, ingest_date, raw_rows, suffix=suffix)
            norm_p = store.append_normalized(dataset, ingest_date, rows)
        elif blob is not None:
            raw_path = store.append_raw_bytes(
                source, endpoint, ingest_date, blob, suffix=suffix, force=args.force
            )
            norm_p = store.write_normalized(dataset, ingest_date, rows, force=args.force)
        else:
            raw_path = store.append_raw(source, endpoint, ingest_date, raw_rows, force=args.force)
            norm_p = store.write_normalized(dataset, ingest_date, rows, force=args.force)
        print(f"      raw  : {raw_path}", flush=True)
        print(f"      norm : {norm_p}", flush=True)
    except OverwriteRefusedError as exc:
        action = "skip"
        print(f"      SKIP {exc}（用 --force 覆盖）", flush=True)
        raw_path = store.raw_path(source, endpoint, ingest_date, suffix)
        norm_p = store.norm_path(dataset, ingest_date)

    if dataset == L3_DATASET and raw_flushed:
        # 层间一致性（**必须在 norm 落盘后检查**）：崩溃续跑会让「raw 有、norm 无」的
        # code 静默存在（2026-10-12 事故：raw 456 只 / norm 0 只）。
        # 缺口用 --rebuild-norm 从 raw 幂等补齐；此处只负责**显式化**，绝不静默。
        # P010 Q3.2：反向（「norm 有、raw 无」的 orphan）同样要显式 —— 只查一个方向
        # 会漏掉「半个 code」失败形态（行数相等而 code 集合不等）。
        gap = _layer_gap(store, source, endpoint, ingest_date, L3_DATASET)
        metrics["layer_gap_raw_codes"] = gap["raw_codes"]
        metrics["layer_gap_norm_codes"] = gap["norm_codes"]
        metrics["layer_gap_in_raw_not_norm"] = len(gap["in_raw_not_norm"])
        metrics["layer_gap_in_norm_not_raw"] = len(gap["in_norm_not_raw"])
        if gap["in_raw_not_norm"]:
            problems.append(
                f"WARN 规范层落后于原始层 {len(gap['in_raw_not_norm'])} 只"
                f"（崩溃续跑的后遗症；用 --rebuild-norm 从 raw 补齐）: {gap['in_raw_not_norm'][:5]}"
            )
        if gap["in_norm_not_raw"]:
            problems.append(
                f"WARN 规范层多出原始层 {len(gap['in_norm_not_raw'])} 只"
                f"(orphan 残留：「半个 code」失败形态，须人工排查后清除): {gap['in_norm_not_raw'][:5]}"
            )

    entry: Dict[str, Any] = {
        "ts": as_of,
        "ingest_run_id": run_id,
        "dataset": dataset,
        "source": source,
        "endpoint": endpoint,
        "ingest_date": ingest_date,
        "pit_mode": meta["pit_mode"],
        "rows": len(rows),
        "raw_rows": len(raw_rows),
        "raw_sha256": sha256_of_file(raw_path) if raw_path.exists() else None,
        "norm_sha256": sha256_of_file(norm_p) if norm_p.exists() else None,
        "status": "FAIL" if fails else ("WARN" if problems else "OK"),
        "problems": problems,
        "metrics": metrics,
        "action": action,
        "force": bool(args.force),
    }
    store.log_ingest(entry)

    if fails:
        print("      ❌ 自检 FAIL → 非零退出（不得静默通过）", flush=True)

    if args.reconcile:
        if dataset == L3_DATASET:
            raise SystemExit(
                "L3 的对账请用 scripts/run_l3_valuation_reconciliation.py"
                "（与 pit_fundamentals 的 pb/pe_ttm 对账，口径与 L1/L2 不同）"
            )
        print(f"[5/5] 与 {args.reconcile} 交叉核对 ...", flush=True)
        rec = (_reconcile_l1 if dataset == L1_DATASET else _reconcile_l2)(
            store, args.reconcile, ingest_date
        )
        for k, v in rec.items():
            if isinstance(v, (dict, list)):
                print(f"      {k}: {json.dumps(v, ensure_ascii=False)[:300]}", flush=True)
            else:
                print(f"      {k}: {v}", flush=True)
        if args.out:
            outp = Path(args.out)
            outp.parent.mkdir(parents=True, exist_ok=True)
            with outp.open("w", encoding="utf-8", newline="\n") as fh:
                fh.write(json.dumps(rec, ensure_ascii=False, indent=2))
            print(f"      已写 {outp}", flush=True)
    else:
        print("[5/5] 跳过对账（未传 --reconcile）", flush=True)

    return 2 if fails else 0


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="PIT 快照采集（L1 上市/退市日 · L2 申万行业变迁史 · L3 日频估值历史）")
    ap.add_argument("--root", default="D:/pit_snapshots", help="快照库根目录")
    ap.add_argument("--dataset", default=L1_DATASET, choices=sorted(DATASET_REGISTRY))
    ap.add_argument("--all", action="store_true", help="采集全部已登记数据集")
    ap.add_argument("--date", default=None, help="落盘日期 YYYY-MM-DD（默认今天）")
    ap.add_argument("--force", action="store_true", help="覆盖已落盘日期（留痕）")
    ap.add_argument("--reconcile", default=None, help="与本地数据集交叉核对（如 D:/tdx_dataset_v3）")
    ap.add_argument("--out", default=None, help="对账结果 JSON 输出路径")
    # --- L3 专用 ---
    ap.add_argument("--universe", default=None,
                    help="L3：本地数据集目录（取其 stocks/*.csv 的代码作为标的池）")
    ap.add_argument("--start", default=None, help="L3：起始日 YYYY-MM-DD")
    ap.add_argument("--end", default=None, help="L3：结束日 YYYY-MM-DD")
    ap.add_argument("--limit", type=int, default=0,
                    help="L3：只取前 N 只（0=全部；小样本试跑用）")
    ap.add_argument("--resume", action="store_true",
                    help="L3：跳过已落盘标的并**追加**（长期回填的断点续传）")
    ap.add_argument("--record-zero-data", action="store_true", dest="record_zero_data",
                    help="L3：把本轮「查询成功但 0 行」的代码追加进零数据边车清单"
                         "（meta/l3_zero_data_codes_<date>.txt；须经人工核实后再用 —— "
                         "默认关闭，防止把瞬时空响应误永久记为无数据；--resume 会排除清单内代码）")
    ap.add_argument("--rebuild-norm", action="store_true", dest="rebuild_norm",
                    help="L3：不抓取，仅从原始层补建规范层缺失的标的（幂等，按 code 粒度）")
    ap.add_argument("--flush-every", type=int, default=100, dest="flush_every",
                    help="L3：每 N 只增量落盘一次（0=只在结束时写；长期回填务必保持 >0）")
    args = ap.parse_args(argv)

    targets = sorted(DATASET_REGISTRY) if args.all else [args.dataset]
    # `--all` 默认**跳过 L3** —— 它需要 --universe/--start/--end。
    # 缺参时**显式跳过并说明**，比直接抛错更合适（`--all` 的语义是「能采的都采」），
    # 但绝不静默跳过。
    if args.all and L3_DATASET in targets and not (args.universe and args.start and args.end):
        targets = [d for d in targets if d != L3_DATASET]
        print(f"ⓘ --all 跳过 {L3_DATASET}（缺 --universe / --start / --end）", flush=True)
    rc = 0
    for ds in targets:
        rc = max(rc, _ingest_one(ds, args))
    print(f"\n完成：{len(targets)} 个数据集 · 退出码 {rc}", flush=True)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
