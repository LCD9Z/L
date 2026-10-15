# 成本口径重算 · 执行清单（方案③下半场）

> **建立**：2026-10-15　**建立方**：海外版 WorkBuddy（副本侧）
> **上位依据**：`COST_BASELINE_PENDING_RECOMPUTE.md`（登记册）· 方案③（双方 10-14 商定：
> A2 合并取主干版代码 → 合并落定后统一重算）
> **规范集**：`gen_evidence_index.stamp_duty_stale` 规则产出的 **24 份**（主侧 12 + 副本 12）

---

## 一、前提核验（已完成）

| # | 前提 | 状态 | 证据 |
|:--:|------|:----:|------|
| 1 | A2 合并落定（代码统一基线） | ✅ | 合并提交 `86956c8`；主干 ff 至同一历史 |
| 2 | `_stamp_rate` 印花税分段已修复 | ✅ | 实测 `'20230825'`→0.001（旧税率）、`'20230901'`→0.0005；两种日期格式均正确 |
| 3 | `_norm_date` 与 `test_execution_stress.py` 已合入 | ✅ | `backtest_engine.py:28`；`tests/test_execution_stress.py` 存在 |
| 4 | 工具链可用（CI 可跑） | ✅ | 修复两处运行时断链后 CI 6/6 |

---

## 二、执行设计

### 2.1 为什么必须按窗口拆分

单份产物运行 **790 ~ 3,542 s**（13 ~ 59 分钟），而本机**后台任务 25~40 分钟静默死亡**
（AGENTS.md §5）。故每个**窗口**一个独立进程，各自落盘，支持断点续跑。

- 总窗口任务数：**81 个**（24 份的窗口数之和）
- 总估算算力：**约 11~15 小时**（按每窗口 400~600 s）

### 2.2 落盘与隔离

- 输出目录：`reports/_recalc/<产物名>_<窗口>.json`
- `_` 前缀命中 `.gitignore` 的 `reports/_*.json` → **不会误入库**（原产物保持不动）
- 原产物在重算完成并经双方确认前，**一律维持「成本口径待核」标注**

### 2.3 验收标准（事前固定）

| # | 标准 | 判定 |
|:--:|------|------|
| V1 | 产物结构与原产物可比（同 arm 键、同窗口键） | 逐键比对 |
| V2 | 重算**确实产生差异**（不是"跑了等于没跑"） | 至少一处数值变化 |
| V3 | 差异方向：成本升 → 收益降 / 超额降 | 数值方向检查 |
| V4 | 无 NaN / 无缺失 arm | 结构完整性 |
| V5 | 登记册逐条标注「已重算（日期/commit）」或说明不适用 | 册子更新 |

> ⚠️ **V3 的边界（验证跑实测教训）**：差异**不全部来自印花税**。
> 验证跑（`ss_p1` 单窗口）显示：同一份产物内 `SS_inv_falsify` 变化 **-12.09pp**（远超
> 印花税量级 ~1.2%），而 `SS_style_switch` **逐位不变**。这说明差异含**合并带来的
> 代码基线演进**（方案③的固有性质：统一基线 = 合并后代码）。
> → 验收应表述为「**以合并后代码为准的新基线**」，而非「小幅修正」。

---

## 三、命令表（副本侧 12 份，可立即执行）

> 命令由产物 `args` 字段**程序化反推**（`--windows` 已替换为单窗口占位）；
> 显式传参 = 原 `args` 与默认值不同者，省略者与原默认一致。

| # | 产物 | 脚本 | 数据集 | 窗口数 |
|:--:|------|------|--------|:--:|
| 1 | `combo_study_h20` | `run_combo_study.py` | v3 | 3 |
| 2 | `combo_study_h20_fixed` | `run_combo_study.py` | v3 | 3 |
| 3 | `cost_model_check` | **`run_cost_model_check.py`** | `D:/tdx_dataset` | 2 |
| 4 | `five_factor_ab_v2` | `run_five_factor_ab.py` | v2 | 5 |
| 5 | `horizon_study` | `run_horizon_study.py` | v3 | 3 |
| 6 | `horizon_study_turnover_fixed` | `run_horizon_study.py` | v3 | 3 |
| 7 | `impact_cost` | `run_five_factor_ab.py` | v2 | 5 |
| 8 | `tc_t0` | `run_five_factor_ab.py` | v2 | 5 |
| 9 | `tc_t2` | `run_five_factor_ab.py` | v2 | 5 |
| 10 | `v2_rolling_eval_ew` | `run_tdx_rolling_eval.py` | v2 | 6 |
| 11 | `v3_rolling_eval_ew` | `run_tdx_rolling_eval.py` | v3 | 6 |
| 12 | `v3_rolling_eval_ew_full` | `run_tdx_rolling_eval.py` | v3 | 6 |

