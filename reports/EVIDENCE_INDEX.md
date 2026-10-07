# 研究证据索引（reports/*.json）

> **为什么有这个文件**（2026-10-02 独立审计发现）
>
> `.gitignore` 曾忽略整个 `reports/`，导致 2026-09-19 之后**全部实验的原始
> JSON 从未入库**。文档里每个收益率、Δ、命中率都因此无法复核——负面结果
> 尤其如此，而「负面结果必须归档」是本项目一半以上的资产。
>
> 现已放行 `reports/*.json`（研究证据），继续忽略 `reports/daily/`
> （每日报告、tracking 回填、run.log 等可再生产物）。
>
> **纪律提醒**：VERDICT / REPORT 里的每个数字都应能在此表找到对应 JSON。
> 找不到的，说明该结论没有证据支撑，不得引用。

---

## 一、窗口 A/B 对照类（`windows[]` + `prereg` 双字段）

这批文件的每个窗口对象都带 `prereg` 字段指回预注册文档，是「预注册先行」
纪律的**物理留痕**。字段 `delta_excess_pp` 为两臂超额差（负 = B 臂更差）。

### 1. 五因子主检验 —— 判定「无 Alpha」
| 文件 | 窗口数 | 对照臂 | 预注册 |
|---|---|---|---|
| `five_factor_ab_main.json` | 3 | `A_baseline` vs `B_fivefactor` | `FIVE_FACTOR_PREREG.md` |
| `five_factor_ab_smoke.json` | 1 | 同上（冒烟） | 同上 |
| `five_factor_ab_smoke2.json` | 2 | 同上（冒烟） | 同上 |
| `f4_p1/p2/p3.json` | 2/2/1 | `A_baseline` vs `B_fivefactor` vs `B_subset` | 同上 |
| `f4_smoke.json` | 1 | 同上（冒烟） | 同上 |

对应结论：`STEP1_3_EXECUTION_REPORT.md` §4、§18（H-F4）

### 2. 组合层 V1 / V2 —— V2 有效，V1 无效
| 文件 | 窗口数 | 对照臂 |
|---|---|---|
| `v2_p1/p2/p3.json` | 2/2/1 | `A_baseline` vs `A_plus_V1` vs `A_plus_V1_V2` |
| `v2_c20_v1_p1.json` | 2 | `A_baseline` vs `A_plus_V1` |
| `v2_c20_v1_p2.json` | 3 | 同上 |

对应结论：`STEP1_3_EXECUTION_REPORT.md` §二十三（登记见 `FACTOR_SUBSET_PREREG.md`）

### 3. N3 信号日涨停过滤 —— 判定**冗余**（5/5 窗口 Δ 全为 +0.00pp）
| 文件 | 窗口数 | 臂 |
|---|---|---|
| `ab_n3_batchA.json` | 2（2023-07-03、2024-01-02） | `A_plus_V1_V2` vs `A_V1V2_N3_nolimitup` |
| `ab_n3_w3.json` | 1（2024-07-01） | 同上 |
| `ab_n3_w4.json` | 1（2025-01-02） | 同上 |
| `ab_n3_w5.json` | 1（2025-07-01） | 同上 |

⚠️ **已知缺口**：原计划的 `ab_n3_batchB.json`（2024-07-01 + 2025-01-02）
因后台进程静默死亡未落盘（见 `.workbuddy/memory/2026-10-01.md`），
改由 `w3/w4` 单独重跑补齐，结论未受影响。

### 4. 成本与换手（IMPACT / T1 / T1b）
| 文件 | 窗口数 | 备注 |
|---|---|---|
| `impact_p1.json` | 2 | ⚠️ 臂为 `A_baseline` vs `A_plus_V1`，**非**滑点模型对照 |
| `impact_p3.json` | 2 | ⚠️ 缺 2024-01-02 窗口 |
| `t1b_p1.json` / `t1b_p2.json` | 2 / 2 | ⚠️ 缺 `t1b_p3`（5 窗口结论只有 4 窗口落盘） |
| `tc_t1_p1/p2/p3.json` | 2/2/1 | — |
| `tc_t2_p1.json` | 2 | — |
| `cost_model_check.json` | 2 | 成本模型切换检查 |

⚠️ **`STEP1_3_EXECUTION_REPORT.md:407-413` 的 H-IMPACT 结论表
（5 窗口 Δ+0.70~0.85pp）在仓库中找不到对应数据源**——现有
`impact_p*.json` 是 V1 对照臂，不是「阶梯滑点 vs sqrt 冲击」。
该表已降级为 ⚠️ 待核，见审计报告发现 2。

