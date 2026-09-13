# -*- coding: utf-8 -*-
"""因子研究子包：注册、准入、验证、IC 检验与盲测。

本包回答的是「一个因子值不值得进入研究结论」，而不是「因子怎么算」——
后者在 :mod:`ashare.ashare_factor_engine`。两者分离，
使得同一套因子可以在不同数据版本上重复跑同一套验证流程。

共同红线：

* **可支持 ≠ 想要测**。注册表区分「想测的因子」与「当前数据实际能支撑的因子」，
  不可得的基本面 / 事件因子绝不静默填充（见 :mod:`factors.factor_registry`）。
* **无前视泄漏**。远期收益只由**之后**的收盘价构建，
  t 时刻的观测永远看不到 t+h 的收盘价作为输入因子。
* **不到门槛就不出结论**。覆盖度不足、样本不足时给出的是「无法判定」，
  而不是一个看起来能用的数字。
* **幸存者偏差要显式声明**。横截面 IC 看排序关系，受幸存者偏差影响远小于
  组合回测，但**不等于免疫**；任何 Alpha 结论仍需过 ``release_gate``。

模块一览：

* :mod:`factors.factor_registry`     —— 候选因子注册表与可支持性查询。
* :mod:`factors.factor_gate`         —— 质量 + 冗余度的证据化准入闸门。
* :mod:`factors.factor_validation`   —— 轻量、防泄漏的横截面因子验证。
* :mod:`factors.factor_ic_lab`       —— 横截面 IC 检验引擎（经济逻辑驱动）。
* :mod:`factors.factor_lab`          —— Phase 39 因子实证 runner（读 PIT 研究行）。
* :mod:`factors.factor_blind_test`   —— Phase 45 流式价格因子盲测。

依赖方向：``lab -> (gate, registry, validation)``、``blind_test -> ashare``，单向无环。
"""