**命令模板**（示例，逐份参数见 §五附录）：

```bash
# 示例：five_factor_ab_v2 的 2023-07-03 窗口
python scripts/run_five_factor_ab.py --dataset D:/tdx_dataset_v2 --horizon 20 \
  --exclude-ret20-top 0.2 --exclude-jump --windows 2023-07-03 \
  --out reports/_recalc/five_factor_ab_v2_2023-07-03.json
```

---

## 四、主侧 12 份（待主干确认命令）

| # | 产物 | 推断脚本 | 备注 |
|:--:|------|----------|------|
| 1 | `ab_n3_batchA` | `run_five_factor_ab.py` | `--exclude-ret20-top 0.2 --exclude-jump --exclude-limitup --skip-legacy-arms --horizon 20` |
| 2 | `f4_p1` | `run_five_factor_ab.py` | `--survivorship-evidence …/evidence.json` |
| 3 | `five_factor_ab_main` | `run_five_factor_ab.py` | 同上 |
| 4 | `impact_p3` | `run_five_factor_ab.py` | `--impact-model --exclude-ret20-top 0.2` |
| 5 | `rs_main` | `run_five_factor_ab.py` | `--regime-switch` |
| 6 | `ss_p1` | `run_five_factor_ab.py` | `--style-switch`（**已做验证跑**，见 §六） |
| 7 | `t1b_p1` | `run_five_factor_ab.py` | `--horizon 60 --exclude-ret20-top 0.2` |
| 8 | `tc_t1_p2` | `run_five_factor_ab.py` | `--horizon 20 --exclude-ret20-top 0.2` |
| 9 | `tc_t2_p1` | `run_five_factor_ab.py` | `--max-participation 0.05 --exclude-ret20-top 0.2` |
| 10 | `v2_c20_v1_p2` | `run_five_factor_ab.py` | `--exclude-ret20-top 0.2` |
| 11 | `v2_ew_bench_part1` | **待确认** | args 仅 `dataset/max_stocks/windows/benchmark`（形状不同于 five_factor_ab） |
| 12 | `v2_p1` | `run_five_factor_ab.py` | `--horizon 20 --exclude-ret20-top 0.2 --exclude-jump` |

> **请求**：请主干确认 #11 的生成脚本与 #1–#10 的完整参数（尤其**未在 args 中出现的
> 显式传参**——args 只记值，不记是否显式传）。

---

## 五、附录：副本侧 12 份完整命令

