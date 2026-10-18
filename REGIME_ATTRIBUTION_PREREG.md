# 预注册：Regime 分层归因（只做尸检，不改交易逻辑）

> **建立**：2026-10-18　**状态**：已执行并判定（H0，见 `REGIME_ATTRIBUTION_VERDICT.md`）
> 写于 2026-10-18，**先注册后动手**（AGENTS.md §2.2）。
> 判定落 `REGIME_ATTRIBUTION_VERDICT.md`。

## 〇、三条必须先说清的前置事实（都有仓库证据）

### 1. 与既有 overlay 研究的关系——**这不是从零开始**

`scripts/run_regime_overlay_study.py` 已跑过两轮，产物在案：

| 产物 | 窗口 | baseline | overlay | Δ | 恒定敞口对照 |
|---|---|---|---|---|---|
| `reports/regime_overlay_study_w5.json` | 2025-07-01 | −31.21% | −19.89% | **+11.69pp** | — |
| `reports/regime_overlay_const05_pilot.json` | 2024-01-02 | −66.85% | −41.12% | **+20.56pp** | const05 −51.84%（overlay 优于它 +10.72pp） |

结论已登记在 `ALPHA_CAPABILITY_GAP_ANALYSIS.md:147`（P5）：
**3/5 窗口优于常数敞口（中位 +5.87pp），但平均敞口不等、非严格匹配对照 ⇒ 观察级、默认关闭**。

⇒ 所以「regime 接线」不是没做过，是**做过、且因对照不严而保持观察级**。
**本轮不重做 overlay**（那会重复劳动），只做**归因**：

| | 问的问题 | 是否改仓位 |
|---|---|---|
| 既有 overlay | 减仓能不能少亏？ | 改 |
| 本立项 | 亏是均匀分布，还是集中在某类行情？ | **不改** |

前者已答（能少亏，但那不是 alpha）；后者没答过。

### 2. `market_regime.py` 的离线静默失效——**已修，本轮不重复修**

2026-09-30 已改为**显式降级**（`degraded=True` + `available_indices`），
`tests/test_market_regime_offline.py` **8 项全绿**，
`scripts/scan_silent_failures.py` 的 `KNOWN_GUARD_RISKS` 也已登记为
`"status": "已修（单指数降级 + degraded 标记）"`。

> ⚠️ 我在 2026-10-18 20:0x 的核对中把这一条当成「现存 bug」报告，是**读扫描器
> docstring 第一段就当现状**造成的错误——那段列的是**历史实例**。已更正。

### 3. `run_tdx_rolling_eval.py` **没有逐笔数据**——这是草稿的硬伤

该脚本（297 行）是向量化按月调仓，产物 `rec` 只有窗口级汇总
（`trades` 是**笔数**，不是交易明细）。所以「给每笔交易打 regime 标签」
**无法照草稿实现**。

但——`portfolio_backtest` 的返回值里**本来就有** `trade_log` 与 `equity_curve`
（见 `portfolio_backtest.py:189`），只是 `run_tdx_rolling_eval.py` 没把它们写进 JSON。
⇒ 这决定了本立项的**唯一代码改动**：加两个键，**不碰任何计算**。

## 一、目标与非目标

**目标**：在**与「六窗口全负超额」完全同源**的产物上，把日收益与交易按 regime 切片，
回答「负超额是均匀分布，还是集中在某类行情」。

**非目标**（写成硬约束，违反即实验作废）：

- 不实现 regime 过滤、不调仓位、不改选股/交易参数；
- 不新造 regime 阈值（复用 `regime/adx_router.py` 默认值）；
- 不覆盖任何归档产物；
- 不把本轮结果表述为「regime 有效」或「策略有救」。

## 二、对象与数据（事前固定）

| 项 | 值 |
|---|---|
| 数据集 | `D:/tdx_dataset_v3`（与 `v3_rolling_eval_ew_full.json` 同源） |
| `max_stocks` / `min_periods` / `min_rows_asset` | 1000 / 252 / 504（同归档） |
| 窗口 | `2023-01-03, 2023-07-03, 2024-01-02, 2024-07-01, 2025-01-02, 2025-07-01` |
| 组合构造 | `portfolio_backtest(threshold=70, top_n=5, horizon=5)`（**不改**） |
| regime 数据源 | 数据集基准 `000300` 日线（与 overlay 研究同口径） |
| regime 规则 | `RegimeRouter` 默认：ADX(14)，`oscillation_lt=20`、`trending_ge=25`，`confirm_days=1`，三档「震荡/萌芽/明确」（**不调参**） |

