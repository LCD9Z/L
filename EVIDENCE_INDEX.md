# 证据索引（EVIDENCE_INDEX）

> **自动生成** —— 由 `scripts/gen_evidence_index.py` 产出，**请勿手改**。
> 重新生成：`python scripts/gen_evidence_index.py`

## 这份索引解决什么

报告里的每个数字都来自 `reports/*.json`。这些文件此前被 `.gitignore` 整体排除，
导致**报告与证据脱钩** —— 换会话/换人时无法判断「这个数字怎么来的」。

现策略：**跟踪 `reports/*.json`**（证据快照），忽略日志 / `_*` 临时探针 /
`*.partial` 中间产物 / 子目录。判定规则 —— **未跟踪的 = 可重生成的中间产物；
已跟踪的 = 证据快照**。

## ⚠️ 读法（三点）

1. **sha256 仅供核对，不作门禁** —— 数据更新后重跑会改变哈希，属正常。
   需要核验时用 `python scripts/gen_evidence_index.py --check`。
2. **「生成脚本」列为 `—` 不等于无法复现** —— 多数脚本把输出路径作为 `--out` 参数，
   文件名不出现在代码里。此时以**引用它的报告**中的命令行为准。
3. **同一份证据可能被多份报告引用** —— 这属正常（如 `five_factor_ab_v2.json` 被 4 份引用）。

**当前跟踪 55 份证据。**

---

