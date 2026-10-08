# BENCHMARK_ALIGNMENT.md · 主干侧基准代次对照表

> **建立**：2026-10-08 19:13　**建立方**：国内版（主干侧）
> **依据**：P005 §3.2（字段采用副本 8 列方案）+ §3.4（不可确认者**标注**，**不回填**）
> **姊妹文件**：副本 `BENCHMARK_ALIGNMENT.md`（字段对齐，便于横向比对）

---

## §〇 字段定义

| 字段 | 含义 |
|---|---|
| 产物路径 | 相对项目根的文件路径 |
| 数据源 | 使用的数据集目录 |
| 基准 | 沪深300 / 等权全A / 无 |
| 代次 | **旧**（沪深300）/ **新**（等权全A）/ — |
| 含退市股 | 数据侧是否含退市股（决定幸存者偏差敏感性） |
| **覆盖区间** | 基准文件实际覆盖的起止日期（副本新增维度，本表沿用） |
| 生成时间 | 产物的落盘时间 |
| **标注状态** | ✅已标注 / ⚠️推断 / ❌不可确认 |

---

## §一 数据集层

| 数据集 | 基准文件 | 基准 | code | 覆盖区间 | 行数 | 含退市股 |
|---|---|---|---|---|---|---|
| `D:/tdx_dataset` | `benchmark.csv` | 沪深300 | `000300` | 2021-08-02 ~ 2026-09-10 | 1,240 | 是（180 只） |
| `D:/tdx_dataset_v2` | `benchmark.csv` | 沪深300 | `000300` | 2021-08-02 ~ 2026-09-10 | 1,240 | 是（239 只） |
| `D:/tdx_dataset_v2` | **`benchmark_ew.csv`** | **等权全A** | `EW_ALL` | **2016-01-05 ~ 2026-09-11** | **2,598** | — |
| `D:/tdx_dataset_v3` | `benchmark.csv` | 沪深300 | `000300` | 2021-08-02 ~ 2026-09-10 | 1,240 | 是（239 只） |
| `D:/tdx_dataset_v3` | `benchmark_ew.csv` | ❌ **不存在** | — | — | — | 副本侧有等价物 `reports/ew_benchmark_v3.json` |

> ⚠️ **覆盖区间错配（重要）**：项目实际使用的等权基准是 **1,240 根**那个（与沪深300 同区间），
> 而 `D:/tdx_dataset_v2/benchmark_ew.csv` 覆盖 **2,598 根（2016 起）**。
> 二者**区间不同**，直接对照存在错配风险。→ 这正是本表设「覆盖区间」列的原因。

---

## §二 产物层（`reports/*.json`，共 59 份）

### 2.1 ✅ 基准**可确认**（3 份）

| 产物 | `benchmark` 字段值 |
|---|---|
| `v2_ew_bench_20230103.json` | D:/tdx_dataset_v2/benchmark_ew.csv |
| `v2_ew_bench_part1.json` | D:/tdx_dataset_v2/benchmark_ew.csv |
| `v2_ew_bench_part2.json` | D:/tdx_dataset_v2/benchmark_ew.csv |

### 2.2 ⚠️ `benchmark` 为**空串** → **推断 = 沪深300**（31 份）

> **推断依据**：脚本 `--benchmark` 默认空串，运行时不显式传入则兜底到
> `<dataset>/benchmark.csv`（**沪深300**）。此推断**已明示依据，非凭空生成凭据**。

