# 换手与容量约束 · 判决（V-TURNOVER-CAPACITY）

> 生成时间：2026-10-14（A2 合并时固结）　数据：`D:/tdx_dataset_v2`（认证数据集）
> 预注册：`TURNOVER_CAPACITY_PREREG.md`（H-TC）
> **判决日期**：2026-10-11（执行日；本文件按合并后纪律补立判决正本）

---

## 结论速览

| 子检验 | 判定 | 依据 |
|------|------|------|
| **T1**（换手约束能否改善结果） | ❌ **无效** | `reports/tc_t0.json` / `reports/five_factor_ab_v2.json`：加约束相对基线无改善 |
| **T2**（容量约束能否触发） | ➖ **从未触发（未被检验）** | `reports/tc_t2.json`：信号日成交额口径下约束从未生效，该情形无判据 |

**一句话**：换手/容量约束对本策略**不是主要矛盾** —— T1 无效、T2 未被触发；
这正是预注册 §五 局限 #1 的预判（「这本身就是结论：容量/冲击成本对 100 万小资金不是主要矛盾」）。

## 产物

- 完整报告：`IMPACT_AND_CAPACITY_REPORT.md`
- `reports/tc_t0.json`（本次重测 T0，基线）· `reports/tc_t2.json`（T2）·
  `reports/five_factor_ab_v2.json`（T1）
- 复现：按 `TURNOVER_CAPACITY_PREREG.md` §执行 一节的口径重跑

## 边界与连带

- 「T2 未被检验」是**条件性结论**：只在既有的资金/持仓规模下成立；规模上去后须重检。
- ⚠️ 本组产物窗口跨越印花税分段生效日 2023-08-28，成本数字受
  `COST_BASELINE_PENDING_RECOMPUTE.md` 登记的分段缺陷影响（低估卖出成本）；
  **方向性结论（T1 无效）不受影响**，数字重算待 A2 合并落定后统一进行。