### 5. 假设证伪与其他
| 文件 | 内容 |
|---|---|
| `neu_p2/p3.json` | 中性反转 `N_neutral_reversal` |
| `ss_p1/p2.json`、`ss_smoke.json` | 风格切换 `SS_style_switch` + 证伪臂 `SS_inv_falsify` |
| `rs_main.json`（4 窗）、`rs_smoke.json` | 制度切换 `RS_regime_switch` |
| `ss_smoke.json` / `rs_smoke.json` | 冒烟 |

---

## 二、因子与 IC 诊断类

| 文件 | 字段 / 含义 | 对应结论 |
|---|---|---|
| `ic_diagnosis.json` | `ic` / `abs_ic_decay_L1M1` 逐 horizon | `STEP1_3_EXECUTION_REPORT.md` §二十（IC 虚高诊断） |
| `ic_diag_smoke.json` | 同上（冒烟） | — |
| `decay_h1/h5/h10/h20/h60.json` | `flagged_share` 五档 | §二十四（IC 衰减，登记见 `IC_DECAY_PREREG.md`） |
| `tdx_ic_full.json` / `tdx_ic_800.json` / `tdx_ic_smoke.json` | TDX 原生 IC | — |
| `v2_factor_correlation.json` | `avg_cross_sectional_*` | §二十三 |
| `v2_factor_study.json` | `full` / `quintiles` / `subperiods` | §二十三 |

---

## 三、基准口径类（★ 口径修正的关键证据）

| 文件 | 说明 |
|---|---|
| `v2_ew_bench_20230103.json` | 等权全A基准，1 窗 |
| `v2_ew_bench_part1.json` | 等权全A基准，2 窗 |
| `v2_ew_bench_part2.json` | 等权全A基准，3 窗 |
| `v2_rolling_eval_w6.json` | 滚动评估，带 `p_value` / `ci_lower` / `ci_upper` / `t_stat` |

这批文件字段最完整（含 `statistical_verdict` / `alpha_status` / `max_drawdown_pct`），
是**唯一带显著性检验**的一类结果。

> ⚠️ **但注意**：`STEP1_3_EXECUTION_REPORT.md` §1~§二十一 的组合层结论
> 基于 v1/v2 认证基准（沪深300 / 指数口径），§二十二 起才是等权全A。
> **跨口径的收益数字不可直接比较。**

---

## 四、诊断与形态评估类

| 文件 | 内容 | 对应结论 |
|---|---|---|
| `form_screen_eval.json` | `n_sections_used` / `corr` / `trigger_rate` | `FORM_SCREEN_VERDICT.md`（Sequoia-X 六策略） |
| `form_screen_eval.md` | 同上的可读版 | 同上 |
| `newstock_pref_diag.json` | `n_sections` / `pool_new` / `top_new` | `CANDIDATE_FILTERS_VERDICT.md`（N1 次新股） |
| `adx_attr_w1~w4.json` | `regime_day_counts` / `const05` | 制度状态归因 |
| `regime_overlay_const05_pilot.json` | `overlay` / `excess_delta_pp` | — |
| `regime_overlay_study_w5.json` | 同上 | — |

⚠️ `FORM_SCREEN_VERDICT.md:75` 的「61.1%（1,072 次触发）」在
`form_screen_eval.json` 中**无对应字段**，属未落盘数字，已标注待核。

---

## 五、推荐系统冒烟产物（`tdx_native/` 冒烟测试）

| 文件 | 说明 |
|---|---|
| `tdx_native_screen.json` | 原生筛选冒烟（不复权） |
| `tdx_native_screen_adj.json` | 原生筛选冒烟（前复权） |
| `daily_screen_2026-09-19.json` | 每日筛选冒烟 |

## 五之二、外部项目 V3 交叉验证（2026-10-06 新增）

**背景**：外部项目 `Phase144 v3_TDX_10W_PaperPortfolio` 用**完全独立的代码路径**
实现了同一套五因子。归档于 `docs/external/phase144_v3/`，调研报告见
[`EXTERNAL_REVIEW_2026_10_06.md`](../EXTERNAL_REVIEW_2026_10_06.md)。

