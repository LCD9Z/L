# 目录全景（分层后）

> 本文件由 `scripts/gen_layout_doc.py` **从真实仓库状态自动生成**，请勿手工编辑；
> 每次移动模块后重新生成即可，避免文档与实际结构漂移。
> 生成命令：`python scripts/gen_layout_doc.py`　校验：`python scripts/gen_layout_doc.py --check`

## 总览

| 指标 | 值 |
|------|----|
| 子包数 | **20** |
| 已入包模块 | **85**（约 10,860 行） |
| 根目录 `.py` | **57**（约 6,108 行） |
| 分层前（起点） | 188 个平铺在根目录，零子目录 |
| `tests/` / `scripts/` | 第一轮迁出 |

> 注：`fetch/` 是 `data_fetcher.py` 门面背后的实现包——
> **对外请继续用 `from data_fetcher import ...`**，不要直接依赖 `fetch.*`。

## 子包

### `alpha/`　（2 模块，约 229 行）

**职责**：Alpha 假设实验与存活实验室。

<details><summary>包级说明与红线（点击展开）</summary>

```
Alpha 假设实验与存活实验室。

- `alpha_experiment`     —— 单一经济假设的因子检验入口
- `alpha_survival_lab`  —— Alpha 存活实验协议（预登记门槛、INCONCLUSIVE 兜底）

共同红线：
1. 假设须预先登记（样本外起点、显著性门槛），不得事后调参挑结论。
2. 不把工程/样本内实验结果包装成真实 Alpha 结论。
3. 数据不足或证据缺失时强制返回 `INCONCLUSIVE`，不补造、不推断为有效。
```

</details>

| 模块 | 行数 |
|------|-----:|
| `alpha/alpha_experiment.py` | 11 |
| `alpha/alpha_survival_lab.py` | 218 |

### `ashare/`　（6 模块，约 495 行）

**职责**：A 股市场结构与确定性特征层。

<details><summary>包级说明与红线（点击展开）</summary>

```
A 股市场结构与确定性特征层。

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
```

</details>

| 模块 | 行数 |
|------|-----:|
| `ashare/ashare_cross_section.py` | 53 |
| `ashare/ashare_event_engine.py` | 127 |
| `ashare/ashare_factor_engine.py` | 103 |
| `ashare/ashare_flow_engine.py` | 54 |
| `ashare/ashare_market.py` | 99 |
| `ashare/ashare_universe.py` | 59 |

### `console/`　（2 模块，约 254 行）

**职责**：交互式命令行层（展示、输入、团队流程执行）。

<details><summary>包级说明与红线（点击展开）</summary>

```
交互式命令行层（展示、输入、团队流程执行）。

从 `main.py` 迁出。`main.py` 保留为**入口与编排**：它调用本包完成
「读输入 → 跑团队 → 出报告」，自身不再包含展示与交互细节。

模块一览：

* :mod:`console.display` —— 终端颜色、打印辅助、输入辅助（纯展示/交互，无业务判断）。
* :mod:`console.teams`   —— 多 Agent 团队的阶段规格与统一执行器。

共同红线：

* **本层不做业务判断**。评分解析、阶段推进、结果落库都由
  :mod:`orchestrator` 负责；这里只负责「把提示词展示给用户、把粘贴内容读回来」。
* **空输入绝不提交**。用户粘贴为空时跳过该阶段，不得写入空结果污染会话。
* **交互可被随时中断**。每次提交后立即 `save_session()`；
  `EOFError` / `KeyboardInterrupt` 走干净退出而非抛出未捕获异常。

依赖方向：``console.teams -> console.display``，单向无环。
本包**不反向依赖** `main.py`。
```

</details>

| 模块 | 行数 |
|------|-----:|
| `console/display.py` | 108 |
| `console/teams.py` | 146 |

### `corporate/`　（3 模块，约 444 行）

**职责**：A 股公司行为（corporate action）与复权因子子包。

<details><summary>包级说明与红线（点击展开）</summary>

```
A 股公司行为（corporate action）与复权因子子包。

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
```

</details>

| 模块 | 行数 |
|------|-----:|
| `corporate/corporate_action_ingest.py` | 71 |
| `corporate/corporate_action_provider.py` | 202 |
| `corporate/corporate_actions.py` | 171 |

### `factors/`　（6 模块，约 1,212 行）

**职责**：因子研究子包：注册、准入、验证、IC 检验与盲测。

