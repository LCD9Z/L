# 成本口径待重算登记册（印花税分段缺陷 · 副本侧）

| 项 | 内容 |
|---|---|
| **建立** | 2026-10-14 18:4x　**建立方**：海外版 WorkBuddy（副本侧 `1.0 - 副本`） |
| **触发** | `backtest_engine._stamp_rate` 印花税分段失效（我方 10-14 `755212c` 独立发现；主干 10-13 `8b3cba8` 亦独立发现 → **双向印证**） |
| **处置口径** | **方案③**（双方 10-14 商定）：A2 合并取主干版代码（`_norm_date` + `tests/test_execution_stress.py`）→ **合并落定后统一重算** |
| **本册性质** | **只标注、不改任何数字**。在重算完成前，册内产物的超额/收益数字**不得作为有效结论引用** |
| **解除条件** | A2 合并 → 逐份重算 → 本册归档（见 §五） |

---

## 一、缺陷与影响条件（一句话）

`_stamp_rate` 用 `str(trade_date) >= str(change)` 比较：`change` 写作 `"2023-08-28"`（带横杠）、
而 K 线 `trade_date` 为 `"20230825"`（不带）→ `'-' < '0'` ⇒ 比较**恒真** ⇒
**2023-08-28 之前的卖出按新税率 0.5‰ 计（应为旧税率 1‰）** ⇒ **成本被低估（乐观方向偏差）**。

**影响条件（两条同时成立）**：
1. 产物由**成本类代码路径**产出（`backtest_engine` / `portfolio_backtest` 的成本计算链）；
2. 其**窗口跨过 `2023-08-28`**（即窗口起点早于该日）。

> **⚠️ 触发的必要形态（2026-10-17 补，裁定 D）**：上述「恒真」只在 `trade_date`
> 的字符串形式为**无横杠 `YYYYMMDD`**（如通达信原生 `.day` 的 `20230825`）时成立。
> **certified CSV 的 `date` 列带横杠**（`2023-08-25`），`str("2023-08-25") >= "2023-08-28"`
> = False ⇒ `_norm_date` 修复前后比较**均正确** ⇒ **不触发**。
> 实测现有全部数据通道（`walk_forward` / `portfolio_backtest` 的 `trade_date` 均取自
> `bar['date']`；`tdx_native/` 全目录不 import 任何成本链）**触发面 = 0**。
> 副本侧 7 个跨线窗口重算**逐位零差异**为其实证。

> ⚠️ 方向说明：修复后成本**升**、收益**降** ⇒「无 alpha」的结论**更稳、不翻转**。
> 即本缺陷不会把「有 alpha」误判成「无 alpha」，只会让「无 alpha」略偏乐观。

---

## 二、判定方法（可复现）

```bash
# 判据 A（成本类）：产物任意层级出现成本特征键
#   trades / costs / annualized_excess / max_drawdown_pct / total_return_pct
#   / A_baseline / net_return / turnover / win_rate_pct
# 判据 B（跨线）：产物内任意 YYYY-MM-DD 字符串的最小值 < 2023-08-28
#   （日期由递归扫描全部字符串字段收集；口径：reports/*.json 顶层、排除 `_` 前缀与 smoke）
```

**成本类脚本集合（16 个，import `backtest_engine`/`portfolio_backtest`）**：
`run_backtest` · `run_combo_study` · `run_concentration_study` · `run_contrarian_portfolio` ·
`run_cost_model_check` · `run_expert_filter_study` · `run_five_factor_ab` · `run_horizon_study` ·
`run_portfolio_backtest` · `run_regime_overlay_study` · `run_sampling_sensitivity_study` ·
`run_stop_loss_ab` · `run_tail_exclusion_study` · `run_tdx_rolling_eval` ·
`run_universe_replication` · `run_valuation_weight_ab`
（各脚本 `--out` 均为运行时指定，故**按产物内容判定**，不按脚本静态映射）

---

## 三、受影响产物

