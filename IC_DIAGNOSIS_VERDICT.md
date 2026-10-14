# IC 虚高诊断 · 判决（V-IC-DIAGNOSIS）

> 生成时间：2026-10-14（A2 合并时固结）　数据：`D:/tdx_dataset_v2`（认证数据集）
> 预注册：`IC_DIAGNOSIS_PREREG.md`（H-ICX）
> **判决日期**：2026-10-11（执行日；本文件按合并后纪律补立判决正本）

---

## 结论速览

| 检验问题 | 判定 | 依据 |
|------|------|------|
| 「不屏蔽涨跌停/停牌/公告 → 回测 IC 系统性虚高 20~30%」（外部项目暗门 #2）在本项目是否成立 | ⚠️ **不成立，但为边界结果** | `reports/ic_diagnosis.json`：L1M1 相对 L0M0 的 \|IC\| 衰减中位 **0.144**（远小于 20~30% 的量级）；L1M1 中 t<2 的因子数 **0** |

**一句话**：外部项目警示的「IC 虚高」现象在本项目的口径下**未复现**；但衰减中位 0.144 不是零，判定为**边界结果**而非强否证。

## 产物

- `reports/ic_diagnosis.json`（逐因子 L0M0/L1M1 对比、`abs_ic_decay_L1M1_vs_L0M0`、`factors_t_below_2_in_L1M1`）
- 复现：按 `IC_DIAGNOSIS_PREREG.md` §执行 一节的口径重跑

## 边界与连带

- 本诊断只解释约 16% 的「强 IC 不赚钱」落差（承自预注册动机段的既有拆分），
  剩余部分由成本侧实验承接（见 `IMPACT_COST_VERDICT.md` / `TURNOVER_CAPACITY_VERDICT.md`）。
- 本判决为 IC 层诊断，**不涉及交易成本**，不受 `COST_BASELINE_PENDING_RECOMPUTE.md`
  登记的分段缺陷影响（该册只收成本类产物）。