<details><summary>包级说明与红线（点击展开）</summary>

```
因子研究子包：注册、准入、验证、IC 检验与盲测。

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
```

</details>

| 模块 | 行数 |
|------|-----:|
| `factors/factor_blind_test.py` | 102 |
| `factors/factor_gate.py` | 83 |
| `factors/factor_ic_lab.py` | 739 |
| `factors/factor_lab.py` | 76 |
| `factors/factor_registry.py` | 82 |
| `factors/factor_validation.py` | 130 |

### `fetch/`　（8 模块，约 1,377 行）

**职责**：L2 数据管道实现层（由 data_fetcher.py 拆分）。

<details><summary>包级说明与红线（点击展开）</summary>

```
L2 数据管道实现层（由 data_fetcher.py 拆分）。

对外**不要**直接依赖本包 —— 请继续使用 `from data_fetcher import ...`。
`data_fetcher.py` 是本包的门面，重新导出全部既有符号，故拆分对下游零影响。

| 模块 | 职责 |
|------|------|
| `transport` | HTTP 传输：SSL 复用 / 内存缓存 / 令牌桶限流 / 统一 GET |
| `common`    | 公共常量与纯函数（字段表、代码规范化、数值解析、日期工具） |
| `quote`     | 实时行情（东财 + 腾讯兜底） |
| `kline`     | 历史日K（东财 / 腾讯 / 通达信本地，不复权） |
| `news`      | 新闻与事实数据包（含 Crawl4AI 可选增强） |
| `cli`       | 命令行入口 |

依赖方向（无环）：`transport`/`common` → `quote`/`kline` → `news` → `cli`

共同红线：
1. 纯标准库，零第三方依赖（Crawl4AI 为可选增强，缺失即降级）。
2. 缺失数据**不补造**：取不到就是取不到，返回空 / None 并如实标注来源。
3. 本地通达信日K为**不复权**，必须在返回包中标注，不得与前复权口径混用。
```

</details>

| 模块 | 行数 |
|------|-----:|
| `fetch/akshare_source.py` | 142 |
| `fetch/cli.py` | 41 |
| `fetch/common.py` | 120 |
| `fetch/fundamentals_source.py` | 307 |
| `fetch/kline.py` | 257 |
| `fetch/news.py` | 243 |
| `fetch/quote.py` | 137 |
| `fetch/transport.py` | 130 |

### `notify/`　（2 模块，约 240 行）

**职责**：通知通道（飞书 / Lark）。

<details><summary>包级说明与红线（点击展开）</summary>

```
通知通道（飞书 / Lark）。

- `feishu_notifier` —— 飞书多维表格写入与消息推送
- `lark_notify`     —— Lark 通用通知封装

共同红线：
1. 通知失败不得阻断主流程（选股 / 回测 / 发布），异常就地记录并降级。
2. 推送内容不含凭据、Token、密钥。
3. 与外部服务相关的失败走超时 + 重试，不无限阻塞。
```

</details>

| 模块 | 行数 |
|------|-----:|
| `notify/feishu_notifier.py` | 126 |
| `notify/lark_notify.py` | 114 |

### `phase62/`　（2 模块，约 89 行）

**职责**：PHASE62 系列 —— TDX 指数 / 序列接入（v4.9 选择性移植）。

<details><summary>包级说明与红线（点击展开）</summary>

```
PHASE62 系列 —— TDX 指数 / 序列接入（v4.9 选择性移植）。

- `phase62_series`    —— 指数序列读取与对齐
- `phase62_tdx_index` —— TDX 指数元信息适配

共同红线：
1. 保留 v4.9 原始口径，不在移植层改写语义或单位。
2. 缺失序列不补造，缺字段显式报错而非静默返回 0。
3. 与 `tdx/` 包分工：本包只管「指数侧」，个股日线仍在 `tdx/`。
```

</details>

| 模块 | 行数 |
|------|-----:|
| `phase62/phase62_series.py` | 19 |
| `phase62/phase62_tdx_index.py` | 70 |

### `pit/`　（6 模块，约 745 行）

**职责**：Point-in-time (PIT) 研究数据子集。

<details><summary>包级说明与红线（点击展开）</summary>

```
Point-in-time (PIT) 研究数据子集。

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
```

</details>

