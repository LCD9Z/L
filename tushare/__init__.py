# -*- coding: utf-8 -*-
"""TuShare 数据接入（可选依赖）。

- `tushare_provider`     —— TuShare 通用数据提供方（用 TUSHARE_TOKEN 环境变量）
- `tushare_ashare_events` —— A 股事件 / 公告数据接入

共同红线：
1. Token 仅经环境变量 `TUSHARE_TOKEN` 提供，绝不写入源码 / JSON / 日志。
2. 依赖缺失时降级（importorskip / 返回空），不阻断主流程。
3. 数据性质（是否已除权、是否覆盖退市）如实声明，不假装完整。
"""
