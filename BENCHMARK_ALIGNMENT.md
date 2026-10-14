# 副本内基准对照表（Benchmark Alignment Registry）

> **建立**：2026-10-08　**建立方**：海外版 WorkBuddy AI（副本侧 `C:\Users\T430\Desktop\1.0 - 副本`）
> **依据**：`P004 §3.2`（主干侧回执：✅ 接受）+ `P005 §3.2`（字段建议）
> **用途**：让「某个数字属哪一代基准」**可查、可复核**，避免跨口径混比（`STEP1_3_EXECUTION_REPORT.md` §〇 0.3 禁止项）。

---

## 〇、字段定义

| 字段 | 含义 |
|---|---|
| 产物 / 报告 | 文件路径（相对副本根目录） |
| 数据源 | `args.dataset` 实测值 |
| 基准 | 沪深300 / 等权全A / 待确认 |
| 代次 | **旧代**（沪深300 / 指数口径）· **新代**（等权全A）· **待确认** |
| 含退市股 | 数据源是否含 2016 年后退市股（幸存者偏差是否消除） |
| 覆盖区间 | 基准/窗口实际覆盖的日期范围与根数 |
| 生成时间 | 文件 mtime |
| 标注状态 | 是否已在报告正文声明口径 |

> ⚠️ **本表与主干 `reports/EVIDENCE_INDEX.md` §三 无法直接对齐**：该节实际字段为「文件 | 说明」两列，
> **不含** 数据源 / 基准 / 代次 / 含退市股 / 覆盖区间。故本表字段按 `P004 §3.2` 自定，
> 建议双方各自维护、以**本表字段**为横向比对口径（详见 P005 回执 §二）。

---

## 一、数据集层：基准文件实况

| 基准文件 | 数据集 | 基准 | 代次 | 含退市股 | 覆盖区间 | 生成时间 | 备注 |
|---|---|---|---|---|---|---|---|
| `benchmark.csv` | v2 | **沪深300**（`code:000300`） | 旧代 | —（基准文件本身不涉股票池） | 2021-08-02 ~ 2026-09-10（**1,240** 行） | 09-19 14:02 | sha256 `83dab01f…60d3` |
| `benchmark.csv` | v3 | **沪深300**（`code:000300`） | 旧代 | — | 2021-08-02 ~ 2026-09-10（**1,240** 行） | 09-19 22:28 | **与 v2 同 sha256** |
| `benchmark_ew.csv` | v2 | **等权全A**（`code:EW_ALL`） | 新代 | — | **2016-01-05 ~ 2026-09-11（2,598 行）** | 09-19 20:36 | ⚠️ **区间与认证窗口不一致**（见 §四 发现 3） |
| `benchmark_ew.csv` | v3 | — | — | — | — | — | ❌ **不存在**；等权基准改以 `reports/ew_benchmark_v3.json` 形式落盘 |

**结论**：v2 / v3 的**沪深300 基准是同一个文件**（同 sha256）；**等权全A 基准 v2 有 CSV、v3 只有 JSON**。

---

## 二、副本产物层：基准归属

### 2.1 等权全A 口径（新代）

| 产物 | 数据源 | 基准 | 代次 | 含退市股 | 覆盖区间 | 生成时间 |
|---|---|---|---|---|---|---|
| `reports/ew_benchmark_v3.json` | `D:/tdx_dataset_v3` | **等权全A（自建）** | 新代 | ✅ | 2021-08-02 ~ 2026-09-10（1,240 日；分母均值 5,187.11，池 5,667 只） | 09-20 06:01 |
| `reports/v3_rolling_eval_ew_full.json` | `D:/tdx_dataset_v3` | 等权全A（同上，字段 `ew_benchmark_source` 自证） | 新代 | ✅ | 6 窗口 | 09-20 07:56 |
| `reports/v3_rolling_eval_ew.json` | `D:/tdx_dataset_v3` | 等权全A | 新代 | ✅ | 6 窗口 | 09-20 00:40 |
| `reports/v2_rolling_eval_ew.json` | `D:/tdx_dataset_v2` | 等权全A | 新代 | ✅ | 6 窗口 | 09-19 22:16 |
| `reports/combo_study_h20_fixed.json` | `D:/tdx_dataset_v3` | 等权全A | 新代 | ✅ | 3 窗口 | 09-26 21:20 |
| `reports/combo_study_h20.json` | `D:/tdx_dataset_v3` | 等权全A（修复前） | 新代 | ✅ | 3 窗口 | 09-26 08:09 |

> `combo_study` 基准判定依据：`reports/_combo_fixed.log:7` —— 「PIT 快照 2,599 日 | **基准 1,240 根**」。
> **1,240 根**与认证窗口一致，**与 v2 `benchmark_ew.csv`（2,598 行）不是同一文件**。

### 2.2 沪深300 口径（旧代）