| 模块 | 行数 |
|------|-----:|
| `pit/pit_event_master.py` | 87 |
| `pit/pit_fundamentals.py` | 378 |
| `pit/pit_integrity.py` | 88 |
| `pit/pit_research_rows.py` | 44 |
| `pit/pit_trading_filter.py` | 57 |
| `pit/pit_universe_builder.py` | 91 |

### `regime/`　（3 模块，约 324 行）

**职责**：市场状态（regime）识别与回测验证。

<details><summary>包级说明与红线（点击展开）</summary>

```
市场状态（regime）识别与回测验证。

- `regime_validation`      —— 状态判定的回测验证
- `regime_backtest_report` —— 不同市场状态下的策略表现报告

共同红线：
1. 状态判定只用历史时点数据，禁止用今天的状态回填历史（避免分类漂移 / 幸存者偏差）。
2. 报告只呈现机制，不把「某状态下表现好」当作可发布结论。
3. 不依赖 `daily_stock_pick` 运行时编排，保持可独立回测。
```

</details>

| 模块 | 行数 |
|------|-----:|
| `regime/adx_router.py` | 273 |
| `regime/regime_backtest_report.py` | 35 |
| `regime/regime_validation.py` | 16 |

### `reporting/`　（3 模块，约 1,054 行）

**职责**：HTML 研究报告生成子包。

<details><summary>包级说明与红线（点击展开）</summary>

```
HTML 研究报告生成子包。

由 1.0 对 `report_generator.py` 的职责拆分而来：CSS 与 Markdown 转换原本
和生成逻辑混在同一个 950+ 行的文件里，拆开后各自可单独调整与测试。

模块一览：

* :mod:`reporting.report_styles`   —— `REPORT_CSS`，完整 `<style>` 块。
* :mod:`reporting.report_markdown` —— `markdown_to_html()`，纯函数，
  不依赖任何实例状态（支持代码块、三级标题、粗斜体、有序/无序列表、段落）。
* :mod:`reporting.report_generator` —— `HTMLReportGenerator`：各章节生成、
  拼装与保存。这是对外唯一需要使用的入口。

红线：**报告不改写结论**。本报告层只做展示，不做任何判定；所有结论在
进入报告之前就已由各自的分析与门禁环节确定。报告中出现的内容必须与
上游给出的 `verdict` / `alpha_status` 一致，不得为了可读性软化措辞
（例如把 `INCONCLUSIVE` 渲染成看似确定的表述）。
```

</details>

| 模块 | 行数 |
|------|-----:|
| `reporting/report_generator.py` | 501 |
| `reporting/report_markdown.py` | 90 |
| `reporting/report_styles.py` | 463 |

### `risk/`　（7 模块，约 937 行）

**职责**：风险与可执行性子包。

<details><summary>包级说明与红线（点击展开）</summary>

```
风险与可执行性子包。

这里放**决定"能不能做、做多大"**的模块，与 `factors/`、`ashare/` 里
"值不值得做"的模块分工不同。

模块一览：

* :mod:`risk.a_share_risk` —— A 股策略风控层：市场环境判定、ATR、
  仓位计划、regime 调整。
* :mod:`risk.risk_engine`  —— 组合级风险引擎：统一裁决是否允许新开仓
  与仓位倍率（回撤 / 连亏 / 单票上限 / 总敞口）。
* :mod:`risk.risk_budget`  —— 波动率与集中度感知的仓位权重
  （反向波动率加权 + 上限迭代再分配）。
* :mod:`risk.liquidity`    —— 流动性过滤与动态滑点模型。

共同红线：

* **优先用真实成交额**。公开数据源常只有 OHLCV，`volume` 还可能按 A 股
  常见的"手"计量；此时应**显式**从价格与成交量估算成交额，
  不能把缺失 `amount` 当成"零流动性"，也不能当成"流动性无限好"。
* **不可执行就是不可执行**。跌停封死的 bar 不能被假设成可以卖出；
  这类约束由 `execution_rules` / 回测层消费，本包只提供判定。
* **限制取严**。多个限制同时命中时取最保守的一条，不做"综合权衡"式放宽。
```

</details>

| 模块 | 行数 |
|------|-----:|
| `risk/a_share_risk.py` | 46 |
| `risk/expert_filter.py` | 286 |
| `risk/liquidity.py` | 59 |
| `risk/market_risk_gate.py` | 311 |
| `risk/risk_budget.py` | 22 |
| `risk/risk_engine.py` | 22 |
| `risk/var_calculator.py` | 191 |

