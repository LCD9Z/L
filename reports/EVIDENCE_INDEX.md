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

**当前跟踪 82 份证据。**

---

| 证据文件 | 字节 | sha256 | 引用它的报告 | 生成脚本 |
|------|-----:|--------|------|------|
| `ab_n3_batchA.json` | 1,933 | `1e00a5afe784` | BENCHMARK_ALIGNMENT.md | — |
| `ab_n3_w3.json` | 1,262 | `4c964bca7b09` | BENCHMARK_ALIGNMENT.md | — |
| `ab_n3_w4.json` | 1,268 | `3e03b256e03a` | BENCHMARK_ALIGNMENT.md | — |
| `ab_n3_w5.json` | 1,260 | `32220c37299d` | BENCHMARK_ALIGNMENT.md | — |
| `adx_attr_w1.json` | 595 | `96f012a93f91` | BENCHMARK_ALIGNMENT.md | — |
| `adx_attr_w2.json` | 597 | `0eb1abd6cf69` | BENCHMARK_ALIGNMENT.md | — |
| `adx_attr_w3.json` | 595 | `094810537084` | BENCHMARK_ALIGNMENT.md | — |
| `adx_attr_w4.json` | 593 | `297351b722ae` | BENCHMARK_ALIGNMENT.md | — |
| `cost_model_check.json` | 1,452 | `c844f528f28a` | BENCHMARK_ALIGNMENT.md<br>STEP1_3_EXECUTION_REPORT.md | — |
| `cross_decade/CORR.json` | 2,833 | `f43f68059e9e` | AGENTS.md<br>CROSS_DECADE_REVIEW_RESPONSE.md<br>CROSS_DECADE_VERDICT.md<br>DATA_ASSET_REGISTRY.md<br>FACTOR_ORTHOGONALITY_PREREG.md<br>FACTOR_SUBSET_PREREG.md | `factor_corr_by_window.py` |
| `cross_decade/ORTH.json` | 8,997 | `b1fddcf0b6b1` | DATA_ASSET_REGISTRY.md<br>FACTOR_ORTHOGONALITY_PREREG.md<br>FACTOR_ORTHOGONALITY_VERDICT.md<br>REVIEW_ROUND2_PACKAGE.md | `run_factor_orthogonality.py`<br>`run_xsrc_ic.py` |
| `cross_decade/R.json` | 9,924 | `bde915cfd519` | AGENTS.md<br>CROSS_DECADE_REVIEW_RESPONSE.md<br>CROSS_DECADE_VERDICT.md<br>DATA_ASSET_REGISTRY.md<br>FACTOR_ORTHOGONALITY_PREREG.md<br>FACTOR_SUBSET_PREREG.md | `factor_corr_by_window.py` |
| `cross_decade/VERDICT.json` | 806 | `4a6e2f30d934` | DATA_ASSET_REGISTRY.md | `run_xsrc_ic.py`<br>`summarize_cross_decade.py` |
| `cross_decade/W1.json` | 9,677 | `9a8113be0468` | （暂无报告直接引用） | `gen_evidence_index.py` |
| `cross_decade/W1a.json` | 9,448 | `c2432d7ffef5` | W1_SPLIT_PREREG.md<br>W1_SPLIT_VERDICT.md | — |
| `cross_decade/W1b.json` | 9,622 | `e01b3b5b325a` | W1_SPLIT_PREREG.md<br>W1_SPLIT_VERDICT.md | — |
| `cross_decade/W2.json` | 9,854 | `f26111ff4060` | （暂无报告直接引用） | — |
| `cross_decade/W3.json` | 9,892 | `babbd6bcaa6c` | （暂无报告直接引用） | — |
| `cross_decade/W4.json` | 9,922 | `31e5fd58895c` | （暂无报告直接引用） | — |
| `cross_decade/W5.json` | 9,925 | `ca3815c012af` | （暂无报告直接引用） | — |
| `cross_decade/_intermediate/VERDICT_partial.json` | 1,050 | `58d027ec2283` | CROSS_DECADE_REVIEW_RESPONSE.md<br>CROSS_DECADE_VERDICT.md | `gen_evidence_index.py` |
| `cross_decade/_intermediate/verify_after_800.json` | 5,058 | `94a2233a47ac` | CROSS_DECADE_REVIEW_RESPONSE.md | — |
| `cross_decade/sample_sizes.json` | 436 | `3a641dc38218` | CROSS_DECADE_PREREG.md<br>DATA_ASSET_REGISTRY.md | — |
| `daily_screen_2026-09-19.json` | 4,746 | `798f50c6f931` | BENCHMARK_ALIGNMENT.md<br>HANDOVER.md<br>STEP1_3_EXECUTION_REPORT.md | — |
| `decay_h1.json` | 2,372 | `9ec2095d4a36` | BENCHMARK_ALIGNMENT.md<br>HANDOVER.md | — |
| `decay_h10.json` | 2,330 | `6961ab958edb` | BENCHMARK_ALIGNMENT.md<br>HANDOVER.md | — |
| `decay_h20.json` | 2,306 | `9e2b932d5c63` | BENCHMARK_ALIGNMENT.md<br>HANDOVER.md | — |
| `decay_h5.json` | 2,337 | `4aca40035884` | BENCHMARK_ALIGNMENT.md<br>HANDOVER.md | — |
| `decay_h60.json` | 2,310 | `683bc5b862b3` | BENCHMARK_ALIGNMENT.md<br>HANDOVER.md | — |
| `delisted/cand_bj_253.json` | 13,530 | `5035385cf666` | （暂无报告直接引用） | — |
| `delisted/cand_shsz_346.json` | 18,025 | `28bee1c6b5b5` | （暂无报告直接引用） | — |
| `delisted/tencent_universe_6170.json` | 169,252 | `a40e0cfd7f5d` | （暂无报告直接引用） | — |
| `external_v3/_raw_crosscheck.json` | 523 | `b2bfa54d1f17` | （暂无报告直接引用） | — |
| `external_v3/crosscheck_20260911.json` | 523 | `b2bfa54d1f17` | （暂无报告直接引用） | — |
| `external_v3/run_report.json` | 1,322 | `1666440e7a8a` | EXTERNAL_REVIEW_2026_10_06.md<br>STEP1_3_EXECUTION_REPORT.md | — |
| `f4_p1.json` | 2,494 | `6b93b67a4363` | BENCHMARK_ALIGNMENT.md | — |
| `f4_p2.json` | 2,489 | `44fedd7ce65f` | BENCHMARK_ALIGNMENT.md | — |
| `f4_p3.json` | 1,536 | `d6b66f43a7c6` | BENCHMARK_ALIGNMENT.md | — |
| `f4_smoke.json` | 1,539 | `c43bdf726a61` | BENCHMARK_ALIGNMENT.md | — |
| `five_factor_ab_main.json` | 2,186 | `d0999ddd4ff9` | BENCHMARK_ALIGNMENT.md | — |
| `five_factor_ab_smoke.json` | 958 | `63e9cf676f61` | BENCHMARK_ALIGNMENT.md | — |
| `five_factor_ab_smoke2.json` | 1,581 | `a063f2d01acc` | BENCHMARK_ALIGNMENT.md | — |
| `form_screen_eval.json` | 5,483 | `b1dd45d37ea0` | BENCHMARK_ALIGNMENT.md<br>FORM_SCREEN_VERDICT.md<br>reports/form_screen_eval.md | `evaluate_form_screen.py` |
| `ic_diag_smoke.json` | 3,159 | `13a1c4d2fa34` | BENCHMARK_ALIGNMENT.md | — |
| `ic_diagnosis.json` | 3,134 | `522126a5b3f8` | BENCHMARK_ALIGNMENT.md<br>EXTERNAL_REVIEW_2026_10_06.md | — |
| `impact_p1.json` | 1,834 | `f52a6592be3f` | BENCHMARK_ALIGNMENT.md<br>STEP1_3_EXECUTION_REPORT.md | — |
| `impact_p3.json` | 1,841 | `a6b5754cda9c` | BENCHMARK_ALIGNMENT.md<br>STEP1_3_EXECUTION_REPORT.md | — |
| `long_history/data_readiness_20261007.json` | 838 | `0088a0afee4c` | （暂无报告直接引用） | — |
| `long_history/feasibility_20261006.json` | 985 | `63d96ab25f77` | （暂无报告直接引用） | — |
| `neu_p2.json` | 1,653 | `ab2c7b50e172` | BENCHMARK_ALIGNMENT.md | — |
| `neu_p3.json` | 1,650 | `2a8b169664f8` | BENCHMARK_ALIGNMENT.md | — |
| `newstock_pref_diag.json` | 495 | `7c2f9eca728e` | BENCHMARK_ALIGNMENT.md | `diagnose_newstock_pref.py` |
| `regime_overlay_const05_pilot.json` | 1,038 | `784bcbaee4d1` | BENCHMARK_ALIGNMENT.md<br>STEP1_3_EXECUTION_REPORT.md | — |
| `regime_overlay_study_w5.json` | 820 | `aa6b5726baa7` | BENCHMARK_ALIGNMENT.md | — |
| `rs_main.json` | 1,841 | `a6b3ce6023d4` | BENCHMARK_ALIGNMENT.md | — |
| `rs_smoke.json` | 780 | `126e01fab260` | BENCHMARK_ALIGNMENT.md | — |
| `ss_p1.json` | 1,682 | `e14263637842` | BENCHMARK_ALIGNMENT.md | — |
| `ss_p2.json` | 1,677 | `cbf332bf162c` | BENCHMARK_ALIGNMENT.md | — |
| `ss_smoke.json` | 1,066 | `231573e1fa02` | BENCHMARK_ALIGNMENT.md | — |
| `t1b_p1.json` | 1,884 | `e3ba7033a3b7` | BENCHMARK_ALIGNMENT.md<br>STEP1_3_EXECUTION_REPORT.md | — |
| `t1b_p2.json` | 1,877 | `8b3e3444f865` | BENCHMARK_ALIGNMENT.md<br>STEP1_3_EXECUTION_REPORT.md | — |
| `tc_t1_p1.json` | 1,814 | `aaa8cb918759` | BENCHMARK_ALIGNMENT.md | — |
| `tc_t1_p2.json` | 1,819 | `c570a18f212a` | BENCHMARK_ALIGNMENT.md | — |
| `tc_t1_p3.json` | 1,147 | `f9005f5d5aba` | BENCHMARK_ALIGNMENT.md | — |
| `tc_t2_p1.json` | 1,816 | `53bf527154ea` | BENCHMARK_ALIGNMENT.md | — |
| `tdx_ic_800.json` | 1,558 | `fae02eab688a` | BENCHMARK_ALIGNMENT.md<br>HANDOVER.md | — |
| `tdx_ic_full.json` | 2,339 | `8c103cfc5a27` | BENCHMARK_ALIGNMENT.md<br>CROSS_DECADE_PREREG.md<br>CROSS_DECADE_REVIEW_PACKAGE.md<br>CROSS_DECADE_VERDICT.md<br>FACTOR_SUBSET_PREREG.md<br>HANDOVER.md | `summarize_cross_decade.py` |
| `tdx_ic_smoke.json` | 1,560 | `6a877153bbac` | BENCHMARK_ALIGNMENT.md | — |
| `tdx_native_screen.json` | 4,863 | `b9ada444e953` | BENCHMARK_ALIGNMENT.md | — |
| `tdx_native_screen_adj.json` | 2,609 | `0661f5004678` | BENCHMARK_ALIGNMENT.md | — |
| `v2_c20_v1_p1.json` | 1,596 | `82051bb3a746` | BENCHMARK_ALIGNMENT.md | — |
| `v2_c20_v1_p2.json` | 2,194 | `8dfbbac8ceba` | BENCHMARK_ALIGNMENT.md | — |
| `v2_ew_bench_20230103.json` | 879 | `dae5409bfa76` | BENCHMARK_ALIGNMENT.md | — |
| `v2_ew_bench_part1.json` | 1,435 | `c52c93b6c263` | BENCHMARK_ALIGNMENT.md | — |
| `v2_ew_bench_part2.json` | 1,981 | `503009f21c12` | BENCHMARK_ALIGNMENT.md | — |
| `v2_factor_correlation.json` | 1,637 | `ccabf17b8e10` | BENCHMARK_ALIGNMENT.md<br>FIVE_FACTOR_PREREG.md | — |
| `v2_factor_study.json` | 11,906 | `fa5aa1137fa7` | BENCHMARK_ALIGNMENT.md<br>FIVE_FACTOR_PREREG.md<br>IC_DIAGNOSIS_PREREG.md<br>STEP1_3_EXECUTION_REPORT.md | `run_tdx_universe_ic.py` |
| `v2_p1.json` | 2,471 | `3972fbc422a0` | BENCHMARK_ALIGNMENT.md | — |
| `v2_p2.json` | 2,464 | `07150dada9db` | BENCHMARK_ALIGNMENT.md | — |
| `v2_p3.json` | 1,504 | `4c8635c7e17f` | BENCHMARK_ALIGNMENT.md | — |
| `v2_rolling_eval_w6.json` | 798 | `3554bec67bc1` | BENCHMARK_ALIGNMENT.md<br>STEP1_3_EXECUTION_REPORT.md | — |
| `xsource/XSRC.json` | 4,109 | `96a75c3749e7` | XSOURCE_VALIDATION_PREREG.md | `run_xsrc_ic.py` |

---

## 未被任何报告直接引用的证据

以下文件已跟踪但暂无报告直接引用 —— 可能是**中间产物**或**脚本内部消费**。
保留它们是为可复现性；若确认无用，应移出 `reports/` 或加 `_` 前缀使其被忽略。

- `cross_decade/W1.json`
- `cross_decade/W2.json`
- `cross_decade/W3.json`
- `cross_decade/W4.json`
- `cross_decade/W5.json`
- `delisted/cand_bj_253.json`
- `delisted/cand_shsz_346.json`
- `delisted/tencent_universe_6170.json`
- `external_v3/_raw_crosscheck.json`
- `external_v3/crosscheck_20260911.json`
- `long_history/data_readiness_20261007.json`
- `long_history/feasibility_20261006.json`

---

**声明**：本索引只描述「哪些证据被跟踪」，**不构成任何策略有效性判断**。
**本文件不构成投资建议。**