> **⚠️ A2 合并后的计数口径（2026-10-15 补记）**：本册 Tier A/B 是**我方侧**于 10-14
> 用「成本特征键」启发式人工分类的结果（18+1 份）。A2 合并后，合并树的**机器规范集**
> 由 `scripts/gen_evidence_index.py` 的 `stamp_duty_stale` 规则产出（判据 = 含
> `windows` 键 ∧ 窗口跨 2023-08-28）—— **24 份 = 主侧 12 + 副本侧 12**，
> 已由 `tests/test_evidence_index.py::test_stamp_duty_stale_is_expected_set_today`
> 锁定，并以 `⚠️ 待核` 标注写入 `reports/EVIDENCE_INDEX.md`。
> **两者判据不同、不矛盾**：机器规则按 `windows` 键机械判定，本册按成本代码链人工
> 细分（如 `cost_model_check.json` 用哨兵日期须特判）。重算时以**机器 24 份为工作
> 清单**，本册 §四 的引用规则对两者同等适用。

### 3.1 Tier A · 确认受影响（成本类 + 窗口跨线）—— **18 份**

| # | 产物 | 最早窗口 | 状态 |
|:--:|---|---|---|
| 1 | `reports/adx_attr_w1.json` | 2023-07-03 | ⏳ 待重算 |
| 2 | `reports/combo_study_h20.json` | 2023-07-03 | ⏳ 待重算 |
| 3 | `reports/combo_study_h20_fixed.json` | 2023-07-03 | ⏳ 待重算 |
| 4 | `reports/cost_model_check.json` | （哨兵 `0001-01-01`） | ⏳ 待重算（成本模型检查，**必然受影响**） |
| 5 | `reports/cost_model_check_with_p.json` | （哨兵 `0001-01-01`） | ⏳ 待重算 |
| 6 | `reports/five_factor_ab_v2.json` | 2023-07-03 | ⏳ 待重算 |
| 7 | `reports/horizon_study.json` | 2023-07-03 | ⏳ 待重算 |
| 8 | `reports/horizon_study_turnover_fixed.json` | 2023-07-03 | ⏳ 待重算 |
| 9 | `reports/impact_cost.json` | 2023-07-03 | ⏳ 待重算 |
| 10 | `reports/stop_loss_ab.json` | 2023-07-03 | ⏳ 待重算 |
| 11 | `reports/stop_loss_ab_5win.json` | 2023-07-03 | ⏳ 待重算 |
| 12 | `reports/tail_exclusion_with_p.json` | 2023-07-03 | ⏳ 待重算 |
| 13 | `reports/tc_t0.json` | 2023-07-03 | ⏳ 待重算 |
| 14 | `reports/tc_t2.json` | 2023-07-03 | ⏳ 待重算 |
| 15 | `reports/v2_rolling_eval_ew.json` | 2023-01-03 | ⏳ 待重算 |
| 16 | `reports/v3_rolling_eval_ew.json` | 2023-01-03 | ⏳ 待重算 |
| 17 | `reports/v3_rolling_eval_ew_full.json` | 2023-01-03 | ⏳ 待重算 |
| 18 | `reports/valuation_weight_ab.json` | 2023-07-03 | ⏳ 待重算 |

### 3.2 Tier B · ~~待核~~ → **已定性：不受影响**（2026-10-17）

| 产物 | 情况 | 处置 |
|---|---|---|
| `reports/contrarian_ab_with_p.json` | 含成本特征键，但**无任何 `YYYY-MM-DD` 字段**，也无 `args.dataset` | **已确认窗口**：`results` 键 = `2024-01-02~2026-09-30` / `2025-01-02~2026-09-30` ⇒ **两窗口起点均 ≥ 2023-08-28** ⇒ D1 不受影响、不重算 → **移入 §3.3**。⚠️ 但其生成链 `run_contrarian_portfolio._trade_return` 曾**不传 `trade_date`**（缺陷 #16，2026-10-17 已修）—— 因窗口全在线后，该缺陷对本产物数值**同样无影响**；修复不改变本产物 |

### 3.3 已排除（说明为何不列入）

| 类 | 份数 | 理由 |
|---|--:|---|
| 非成本类（对账 / IC / 审计 / 行业归因 / 退市研究） | 10+ | 不含成本计算链 ⇒ 印花税缺陷**不影响**（即便窗口跨线，如 `l3_reconciliation*`、`hd1~hd4`、`industry_ic_attribution*`、`v3_alpha_gap_probe*`） |
| 成本类但窗口全在 2023-08-28 之后 | 1 | 全部交易在新税率期 ⇒ 无偏差。**2026-10-17 新增**：`contrarian_ab_with_p.json`（窗口 `2024-01-02~` / `2025-01-02~`，见 §3.2） |
| `_` 前缀探针 / smoke 夹具 | — | 非结论性产物，规则内排除 |

