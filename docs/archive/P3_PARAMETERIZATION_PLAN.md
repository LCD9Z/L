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
| 5 | `board_of` **×3**（审计列 2 处，实为 3 处） | ⚠️ **②③ 完全相同，① 另一值域** | ②③ 仅变量名（`code`/`c`）不同；① 返回**中文板块名**且含 B 股分类 → **不可三合一** | **中**（②**生产零消费者** → 直接删 13 行） | **低**（不动回测主路径） | **推荐：删 ②，保留 ①③** |

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

### 组 5（`board_of`）—— 依赖图已画：**修正审计，实际 3 处且值域分两派**

> **2026-10-15 补正**（逐码比对后推翻原方案的两点）

#### 修正一：审计列 2 处，实际 **3 处**

| # | 位置 | 值域 | 生产消费者 |
|:--:|---|---|---|
| ① | `ashare/ashare_market.py:10` | **中文板块名**（沪主板/创业板/科创板/北交所/**沪B股/深B股**/其他A股） | `exchange_rules.py:87`、`ashare_universe.py:15`、`fetch/news.py:150` —— **回测主路径** |
| ② | `tdx/tdx_csv_adapter.py:124` | 英文短码（`sh_main`/`star`/`sz_main`/`chinext`/`bse`） | **仅 `tests/test_tdx_adapter.py:99`——生产侧零消费者** |
| ③ | `tdx_native/day_reader.py:96` | 英文短码（同上） | `daily_report.py:40`、`limit_pct`（盘后报告） |

**①②值域互不相交**（中文名 vs 英文短码）⇒ **不可三合一**；组 5 只收敛 **②③**。

#### 修正二：方案从「定宿主」改为「**删除 ②**」

原方案（② 改为 `from tdx_native.day_reader import board_of`）会引入
`tdx/ → tdx_native/` 的**跨包反向依赖**（`tdx_csv_adapter` 数据集构建 ← `tdx_native`
推荐系统），架构上不成立。依赖图既明，**更干净的做法**：

- **删除 ②**（生产侧零消费者，唯一引用是 `tests/test_tdx_adapter.py:99`）；
- 该测试改指向 ③（`tdx_native.day_reader.board_of`，与其断言值一致）；
- ① 与 ③ **保留**（值域不同、消费者不同，**不是重复**）。

⇒ 组 5 消除后的净效果：删 13 行 + 消除 1 处跨包依赖风险，且**不动回测主路径**。
（若日后要统一值域，那是**独立专项**，须同时改 3 处消费者并回归，不在本次范围。）

#### 顺带发现：②③/① 的 3 处静默错误分类（**登记，不在本次修**）

| 输入 | ① ashare | ②③ tdx | 影响面评估 |
|---|---|---|---|
| `900901` / `200011`（B 股） | 沪B股 / 深B股 ✅ | **`bse`（北交所）** ✗ → `limit_pct` 给 **30%**（实为 10%） | ②生产零消费者；③仅盘后报告。**待查 universe 是否含 B 股**（未定性） |
| `sh600519`（带市场前缀） | 沪主板 ✅（会剥离 `sh/sz/bj`） | **`bse`** ✗ | 同上；②③ 只做 `zfill(6)`，不剥前缀 |
| `689009`（科创板 CDR） | **`其他A股`** ✗ | `star` ✅ | 本地通达信 `sh/lday` **689 段 0 只** → **当前无实际影响** |

三者均为**分类函数缺陷**而非本次重复治理目标；已写入
`tests/test_p3_equivalence_baseline.py::test_board_of_known_divergences_locked`
作为 characterization 锁定（**若日后修了，该测试会变红 → 强制人工确认影响面**）。

**验证**：15 → **17 项**全绿（`test_board_of_third_site_is_a_distinct_value_domain`
钉死「不可三合一」；`test_board_of_known_divergences_locked` 钉死 3 处现状）。

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
2. **组 5**（依赖图已画：删 ② + 改 `tests/test_tdx_adapter.py:99` 指向 ③）→ 跑 CI；
   ⚠️ 删 ② 时**不要**顺手修 B 股/前缀分类（见 §组5「3 处静默错误分类」）——
   那是行为变更，须独立评估；若修了，`test_board_of_known_divergences_locked`
   会变红并强制确认；
3. **组 2**（等价性测试先行，6 处逐一改）→ 跑 CI；**须等重算结束**（涉 `factor_ic_lab`）；
4. 组 1 / 4 **不做**（方案 §二 已说明理由）；
5. 全部完成后重跑 `scripts/audit_code_redundancy.py` 记录组数变化
   （当前：完全重复组 7 / 同构组 5；基线：13 / 7）。

**预期**：同构组 5 → 3（组 2/3/5 消除；组 1/4 保留）；完全重复组 7 → 6
（组 5 的 `board_of` 从 exact 列表消除）。

> 组 5 的删除动作**不引入任何新依赖**，且不触碰回测主路径（①`ashare`）
> —— 这是依赖图带来的最大收益：原「跨包 import」方案被否决。
