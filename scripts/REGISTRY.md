# `scripts/` 脚本注册表（SCRIPT REGISTRY）

> **由 `scripts/gen_scripts_registry.py` 生成，不要手改。**
> 改了脚本或引用关系后跑一次 `python scripts/gen_scripts_registry.py`；
> 守卫 `tests/test_scripts_registry.py` 会重算判据并比对，不一致即失败。

**总数 90**　·　`active` 59　·　`one-off` 30　·　`deprecated` 1

## 一、状态判据（可自动重算）

| 状态 | 判据 |
|---|---|
| `active` | 满足任一**可执行引用**：① `tests/`；② `scripts/` 外的生产代码；③ `run_daily.bat` / `run_ci.py` / `pytest.ini`；④ `ENTRYPOINTS.md` §二–§五 登记 |
| `deprecated` | 文档**明文**标注「已被…取代」，且无可执行引用 |
| `one-off` | 其余 —— 有 `__main__` 可手工执行，属历史凭据 |

⚠️ **「被某份报告提到」不算 `active`** —— 只能证明当年跑过一次。

## 二、逐份登记

| # | 脚本 | 职责 | 入口 | 被谁调用 | 状态 |
|---:|------|------|------|----------|------|
| 1 | `_audit_l3_tail_gap.py` | L3 回填收官核查（2026-10-13）：universe vs raw 差额代码的显式定性。 | `python scripts/_audit_l3_tail_gap.py` | —（无可执行引用） | `one-off` |
| 2 | `_study_common.py` | 研究脚本共享 helper（CODE_REDUNDANCY_AUDIT P2 收敛落点）。 | —（helper 模块，供 import） | `tests/test_study_common.py` | `active` |
| 3 | `audit_code_redundancy.py` | 代码冗余审计（**只读**）：AST 归一化重复 + 长函数 + 跨文件同名符号 + 常量重复。 | `python scripts/audit_code_redundancy.py` | `tests/test_code_redundancy_baseline.py` | `active` |
| 4 | `audit_family_schema.py` | 同族产物结构一致性审计（防「同名不同物」）。 | `python scripts/audit_family_schema.py` | `tests/test_audit_family_schema.py` | `active` |
| 5 | `build_certified_dataset_v2.py` | 认证数据集 v2 构建器（源：D:/原始数据 AkShare 全A数据，含退市股与 ST 逐日状态）。 | `python scripts/build_certified_dataset_v2.py` | `tests/test_dataset_incremental_update.py`、`market_regime.py` | `active` |
| 6 | `build_equal_weight_benchmark.py` | 构建**全池**等权全市场基准的日收益序列。 | `python scripts/build_equal_weight_benchmark.py` | —（无可执行引用） | `one-off` |
| 7 | `build_equalweight_benchmark.py` | 从认证数据集构建**等权全A基准**（PIT 股票池口径，零依赖）。 | `python scripts/build_equalweight_benchmark.py` | —（无可执行引用） | `one-off` |
| 8 | `build_security_map.py` | 构建证券代码映射表（DATA_CHANNEL_PREREG 组件 B，②）。 | `python scripts/build_security_map.py` | `tests/test_security_map.py` | `active` |
| 9 | `build_tdx_dataset.py` | 把通达信全市场日线 CSV 转换为项目管线可用的认证数据集。 | `python scripts/build_tdx_dataset.py` | `tests/test_package_layout.py`、`tests/test_python_compat.py` | `active` |
| 10 | `check_recompute.py` | 成本口径重算 · 对账（验收 V1–V4 自动化）。 | `python scripts/check_recompute.py` | `tests/test_check_recompute_caliber.py`、`tests/test_recompute_baseline_stamp.py`、`tests/test_recompute_reconciliation.py` | `active` |
| 11 | `crosscheck_disclosure_sources.py` | 双源披露日交叉校验（DATA_CHANNEL_PREREG 组件 C，判据 D-2~D-5）。 | `python scripts/crosscheck_disclosure_sources.py` | `tests/test_crosscheck_disclosure.py`、`fetch/disclosure_eastmoney.py` | `active` |
| 12 | `csv_to_tdx_day.py` | 把退市股 CSV 转成通达信原生 `.day` 格式。 | `python scripts/csv_to_tdx_day.py` | —（无可执行引用） | `one-off` |
| 13 | `diagnose_newstock_pref.py` | H-N1 替代诊断：五因子是否系统性偏好次新股。 | `python scripts/diagnose_newstock_pref.py` | `ENTRYPOINTS.md` | `active` |
| 14 | `enumerate_delisted_universe.py` | 枚举 A 股全代码空间，找出**退市股**——即 TDX 数据集缺失的样本。 | `python scripts/enumerate_delisted_universe.py` | —（无可执行引用） | `one-off` |
| 15 | `evaluate_form_screen.py` | 形态策略冗余度诊断：Sequoia-X 六策略是否值得进入预注册队列。 | `python scripts/evaluate_form_screen.py` | `tests/test_p3_equivalence_baseline.py` | `active` |
| 16 | `factor_corr_by_window.py` | 跨年代因子相关矩阵（H-CD 补充检验） | `python scripts/factor_corr_by_window.py` | `tests/test_p3_equivalence_baseline.py` | `active` |
| 17 | `fetch_baostock_klines.py` | 从 baostock 拉取全量日线，用于 H-XSRC 外部源交叉验证。 | `python scripts/fetch_baostock_klines.py` | —（无可执行引用） | `deprecated` |
| 18 | `fetch_baostock_xsrc.py` | H-XSRC 数据源 B：baostock 拉取（带「一页陷阱」守卫）。 | `python scripts/fetch_baostock_xsrc.py` | `tests/test_fetch_baostock_timeout.py`、`ENTRYPOINTS.md` | `active` |
| 19 | `fetch_corporate_actions.py` | 从东方财富抓取 A 股分红送股数据，输出为项目公司行动层可消费的 CSV。 | `python scripts/fetch_corporate_actions.py` | `tests/test_package_layout.py`、`ENTRYPOINTS.md` | `active` |
| 20 | `fetch_delisted_full.py` | 拉取退市股全历史日线（腾讯源，end 递推，抗死机）。 | `python scripts/fetch_delisted_full.py` | `tests/test_fetch_baostock_timeout.py`、`ENTRYPOINTS.md` | `active` |
| 21 | `fetch_delisted_klines.py` | 抓取窗口内退市股票的日线，用于量化幸存者偏差。 | `python scripts/fetch_delisted_klines.py` | —（无可执行引用） | `one-off` |
| 22 | `fetch_disclosure_eastmoney.py` | 抓取东财预约披露时间表（DATA_CHANNEL_PREREG 组件 C，A8 数据通道）。 | `python scripts/fetch_disclosure_eastmoney.py` | —（无可执行引用） | `one-off` |
| 23 | `fetch_fundamentals.py` | 抓取并落盘 PIT 财务数据（业绩报表）。 | `python scripts/fetch_fundamentals.py` | `tests/test_fundamentals_source.py` | `active` |
| 24 | `gen_evidence_index.py` | 生成 `EVIDENCE_INDEX.md`：把「报告引用的证据 JSON」编成可核对的索引。 | `python scripts/gen_evidence_index.py` | `tests/test_evidence_index.py`、`runtime/receipt.py` | `active` |
| 25 | `gen_layout_doc.py` | 从真实仓库状态生成 `DIRECTORY_LAYOUT.md`（目录全景）。 | `python scripts/gen_layout_doc.py` | `tests/test_layout_doc_in_sync.py` | `active` |
| 26 | `gen_receipt.py` | 生成收据（A7）：`runtime/receipt.py` 的命令行入口。 | `python scripts/gen_receipt.py` | `tests/test_receipt.py` | `active` |
| 27 | `gen_scripts_registry.py` | 生成 `scripts/REGISTRY.md` —— `scripts/` 下每个脚本的**逐份**登记（A2）。 | `python scripts/gen_scripts_registry.py` | `tests/test_scripts_registry.py` | `active` |
| 28 | `list_uncovered_modules.py` | 列出**无直接测试覆盖**的源码模块（HANDOVER §7 第 4 项：剩余 9 个）。 | `python scripts/list_uncovered_modules.py` | —（无可执行引用） | `one-off` |
| 29 | `merge_delisted_into_dataset.py` | 把窗口内退市股并入 TDX 认证数据集。 | `python scripts/merge_delisted_into_dataset.py` | —（无可执行引用） | `one-off` |
| 30 | `microstructure_ic.py` | PREREG_02 的执行脚本：量价微观结构因子的 IC 检验与 Double Sort。 | `python scripts/microstructure_ic.py` | `tests/test_microstructure_ic.py` | `active` |
| 31 | `migrate_root_docs.py` | 根目录文档收敛（B3）：把历史报告移入 `docs/archive/`，并**重写全部相对链接**。 | `python scripts/migrate_root_docs.py` | `tests/test_doc_layout.py` | `active` |
| 32 | `migrate_tracking_records.py` | 迁移 lost 系工作目录的 L3 推荐记录到本项目 tracking.db。 | `python scripts/migrate_tracking_records.py` | —（无可执行引用） | `one-off` |
| 33 | `patch_limit_ratio.py` | 把已构建数据集里的 ``limit_ratio`` 按 **PIT 正确规则**重算并回写。 | `python scripts/patch_limit_ratio.py` | —（无可执行引用） | `one-off` |
| 34 | `regime_attribution.py` | Regime 分层归因：把「六窗口全负超额」按市场状态切片（**只做尸检**）。 | `python scripts/regime_attribution.py` | `tests/test_regime_attribution.py` | `active` |
| 35 | `repair_tdx_metadata.py` | 为已导出的每股 CSV 重建 .metadata.json（修复用）。 | `python scripts/repair_tdx_metadata.py` | `tests/test_package_layout.py` | `active` |
| 36 | `rerun_studies_corrected.py` | 用修正后的数据集（含 180 只退市股）重跑全部既有研究。 | `python scripts/rerun_studies_corrected.py` | —（无可执行引用） | `one-off` |
| 37 | `run_adjusted_factor_study.py` | 复权价格 vs 原始价格的因子对比研究。 | `python scripts/run_adjusted_factor_study.py` | —（无可执行引用） | `one-off` |
| 38 | `run_alpha_gap_probe.py` | Alpha 能力缺口探查：基准错配与因子冗余的实测。 | `python scripts/run_alpha_gap_probe.py` | —（无可执行引用） | `one-off` |
| 39 | `run_analysis.py` | run_analysis.py - AI股神系统 · 分析入口（L2 落地） | `python scripts/run_analysis.py` | `daily_stock_pick.py`、`prompt_engine.py` | `active` |
| 40 | `run_astock_reconciliation.py` | 抽样对账：`a-stock-data` 的行情层 vs 我方通达信原生 `.day`。 | `python scripts/run_astock_reconciliation.py` | —（无可执行引用） | `one-off` |
| 41 | `run_backtest.py` | 单股日线回测 CLI（L1 遗留）：给定 code + 区间，跑 `backtest_engine.backtest`。 | `python scripts/run_backtest.py` | —（无可执行引用） | `one-off` |
| 42 | `run_c2_ab.py` | C2 条件 A/B —— 产业策略师「风格拥挤度 gate」与估值分析师「上轨排除」。 | `python scripts/run_c2_ab.py` | `tests/test_c2_ab_variants.py` | `active` |
| 43 | `run_combo_study.py` | 组合层研究：**尾部剔除 × 持仓分散度** 的联合效果。 | `python scripts/run_combo_study.py` | —（无可执行引用） | `one-off` |
| 44 | `run_concentration_study.py` | 持仓分散度研究：提高分散度能否降低抽样噪声？ | `python scripts/run_concentration_study.py` | `tests/test_annualization_conventions.py`、`tests/test_research_artifacts.py`、`tests/test_study_common.py` | `active` |
| 45 | `run_contrarian_portfolio.py` | 组合层面对照实验：基线动量(A) vs H-C1 反转复合(B)，**同一框架** A/B。 | `python scripts/run_contrarian_portfolio.py` | `tests/test_annualization_conventions.py`、`tests/test_contrarian_costs.py`、`tests/test_research_artifacts.py` +4 | `active` |
| 46 | `run_contrarian_study.py` | 复合「反转 + 低波 + 小规模 + 非流动性」打分假设检验。 | `python scripts/run_contrarian_study.py` | `tests/test_study_common.py` | `active` |
| 47 | `run_cost_model_check.py` | 成本模型修正的敏感性检查（真实 TDX 数据，观察性对照）。 | `python scripts/run_cost_model_check.py` | `tests/test_cost_authority.py`、`tests/test_research_artifacts.py`、`ENTRYPOINTS.md` | `active` |
| 48 | `run_daily_factor_screen.py` | 五因子日度选股（v2 认证数据源版，零第三方依赖）。 | `python scripts/run_daily_factor_screen.py` | `factors/factor_ic_lab.py` | `active` |
| 49 | `run_daily_screening.py` | AI股神团队 - 每日选股执行脚本 | `python scripts/run_daily_screening.py` | —（无可执行引用） | `one-off` |
| 50 | `run_delta_statistics_audit.py` | Δ 型策略结论的配对统计量补记。 | `python scripts/run_delta_statistics_audit.py` | —（无可执行引用） | `one-off` |
| 51 | `run_disclosure_factor_study.py` | H-D2 检验：定期报告**预约披露日变更次数**是否预示负面收益。 | `python scripts/run_disclosure_factor_study.py` | `tests/test_disclosure_factor_study.py` | `active` |
| 52 | `run_expert_filter_study.py` | 专家组合过滤器研究：逐条件归因 + 组合对比。 | `python scripts/run_expert_filter_study.py` | `tests/test_expert_filter.py`、`tests/test_expert_filter_c2.py`、`tests/test_study_common.py` +1 | `active` |
| 53 | `run_factor_correlation.py` | 五因子截面相关性与组合增量检验（v2 数据源，零第三方依赖）。 | `python scripts/run_factor_correlation.py` | `ENTRYPOINTS.md` | `active` |
| 54 | `run_factor_orthogonality.py` | 因子正交化后的方向稳健性（H-ORTH） | `python scripts/run_factor_orthogonality.py` | `tests/test_p3_equivalence_baseline.py`、`ENTRYPOINTS.md` | `active` |
| 55 | `run_factor_study.py` | 在 TDX 数据集上检验经济逻辑驱动的因子假设。 | `python scripts/run_factor_study.py` | —（无可执行引用） | `one-off` |
| 56 | `run_feishu_acceptance.py` | 飞书 notify 模块真实凭据验收（不接触明文）。 | `python scripts/run_feishu_acceptance.py` | —（无可执行引用） | `one-off` |
| 57 | `run_five_factor_ab.py` | H-F5 五因子组合 A/B 实验（事前登记见 `FIVE_FACTOR_PREREG.md`）。 | `python scripts/run_five_factor_ab.py` | `ENTRYPOINTS.md` | `active` |
| 58 | `run_fundamental_factor_study.py` | 基本面因子横截面 IC 检验（PIT 财务数据）。 | `python scripts/run_fundamental_factor_study.py` | `tests/test_dataset_fingerprint.py`、`tests/test_deflated_family.py`、`tests/test_receipt.py` | `active` |
| 59 | `run_horizon_study.py` | 持有期净效果研究：5 / 10 / 20 / 40 日持有的**组合层面净收益**对比。 | `python scripts/run_horizon_study.py` | —（无可执行引用） | `one-off` |
| 60 | `run_ic_diagnosis.py` | IC 虚高诊断（H-ICX，登记见 `IC_DIAGNOSIS_PREREG.md`）。 | `python scripts/run_ic_diagnosis.py` | `ENTRYPOINTS.md` | `active` |
| 61 | `run_industry_ic_attribution.py` | 行业分层 IC 归因：直接检验「IC 强显著但组合不赚钱」的产业解释。 | `python scripts/run_industry_ic_attribution.py` | `tests/test_pit_snapshot_scripts.py` | `active` |
| 62 | `run_l3_valuation_reconciliation.py` | L3 估值历史的**抽样对账**（设计文档规定的「接入前必过闸门」）。 | `python scripts/run_l3_valuation_reconciliation.py` | `tests/test_pit_snapshot_scripts.py` | `active` |
| 63 | `run_limit_structure_study.py` | H-D4 检验：涨跌停结构（一字涨停占比）是否预示负面收益。 | `python scripts/run_limit_structure_study.py` | —（无可执行引用） | `one-off` |
| 64 | `run_multiple_testing_audit.py` | 多重检验校正审计：把「跑了很多次」算进已发布结论的显著性里。 | `python scripts/run_multiple_testing_audit.py` | `tests/test_rejected_registry.py` | `active` |
| 65 | `run_pipeline.py` | V3.4 market-wide runner. | `python scripts/run_pipeline.py` | —（无可执行引用） | `one-off` |
| 66 | `run_pit_gap_check.py` | PIT 快照断更检测 + 告警。 | `python scripts/run_pit_gap_check.py` | `tests/test_pit_snapshot_scripts.py` | `active` |
| 67 | `run_pit_snapshot_ingest.py` | PIT 快照采集：L1 上市/退市日（baostock）+ L2 申万行业变迁史（申万官网 xls）。 | `python scripts/run_pit_snapshot_ingest.py` | `tests/test_data_contracts_num.py`、`tests/test_pit_snapshot_scripts.py` | `active` |
| 68 | `run_portfolio_backtest.py` | 多股组合回测 CLI（Phase 5，L1/L2 遗留）：读 universe JSON，逐股取数后跑组合回测。 | `python scripts/run_portfolio_backtest.py` | `tests/test_scripts_registry.py` | `active` |
| 69 | `run_real_data_collection.py` | 真实行情采集 CLI（L1 遗留）：按 `--symbols` 列表取材并落盘到 `real_data/`。 | `python scripts/run_real_data_collection.py` | `tests/test_scripts_registry.py` | `active` |
| 70 | `run_recompute.py` | 成本口径重算 · 驱动脚本（方案③下半场）。 | `python scripts/run_recompute.py` | `tests/test_check_recompute_caliber.py`、`tests/test_no_foreign_pyc.py`、`tests/test_recompute_baseline_stamp.py` | `active` |
| 71 | `run_regime_overlay_study.py` | ADX 市场状态仓位叠加层 · 观察性检验（真实 TDX 数据）。 | `python scripts/run_regime_overlay_study.py` | `tests/test_research_artifacts.py`、`ENTRYPOINTS.md` | `active` |
| 72 | `run_sampling_sensitivity_study.py` | 采样敏感性研究：提高持仓分散度能否让回测结论稳定下来？ | `python scripts/run_sampling_sensitivity_study.py` | `tests/test_annualization_conventions.py`、`tests/test_study_regressions.py` | `active` |
| 73 | `run_signal_diagnosis.py` | 基线策略的因子暴露诊断：把"策略亏钱"与"因子暴露"连成因果链。 | `python scripts/run_signal_diagnosis.py` | `ENTRYPOINTS.md` | `active` |
| 74 | `run_st_reversal_study.py` | H-D3 检验：ST 困境反转（ST 组未来收益是否高于非 ST 组）。 | `python scripts/run_st_reversal_study.py` | `tests/test_st_reversal_study.py` | `active` |
| 75 | `run_stop_loss_ab.py` | ATR 移动止损 A/B 研究：把「能力孤岛」接进回测闭环后的实证。 | `python scripts/run_stop_loss_ab.py` | —（无可执行引用） | `one-off` |
| 76 | `run_survivorship_study.py` | 幸存者偏差对因子研究的影响：把退市股并入数据集，对比因子 IC。 | `python scripts/run_survivorship_study.py` | —（无可执行引用） | `one-off` |
| 77 | `run_tail_exclusion_study.py` | 尾部剔除实验：把因子结论转化为**事前设定**的单一修改并检验。 | `python scripts/run_tail_exclusion_study.py` | `tests/test_annualization_conventions.py`、`tests/test_research_artifacts.py`、`tests/test_study_common.py` +2 | `active` |
| 78 | `run_tdx_evaluation.py` | 在 TDX 数据集上运行真实 Alpha 评估。 | `python scripts/run_tdx_evaluation.py` | —（无可执行引用） | `one-off` |
| 79 | `run_tdx_rolling_eval.py` | 多窗口滚动样本外稳健性检验。 | `python scripts/run_tdx_rolling_eval.py` | `tests/test_alpha_release_gate.py`、`tests/test_bench_meta_resolution.py`、`conftest.py` +1 | `active` |
| 80 | `run_tdx_universe_ic.py` | 全市场五因子 IC 研究（原生 TDX 数据，原始价 vs 前复权对照）。 | `python scripts/run_tdx_universe_ic.py` | `tests/test_cross_decade_consistency.py`、`tests/test_p3_equivalence_baseline.py`、`ENTRYPOINTS.md` | `active` |
| 81 | `run_tracking.py` | run_tracking.py - L3 回测闭环 CLI | `python scripts/run_tracking.py` | `tracking.py` | `active` |
| 82 | `run_universe_replication.py` | 多股票池独立重复验证：V0（基线）vs V1（剔除 ret_20 尾部）是否可复现。 | `python scripts/run_universe_replication.py` | `tests/test_annualization_conventions.py`、`tests/test_study_common.py` | `active` |
| 83 | `run_valuation_weight_ab.py` | 估值权重调节器 A/B：把 `pb`/`pe_ttm` 从「排序因子」升级为「仓位权重」的实证。 | `python scripts/run_valuation_weight_ab.py` | —（无可执行引用） | `one-off` |
| 84 | `run_walk_forward.py` | 单股 walk-forward 对比 CLI（L1 遗留）：`walk_forward.compare` 的前后段对照。 | `python scripts/run_walk_forward.py` | `tests/test_scripts_registry.py` | `active` |
| 85 | `run_xsrc_daemon.py` | H-XSRC 拉取守护：低频重试直至完成（应对 IP 级限流）。 | `python scripts/run_xsrc_daemon.py` | `ENTRYPOINTS.md` | `active` |
| 86 | `run_xsrc_fetch.py` | H-XSRC 拉取协调器：并行启动 N 个分片并等待全部结束。 | `python scripts/run_xsrc_fetch.py` | `ENTRYPOINTS.md` | `active` |
| 87 | `run_xsrc_ic.py` | H-XSRC：跨源验证 —— 在独立源（腾讯）上重算因子 IC，对比主干符号。 | `python scripts/run_xsrc_ic.py` | `tests/test_p3_equivalence_baseline.py`、`ENTRYPOINTS.md` | `active` |
| 88 | `scan_silent_failures.py` | 静默失效扫描器（silent-failure scanner）。 | `python scripts/scan_silent_failures.py` | —（无可执行引用） | `one-off` |
| 89 | `summarize_cross_decade.py` | 跨年代方向验证 · 判定汇总（H-CD） | `python scripts/summarize_cross_decade.py` | —（无可执行引用） | `one-off` |
| 90 | `update_certified_dataset.py` | 认证数据集**增量更新**：用新快照追加交易日。 | `python scripts/update_certified_dataset.py` | `tests/test_dataset_incremental_update.py` | `active` |

