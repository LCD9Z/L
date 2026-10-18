# 拒绝实验登记册（REJECTED_EXPERIMENTS）

> **建立**：2026-10-18　**状态**：在册（EVIDENCE_CHAIN_PREREG 组件 A12）
> 对应 `GITHUB_ASHARE_QUANT_SURVEY.md` §8.4-A12：「拒绝的实验未系统入册」，
> 验收原话「登记册含被拒条目；**条目数 = `n_trials` 来源**」。
>
> **只登记不改**：本册不重新判读任何已归档结论，只转写其要义并给出来源路径。
> 本项目一半以上资产是负结论（AGENTS.md §2.3）——负结论的价值完全依赖
> 「可找到、可数清、可复核」。

## 一、计数来源（n_trials 的四个清单）

`n_trials` 的权威来源是 `scripts/run_multiple_testing_audit.py` 的四个模块级清单
（守卫 `tests/test_rejected_registry.py` 直接 import 它们对账，不硬编码数字）：

| 清单 | 条数 | 含义 |
|---|---|---|
| `DECLARED_NON_IC_TESTS` | 12 | 执行过但无机器可读 p 值的检验 |
| `DISTINCT_STRATEGY_CONFIGS` | 13 | 策略层面的不同假设/配置 |
| `STRATEGY_SOURCES` | 6 | 有逐窗口 p 值的归档（滚动评估族） |
| `SOURCES` | 2 | 因子 IC 族（v1/v2 是同一批因子的复检） |

归档审计数值（`reports/multiple_testing_audit.json`）：`n_hypotheses = 23`
（10 因子 + 13 策略配置）、`n_executions = 32`（20 有 p + 12 无 p）、
策略族 BH(m=6) **拒绝 0**。

## 二、表一 · 检验级（逐条对应审计脚本清单）

「参数组数」= 该行实验实际执行过的独立参数配置组数（执行口径）。
「结论」列为**转写**，权威在来源文件。

| # | 实验 | 计数来源 | 判定/证据文件 | 结论（转写） | 参数组数 |
|---|---|---|---|---|---|
| 1 | H-C1 复合反转 · IC 层面 | 声明族 | `ALPHA_HYPOTHESIS_PREREG.md` | 预注册假设，IC 层面检验（无 p 值归档） | 1 |
| 2 | H-C1 复合反转 · 组合层面 A/B 一阶段 | 声明族 | `docs/archive/PORTFOLIO_AB_REPORT.md` | 严格结论：「反转优于动量」成立；「存在可实现 Alpha」**待复核后判定**（保守负结论） | 1 |
| 3 | H-C1 复合反转 · 组合层面 A/B 二阶段 | 声明族 | `docs/archive/PORTFOLIO_AB_REPORT_2.md` | 同上族：可实现 Alpha 未获判定 | 1 |
| 4 | H-C1 复合反转 · 组合层面 A/B 三阶段 | 声明族 | `docs/archive/PORTFOLIO_AB_REPORT_3.md` | 同上族：可实现 Alpha 未获判定 | 1 |
| 5 | 尾部剔除 V1 | 声明族 | `docs/archive/TAIL_EXCLUSION_REPORT.md` | 3 个额外独立抽样复现后**结论收窄**（改善不可靠） | 1 |
| 6 | 尾部剔除 V2 | 声明族 | `docs/archive/TAIL_EXCLUSION_REPORT.md` | 同上 | 1 |
| 7 | 集中度 C10 / C20 / C30 | 声明族 | `docs/archive/CONCENTRATION_REPORT.md` | 集中度是抽样噪声根因：分散后离散度降 5~14 倍；**C5 集中配置的结论被拒绝** | 3 |
| 8 | 采样敏感性 4 组独立抽样 | 声明族 | `docs/archive/SAMPLING_SENSITIVITY_REPORT.md` | 「提高持仓数能稳定结论」被拒：标准差降 4.2 倍但**不改变「基线无 Alpha」**方向 | 4 |
| 9 | 多股票池重复验证 6 组 | 声明族 | `docs/archive/UNIVERSE_REPLICATION_REPORT.md` | 唯一可复现的是回撤改善；**超额结论不可靠**；推翻「方向稳健」表述 | 6 |
| 10 | 多窗口滚动检验 6 窗口 | 声明族 | `STEP1_3_EXECUTION_REPORT.md` §5.2 | 滚动窗口族（无 p 值归档） | 6 |
| 11 | ADX 叠加 5 窗口 + 常数敞口对照 5 窗口 | 声明族 | `STEP1_3_EXECUTION_REPORT.md` §6.4 | ADX 状态叠加族（无 p 值归档） | 10 |
| 12 | 成本模型 legacy/new 对照 2 窗口 | 声明族 | `reports/cost_model_check.json` | 成本口径对照（机器可读，见策略族 #10/#11） | 2 |
| 13 | 基线 V0（内置动量追高） | 策略配置族 | `reports/multiple_testing_audit.json` `strategy_family` | 6 个可机读配置中位 p **0.094~0.521**；BH(m=6) **拒绝 0**；个别窗口显著但校正后不拒绝 | 1 |
| 14 | H-C1 复合反转 · A/B 三阶段 | 策略配置族 | `docs/archive/PORTFOLIO_AB_REPORT{,_2,_3}.md` | 同 #2~#4 | 1 |
| 15 | 尾部剔除 V1 | 策略配置族 | `docs/archive/TAIL_EXCLUSION_REPORT.md` | 同 #5 | 1 |
| 16 | 尾部剔除 V2 | 策略配置族 | `docs/archive/TAIL_EXCLUSION_REPORT.md` | 同 #6 | 1 |
| 17 | 集中度 C10 | 策略配置族 | `docs/archive/CONCENTRATION_REPORT.md` | 同 #7（分散档可解释，集中档被拒） | 1 |
| 18 | 集中度 C20 | 策略配置族 | `docs/archive/CONCENTRATION_REPORT.md` | 同 #17 | 1 |
| 19 | 集中度 C30 | 策略配置族 | `docs/archive/CONCENTRATION_REPORT.md` | 同 #17 | 1 |
| 20 | ADX 状态叠加 | 策略配置族 | `STEP1_3_EXECUTION_REPORT.md` §6.4 | 同 #11 | 1 |
| 21 | ADX 常数敞口对照 | 策略配置族 | `STEP1_3_EXECUTION_REPORT.md` §6.4 | 同 #11 | 1 |
| 22 | 成本模型 legacy | 策略配置族 | `reports/cost_model_check.json` | 同 #12 | 1 |
| 23 | 成本模型 new | 策略配置族 | `reports/cost_model_check.json` | 同 #12 | 1 |
| 24 | 采样敏感性 4 组抽样 | 策略配置族 | `docs/archive/SAMPLING_SENSITIVITY_REPORT.md` | 同 #8 | 4 |
| 25 | 多股票池重复验证 6 组 | 策略配置族 | `docs/archive/UNIVERSE_REPLICATION_REPORT.md` | 同 #9 | 6 |