---

## 四、引用规则（重算完成前）

1. 册内产物（Tier A）的**超额 / 年化 / 总收益**数字，**不得**作为有效结论引用；
2. 如需引用，须**同时**声明「成本口径待重算（乐观偏差，量级待定）」并指向本册；
3. **方向性结论**（如 `verdict: INCONCLUSIVE` / `ALPHA_NOT_ESTABLISHED`）**不受影响**
   ——偏差只会让「无 alpha」更稳，**不会翻转**；
4. 本册**不改变**任何产物文件（数字、mtime 均不动）。

---

## 五、解除条件与后续

| 步 | 动作 | 归属 |
|---|---|---|
| 1 | A2 合并：取主干版 `backtest_engine.py`（含 `_norm_date`）+ `tests/test_execution_stress.py` | A2 执行方 |
| 2 | 合并落定后逐份重算 Tier A（18 份）+ Tier B 定性 | 双方各自侧 |
| 3 | 重算后更新各产物 → 本册标注「已重算（日期/commit）」或归档 | 本册维护方 |
| 4 | Tier B 若确认不受影响 → 移入 §3.3 | 同上 |

**关联**：`P005_3_3_BENCHMARK_PREREG.md`（基准口径预注册，R2 生效时点机制）·
`HANDOVER.md` §5 已知缺陷第 5 条 · 当日日志第五节/第六节 ·
信箱 `02_回执/P011复核C1-C5落实+印花税方案三采纳_海外版_2026-10-14.md` §三。

**本册不构成投资建议。**

---

## 六、主侧 12 份验收记录（主干侧，2026-10-15 晚 · P013 口径）

**执行**：`scripts/run_recompute.py --side main --crossing-only`（`MAIN_TASKS`，
命令由主干逐份反推 args 确认，含 #11 `v2_ew_bench_part1` = `run_tdx_rolling_eval.py`）。
12/12 跨线窗口（每份 `2023-07-03`）全部成功、零失败；基线 commit `8db1c65`；
产物 `reports/_recalc/<name>_2023-07-03.json`（`_` 前缀不入库）。

**对账（`check_recompute.py`）**：V1 结构缺失 0；V2 差异 12/12 窗口；
V4 无结构异常。**V3 方向异常 6 份 14 处**（收益/超额**上升**，与「成本升⇒收益降」相反）：

| 产物 | 异常字段 | 幅度（原 → 重算） |
|---|---|---|
| `impact_p3` | A_baseline 总收益/年化超额 | -10.18% → -6.08% |
| `rs_main` | RS_regime_switch 总收益/年化超额 | +0.29% → +13.33% |
| `t1b_p1` | A_baseline + A_plus_V1 总收益/年化超额（4 处） | +6.63% → +28.12% |
| `tc_t1_p2` | A_baseline 总收益/年化超额 | -13.10% → -9.06% |
| `v2_ew_bench_part1` | 总收益/年化超额 | -43.75% → -26.45% |
| `v2_p1` | A_baseline 总收益/年化超额 | -13.10% → -9.06% |

**口径判定（P013）**：上升方向**不可能来自印花税修复**（该修复只升成本、降收益）
⇒ 差异源自 A2 合并的**代码基线演进**（与 §六验证跑 12pp 观察同源）。**不静默通过**：
6 份标「⚠️ V3 方向异常，基线演进成分未归因」，归因排查列 **07 篇 L9**。

**三分类标注（主侧 12 份统一适用）**：
- 跨线窗口（`2023-07-03`）：**已重算**（作 D1 影响量独立证据，**未并入**正式报告）；
- 非跨线窗口：D1 不受影响、**不重算**；主侧 12 份均为多窗口对照设计，
  其**跨窗口比较结论统一标注「基线混合，结论待定」**；
- 单窗口内结论（同臂同窗口新旧对照）可用，引用时须注明基线 commit。

---

