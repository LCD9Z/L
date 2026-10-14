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

### 3.2 Tier B · 待核（成本类但**无日期字段**，无法静态判定）—— **1 份**

| 产物 | 情况 | 待核动作 |
|---|---|---|
| `reports/contrarian_ab_with_p.json` | 含成本特征键，但**无任何 `YYYY-MM-DD` 字段**，也无 `args.dataset`（`BENCHMARK_ALIGNMENT.md` §2.3 亦将其列为数据源待确认） | 重算任务第 1 步：查该产物的生成命令/日志确认窗口，再定是否入 Tier A |

### 3.3 已排除（说明为何不列入）

| 类 | 份数 | 理由 |
|---|--:|---|
| 非成本类（对账 / IC / 审计 / 行业归因 / 退市研究） | 10+ | 不含成本计算链 ⇒ 印花税缺陷**不影响**（即便窗口跨线，如 `l3_reconciliation*`、`hd1~hd4`、`industry_ic_attribution*`、`v3_alpha_gap_probe*`） |
| 成本类但窗口全在 2023-08-28 之后 | — | 全部交易在新税率期 ⇒ 无偏差（本次扫描未发现此类，因成本类产物默认窗口集多含 2023-07-03） |
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