| 产物 | 数据源 | 基准 | 代次 | 含退市股 | 覆盖区间 | 生成时间 |
|---|---|---|---|---|---|---|
| `reports/stop_loss_ab_5win.json` | `D:/tdx_dataset_v3` | **沪深300** | 旧代 | ✅ 239 | 1,240 日 | 10-07 22:13 |
| `reports/stop_loss_ab.json` | `D:/tdx_dataset_v3` | 沪深300 | 旧代 | ✅ | 1,240 日 | 09-30 20:25 |
| `reports/valuation_weight_ab.json` | `D:/tdx_dataset_v3` | 沪深300 | 旧代 | ✅ | 1,240 日 | 10-07 22:37 |
| `reports/v2_rolling_eval_w6.json` | `D:/tdx_dataset_v2` | 沪深300（推断） | 旧代 | ✅ | 1 窗口 | 09-19 14:44 |

> `stop_loss_ab*` / `valuation_weight_ab` 基准判定依据：产物 `args.dataset = D:/tdx_dataset_v3`，
> 而 **v3 目录只有 `benchmark.csv`（沪深300）**，无 `benchmark_ew.csv` → 默认兜底即沪深300。

### 2.3 ⚠️ 基准**待确认**（JSON 无 `benchmark` 字段，日志未记录生效基准）

> **不得凭默认值推断就下标注**——否则重犯本案要修的「推断当确认」问题。
> 建议：按 §〇 0.4「口径信息去哪里查」补齐后，再纳入 2.1 / 2.2。

| 产物 | 数据源 | 生成时间 | 待确认项 |
|---|---|---|---|
| `reports/concentration_with_p.json` | `D:/tdx_dataset_v3` | 09-23 22:59 | 是否显式传 `--benchmark` |
| `reports/tail_exclusion_with_p.json` | `D:/tdx_dataset_v3` | 09-22 20:48 | 同上 |
| `reports/horizon_study_turnover_fixed.json` | `D:/tdx_dataset_v3` | 09-26 20:11 | 同上 |
| `reports/horizon_study.json` | `D:/tdx_dataset_v3` | 09-26 07:11 | 同上 |
| `reports/expert_filter_study.json` | `D:/tdx_dataset_v3` | 09-30 17:53 | 同上 |
| `reports/cost_model_check_with_p.json` | `D:/tdx_dataset_v3` | 09-22 04:35 | 同上 |
| `reports/industry_ic_attribution.json` | `D:/tdx_dataset_v3` | 09-30 20:17 | 同上 |
| `reports/decay_h5/h10/h20/h40.json` | `D:/tdx_dataset_v3` | 09-26 | 同上 |
| `reports/contrarian_ab_with_p.json` | —（无 `args.dataset`） | 09-23 22:24 | 数据源亦待确认 |

**副本侧实测统计**（`reports/*.json`，排除 `.partial`，共 **46** 份）：

| 项 | 份数 | 说明 |
|---|---|---|
| 含 `benchmark` 字段 | **4** | 见 §2.4 |
| 含 `benchmark` 字段且**值为空串** | **1** | `five_factor_ab_v2.json` → `args.benchmark = ""`，**直接印证隐式兜底根因** |
| 字段名含 `ew` 可辨为等权口径 | 4 | `ew_benchmark_v3` / `v3_rolling_eval_ew` / `v3_rolling_eval_ew_full` / `v2_rolling_eval_ew` |
| **基准完全不可辨** | **38** | 只能靠数据源 + 默认值**推断**，不能确认 |

→ 与主干 `reports/EVIDENCE_INDEX.md:177`「修复前 42 份 JSON 仅 3 份可辨基准」**同构**。

### 2.4 含 `benchmark` 字段的 4 份产物（逐一列明）

| 产物 | 字段位置 | 值 | 判定 |
|---|---|---|---|
| `reports/five_factor_ab_v2.json` | `args.benchmark` | **`""`（空串）** | ⚠️ **根因直证**：空串 → 脚本兜底到 `benchmark.csv`（沪深300）。数据源 v2 |
| `reports/v3_alpha_gap_probe.json` | `benchmark.windows[]` | 含 **`ew_pct` 与 `hs300_pct` 双基准**（2024-01-02~2026-09-10） | ✅ **唯一双基准产物**；数据源 v3 |
| `reports/v3_alpha_gap_probe_coverage.json` | `benchmark.windows[]` | 同上（双基准） | ✅ 同上 |
| `reports/contrarian_ab_with_p.json` | `results.<窗口>.benchmark` | `{days, total_return_pct, annualized_pct}` | ⚠️ 有基准收益对象，**但未标明是哪个基准**；`args.dataset` 亦缺失 |

> **两点由此确认**：
> ① **副本同样存在「`--benchmark` 空串 → 隐式兜底」**（`five_factor_ab_v2.json` 直证），
>    与主干 §〇 0.1 的根因警句**完全对应** → P005 §3.3 的根因治疗对副本同样适用。
> ② **副本已具备双基准对照能力**（`v3_alpha_gap_probe*`），并非只能单基准。

---

## 三、报告层：标注状态

