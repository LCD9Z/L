# 阶段文档归档

本目录分**两批**：

| 批次 | 内容 | 份数 |
|---|---|---|
| 一（原始） | `PHASE8` ~ `PHASE43` 逐阶段文档、合并清单、评审协议、数据卫生审计 | 33 |
| 二（2026-10-18） | 从**根目录**收进来的历史报告（实验过程 / 审计 / 数据评估 / 合并记录 / 计划） | 50 |

**这些文件为历史存档，不再作为当前权威文档维护。** 请优先阅读：

| 想了解 | 看这个 |
|--------|--------|
| 项目当前能力与用法 | [`../../README.md`](../../README.md) |
| 版本演进脉络（已归并） | [`../../CHANGELOG.md`](../../CHANGELOG.md) |
| 当前结论与判定 | [`../../AGENTS.md`](../../AGENTS.md) 的「项目最终结论」表 |
| 代码审计与合并明细 | [`AUDIT_REPORT.md`](AUDIT_REPORT.md) · [`MERGE_1.0_REPORT.md`](MERGE_1.0_REPORT.md) |

归档原因：逐阶段文档维护负担重、检索困难，且部分内容已被后续阶段覆盖。
归档保留完整原文，便于追溯设计决策与实验记录。

> **注意**：`*_PREREG.md` / `*_VERDICT.md` 等**结论源不在此处**，仍留在根目录 ——
> 它们是可追溯性的锚点，藏进归档会让引用链断掉。

<!-- ARCHIVED_LIST:BEGIN -->

## 二、2026-10-18 收敛：根目录历史报告

根目录曾有 **112 份**同级 md。按「结论源留根、过程记录归档」（`ENTRYPOINTS.md` §八 的分级原则），把 **50 份**已完成实验的过程记录移入本目录，根目录降至 **62 份**。

> 移动的是**位置**，不是权威性：这些文件全文保留、未改一字。
> `*_PREREG.md` / `*_VERDICT.md` 等**结论源一律留在根目录**，
> 因为它们是「可追溯性」的锚点，藏进归档目录会让引用链断掉。

### 实验结果报告（21）

