# 两条演进线的合并报告（2026-09-30）

> **背景**：`C:\Users\T430\Desktop\1.0`（原版）与 `1.0 - 副本`（工作副本）
> 是**同一起点的两个独立 git 仓库**，在提交 **`ef0f5a9`** 处分叉，各自独立推进。
> 本报告记录本次**单向合并**（`1.0` → 工作副本）的范围、冲突处置与交叉验证结论。

---

## 一、分叉后的两条线

| | 桌面 `1.0` | 工作副本 `1.0 - 副本` |
|---|---|---|
| **路线** | TDX 原生数据栈 + 产品化 | 口径修复 + 假设检验 |
| **主要产物** | `tdx_native/`（11 模块）· 8 份事前登记 · 5 个研究脚本 · `risk/liquidity.sqrt_impact` | turnover 缺陷修复 · 披露日/涨跌幅 PIT 修复 · H-D1~H-D4 · 持有期/组合层研究 |
| **假设编号** | H-F5 / H-DECAY / H-F4 / H-V2 / H-ICX / H-SS / H-IMPACT / H-TC | H-D1 / H-D2 / H-D3 / H-D4 |
| **门禁** | ruff 51→0、mypy 57→0、pytest 538→620 | 持续 6/6 绿 |
| **关键结论** | T1（持有期 5→20）为"唯一按登记标准成立的组合层改善"（5/5 窗口、Δ中位 +4.27pp） | 持有期 h=20 改善 **+27.26pp**；**turnover 修复后 h=10/20/40 转正** |

**假设编号不冲突**（两套编号无重叠）✓

## 二、冲突面与处置

分叉后两边共修改 73 / 89 个文件，**交集 33 个**，其中**内容真不同 18 个**。

| 类别 | 文件数 | 处置 |
|------|-------:|------|
| `1.0` 独有改动（副本未改） | 40 | ✅ **直接搬入**（无覆盖风险） |
| 两边都改、内容相同 | 15 | 无需处置 |
| 两边都改、内容不同 | 18 | **逐项判断**（见下） |

### 18 个差异文件的处置

**文档类（7 个）—— 保留副本版本**
`.workbuddy/memory/2026-09-19/22/23/24.md` · `DIRECTORY_LAYOUT.md` · `HANDOVER.md` ·
`WORKLOG.md` · `STEP1_3_EXECUTION_REPORT.md`
→ 副本版本含 09-25~09-26 的最新工作；`1.0` 的对应内容以**独立文件**保留（见下）

**代码类（1 个）—— 采用 `1.0` 版本（超集）**
`portfolio_backtest.py`：`1.0` 版本 = 副本版本 + 3 个新特性
（`score_func` / `max_participation` / `impact_model`），
**且完整包含副本的 `position_scaler`、`_trade_cost(...,day)`、停牌不建仓改动**，
默认值均保持历史行为 → 向后兼容 ✓

**配置类（1 个）—— 合并**
`mypy.ini`：加入 `[mypy-pytdx.*] ignore_missing_imports`（tdx_native 的可选依赖），
保留副本的 akshare 注释

**脚本/测试类（9 个）—— 保留副本版本**
`scripts/run_cost_model_check.py` · `run_regime_overlay_study.py` ·
`run_tail_exclusion_study.py` · `run_tdx_rolling_eval.py` ·
`scripts/build_certified_dataset_v2.py` · `tests/test_package_layout.py` ·
`tests/test_var_calculator.py` · `risk/var_calculator.py`
→ 副本版本含后续修复；`1.0` 对同名脚本的改动若有用，以**新文件**形式保留

**`risk/liquidity.py` —— 采用 `1.0` 版本（纯新增）**
`1.0` 在副本版本（38 行）上**追加** `sqrt_impact()`（Almgren-Chriss √ 冲击成本），
共 59 行 → 副本版本是其子集 ✓

## 三、搬入内容清单（40 个文件）

| 类别 | 内容 |
|------|------|
| **TDX 原生模块** | `tdx_native/`（`day_reader` / `gbbq_reader` / `adjust` / `fetch_names` / `five_factor` / `screen` / `backfill` / `daily_report` / `run_daily` / `smoke_test` / `__init__` + README + `_smoke/` 合成 fixture） |
| **守卫测试** | `tests/test_tdx_native.py`（40 项） |
| **事前登记（8 份）** | `FIVE_FACTOR_PREREG.md`(H-F5) · `IC_DECAY_PREREG.md`(H-DECAY) · `FACTOR_SUBSET_PREREG.md`(H-F4/H-V2) · `IC_DIAGNOSIS_PREREG.md`(H-ICX) · `STYLE_REGIME_PREREG.md` · `STYLE_SWITCH_PREREG.md`(H-SS) · `IMPACT_COST_PREREG.md`(H-IMPACT) · `TURNOVER_CAPACITY_PREREG.md`(H-TC) |
| **研究脚本（5 个）** | `run_five_factor_ab.py` · `run_ic_diagnosis.py` · `run_tdx_universe_ic.py` · `run_factor_correlation.py` · `build_equalweight_benchmark.py` |
| **数据与运行** | `data/names.csv` · `data/gbbq_events.csv` · `run_daily.bat` |
| **调研** | `GITHUB_ASHARE_QUANT_SURVEY.md` |
| **记忆** | `.workbuddy/memory/2026-09-30.md` |