| 报告 | 基准 | 代次 | 标注状态 | 处置 |
|---|---|---|---|---|
| `SIX_ISLANDS_WIRING_REPORT.md` | 沪深300 | 旧代 | ✅ **本次补标**（2026-10-08，纯追加 34 行） | 完成（P004 §3.1） |
| `COMBO_STUDY_REPORT.md` | 等权全A | 新代 | ✅ 已声明（`:5`） | 无需动作 |
| `PORTFOLIO_AB_REPORT_3.md` | 沪深300 | 旧代 | ✅ 标题即声明 | 无需动作 |
| `PORTFOLIO_AB_REPORT.md` / `_2.md` | 无基准指数对照 | — | N/A（自述「缺基准指数对照」） | 无需动作 |
| `TAIL_EXCLUSION_REPORT.md` | 待确认 | 待确认 | ❌ 未声明（正文仅表头「基准%」） | ⚠️ **超出 P004 原清单**，待贵方确认是否纳入 |
| `CONCENTRATION_REPORT.md` | 待确认 | 待确认 | ❌ 未声明（仅结论提及「跑输沪深300」） | ⚠️ 同上 |
| `MARKET_RISK_GATE_REPORT.md` | 待确认 | 待确认 | ❓ 提及 `benchmark.csv` 但无口径标签 | ⚠️ 同上 |
| `HORIZON_NET_EFFECT_REPORT.md` | 待确认 | 待确认 | ❓ | ⚠️ 同上 |
| `EXPERT_FILTER_AND_HF4_HV2_REPORT.md` | 待确认 | 待确认 | ❓ | ⚠️ 同上 |

> **范围纪律**：P004 §二 清单只列了 `SIX_ISLANDS_WIRING_REPORT.md` 与 `COMBO_STUDY_REPORT.md`。
> 本次**只对 `SIX_ISLANDS_WIRING_REPORT.md` 执行 3.1 标注**；
> 其余未声明报告**列入本表待确认**，扩大标注范围须先确认其基准（协议第 2 条）。

---

## 四、四项关键发现

1. **v3 并非「无等权基准可指」** —— 主干 `P005 §二` 与 `P002答复 §四` 称 v3 缺 `benchmark_ew.csv`、
   「即便想用等权全A 重跑也无基准文件可指」。实测**不成立**：
   v3 的等权全A 基准已以 **`reports/ew_benchmark_v3.json`** 形式存在
   （`source: build_equal_weight_benchmark.py --dataset D:\tdx_dataset_v3（流式全池）`，
   池 5,667 只、1,240 日、分母均值 5,187.11）。缺的是**写回数据集目录**这一步，不是基准本身。

2. **v3 的等权全A 口径滚动评估已跑过** —— `reports/v3_rolling_eval_ew_full.json`（09-20）6 窗口
   结论**全部 `ALPHA_NOT_ESTABLISHED`**（t 全部为负，p 0.096~0.591）。
   → P004 §3.3 的「重跑」在**滚动评估层面已有产物**，无需重跑；
   但 ATR 止损 / 估值权重这两项**组合层 A/B**在等权全A 口径下**确无产物**——3.3 的决策点依然成立。

3. **v2 `benchmark_ew.csv` 的覆盖区间与认证窗口不一致** ——
   该文件覆盖 **2016-01-05 ~ 2026-09-11（2,598 行）**，而 v2/v3 认证窗口是
   **2021-08-02 ~ 2026-09-10（1,240 日）**。项目实际使用的等权基准是 **1,240 根**那个
   （`_combo_fixed.log:7`）。→ 若把 v2 的 `benchmark_ew.csv` 当作标准等权基准做对照，存在**区间错配**风险。

4. **`reports/` 未纳入版本控制** —— `.gitignore:22` 忽略 `reports/`，
   导致**全部研究产物（含等权基准本体 `ew_benchmark_v3.json`）无回退点、无变更追溯**。
   主干侧有同类历史（`chore(gitignore): 放行 reports/cross_decade（第 3 次同类漏洞，已加检查清单）`）。
   → 建议双方统一处置（详见 P005 回执独立意见 4）。

---

## 五、维护规则

1. **新增产物必须落盘 `benchmark` 字段**（主干已有 7 个脚本实现，副本应比照补齐）。
2. 本表**每次新增组合层产物时同步追加一行**；不确定的一律进 §2.3「待确认」，**不得推断填表**。
3. 跨口径数字**禁止直接比较**（§〇 0.3）；确需比较时须先做口径敏感性检验并落预注册。

---

**本表不构成投资建议。**

---

## 附件：主干侧基准对照表（2026-10-14 A2 合入 · 对方维护口径）

> 本附件为**主干侧 `BENCHMARK_ALIGNMENT.md` 全文**（R5「副本版为底 +
> 主干独有段落显式列清单并入」的执行）。两表是**两侧平行台账**：
> 上表（§一~§五）= 副本侧 59 份；下表 = 主干侧 59 份（3 可确认 /
> 31 空串 / 25 不可确认）。**不得把两表数字相加或互推**。
> 引用主干侧数字时须注明「主干侧台账」。

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