| 文件 | 主题（原文标题） |
|---|---|
| [`ADJUSTED_FACTOR_REPORT.md`](ADJUSTED_FACTOR_REPORT.md) | 复权价格 vs 原始价格 · 因子对比报告 |
| [`COMBO_STUDY_REPORT.md`](COMBO_STUDY_REPORT.md) | 组合层研究：尾部剔除 × 持仓分散度（2026-09-26） |
| [`CONCENTRATION_REPORT.md`](CONCENTRATION_REPORT.md) | 持仓分散度研究报告 |
| [`CONTRARIAN_HYPOTHESIS_REPORT.md`](CONTRARIAN_HYPOTHESIS_REPORT.md) | 复合反转打分假设检验报告（H-C1） |
| [`DELISTED_UNIVERSE_REPORT.md`](DELISTED_UNIVERSE_REPORT.md) | 退市股数据可行性报告 |
| [`EXPERT_FILTER_AND_HF4_HV2_REPORT.md`](EXPERT_FILTER_AND_HF4_HV2_REPORT.md) | 专家组合过滤器 + H-F4/H-V2 执行报告（2026-09-30） |
| [`FACTOR_HORIZON_DECAY_REPORT.md`](FACTOR_HORIZON_DECAY_REPORT.md) | 因子持有期衰减研究（2026-09-26） |
| [`FACTOR_HYPOTHESIS_REPORT.md`](FACTOR_HYPOTHESIS_REPORT.md) | A股因子假设检验报告 |
| [`HORIZON_NET_EFFECT_REPORT.md`](HORIZON_NET_EFFECT_REPORT.md) | 持有期净效果研究（2026-09-26） |
| [`IC_DIAGNOSIS_REPORT.md`](IC_DIAGNOSIS_REPORT.md) | IC 虚高诊断 · 执行报告（H-ICX） |
| [`IMPACT_AND_CAPACITY_REPORT.md`](IMPACT_AND_CAPACITY_REPORT.md) | sqrt 冲击成本与容量约束 · 执行报告（H-IMPACT / H-TC） |
| [`MARKET_RISK_GATE_REPORT.md`](MARKET_RISK_GATE_REPORT.md) | 专家圆桌落地报告 · 市场级风险门（2026-09-30） |
| [`PORTFOLIO_AB_REPORT.md`](PORTFOLIO_AB_REPORT.md) | 组合层面对照实验报告（基线动量 A vs H-C1 反转复合 B） |
| [`PORTFOLIO_AB_REPORT_2.md`](PORTFOLIO_AB_REPORT_2.md) | 组合层面 A/B · 第二阶段报告（动态滑点修正） |
| [`PORTFOLIO_AB_REPORT_3.md`](PORTFOLIO_AB_REPORT_3.md) | A/B 第三阶段报告：沪深 300 基准对照（判定 Alpha 的最后一环） |
| [`RERUN_CORRECTED_REPORT.md`](RERUN_CORRECTED_REPORT.md) | 修正数据集后的研究重跑报告 |
| [`SAMPLING_SENSITIVITY_REPORT.md`](SAMPLING_SENSITIVITY_REPORT.md) | 采样敏感性 × 持仓分散度报告 |
| [`SURVIVORSHIP_IMPACT_REPORT.md`](SURVIVORSHIP_IMPACT_REPORT.md) | 幸存者偏差对因子研究的影响报告 |
| [`TAIL_EXCLUSION_REPORT.md`](TAIL_EXCLUSION_REPORT.md) | 尾部剔除实验报告 |
| [`TDX_EVALUATION_REPORT.md`](TDX_EVALUATION_REPORT.md) | TDX 真实数据评估报告 |
| [`UNIVERSE_REPLICATION_REPORT.md`](UNIVERSE_REPLICATION_REPORT.md) | 多股票池重复验证报告 |

### 审计 / 缺陷记录（6）

| 文件 | 主题（原文标题） |
|---|---|
| [`AOCI_INDEX_DEFECT_REPORT.md`](AOCI_INDEX_DEFECT_REPORT.md) | AOCI 索引缺陷报告（目录段被截断，指向另一个仓库） |
| [`AUDIT_REPORT.md`](AUDIT_REPORT.md) | 1.0 项目多角度专业审计报告 |
| [`CALIBRATION_DISCREPANCY_REPORT.md`](CALIBRATION_DISCREPANCY_REPORT.md) | 口径不一致排查报告 |
| [`CODE_REDUNDANCY_AUDIT.md`](CODE_REDUNDANCY_AUDIT.md) | 代码冗余审计报告（CODE_REDUNDANCY_AUDIT） |
| [`CROSS_DECADE_AUDIT.md`](CROSS_DECADE_AUDIT.md) | H-CD 跨年代方向验证 · 独立审阅（海外版） |
| [`SCORE_TURNOVER_DEFECT_REPORT.md`](SCORE_TURNOVER_DEFECT_REPORT.md) | 打分函数「换手率分项静默失效」缺陷报告（2026-09-26） |

### 数据评估 / 可行性（5）

| 文件 | 主题（原文标题） |
|---|---|
| [`ASTOCK_DATA_ASSESSMENT.md`](ASTOCK_DATA_ASSESSMENT.md) | `a-stock-data` 数据可用性评估 |
| [`D_DRIVE_FOLDERS_ANALYSIS.md`](D_DRIVE_FOLDERS_ANALYSIS.md) | D 盘标注文件夹扫描分析报告 |
| [`PIT_L3_920_BACKFILL_FEASIBILITY.md`](PIT_L3_920_BACKFILL_FEASIBILITY.md) | L3 北交所 920 段补数 · 可行性调研（2026-10-15） |
| [`TDX_DATA_ASSESSMENT.md`](TDX_DATA_ASSESSMENT.md) | TDX 历史数据评估报告 |
| [`V49_REFERENCE_ASSESSMENT.md`](V49_REFERENCE_ASSESSMENT.md) | v4.9 参考包评估报告 |