## 三、治理结论

- **无 `__main__` 守卫**：1 个 —— `_study_common.py`
- **零可执行引用**（既无测试、无生产代码、不在正式清单）：31 个

  `_audit_l3_tail_gap.py`、`build_equal_weight_benchmark.py`、`build_equalweight_benchmark.py`、`csv_to_tdx_day.py`、`enumerate_delisted_universe.py`、`fetch_baostock_klines.py`、`fetch_delisted_klines.py`、`fetch_disclosure_eastmoney.py`、`list_uncovered_modules.py`、`merge_delisted_into_dataset.py`、`migrate_tracking_records.py`、`patch_limit_ratio.py`、`rerun_studies_corrected.py`、`run_adjusted_factor_study.py`、`run_alpha_gap_probe.py`、`run_astock_reconciliation.py`、`run_backtest.py`、`run_combo_study.py`、`run_daily_screening.py`、`run_delta_statistics_audit.py`、`run_factor_study.py`、`run_feishu_acceptance.py`、`run_horizon_study.py`、`run_limit_structure_study.py`、`run_pipeline.py`、`run_stop_loss_ab.py`、`run_survivorship_study.py`、`run_tdx_evaluation.py`、`run_valuation_weight_ab.py`、`scan_silent_failures.py`、`summarize_cross_decade.py`

> `one-off` / 零引用**不等于该删** —— 它们是历史凭据，删掉会破坏可追溯性。
> 本节的作用是让「谁在用」从**猜**变成**查**。

## 四、新增脚本的纪律

1. 新建 `scripts/*.py` 后**必须**重跑生成器，否则守卫失败（防「悄悄加一个脚本」）；
2. 若它是正式入口/研究入口，同步登记到 `ENTRYPOINTS.md` 对应章节；
3. 若它已被取代，加进本模块的 `DEPRECATED` 表并**附可检索的依据原话**；
4. 纯 helper 用 `_` 前缀（允许无 `__main__`），否则必须有 `__main__` 守卫。

