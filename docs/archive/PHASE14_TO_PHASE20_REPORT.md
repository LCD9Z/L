# Phase 14–20 连续测试与升级报告

本轮遵循“先修复真实性，再提高验证能力，最后设置发布闸门”的原则；没有通过人为优化参数来追求更高历史收益。

## Phase 14：数据质量与 Point-in-Time 审计
新增 `data_quality.py`：OHLC 完整性、日期顺序、重复日期及未来发布日期检查。

## Phase 15：公司行为处理
新增 `corporate_actions.py`：拆分、现金分红的保守价格调整接口。真实复权数据仍应来自可信 Point-in-Time 数据源。

## Phase 16：风险预算
新增 `risk_budget.py`：逆波动率权重、单仓上限与 HHI 集中度指标。

## Phase 17：市场状态分段验证
新增 `regime_validation.py`：牛市、熊市、震荡状态下的独立统计。

## Phase 18：AI Alpha 对照实验
新增 `alpha_experiment.py`：显式比较纯量化、量化+AI、AI 等实验组，避免把报告能力误认为 Alpha。

## Phase 19：模拟盘不可篡改倾向记录
新增 `paper_trading.py`：追加式事件账本接口，用于记录信号和后续成交。

## Phase 20：发布闸门
新增 `release_gate.py`：测试数量、密钥扫描、Point-in-Time 验证未满足时拒绝标记为可发布。

## 三轮验证
1. 全量 pytest 回归；
2. 全项目 compileall 与敏感配置检查；
3. Phase 14–20 端到端专项测试。

**重要结论：** Phase 20 提高的是研究真实性与验证门槛，并不能在没有完整真实 A 股 Point-in-Time 数据和长期前瞻模拟盘结果的情况下证明策略必然盈利。
