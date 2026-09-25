# -*- coding: utf-8 -*-
"""Point-in-time (PIT) 研究数据子集。

本包只放「保证研究时点正确性」的纯函数模块：不落盘、不发网络请求、
不依赖项目内其他业务包，因此可以在任何环境下单独 import 与单测。

设计红线（各模块共同遵守）：

* **缺失 ≠ 已知**。PIT 数据缺失时绝不推断为「可交易」「未停牌」「未 ST」，
  未知应显式保持未知，或按调用方的 strict 语义拒绝该样本。
* **不做自动事件合成**。停牌 / ST / 退市等事件只接受外部已核验的事件主表，
  绝不把「当日缺失行情 bar」自动解释成停牌。
* **时间单调性**。任何记录的 availability / publication / as-of 时间戳晚于
  研究截止时点的，一律视为前视偏差并拒绝。

模块一览：

* :mod:`pit.pit_integrity`        —— 重复观测、时序错乱、前视时间戳的前置校验。
* :mod:`pit.pit_universe_builder` —— 由带日期的证券主表构建 PIT 宇宙快照。
* :mod:`pit.pit_event_master`     —— 已核验风险 / 停牌事件主表（保守只读）。
* :mod:`pit.pit_trading_filter`   —— 将事件证据应用到可交易性过滤。
* :mod:`pit.pit_research_rows`    —— 仅由 PIT 可交易观测构建研究样本行。
* :mod:`pit.pit_fundamentals`     —— **PIT 财务数据**：按**公告日**索引业绩报表，
  给定 ``(code, date)`` 只返回该日**确实已公告**的最新一期。
  它是"财务数据不得前视"的唯一执行点 —— 前视偏差不会报错，只会让回测悄悄变好。

依赖方向为单向：``research_rows -> trading_filter -> event_master``，
``integrity`` 与 ``universe_builder`` 互不依赖，也不依赖其余模块。
``pit_fundamentals`` 独立（纯内存查表，不落盘、不发网络请求）。
"""