```bash
# 1) combo_study_h20（v3，3 窗口）
python scripts/run_combo_study.py --dataset D:/tdx_dataset_v3 --max-stocks 300 \
  --top-frac 0.2 --threshold 70.0 --horizon 20 --windows <W> \
  --out reports/_recalc/combo_study_h20_<W>.json

# 2) combo_study_h20_fixed（同上，仅输出名不同）
python scripts/run_combo_study.py --dataset D:/tdx_dataset_v3 --max-stocks 300 \
  --top-frac 0.2 --threshold 70.0 --horizon 20 --windows <W> \
  --out reports/_recalc/combo_study_h20_fixed_<W>.json

# 3) cost_model_check（D:/tdx_dataset，2 窗口）
python scripts/run_cost_model_check.py --dataset D:/tdx_dataset --max-stocks 400 \
  --windows <W> --out reports/_recalc/cost_model_check_<W>.json

# 4) five_factor_ab_v2（v2，5 窗口）
python scripts/run_five_factor_ab.py --dataset D:/tdx_dataset_v2 --horizon 20 \
  --exclude-ret20-top 0.2 --exclude-jump --windows <W> \
  --out reports/_recalc/five_factor_ab_v2_<W>.json

# 5) horizon_study（v3，3 窗口）
python scripts/run_horizon_study.py --dataset D:/tdx_dataset_v3 --horizons 5,10,20,40 \
  --max-stocks 300 --top-n 5 --position-pct 0.25 --threshold 70.0 --windows <W> \
  --out reports/_recalc/horizon_study_<W>.json

# 6) horizon_study_turnover_fixed（同上）
python scripts/run_horizon_study.py --dataset D:/tdx_dataset_v3 --horizons 5,10,20,40 \
  --max-stocks 300 --top-n 5 --position-pct 0.25 --threshold 70.0 --windows <W> \
  --out reports/_recalc/horizon_study_turnover_fixed_<W>.json

# 7) impact_cost（v2，5 窗口）
python scripts/run_five_factor_ab.py --dataset D:/tdx_dataset_v2 --horizon 20 \
  --exclude-ret20-top 0.2 --impact-model --windows <W> \
  --out reports/_recalc/impact_cost_<W>.json

# 8) tc_t0（v2，5 窗口）
python scripts/run_five_factor_ab.py --dataset D:/tdx_dataset_v2 \
  --exclude-ret20-top 0.2 --windows <W> --out reports/_recalc/tc_t0_<W>.json

# 9) tc_t2（v2，5 窗口）
python scripts/run_five_factor_ab.py --dataset D:/tdx_dataset_v2 \
  --exclude-ret20-top 0.2 --max-participation 0.05 --windows <W> \
  --out reports/_recalc/tc_t2_<W>.json

# 10) v2_rolling_eval_ew（v2，6 窗口）
python scripts/run_tdx_rolling_eval.py --dataset D:/tdx_dataset_v2 \
  --windows <W> --out reports/_recalc/v2_rolling_eval_ew_<W>.json

# 11) v3_rolling_eval_ew（v3，6 窗口）
python scripts/run_tdx_rolling_eval.py --dataset D:/tdx_dataset_v3 --max-stocks 1000 \
  --windows <W> --out reports/_recalc/v3_rolling_eval_ew_<W>.json

# 12) v3_rolling_eval_ew_full（同上）
python scripts/run_tdx_rolling_eval.py --dataset D:/tdx_dataset_v3 --max-stocks 1000 \
  --windows <W> --out reports/_recalc/v3_rolling_eval_ew_full_<W>.json
```

> `<W>` = 单窗口，取自产物 `args.windows` 的逐项拆分。

---

## 六、验证跑结果（`ss_p1` 单窗口 2023-07-03，2026-10-15）

**目的**：确认重算管线可用 + 差异方向。**结论：管线可用，但归因需对齐。**

| 指标 | 原产物 | 重算 | 差异 |
|------|-------:|-----:|-----:|
| `SS_style_switch` 总收益 | -8.242% | -8.242% | **0** |
| `SS_style_switch` trades | 3,119 | 3,119 | 0 |
| `SS_inv_falsify` 总收益 | -25.554% | **-37.648%** | **-12.09pp** |
| `SS_inv_falsify` 超额 | -20.59% | **-26.12%** | -5.52pp |
| `SS_inv_falsify` trades | 3,108 | 3,104 | -4 |
| `delta_excess_pp` | -6.28 | **-11.80** | -5.52pp |

**两点观察（不掩盖）**：
1. 差异量级 **12pp 远超印花税影响**（估 ~1.2%）→ 含**代码基线演进**（合并带来的其他改动）。
2. **一个 arm 逐位不变、另一个显著变化**——同段代码（`_ss` 函数，仅 `inv` 翻转），
   现象**未解释**。可能来源：原产物生成于 10-02 审计（`75749cf`）时点、其后的代码演进
   对两个 arm 的路径影响不同。**请主干确认 `ss_p1` 的生成历史**。

**产物**：`reports/_recalc_ss_p1_20230703.json`（`_` 前缀，不入库）· 运行 582 s。

---

## 七、执行序（建议）