## 四、⚠️ 合并带来的重要交叉验证

### 4.1 两条线**独立发现同一件事**

| 来源 | 表述 |
|------|------|
| `1.0` `TURNOVER_CAPACITY_PREREG.md`(H-TC) | 「剩余最大的**确定性损耗**是换手成本——5 日全调仓…」 |
| 工作副本 `FACTOR_HORIZON_DECAY_REPORT.md` | 「成本拖累 **16.58pp/年**，与唯一稳健 alpha(+7.17pp) 同量级」 |

→ **两个独立仓库、两套独立分析，得到同一结论**。这是较强的交叉验证。

### 4.2 工作副本的结论**直接回答了 `1.0` 的登记问题**

`1.0` 的 `IC_DECAY_PREREG.md`(H-DECAY) 登记动机原文：

> 「T1（持有期 5 → 20 日）是全项目唯一按登记标准成立的组合层改善（5/5 窗口、Δ超额中位 +4.27pp）。
> 但它同时改变换手与信号有效期，**无法区分"省成本"与"信号仍在"**。」

**工作副本已做了该实验**（`FACTOR_HORIZON_DECAY_REPORT.md`，`--horizon {5,10,20,40}`，
`--step` 与 horizon 相等以保证前瞻不重叠）：

| 因子 | IC@5 | IC@10 | IC@20 | IC@40 | 类型 |
|------|-----:|-----:|-----:|-----:|------|
| `amihud_20` | +0.0286 | +0.0395 | +0.0462 | **+0.0654** | 慢变量（229%） |
| `log_amount_20` | −0.0613 | −0.0764 | −0.0842 | **−0.1058** | 慢变量（173%） |
| `vol_20` | −0.0718 | −0.0830 | −0.0906 | **−0.1001** | 慢变量（139%） |
| `ret_5` | −0.0265 | −0.0326 | −0.0284 | **−0.0235** | 快变量（89%） |
| `vol_ratio` | −0.0319 | −0.0326 | −0.0243 | **−0.0153** | 快变量（48%） |

**结论**：**「信号仍在」** —— 规模/波动/流动性/价格类**慢变量**的 IC
随持有期**单调增强至 40 日**，不是单纯的省成本。

**但**：`FACTOR_HORIZON_DECAY_REPORT.md` §三 同时警告
「年化毛超额 ∝ IC(H)/√H 随 H 下降，成本 ∝ 1/H 也下降，**净效果符号无法由 IC 数据判定**」——
故该问题需**组合层**验证，工作副本的 `HORIZON_NET_EFFECT_REPORT.md` 已补上。

### 4.3 ⚠️ 一条必须声明的差异：`1.0` **没有** turnover 修复

`1.0` 的 `real_alpha_pipeline.load_certified_csv` **未包含 `turnover` 透传修复**
（`grep -c turnover_rate` 返回 0）。

**影响**：
- `1.0` 的 T1 结论（5→20 日改善）是在**「turnover 分项失效」口径**下得到的
- 工作副本已证明该缺陷使过线率从 18.71% 降到 6.65%（**近 3 倍**）
- 故 **`1.0` 的绝对数值不能与工作副本的新口径直接比较**，但其**方向性结论
  （持有期延长是改善）与新口径一致** ✓

**待办**：若在 `1.0` 上重跑 T1，应采用新口径（或把该修复也同步回 `1.0`）。

## 五、合并后验证

| 项 | 结果 |
|------|------|
| `run_ci.py` | ✅ **6/6 全绿**（syntax / ruff / mypy / compat / pytest **934 项** / credentials） |
| `tests/test_tdx_native.py` | ✅ 40 项全通过 |
| `tdx_native.smoke_test` | ✅ 端到端通过（合成 vipdoc 树 + V1 尾部剔除） |
| `DIRECTORY_LAYOUT.md` | ✅ 重生成（793 → **818 行**，含 `tdx_native` 子包） |
| 凭据扫描 | ✅ 421 个文件，未发现明文凭据 |

## 六、合并后仍存在的差异（未处置，需决策）

| 项 | 说明 |
|------|------|
| **8 份 `1.0` 的事前登记** | 已搬入，但**均未执行**（状态「待执行」）。工作副本已用 H-D1~H-D4 占用了部分方向 |
| **`1.0` 的文档版本** | `1.0` 的 `HANDOVER.md` / `WORKLOG.md` 含其 T1 等结论；副本版本未吸收（避免覆盖副本更新内容） |
| **`tdx_native` 数据依赖** | 需本机通达信客户端更新 `.day` 文件；`run_daily` 的调度未注册（`run_daily.bat` + schtasks 命令在 README） |
| **编号体系统一** | 两套编号（H-D*/H-F*/H-V*/H-TC…）并存，**无冲突但需在文档中说明** |

## 七、声明

- 本合并为**单向**（`1.0` → 工作副本）；**未修改 `1.0`**（用户的原版目录保持原状）
- 所有搬入文件**经 CI 验证**；未通过的文件已单独处置（见 §二）
- **本报告不构成投资结论**
