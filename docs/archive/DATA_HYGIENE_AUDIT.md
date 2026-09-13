# 数据卫生与沉没数据审计

## 发布包原则
- 不携带 candidate_pool.json、watchlist.json、pool_state.json 等历史运行状态。
- 不携带日志、缓存、__pycache__、.pyc、.bak。
- Walk-forward/Alpha 研究模块不得依赖每日选股脚本中的运行状态。

## 每日选股状态
每日选股股票池、候选池、游标等属于运行态数据，默认放在用户目录 `~/.ai-stock-god/`，或通过环境变量指定：
- `AI_STOCK_WATCHLIST_FILE`
- `AI_STOCK_STATE_DIR`
- `AI_STOCK_LOG_DIR`

项目找不到外部股票池时必须报错，不允许回退到项目内静态样例。

## 历史研究
历史回测必须使用不晚于信号日的 PIT 股票池/数据快照。当前 watchlist、candidate pool、今日行情不得替代历史数据。