| 文件 | 说明 |
|---|---|
| `external_v3/run_report.json` | V3 自报结果：总收益 +20.30%、回撤 36.74%、Sharpe 0.2785 |
| `external_v3/run_report.txt` | 同上简版 |
| `external_v3/v3_signals.csv` | V3 全部 61 个信号日的 Top20（1,220 条） |
| `external_v3/crosscheck_20260911.json` | **同日交叉验证**：本项目 vs V3 的 Top20 对比 |

**关键结论（主审独立复算，非引用）**：

1. **V3 复算一致** —— 用 `daily_nav.csv`（1,253 点）独立复算
   最大回撤 −36.74%、Sharpe 0.2785、总收益 20.30%，**与 V3 报告完全吻合**
   → V3 的实现没有算错。

2. **因子方向被独立验证** —— V3 的 `factor_direction` 与本项目
   `five_factor.py:23` 的 `DIRECTIONS` **逐项一致**。
   同日（20260911）同数据同方向，两条独立路径 Top20 **重合 17/20 = 85%**
   （候选池同为 3,124 只）。差异 3 只已定位为**流动性均额窗口口径不同**，
   非数据污染、非方向分歧。

3. **⚠️ V3 的 +20.30% 不可作为业绩证据** —— 同期对照：
   等权全A +12.05%（用本项目 `_ew_ret` 口径实算）、上证指数 +10.91%。
   且 V3 **缺少**本项目已验证有效的两项改进（V1 尾部剔除 +4.27pp、
   V2 跳空过滤 +3.12pp）与前复权（V3 为 `RAW_TDX_UNADJUSTED`），
   数据集为全市场实时快照（**不含退市股**，与本项目 PIT universe 不同源）。
   **口径不同，不可与本项目结论混用。**

---

## 六、证据缺口清单（2026-10-02 审计，2026-10-06 / 10-07 增补）

以下结论**在仓库中找不到完整数据源**，引用时必须标注「⚠️ 待核」：

| 结论位置 | 缺失内容 |
|---|---|
| `STEP1_3_EXECUTION_REPORT.md:407-413` | H-IMPACT 5 窗口滑点模型对照（`impact_p*.json` 实为 V1 对照臂） |
| `STEP1_3_EXECUTION_REPORT.md:551-556` | T1b 第 5 窗口（`t1b_p3.json` 缺失） |
| `FORM_SCREEN_VERDICT.md:75` | 61.1% V1 尾部重叠（JSON 无此字段） |
| **`STEP1_3_EXECUTION_REPORT.md` §九 ~ §二十四（部分）** | **基准口径未逐节标注**（2026-10-06 新增，**根因已修，历史 JSON 待补**）。正文仅 §十/§十一/§十三/§十七/§十九/§二十五 明确写了「等权全A」，其余章节靠默认兜底。<br>**已修**：`run_five_factor_ab.py` / `run_tdx_rolling_eval.py` / `run_cost_model_check.py` / `run_regime_overlay_study.py` / `run_tail_exclusion_study.py` / `run_concentration_study.py` / `run_sampling_sensitivity_study.py` 共 7 个脚本已在落盘时记录**生效基准路径**（`"benchmark"` 字段）。<br>**仍缺**：修复前跑的 42 份 JSON 中只有 3 份（`v2_ew_bench_*.json`）能看出基准。**引用旧 JSON 里的数字时，基准只能推断，不能确认** |
| **`scripts/run_tdx_universe_ic.py:47` 的注释** | **声称「与 `five_factor.compute_factors` 逐字一致」，实测不成立**（2026-10-07 新增）。amihud 两处差异：① 取值分母 生产固定 `/20`、IC 用实际个数；② 样本门槛 生产 `≥20`、IC `≥15`。<br>**实测影响**：无停牌 **0.00%**（851 个信号日）；窗口内 1 天 `amount=0` 时 **0.26%**（合成夹具）。<br>**对本实验（Spearman IC）影响可忽略**（只看排序），但**该注释本身是错的**，会误导后续交叉比对。<br>处置见 [`CROSS_DECADE_PREREG.md`](../CROSS_DECADE_PREREG.md) §六（方案 A 统一口径 / 方案 B 标注差异） |
| `DAILY_OPERATION.md:112` | 指数 −2.13% / 等权 +3.06%（来自 3 行冒烟夹具，非真实数据） |
| `tdx_native/backfill.py:13` | 同上，已在该文件就地标注撤回 |

> **教训**：跑完实验必须落盘 JSON 并入库。「判定写进 md」只满足了一半，
> 数字的原始凭据缺失等于结论不可复核。
