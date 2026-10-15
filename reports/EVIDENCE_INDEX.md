# 证据索引（EVIDENCE_INDEX）

> **自动生成** —— 由 `scripts/gen_evidence_index.py` 产出，**请勿手改**。
> 重新生成：`python scripts/gen_evidence_index.py`

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

**当前跟踪 129 份证据。**

---

| 证据文件 | 字节 | sha256 | 引用它的报告 | 生成脚本 |
|------|-----:|--------|------|------|
| `_turnover_fix_probe.json` | 919 | `2da35beca972` | P005_3_3_BENCHMARK_PREREG.md | — |
| `ab_n3_batchA.json` ⚠️ | 1,933 | `1e00a5afe784` | BENCHMARK_ALIGNMENT.md | — |
| `ab_n3_w3.json` | 1,262 | `4c964bca7b09` | BENCHMARK_ALIGNMENT.md | — |
| `ab_n3_w4.json` | 1,268 | `3e03b256e03a` | BENCHMARK_ALIGNMENT.md | — |
| `ab_n3_w5.json` | 1,260 | `32220c37299d` | BENCHMARK_ALIGNMENT.md | — |
| `adx_attr_w1.json` | 595 | `96f012a93f91` | BENCHMARK_ALIGNMENT.md<br>COST_BASELINE_PENDING_RECOMPUTE.md | — |
| `adx_attr_w2.json` | 597 | `0eb1abd6cf69` | BENCHMARK_ALIGNMENT.md | — |
| `adx_attr_w3.json` | 595 | `094810537084` | BENCHMARK_ALIGNMENT.md | — |
| `adx_attr_w4.json` | 593 | `297351b722ae` | BENCHMARK_ALIGNMENT.md | — |
| `ah_codes.json` | 2,569 | `4e543e108146` | （暂无报告直接引用） | `run_l3_valuation_reconciliation.py` |
| `astock_reconciliation.json` | 1,779 | `98f8ea83515c` | ASTOCK_DATA_ASSESSMENT.md | — |
| `combo_study_h20.json` ⚠️ | 6,923 | `1fcfb4b6164d` | BENCHMARK_ALIGNMENT.md<br>COMBO_STUDY_REPORT.md<br>COST_BASELINE_PENDING_RECOMPUTE.md<br>WORKLOG.md | — |
| `combo_study_h20_fixed.json` ⚠️ | 6,896 | `a59bd8921f48` | BENCHMARK_ALIGNMENT.md<br>COMBO_STUDY_REPORT.md<br>COST_BASELINE_PENDING_RECOMPUTE.md | — |
| `concentration_with_p.json` | 5,768 | `042adf2cada8` | BENCHMARK_ALIGNMENT.md<br>P0_P1_EXECUTION_REPORT.md | — |
| `contrarian_ab_with_p.json` | 2,407 | `592095aeaac3` | BENCHMARK_ALIGNMENT.md<br>COST_BASELINE_PENDING_RECOMPUTE.md<br>P005_3_3_BENCHMARK_PREREG.md<br>P0_P1_EXECUTION_REPORT.md | — |
| `cost_model_check.json` ⚠️ | 1,452 | `c844f528f28a` | BENCHMARK_ALIGNMENT.md<br>COST_BASELINE_PENDING_RECOMPUTE.md<br>STEP1_3_EXECUTION_REPORT.md | `run_multiple_testing_audit.py` |
| `cost_model_check_with_p.json` | 1,765 | `976d7fa2da14` | BENCHMARK_ALIGNMENT.md<br>COST_BASELINE_PENDING_RECOMPUTE.md<br>P0_P1_EXECUTION_REPORT.md | — |
| `cross_decade/CORR.json` | 2,833 | `f43f68059e9e` | AGENTS.md<br>CROSS_DECADE_REVIEW_RESPONSE.md<br>CROSS_DECADE_VERDICT.md<br>DATA_ASSET_REGISTRY.md<br>FACTOR_ORTHOGONALITY_PREREG.md<br>FACTOR_SUBSET_PREREG.md | `factor_corr_by_window.py` |
| `cross_decade/ORTH.json` | 8,997 | `b1fddcf0b6b1` | DATA_ASSET_REGISTRY.md<br>FACTOR_ORTHOGONALITY_PREREG.md<br>FACTOR_ORTHOGONALITY_VERDICT.md<br>REVIEW_ROUND2_PACKAGE.md<br>XSOURCE_VALIDATION_PREREG.md<br>XSOURCE_VALIDATION_VERDICT.md | `run_factor_orthogonality.py`<br>`run_xsrc_ic.py` |
| `cross_decade/R.json` | 9,924 | `bde915cfd519` | AGENTS.md<br>CROSS_DECADE_ADDENDUM.md<br>CROSS_DECADE_REVIEW_RESPONSE.md<br>CROSS_DECADE_VERDICT.md<br>DATA_ASSET_REGISTRY.md<br>FACTOR_ORTHOGONALITY_PREREG.md<br>FACTOR_SUBSET_PREREG.md | `factor_corr_by_window.py` |
| `cross_decade/VERDICT.json` | 806 | `4a6e2f30d934` | CROSS_DECADE_ADDENDUM.md<br>CROSS_DECADE_AUDIT.md<br>DATA_ASSET_REGISTRY.md<br>EXTERNAL_AUDIT_ADOPTION.md | `run_xsrc_ic.py`<br>`summarize_cross_decade.py` |
| `cross_decade/W1.json` | 9,677 | `9a8113be0468` | CROSS_DECADE_ADDENDUM.md<br>PIT_SNAPSHOT_P0_REPORT.md | `gen_evidence_index.py` |
| `cross_decade/W1a.json` | 9,448 | `c2432d7ffef5` | W1_SPLIT_PREREG.md<br>W1_SPLIT_VERDICT.md | — |
| `cross_decade/W1b.json` | 9,622 | `e01b3b5b325a` | W1_SPLIT_PREREG.md<br>W1_SPLIT_VERDICT.md | — |
| `cross_decade/W2.json` | 9,854 | `f26111ff4060` | （暂无报告直接引用） | — |
| `cross_decade/W3.json` | 9,892 | `babbd6bcaa6c` | （暂无报告直接引用） | — |
| `cross_decade/W4.json` | 9,922 | `31e5fd58895c` | （暂无报告直接引用） | — |
| `cross_decade/W5.json` | 9,925 | `ca3815c012af` | （暂无报告直接引用） | — |
| `cross_decade/_intermediate/VERDICT_partial.json` | 1,050 | `58d027ec2283` | CROSS_DECADE_ADDENDUM.md<br>CROSS_DECADE_AUDIT.md<br>CROSS_DECADE_REVIEW_RESPONSE.md<br>CROSS_DECADE_VERDICT.md<br>EXTERNAL_AUDIT_ADOPTION.md | `gen_evidence_index.py` |
| `cross_decade/_intermediate/verify_after_800.json` | 5,058 | `94a2233a47ac` | CROSS_DECADE_ADDENDUM.md<br>CROSS_DECADE_AUDIT.md<br>CROSS_DECADE_REVIEW_RESPONSE.md | — |
| `cross_decade/sample_sizes.json` | 436 | `3a641dc38218` | CROSS_DECADE_ADDENDUM.md<br>CROSS_DECADE_PREREG.md<br>DATA_ASSET_REGISTRY.md | — |
| `daily_screen_2026-09-19.json` | 4,746 | `798f50c6f931` | BENCHMARK_ALIGNMENT.md<br>HANDOVER.md<br>STEP1_3_EXECUTION_REPORT.md | — |
| `decay_h1.json` | 2,372 | `9ec2095d4a36` | BENCHMARK_ALIGNMENT.md<br>HANDOVER.md | — |
| `decay_h10.json` | 11,993 | `ded0486f1d6d` | BENCHMARK_ALIGNMENT.md<br>HANDOVER.md | — |
| `decay_h10_ic.json` | 2,756 | `db98f9647190` | HANDOVER.md | — |
| `decay_h20.json` | 11,859 | `b3021856a13c` | BENCHMARK_ALIGNMENT.md<br>HANDOVER.md | — |
| `decay_h20_ic.json` | 2,732 | `fdb88be7f67a` | HANDOVER.md | — |
| `decay_h40.json` | 11,770 | `0466fe78aaff` | HANDOVER.md | — |
| `decay_h5.json` | 11,901 | `3fef6931292f` | BENCHMARK_ALIGNMENT.md<br>HANDOVER.md | — |
| `decay_h5_ic.json` | 2,763 | `f16047a25e69` | HANDOVER.md | — |
| `decay_h60.json` | 2,310 | `683bc5b862b3` | BENCHMARK_ALIGNMENT.md<br>HANDOVER.md | — |
| `delisted/cand_bj_253.json` | 13,530 | `5035385cf666` | （暂无报告直接引用） | — |
| `delisted/cand_shsz_346.json` | 18,025 | `28bee1c6b5b5` | PIT_SNAPSHOT_P0_REPORT.md | — |
| `delisted/tencent_universe_6170.json` | 169,252 | `a40e0cfd7f5d` | （暂无报告直接引用） | — |
| `delta_statistics_audit.json` | 4,618 | `68643ac24a78` | P0_P1_EXECUTION_REPORT.md | — |
| `ew_benchmark_v3.json` | 45,808 | `07a654371278` | BENCHMARK_ALIGNMENT.md<br>P005_3_3_BENCHMARK_PREREG.md<br>P0_P1_EXECUTION_REPORT.md<br>SIX_ISLANDS_WIRING_REPORT.md | `build_equal_weight_benchmark.py` |
| `expert_filter_study.json` | 4,366 | `cb29912d2a23` | BENCHMARK_ALIGNMENT.md<br>EXPERT_FILTER_AND_HF4_HV2_REPORT.md | `run_expert_filter_study.py` |
| `external_v3/_raw_crosscheck.json` | 523 | `b2bfa54d1f17` | （暂无报告直接引用） | — |
| `external_v3/crosscheck_20260911.json` | 523 | `b2bfa54d1f17` | （暂无报告直接引用） | — |
| `external_v3/run_report.json` | 1,322 | `1666440e7a8a` | EXTERNAL_REVIEW_2026_10_06.md<br>STEP1_3_EXECUTION_REPORT.md | — |
| `f4_p1.json` ⚠️ | 2,494 | `6b93b67a4363` | BENCHMARK_ALIGNMENT.md | — |
| `f4_p2.json` | 2,489 | `44fedd7ce65f` | BENCHMARK_ALIGNMENT.md | — |
| `f4_p3.json` | 1,536 | `d6b66f43a7c6` | BENCHMARK_ALIGNMENT.md | — |
| `f4_smoke.json` | 1,539 | `c43bdf726a61` | BENCHMARK_ALIGNMENT.md | — |
| `five_factor_ab_main.json` ⚠️ | 2,186 | `d0999ddd4ff9` | BENCHMARK_ALIGNMENT.md | — |
| `five_factor_ab_smoke.json` | 958 | `63e9cf676f61` | BENCHMARK_ALIGNMENT.md | — |
| `five_factor_ab_smoke2.json` | 1,581 | `a063f2d01acc` | BENCHMARK_ALIGNMENT.md | — |
| `five_factor_ab_v2.json` ⚠️ | 5,164 | `5df9351e0b5f` | BENCHMARK_ALIGNMENT.md<br>COST_BASELINE_PENDING_RECOMPUTE.md<br>EXPERT_FILTER_AND_HF4_HV2_REPORT.md<br>FACTOR_SUBSET_VERDICT.md<br>IMPACT_AND_CAPACITY_REPORT.md<br>P005_3_3_BENCHMARK_PREREG.md<br>TURNOVER_CAPACITY_PREREG.md<br>TURNOVER_CAPACITY_VERDICT.md | `gen_evidence_index.py` |
| `fixedpool_v2.json` | 1,480 | `32064baa08d3` | （暂无报告直接引用） | `run_multiple_testing_audit.py` |
| `fixedpool_v3.json` | 1,480 | `3dfc8c4d79f5` | （暂无报告直接引用） | `run_multiple_testing_audit.py` |
| `form_screen_eval.json` | 5,483 | `b1dd45d37ea0` | BENCHMARK_ALIGNMENT.md<br>FORM_SCREEN_VERDICT.md<br>reports/form_screen_eval.md | `evaluate_form_screen.py` |
| `hd1_disclosure_advance.json` | 1,331 | `67b72c49a2ad` | ALPHA_HYPOTHESIS_PREREG_HD1.md<br>HANDOVER.md | — |
| `hd2_disclosure_revisions.json` | 1,178 | `bbdec516b597` | ALPHA_HYPOTHESIS_BACKLOG.md<br>ALPHA_HYPOTHESIS_PREREG_HD2.md<br>HANDOVER.md | `run_disclosure_factor_study.py` |
| `hd3_st_reversal.json` | 1,637 | `5171f35be6ec` | ALPHA_HYPOTHESIS_PREREG_HD3.md<br>HANDOVER.md | `run_st_reversal_study.py` |
| `hd4_limit_structure.json` | 1,280 | `fdf2a0e6882e` | ALPHA_HYPOTHESIS_PREREG_HD4.md<br>HANDOVER.md | `run_limit_structure_study.py` |
| `horizon_study.json` ⚠️ | 6,047 | `40c805f3e44b` | BENCHMARK_ALIGNMENT.md<br>COST_BASELINE_PENDING_RECOMPUTE.md<br>HORIZON_NET_EFFECT_REPORT.md<br>SCORE_TURNOVER_DEFECT_REPORT.md<br>WORKLOG.md | `run_horizon_study.py` |
| `horizon_study_turnover_fixed.json` ⚠️ | 5,968 | `65d635d22311` | BENCHMARK_ALIGNMENT.md<br>COST_BASELINE_PENDING_RECOMPUTE.md<br>SCORE_TURNOVER_DEFECT_REPORT.md<br>WORKLOG.md | — |
| `ic_diag_smoke.json` | 3,159 | `13a1c4d2fa34` | BENCHMARK_ALIGNMENT.md | — |
| `ic_diagnosis.json` | 3,164 | `0406cd83909d` | BENCHMARK_ALIGNMENT.md<br>EXTERNAL_REVIEW_2026_10_06.md<br>IC_DIAGNOSIS_PREREG.md<br>IC_DIAGNOSIS_REPORT.md<br>IC_DIAGNOSIS_VERDICT.md | — |
| `impact_cost.json` ⚠️ | 6,444 | `bb88751fe5da` | COST_BASELINE_PENDING_RECOMPUTE.md<br>IMPACT_AND_CAPACITY_REPORT.md<br>IMPACT_COST_PREREG.md<br>IMPACT_COST_VERDICT.md | — |
| `impact_p1.json` | 1,834 | `f52a6592be3f` | BENCHMARK_ALIGNMENT.md<br>STEP1_3_EXECUTION_REPORT.md | — |
| `impact_p3.json` ⚠️ | 1,841 | `a6b5754cda9c` | BENCHMARK_ALIGNMENT.md<br>STEP1_3_EXECUTION_REPORT.md | — |
| `industry_ic_attribution.json` | 58,556 | `318ab564785f` | BENCHMARK_ALIGNMENT.md | `run_industry_ic_attribution.py` |
| `industry_ic_attribution_sw.json` | 69,367 | `9b6fec09ca0b` | （暂无报告直接引用） | `run_industry_ic_attribution.py` |
| `l3_reconciliation.json` | 2,944 | `4f58e9e01b9b` | PIT_SNAPSHOT_P2_REPORT.md | — |
| `l3_reconciliation_n60_2026-10-13.json` | 2,113 | `651ecc071307` | PIT_SNAPSHOT_P3_REPORT.md | — |
| `l3_reconciliation_n60_post_regression_2026-10-13.json` | 2,113 | `651ecc071307` | （暂无报告直接引用） | — |
| `long_history/data_readiness_20261007.json` | 838 | `0088a0afee4c` | （暂无报告直接引用） | — |
| `long_history/feasibility_20261006.json` | 985 | `63d96ab25f77` | （暂无报告直接引用） | — |
| `multiple_testing_audit.json` | 9,523 | `7b1c929483c4` | P0_P1_EXECUTION_REPORT.md | `run_multiple_testing_audit.py` |
| `neu_p2.json` | 1,653 | `ab2c7b50e172` | BENCHMARK_ALIGNMENT.md | — |
| `neu_p3.json` | 1,650 | `2a8b169664f8` | BENCHMARK_ALIGNMENT.md | — |
| `newstock_pref_diag.json` | 495 | `7c2f9eca728e` | BENCHMARK_ALIGNMENT.md | `diagnose_newstock_pref.py` |
| `pit_gaps.json` | 1,620 | `051603363874` | （暂无报告直接引用） | — |
| `pit_l1_reconciliation.json` | 841 | `b674dabad7fe` | PIT_SNAPSHOT_P0_REPORT.md | — |
| `pit_l2_reconciliation.json` | 876 | `4129192e022a` | （暂无报告直接引用） | — |
| `regime_overlay_const05_pilot.json` | 1,038 | `784bcbaee4d1` | BENCHMARK_ALIGNMENT.md<br>STEP1_3_EXECUTION_REPORT.md | — |
| `regime_overlay_study_w5.json` | 820 | `aa6b5726baa7` | BENCHMARK_ALIGNMENT.md | — |
| `rs_main.json` ⚠️ | 1,841 | `a6b3ce6023d4` | BENCHMARK_ALIGNMENT.md | — |
| `rs_smoke.json` | 780 | `126e01fab260` | BENCHMARK_ALIGNMENT.md | — |
| `silent_scan.json` | 34,601 | `cb09c2c8c796` | PROJECT_HEALTH_AUDIT.md | — |
| `ss_p1.json` ⚠️ | 1,682 | `e14263637842` | BENCHMARK_ALIGNMENT.md | — |
| `ss_p2.json` | 1,677 | `cbf332bf162c` | BENCHMARK_ALIGNMENT.md | — |
| `ss_smoke.json` | 1,066 | `231573e1fa02` | BENCHMARK_ALIGNMENT.md | — |
| `stop_loss_ab.json` | 2,327 | `80c7e5f5a1e6` | BENCHMARK_ALIGNMENT.md<br>COST_BASELINE_PENDING_RECOMPUTE.md | `run_stop_loss_ab.py` |
| `stop_loss_ab_5win.json` | 3,458 | `883716b25363` | BENCHMARK_ALIGNMENT.md<br>COST_BASELINE_PENDING_RECOMPUTE.md<br>SIX_ISLANDS_WIRING_REPORT.md | — |
| `t1b_p1.json` ⚠️ | 1,884 | `e3ba7033a3b7` | BENCHMARK_ALIGNMENT.md<br>STEP1_3_EXECUTION_REPORT.md | — |
| `t1b_p2.json` | 1,877 | `8b3e3444f865` | BENCHMARK_ALIGNMENT.md<br>STEP1_3_EXECUTION_REPORT.md | — |
| `tail_exclusion_with_p.json` | 4,164 | `28927b7c2e42` | BENCHMARK_ALIGNMENT.md<br>COST_BASELINE_PENDING_RECOMPUTE.md<br>FACTOR_HORIZON_DECAY_REPORT.md<br>P0_P1_EXECUTION_REPORT.md | `run_horizon_study.py` |
| `tc_t0.json` ⚠️ | 6,432 | `595ad74d9161` | COST_BASELINE_PENDING_RECOMPUTE.md<br>IMPACT_AND_CAPACITY_REPORT.md<br>TURNOVER_CAPACITY_PREREG.md<br>TURNOVER_CAPACITY_VERDICT.md | — |
| `tc_t1_p1.json` | 1,814 | `aaa8cb918759` | BENCHMARK_ALIGNMENT.md | — |
| `tc_t1_p2.json` ⚠️ | 1,819 | `c570a18f212a` | BENCHMARK_ALIGNMENT.md | — |
| `tc_t1_p3.json` | 1,147 | `f9005f5d5aba` | BENCHMARK_ALIGNMENT.md | — |
| `tc_t2.json` ⚠️ | 6,433 | `c3174caffcca` | COST_BASELINE_PENDING_RECOMPUTE.md<br>IMPACT_AND_CAPACITY_REPORT.md<br>TURNOVER_CAPACITY_PREREG.md<br>TURNOVER_CAPACITY_VERDICT.md | — |
| `tc_t2_p1.json` ⚠️ | 1,816 | `53bf527154ea` | BENCHMARK_ALIGNMENT.md | — |
| `tdx_ic_800.json` | 1,558 | `fae02eab688a` | BENCHMARK_ALIGNMENT.md<br>HANDOVER.md | — |
| `tdx_ic_full.json` | 2,339 | `8c103cfc5a27` | BENCHMARK_ALIGNMENT.md<br>CROSS_DECADE_AUDIT.md<br>CROSS_DECADE_PREREG.md<br>CROSS_DECADE_REVIEW_PACKAGE.md<br>CROSS_DECADE_VERDICT.md<br>EXPERT_FILTER_AND_HF4_HV2_REPORT.md<br>FACTOR_SUBSET_PREREG.md<br>HANDOVER.md | `summarize_cross_decade.py` |
| `tdx_ic_smoke.json` | 1,560 | `6a877153bbac` | BENCHMARK_ALIGNMENT.md | — |
| `tdx_native_screen.json` | 4,863 | `b9ada444e953` | BENCHMARK_ALIGNMENT.md | — |
| `tdx_native_screen_adj.json` | 2,609 | `0661f5004678` | BENCHMARK_ALIGNMENT.md | — |
| `v2_c20_v1_p1.json` | 1,596 | `82051bb3a746` | BENCHMARK_ALIGNMENT.md | — |
| `v2_c20_v1_p2.json` ⚠️ | 2,194 | `8dfbbac8ceba` | BENCHMARK_ALIGNMENT.md | — |
| `v2_ew_bench_20230103.json` | 879 | `dae5409bfa76` | BENCHMARK_ALIGNMENT.md | — |
| `v2_ew_bench_part1.json` ⚠️ | 1,435 | `c52c93b6c263` | BENCHMARK_ALIGNMENT.md | — |
| `v2_ew_bench_part2.json` | 1,981 | `503009f21c12` | BENCHMARK_ALIGNMENT.md | — |
| `v2_factor_correlation.json` | 1,637 | `ccabf17b8e10` | BENCHMARK_ALIGNMENT.md<br>FIVE_FACTOR_PREREG.md | — |
| `v2_factor_study.json` | 11,906 | `fa5aa1137fa7` | BENCHMARK_ALIGNMENT.md<br>FIVE_FACTOR_PREREG.md<br>IC_DIAGNOSIS_PREREG.md<br>IC_DIAGNOSIS_REPORT.md<br>STEP1_3_EXECUTION_REPORT.md | `run_multiple_testing_audit.py`<br>`run_tdx_universe_ic.py` |
| `v2_p1.json` ⚠️ | 2,471 | `3972fbc422a0` | BENCHMARK_ALIGNMENT.md | — |
| `v2_p2.json` | 2,464 | `07150dada9db` | BENCHMARK_ALIGNMENT.md | — |
| `v2_p3.json` | 1,504 | `4c8635c7e17f` | BENCHMARK_ALIGNMENT.md | — |
| `v2_rolling_eval_ew.json` ⚠️ | 5,698 | `8dee8757ce05` | ALPHA_CAPABILITY_GAP_ANALYSIS.md<br>BENCHMARK_ALIGNMENT.md<br>COST_BASELINE_PENDING_RECOMPUTE.md<br>WORKLOG.md | `run_multiple_testing_audit.py` |
| `v2_rolling_eval_w6.json` | 798 | `3554bec67bc1` | BENCHMARK_ALIGNMENT.md<br>STEP1_3_EXECUTION_REPORT.md | — |
| `v3_alpha_gap_probe.json` | 2,473 | `4c354ef681dc` | BENCHMARK_ALIGNMENT.md | — |
| `v3_alpha_gap_probe_coverage.json` | 1,180 | `57a23de20ead` | BENCHMARK_ALIGNMENT.md | — |
| `v3_fundamental_factor_study.json` | 11,136 | `3652c340c206` | （暂无报告直接引用） | — |
| `v3_rolling_eval_ew.json` ⚠️ | 5,684 | `0e26a4060d66` | BENCHMARK_ALIGNMENT.md<br>COST_BASELINE_PENDING_RECOMPUTE.md | — |
| `v3_rolling_eval_ew_full.json` ⚠️ | 6,197 | `1becb18f2bf5` | BENCHMARK_ALIGNMENT.md<br>COST_BASELINE_PENDING_RECOMPUTE.md<br>P0_P1_EXECUTION_REPORT.md | `run_multiple_testing_audit.py` |
| `valuation_weight_ab.json` | 2,192 | `1ee76356ac9c` | BENCHMARK_ALIGNMENT.md<br>COST_BASELINE_PENDING_RECOMPUTE.md<br>SIX_ISLANDS_WIRING_REPORT.md | `run_valuation_weight_ab.py` |
| `xsource/XSRC.json` | 4,109 | `96a75c3749e7` | XSOURCE_VALIDATION_PREREG.md<br>XSOURCE_VALIDATION_VERDICT.md | `run_xsrc_ic.py` |