### `router/`　（2 模块，约 108 行）

**职责**：数据 / 技能路由层。

<details><summary>包级说明与红线（点击展开）</summary>

```
数据 / 技能路由层。

- `provider_router`     —— 行情 / 基本面数据提供方路由
- `quant_skill_router`  —— 量化技能（因子 / 打分）路由

共同红线：
1. 路由失败必须降级到默认源，不得抛未捕获异常中断整条管道。
2. 不把某个提供方的私有口径当成全局事实；切换提供方不改变对外契约。
3. 与 `v3_data_bus` 分工：本包只做「选哪个源」，数据搬运在 bus 层。
```

</details>

| 模块 | 行数 |
|------|-----:|
| `router/provider_router.py` | 52 |
| `router/quant_skill_router.py` | 56 |

### `runtime/`　（2 模块，约 105 行）

**职责**：运行时环境与资源画像子包。

<details><summary>包级说明与红线（点击展开）</summary>

```
运行时环境与资源画像子包。

两个模块都由「拆巨石文件」而来，共同点是**刻意不依赖项目内其他模块**：
`runtime_env` 是为了让 `daily_stock_pick.py` 的拆分不产生循环导入，
`runtime_profile` 是为了能被 CLI 与研究脚本在导入任何重型模块之前就读到。
**新增依赖进入本包前请三思** —— 一旦本包开始依赖业务模块，上述两个目的都会失效。

模块一览：

* :mod:`runtime.runtime_env` —— 路径 / 日志 / 配置加载。
  运行时状态目录默认外置到 `~/.ai-stock-god/`（数据卫生设计，
  避免仓库工作区被运行产物污染），可用环境变量覆盖：
  `AI_STOCK_WATCHLIST_FILE`（股票池）、`AI_STOCK_STATE_DIR`（候选池/游标）、
  `AI_STOCK_LOG_DIR`（日志）。
* :mod:`runtime.runtime_profile` —— 8GB 机器的资源画像。
  系统的重头是远程 LLM 调用而非本地因子计算，因此这里只做两件事：
  限制并发、限制输出 token 上限。

红线：**配置的默认必须是安全的**。缺失配置时走保守分支并明确记录，
不得为了"让流程跑通"而回退到会静默改变行为（例如放开并发）的默认值。
```

</details>

| 模块 | 行数 |
|------|-----:|
| `runtime/runtime_env.py` | 56 |
| `runtime/runtime_profile.py` | 49 |

### `stage2/`　（3 模块，约 295 行）

**职责**：Stage-2 Alpha 重排 / 富集 / 消融实验。

<details><summary>包级说明与红线（点击展开）</summary>

```
Stage-2 Alpha 重排 / 富集 / 消融实验。

本包把「候选排序之后的二次加工」集中管理：
- `stage2_scoring`    —— 对 Stage-1 候选做确定性横截面二次排序
- `stage2_enrichment` —— 在候选上叠加资金流 / 龙虎榜 / 微观结构特征
- `stage2_ablation`   —— 逐层叠加实验，验证 Stage-2 是否提供独立增量信息

共同红线：
1. 纯历史模块，不依赖 `daily_stock_pick` 等运行时编排，避免把「已选股」当成输入。
2. 不引入未来函数：特征一律用 t 日及之前观测，收益只用 t+1 之后收盘价。
3. 不把工程实验结果包装成真实 Alpha：消融只说明「增量信息是否存在」。
```

</details>

| 模块 | 行数 |
|------|-----:|
| `stage2/stage2_ablation.py` | 179 |
| `stage2/stage2_enrichment.py` | 44 |
| `stage2/stage2_scoring.py` | 72 |

### `tdx/`　（3 模块，约 436 行）

**职责**：通达信（TDX）本地数据集适配子包。

<details><summary>包级说明与红线（点击展开）</summary>

```
通达信（TDX）本地数据集适配子包。

本包只负责「把 TDX 导出的原始文件读成研究可用的结构」，不引入网络依赖，
也不对数据缺口做业务推断。

共同红线：

* **原始价格保持不复权**。复权因子由 :mod:`corporate` 包显式给出，
  本包绝不自行调整 close/open。
* **观测 ≠ 事实**。缺失的行情 bar 只记录为「观测到的交易历史在此中断」，
  不推断为停牌、退市或公司行为（见 :mod:`tdx.tdx_lifecycle`）。

模块一览：

* :mod:`tdx.tdx_csv_adapter` —— 单文件全市场日线 CSV 的流式读取与字段规整。
* :mod:`tdx.tdx_inventory`   —— 数据集清单统计（行数 / 代码数 / 日期跨度），
  面向 9.8M 行级别的归档，避免整表入内存。
* :mod:`tdx.tdx_lifecycle`   —— 由原始日线派生「已观测生命周期」证据。
```

