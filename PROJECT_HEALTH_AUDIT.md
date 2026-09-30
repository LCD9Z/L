# 项目体检报告：过滤器形态 · 静默失效 · 大文件（2026-09-30）

> **触发**：用户三问 —— ①市场门转成过滤器有哪些要注意 ②项目是不是有很多静默失效
> ③有没有大文件、是否要拆分
> **产物**：`risk/market_risk_gate.py`（新增 `build_market_filter`）·
> `scripts/scan_silent_failures.py`（新增扫描器）· `reports/silent_scan.json`

---

## 一、市场门 → 过滤器：三条必须注意的差异

### 1.1 两种形态的语义**不同**（已用代码核实）

`portfolio_backtest.py` 的关键两行：

```python
if candidate_filter is not None and not candidate_filter(code,hist,day): continue   # 排除 → 不进 candidates
...
if scale<=0: slots=0    # position_scaler=0 → 直接不开新仓
```

| | `position_scaler`（gate） | `candidate_filter`（filter） |
|---|---|---|
| 签名 | `(day) -> float` | `(code, hist, day) -> bool` |
| 阻断方式 | 新开仓预算 = 0 → **当日不建仓** | 该股不进候选池 → **顺位选下一只** |
| **全池**阻断 | 空仓 | 候选池空 → 空仓（**等价**） |
| **部分**阻断 | 不适用（无逐股能力） | **换股**，持仓数可能仍填满 |
| 卖出 | 不影响 | 不影响 |
| 计算位置 | 打分**之后**（`slots` 计算处） | 打分**之前**（可省算力） |

### 1.2 ⚠️ 坑 1~3（第 4 个坑见 §1.5，实测才发现）

**坑 1 · 「排除全池」才等价于「不开仓」**
若只想在风险日「少买」，用 filter 会变成**换股**（买排名更低的票）—— 与「降敞口」不是一回事。
**市场级 filter 是"全池开关"，不是"降敞口旋钮"。**

**坑 2 · filter 可能**增加**交易数，而成本是本项目最大确定性损耗**
换股 = 卖出 + 买入。项目已测出**成本拖累 16.58pp/年**是最大确定性损耗
（见 `FACTOR_HORIZON_DECAY_REPORT.md`）。**换股会加剧它**；
gate 则直接减少建仓，不产生额外交易。
→ **若目标是降风险敞口，gate 更合适；filter 只在需要"风险日换股"时才有优势。**

**坑 3 · filter 在回测热路径里被逐股逐日调用**
`candidate_filter` 在 `for code, bars in data.items()` 循环内调用 →
**函数内不得有任何 I/O**（本实现用预计算集合查表，零 I/O）。
若写成「每次调用重算风险状态」，回测会慢几个数量级。

### 1.3 实现

新增 `build_market_filter(risk_by_day, *, block_states, cooldown_days, trading_days)`，
与 `build_market_gate` 共享冷却期语义（承接「EXTREME 日落在调仓日的概率仅 1/20」那次教训）。

守卫测试 7 项（`tests/test_market_risk_gate.py`），锁住：
全池判定 · 未知日期放行 · **不区分个股** · 冷却期 · 与 gate 在阻断日一致 · **无副作用**。

### 1.4 实测对比：**发现了第 4 个坑，且它最隐蔽**

`reports/_ab_filter.log`（同窗口 `2024-01-02` 起 / 300 只 / h=20 / 冷却 10 日）：

| 配置 | 净超额 | 交易数 | 最大回撤 |
|------|------:|------:|--------:|
| ① 无门 | **+3.92%** | 165 | 30.243% |
| ② `gate`（预算=0） | **−3.38%** | 163 | **25.702%** |
| ③ `filter`（全池排除） | **−4.61%** | 163 | 26.123% |
| **filter vs gate** | **−1.23pp** | **0** | **+0.421** |

**交易数完全相同（163），但结果差 1.23pp** —— 说明两者**并非等价**。

### 1.5 ⚠️ 坑 4（最隐蔽）：**过滤器是布尔语义，无法表达「降敞口」**

根因已查明 —— 窗口内的状态分布：

| 状态 | 天数 | `gate` 行为 | `filter` 行为 |
|------|:---:|------|------|
| `EXTREME` | **2**（2024-02-05、2025-04-07） | 预算 = 0 → 不建仓 | 排除 → 不建仓（**等价**） |
| `ELEVATED` | **5**（2024-02-28、04-15、04-16、10-09、2026-07-20） | **预算 × 0.5 → 半仓** | **无动作** |

**`candidate_filter` 的返回类型是 `bool`，只有「买 / 不买」两态，
无法表达 `position_scaler` 的「买多少」。**

→ **把门转成过滤器，会丢失 `ELEVATED` 档的"减半"能力。**
实测这一丢失值 **−1.23pp 超额 / +0.42pp 回撤**（相对 gate）。

**这是本轮最重要的结论**：

