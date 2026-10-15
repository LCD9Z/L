# 审计 P3 · 同构函数参数化方案（2026-10-15）

> **上位依据**：`CODE_REDUNDANCY_AUDIT.md`（P3 = 同构组参数化，原估 1~1.5 人日，中风险）。
> **性质**：只读分析 + 方案设计。**未改任何代码** —— 因当前**跨线重算运行中**，
> 其中组 2 涉及重算依赖模块（`factors/factor_ic_lab.py`），改动会使重算产物混用版本。
> **执行时机**：重算完成后（或经双方确认的窗口期）。

---

## 一、五组实况（本轮逐组读码比对，非照抄审计）

| 组 | 位置 | 真重复？ | 实测差异 | 参数化收益 | 风险 | 建议 |
|:--:|---|:--:|---|---|:--:|---|
| 1 | `agents_analysts.py` `generate_prompt ×4` | ⚠️ 结构重复 | 前导 3 行 + f-string 结构相同；**模板内容完全不同**（基本面/情绪/新闻/技术） | **低**（省 ~9 行；模板仍须各自定义） | **中**（**改 LLM 输入**） | **保留** |
| 2 | `factors/factor_ic_lab.py:143` + 5 脚本 `_rank` | ✅ **逻辑相同** | 仅变量名（`values/r`）与签名（`Sequence`/`List`）不同；**平均秩算法逐行一致** | **中高**（省 ~78 行） | 中（改 6 处调用） | **推荐** |
| 3 | `fetch/fundamentals_source.py` `fetch_all_periods` / `fetch_all_disclosures` | ✅ **结构相同** | 逐期循环 + try/except + 空结果检查 + `on_progress` + `delay` **完全一致**；仅被调函数不同（`fetch_period` / `fetch_disclosure_period`） | **中**（省 ~25 行 + 消除双份维护） | **低** | **推荐** |
| 4 | `orchestrator.py` `_get_agent_name` / `_get_agent_emoji` | ❌ **语义不同** | 两个**独立映射表**（中文名 vs emoji），结构相似但语义无关 | 低 | 低 | **保留**（可选合并为 `_AGENT_META`） |
| 5 | `tdx/tdx_csv_adapter.py:124` + `tdx_native/day_reader.py:96` `board_of` | ✅ **完全相同** | 仅变量名（`code`/`c`）与 docstring 不同 | **中**（省 13 行） | **低** | **推荐** |

**结论**：推荐收敛 **2 / 3 / 5**（真重复、风险可控）；**保留 1**（改 LLM 输入收益低）、
**4**（语义不同，强行合并会引入无谓嵌套）。

> ⚠️ 与审计原文的差异：审计称「`_rank` 口径待比对」——**本轮比对完成：逻辑一致**
> （均为「平均秩处理并列」，逐行等价）。故组 2 可收敛，前提是加等价性测试。

---

## 二、各组方案

### 组 3（`fetch_all_*`）—— 最低风险，建议先做

```python
def _fetch_all(items: List[str], fetch_fn, *, delay: float = 0.4,
               on_progress=None) -> Dict[str, Any]:
    """逐期抓取的通用骨架。失败/空结果**如实记入 failed**，不静默跳过。"""
    records: List[Dict[str, Any]] = []
    ok: List[str] = []
    failed: Dict[str, str] = {}
    for i, it in enumerate(items):
        try:
            got = fetch_fn(it)
        except AkshareUnavailable as exc:
            failed[it] = str(exc)
            if on_progress:
                on_progress(i + 1, len(items), it, 0, str(exc))
            continue
        if not got:
            failed[it] = "empty_records"
            if on_progress:
                on_progress(i + 1, len(items), it, 0, "empty_records")
            continue
        records.extend(got)
        ok.append(it)
        if on_progress:
            on_progress(i + 1, len(items), it, len(got), "")
        if delay:
            time.sleep(delay)
    return {"records": records, "ok_periods": ok, "failed": failed}

def fetch_all_periods(periods, *, delay=0.4, on_progress=None):
    return _fetch_all(periods, fetch_period, delay=delay, on_progress=on_progress)

def fetch_all_disclosures(report_period_list, *, delay=0.4, on_progress=None):
    return _fetch_all(report_period_list, fetch_disclosure_period,
                      delay=delay, on_progress=on_progress)
```