1. 副本侧 12 份（本清单 §三/§五）→ 分 3~4 批后台跑，每批 3~5 小时；
2. 主侧 12 份：待主干确认命令后，**由主干执行**（其产物、其环境）；
3. 双方产物齐备 → 按 §2.3 V1–V5 验收 → 更新登记册与 `EVIDENCE_INDEX` 标注；
4. 若 V2/V3 出现方向相反（成本降/收益升）的条目 → 单独排查，不得静默通过。

---

## 八、⚠️ 实测时长与范围调整（2026-10-15 补记，重要）

### 8.1 实测单窗口时长远超估算

批次 1 首份（`combo_study_h20`）实测：**5 个组合 × ~600s ≈ 43 分钟/窗口**
（`C5_V0_基线` 971s、`C5_V2_仅尾部剔除` 1547s 为累计值）。

按此推算 **52 窗口（副本侧）需 30+ 小时**，远超 §二 估算的 11~15 小时
（原估算按「单窗口 400~600s」，实际 combo_study 类高一个量级）。

### 8.2 范围调整：只跑**跨线窗口**（`--crossing-only`）

**判据**：窗口起点 < `2023-08-28`（印花税分段生效日）⇒ 窗口内交易跨越生效日
⇒ **受缺陷影响**（与 `gen_evidence_index.STAMP_DUTY_CUT` 同口径）。

| 份 | 跨线/总窗口 |
|---|---|
| combo_study_h20 / _fixed | 1/3 各 |
| cost_model_check | 1/2 |
| five_factor_ab_v2 · impact_cost · tc_t0 · tc_t2 | 1/5 各 |
| horizon_study / _turnover_fixed | 1/3 各 |
| v2/v3_rolling_eval_ew / _full | 2/6 各 |
| **合计** | **15/52（29%）** |

→ 驱动脚本已加 `--crossing-only`；**预计 6~10 小时**（vs 全量 30+ 小时）。

### 8.3 未重算的 37 个非跨线窗口：**登记为待决，不擅自扩大范围**

- **印花税维度**：它们**不受影响**（窗口全在生效日之后）⇒ 按缺陷修复的目的，无需重算；
- **代码基线维度**：验证跑显示差异含「代码基线演进」成分（`ss_p1` 12pp 中约 10.8pp
  非印花税）⇒ 若要求「全产物同基线」，则 37 个窗口也需重算（**+30 小时**）；
- **待决点（提请双方）**：非跨线窗口是否也重算？取决于双方对「统一基线」的定义
  是「只修缺陷」还是「全量同基线」。**未得结论前不扩大范围**（避免无谓算力消耗）。

### 8.4 验收口径相应调整

- V2/V3 只对**跨线窗口**判定（非跨线窗口未重算，无对比）；
- 登记册逐条标注时须区分：「已重算（跨线窗口）」/「不受影响（窗口全在生效日后）」
  /「待决（基线一致性）」三类，**不得笼统写「已重算」**。

---

## 九、⚠️ 非跨线窗口口径定义（2026-10-15 补记，供双方裁定）

> 承接 §8.2「37 个非跨线窗口**登记为待决**」。本节给出**我方口径提案**，
> 并报告一处**原记录未捕捉到的问题**。

### 9.1 问题：只跑跨线会让 **12/12 份报告变成「新旧基线混合」**

逐份核对 `COPY_TASKS`（实测，非推断）：

| 份 | 跨线 | 非跨线 | 只跑跨线后 |
|---|:--:|:--:|---|
| combo_study_h20 / _fixed | 1 | 2 | ⚠️ 混合 |
| cost_model_check | 1 | 1 | ⚠️ 混合 |
| five_factor_ab_v2 · impact_cost · tc_t0 · tc_t2 | 1 | 4 | ⚠️ 混合 |
| horizon_study / _turnover_fixed | 1 | 2 | ⚠️ 混合 |
| v2 / v3_rolling_eval_ew · v3_full | 2 | 4 | ⚠️ 混合 |
| **合计 12 份** | **15** | **37** | **12/12 全部混合** |

