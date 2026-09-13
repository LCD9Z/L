# Phase 35 — Stage-2 Alpha Reranking

## 目标
让 Stage-2 的资金流、龙虎榜、涨跌停/炸板微结构和事件风险真正参与候选排序，而不是只作为附加信息。

## 实现
新增 `stage2_scoring.py`，对 Stage-1 候选做确定性的横截面二次排序：

- 正向：资金流均值、资金流为正比例、龙虎榜净买为正比例、龙虎榜净买总额、涨停高度
- 负向：跌停天数、炸板代理次数、高风险事件数量
- 默认 Stage-2 overlay 权重 35%，最高限制 50%
- Stage-2 数据缺失时不制造数值；证据覆盖率越低，overlay 影响越小
- 最终输出 `stage2_alpha_score` 与 `stage2_alpha_overlay`
- 保留 Stage-1 分数，避免 Stage-2 噪声完全覆盖基础量价信号

## 验证
- Python compileall：PASS
- 全量单元测试：**88 passed**
- 1000 行合成 smoke test：`seen=1000 / eligible=1000 / errors=0 / stage1=300 / stage2=50 / ai=20`

## 重要边界
这证明的是工程链路和排序逻辑正确，不代表真实 A 股 Alpha 已经成立。真实 Alpha 结论仍必须使用经过 Point-in-Time 审计的长期 A 股历史数据做 walk-forward / out-of-sample 回测。
