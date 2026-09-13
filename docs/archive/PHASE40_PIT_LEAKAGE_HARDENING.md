# Phase 40 — PIT / 隐性数据泄漏加固

本版本完成以下隔离：

1. `walk_forward.py` 不再导入 `daily_stock_pick.py`，改依赖纯历史模块 `cycle_price_action.py`。
2. 每日选股的 watchlist/candidate pool/pool state 改为外部运行态目录，默认 `~/.ai-stock-god/`。
3. 项目发布包不再携带静态股票池和运行日志。
4. 缺少外部 watchlist 时，daily picker 必须明确报错，不能回退到项目静态样例。
5. 历史回测继续要求 PIT 股票池；当前股票池不能替代历史股票池。

本阶段只加固研究边界，不宣称已经获得真实历史 Alpha。真实 Alpha 仍需通过 PIT 历史数据、OOS、交易成本和基准数据验证。

## v4.2 追加修复

6. 新增 `pit_integrity.py`：检查 code+trade_date 重复、日期倒序、可用/发布时间晚于研究 cutoff 等问题。
7. `real_alpha_pipeline.py` 现在强制要求提供 PIT 历史股票池；缺失时返回 `INCONCLUSIVE`，不允许当前股票池替代。
8. OOS 回测保留 OOS 开始日前的历史 K 线作为因子 warm-up，但只允许在 `oos_start` 当日及以后产生交易信号，避免冷启动偏差。
9. OOS 每个交易日进一步按 PIT 股票池过滤，防止历史不存在的成分进入回测。
10. EOD 行情不被错误要求必须存在 `published_at`；新闻/事件等信息仍必须使用自身可用时间戳做 PIT 审计。

当前状态：工程级 PIT/未来信息防护增强；尚无真实认证全市场历史数据，因此不得据此宣称 Alpha 已成立。