## 三、唯一允许的代码改动：日志补丁

1. `scripts/run_tdx_rolling_eval.py` 的 `rec` 增加 `equity_curve` 与 `trade_log`
   （两者均由 `portfolio_backtest` 返回，本改动**只写不读、不参与任何计算**）。
2. 输出到**新路径** `D:/_ext_verify/regime_attr/rolling_eval_v3_logged.json`；
   **不覆盖** `reports/v3_rolling_eval_ew_full.json`。
3. **数值不变守卫**（本立项最重要的一条）：重跑后 6 个窗口的
   `total_return_pct` / `max_drawdown_pct` / `trades` / `win_rate_pct` /
   `annualized_excess` / `aligned` **必须与归档产物逐位相同**。
   任一不同 ⇒ 判定「补丁改变了行为」，**实验作废**，不得解释差异。

### 三.0 事前补充（2026-10-18 动手前核定，**不是**事后追加）

> 下面五条是落笔前只读核对的结果。凡与原 §三 冲突的，以本节为准；
> 全部已同步进 §九 偏离登记（标注「动手前」）。

**A. 引擎**已有成本与一字板处理，但**买入侧拒单不留痕**。

`portfolio_backtest.py` 第 58 行 `costs=costs or Costs()`、第 93/149 行 `_trade_cost`、
第 88/129 行滑点 → **不是**零成本；第 87 行遇一字跌停**卖出顺延**（`exit_deferred`）、
第 128 行遇一字涨停**放弃买入**。⇒ Critic 担心的「跌停买不进」在卖出侧已被处理，
但第 128 行 `continue` **不记录原因**，事后无法统计「有多少信号被涨停挡掉」。
故增加 **纯计数**（理由记入 §九）：

- 统计键 `execution_stats.rejects = {limit_up, shares_zero, cash_short, no_cash, exit_deferred_days}`
  与明细 `execution_stats.limit_up_skips`（`date/code/score`，上限 5000 条）；
- **不改变任何分支条件与执行顺序**，只累加整数 ← 这条是守卫的语义边界。

**B. 归档产物无法用当前脚本原样复现** —— 守卫基线须换口径。

`reports/v3_rolling_eval_ew_full.json` 的 `args` 含 `ew_benchmark: true` 与
`ew_series: reports/ew_benchmark_v3.json`，而 `scripts/run_tdx_rolling_eval.py`
**没有**这两个参数（`--ew-series` 在回退点 `c14d8c9` 一并被移除）。

⇒ 复现命令改用**默认基准（`<dataset>/benchmark.csv` = 沪深300）**，守卫只比归档中
**非 `ew_` 前缀**那一组字段（归档里同时存在两套基准：`annualized_excess` = 沪深300，
`ew_annualized_excess` = 等权）。`ew_*` 组**不参与守卫**，也不作为本立项的结论口径。

**C. `D:/tdx_dataset_v3/benchmark_ew.csv` 现已存在**（2026-10-17 06:16 建，1,240 行，
由 `ew_benchmark_v3.json` 的日收益回填为基期 100 的指数）。

与 `BENCHMARK_ALIGNMENT.md:35`「v3 `benchmark_ew.csv` ❌ **不存在**」**矛盾** ⇒ 该文档
过期。本条只登记为文档缺陷（§九），**不在本立项修**（避免与归因混在一起）。

**D. regime 数据源文件事前钉死**：`D:/tdx_dataset_v3/benchmark.csv`
（`code:000300`，1,240 行，2021-08-02 ~ 2026-09-10）。**不用** `benchmark_ew.csv`
做 regime 判定（与既有 overlay 研究同口径；换基准须另立预注册）。

**E. 取标签时 `RegimeRouter` 必须 `enabled=True`，但路由结果只读不接线。**

