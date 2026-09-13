# -*- coding: utf-8 -*-
"""L3 回测闭环 · 实现层（由 tracking.py 拆分）。

对外请继续使用 `import tracking` / `from tracking import ...`；
`tracking.py` 是门面，重新导出全部符号，故拆分对下游零影响。

| 模块 | 职责 |
|------|------|
| `costs`  | 交易成本模型与净收益率换算 |
| `schema` | 常量与表结构（默认库路径、建表语句、立场映射） |
| `store`  | SQLite 持久化（连接 / 建表 / 写入 / 查重 / 列举） |
| `stats`  | 校准统计（命中判定 / 回填 / 胜率与平均收益） |

依赖方向（无环）：`costs`/`schema` → `store` → `stats`

共同红线：
1. 零第三方依赖（仅标准库 sqlite3 / dataclasses）。
2. **缺失数据不补造**：回填不到真实收盘价的记录保持 pending，不猜价格。
3. 胜率口径固定：看多 >0 命中、看空 <0 命中、中性不参与胜率。
"""