| 产物 | 状态 |
|---|---|
| `ab_n3_batchA.json` | 空串 → 推断=沪深300（脚本默认兜底 benchmark.csv） |
| `ab_n3_w3.json` | 空串 → 推断=沪深300（脚本默认兜底 benchmark.csv） |
| `ab_n3_w4.json` | 空串 → 推断=沪深300（脚本默认兜底 benchmark.csv） |
| `ab_n3_w5.json` | 空串 → 推断=沪深300（脚本默认兜底 benchmark.csv） |
| `f4_p1.json` | 空串 → 推断=沪深300（脚本默认兜底 benchmark.csv） |
| `f4_p2.json` | 空串 → 推断=沪深300（脚本默认兜底 benchmark.csv） |
| `f4_p3.json` | 空串 → 推断=沪深300（脚本默认兜底 benchmark.csv） |
| `f4_smoke.json` | 空串 → 推断=沪深300（脚本默认兜底 benchmark.csv） |
| `five_factor_ab_main.json` | 空串 → 推断=沪深300（脚本默认兜底 benchmark.csv） |
| `five_factor_ab_smoke.json` | 空串 → 推断=沪深300（脚本默认兜底 benchmark.csv） |
| `five_factor_ab_smoke2.json` | 空串 → 推断=沪深300（脚本默认兜底 benchmark.csv） |
| `impact_p1.json` | 空串 → 推断=沪深300（脚本默认兜底 benchmark.csv） |
| `impact_p3.json` | 空串 → 推断=沪深300（脚本默认兜底 benchmark.csv） |
| `neu_p2.json` | 空串 → 推断=沪深300（脚本默认兜底 benchmark.csv） |
| `neu_p3.json` | 空串 → 推断=沪深300（脚本默认兜底 benchmark.csv） |
| `rs_main.json` | 空串 → 推断=沪深300（脚本默认兜底 benchmark.csv） |
| `rs_smoke.json` | 空串 → 推断=沪深300（脚本默认兜底 benchmark.csv） |
| `ss_p1.json` | 空串 → 推断=沪深300（脚本默认兜底 benchmark.csv） |
| `ss_p2.json` | 空串 → 推断=沪深300（脚本默认兜底 benchmark.csv） |
| `ss_smoke.json` | 空串 → 推断=沪深300（脚本默认兜底 benchmark.csv） |
| `t1b_p1.json` | 空串 → 推断=沪深300（脚本默认兜底 benchmark.csv） |
| `t1b_p2.json` | 空串 → 推断=沪深300（脚本默认兜底 benchmark.csv） |
| `tc_t1_p1.json` | 空串 → 推断=沪深300（脚本默认兜底 benchmark.csv） |
| `tc_t1_p2.json` | 空串 → 推断=沪深300（脚本默认兜底 benchmark.csv） |
| `tc_t1_p3.json` | 空串 → 推断=沪深300（脚本默认兜底 benchmark.csv） |
| `tc_t2_p1.json` | 空串 → 推断=沪深300（脚本默认兜底 benchmark.csv） |
| `v2_c20_v1_p1.json` | 空串 → 推断=沪深300（脚本默认兜底 benchmark.csv） |
| `v2_c20_v1_p2.json` | 空串 → 推断=沪深300（脚本默认兜底 benchmark.csv） |
| `v2_p1.json` | 空串 → 推断=沪深300（脚本默认兜底 benchmark.csv） |
| `v2_p2.json` | 空串 → 推断=沪深300（脚本默认兜底 benchmark.csv） |
| `v2_p3.json` | 空串 → 推断=沪深300（脚本默认兜底 benchmark.csv） |

### 2.3 ❌ **基准不可确认**（25 份）

> 这些 JSON **无 `benchmark` 字段**，且日志未记录生效基准。
> **按 P005 §3.4：不回填、不推断，统一标注「基准不可确认」。**

| 产物 | 标注 |
|---|---|
| `adx_attr_w1.json` | 无字段 |
| `adx_attr_w2.json` | 无字段 |
| `adx_attr_w3.json` | 无字段 |
| `adx_attr_w4.json` | 无字段 |
| `cost_model_check.json` | 无字段 |
| `daily_screen_2026-09-19.json` | 无字段 |
| `decay_h1.json` | 无字段 |
| `decay_h10.json` | 无字段 |
| `decay_h20.json` | 无字段 |
| `decay_h5.json` | 无字段 |
| `decay_h60.json` | 无字段 |
| `form_screen_eval.json` | 无字段 |
| `ic_diag_smoke.json` | 无字段 |
| `ic_diagnosis.json` | 无字段 |
| `newstock_pref_diag.json` | 无字段 |
| `regime_overlay_const05_pilot.json` | 无字段 |
| `regime_overlay_study_w5.json` | 无字段 |
| `tdx_ic_800.json` | 无字段 |
| `tdx_ic_full.json` | 无字段 |
| `tdx_ic_smoke.json` | 无字段 |
| `tdx_native_screen.json` | 无字段 |
| `tdx_native_screen_adj.json` | 无字段 |
| `v2_factor_correlation.json` | 无字段 |
| `v2_factor_study.json` | 无字段 |
| `v2_rolling_eval_w6.json` | 无字段 |

---

## §三 报告层

| 报告 | 基准 | 代次 | 标注状态 |
|---|---|---|---|
| `PORTFOLIO_AB_REPORT.md` | **无基准对照** | — | ✅ 已补声明（2026-10-08） |
| `PORTFOLIO_AB_REPORT_2.md` | **无基准对照** | — | ✅ 已补声明（2026-10-08） |
| `PORTFOLIO_AB_REPORT_3.md` | **沪深300** | 旧 | ✅ 已补声明（2026-10-08） |
| `CONCENTRATION_REPORT.md` | ？ | ？ | ⏳ **待确认是否扩大标注范围** |
| `TDX_EVALUATION_REPORT.md` | ？ | ？ | ⏳ **待确认** |
| `STEP1_3_EXECUTION_REPORT.md` | 两代**并存** | 旧+新 | ✅ 已有 §〇 口径声明 |

---

## §四 发现

1. **主干侧同样「数据侧已修、基准侧未修」**：v2/v3 均含退市股（数据侧新代），
   但 `benchmark.csv` 全是**沪深300**（基准侧旧代）。
2. **`benchmark=""` 是普遍状态**（31 / 59 份）——**直接印证 §〇 0.1 的根因警句**。
3. **`D:/tdx_dataset_v3` 缺 `benchmark_ew.csv`**（v2 有）→ 与副本侧同一缺口。
4. **覆盖区间错配**：见 §一 注。

---

## §五 维护规则

1. 本表**由脚本生成**，改数据后重跑生成脚本即可。
2. 新增产物**必须**显式传入 `--benchmark` 并落盘生效基准（P005 §3.3 治疗目标）。
3. 引用 §2.3 中任何数字前，**基准只能声明「不可确认」**。

---

**本表不构成投资建议。**