**为什么这是问题**：每份报告都是**多窗口对照设计**（如 rolling_eval 的
2024-01 → 2024-07 → 2025-01 → 2025-07 是**时间序列**，其结论依赖窗口间可比）。
只重算其中 1~2 个窗口 ⇒ 该份内**同时存在「合并前代码基线」与「合并后代码基线」
两种产物** ⇒ **跨窗口比较失效**（窗口间的差异无法区分「市场变化」还是
「代码基线变化」）。

⇒ **混合基线比「全部旧基线」更危险**：后者只是印花税维度错（已知、可标注），
前者会**静默污染跨窗口结论**。

### 9.2 三个维度的正式定义（消除此前口径含混）

| 维度 | 受影响窗口 | 判据 | 是否必须重算 |
|---|---|---|---|
| **D1 印花税分段** | 仅**跨线**（起点 < 2023-08-28） | 窗口内交易跨越 2023-08-28，旧代码 `_stamp_rate` 字符串比较恒真 → 卖出成本低估 | **是**（15 个） |
| **D2 代码基线一致性** | **全部 52 个** | A2 合并后代码演进（验证跑实测差异 12pp，远超印花税 ~1.2% 量级） | **取决于是否要跨窗口比较** |
| **D3 数据/依赖变更** | 视具体 | 数据集、估值源等 | 本轮不涉及 |

**此前口径含混处**：§8.4 把非跨线窗口归为「不受影响」——那**只对 D1 成立**，
对 D2 不成立。本节予以区分。

### 9.3 我方提案：按「结论是否依赖跨窗口比较」分档

| 档 | 判据 | 份 | 窗口数 | 处置 |
|:--:|---|:--:|:--:|---|
| **A** | 结论**依赖跨窗口比较**（rolling 时间序列、多期稳健性检验） | v2/v3_rolling_eval_ew · v3_full · five_factor_ab_v2 · impact_cost · tc_t0 · tc_t2 | **26** | **须全份同基线** → 要么补跑全份，要么整份不重算 |
| **B** | 各窗口**独立成结论** | combo_study_h20 / _fixed · horizon_study / _turnover_fixed · cost_model_check | **11** | 可只跑跨线；**但须在产物与报告中显式标注基线** |
| **C** | 已废弃 / 被取代 | ——（本轮无） | 0 | 不重算 |

> A/B 分档是**我方按脚本语义的判断**，须主干确认（尤其 `five_factor_ab_v2` 等
> 是否确为「多期稳健性」而非「独立期」）。

### 9.4 无论是否重算，都须立即落实的两条（低成本、高收益）

1. **产物带基线标识**：重算产物 JSON 写入生成时的 `git rev-parse HEAD`（短 sha）
   与时间戳 —— 否则「哪个窗口是哪条基线」**事后无法追溯**；
   - 现状：`reports/_recalc/{name}_{window}.json` **不含基线信息** ⇒ 一旦
     日后代码再演进，混合基线的产物将无法区分；
   - 落地点：`scripts/run_recompute.py` 写产物时加 `_baseline` 字段
     （**须等本轮重算结束**再改——改的是重算的驱动）。
2. **报告标注纪律**：凡引用重算产物的文档，须逐窗口标注
   「新基线 `sha`」/「旧基线（合并前）」，**不得笼统写「已重算」**。

### 9.5 我方结论与待裁定项

- **我方倾向**：37 个非跨线窗口**默认不重算**（省 ~26 小时），
  但**A 档 6 份（26 窗口）须由主干确认是否补跑**；在确认前，
  这 6 份的**跨窗口结论暂不可用**（标注为「基线混合，结论待定」）。
- **待主干裁定**：
  1. A/B 分档是否认可（尤其 6 份是否确为「依赖跨窗口比较」）？
  2. A 档 26 窗口是否补跑（约 **18~20 小时**，按 43 分钟/窗口）？
  3. 若都不补跑 —— 是否接受「**回滚方案**」：15 个跨线重算产物**不并入正式报告**，
     仅作为「印花税缺陷影响量」的**独立证据**保存？
     （我方认为这是**当前信息下最诚实的选择**：既拿到影响量，又不污染跨窗口结论。）

**本节的判断基于脚本语义与文件名推断，未经逐份阅读其结论文本 —— 若主干掌握
某份确为「独立期结论」的证据，以贵侧为准。**
