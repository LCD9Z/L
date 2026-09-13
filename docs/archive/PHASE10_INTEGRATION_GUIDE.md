# Phase 10：系统集成版

本阶段将此前独立的模块真正接入每日主流程：

1. **市场环境**：每日先判断 STRONG / RANGE / WEAK。
2. **行业强度**：基于当前股票池历史K线计算行业相对强度，并调整个股评分。
3. **个股评分**：保留透明规则与周期阶段识别。
4. **风险控制**：每日结果尝试写入建议仓位和风控说明；若数据不足则安全降级。
5. **长期验证**：每日推荐自动写入 `tracking.db`，后续通过 `run_tracking.py backfill` 回填真实表现。
6. **统一日报**：`reports/daily/screening_*.json` 现在包含市场、行业排名和个股结果。
7. **飞书**：保留原有多维表格写入与每日消息推送。

## 建议运行方式

```bash
python daily_stock_pick.py --dry-run
python daily_stock_pick.py --no-deep
python daily_stock_pick.py
python run_tracking.py backfill
python run_tracking.py stats
```

## 注意

- 行业分类当前优先读取 `watchlist.json` 中的 `industry` 字段；旧数据兼容从 `note` 推断。
- 真实长期回测仍需要 Point-in-Time 历史股票池和可靠行业分类数据。
- 所有输出仅供研究与辅助决策，不构成投资建议。