### 合并 / 迁移 / 接线（6）

| 文件 | 主题（原文标题） |
|---|---|
| [`AOCI_INTEGRATION_REPORT.md`](AOCI_INTEGRATION_REPORT.md) | AOCI 接入执行报告（2026-10-07） |
| [`AOCI_INVESTIGATION.md`](AOCI_INVESTIGATION.md) | AOCI 调研报告：能否引入本机并用于后期项目（2026-10-04） |
| [`BRANCH_MERGE_REPORT.md`](BRANCH_MERGE_REPORT.md) | 两条演进线的合并报告（2026-09-30） |
| [`GITHUB_REFERENCE_INTEGRATION_REPORT.md`](GITHUB_REFERENCE_INTEGRATION_REPORT.md) | GitHub 参考项目对比与结合建议报告 |
| [`MERGE_1.0_REPORT.md`](MERGE_1.0_REPORT.md) | 1.0 版本合并报告 |
| [`SIX_ISLANDS_WIRING_REPORT.md`](SIX_ISLANDS_WIRING_REPORT.md) | 六条「能力孤岛」接线报告（2026-09-30） |

### 计划 / 设计过程（6）

| 文件 | 主题（原文标题） |
|---|---|
| [`P0_P1_EXECUTION_REPORT.md`](P0_P1_EXECUTION_REPORT.md) | P0 / P1 落地执行报告 |
| [`P3_PARAMETERIZATION_PLAN.md`](P3_PARAMETERIZATION_PLAN.md) | 审计 P3 · 同构函数参数化方案（2026-10-15） |
| [`PIT_SNAPSHOT_P0_REPORT.md`](PIT_SNAPSHOT_P0_REPORT.md) | PIT 快照 P0 落地报告（L1 上市日/退市日） |
| [`PIT_SNAPSHOT_P2_REPORT.md`](PIT_SNAPSHOT_P2_REPORT.md) | PIT 快照 P2 报告 —— L3 日频估值历史（抽样对账阶段） |
| [`PIT_SNAPSHOT_P3_REPORT.md`](PIT_SNAPSHOT_P3_REPORT.md) | PIT 快照 P3 报告：全市场 L3 回填 —— 崩溃事故、韧性补丁与重启方案 |
| [`RECOMPUTE_EXECUTION_PLAN.md`](RECOMPUTE_EXECUTION_PLAN.md) | 成本口径重算 · 执行清单（方案③下半场） |

### 审阅 / 外部借鉴 / 其他（6）

| 文件 | 主题（原文标题） |
|---|---|
| [`BOLD_IDEAS_2026_10_11.md`](BOLD_IDEAS_2026_10_11.md) | 对项目的大胆建议（2026-10-11） |
| [`CROSS_DECADE_ADDENDUM.md`](CROSS_DECADE_ADDENDUM.md) | H-CD 审阅 addendum（回给实验执行方） |
| [`EXTERNAL_AUDIT_ADOPTION.md`](EXTERNAL_AUDIT_ADOPTION.md) | 外部审阅采纳清单（H-CD 独立审阅 → 本项目） |
| [`L1_分析模板.md`](L1_分析模板.md) | L1 · 优化版分析模板（可直接复制给模型） |
| [`README_CRAWL4AI_A_SHARE.md`](README_CRAWL4AI_A_SHARE.md) | Crawl4AI 接入说明 |
| [`REVIEW_ROUND2_PACKAGE.md`](REVIEW_ROUND2_PACKAGE.md) | 第二轮独立审阅包（2026-10-11 当日产出） |

<!-- ARCHIVED_LIST:END -->
