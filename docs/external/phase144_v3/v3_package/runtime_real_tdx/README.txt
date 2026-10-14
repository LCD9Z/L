A股量化 TDX 真实数据闭环 V3（10万元模拟资金）

目标：
真实通达信 .day -> 五因子 -> Top20 -> T+1开盘模拟买入 -> 持仓 -> 每日净值 -> 每20个交易日调仓 -> 交易成本/涨跌停约束 -> 回撤/Sharpe/日报。

冻结策略：A股5Factor_RankTop20_20D
五因子：ret_20(-)、vol_20(-)、amihud_20(+)、log_amount_20(-)、max_ret_20(-)
流动性：20日平均成交额 >= 1亿元
组合：Top20，20个交易日调仓，等权，100股整手
初始资金：100,000 元
成本：买/卖佣金0.03%，最低5元；卖出印花税0.05%；买卖滑点0.05%
执行：信号日收盘后产生信号，下一交易日开盘模拟执行；T+1持仓逻辑；仅模拟，不连接券商。
数据：RAW TDX .day；不使用 tdx_daily_all.csv；不补造历史ST；MaxCorr关闭。

运行：双击 start.bat
TDX路径：tdx_path.txt（默认 D:\new_tdx\vipdoc）

输出：
- output\all_top20_signals.csv：所有20日调仓信号
- output\trades.csv：模拟成交记录
- output\daily_nav.csv：每日净值/回撤
- output\rebalance_log.csv：调仓日志
- output\run_report.json：机器可读总报告
- output\run_report.txt：简版报告