`RegimeRouter.decide` 在 `enabled=False` 时直接返回 `source="disabled"`、`regime=""`，
**取不到档位**。故标签侧用 `RegimeRouter({"enabled": True}, index_bars=000300)`，
**硬约束：`make_position_scaler()` 绝不传入 `portfolio_backtest`** ——
违反即「改了仓位」，与 §一 非目标冲突，实验作废。

### 三.1 守卫基线更换（2026-10-18，**动手后如实留痕**）

§三.3 原定「与 `reports/v3_rolling_eval_ew_full.json` 逐位相同」。**该守卫第一次就红了**，
如实记录：

| 字段 | 归档（09-20） | 本次实跑 | 差 |
|---|---|---|---|
| `aligned` | 293 | 293 | ✅ |
| `assets` | 971 | 971 | ✅ |
| `trades` | 295 | 295 | ✅ |
| `win_rate_pct` | 40.00 | 42.03 | ❌ |
| `total_return_pct` | −31.486 | **−5.552** | ❌ 26pp |
| `max_drawdown_pct` | 41.275 | 23.196 | ❌ |

**红的原因不是补丁，是基线选错了。** 证据两条：

1. `COST_BASELINE_PENDING_RECOMPUTE.md:88` 把该归档登记为 **⏳ 待重算**：
   09-20 之后代码基线演进（候选池修复 `0a81a5f` 等），归档与新基线**不同源**。
   同一文档 §八 记载其重算已于 **2026-10-18 00:30:56** 完成。
2. 拿重算产物 `reports/_recalc/v3_rolling_eval_ew_full_2025-07-01.json` 对照，
   本次实跑 **5 个策略侧字段逐位相同**（−5.552 / 23.196 / 295 / 42.03 / 293）。

⇒ **守卫的参照物换为 `reports/_recalc/v3_rolling_eval_ew_full_<窗口>.json`**
（2026-10-17/18 生成，与当前代码基线同源）。更换**不降低严格度**：

- 原守卫的对象是一份**已知过时**的产物，红或绿都不说明补丁有没有改行为；
- 新守卫的对象与当前基线同源，逐位相同才有意义。

**同时补一条更强的检查**：重算产物用 `--benchmark benchmark_ew.csv`，
本次用默认 `benchmark.csv`（§三.0-B），故 `annualized_excess` 不可直接对账
⇒ 改用「从本次的 `equity_curve` + 等权序列自行复算超额，与重算产物的
`annualized_excess` 对账」来验证超额计算链路，误差要求 ≤1e-6
（两序列来源不同：JSON 全精度 vs CSV 六位小数，日收益最大差 1.04e-8）。

> ⚠️ 结论层面必须先说清：**「六窗口全负超额」这一 09-20 headline 的绝对值已经过时**。
> 本轮归因一律基于**当前基线**的实跑数值，并同时给出归档值供对照，
> **不得**把两者混着引用。

## 四、归因口径（事前固定）

### 4.1 主口径：日频归因（主证据）

`equity_curve` → 日收益序列 → 按**当日** regime 标签聚合：
每档的日均收益、日波动、t 值、以及年化贡献分解
（`Σ该档日收益 / 总交易日数 × 252`，用于回答「亏损来自哪几档」）。

> **订正（2026-10-18，看分层结果之前）**：上式原写 `× 242`，系笔误。
> 项目统一算术年化口径是 **252**（`alpha.alpha_survival_lab.annualized_excess_arithmetic`
> 的默认值）⇒ 改为 252，避免出现两套年化口径。

### 4.2 交易口径：按**入场日** regime 分组

每笔交易按其 `entry_date` 前一日（信号日 T，标签用 T 日收盘可得数据）的 regime 分组，
输出：笔数、胜率、平均单笔收益（bps）、平均持有天数。

### 4.3 敏感性：按**出场日** regime 分组

若与 4.2 结论不同（持有期跨越 regime），**两套都要报**，不许择一。

## 五、判据（事前固定）

### 5.0 释义（2026-10-18 动手前固定，写于看到任何分层结果之前）

上面四条判据里有三处必须给出可复算的算式，否则「同一条判据」在两次执行里可以
得出不同结论。以下为**事前**锁定：