**验证**：mock `fetch_fn`，断言两函数在「全成功 / 部分空 / 抛 `AkshareUnavailable`」
三种输入下的返回**逐键一致**（与改造前实现对比）。

### 组 5（`board_of`）—— 需定宿主

- 两处逻辑相同；`tdx/tdx_csv_adapter.py` 与 `tdx_native/day_reader.py` 是**不同包**；
- **方案**：以 `tdx_native/day_reader.board_of` 为宿主（它带 `limit_pct` 同伴函数，
  语义更完整），`tdx/tdx_csv_adapter.py` 改为 `from tdx_native.day_reader import board_of`；
- ⚠️ **依赖方向检查**：须确认 `tdx/` 不因该 import 产生循环依赖或使 `tdx_native` 成为
  `tdx/` 的强制依赖（`tdx_csv_adapter` 是**数据集构建**用，`tdx_native` 是**推荐系统**用
  —— 反向依赖可能不合架构，**须先画依赖图**）。若不合，改为两处都从
  `exchange_rules.py` 导入（该模块已含 `derive_limit_ratio`/`is_st_flag`，语义最贴近）。

**验证**：对 `600/688/000/300/920/8xx` 等前缀断言返回值一致（两实现现成可比）。

### 组 2（`_rank ×6`）—— 需等价性测试 + 需等重算结束

- 6 处：`factors/factor_ic_lab.py:143`（宿主候选）+ `scripts/{evaluate_form_screen:62,
  factor_corr_by_window:60, run_factor_orthogonality:62, run_tdx_universe_ic:108,
  run_xsrc_ic:67}`；
- **方案**：统一 `from factors.factor_ic_lab import _rank as _rank`（脚本侧已有 sys.path 插入）；
- ⚠️ **两个障碍**：
  1. **重算依赖**：`factor_ic_lab` 在跨线重算的依赖链上 → **必须等重算完成**；
  2. 5 个脚本各带 `sys.path` 设置，import 形态需逐一核对（`scripts/` 侧已有
     `_study_common` 先例可参照）。
- **验证**：加等价性测试——同一组含**并列值**的输入（如 `[3, 1, 1, 2]`）下，
  新旧实现返回**逐元素相等**（并列处理是唯一易错点）。

### 组 1（`generate_prompt ×4`）—— 保留，理由

- 4 个模板**内容完全不同**（不同分析师角色），参数化只能抽走前导 3 行；
- **改 prompt = 改 LLM 输入**，任何字符差异都会改变输出 → 须专项冒烟（成本 > 收益）；
- **结论**：**保留现状**；若将来要统一，做法是基类 `_render(template)` + 各子类
  `TEMPLATE` 常量，并**用字节级测试锁定 4 个 prompt 与改造前一致**。

### 组 4（`_get_agent_*`）—— 保留

- 两表语义无关（名称 / emoji），强行合并为嵌套 dict 会让「取名称」多一层解引用；
- **结论**：**保留**（收益 < 可读性损失）。

---

## 三、执行序（重算完成后）

1. **组 3**（最低风险，先做 + 等价性测试）→ 跑 CI；
2. **组 5**（先画依赖图定宿主）→ 跑 CI；
3. **组 2**（等价性测试先行，6 处逐一改）→ 跑 CI；
4. 组 1 / 4 **不做**（方案 §二 已说明理由）；
5. 全部完成后重跑 `scripts/audit_code_redundancy.py` 记录组数变化
   （当前：完全重复组 7 / 同构组 5；基线：13 / 7）。

**预期**：同构组 5 → 3（组 2/3/5 消除；组 1/4 保留）；完全重复组 7 → 6
（组 5 的 `board_of` 从 exact 列表消除）。