**2026-10-17 补（裁定 G）**：经用户 10-16 指令，主侧 16 个**非跨线**窗口已补跑，
`MAIN_TASKS` 合计 **28/28 全完成、零失败**（基线 `8db1c65`）。示例：
`v2_p1@2024-01-02` A_baseline 总收益 **−13.662% → +50.300%**、年化超额 **−0.1834 → +0.0271**
（候选池修复的基线演进，合法）。主侧 12 份跨窗口比较口径已统一，
**「基线混合，结论待定」对主侧解除**。

---

## 七、V3 方向异常归因（L9 收口，2026-10-16）

**归因结论**：6 份产物收益**上升**的直接原因是 **A2 合并带入的代码基线演进**，
与印花税修复（只升成本、降收益）方向相反、相互独立。

**根因提交**（`f293d40`（主干 A2 前）→ `8db1c65`（重算基线）之间的关键演进）：

| # | 提交 | 文件 | 机制 | 对收益的影响方向 |
|:--:|---|---|---|---|
| 1 | **`0a81a5f`** | `real_alpha_pipeline.py` / `walk_forward.py` | **修复「换手率分项静默失效」**：`load_certified_csv` 白名单漏掉 `turnover` 字段 → `score_history` 换手率分项恒为 0 → 候选池过线率 **6.65% → 18.71%**（近 3 倍） | **大幅上升**（候选池扩大，策略从远窄于设计意图的池子选股） |
| 2 | `bfd4c52` | `portfolio_backtest.py` | 新增 `impact_stats`（sqrt 冲击成本必报 bps），默认关闭 | 中性（仅记录，不改计算） |
| 3 | `a3a7f88` | `portfolio_backtest.py` | 新增 ATR 止损（`stop_atr_k`）、`weight_func` 估值权重 | 默认关闭（`stop_atr_k=0`），中性 |
| 4 | `86956c8` | `scripts/run_five_factor_ab.py` | A2 合并：新增 `--min-listing-days` / `--exclude-limitup` / `--skip-legacy-arms` / `benchmark` 落盘字段 | 默认关闭，中性 |

**解释力验证**：
- `0a81a5f` 的量化影响（h=20 组合层）：C5_V0 基线 **-7.46% → +5.21%**（+12.67pp），
  C5_V2 仅尾部剔除 **+4.96% → +9.31%**（+4.35pp）；
- 与实测 V3 异常幅度吻合：`t1b_p1` +21.49pp（6.63→28.12）、`rs_main` +13.04pp、
  `tc_t1_p2`/`v2_p1` +4.05pp（-13.10→-9.06）；
- 共用 `A_baseline` 臂的产物（`tc_t1_p2` 与 `v2_p1`）数值变化完全一致
  （-13.103→-9.055），证实为同一代码路径的系统性漂移；
- 对照组 `ss_p1`：SS_style_switch 逐位不变（该臂不走 `score_history`），
  SS_inv_falsify 降 12pp（走 `score_history`，受候选池扩大影响）——
  **同一产物内两臂方向相反**，进一步锁定 `score_history` 候选池变化是根因。

**口径判定**：
- 收益上升**不是**印花税修复引入的偏差，而是**策略真实表现因候选池修复而改善**；
- 原产物（A2 前基线）的候选池**过窄**（6.65% 过线率），属于**已知缺陷状态**；
- 重算产物（`8db1c65` 基线）的候选池**恢复正常**（18.71% 过线率），数字更接近策略设计意图；
- 因此 **6 份跨窗口结论的「基线混合」标注解除**，但**跨窗口比较仍不可直接引用**
  （因非跨线窗口未重算，口径仍不一致）。

**处置**：
- 6 份产物标注更新为「**已重算（基线 `8db1c65`），收益上升含 `0a81a5f` 候选池修复成分**」；
- 07 篇 L9「6 份跨窗口结论冻结」**解除**，改为「**基线演进已归因，跨窗口比较待非跨线窗口重算后统一引用**」；
- 非跨线窗口（2024-01-02 / 2024-07-01 / 2025-01-02 等）是否补跑，由 P013 裁定 A/B 档时一并决定。

---

## 八、副本侧 15 份验收记录（主干侧，2026-10-17）