1. **G-3 的「有效观测」**：`n_eff = floor(n_days / horizon)`，`horizon=5`，
   按**单个窗口内该档的交易日数**算。窗口上界 = `floor(aligned/5)`
   （最长窗口 894 日 → **179**；最短 293 日 → 58）。
   ⇒ 只有某档占据该窗口 **≥56%** 交易日才可能达到 100。**这是有意从严**：
   H1 若要成立，必须在大样本上成立，而不是靠重叠观测把 n 撑大。
   产物里 `gates.G3_max_possible` 直接给出每窗口的上界，供读者判断「是否本来就无法达标」。
2. **G-4 必须**按窗口**闭环**：BH 在**每个窗口内**对该窗口的 6 个 p 值
   （3 档 × 2 基准）分别做；`H1 = 存在 (档位, 窗口) 使 G-1∧G-2∧G-3∧G-4 在该窗口内
   同时成立`。
   ❌ 禁止「用 A 窗满足 G-2、用 B 窗满足 G-4」的拼接式证明——那不是预注册的假设族，
   而是事后挑窗口。
3. **主判定口径 = 沪深300**（§三.0-B 已定），等权（`ew`）口径**同时报出**但只作稳健性。

**H1 成立需同时满足**（缺一即判 H0）：

| 编号 | 判据 |
|---|---|
| G-1 | 某档实测日均超额 > 0（4.1 与 4.2 **同号**） |
| G-2 | 该档 **block bootstrap** 95% CI 下界 > 0（block=5 日，因 `horizon=5`；1000 次；种子 `20261018`） |
| G-3 | 该档**去重后**的有效观测 ≥ 100 个交易日（`top_n=5, horizon=5` ⇒ 日收益高度重叠，**原始天数不是有效样本**） |
| G-4 | 多重检验：3 档 × 2 基准（沪深300 / 等权）= 6 个假设，BH `q < 0.10` |

**H0（预期更可能）**：各档均无显著正超额，或全负 ⇒ 负超额**均匀分布**，
regime 不是解释变量。

> 为什么预期 H0：主结论已经是毛口径全负；既有 overlay 只证明了「减仓少亏」，
> 那是**风险缩放**而不是收益来源。归因很可能只是把同一个负数切成三段。

## 六、禁止项

1. **禁止**看过分层结果后修改 regime 阈值、窗口划分或分组口径。
2. **禁止**用 SPA 做「同一策略跨 regime 均值比较」——SPA 的 H0 是
   「k 个策略都不优于基准」，不是「均值相等」；套用会得到无意义的 p 值。
   若确需 SPA，须单独立项并说明构造。
3. **禁止**把「少亏」写成「有效」，把「不显著」写成「无效」。
4. **禁止**覆盖 `reports/` 下的归档产物（本立项输出一律落 `D:/_ext_verify/`）。
5. **禁止**为让结果好看而删窗口、删股票或改 `min_periods`。

## 七、失败/成功预案

- **H1 成立**：结论仅到「某档下超额为正且显著」为止。
  「过滤震荡市」是**另一个实验**（要含样本外验证），须另立预注册，本轮不实现。
- **H0 成立**：宣告「regime 不是解释变量」，**不再在现有因子族上做参数调优**；
  方向转向新维度因子（资金流/文本等），另立项。

## 八、验收合并判据

1. G-1~G-4 全部可复算（判定文档给出每个数字的出处与命令）；
2. 日志补丁的**数值不变守卫**通过（逐位相同），否则实验作废；
3. 全量测试 rc=0；`ruff check .` / `mypy . --config-file mypy.ini` 全绿；
4. 反向验证：植入「按出场日标签替换入场日标签」⇒ 主口径必须变化（证明标签真的生效，
   不是摆设）；植入「补丁顺手改了 horizon」⇒ 数值不变守卫必须红；
5. 判定写入 `REGIME_ATTRIBUTION_VERDICT.md`，必须含「没证明什么」。

## 偏离登记

