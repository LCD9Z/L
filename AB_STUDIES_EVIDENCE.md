# A/B 对照与 H-C1 检验的原始结果（证据归档）

> **归档日期**：2026-09-16
> **来源**：会话 scratch 目录 `…/WorkBuddy/2026-09-13-15-48-32/`，
> 这些 JSON **此前从未入库**，仅以汇总数字的形式出现在报告中。
> **性质**：本文件说明这 4 份 JSON 是什么、为什么留着、以及复算时要注意的口径。

## 一、文件对照

| 文件 | 对应阶段 | `verdict`（原文） | 支撑报告 |
|------|---------|------------------|---------|
| `tdx_contrarian_ic_summary.json` | H-C1 复合反转 **IC 层面**检验 | **强支持** | [`CONTRARIAN_HYPOTHESIS_REPORT.md`](docs/archive/CONTRARIAN_HYPOTHESIS_REPORT.md) |
| `tdx_ab_stage1_summary.json` | A/B 第一阶段（固定滑点 0.05%） | B 优于 A 且扣费后为正 → 支持「存在可实现 Alpha」（待基准指数复核） | [`PORTFOLIO_AB_REPORT.md`](docs/archive/PORTFOLIO_AB_REPORT.md) |
| `tdx_ab_stage2_summary.json` | A/B 第二阶段（动态滑点） | 同上 —— **verdict 文案未随脚本更新，数字已变**（B 年化被成本吃掉约 10.5pp/年） | [`PORTFOLIO_AB_REPORT_2.md`](docs/archive/PORTFOLIO_AB_REPORT_2.md) |
| `tdx_ab_stage3_summary.json` | A/B 第三阶段（沪深 300 基准） | 两窗口超额符号相反 → **证据不足** | [`PORTFOLIO_AB_REPORT_3.md`](docs/archive/PORTFOLIO_AB_REPORT_3.md) |

> **注意**：`tdx_ab_stage2_summary.json` 的 `verdict` 字段与一阶段完全相同，
> 这是**脚本的缺陷**（改滑点模型时未同步记录成本模型），不是数据重复。
> 请以报告与数字为准，不要据此 JSON 的 verdict 判断二阶段结论。
>
> **根因（2026-09-16 查明并修复）**：脚本输出的 `params` **从未记录 `slip_mode`**，
> 结论文案也不含滑点模型 —— 所以一阶段（固定滑点）与二阶段（动态滑点）
> 除了数字之外**看起来一模一样**。已修复 `scripts/run_contrarian_portfolio.py`：
> ①`params` 新增 `slip_mode`；②结论文案加 `[滑点=…]` 前缀；
> ③抽出 `_result_payload()` 并加守卫测试 `test_contrarian_payload_records_slippage_model`。
>
> **本目录 4 个 JSON 是修复前的产物，保持原样**（它们是历史证据，不可改写）。
> 其 `params` 无 `slip_mode` 字段属**预期**；如需区分，请以文件名与数字为准。

## 二、为什么必须留着

这 4 份结果记录了本项目最重要的一次**自我证伪**，链条如下：

| 阶段 | 发现 | 当时的判断 |
|:---:|------|-----------|
| 一 | B（H-C1 反转）大幅优于 A（基线动量），+41.04pp / +26.96pp | 看似找到 Alpha |
| 二 | 换用真实动态滑点后，B 的优势被成本吃掉约 10.5pp/年（成本敏感性是 A 的 **5 倍**） | 优势稳健但绝对水平须下调 |
| 三 | 加入沪深 300 基准后，**B 的超额仅 +0.48pp / −4.88pp** | 反转只是修复了方向性错误、回到指数水平，**未超越市场** |

**最终对外结论：`ALPHA_NOT_ESTABLISHED`。**

若无这些原始 JSON，上述链条只能靠报告里的汇总数字间接印证 ——
无法复算，也无法在结论被质疑时回溯到原始输出。

## 三、口径提醒（引用前必读）

| 文件组 | 年化口径 | 公式 |
|--------|---------|------|
| 本目录 `tdx_ab_*` | **几何（复合）** | `(期末/期初)^(1/年) − 1`，其「年化超额」= 两个几何年化率相减 |
| `reports/survivorship_rerun/*.json`、其余 `tdx_*_summary.json` | **算术** | `mean(日超额) × 252` |

**两组数字不可直接比较**（有波动时必然 算术 ≥ 几何）。详见
[`CALIBRATION_DISCREPANCY_REPORT.md`](docs/archive/CALIBRATION_DISCREPANCY_REPORT.md) §2.3。

另：`tdx_contrarian_ic_summary.json` 是**横截面 IC 证据，不是组合收益**，
未计交易成本 —— 其组合层面的验证即上述 A/B 实验。

## 四、复现

| 文件 | 生成脚本 |
|------|---------|
| `tdx_contrarian_ic_summary.json` | `python scripts/run_contrarian_study.py --dataset D:/tdx_dataset` |
| `tdx_ab_stage{1,2,3}_summary.json` | `python scripts/run_contrarian_portfolio.py --dataset D:/tdx_dataset`（三阶段为同一脚本的不同版本，按报告中的事前登记逐阶段修改后运行） |