---

## ⚠️ 成本口径待核（窗口跨 `2023-08-28`）

**判据（机械可复算，`stamp_duty_stale()`）**：产物含 `windows` 键
（＝**组合/回测类**；IC/因子研究类键为 `source`/`stocks`/`cross_sections`…，**无交易成本**，已排除）**且**其日期区间**跨过** `2023-08-28`
（= `STAMP_DUTY_CHANGE_DATE`，**印花税分段生效日**）。

**背景**：`backtest_engine._stamp_rate` 的分段判定曾因 `str(trade_date) >= str(change)`（`'-' < '0'` ⇒ **恒真**）**完全失效** —— 2023-08-28 前的卖出一律按**新**税率 0.5‰ 计，**旧税率 1‰ 从未生效**。
已于 `8b3cba8`（2026-10-13）修复，**但修复后未重算下列产物** —— 它们处于「**新代码 vs 旧数字**」状态。

**处置**：P006 A2 合并落定后由主干**统一重算**（此时代码/数据/口径三者才同时稳定）；在此之前引用须显式标注，**不得静默当作现行成本口径**。
**方向预期**：修复 ⇒ 2023-08-28 前卖出成本 0.5‰→1‰ ⇒ 成本升、收益降 ⇒ 「**无 alpha**」结论**更稳、不翻转**。