| 证据文件 | 字节 | sha256 | 引用它的报告 | 生成脚本 |
|------|-----:|--------|------|------|
| `adx_attr_w1.json` | 595 | `96f012a93f91` | （暂无报告直接引用） | — |
| `adx_attr_w2.json` | 597 | `0eb1abd6cf69` | （暂无报告直接引用） | — |
| `adx_attr_w3.json` | 595 | `094810537084` | （暂无报告直接引用） | — |
| `adx_attr_w4.json` | 593 | `297351b722ae` | （暂无报告直接引用） | — |
| `astock_reconciliation.json` | 1,779 | `98f8ea83515c` | ASTOCK_DATA_ASSESSMENT.md | — |
| `combo_study_h20.json` | 6,923 | `1fcfb4b6164d` | BENCHMARK_ALIGNMENT.md<br>COMBO_STUDY_REPORT.md<br>WORKLOG.md | — |
| `combo_study_h20_fixed.json` | 6,896 | `a59bd8921f48` | BENCHMARK_ALIGNMENT.md<br>COMBO_STUDY_REPORT.md | — |
| `concentration_with_p.json` | 5,768 | `042adf2cada8` | BENCHMARK_ALIGNMENT.md<br>P0_P1_EXECUTION_REPORT.md | — |
| `contrarian_ab_with_p.json` | 2,407 | `592095aeaac3` | BENCHMARK_ALIGNMENT.md<br>P0_P1_EXECUTION_REPORT.md | — |
| `cost_model_check.json` | 1,452 | `c844f528f28a` | STEP1_3_EXECUTION_REPORT.md | `run_multiple_testing_audit.py` |
| `cost_model_check_with_p.json` | 1,765 | `976d7fa2da14` | BENCHMARK_ALIGNMENT.md<br>P0_P1_EXECUTION_REPORT.md | — |
| `daily_screen_2026-09-19.json` | 4,746 | `798f50c6f931` | STEP1_3_EXECUTION_REPORT.md | — |
| `decay_h10.json` | 11,993 | `ded0486f1d6d` | （暂无报告直接引用） | — |
| `decay_h20.json` | 11,859 | `b3021856a13c` | （暂无报告直接引用） | — |
| `decay_h40.json` | 11,770 | `0466fe78aaff` | （暂无报告直接引用） | — |
| `decay_h5.json` | 11,901 | `3fef6931292f` | （暂无报告直接引用） | — |
| `delta_statistics_audit.json` | 4,618 | `68643ac24a78` | P0_P1_EXECUTION_REPORT.md | — |
| `ew_benchmark_v3.json` | 45,808 | `07a654371278` | BENCHMARK_ALIGNMENT.md<br>P0_P1_EXECUTION_REPORT.md<br>SIX_ISLANDS_WIRING_REPORT.md | `build_equal_weight_benchmark.py` |
| `expert_filter_study.json` | 4,366 | `cb29912d2a23` | BENCHMARK_ALIGNMENT.md<br>EXPERT_FILTER_AND_HF4_HV2_REPORT.md | `run_expert_filter_study.py` |
| `five_factor_ab_v2.json` | 5,164 | `5df9351e0b5f` | BENCHMARK_ALIGNMENT.md<br>EXPERT_FILTER_AND_HF4_HV2_REPORT.md<br>IMPACT_AND_CAPACITY_REPORT.md<br>TURNOVER_CAPACITY_PREREG.md | `gen_evidence_index.py` |
| `fixedpool_v2.json` | 1,480 | `32064baa08d3` | （暂无报告直接引用） | `run_multiple_testing_audit.py` |
| `fixedpool_v3.json` | 1,480 | `3dfc8c4d79f5` | （暂无报告直接引用） | `run_multiple_testing_audit.py` |
| `hd1_disclosure_advance.json` | 1,331 | `67b72c49a2ad` | ALPHA_HYPOTHESIS_PREREG_HD1.md<br>HANDOVER.md | — |
| `hd2_disclosure_revisions.json` | 1,178 | `bbdec516b597` | ALPHA_HYPOTHESIS_BACKLOG.md<br>ALPHA_HYPOTHESIS_PREREG_HD2.md<br>HANDOVER.md | `run_disclosure_factor_study.py` |
| `hd3_st_reversal.json` | 1,637 | `5171f35be6ec` | ALPHA_HYPOTHESIS_PREREG_HD3.md<br>HANDOVER.md | `run_st_reversal_study.py` |
| `hd4_limit_structure.json` | 1,280 | `fdf2a0e6882e` | ALPHA_HYPOTHESIS_PREREG_HD4.md<br>HANDOVER.md | `run_limit_structure_study.py` |
| `horizon_study.json` | 6,047 | `40c805f3e44b` | BENCHMARK_ALIGNMENT.md<br>HORIZON_NET_EFFECT_REPORT.md<br>SCORE_TURNOVER_DEFECT_REPORT.md<br>WORKLOG.md | `run_horizon_study.py` |
| `horizon_study_turnover_fixed.json` | 5,968 | `65d635d22311` | BENCHMARK_ALIGNMENT.md<br>SCORE_TURNOVER_DEFECT_REPORT.md<br>WORKLOG.md | — |
| `ic_diagnosis.json` | 3,164 | `0406cd83909d` | IC_DIAGNOSIS_PREREG.md<br>IC_DIAGNOSIS_REPORT.md | — |
| `impact_cost.json` | 6,444 | `bb88751fe5da` | IMPACT_AND_CAPACITY_REPORT.md<br>IMPACT_COST_PREREG.md | — |
| `industry_ic_attribution.json` | 58,556 | `318ab564785f` | BENCHMARK_ALIGNMENT.md | `run_industry_ic_attribution.py` |
| `industry_ic_attribution_sw.json` | 69,367 | `9b6fec09ca0b` | （暂无报告直接引用） | `run_industry_ic_attribution.py` |
| `l3_reconciliation.json` | 909 | `2b73609df254` | PIT_SNAPSHOT_P2_REPORT.md | — |
| `multiple_testing_audit.json` | 9,523 | `7b1c929483c4` | P0_P1_EXECUTION_REPORT.md | `run_multiple_testing_audit.py` |
| `pit_gaps.json` | 1,620 | `051603363874` | （暂无报告直接引用） | — |
| `pit_l1_reconciliation.json` | 841 | `b674dabad7fe` | PIT_SNAPSHOT_P0_REPORT.md | — |
| `pit_l2_reconciliation.json` | 876 | `4129192e022a` | （暂无报告直接引用） | — |
| `regime_overlay_const05_pilot.json` | 1,038 | `784bcbaee4d1` | STEP1_3_EXECUTION_REPORT.md | — |
| `regime_overlay_study_w5.json` | 820 | `aa6b5726baa7` | （暂无报告直接引用） | — |
| `silent_scan.json` | 34,601 | `cb09c2c8c796` | PROJECT_HEALTH_AUDIT.md | — |
| `stop_loss_ab.json` | 2,327 | `80c7e5f5a1e6` | BENCHMARK_ALIGNMENT.md | `run_stop_loss_ab.py` |
| `stop_loss_ab_5win.json` | 3,458 | `883716b25363` | BENCHMARK_ALIGNMENT.md<br>SIX_ISLANDS_WIRING_REPORT.md | — |
| `tail_exclusion_with_p.json` | 4,164 | `28927b7c2e42` | BENCHMARK_ALIGNMENT.md<br>FACTOR_HORIZON_DECAY_REPORT.md<br>P0_P1_EXECUTION_REPORT.md | `run_horizon_study.py` |
| `tc_t0.json` | 6,432 | `595ad74d9161` | IMPACT_AND_CAPACITY_REPORT.md<br>TURNOVER_CAPACITY_PREREG.md | — |
| `tc_t2.json` | 6,433 | `c3174caffcca` | IMPACT_AND_CAPACITY_REPORT.md<br>TURNOVER_CAPACITY_PREREG.md | — |
| `tdx_ic_full.json` | 2,339 | `be7849a47da2` | CROSS_DECADE_AUDIT.md<br>EXPERT_FILTER_AND_HF4_HV2_REPORT.md<br>FACTOR_SUBSET_PREREG.md | — |
| `v2_factor_study.json` | 11,906 | `fa5aa1137fa7` | FIVE_FACTOR_PREREG.md<br>IC_DIAGNOSIS_PREREG.md<br>IC_DIAGNOSIS_REPORT.md<br>STEP1_3_EXECUTION_REPORT.md | `run_multiple_testing_audit.py`<br>`run_tdx_universe_ic.py` |
| `v2_rolling_eval_ew.json` | 5,698 | `8dee8757ce05` | ALPHA_CAPABILITY_GAP_ANALYSIS.md<br>BENCHMARK_ALIGNMENT.md<br>WORKLOG.md | `run_multiple_testing_audit.py` |
| `v2_rolling_eval_w6.json` | 798 | `3554bec67bc1` | BENCHMARK_ALIGNMENT.md<br>STEP1_3_EXECUTION_REPORT.md | — |
| `v3_alpha_gap_probe.json` | 2,473 | `4c354ef681dc` | BENCHMARK_ALIGNMENT.md | — |
| `v3_alpha_gap_probe_coverage.json` | 1,180 | `57a23de20ead` | BENCHMARK_ALIGNMENT.md | — |
| `v3_fundamental_factor_study.json` | 11,136 | `3652c340c206` | （暂无报告直接引用） | — |
| `v3_rolling_eval_ew.json` | 5,684 | `0e26a4060d66` | BENCHMARK_ALIGNMENT.md | — |
| `v3_rolling_eval_ew_full.json` | 6,197 | `1becb18f2bf5` | BENCHMARK_ALIGNMENT.md<br>P0_P1_EXECUTION_REPORT.md | `run_multiple_testing_audit.py` |
| `valuation_weight_ab.json` | 2,192 | `1ee76356ac9c` | BENCHMARK_ALIGNMENT.md<br>SIX_ISLANDS_WIRING_REPORT.md | `run_valuation_weight_ab.py` |

---

## 未被任何报告直接引用的证据

以下文件已跟踪但暂无报告直接引用 —— 可能是**中间产物**或**脚本内部消费**。
保留它们是为可复现性；若确认无用，应移出 `reports/` 或加 `_` 前缀使其被忽略。

- `adx_attr_w1.json`
- `adx_attr_w2.json`
- `adx_attr_w3.json`
- `adx_attr_w4.json`
- `decay_h10.json`
- `decay_h20.json`
- `decay_h40.json`
- `decay_h5.json`
- `fixedpool_v2.json`
- `fixedpool_v3.json`
- `industry_ic_attribution_sw.json`
- `pit_gaps.json`
- `pit_l2_reconciliation.json`
- `regime_overlay_study_w5.json`
- `v3_fundamental_factor_study.json`

---

**声明**：本索引只描述「哪些证据被跟踪」，**不构成任何策略有效性判断**。
**本文件不构成投资建议。**