**表一合计：58 组**（声明族 37 + 策略配置族 21）。
条目数对账：声明族行数 12 = `len(DECLARED_NON_IC_TESTS)`；
策略配置族行数 13 = `len(DISTINCT_STRATEGY_CONFIGS)`（守卫 R-3 逐项断言）。

> ⚠️ **结构性缺口（审计脚本自己的 notes 已记）**：策略层面实验多数无 p 值归档，
> 只能逐项声明、无法逐项校正。本册把「无 p 值」如实标在结论列，不伪装成已检验。

## 三、表二 · 路线级（假设族/项目级证伪）

| # | 路线 | 预注册/来源 | 判定文件 | 结论（转写） |
|---|---|---|---|---|
| R1 | H-D1 | `ALPHA_HYPOTHESIS_PREREG_HD1.md` | `deliverables/stock-partner/2026-09-30/AI股神团队1.0-项目升级审查-圆桌报告.md` | 不成立 |
| R2 | H-D2 | `ALPHA_HYPOTHESIS_PREREG_HD2.md` | 同上 | 不成立 |
| R3 | H-D3 | `ALPHA_HYPOTHESIS_PREREG_HD3.md` | 同上 | 不成立 |
| R4 | H-D4 | `ALPHA_HYPOTHESIS_PREREG_HD4.md` | 同上 | 不成立 |
| R5 | A10 · CNE6 中性化 | `GITHUB_ASHARE_QUANT_SURVEY.md` §8.6 | 同左 | 中性化已证伪（暂缓项，不追） |
| R6 | 「信号真实但不可变现」 | `CROSS_DECADE_PREREG.md` | `CROSS_DECADE_VERDICT.md` | 负结论不变（跨年代复现后更可信） |
| R7 | 外部独立复现 | `GITHUB_ASHARE_QUANT_SURVEY.md` §二.1 | 同左 | `wangpage/quant-ashare`：2024–2026 牛市无可落地公开因子 alpha，与本项目负结论一致 |

## 四、本册不包含什么

1. **因子 IC 族**（`SOURCES` 2 族、共 10 因子假设）：其显著性状态由
   `reports/multiple_testing_audit.json` 与 `DSR_IC_FAMILY_VERDICT.md` 承载
   （BH 拒绝 4/7 是**显著性声明**，不是被拒实验），不混入本册。
2. **缺陷修复**（HANDOVER §5.3 的 #1~#17）：是工程债务台账，不是实验判定。
3. **今日三个立项的中间态**：判定以各自 VERDICT 为准。

## 五、已知的一处引用腐烂（登记不修）

`run_multiple_testing_audit.py` 的 `DECLARED_NON_IC_TESTS` 标签按**旧裸名**
引用 6 份报告（如 `PORTFOLIO_AB_REPORT.md`），这些文件现位于 `docs/archive/`。
标签是人类可读串、无运行时加载，故不影响审计数值；但读者按图索骥会断链。
本册表一已按**现实路径**登记；脚本标签的路径更新登记为待办（改标签会动
审计输出文本，须另立小预注册，不顺手改）。

**本登记册不构成投资建议。**