**当前 24 份待核：**

- `ab_n3_batchA.json`
- `combo_study_h20.json`
- `combo_study_h20_fixed.json`
- `cost_model_check.json`
- `f4_p1.json`
- `five_factor_ab_main.json`
- `five_factor_ab_v2.json`
- `horizon_study.json`
- `horizon_study_turnover_fixed.json`
- `impact_cost.json`
- `impact_p3.json`
- `rs_main.json`
- `ss_p1.json`
- `t1b_p1.json`
- `tc_t0.json`
- `tc_t1_p2.json`
- `tc_t2.json`
- `tc_t2_p1.json`
- `v2_c20_v1_p2.json`
- `v2_ew_bench_part1.json`
- `v2_p1.json`
- `v2_rolling_eval_ew.json`
- `v3_rolling_eval_ew.json`
- `v3_rolling_eval_ew_full.json`

---

## 未被任何报告直接引用的证据

以下文件已跟踪但暂无报告直接引用 —— 可能是**中间产物**或**脚本内部消费**。
保留它们是为可复现性；若确认无用，应移出 `reports/` 或加 `_` 前缀使其被忽略。

- `ah_codes.json`
- `cross_decade/W2.json`
- `cross_decade/W3.json`
- `cross_decade/W4.json`
- `cross_decade/W5.json`
- `delisted/cand_bj_253.json`
- `delisted/tencent_universe_6170.json`
- `external_v3/_raw_crosscheck.json`
- `external_v3/crosscheck_20260911.json`
- `fixedpool_v2.json`
- `fixedpool_v3.json`
- `industry_ic_attribution_sw.json`
- `l3_reconciliation_n60_post_regression_2026-10-13.json`
- `long_history/data_readiness_20261007.json`
- `long_history/feasibility_20261006.json`
- `pit_gaps.json`
- `pit_l2_reconciliation.json`
- `v3_fundamental_factor_study.json`

---

**声明**：本索引只描述「哪些证据被跟踪」，**不构成任何策略有效性判断**。
**本文件不构成投资建议。**