</details>

| 模块 | 行数 |
|------|-----:|
| `tdx/tdx_csv_adapter.py` | 332 |
| `tdx/tdx_inventory.py` | 22 |
| `tdx/tdx_lifecycle.py` | 82 |

### `tdx_native/`　（10 模块，约 1,375 行）

**职责**：tdx_native 测试包：把五因子研究接入通达信原生 `.day` 数据。

<details><summary>包级说明与红线（点击展开）</summary>

```
tdx_native 测试包：把五因子研究接入通达信原生 `.day` 数据。
```

</details>

| 模块 | 行数 |
|------|-----:|
| `tdx_native/adjust.py` | 81 |
| `tdx_native/backfill.py` | 247 |
| `tdx_native/daily_report.py` | 157 |
| `tdx_native/day_reader.py` | 178 |
| `tdx_native/fetch_names.py` | 120 |
| `tdx_native/five_factor.py` | 85 |
| `tdx_native/gbbq_reader.py` | 81 |
| `tdx_native/run_daily.py` | 168 |
| `tdx_native/screen.py` | 148 |
| `tdx_native/smoke_test.py` | 110 |

### `track/`　（4 模块，约 359 行）

**职责**：L3 回测闭环 · 实现层（由 tracking.py 拆分）。

<details><summary>包级说明与红线（点击展开）</summary>

```
L3 回测闭环 · 实现层（由 tracking.py 拆分）。

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
```

</details>

| 模块 | 行数 |
|------|-----:|
| `track/costs.py` | 81 |
| `track/schema.py` | 46 |
| `track/stats.py` | 163 |
| `track/store.py` | 69 |

### `tushare_client/`　（2 模块，约 121 行）

**职责**：TuShare 数据接入（可选依赖）。

<details><summary>包级说明与红线（点击展开）</summary>

```
TuShare 数据接入（可选依赖）。

- `tushare_provider`     —— TuShare 通用数据提供方（用 TUSHARE_TOKEN 环境变量）
- `tushare_ashare_events` —— A 股事件 / 公告数据接入

共同红线：
1. Token 仅经环境变量 `TUSHARE_TOKEN` 提供，绝不写入源码 / JSON / 日志。
2. 依赖缺失时降级（importorskip / 返回空），不阻断主流程。
3. 数据性质（是否已除权、是否覆盖退市）如实声明，不假装完整。
```

</details>

| 模块 | 行数 |
|------|-----:|
| `tushare_client/tushare_ashare_events.py` | 65 |
| `tushare_client/tushare_provider.py` | 56 |

### `validation/`　（9 模块，约 661 行）

**职责**：回测与策略结果的验证子包。

<details><summary>包级说明与红线（点击展开）</summary>

```
回测与策略结果的验证子包。

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
```

</details>

| 模块 | 行数 |
|------|-----:|
| `validation/benchmark.py` | 143 |
| `validation/health_monitor.py` | 17 |
| `validation/multiple_testing.py` | 380 |
| `validation/performance.py` | 16 |
| `validation/phase13_risk.py` | 14 |
| `validation/robustness.py` | 17 |
| `validation/strategy_validation.py` | 37 |
| `validation/stress_test.py` | 12 |
| `validation/validation_suite.py` | 25 |

## 根目录剩余模块

分类依据：`出边(根)`=该模块 import 的根目录其他模块数；`入边`=有多少**根目录**模块 import 它。
（`tests/` 与 `scripts/` 的引用不计入；行数为生成时刻快照。）

### 门面 / 入口 / 门禁工具

| 模块 | 行数 | 入边 | 出边(根) |
|------|-----:|-----:|--------:|
| `conftest.py` | 23 | 0 | 0 |
| `credential_scan.py` | 192 | 0 | 0 |
| `data_fetcher.py` | 101 | 8 | 0 |
| `main.py` | 158 | 0 | 1 |
| `paper_trading.py` | 16 | 0 | 0 |
| `run_ci.py` | 262 | 0 | 0 |
| `stock_god.py` | 71 | 0 | 0 |

