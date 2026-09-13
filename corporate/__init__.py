# -*- coding: utf-8 -*-
"""A 股公司行为（corporate action）与复权因子子包。

与 :mod:`tdx` 的分工：TDX 提供**不复权**的原始价格，本包提供**显式**的
公司行为事件与由其派生的复权因子。两者不互相隐式补全。

共同红线：

* **缺行 ≠ 无事件，也不 = 有事件**。数据源缺失一行时既不伪造除权除息日，
  也不假定当日无事件——覆盖度必须由 :func:`corporate.corporate_action_provider.audit_action_coverage`
  显式审计并出具结论。
* **凭证不入研究运行时**。TuShare 等外部数据源为可选依赖，
  仅在显式传入 token/client 时才访问；离线研究路径不依赖它。
* **证据先行**。所有因子带 evidence 摘要，说明其来源与可信级别，
  便于在发布门禁（``release_gate``）中区分「已核验」与「未知」。

模块一览：

* :mod:`corporate.corporate_actions`         —— 事件模型与后复权因子推导
  （现金分红、送股、配股、拆并股、现金+送股组合）。
* :mod:`corporate.corporate_action_provider` —— 数据源适配器与覆盖度审计。
* :mod:`corporate.corporate_action_ingest`   —— 提供商导出 CSV 的摄入与审计。

依赖方向：``ingest -> provider -> actions``，单向无环。
"""