> **基准口径收口（2026-10-17 裁定 A / B）**：
> - `v2_rolling_eval_ew`：以 **`D:/tdx_dataset_v2/benchmark_ew.csv`（认证全A，strict、2,598 行）为权威**；
>   原产物脚本内现算 ew（35.34 / 37.53，400 只抽样池窄口径、覆盖率 26.8%）**废弃不引用**，
>   重算值（40.15 / 34.73）超额口径**有效**。
> - `v3_rolling_eval_ew` 与 `v3_rolling_eval_ew_full`：**自 2026-10-17 起基准等价**
>   （统一为全 PIT 认证序列 54.16 / 43.83）；旧 51.58 / 41.66 系抽样池窄口径，
>   **废弃不引用**。两者策略侧数值逐位相同，视为等价实验（不重跑）。

**执行**：`scripts/run_recompute.py --side copy --crossing-only`（`COPY_TASKS`，12 任务 / **15 跨线窗口**）。
**15/15 完成、零失败**（9 单窗任务 10-16 19:13–21:43；`rolling_eval` 6 窗口 10-17 06:25–08:04，经
「人工修正通道」还原参数后重跑）。对账：`scripts/check_recompute.py --verbose`。
回执：`_AI协作信箱/02_回执/成本口径重算副本侧15跨线窗口验收_主干_2026-10-17.md`。

| # | 标准 | 结果 |
|:--:|---|---|
| V1 | 结构可比 | ⚠️ **缺键 6**（3 个 `rolling_eval` 任务 × 2 窗口，缺 `ew_*` 系列）——原产物 `ew_benchmark: true` **现算** vs 重算 `--benchmark` 外部基准，属**字段口径替换**（非数据缺失） |
| V2 | 确实产生差异 | ⚠️ **8/15 命中**；7 窗口**逐位零差异**（`combo_study_h20_fixed` / `cost_model_check` / `five_factor_ab_v2` / `horizon_study_turnover_fixed` / `impact_cost` / `tc_t0` / `tc_t2`） |
| V3 | 方向（成本升⇒收益降） | ⚠️ **异常 15 处 / 8 窗口**（皆上升）：基准口径替换约 8 处 + A2 基线演进 7 处；**无一处来自印花税修复** |
| V4 | 无 NaN / 无缺失 arm | ✓ 关键字段 None/NaN 命中 0 |
| V5 | 登记册标注 | ✓ 本节 |

**⭐ 重大发现：缺陷未触发。** 修复前 `str(trade_date) >= str("2023-08-28")` **仅当**
`trade_date` 字符串**无横杠**（如 `20230825`）时恒真。本项目数据集 CSV 的 `date` 列**带横杠**
（实测 `D:/tdx_dataset_v2|v3/benchmark*.csv` 首行 `2021-08-02`；`load_certified_csv` 返回
`first=2021-08-02`），且两条成本链的 `trade_date` 均取自 **`bar['date']`**
（`walk_forward.py:76-77`、`portfolio_backtest.py:93,149`）⇒ 比较正确、**缺陷未触发**。
副本侧 7 窗口逐位零差异为其佐证。⇒ 两库产物差异**全部**为 A2 代码基线演进，
本缺陷属「**名义缺陷**」（代码错、数据格式恰好使比较正确）——§一「影响条件」表述待修订。
**建议专项复核**三条链的实际触发范围（含 `run_contrarian_portfolio.py` **不传** `trade_date` 的情形）。

**遗留（待裁定）**：
1. 基准口径疑点 A：`v2_rolling_eval_ew` 重算基准 40.15 ≠ 原 `ew` 现算 35.34；
2. 基准口径疑点 B：`v3_rolling_eval_ew` 与 `_full` 本是**两个实验**（原 ew 基准 51.58 vs 54.16），
   本次误用 `_full` 基准 → 该份口径失真；
3. V1 缺键处置：补回 `ew_*`（双基准）或改判定口径（单一认证基准）；
4. `check_recompute.py` 将 `benchmark_return_pct` 计入 `RETURN_KEYS` → 基准替换被误报为方向异常。

**三分类标注（副本侧 15 份统一适用）**：跨线窗口**已重算**（D1 独立证据，**未并入**正式报告）；
非跨线 37 窗口**不受影响/待决**（§8.3）；多窗口产物跨窗口结论**标「基线混合，结论待定」**。

---

## 九、终版对账与裁定（2026-10-17，任务A 口径拆分后）