| 目标 | 该用哪个 |
|------|---------|
| 「风险日**不买**」 | 两者皆可（等价） |
| 「风险日**少买**」（降敞口） | **只能用 `gate`** —— filter 做不到 |
| 「风险日**换股**」（避开某类个股） | **只能用 `filter`** —— gate 无逐股能力 |
| 两者**同时用** | 可组合（`position_scaler` + `candidate_filter` 是两个独立参数） |

**建议**：**市场级风险控制用 `gate`**（需要"减半"这个中间档）；
`filter` 留给**逐股**场景（如「风险日排除高波动股」）——
那才是 `candidate_filter(code, hist, day)` 这个签名存在的意义。

---

## 二、静默失效排查：**有，但数量最多的那类不是最危险的**

新增 `scripts/scan_silent_failures.py`（5 类模式），结果：

| 类别 | 数量 | 风险判读 |
|------|-----:|---------|
| ① 被吞掉的 `except: pass` | **13 处** | 需逐处判断 —— 数据源不可用时的诚实降级是合理的，但每处都可能让上游缺陷静默 |
| ② 数据字段静默默认值（`x.get(k) or 0`） | **189 处** | **数量最多，但实测几乎全部无害**（见 §2.2） |
| ③ 返回 `None` 但签名未标注 `Optional` | **38 处** | 调用方容易直接对 `None` 做算术（运行时才炸） |
| ④ 恒真/恒假守卫 | 1 处 | `market_regime` 的 `bulls >= 2`（**已修**） |
| ⑤ 数据集列 vs 代码引用 | **0 处** | ✅ 所有列都被引用过（turnover 修复已闭环） |

### 2.1 真正造成损害的 5 个静默缺陷（全部已修）

| 缺陷 | 表现 | 影响 |
|------|------|------|
| `_norm_date` 把 `pd.NaT` 写成 `"NaT"` | 日期字段变垃圾值，无异常 | 连带 `revisions` **恒等于 3** |
| `load_certified_csv` 白名单漏 `turnover` | 打分函数换手率分项**恒为 0** | **过线率 6.65% vs 应有的 18.71%**（近 3 倍） |
| `revisions` 字段 | 因 NaT 问题恒等于 3 | 假设检验失真 |
| 创业板涨跌幅 PIT 违规 | 改革前按 10% 而非 5% | 单向乐观偏差（已回写 834 只） |
| `market_regime` 的 `bulls >= 2` | 离线只有 1 个指数 → **永远返回 RANGE** | 模块静默无用 |

### 2.1b 本轮新踩的一个「静默」实例（值得记下）

写 `scan_silent_failures.py` 时，我用 `Path.write_text(json.dumps(...), encoding="utf-8")`
输出结果 —— **在 Windows 上这会把 `\n` 静默转成 `\r\n`**，
导致 `tests/test_module_splits.py::test_line_endings_are_lf` 失败。

**它属于哪一类**：既不是异常（不报错），也不是缺失（数据完整），
而是**「产物不合规但不自知」** —— 与 §2 的契约断裂同类：
**代码"成功"了，结果却错了。**

**修法**：显式 `open(..., newline="\n")`。已在脚本里加注释说明，防止后人再踩。

> 这个例子恰好说明：**"静默失效"不是一种代码模式，而是一种结果状态** ——
> 扫描器能定位候选点（`write_text` 没有 `newline` 参数），
> 但**"它会不会造成问题"取决于运行环境**（Windows vs Linux）。
> 这就是为什么本项目坚持「守卫测试 + CI 全绿」而不是只靠静态检查。

### 2.1b 本轮新踩的一个「静默」实例（值得记下）

写 `scan_silent_failures.py` 时，我用 `Path.write_text(json.dumps(...), encoding="utf-8")`
输出结果 —— **在 Windows 上这会把 `
` 静默转成 `
`**，
导致 `tests/test_module_splits.py::test_line_endings_are_lf` 失败。

**它属于哪一类**：既不是异常（不报错），也不是缺失（数据完整），
而是**「产物不合规但不自知」** —— 与 §2 的契约断裂同类：
**代码"成功"了，结果却错了。**

**修法**：显式 `open(..., newline="
")`。已在脚本里加注释说明，防止后人再踩。

> 这个例子恰好说明：**"静默失效"不是一种代码模式，而是一种结果状态** ——
> 扫描器能定位候选点（`write_text` 没有 `newline` 参数），
> 但**"它会不会造成问题"取决于运行环境**（Windows vs Linux）。
> 这就是为什么本项目坚持「守卫测试 + CI 全绿」而不是只靠静态检查。

### 2.2 ⚠️ 关键判读：**189 处静默默认值，实测几乎全部无害**

对 v3 全池做数据完整性核查（**5,667 只 / 11,078,232 行**）：

| 字段 | 缺失 | 为 0 |
|------|-----:|-----:|
| `date` / `close` / `open` / `high` / `low` | **0** | 0 |
| `volume` / `amount` | **0** | **24 行（0.0002%）** |
| `turnover` / `limit_ratio` / `is_st` | **0** | 0 |