### 高耦合核心（被多处依赖或依赖多处）

| 模块 | 行数 | 入边 | 出边(根) |
|------|-----:|-----:|--------:|
| `agents.py` | 105 | 3 | 4 |
| `agents_analysts.py` | 209 | 1 | 1 |
| `agents_base.py` | 89 | 4 | 1 |
| `agents_decision.py` | 153 | 1 | 1 |
| `agents_researchers.py` | 192 | 1 | 1 |
| `backtest_engine.py` | 116 | 3 | 2 |
| `cycle_price_action.py` | 63 | 2 | 0 |
| `daily_stock_pick.py` | 242 | 0 | 6 |
| `execution_rules.py` | 18 | 2 | 1 |
| `historical_universe.py` | 33 | 3 | 0 |
| `industry_context.py` | 50 | 1 | 2 |
| `market_regime.py` | 124 | 1 | 1 |
| `orchestrator.py` | 328 | 1 | 1 |
| `phase22_alpha_runner.py` | 15 | 0 | 2 |
| `phase41_data_workbench.py` | 123 | 0 | 2 |
| `pool_manager.py` | 166 | 1 | 1 |
| `portfolio_backtest.py` | 120 | 1 | 3 |
| `professional_committee.py` | 89 | 1 | 1 |
| `prompt_engine.py` | 187 | 0 | 3 |
| `real_alpha_pipeline.py` | 209 | 0 | 4 |
| `real_data_collector.py` | 115 | 0 | 1 |
| `release_gate.py` | 156 | 1 | 1 |
| `stock_scoring.py` | 173 | 2 | 2 |
| `v3_data_bus.py` | 65 | 0 | 3 |
| `walk_forward.py` | 98 | 1 | 3 |

### 零出边单例（不成族，刻意留根）

| 模块 | 行数 | 入边 | 出边(根) |
|------|-----:|-----:|--------:|
| `candidate_prefilter.py` | 40 | 1 | 0 |
| `crawl4ai_fetcher.py` | 370 | 0 | 0 |
| `daily_csv_adapter.py` | 74 | 0 | 0 |
| `data_contracts.py` | 91 | 1 | 0 |
| `data_quality.py` | 111 | 0 | 0 |
| `exchange_rules.py` | 127 | 1 | 0 |
| `industry_strength.py` | 44 | 1 | 0 |
| `lifecycle_event_evidence.py` | 77 | 0 | 0 |
| `llm_client.py` | 130 | 0 | 0 |
| `log_utils.py` | 55 | 0 | 0 |
| `market_universe_provider.py` | 29 | 0 | 0 |
| `phase15_governance.py` | 97 | 0 | 0 |
| `point_in_time.py` | 13 | 0 | 0 |
| `preregistered_alpha_experiment.py` | 25 | 1 | 0 |
| `professional_audit.py` | 73 | 1 | 0 |
| `public_daily_source.py` | 85 | 0 | 0 |
| `real_data_integrity.py` | 23 | 1 | 0 |
| `real_data_registry.py` | 53 | 1 | 0 |
| `recon_price_factor_lab.py` | 75 | 0 | 0 |
| `research_artifacts.py` | 93 | 0 | 0 |
| `research_integrity.py` | 24 | 0 | 0 |
| `screen_pipeline.py` | 155 | 0 | 0 |
| `streaming_topk.py` | 31 | 0 | 0 |
| `survivorship_guard.py` | 78 | 1 | 0 |
| `tracking.py` | 74 | 1 | 0 |

## 为什么这些留在根目录

1. **门面（`data_fetcher.py` / `agents.py`）**：实现已下沉到 `fetch/` 等包，
   门面保留是为让既有 `from X import ...` 全部不变。
2. **高耦合核心**：依赖边密集，强行入包只会把「根目录的耦合」搬成
   「跨包的耦合」，净收益为负（项目红线：划包先看依赖边，再看名字）。
3. **零出边单例**：彼此没有依赖边，按名字硬凑成包属于「名义分组」，
   会制造虚假内聚——与本项目『不许自欺』的原则相悖。
4. **`run_ci.py` / `credential_scan.py` / `conftest.py`**：门禁与 pytest 配置，
   文档与测试均按顶层路径引用，刻意留在根目录。