**对账脚本**：`scripts/check_recompute.py`（本次按裁定 C/F 拆分口径）。

**终版汇总行（原样粘贴，命令：`python scripts/check_recompute.py`，执行侧：主干，日期：2026-10-17）**：

```text
汇总：V1 真实缺键 0 · CALIBER 口径替换 6 · 有差异窗口 36 · V3 未归因上升 0 · ATTRIBUTED 已归因上升 49 · 基准替换 6
```

**口径拆分说明**：
- **CALIBER**（`ew_*` 族 → 单一认证基准）：旧侧 `ew_aligned/ew_annualized_excess/ew_benchmark_return_pct/ew_ci_*/ew_p_value/ew_t_stat/ew_verdict/ew_statistical_verdict` 因改用 `--benchmark` 不再产出 ⇒ 记 CALIBER，**不计 V1 失败**；但仅当新侧**含外部基准字段**（`benchmark_return_pct`/`annualized_excess`）时才允许销项，否则仍计 V1（防滥用）。
- **ATTRIBUTED**（已归因 D2 基线演进）：白名单 = 主侧 12 + 副本侧 12（见 `check_recompute.ATTRIBUTED_TO_BASELINE`），其收益上升单列、**不计 V3**；**白名单外产物上升仍计 V3**（守卫保持有效）。
- **BENCHMARK**（`benchmark_return_pct`/`ew_benchmark_return_pct`）：只报告基准口径替换，**不计 V3**。

**裁定引用**：本轮全部裁定见信箱 `02_回执/成本口径重算副本侧15跨线窗口验收_主干_2026-10-17.md` §九 A–G（A v2 基准权威 / B v3 两实验等价 / C V1 缺键记 CALIBER / D 缺陷未触发 / E 新缺陷 #16 / F V3 判据拆分 / G 范围与状态）。

**`stamp_duty_stale` 机器规则（24 份清单）保留** —— 格式无关的**保守哨兵**：
现有数据通道触发面虽为 0，但未来原生 `.day`（无横杠 `YYYYMMDD`）接入成本链即会触发；
机器清单不因「当前未触发」而删减。

**本轮同时修复**：缺陷 **#16**（`run_contrarian_portfolio._trade_return` 不传 `trade_date`，
跨线卖出恒按 0.5‰）—— 见 `HANDOVER.md` §5.3 #16，守卫 `tests/test_contrarian_costs.py`（含反向验证）。

**本册不构成投资建议。**

---

## 十、P014 备注整改与 P013-④ 落实（2026-10-17）

**P014**（`03_已确认/P014成本重算裁定落实_验收确认_主干_2026-10-17.md`）验收通过，
三条不阻塞备注已全部关闭，另补落实悬空的 **P013-④ `_baseline`**。

| 项 | 结果 |
|---|---|
| ① CI 红灯（缺 `grep.exe`） | `tests/test_data_contracts_num.py` 改**纯 Python 扫描**（`_scan_local_num_defs`），新增 2 条反向验证；实测无 `grep` 的 PATH 下旧实现 `FileNotFoundError`、新实现 34 项全过 |
| ② 白名单换基线复核 | 新增 `ATTRIBUTED_BASELINE = {main: 8db1c65, copy: 2b9f97d, recorded_at: 2026-10-17}` + 2 条守卫（与任务表双向零漂移 / 基线时点可追溯） |
| ③ 文案与计数 | WIKI L9 旧措辞已改；**副本 `.partial` 实测全树 15 个**（`_recalc` 9 + `reports/` 根 6），§十 的「7」与 P014 的「9」均为较窄口径 |
| **P013-④ `_baseline`** | **已实现**：新产物由 `stamp_baseline()` 内嵌 `{commit, as_of, source}`（幂等）；已落 **43 份**用 `--baseline-index f8f020d` 生成旁挂索引 `reports/_recalc/_baseline_index.json`，**不重写产物字节/mtime**（聚合 md5 前后一致） |

**质量门**：`run_ci.py` 6/6 PASS；pytest **1,494 项、失败 0**。
**判据**：`_baseline` 只解决「哪份代码产出本产物」的可追溯性，**不改任何数字**，不影响 §九 终版对账结论。

**本册不构成投资建议。**