| 项目 | 预注册值 | 实际值 | 理由 | 影响 |
|---|---|---|---|---|
| 代码改动范围 | 唯一改动 = `run_tdx_rolling_eval.py` 的 `rec` 加两键 | 另加 `portfolio_backtest.py` **纯计数**（`execution_stats`） | **动手前**核定：第 128 行拒单不留痕，Critic 要求的失败单统计无从做起（§三.0-A） | 无。不改分支条件；受数值不变守卫覆盖，守卫红即作废 |
| 数值不变守卫的基线口径 | 与归档 6 窗口 **全部字段**逐位相同 | 只比归档中**非 `ew_`** 一组（沪深300 口径） | **动手前**核定：归档由已移除的 `--ew-series` 版本产出（§三.0-B），当前脚本无法原样复现 | 等权口径（`ew_annualized_excess`）不在守卫内，也不作结论口径；结论一律用沪深300 |
| regime 数据源 | 「数据集基准 `000300` 日线」 | `D:/tdx_dataset_v3/benchmark.csv`（1,240 行，2021-08-02~2026-09-10） | **动手前**钉死为具体文件（§三.0-D） | 无 |
| 数值不变守卫的**参照物** | `reports/v3_rolling_eval_ew_full.json` | `reports/_recalc/v3_rolling_eval_ew_full_<窗口>.json` | 归档守卫**第一次就红**（−31.486 → −5.552）；查明归档已登记「⏳ 待重算」，与当前基线**不同源**；重算产物与本次实跑 5 字段逐位相同 | 归档绝对值作废，不作结论口径；更换后**更严**（参照物与当前基线同源）。详见 §三.1 |
| 取 regime 标签的实现 | `RegimeRouter({"enabled": True})` + `decide()` | `compute_adx_by_date` + `classify_regime`（同一模块的两个纯函数） | 让「只取标签、不产生仓位系数」在**代码结构上**不可能越界（`decide` 同时返回 `position_ratio`，留着就有被误接线的可能） | 无。已证逐日等价：真实基准 **1,213 个 ADX 可用日全部一致**，守卫 `tests/test_regime_attribution.py::test_pure_function_labels_equal_router_decisions` |
| 年化折算乘数 | 242（§4.1 初稿） | **252** | 笔误；项目统一算术年化口径是 252（`annualized_excess_arithmetic` 默认值） | 仅影响 `ann_contrib` 的绝对值，不影响任何判据（G-1~G-4 都不看它） |
| 代码改动范围（第二次修订） | 上一行「另加 `portfolio_backtest` 纯计数」 | 再加：新增 `scripts/regime_attribution.py`、`_resolve_bench_meta()`（修**缺陷 #20**）、`--flush-each-window` | `portfolio_backtest` 无 `equity_curve`→归因无法做，须有分析脚本；默认基准元数据路径拼错导致**默认参数跑不起来**（§三.0 前置发现） | 分析脚本不改任何交易逻辑（只读产物）；缺陷 #20 只改审计预检路径。守卫：`tests/test_bench_meta_resolution.py`、`tests/test_regime_attribution.py`、`tests/test_execution_rejects.py` |
| 判据 G-3 的可达性 | 「≥100 个有效观测，从严但可达」 | 18 格实测 `n_eff` 全部落在 16~71；窗口上界最大 178，要通过需单档占窗口 ≥56%，实测最大占比 50.2%（且出现在上界仅 82 的短窗口） | §5.0-1 的算式在真实 ADX 三档分布下**不可满足**；算式本身未在看结果后改动 | **H1 在本设计下不可能成立**；H0 只能读作「未能在足够功效下建立」，不能读作「已否证 regime」。详见 VERDICT §四.1 |
| 执行约束的影响 | Critic 预期「跌停/涨停买不进会让危机期亏损被低估」 | 3,560 笔建仓中仅 **3 笔**被一字涨停拒单（0.08%）；跌停卖出顺延共 **6** 个持仓日；3 笔情景 5 日收益 −12.42%/−10.00%/−10.00%，合计 **−8.10pp** | 引擎侧本就处理（`portfolio_backtest.py:87` 卖出顺延、`:128` 买入放弃），而该策略的候选极少落在一字板 | 该风险在本引擎/本参数下**不成立**；不得再用「执行约束」解释负超额。详见 VERDICT §六 |