**→ 数据是完整的，所以 `x.get(k) or 0` 在实践中几乎从不触发。**

**这条结论很重要**：它说明**「静默默认值的数量」与「静默失效的风险」不是一回事**。
危险的静默失效来自**契约断裂**（列有值但代码不读、守卫条件恒假、字段被中间层丢弃），
**而契约断裂没有任何 linter 能发现** —— 只能靠**针对性契约断言**（本项目已加 3 组）。

**风险分级建议**：

| 级别 | 对象 | 处置 |
|------|------|------|
| **高** | 核心模块（factors/risk/pit/ashare，**25 处**）的 `or 0` | 逐个复核；对**会影响数值**的（如 `amount or 0` → 除零/因子失真）加显式缺失处理 |
| 中 | ③ 类 38 处未标注 `Optional` | 补标注（mypy 会强制调用方处理 `None`） |
| 低 | 脚本 / 展示层的 `or 0`（71 + 49 处） | 保持现状，但**不得**在核心路径复用 |

### 2.3 ⚠️ 一处**我起初误判**的高风险点（已核实并撤回）

我最初把 `factors/factor_ic_lab.py:93-94` 标为「高杠杆点」：

```python
amts = [float(b.get("amount") or 0) for b in win]
```

**核实后：该代码已经正确处理，我的标记是错的。** 完整逻辑是：

```python
amts = [float(b.get("amount") or 0) for b in win]          # ← 类型转换兜底，非静默默认
f["log_amount_20"] = math.log(avg_amt) if avg_amt > 0 else float("nan")   # 显式 NaN
amihud = [abs(rets[k]) / amts[k+1] for k in range(len(rets)) if amts[k+1] > 0]  # 显式除零保护
f["vol_ratio"] = (v5 / v20) if v20 > 0 else float("nan")
...
if any(not math.isfinite(v) for v in f.values()): return None   # NaN → 整体返回 None
```

**三处显式保护齐全**（`avg_amt > 0` / `amts[k+1] > 0` / `v20 > 0`），
且末尾用 `isfinite` 把 NaN **统一转成 `None`** —— 这是**教科书式的"缺失即缺失"实现**。

**教训（与 2026-09-26 撤回「创业板 ST 缺口」同一类）**：
**不要未核实就下结论**。我这次只看到 `or 0` 就判为风险，
没有读完整函数 —— 而 `or 0` 在这里是**类型转换兜底**，不是静默默认值。

> **对扫描器的启示**：`x.get(k) or 0` 的**语义取决于紧邻的后续处理**。
> 静态扫描只能**定位候选点**，判定必须读代码。本报告 §2 的 189 处同理 ——
> 数量多不等于风险高，**真正的判定只能逐处读**。

---

## 三、大文件体检：**不需要拆分**

| 项 | 数值 |
|------|------|
| 工作区总大小 | **22 MB** |
| Python 总行数 | **38,896 行** |
| 唯一 >1MB 文件 | `data/gbbq_events.csv`（**数据文件，合理**） |
| 最大 Python 模块 | `factors/factor_ic_lab.py` **739 行** |

**Top 5 模块**：`factor_ic_lab`(739) · `scripts/build_certified_dataset_v2`(552) ·
`scripts/run_five_factor_ab`(526) · `scripts/run_fundamental_factor_study`(518) ·
`reporting/report_generator`(501)

### 判读

1. **项目已有拆分约定**：`tests/test_module_splits.py` 与 `tests/test_package_layout.py`
   强制「包内模块清单」与「facade 再导出」，说明**历史上已经做过模块拆分**，
   且有守卫防止回退。
2. **脚本（`scripts/`）天然较长**（单文件一条研究流水线），**不建议拆** ——
   拆了反而破坏「一个脚本一次实验」的可追溯性。
3. **唯一候选**：`factors/factor_ic_lab.py`（739 行）内部有清晰分区：
   - 因子计算（`compute_factors` / `forward_return`）
   - 统计工具（`spearman` / `_t_pvalue` / `_winsorize`）
   - 面板构建（`build_panel` / `build_factor_panel` / `panel_ic_series`）
   - **正交化（~300 行，线性代数，自成一类）** ← 天然拆分点
   - IC 研究（`run_ic_study` / `quintile_returns`）

   **建议**：把正交化那 ~300 行拆到 `factors/orthogonalization.py`。
   但**优先级低** —— 739 行未到失控程度，而拆分会带来 import churn，
   且需同步更新 `test_package_layout.py` 的模块清单守卫。
   **结论：可拆可不拆，当前不构成问题。**

---

## 四、口径声明

- 数据完整性核查覆盖 v3 **全池 5,667 只 / 11,078,232 行**（非抽样）
- 静默扫描的「③ 未标注 Optional」用 AST 静态判定，**可能存在假阳性**（如函数体内嵌套函数的 `return None`）
- 「② 静默默认值」的 189 处含**展示层兜底**，已按目录分级，未逐条人工复核
- **本报告不构成投资建议**
