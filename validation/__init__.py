# -*- coding: utf-8 -*-
"""回测与策略结果的验证子包。

这里回答的是**「一个回测结果能不能信」**，而不是「策略能不能赚」。
因此本包的函数基本都返回「问题清单 / 判定 / 置信区间」这类**可质疑**的结构，
而不是一个看起来很确定的收益数字。

模块一览：

* :mod:`validation.validation_suite`     —— 编排入口：质量 + 样本充分性 +
  风险 + 红队审计的合成判定（`PASS` / `CAUTION` / `FAIL`）。
* :mod:`validation.performance`          —— 绩效指标（CAGR / 波动 / 夏普 / 回撤），
  存在的意义就是**避免只看收益率**。
* :mod:`validation.benchmark`            —— 基准对比与超额收益（无第三方依赖）。
  含**等权全市场基准**构造器 `equal_weight_returns`（日频再平衡、PIT 成分、
  停牌按 0 收益持有）——用于纠正"全市场策略只对标沪深300"的基准错配。
* :mod:`validation.strategy_validation`  —— Bootstrap 与前向窗口划分，
  判断结果是否只是运气。
* :mod:`validation.robustness`           —— 参数稳健性扫描，
  避免结论依赖某一组"最佳参数"。
* :mod:`validation.stress_test`          —— 滑点敏感性压力测试。
* :mod:`validation.phase13_risk`         —— 红队审计：前视执行、单笔巨亏、
  同日过度集中。
* :mod:`validation.health_monitor`       —— 实盘/模拟盘健康度告警。
* :mod:`validation.multiple_testing`     —— **多重检验校正**：紧缩夏普比率（DSR）、
  BH-FDR、Bonferroni、最小跟踪记录长度（MinTRL）。本项目累计报告 30+ 项
  统计检验，未做校正时"至少出现一个显著结果"的概率达 78.5%——本模块是把
  这件事算进显著性里的唯一入口。

共同红线：

* **不补造数据**。`stress_test` 只做敏感性外推并显式标注
  `assumption: Approximate sensitivity only`，不作为权威结果。
* **样本不足就判不足**。交易数不够、区间不够时给出的是"无法判定"，
  不是一个勉强能看的数字。
* **关键问题一票否决**。`validation_suite` 中
  `data_quality_failed` / `no_realized_trades` /
  `possible_lookahead_or_same_day_execution` 属 critical，直接判 `FAIL`。
* **输出必须带免责声明**：`not_investment_advice`。

依赖方向：`validation_suite -> (performance, phase13_risk)`，
外加一条对根目录 `data_quality` 的外部依赖；其余模块彼此独立。
"""
