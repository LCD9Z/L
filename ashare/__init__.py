# -*- coding: utf-8 -*-
"""A 股市场结构与确定性特征层。

本包是**纯计算层**：不联网、不读写文件、不依赖 pandas/numpy，
输入完全由调用方提供，输出完全确定（相同输入必得相同输出）。
这是它能在 LLM 判断之前独立运行、并被单测完整覆盖的前提。

共同红线：

* **缺失保持缺失**。输入缺字段时不填充合成值、不做均值替代，
  缺失在下游显式可见（见 :mod:`ashare.ashare_factor_engine`）。
* **不扩大数据语义**。资金流只给可复核的比率与标签，
  不解释为「主力买入」；事件只做结构化与风险标签，不猜测影响方向与幅度。
* **规则与数据分离**。涨跌幅限制优先取逐日数据源字段，
  模块内只提供市场结构层面的默认口径（见 :mod:`ashare.ashare_market`）。

模块一览：

* :mod:`ashare.ashare_market`         —— 板块归属、涨跌停限制、可执行性约束。
* :mod:`ashare.ashare_factor_engine`  —— 日线派生的确定性因子与候选打分。
* :mod:`ashare.ashare_cross_section`  —— 横截面因子排名与候选排序。
* :mod:`ashare.ashare_event_engine`   —— 公告 / 业绩 / 解禁 / 减持 / 回购 /
  龙虎榜等事件的归一化与风险标签。
* :mod:`ashare.ashare_flow_engine`    —— 资金流与龙虎榜特征。
* :mod:`ashare.ashare_universe`       —— 候选池硬门槛筛选 + 可解释排序。

依赖方向：``universe -> market``（唯一一条内部边），其余模块彼此独立。
"""
