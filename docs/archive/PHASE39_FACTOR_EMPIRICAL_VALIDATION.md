# Phase 39 — Factor Empirical Validation Runner

## 目标
把 Phase 38 的“候选因子注册 + 预筛门”接到可执行的经验验证链路，做到：

1. 只验证数据里真实存在且达到覆盖率门槛的因子；
2. 使用 `factor_validation.validate_factor`，严格按 t 日因子、未来 t+h 收益计算，避免未来函数；
3. 同时输出 1/3/5/10/20 日维度的 IC、RankIC、ICIR、RankICIR、正 IC 比例、Top-Bottom spread 与胜率；
4. 再由 Phase 38 `factor_gate` 做 5 日预筛及高相关因子去冗余；
5. 不填充、不伪造缺失数据，也不把工程测试结果包装成真实 Alpha。

## 新增/扩展

### `ashare_factor_engine.py`
新增可从历史 K 线直接计算的候选因子：
- `momentum_10d`
- `momentum_60d`
- `momentum_accel_5_20`
- `breakout_20d`
- `realized_vol_60d`
- `range_pct_20d`
- `volume_ratio_20d`
- `turnover_mean_20d`

保留已有因子名，避免破坏旧接口。

### `factor_lab.py`
支持 JSONL/CSV 输入，输出完整 JSON 报告。核心流程：

`rows → availability → validate_factor → gate_factors`

默认：
- horizons = 1/3/5/10/20
- min_coverage = 20%
- min_assets = 20
- gate horizon = 5d

## 输出语义

- `PRE_SCREEN_PASS`：通过预筛门，进入后续 Walk-Forward/OOS。
- `INCONCLUSIVE`：证据不足，不能得出因子有效或无效结论。

这里的 `PRE_SCREEN_PASS` **不是 Alpha_SUPPORTED**。最终结论仍必须经过 PIT 数据审计、Walk-Forward、独立 OOS、A 股交易规则与成本模型、基准对照等流程。

## 8GB 运行设计

纯标准库、逐因子验证、无需 Pandas/NumPy/模型训练。适合本地 8GB 机器和夜间批处理。
