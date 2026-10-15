# 工作交接文档

> **项目**：AI股神团队 1.0 · A股多 Agent 智能分析系统
> **仓库**：`https://github.com/LCD9Z/L.git`（**私有**）　**分支**：`main`
> **HEAD**：`7a3d005`（**写入本文件时的值；每次提交都会变，以 `git log` 实际为准**）
> **交接范围**：2026-09-13 ~ 2026-09-19 的工程改造、量化研究与 Alpha 能力缺口补齐
> **HEAD**：`dbb198a`（**写入本文件时的值；每次提交都会变，以 `git log` 实际为准**）
> **交接范围**：2026-09-13 ~ 2026-09-30（工程改造 + 量化研究 + TDX 原生数据/推荐系统）
> **配套阅读**：[`WORKLOG.md`](WORKLOG.md)（过程与证据）· [`CHANGELOG.md`](CHANGELOG.md)（版本演进）· [`DIRECTORY_LAYOUT.md`](DIRECTORY_LAYOUT.md)（结构全景，脚本生成）
> **本轮新增**：[`ALPHA_CAPABILITY_GAP_ANALYSIS.md`](ALPHA_CAPABILITY_GAP_ANALYSIS.md)（能力缺口分析）·
> [`P0_P1_EXECUTION_REPORT.md`](P0_P1_EXECUTION_REPORT.md)（P0/P1 落地执行报告）

---

## 本文件与「7 点交接要求」的对应

| # | 要求 | 本文件章节 |
|:--:|------|-----------|
| 1 | 项目目标、已完成/待完成功能、验收标准 | [一](#一项目目标与进度) |
| 2 | 源码仓库+分支、临时硬编码、TODO 备注 | [二](#二代码与仓库) |
| 3 | 环境版本、依赖包、数据库脚本、第三方接口 | [三](#三环境与依赖) |
| 4 | 架构/数据库/接口文档 | [四](#四架构与文档) |
| 5 | 测试脚本、已知 bug 与复现步骤 | [五](#五测试与已知缺陷) |
| 6 | 历史踩坑记录、高风险模块 | [六](#六踩坑记录与高风险模块) |
| 7 | 剩余任务与预估工时 | [七](#七剩余任务与预估工时) |

---

## 一、项目目标与进度

### 1.1 项目目标

构建 A 股多 Agent 智能分析/选股系统，并在**真实数据**上诚实地判定
「是否存在可实现的 Alpha」——**不接受把工程实验或样本内结果包装成投资结论**。

### 1.2 已完成功能

| 类别 | 内容 | 状态 |
|------|------|:---:|
| 工程结构 | 188 个平铺 `.py` → **19 子包 / 67 入包模块 / 根目录 56** | ✅ |
| 巨石拆分 | `data_fetcher.py`(807) / `tracking.py`(308) / `main.py`(402) → 门面模式 | ✅ |
| 质量门禁 | ruff 零告警 · mypy 237 文件零错误 · pytest 538 项 · 本地 CI 6/6 | ✅ |
| 数据接入 | 通达信日线 → 认证数据集（清洗 + sha256 + PIT 股票池） | ✅ |
| 数据修正 | **幸存者偏差**（180 只窗口内退市股并入）· **不复权价**（分红送股复权因子） | ✅ |
| 因子研究 | 横截面 IC 检验引擎、9 个经济假设检验、多窗口滚动样本外 | ✅ |
| 组合研究 | 采样敏感性、持仓分散度、尾部剔除、多股票池重复验证 | ✅ |
| 假设检验 | 复合反转 H-C1（事前登记 → IC 强支持 → 组合层面 → 基准对照） | ✅ |
| 外部集成 | 飞书 notify 真实凭据验收通过 | ✅ |
| **基准校正** | **等权全A第二基准**（`validation/benchmark.equal_weight_returns`）—— 纠正"全市场策略只对标沪深300"的错配 | ✅ |
| **多重检验校正** | `validation/multiple_testing.py`：DSR / BH-FDR / Bonferroni / MinTRL / FWER | ✅ |
| **因子正交化** | `factors/factor_ic_lab.orthogonalize_panel`：顺序残差化 + Löwdin | ✅ |
| **涨跌停口径** | `exchange_rules.derive_limit_ratio`：**时变**（主板 ST 2026-07-06 前 ±5% / 之后 ±10%） | ✅ |
| **PIT 财务数据** | `fetch/fundamentals_source` + `pit/pit_fundamentals`：按公告日索引，打开 `pb`/`roe`/`pe_ttm`/`net_profit_growth` 等因子 | ✅ |
| **数据集增量更新** | `scripts/update_certified_dataset.py`：**重叠日校验**（前复权序列不可盲目追加） | ✅ |
| **基本面因子检验** | `scripts/run_fundamental_factor_study.py`：**`pb`(t=−7.42) 与 `pe_ttm`(t=−4.19) 通过 BH+Bonferroni 双校正**；质量/成长 4 因子不显著 | ✅ |
| **控制市值残差检验** | 同上 `--control log_amount_20`：**`pb` 溢价独立于市值（保留 88%）**；控制后 `net_profit_growth`/`ocf_per_share` 变为显著；合并族 m=14 校正后 **4/7 存活** | ✅ |
| **全池等权基准** | `scripts/build_equal_weight_benchmark.py`（流式，内存 O(交易日数)）：分母均值 **937.8 → 5,187 只**，覆盖率 **18.1% → 约 96%** | ✅ |
| **全A股票池** | `D:/tdx_dataset_v3`：入选 **5,667 只**，池规模 2,542~5,428，在市覆盖 22.7% → **约 97.6%** | ✅ |
| **TDX 原生数据** | `tdx_native/`：`.day` 二进制直读、`gbbq` 3DES 解密→权息缓存、前复权（零第三方主路径） | ✅ |
| **全市场复检** | 5,613 只 / 632,968 样本 / 245 个不重叠截面（2021-08~2026-09）；五因子 IC 稳健性成立 | ✅ |
| **执行层改善** | C20 + 持有 20 日 + V2 跳空过滤（**唯二经组合层验证有效的参数**） | ✅ |
| **推荐系统产品化** | `tdx_native/`：日度推荐 + 名称表 + L3 跟踪回填 + 一键运行 + 自选股导出 | ✅ |
| **质量门禁** | ruff 0 · mypy 265 文件 0 错 · pytest **620 项** · 本地 CI 6/6 | ✅ |

### 1.3 待完成功能

| 项 | 说明 |
|----|------|
| **在 v3 上重跑全部关键检验** | v3 构建完成后（6 窗口双基准滚动 + 五因子 IC + 正交化对照 + C20 尾部剔除）。**在 v3 结论出来前不应基于 v2 旧数字做新的策略判断** |
| **新的经济逻辑假设** | 现有 7 因子上已判定无 Alpha；需**新假设**（禁止调权重/阈值）。P1-6 已打开基本面维度，是新假设的主要来源 |
| ~~P1-7 PIT 行业分类~~ | ⛔ **已决策放弃（2026-09-22）** —— 不采购付费源、不自建统计代理。**代价：`pb`/`pe_ttm` 的价值溢价未做行业中性化**，该残留风险已记录在案 |
| ~~P1-8 指数成分历史~~ | ⛔ **已决策放弃（2026-09-22）** —— 免费源只给当前成分快照。基准改用**自建等权全A**（已实现） |
| P1-9 数据集增量更新管线 | 当前为固定快照（锚定 2026-09-11），不可增量 |
| 策略层面实验补记 p 值 | 12 项实验归档的是判定而非 p 值 → 无法纳入多重检验校正 |
| ARK 付费模型凭据验收 | 需用户提供凭据 |
| `disallow_untyped_defs` 收紧 | 569 处纯标注告警，收益递减，暂缓 |
| 无直接测试覆盖模块补测 | 见 [6.2](#62-高风险模块)（`tdx_native` 已于 2026-09-30 补齐） |
| L3 跟踪样本积累 | `tracking.csv` 需随每日运行积累到期样本，才能校准推荐质量 |
| 北交所数据接入 | pytdx `get_security_list` 的 market=2 在 20 台服务器均不可用（已知局限） |

### 1.4 验收标准

**工程验收**（一条命令）：

```bash
cd C:/Users/T430/Desktop/1.0 && python run_ci.py     # 期望 6/6 PASS
```

| 检查 | 通过标准 |
|------|---------|
| syntax | 全部 `.py` 可编译（含 BOM/编码检查） |
| ruff | `All checks passed` |
| mypy | `no issues found in 265 source files` |
| compat | Python 3.10 语法兼容 |
| pytest | 失败 0、错误 0（跳过 ≤1）；当前 **620 项** |
| credentials | 无明文凭据 |

**研究验收**（事前登记门槛，不可事后放宽）：

| 指标 | 门槛 |
|------|------|
| IC 显著性 | 全样本 t > 2 **且** 两个子窗口同号 |
| 组合超额 | 两窗口均 > 0 **且** 均 > 2pp（相对**基准指数**，非仅相对基线） |
| 成本 | 必须用生产级 `dynamic_slippage`，不得用固定滑点 |
| 采样 | 结论须附**采样敏感性区间**，不得用单一采样数 |

> **当前结论**：`ALPHA_NOT_ESTABLISHED` —— 基线在全部实验条件下均为负超额；
> 复合反转 H-C1 对照沪深 300 后超额仅 +0.48pp / −4.88pp（≈ 指数水平）。
>
> **2026-09-30 追加（TDX 原生全市场复检）**：结论未改变，但边界更清晰 ——
> ① 五因子 IC 在 5,613 只 / 632,968 样本上**稳健成立**（maxret20 −0.0787/t−7.78 等），
> 但 IC 层成立 ≠ 组合层可获利；② **IC 随前瞻期单调增强**（1 日 +0.051 → 60 日 +0.130），
> 属持久型截面特征而非短周期择时信号；③ 唯二经组合层验证有效的改善是
> **持有 20 日**与 **V2 跳空过滤**（5/5 窗口改善、Δ中位 +3.12pp）；
> ④ H-F4（剔除 amihud20）IC 层与组合层**双双不通过** —— 又一次「IC 更高但组合更差」。

---

## 二、代码与仓库

### 2.1 仓库与分支

| 项 | 值 |
|----|-----|
| 仓库 | `https://github.com/LCD9Z/L.git`（私有） |
| 分支 | `main` |
| 本地路径 | `C:\Users\T430\Desktop\1.0`（**唯一开发目录**） |
| 只读基线 | `C:\Users\T430\Desktop\4.3`、`C:\Users\T430\Desktop\v3.4_work`（**禁止修改**） |
| 派生数据 | `D:\tdx_dataset`（约 200MB，刻意不放在源码目录） |
| ⚠️ 推送 | 远端 tracking 已失效（`upstream is gone`）；推送需 `git_auth_run.py --no-proxy`，见 [6.1](#61-踩坑清单) 第 9 条 |

### 2.2 临时硬编码清单

> 以下为**已知**的硬编码，均属「研究脚本的默认值」而非生产路径参数。
> 改动前请确认不影响已发布结论的可复现性。

| 位置 | 硬编码内容 | 性质 |
|------|-----------|------|
| `scripts/run_contrarian_portfolio.py:46,54` | `HORIZON = 5`；`WINDOWS = [("2024-01-02","2026-09-30"), ("2025-01-02","2026-09-30")]` | **模块级常量，非 CLI 参数** —— 改窗口必须改源码 |
| `scripts/run_concentration_study.py:92` | `--windows` 默认 `"2024-01-02"`（单窗口） | 默认值 |
| `scripts/run_tail_exclusion_study.py:48` | `DEFAULT_WINDOWS` 五个窗口 | 默认值 |
| `scripts/run_tdx_rolling_eval.py:37` | 滚动起点列表（2023-01 起） | 默认值 |
| 各研究脚本 | `threshold=70`、`horizon=5`、`step=5`、`top_n=5~20`、`seed_base=1000` | 默认值 |
| `factors/factor_ic_lab.py:69-71` | `MIN_HISTORY=25`、`DEFAULT_HORIZON=5`、`DEFAULT_STEP=5` | 契约常量 |
| `factors/factor_ic_lab.py:62` | `PRIOR_SIGN`（各因子先验方向） | **契约常量，改动会翻转策略方向** |
| `lifecycle_event_evidence.py:24` | `VERIFIED_2026_DELISTINGS`（人工核验的退市清单） | 数据快照 |
| `market_regime.py:5` | `BENCHMARKS` | 契约常量 |
| `exchange_rules.py:31-34` | `ST_LIMIT_CHANGE_DATE="2026-07-06"`、`ST_LIMIT_RATIO_BEFORE=0.05`、`ST_LIMIT_RATIO_AFTER=0.10` | **规则常量，改动会翻转涨跌停判定**。出处：沪深北交易所 2026-07-06 同步施行的交易规则修订 |
| `factors/factor_ic_lab.py:COMPOSITE_FACTORS / ORTHO_ORDER_DEFAULT` | 复合五因子集合与**顺序残差化的事前声明顺序** | **契约常量**：改顺序会改变正交化结果，且**不得按 IC 结果调整**（等于用结果选参数） |
| `notify/feishu_notifier.py:14` | `WORK_DIR = dirname(__file__)` | **`__file__` 派生路径** —— 改动风险高，见 [6.2](#62-高风险模块) |
| `track/schema.py:13` | `_DB_PATH` 取两层父目录 | 同上，已有守卫 `test_db_path_stays_at_project_root` |
| `tdx_native/five_factor.py:23` | `DIRECTIONS`（五因子先验方向）、`LIQ_MIN=1e8` | **契约常量，改动会翻转策略方向**（与 `factors/factor_ic_lab.py:62` 同性质） |
| `tdx_native/backfill.py:31` | `INDEX_CODE = "sh000001"` | 交易日历来源（与全市场 IC 研究同源，改则口径不一致） |
| `tdx_native/backfill.py:113` | 建仓停牌顺延上限 **5 个交易日**（`min(i + 6, len(cal))`） | 模块内常量，非 CLI 参数 |
| `tdx_native/daily_report.py:30,38` | V2 跳空阈值 `limit_pct - 0.002`、流动性标签线 `2e8` | 研究默认值 |

### 2.3 TODO / FIXME 备注

**当前代码库中 `TODO` / `FIXME` / `XXX` / `HACK` 标记数 = 0**（已扫描，无遗留标记）。

未完成事项统一记录在本文件第七节与 `WORKLOG.md` 遗留事项，**不散落在代码注释里**。

---

## 三、环境与依赖

### 3.1 运行时

| 用途 | 路径 / 版本 |
|------|------------|
| 运行 / pytest | `C:\Users\T430\AppData\Local\Programs\Python\Python313\python.exe` |
| **ruff / mypy（隔离 venv，系统 Python 内没有）** | `C:\Users\T430\.workbuddy\binaries\python\envs\default\Scripts\` |
| Python 版本下限 | **3.10**（由 `tests/test_python_compat.py` 在 CI 中守卫） |
| CI 覆盖 | py3.10 ~ 3.13（`.github/workflows/ci.yml`） |
| 行尾约定 | **全部 LF**（有守卫测试） |

### 3.2 依赖包

**核心数据管道（`data_fetcher` / `tracking` / `screen_pipeline` / `ashare/*` /
`factors/*` / `pit/*` 等）纯标准库实现，零第三方依赖。**

`requirements.txt`（均为**可选**，按需安装）：

| 包 | 版本 | 启用方式 | 用途 |
|----|------|---------|------|
| `crawl4ai` | >=0.7.0 | `CRAWL4AI_ENABLED=1` | 新闻正文抓取清洗 |
| `beautifulsoup4` | >=4.12 | 同上 | 同上 |
| `tushare` | >=1.4.0（已注释） | `TUSHARE_TOKEN=<token>` | 资金流/龙虎榜/公告等 |
| `pandas` | >=1.5（已注释） | 随 tushare | tushare_provider 测试依赖 |
| `pytdx` | 未固定 | 仅 `tdx_native` 的两条**离线**路径 | `fetch_names`（名称表）、`gbbq_reader.build_cache`（权息解密） |

> **`tdx_native` 的主路径刻意零依赖**：`gbbq` 解密一次后落 `data/gbbq_events.csv`，
> 之后用标准库读缓存；`.day` 读取全部用 `struct`。`pytdx` 缺失不影响 CI
> （`mypy.ini` 已配 `[mypy-pytdx.*] ignore_missing_imports`）。

`requirements-dev.txt`：`pytest>=7.0` · `pytest-cov>=4.0` · `ruff>=0.6` · `mypy>=1.10`

### 3.3 数据库

| 项 | 内容 |
|----|------|
| 引擎 | SQLite（标准库 `sqlite3`） |
| 文件 | `tracking.db`（**项目根目录**，已 gitignore） |
| Schema 位置 | `track/store.py` + `track/schema.py`（`CREATE TABLE IF NOT EXISTS recommendations`） |
| **迁移脚本** | **无** —— 用 `CREATE TABLE IF NOT EXISTS` 隐式建表，无版本化迁移 |
| 风险 | `_DB_PATH` 由 `__file__` 派生；曾因包拆分静默迁址导致「旧记录消失且不报错」，现由 `test_db_path_stays_at_project_root` 守卫 |

> 数据集（`D:/tdx_dataset`）为 CSV + JSON 文件形式，非数据库：
> `stocks/{code}.csv`、`{code}.metadata.json`（含 sha256）、`pit_universe.json`、`benchmark.csv`。

### 3.4 第三方接口

| 提供方 | 端点 | 用途 | 凭据 |
|--------|------|------|:---:|
| 东方财富 | `datacenter-web.eastmoney.com` | 分红送股（`RPT_SHAREBONUS_DET`） | 无 |
| 东方财富 | `push2his.eastmoney.com` · `quote.eastmoney.com` | 日K / 实时行情 | 无 |
| 东方财富 | `search-api-web.eastmoney.com` · `data.eastmoney.com` | 新闻检索 | 无 |
| 腾讯 | `web.ifzq.gtimg.cn` | 日K（**需 `qfq` 后缀，`count` ≤ 640**） | 无 |
| 腾讯 | `qt.gtimg.cn` | 批量行情（可识别退市股） | 无 |
| 新浪 | `money.finance.sina.com.cn` · `finance.sina.com.cn` | 日K 备用源 | 无 |
| 飞书 | `my.feishu.cn` | 通知推送（`lark-cli`） | **需授权** |
| ARK（付费模型） | 见 `llm_config.json` | LLM 分析 | **待验收** |
| TuShare | 见 `tushare_provider` | 补充数据 | 需 `TUSHARE_TOKEN` |

> ⚠️ **限流事实**（实测）：`push2his.eastmoney.com` 全镜像 `RemoteDisconnected`；
> 腾讯 K 线并发 6 后封禁（HTTP 501）；新浪连续 ~72 请求后封禁（HTTP 456）。
> 取数脚本必须设 `--delay ≥1.5`、并发 ≤2，并**区分「数据源拒绝」与「无数据」**
> （否则会输出「窗口内退市 0 只」这类假结论 —— 已实际发生）。

---

## 四、架构与文档

### 4.1 架构总览

```
项目根/
├── *.py          56 个：入口 / 门面 / 核心编排 / 门禁工具 / 未成族单例
├── <20 子包>/     每个都有 __init__.py（写「管什么 + 共同红线」）
├── scripts/       39 个可执行脚本（研究 / 数据准备 / 验收）
├── tests/         71 个测试文件
└── conftest.py    把项目根 + scripts/ 加入 sys.path

> 结构指纹（由 `gen_layout_doc.structural_fingerprint()` 给出，`test_layout_doc_in_sync.py` 守卫）：
> **20 个子包 / 80 个入包模块 / 56 个根目录模块**。
> 子包：`alpha ashare console corporate factors fetch notify phase62 pit regime
> reporting risk router runtime stage2 tdx tdx_native track tushare_client validation`。
```

**分层原则**：用 AST 建全仓库 import 图，统计每个家族的**外部入/出边**，
按耦合从低到高下沉。**划包先看依赖边，再看名字** —— 只选「内部闭合」的家族。

**导入约定**：子包内同族引用用**相对导入**；包外一律**绝对导入**。
门面包（`fetch/` `track/` `console/`）**不要直接依赖**。

### 4.2 关键设计文档

| 文档 | 内容 |
|------|------|
| [`DIRECTORY_LAYOUT.md`](DIRECTORY_LAYOUT.md) | **目录全景**（由 `scripts/gen_layout_doc.py` 自动生成，含各包红线与留根理由） |
| [`CHANGELOG.md`](CHANGELOG.md) | 版本演进（PHASE1~43 归档、v4.9 移植、历次收紧） |
| [`AUDIT_REPORT.md`](AUDIT_REPORT.md) | 多角度静态分析审计与风险项 |
| [`MERGE_1.0_REPORT.md`](MERGE_1.0_REPORT.md) | 1.0 合并报告（4.3 + v3.4_work）与遗留清单 |
| 各子包 `__init__.py` | **每个包的职责与共同红线**（最权威、最贴近代码） |

> **数据库设计文档**：无独立文档 —— schema 即 `track/schema.py`（单表 `recommendations`），
> 规模小到不值得单独成文。
> **接口文档**：本项目无对外 HTTP 服务（无 REST/gRPC 接口），
> 「接口」即各模块的公开函数；契约由 `tests/` 与各 `__init__.py` 红线共同表达。

### 4.3 研究文档索引

| 文档 | 结论 |
|------|------|
| [`ALPHA_CAPABILITY_GAP_ANALYSIS.md`](ALPHA_CAPABILITY_GAP_ANALYSIS.md) | **能力缺口分析**：六环框架（数据→假设→信号→组合→验证→运行），成熟度 数据 L2 / 假设 L1 / 信号 L2 / 组合 L1 / **验证 L3** / 运行 L1；含两项实测（基准错配、因子冗余）与 P0~P3 补足路线 |
| [`P0_P1_EXECUTION_REPORT.md`](P0_P1_EXECUTION_REPORT.md) | **P0/P1 落地执行报告**：4 项 P0 全部完成、P1 前 2 项完成、2 项受阻（附核查证据）；含 4 个额外缺陷 |
| [`AB_STUDIES_EVIDENCE.md`](AB_STUDIES_EVIDENCE.md) | **A/B 与 H-C1 原始结果归档说明**（含口径提醒） |
| [`PORTFOLIO_AB_REPORT_3.md`](PORTFOLIO_AB_REPORT_3.md) | 第三阶段：反转 ≈ 指数，无可靠正超额 |
| [`PORTFOLIO_AB_REPORT_2.md`](PORTFOLIO_AB_REPORT_2.md) | 第二阶段：优势稳健但被成本侵蚀 |
| [`PORTFOLIO_AB_REPORT.md`](PORTFOLIO_AB_REPORT.md) | 第一阶段结果与两个推翻性隐患 |
| [`CONTRARIAN_HYPOTHESIS_REPORT.md`](CONTRARIAN_HYPOTHESIS_REPORT.md) | H-C1 检验结果与五条限定 |
| [`ALPHA_HYPOTHESIS_PREREG.md`](ALPHA_HYPOTHESIS_PREREG.md) | H-C1 事前登记（假设/方向/判定标准固定） |
| [`SAMPLING_SENSITIVITY_REPORT.md`](SAMPLING_SENSITIVITY_REPORT.md) | 采样敏感性：分散化降标准差 4.2 倍但不改结论 |
| [`CALIBRATION_DISCREPANCY_REPORT.md`](CALIBRATION_DISCREPANCY_REPORT.md) | 口径排查与**算术/几何年化**分野 |
| [`RERUN_CORRECTED_REPORT.md`](RERUN_CORRECTED_REPORT.md) | 修正数据集后四项研究重跑 |
| [`SURVIVORSHIP_IMPACT_REPORT.md`](SURVIVORSHIP_IMPACT_REPORT.md) | 幸存者偏差影响是不复权价的 30 倍 |
| [`DELISTED_UNIVERSE_REPORT.md`](DELISTED_UNIVERSE_REPORT.md) | 180 只窗口内退市股识别与并入 |
| [`ADJUSTED_FACTOR_REPORT.md`](ADJUSTED_FACTOR_REPORT.md) | 复权因子对比（预测未获支持） |
| `TDX_DATA_ASSESSMENT.md` / `TDX_EVALUATION_REPORT.md` | 数据性质评估与首次端到端实证 |
| [`tdx_native/README.md`](tdx_native/README.md) | **TDX 原生模块用法与格式备忘**（`.day` 32B `<IIIIIfII`、gbbq 3DES、复权验证法）与结论 |
| [`FACTOR_SUBSET_PREREG.md`](FACTOR_SUBSET_PREREG.md) | H-F4 因子子集事前登记（结果：不支持剔除 amihud20） |
| [`IC_DECAY_PREREG.md`](IC_DECAY_PREREG.md) | H-DECAY 前瞻期衰减登记（结果：IC 单调增强，非衰减） |
| [`IMPACT_COST_PREREG.md`](IMPACT_COST_PREREG.md) · [`TURNOVER_CAPACITY_PREREG.md`](TURNOVER_CAPACITY_PREREG.md) | 冲击成本 / 容量登记 |
| `reports/tdx_ic_full.json` · `reports/tdx_ic_800.json` | 全市场 vs 800 只抽样的 IC 对照（样本稳健性证据） |
| `reports/decay_h1.json` · `decay_h60.json` · **`decay_h5_ic.json`** · **`decay_h10_ic.json`** · **`decay_h20_ic.json`** | **五因子合成 IC 衰减**（主干口径：通达信 `D:/new_tdx/vipdoc`、**1500 只**；10 键，含 `composite_ic` 的 S5_all / S4 / S3 / S2 分解） |
| `reports/decay_h5.json` · `decay_h10.json` · `decay_h20.json` · `decay_h40.json` | **分组 / 子周期衰减**（副本口径：`D:/tdx_dataset_v3`、**400 只**；4 键 `full/quintiles/subperiods/args`） |

> ⚠️ **上两行是两组不同的实验，不可混用或交叉引用**（2026-10-15 拆分）。
> A2 合并（`86956c8`）曾把 `decay_h5/h10/h20` 判为「同型」并取副本版，
> 使同族产物出现两种结构（`h1`/`h60` 为 10 键、`h5`/`h10`/`h20` 为 4 键），
> 而本表原按「IC 衰减曲线原始结果」**一并登记** → 登记与产物不符。
> 现按方案「改名保留两份」拆分：主干那份改名为 `*_ic.json` 恢复入库，
> 副本那份保留原名。**引用任一份前先查它的 `source` 与键结构。**
| `reports/f4_p1~p3.json` · `reports/v2_p1~p3.json` | H-F4 / H-V2 组合层结果 |

---

## 五、测试与已知缺陷

### 5.1 测试脚本

`tests/` 共 **70+ 个测试文件**（2026-09-19 新增 7 个：等权基准 / 多重检验 /
正交化 / 因子IC重构锁定 / 涨跌幅规则 / PIT财务 / 财务数据源，共 **176 项**）。
除常规单测外，**8 个为守卫测试**（防止已修缺陷回退）：
`tests/` 共 **71 个测试文件 / 620 项**。除常规单测外，**9 个为守卫测试**
（防止已修缺陷回退）：

| 守卫测试 | 守住什么 |
|---------|---------|
| `test_package_layout.py` | 包结构不回退：无平铺副本、无裸包名导入、包内相对导入、数据脚本不得散落根目录 |
| `test_python_compat.py` | Python 3.10 兼容；mypy `exclude` 不误伤真实源文件 |
| `test_layout_doc_in_sync.py` | `DIRECTORY_LAYOUT.md` 与仓库结构一致（含反向守卫） |
| `test_annualization_conventions.py` | 年化口径单一来源；禁止重新内联；算术≠几何 |
| `test_study_regressions.py` | 等距抽样塌缩、成本拖累窗口硬编码、滑点模型未记录（**含缺陷复现**） |
| `test_orchestrator.py` | 会话存/读往返完整；序列化键集合 == `AnalysisResult` 字段契约（拦整类「save 写的字段 load 读不了」） |
| **`test_tdx_native.py`** | **`tdx_native` 40 项**：`.day` 二进制往返、板块/涨跌停判定、前复权消除除权缺口、回填 T+1/T+5/T+20 口径与停牌三态、gbbq 解析、五因子方向语义 |
| `test_survivorship_guard.py` | 幸存者偏差门禁 |
| `test_credential_scan.py` | 凭据扫描器自身正确性 |

> ⚠️ **收集陷阱（本轮踩到）**：`tdx_native/smoke_test.py` 虽然函数名以 `test_` 开头，
> 但**位于包内而非 `tests/`**，pytest 默认只收集 `tests/test_*.py` —— 该模块因此
> 长期零门禁覆盖。**新增自测必须落到 `tests/`**。

> 其余：`test_db_path_stays_at_project_root`（在 `test_package_layout.py` 内）、
> `test_main_smoke.py`（15 项，入口冒烟，不触发 LLM/网络）。

### 5.2 验收清单（接手后先跑一遍）

```bash
cd C:/Users/T430/Desktop/1.0

# ① 一条命令覆盖全部（推荐）
python run_ci.py                    # 期望 6/6 PASS

# ② 单独执行
C:\Users\T430\.workbuddy\binaries\python\envs\default\Scripts\ruff.exe check .
C:\Users\T430\.workbuddy\binaries\python\envs\default\Scripts\mypy.exe --config-file mypy.ini .
python -m pytest -q
python credential_scan.py

# ③ 结构守卫
python -m pytest tests/test_package_layout.py tests/test_layout_doc_in_sync.py -q
python scripts/gen_layout_doc.py --check
```

> `run_ci.py` 已改为**以 JUnit 报告判定 pytest**（不再信任退出码）——
> 本机 `safe-delete` 钩子会污染退出码，此前导致 CI 假失败。

### 5.3 已知缺陷与复现步骤

| # | 缺陷 | 状态 | 复现步骤 |
|:--:|------|:---:|---------|
| 1 | ~~`tdx_ab_stage2_summary.json` 的 verdict 与一阶段完全相同~~ | **已修（2026-09-16）** | 根因是脚本 `params` **未记录 `slip_mode`**、结论文案也不含滑点模型。已修 `scripts/run_contrarian_portfolio.py`（params 加 `slip_mode` + 结论加 `[滑点=…]` 前缀 + 抽出 `_result_payload()` + 守卫测试）。**已归档的 4 个 JSON 保持原样**（历史证据不可改写） |
| 2 | 研究脚本**绝对数字不可引用** —— 策略对采样数极度敏感 | 已记录，未根治 | 同窗口 `2023-07-03`：`--max-stocks 400` → V0 −83.06%；`800` → −28.34%（差 54.72pp） |
| 3 | ~~`orchestrator.py`（337 行）无直接测试引用~~ | **已修（2026-09-16）** | 补 `tests/test_orchestrator.py`（21 项）后**立刻发现严重缺陷**：`load_session()` 必然抛 `TypeError`（`save_session` 漏写必填字段 `analysis_type`）→ 会话恢复功能完全不可用。已修 + 加通用守卫 `test_serialized_keys_are_accepted_by_analysis_result` |
| 4 | 10 个根目录模块无直接测试引用 | 未修 | 见 [6.2](#62-高风险模块) |
| 5 | `disallow_untyped_defs` 未开启（569 处纯标注告警） | 刻意暂缓 | `mypy.ini` 中该项为 `False` |
| 6 | ~~北交所 `920xxx` 代码段被 `board_of` 误判为「其他A股」~~ | **已修（2026-09-19）** | 后果：涨跌幅按 10% 而非 **30%**。数据集含 `920000` 安徽凤凰，故为**在线缺陷**。发现方式：新写的 `tests/test_exchange_rules.py` 直接失败。已加 `920` 前缀判定 |
| 7 | ~~`load_certified_csv` 丢弃 `is_st`~~ | **已修（2026-09-19）** | 后果：P0-4 的涨跌停派生规则**无法生效**（回测路径拿不到 ST 状态）。已改为逐日状态字段透传（`is_st`/`limit_ratio`/`limit_pct`） |
| 8 | ~~`build_certified_dataset_v2.py` 引用未定义名 `prev_day`~~ | **已修（2026-09-19）** | 停牌区间推导中 `prev_day` 仅在循环体内赋值，循环后仍被引用。当前路径"恰好安全"但静态上不可保证。已循环外初始化。发现方式：`ruff` F821 |
| 9 | ~~`_rows_iter` 闭包未绑定循环变量 `code`~~ | **已修（2026-09-19）** | 发现方式：`ruff` B023。已加 `code=code` 默认参数绑定 |
| 10 | ~~财务数据源公告日 88.4% 不可信~~ | **已兜底（2026-09-19）** | 东财 `最新公告日期` 在 2016-01~2025-06 **全部期数**上系统性偏移 **+1 年**（茅台 2016Q1 EPS 3.89 确为 2016Q1，却标注 2017-04-25）；仅最近约 4 期正确。**财务数值本身正确，只有公告日错**。已由 `pit.pit_fundamentals.resolve_availability` 兜底：公告日超法定截止日 45 天即判不可信 → 退回法定披露截止日。**残留风险**：真实延迟披露且超窗口者会略早可用（2025-09 后各期 1.6%~4.2%）。彻底解决需改用带真实披露日的源 |
| 11 | `pool_manager._extract_stage`：逻辑串含「周期阶段：」但**其后无括号**时，返回值**丢失最后一个字符** | 待修（2026-10-15 由新增单测暴露） | `pool_manager.py:36-41`：两个 `find` 都未命中时 `j` 为 **-1**，而 `logic[i+len(mark):j]` 用负数切片 ⇒ 末字符被静默切掉。复现：`python -c "import pool_manager as p; print(repr(p._extract_stage('周期阶段：楔形下跌 量能萎缩')))"` → `'楔形下跌 量能萎'`（期望 `'楔形下跌 量能萎缩'`）。**影响面**：仅该形态触发；实测 `~/.ai-stock-god/watchlist.json` 与 `candidate_pool.json` **当前均不存在** ⇒ 生产中暂不可触发。已用 `tests/test_pool_manager.py::test_extract_stage_without_paren_drops_last_char` 锁定现状（修好后该测试会变红，须先评估影响面） |
| 12 | `v3_data_bus.build_v3_bundle`：fact sheet 的 `meta` 为 **`None`** 时（上游给出 `{"meta": null}`）**直接抛 `AttributeError`** | 待修（2026-10-15 由新增单测暴露） | 根因：`dict.get(k, {})` 的默认值**只在键缺失时生效**，键存在但值为 `None` 时不兜底 ⇒ `None.get(...)` 崩。`v3_data_bus.py` 共 **4 处**同形态：L22 / L58 / L59（两处）。复现：`python -m pytest tests/test_v3_data_bus.py::test_meta_none_crashes -q`。**影响面**：上游 `build_fact_sheet` 当前构造的 `meta` 恒为 dict ⇒ 生产中暂不触发；已用该测试锁定现状（修好后测试须改为「不抛异常」） |
| 13 | `fact_sheet` 的 meta 字段**不防缺键/`None`**：两处独立崩溃点 （`fetch/news.py:182` 硬索引 `sheet["meta"]`；`professional_committee.py:71` `meta.get(...)`，而同函数的 `q`/`news`/`kline` 都有 `or {}`/`or []` 防护，**唯独 meta 漏了**） | 待修（2026-10-15 由新增单测暴露） | 复现①缺键：`python -m pytest tests/test_professional_committee.py::test_missing_meta_key_raises_in_pack_data -q`；②None：`...::test_meta_none_fails_in_deterministic_checks -q`；另 `fetch/news.py:234` kline 行缺 `open` 亦 KeyError。影响面：上游 `build_fact_sheet` 恒带 meta 与完整 kline 行 ⇒ 生产中暂不触发；三个崩点已全部用 characterization 测试锁定 |


| 6 | ~~`dbb198a` 之前门禁为红：ruff 51 项 / mypy 57 项 / pytest 2 项~~ | **已修（2026-09-30）** | 根因是 `tdx_native` 产品化提交（`d7625ff`）**未过门禁即入库**，使 `run_ci.py` 失去「一条命令验证状态」的作用。已全部清零并补 40 项守卫测试。**教训：提交前必须跑 `run_ci.py`** |
| 7 | ~~`DIRECTORY_LAYOUT.md` 缺 `tdx_native` 子包~~ | **已修（2026-09-30）** | 新增子包后未重跑 `scripts/gen_layout_doc.py`；`test_layout_doc_in_sync.py` 已捕获。**新增/删除子包后必须重跑生成器** |
| 8 | ~~`reports/daily_screen_2026-09-19.json` 含 CRLF 行尾~~ | **已修（2026-09-30）** | 该旧产物由 Windows 文本模式写出；已转 LF。**注意：`test_line_endings_are_lf` 扫描工作区全部文本文件（不看 git 跟踪状态），未跟踪的产物同样会被扫到** |

> **已修复**的历史缺陷（含复现路径）见 `WORKLOG.md` 第六节与
> `tests/test_study_regressions.py`、`tests/test_annualization_conventions.py`。

---

## 六、踩坑记录与高风险模块

### 6.1 踩坑清单

1. **包名绝不能与第三方/标准库顶层模块同名**
   曾建 `tushare/` 包 → `import tushare as ts; ts.pro_api()` 命中自己的空包 → 运行期 `AttributeError`。
   pytest 抓不到（惰性导入），靠 mypy + 守卫 `test_no_bare_import_of_package_names`。
   同理，`crawl4ai_fetcher` 若拆包**不能叫 `crawl4ai/`**。

2. **monkeypatch 必须打在「名字被查找的那个模块」上**
   门面只保证 `from data_fetcher import X` / `data_fetcher.X` 可达，**不能**让补丁穿透到子模块内部。
   `test_crawl4ai_adapter` 的补丁已从 `data_fetcher` 改指 `fetch.news`。

3. **拆分前先全局搜 `__file__` / 相对路径派生的资源**
   `tracking._DB_PATH` 曾会静默迁到 `<root>/track/tracking.db`（旧记录"消失"且不报错）。
   已加守卫 `test_db_path_stays_at_project_root`。

4. **字符串动态引用是重命名的隐形地雷**
   `open("x.py")`、`import_module("x")`、`importorskip("x")` 不会被普通 import 扫描发现。
   每次改名都要额外搜一遍（已踩 3 次）。

5. **跨组依赖按「实际引用」推导，别全量互导**
   第一版给每个子模块全量互导，直接制造 `transport ↔ quote` **循环导入**。

6. **本机跑全量 pytest 时 `exit=1` 可能是假信号**
   `safe-delete` 钩子清理临时目录超时会污染退出码并吞掉摘要。
   **已根治**：`run_ci.py` 改以 JUnit 报告判定。直接跑 pytest 时看进度条有无 `F`。

7. **Edit 工具偶发「返回成功但内容未落盘」**
   关键改动请**回读校验**，不要只信返回值。

8. **PowerShell 特性**
   无 heredoc（`git commit -F -` 不可用，先写文件再 `-F <path>`）；
   `Set-Content -Encoding UTF8` 会加 **BOM + CRLF**（用 Write 工具代替）。
   `Add-Type` 被安全策略拦截 → 无法用 Recycle Bin API 删目录。

9. **推送链路**
   `.git/config` 的 `http.proxy=127.0.0.1:10808` 常失效但**直连可用**；
   git ↔ GCM 在私有仓库上**静默退出 128 且零输出** → 用
   `git_auth_run.py push --remote origin --branch main --no-proxy` 绕过。
   **避免 `git rebase`**（曾观测到异常退出后 `.git` 目录消失）。

10. **目录体积疑云**
    「10 MB」里约 8.3 MB 是工具缓存（`.mypy_cache` 占 7.5 MB）。

11. **一处错误的类型标注会污染整条调用链**
    `day_reader` 把含 `date: str` 的 bar 标注为 `Dict[str, float]`，下游
    `backfill` / `screen` / `five_factor` / `adjust` / `run_*` 全部据此把 date
    当 float 用 —— **单点错误贡献了 mypy 57 项中的约 30 项**。
    **教训：类型标注必须诚实（混合类型就用 `Dict[str, Any]`），
    不要为了"好看"而声称单一类型。** 排查时先看**根因文件**，别逐条改下游。

12. **循环内定义的闭包会捕获循环变量（ruff B023）**
    若闭包逃逸到循环外，全部实例读到的是最后一轮的值 —— **静默失效**。
    本仓库 9 处属于"同轮内立即调用"，当前正确但依赖隐含前提。
    **约定：循环内定义闭包一律用默认参数显式绑定当轮变量**
    （`def f(x, _v=v)`）；能用模块级函数就不用闭包（`backfill._ret_at` 已如此重构）。

13. **mypy 的变量名复用会让类型推断崩塌**
    同一函数内 `o` 既作 `Optional[float]` 又作循环元素、`c` 既作 float 又作 str、
    `f` 既作 dict 又作文件句柄 —— 都会产生成片的伪错误。
    **排查手法：先看错误消息里的类型，再回头找同名变量的"前一次绑定"。**

14. **`tests/` 之外的自测脚本不会被 pytest 收集**
    `tdx_native/smoke_test.py` 函数名以 `test_` 开头，但 pytest 默认只收集
    `tests/test_*.py` —— 该模块因此长期零门禁覆盖（新模块在门禁之外 = 静默失效）。
    **约定：新增自测一律放 `tests/`。**
    判断真实大小：`git ls-files` 统计受控文件体积。

11. **等距抽样在旋转下可能不变 —— 静默失效**
    1000 抽 300、偏移 200/400/600/800 时，等距抽样的索引集合在旋转下**不变**
    → 5 个子样本完全相同（对称差 0）→ 输出「标准差=0，离散度完美」的假结论。
    已改带种子洗牌，并有复现型回归测试。

12. **退市股数据存在但需主动合并**
    TDX 本地数据只含存活股；退市股在 `D:/tdx_dataset/delist/`，须经
    `scripts/merge_delisted_into_dataset.py` 并入，否则结果含幸存者偏差。

13. **「数据源拒绝」与「无数据」必须区分**
    早期 `kline_span()` 把异常吞掉返回 `(None, None)`，被封禁后仍"正常"跑完并输出
    「窗口内退市 0 只」。已新增 `SourceBlocked` 异常，捕获后**立即中止且不写文件**。

14. **引用「年化超额」必须标注算术还是几何**
    因子/滚动类研究用**算术** `mean(日超额)×252`；A/B 组合层面用**几何**
    `(期末/期初)^(1/年)−1`。两者有波动时必然不等，数字**不可直接比较**。

15. **文档声称"自动生成"就必须真有生成器**
    `DIRECTORY_LAYOUT.md` 曾声明由 `gen_layout_doc.py` 生成，但该脚本
    **从未入库**（只存在于会话 scratch 目录）→ 文档静默漂移（漏 `console/` 包、
    `main.py` 仍写 402 行）。已恢复生成器并加同步守卫。

16. **本机批量删除 >50 个文件会被安全护栏拦截**
    `safe-delete` 钩子报 `SAFE_DELETE_BULK_CONFIRM_REQUIRED`（阈值 50，按轮次累计）。
    这是环境护栏，**不应绕过**；需用户显式确认或自行删除。

### 6.2 高风险模块

> 判据：①正确性关键且错了不易发现；②改动会静默改变已发布结论；③无直接测试覆盖。

| 模块 | 风险 | 原因 |
|------|:---:|------|
| `track/`（`tracking.py`） | 🔴 高 | `_DB_PATH` 由 `__file__` 派生，持有**实盘记录**；已因拆分静默迁址一次 |
| `factors/factor_ic_lab.py` | 🔴 高 | `PRIOR_SIGN` 定义因子方向，**符号写反会让策略完全反向**（基线正是栽在这） |
| `alpha/alpha_survival_lab.py` | 🔴 高 | Alpha 裁决逻辑；年化口径与判定门槛都在此，改错即产出虚假结论 |
| `pit/`（`pit_universe_builder` 等） | 🔴 高 | PIT 正确性 = 无前视偏差；错则全部回测失真且**看不出异常** |
| `release_gate.py` · `research_integrity.py` | 🔴 高 | 发布门禁；判错会把无效结论放行 |
| `survivorship_guard.py` | 🟠 中高 | 数据偏差门禁；失守则研究结论被系统性美化 |
| `fetch/`（`data_fetcher.py`） | 🟠 中高 | 门面 + SSL/限流/缓存；monkeypatch 不穿透问题曾在此暴露 |
| `scripts/run_contrarian_portfolio.py` | 🟠 中高 | 硬编码窗口与滑点模型；三阶段结论全靠它 |
| `credential_scan.py` · `run_ci.py` | 🟠 中高 | 门禁工具自身出错 = **假绿**（已发生一次 pytest 假失败） |
| `orchestrator.py` | 🟡 中 | 337 行核心类；2026-09-16 已补 21 项行为测试（借此发现 `load_session` 必然失败的严重缺陷并修复） |
| `console/`（`main.py`） | 🟡 中 | 程序入口；`main.py` 曾 402 行无测试，现补了 15 项冒烟 |
| `notify/feishu_notifier.py` | 🟡 中 | `WORK_DIR = dirname(__file__)`；发送参数曾用错（`--content` 应为 `--text`） |
| **`tdx_native/day_reader.py`** | 🔴 高 | `.day` 二进制解析是**全部原生数据的唯一入口**；struct 格式或 `PRICE_DIV` 错则整条链路静默失真 |
| **`tdx_native/adjust.py`** | 🔴 高 | 前复权因子；错则 `ret20` 被权息缺口污染（实测 000028 会把 −2.47% 读成 −13.70%） |
| **`tdx_native/backfill.py`** | 🔴 高 | L3 校准的日期口径（T+1 建仓 / T+5 / T+20 / 停牌顺延）；错则推荐质量被系统性误判 |
| **`tdx_native/five_factor.py`** | 🟠 中高 | `DIRECTIONS` 与 `factors/factor_ic_lab.py` 的 `PRIOR_SIGN` 同性质 —— **方向写反即策略反向** |
| 无直接测试引用（10 个） | 🟡 中 | `agents_base` · `cycle_price_action` · `llm_client` · `log_utils` · `market_universe_provider` · `pool_manager` · `professional_committee` · `prompt_engine` · `stock_god` · `v3_data_bus`（可能被间接覆盖） |

> `tdx_native` 的 4 个高风险模块已于 2026-09-30 纳入 `tests/test_tdx_native.py`
> （40 项），风险等级由「🔴 高 + 无覆盖」降为「🔴 高 + 有守卫」。

---

## 七、剩余任务与预估工时

> 工时按**熟悉本项目的单人**估算，含自测与提交；不含等待外部凭据的时间。
> 研究类任务的工时**不可压缩**（须跑多窗口回测，单次 40 分钟以上）。
> **本节已于 2026-09-25 按实际完成情况重排**（此前 7 项已完成却仍列为待办）。

### 7.1 已完成（2026-09-25 核对）

| 原编号 | 任务 | 状态 |
|:---:|------|------|
| 1 | 在 v3 上重跑全部关键检验 | ✅ 6 窗口双基准滚动 + 因子 IC + 正交化前后对照 + 尾部剔除（v3） |
| 2 | 财务因子 IC 检验 | ✅ 7 因子 + 控制市值后的残差 IC；`pb`/`pe_ttm` 双校正显著 |
| 4 | 策略层面实验补记 p 值 | ✅ **Δ 型用配对 t 检验从归档直接算出**（9 项）；绝对型重跑了尾部剔除 / A-B / 集中度 / 成本模型 / ADX |
| 5 | P1-9 数据集增量更新管线 | ✅ 重叠日校验，14 项测试 |
| 6 | P1-7 / P1-8 替代路径决策 | ✅ **已决策放弃**（2026-09-22）；代价已记录（`pb`/`pe_ttm` 未做行业中性化） |
| 7 | 财务数据源真实披露日 | ✅ 巨潮 `实际披露` 接入，A 股池内覆盖 86.8%、实际使用口径 98.4% |
| 8 | 修复 `tdx_ab_stage2` verdict 文案 | ✅ 已修 + 守卫测试 |
| — | 缓存备份处置 | ✅ 已结案（保留现状） |
| — | 长跑脚本分段落盘 | ✅ `research_artifacts` + 5 脚本接入 + 22 项守卫（本轮新增） |

### 7.2 未完成

| 优先级 | 任务 | 预估工时 | 假设与说明 |
|:---:|------|:---:|------|
| **1** | **新的经济逻辑假设（追求 Alpha）** | **3~5 天** | **当前唯一的主攻方向**。含逻辑调研 0.5 天 → 事前登记 0.5 天 → 因子实现 1 天 → IC 检验 0.5 天 → 组合层面 + 基准对照 1~2 天。**前提：必须提出新逻辑，禁止调现有因子权重/阈值**（原则 5） |
| 2 | 为**无直接覆盖模块**补单测 | **2~3 天** | ⚠️ **2026-10-15 复核：实测 29 个**（HANDOVER 原记「剩余 9 个」已过时；首次盘点曾报 43，因脚本漏判 `from pkg import mod` 而虚高，已修）；口径见 `scripts/list_uncovered_modules.py`（只看测试里的直接 import）。✅ 已完成：`orchestrator`(21) · `pool_manager`(22，本轮)。下一步优先 `v3_data_bus`、`professional_committee`；纯标注类（`log_utils`）可略 |
| 3 | 巨潮披露日早年覆盖补强 | **0.5 天** | 2016~2021 年覆盖 73~83%，余 12.8% 走法定截止日兜底。可试逐股接口补齐（`stock_zh_a_disclosure_report_cninfo`），但**已确认缺口多为当时未上市的公司**，收益可能有限 |
| 4 | ADX 叠加的**绝对水平** p 值 | **1~2 小时** | Δ 型已用配对检验补完（§7.13）；`adx_attr_w1~w4.json` 只存了 const05 变体，overlay/baseline 的绝对超额 t/p 需重跑 `run_regime_overlay_study.py` |
| 5 | 补齐数据库迁移机制 | **0.5 天** | 当前无迁移脚本；若 schema 需变更则必须先做 |
| 6 | ARK 付费模型凭据验收 | **0.5 天** | **阻塞于用户提供凭据**；含接通 + 一次真实调用 + 结果留档 |
| 7 | 其余外部集成验收 | **1 天** | **阻塞于凭据**；每项含真实调用 + 留档 |
| 8 | `disallow_untyped_defs` 全量收紧 | **2~3 天** | 569 处纯标注补全，**无缺陷捕获收益**，建议最后做 |

**建议顺序**：**1（主攻）** → 2 → 3 → 4 → 5 → 6/7（待凭据）→ 8
| — | 缓存备份处置 | **已结案（保留）** | 2026-09-16 已核验 `_1.0_cache_backup_…`（9.8M，纯缓存）与 `_backup_1.0`（9.1M，完全冗余）均为零信息损失；因环境批量删除护栏拦截，**用户决定保持现状**。其中的研究证据已抢救入库（`AB_STUDIES_EVIDENCE.md`） |
| — | ~~门禁欠账（ruff 51 / mypy 57 / pytest 2）~~ | **✅ 已完成（2026-09-30）** | 根因是 `d7625ff` 未过门禁即入库。已清零并补 `tdx_native` 守卫测试 40 项；见 [5.3](#53-已知缺陷与复现步骤) 第 6~8 条 |
| — | ~~`tdx_native` 零测试覆盖~~ | **✅ 已完成（2026-09-30）** | `tests/test_tdx_native.py`（40 项），覆盖 4 个高风险模块 |
| **1** | **新的经济逻辑假设（追求 Alpha）** | **3~5 天** | 含：逻辑调研 0.5 天 → 事前登记 0.5 天 → 因子实现 1 天 → IC 检验 0.5 天 → 组合层面 + 基准对照 1~2 天（多窗口回测）。**前提：必须提出新逻辑，禁止调现有 7 因子权重/阈值** |
| 2 | ARK 付费模型凭据验收 | **0.5 天** | 阻塞于用户提供凭据；含接通 + 一次真实调用 + 结果留档 |
| 3 | ~~修复 `tdx_ab_stage2` verdict 文案~~ | **✅ 已完成** | 根因是 `params` 未记录 `slip_mode`。已修脚本 + 加守卫测试（见 [5.3](#53-已知缺陷与复现步骤) 第 1 条） |
| 4 | ~~为 10 个无直接覆盖模块补单测~~ → **实测 29 个**（2026-10-15 复核，原记「剩余 9 个」过时） | **2~3 天** | ✅ `orchestrator`(21) · `pool_manager`(22) · `v3_data_bus`(24) · `professional_committee`(22) · `risk/expert_filter`(33) 已完成（共 122 项，暴露 4 个缺陷）；剩余优先 `v3_data_bus`、`professional_committee`；纯标注类（`log_utils`）可略 |
| 5 | `disallow_untyped_defs` 全量收紧 | **2~3 天** | 569 处纯标注补全，**无缺陷捕获收益**，建议最后做 |
| 6 | 其余外部集成验收 | **1 天** | 需凭据；每项含真实调用 + 留档 |
| 7 | 补齐数据库迁移机制 | **0.5 天** | 当前无迁移脚本；若 schema 需变更则必须先做 |
| 8 | **L3 跟踪样本积累（非工时类）** | **持续** | `tracking.csv` 当前 20 行全 pending（TDX 客户端数据停在 0928）。需**每交易日 15:05 后**开一次通达信更新 `.day`，再 `python -m tdx_native.run_daily`。样本到期后才能校准推荐质量 |
| 9 | 北交所数据接入 | **0.5~1 天** | 阻塞于 pytdx：`get_security_list` 的 `market=2` 在 20 台服务器均不可用。备选：从本地 `bj/lday` 目录直接扫（`scan_stocks` 已支持 `bj`） |

**建议顺序**：2 → 1（主攻方向）→ 8（并行，每日维护）→ 4 → 7 → 9 → 6 → 5。

> **运行前提（重要）**：`tdx_native` 的日度推荐与回填都依赖**本地 TDX 客户端数据**
> （`D:/new_tdx/vipdoc`）。若客户端未更新，`run_daily` 会因**未收盘保护**或
> `as_of_not_in_calendar` 而拒绝/标记，**不会产出假数据**（这是刻意设计）。


## 八、中断后如何接上（会话恢复流程）

长任务可能在任意时刻中断。按以下顺序重建状态，**不要凭印象继续**：

```bash
cd C:/Users/T430/Desktop/1.0

git log --oneline -8      # ① 看最后提交，确认做到哪一步
git status --short        # ② 有无未提交变更（有则上次中断在提交前）
python run_ci.py          # ③ 一条命令验证状态是否绿
```

然后按顺序读：

| 顺序 | 文档 | 回答什么 |
|:---:|------|---------|
| 1 | 本文件 | 现状、约定、**踩坑**、**高风险模块**、待办与工时 |
| 2 | [`WORKLOG.md`](WORKLOG.md) | 上次改造做了什么、为什么、证据 |
| 3 | [`CHANGELOG.md`](CHANGELOG.md) | 版本演进与历次收紧 |

**关键提醒**：

- **本文件 HEAD 可能过期** —— 以 `git log` 实际结果为准。
- **踩坑清单（[6.1](#61-踩坑清单)）务必先读** —— 每次踩的坑都在上面有前例。
- **未提交变更 = 中断风险**。若 `git status` 非空，先跑 `python run_ci.py` 判断完整性。

**降低中断损失**：①分小步提交（每个可验证的小改动就提交）；②提交信息写清"为什么"；
③改动前确认工作区干净。


---

## 长跑脚本增量落盘（2026-09-24 已解决）

**风险**：研究脚本单次运行 10 分钟~2 小时，而本机后台进程会**静默死亡**。
2026-09-23 实测：集中度实验跑到第 11/12 次回测时进程无报错退出，
因脚本只在结尾写一次 JSON，**10 次回测（约 2 小时）结果全丢**。

**机制（已落地）**：`research_artifacts.py` 提供 `.partial` + `complete` 双文件落盘。

| 约定 | 含义 |
|------|------|
| 存在正式 `<out>` | **代表跑完**（`complete: true`） |
| 存在 `<out>.partial` | 部分结果，**可抢救但不得当完整结果** |
| 写入方式 | 原子（`.tmp` + `os.replace`），不会读到半成品 |

**已接入**：`run_tail_exclusion_study` / `run_regime_overlay_study` /
`run_cost_model_check` / `run_contrarian_portfolio` / `run_concentration_study`。

**防回退守卫**：`tests/test_research_artifacts.py`（22 项）——
参数化断言这 5 个脚本必须调用 `write_partial`，且禁止再出现 `open(args.out, "w")` 的裸结尾落盘。

> **新增长跑脚本时**：必须接入 `write_partial` / `write_final`，否则守卫会红。


---

## 附：2026-09-25 新发现的三个数据缺陷（均已处置）

> 三个缺陷都是为「新假设做数据尽调」时暴露的 —— 不做尽调就不会发现。
> **共同教训：新增数据源必须逐字段验证，不能假设"拿到了就是对的"。**

### 缺陷 A · `_norm_date` 把 pandas 缺失值写成字符串 `"NaT"`（✅ 已修 + 已重抓）

| 项 | 内容 |
|------|------|
| **现象** | 巨潮披露日 176,841 条中 **11 条** `actual_disclose="NaT"` |
| **根因** | `_norm_date` 只判 `None`；`str(pd.NaT) == "NaT"`（长度 3，**非空串**），下游 `if not actual` 抓不住 |
| **暴露方式** | `date.fromisoformat("NaT")` 才报错 —— 若下游只做字符串比较则**永远静默** |
| **连带损伤** | `revisions` 字段**从诞生起就是废的**：三个变更字段都被 `"NaT"` 判为非空 → 恒等于 3（分布 `{3: 176310}`） |
| **修复** | ① `_norm_date` 显式判 `nat/nan/none/空` → 返回 `""`；② `load_disclosures` 加 ISO 格式校验（防御纵深） |
| **验证** | 重抓后 **176,830 条、非法日期 0**；`revisions` 恢复意义：0→90.7%、1→8.9%、2→0.5%、3→0.03% |
| **守卫** | `tests/test_disclosure_dates.py` 新增 15 项（含 `float("nan")` 路径，不引入 pandas 依赖） |
| **旧文件** | 保留为 `disclosure_dates.jsonl.defective`（可对照） |

### 缺陷 B · 创业板涨跌幅 PIT 违规（✅ 已修 + 已回写数据）

| 项 | 内容 |
|------|------|
| **现象** | `derive_limit_ratio` 对创业板**无条件返回 0.20**，把 2020-08-24 起才生效的 ±20% 追溯到了 2016 年 |
| **量化** | 创业板 2,121,218 行中 **738,070 行（34.8%）** 涨跌幅被高估，涉及 **834 只** |
| **后果** | **不是"近似"而是偏乐观**：该期间 10% 涨停的「一字板」不会被「涨跌停不可买」检查拦住（10% < 20% 阈值），回测多吃了本不可成交的成交 |
| **修复** | 按交易日分段：创业板 2020-08-24 前 **非 ST 10% / ST 5%**，之后 20%；科创板仍恒 20%（2019-07-22 开板即 20%） |
| **⚠️ 光修代码不够** | 个股 CSV **逐行存了 `limit_ratio`**，而 `exchange_rules.limit_ratio()` **优先采用存储值** → 必须回写数据 |
| **回写工具** | `scripts/patch_limit_ratio.py`（默认试算，`--apply` 才落盘；同步更新 `metadata.sha256` 保持审计链） |
| **验证** | 试算改动数与独立统计**完全一致**（834 只 / 738,070 行 → 全为 0.1）；抽查 6 只 sha256 一致；小样本审计无失败项；`300001` 2020 年正确分段（155 行 10% + 88 行 20%） |
| **守卫** | `tests/test_exchange_rules.py` 新增 7 项（分段边界 2020-08-21 / 2020-08-24、科创板、创业板 ST） |

### ~~缺陷 C · 创业板 ST 标记仅 2020 年起有值~~ → ✅ **【2026-09-26 撤回】不是缺陷**

| 项 | 内容 |
|------|------|
| **现象** | 创业板 `is_st=1` 的行**只出现在 2020 年及以后**；2016~2019 **全为 0** |
| **对照** | 全池 ST 行 2016 年即有 10,556 行（1.64%），并非"早期无 ST" |
| **`st_basis` 构成** | `官方(深交所)` 189,962 行 + `推断(±5%涨跌幅限制)` 129,854 行 —— 推断法对改革前创业板（10% 限制）**失效**，这很可能是缺口来源 |
| **影响** | ① 该期间创业板 ST 股的涨跌幅会按 10% 而非 5% 处理（与缺陷 B 同类乐观偏差，但**规模小得多**）；② 任何依赖 ST 状态的假设（如 backlog 的 H-D3）**创业板部分样本不完整** |
| **处置** | **未修**（需外部 ST 历史数据源）。已写入 `ALPHA_HYPOTHESIS_BACKLOG.md` H-D3 的「已知风险」，**结论必须声明该缺口** |

⚠️ **【2026-09-26 撤回】此判断是错的 —— 创业板 2012-05 ~ 2020-08 确实【没有】ST 制度。**

依据（两条官方来源 + 一条数据验证）：
1. **中国证监会**（2012-05-24，《创业板退市制度解读（一）》）：
   「改革了退市风险提示方式。**为避免存在退市风险的创业板公司与主板、中小企业板被实施
   '*ST' 的公司相混同**…」→ 2012 年修订起创业板**不再使用 *ST 标记**。
2. **深交所**（2020-08-07）：「《交易特别规定》实施前，创业板风险警示股票（ST、*ST 股票）
   的价格涨跌幅限制比例为 5%」→ 2020-08-24 注册制改革**重新引入** ST/*ST。
3. **数据验证**：创业板 `is_st=1` 的行**全部在 2020-09 及之后**，
   改革日（2020-08-24）**之前为 0 行** —— 与「改革后重新引入」完全吻合。

**故数据集该特征【正确】，不是缺陷。** 原始判断把「制度性不存在」误读为「数据覆盖缺口」。
教训：判断某字段「应该有值却没有」之前，**必须先确认该字段在当时的制度下是否本应存在**。


### 关联文档

- `ALPHA_HYPOTHESIS_BACKLOG.md` —— 本轮尽调的产出：4 条基于**新数据维度**的候选假设 + 登记检查清单
- `P0_P1_EXECUTION_REPORT.md` —— P0/P1 执行与统计量补记


---

## 附：H-D2 执行结果（2026-09-25）

**假设**：定期报告预约披露日的变更次数越多，披露后未来收益越低（方向 −1）。
**登记**：`ALPHA_HYPOTHESIS_PREREG_HD2.md`（跑前固定口径）
**产物**：`reports/hd2_disclosure_revisions.json`

| 项 | 值 |
|------|------|
| 有效调仓期数 | 414 |
| IC 均值 | **−0.0034** |
| t（H0: IC=0） | **−1.65**（p = 0.0994） |
| 子窗口 1（2016-08~2021-06） | IC = **−0.0090**，t = **−2.85** |
| 子窗口 2（2021-07~2026-09） | IC = **+0.0012**，t = +0.43（**符号相反**） |
| 组差（有变更 − 无变更） | +0.0260%，t = +0.59 |
| 与既有价量因子相关性 | \|ρ\| ≤ 0.029（因子独立） |

### 判定：❌ **不成立**

按事前登记，「两子窗口 IC 符号相反」直接触发「不成立」。
前半段显著为负（t = −2.85）而后半段消失并翻正 → **一个只在部分样本成立的因子不构成可用信号**。
**不得**表述为「前半段有效」或「待优化」。

### 执行中暴露并修掉的两个问题

1. **判定逻辑与登记矛盾**：原判定内联在 `main()`，把「子窗口符号相反」误判为「弱支持」——
   **即放宽结论**。已抽成纯函数 `decide_verdict`，并加 11 项守卫
   （`tests/test_disclosure_factor_study.py`），其中一条专门锁住该情形。
2. **登记表自身矛盾**：弱支持写「子窗口符号不一致」，不成立又写「两子窗口符号相反」——
   同一情形。已按**更严**方向勘误，并在登记中明确记录"该勘误发生在看到结果之后，
   修正方向是收紧而非放宽"。

> **教训**：事前登记的价值只有在**判定逻辑可测**时才兑现。
> 判定写在 `main()` 里、无法单测，就一定会漂移。


---

## 附：H-D3 执行结果（2026-09-25）

**假设**：ST 状态股票的未来收益高于非 ST（困境反转）；次假设：ST 内部业绩改善者收益更高。
**登记**：`ALPHA_HYPOTHESIS_PREREG_HD3.md`（含**可实现性检查**，跑前固定）
**产物**：`reports/hd3_st_reversal.json`

### 主检验 H-D3a：❌ 不成立（方向相反）

| 项 | 值 |
|------|------|
| Δ 均值（ST − 非 ST） | **−0.2192%** |
| t | **−1.65**（p = 0.0994） |
| 子窗口 1 | **−0.2230%**（t = −1.20） |
| 子窗口 2 | **−0.1894%**（t = −0.96） |

**ST 组跑输非 ST 组**，与假设方向相反；两子窗口同号为负 → 判「不成立」。
按登记，**不得**改述为「反向有效」。

**可实现性检查**：A 流动性 ✅（ST 组成交额中位为非 ST 的 35.9%）·
B 剔除不可成交 ❌（剔除 2,201 个「T+1 开盘即涨停」观测后 Δ = **−0.3584%**，更负）·
C 涨跌停约束 ✅ → **合计未通过**。
> 主检验方向已为负，故「可实现性」不再是瓶颈 —— **它本就没有正向超额可供实现**。

### 次检验 H-D3b：✅ 强支持（但须限定解读）

| 项 | 值 |
|------|------|
| ST 子样本内 `net_profit_growth` 的 IC | **+0.0313** |
| t | **+2.74**（p = 0.0061） |
| 子窗口 | **+0.0391**（t = +2.04）· **+0.0257**（t = +1.83）→ 同号 |

> ⚠️ **必须随结论声明的限制**：H-D3b 检验的是**既有已知因子** `net_profit_growth`
> （全样本 IC = +0.0097，t = 2.58）的**组内**表现。
> 故「强支持」的含义是「**该财务因子的效力集中在困境股群体内**」
> （组内 IC 约为全样本的 **3.2 倍**），**不是**发现新的独立信号，
> **不得**表述为新 Alpha 来源。

### 已知缺陷（登记 §6）

- ST 观测 16,296 个，其中**创业板占 16.5%**
- ~~创业板 ST 标记仅 2020 年起有值~~ → ✅ **【已撤回】这是正确特征**（创业板 2012-05~2020-08 无 ST 制度，见缺陷 C 说明）
- `st_basis` 含「官方(深交所)」与「推断(±5%涨跌幅限制)」两类；推断法对改革前创业板失效
- 未覆盖：新股前 5 日与退市整理期不设涨跌幅限制；未扣除交易成本

### 附带交付

`tests/test_st_reversal_study.py`（12 项）—— 承接 H-D2 的教训，
**判定逻辑一开始就抽成纯函数并单测**，其中一条专门锁住
「可实现性未通过时不得判强支持」。


---

## 附：H-D3 执行结果（2026-09-25）

**假设**：ST 状态股票的未来收益高于非 ST（困境反转）；次假设：ST 内部业绩改善者收益更高。
**登记**：`ALPHA_HYPOTHESIS_PREREG_HD3.md`（含**可实现性检查**，跑前固定）
**产物**：`reports/hd3_st_reversal.json`

### 主检验 H-D3a：❌ 不成立（方向相反）

| 项 | 值 |
|------|------|
| Δ 均值（ST − 非 ST） | **−0.2192%** |
| t | **−1.65**（p = 0.0994） |
| 子窗口 1 | **−0.2230%**（t = −1.20） |
| 子窗口 2 | **−0.1894%**（t = −0.96） |

**ST 组跑输非 ST 组**，与假设方向相反；两子窗口同号为负 → 判「不成立」。
按登记，**不得**改述为「反向有效」。

**可实现性检查**：A 流动性 ✅（ST 组成交额中位为非 ST 的 35.9%）·
B 剔除不可成交 ❌（剔除 2,201 个「T+1 开盘即涨停」观测后 Δ = **−0.3584%**，更负）·
C 涨跌停约束 ✅ → **合计未通过**。
> 主检验方向已为负，故「可实现性」不再是瓶颈 —— **它本就没有正向超额可供实现**。

### 次检验 H-D3b：✅ 强支持（但须限定解读）

| 项 | 值 |
|------|------|
| ST 子样本内 `net_profit_growth` 的 IC | **+0.0313** |
| t | **+2.74**（p = 0.0061） |
| 子窗口 | **+0.0391**（t = +2.04）· **+0.0257**（t = +1.83）→ 同号 |

> ⚠️ **必须随结论声明的限制**：H-D3b 检验的是**既有已知因子** `net_profit_growth`
> （全样本 IC = +0.0097，t = 2.58）的**组内**表现。
> 故「强支持」的含义是「**该财务因子的效力集中在困境股群体内**」
> （组内 IC 约为全样本的 **3.2 倍**），**不是**发现新的独立信号，
> **不得**表述为新 Alpha 来源。

### 已知缺陷（登记 §6）

- ST 观测 16,296 个，其中**创业板占 16.5%**
- ~~创业板 ST 标记仅 2020 年起有值~~ → ✅ **【已撤回】这是正确特征**（创业板 2012-05~2020-08 无 ST 制度，见缺陷 C 说明）
- `st_basis` 含「官方(深交所)」与「推断(±5%涨跌幅限制)」两类；推断法对改革前创业板失效
- 未覆盖：新股前 5 日与退市整理期不设涨跌幅限制；未扣除交易成本

### 附带交付

`tests/test_st_reversal_study.py`（12 项）—— 承接 H-D2 的教训，
**判定逻辑一开始就抽成纯函数并单测**，其中一条专门锁住
「可实现性未通过时不得判强支持」。


---

## 附：H-D4 与 H-D1 执行结果（2026-09-25）

### H-D4 · 涨跌停结构 —— ⚠️ 机械判定不成立，但**因子退化、不具实质意义**

`reports/hd4_limit_structure.json`

| 项 | 值 |
|------|------|
| 原始 IC（仅报告） | **−0.0194**（t = −9.02） |
| **残差 IC（判定依据）** | **+0.0643**（t = +9.73） |
| 残差子窗口 | +0.0596（t=+7.53）· +0.0667（t=+6.23） |
| `one_way_rate_20` 非零占比 | 中位 **1.28%**（最小 0.12%、最大 4.38%） |

**符号反转的根因已查明**：只控 `log_amount_20`+`vol_20`（**不含** `max_ret_20`）时
残差 IC = **+0.0628**（t=+8.89）—— 与含 `max_ret_20` 时几乎相同。
故**不是**"效应被 `max_ret_20` 解释"，而是 **Gram-Schmidt 在近乎退化的变量上
做残差产生的数值 artifact**（97.8% 的观测取同一值）。

**结论**：本假设在本数据集上**无法被可靠检验**。按登记机械判定为「不成立」，
但**不应赋予实质意义**。登记未预设「因子退化」情形 —— 已如实记录该登记缺陷。

### H-D1 · 披露时点偏离 —— ❌ 不成立

`reports/hd1_disclosure_advance.json`

| 项 | 值 |
|------|------|
| IC 均值 | **+0.00197** |
| t | **+1.00**（p = 0.3159） |
| 子窗口 1 | **+0.00353**（t = +1.21） |
| 子窗口 2 | **−0.00027**（t = −0.10）← **符号相反** |
| 组差 | −0.0447%（方向相反） |
| 非零占比中位 | 10.10% → **未退化** |

**判定：不成立**（子窗口符号相反）。

**两项登记改进（均来自前序教训）**：
1. **前视核查前置**：用「`revisions=0` 时 99.6% 满足 `actual == first`」这一分布，
   在跑之前确认 `首次预约` 是原始预约日、未被覆盖 → 排除了 backlog 标记的「最大风险」。
2. **因子可用性前置检查**：把「非零占比中位 ≥ 5%」写进登记（取自 H-D4 教训）。

### 四条候选的最终汇总

见 `ALPHA_HYPOTHESIS_BACKLOG.md` §二·补。**无一条产生可用的新 Alpha**；
唯一显著的是 H-D3b，但那是既有因子的组内增强，非新信号。


---

## 附：持有期与组合层研究（2026-09-26）

> 四条新假设（H-D1~H-D4）全部失败后，**从"找新因子"转向"结构性杠杆"**。
> 两份新报告：`FACTOR_HORIZON_DECAY_REPORT.md`（IC 衰减）·
> `HORIZON_NET_EFFECT_REPORT.md`（净效果）· `COMBO_STUDY_REPORT.md`（组合层）。

### 一、被忽视的量化事实：成本与 alpha 同量级

| 项 | 值 |
|------|------|
| 每 5 日调仓换手 | **~100%**（年化 ~50 次全换仓） |
| 成本拖累（V0 / V1） | **16.58 / 13.55 pp/年** |
| 对比：唯一稳健 alpha | +7.17pp（v3）/ +19.96pp（v1） |

### 二、持有期：h=20 明显优于 h=5（净效果，非 IC）

| 持有期 | 净超额均值 | 成本拖累 | 毛超额均值 | 为正窗口 |
|:---:|---:|---:|---:|:---:|
| 5 | **−34.72%** | 12.85pp | −21.87% | 0/3 |
| 10 | −33.69% | 6.63pp | −27.06% | 0/3 |
| **20** | **−7.46%** | 3.43pp | **−4.03%** | 0/3 |
| 40 | −10.36% | 1.78pp | −8.58% | 0/3 |

**h=20 比 h=5 改善 +27.26pp**，其中毛超额贡献 +17.84pp、成本贡献 +9.42pp。
⚠️ **非单调**（h=5≈h=10，h=20 才好）——机制不明，3 窗口不足以区分真实结构与抽样。

### 三、组合层：首次出现正超额配置，但**精度不足**

| 组合 | 持仓 | 均值 | 标准差 | 为正 |
|------|:---:|---:|---:|:---:|
| `C5_V0` 基线 | 5 | −7.46 | 6.44 | 0/3 |
| **`C5_V2` 仅尾部剔除** | 5 | **+4.96** | **9.69** | **2/3** |
| `C20_V0` 仅分散 | 20 | −2.96 | 13.39 | 1/3 |
| `C20_V2` 联合 | 20 | −6.00 | **1.52** | 0/3 |
| `C30_V2` 联合 | 30 | −5.54 | **1.36** | 0/3 |

**四条判读**：

1. **首次出现正超额配置**：`C5_V2`（h=20 + 尾部剔除）**+4.96%，2/3 窗口为正**。
2. ⚠️ **但它的离散度最大**（sd 9.69 > 均值本身）→ **+4.96% 与 0 无法区分**，不构成结论。
3. **分散度与尾部剔除是「负交互」**：`C20_V2`（−6.00%）比 `C5_V2`（+4.96%）**差 11pp** ——
   与"两者互补"的事前直觉**相反**。机制未查明（属推断）。
4. **分散度降低离散度的结论强复现**：sd **9.69 → 1.36（降 7 倍）**，但**代价是均值更差** ——
   明确的**精度 vs 均值权衡**。

### 四、对项目方向的判断（属推断）

- 四条新假设全失败 + 两条呈"前半段有效、后半段翻号"的同一模式
  → **信息类异象在样本后期已被定价**；
- 组合层已显示"分散度与尾部剔除相互抵消"，继续叠加工程杠杆的边际收益在下降；
- **更现实的路径是提高信号质量本身，而不是继续叠加工程杠杆。**
- ⚠️ 若要确立 `C5_V2` 的 +4.96%，需几十个独立窗口（单次回测 40 分钟以上）——**机器时间不可行**。


---

## ⚠️ 重要：打分函数「换手率分项静默失效」缺陷（2026-09-26 已修）

> 详见 `SCORE_TURNOVER_DEFECT_REPORT.md`。**这是本项目至今影响最大的一次口径变更。**

### 缺陷

`real_alpha_pipeline.load_certified_csv` 的字段白名单**漏掉了 `turnover`**，
而 `walk_forward.score_history` 的换手率分项（**−5 ~ +10 分**）依赖它
→ 该分项**对所有股票恒为 0，静默失效**。
CSV 中该列一直有值（认证字段，抽样 195,472 行全部非空）。

**不报错**：CSV 有值、打分函数有逻辑、中间少一环 —— 所有静态检查都发现不了。

### 量化影响

| 项 | 修复前 | 修复后 |
|------|------:|------:|
| 阈值 70 的**过线率** | **6.65%** | **18.71%**（近 3 倍） |
| h=5 净超额 | −34.72% | **−9.72%** |
| h=10 净超额 | −33.69% | **+1.05%**（2/3 为正） |
| **h=20 净超额** | −7.46% | **+5.21%**（2/3 为正） |
| h=40 净超额 | −10.36% | **+3.78%**（**3/3 为正**） |

**含义**：策略长期在**远窄于设计意图**的候选池里选股（6.65% vs 18.71%），
这直接解释了 5 股组合跨窗口离散度高达 9.69pp。

### 修复与守卫

- 修复：把 `turnover` / `turnover_rate` 加入加载器透传白名单
- 守卫：`tests/test_real_alpha_pipeline.py` +3 项 ——
  断言加载器透传**打分路径依赖的全部字段**（集合差集）、值正确、且分项真的生效

### ⚠️ 口径变更声明

| 项 | 说明 |
|------|------|
| 性质 | **恢复设计意图**（分档边界、权重、阈值一字未改） |
| 但会改变结果 | **所有经 `load_certified_csv` 的回测/研究结论均受影响** |
| 既有结论处理 | 一律标注为**「turnover 分项失效口径」**；新口径下需重验 |
| 不受影响 | 纯因子 IC 研究（不经 `score_history`）、尾部剔除的剔除集合构造（用 `compute_factors`） |
| 诚实声明 | 修复后结果**大幅变好**（+12.67~+34.74pp），但这**不是修复的理由**；若变差同样照实报 |

### 新增结论（新口径下，**3 窗口，不构成 Alpha 结论**）

**h=10 / 20 / 40 的净年化超额全部转正**，其中 **h=40 为 3/3 窗口为正**。
修复后毛超额：h=5 +3.82% · h=10 +7.87% · **h=20 +8.65%** · h=40 +5.55%。

⚠️ 仍受限于"只有 3 个窗口"，**不得作为"已建立 Alpha"引用**。


---

## 附：修复换手率缺陷后的组合层重跑（2026-09-26 晚）

| 组合 | 持仓 | 修复前 | **修复后** | 修复后 sd | 为正 |
|------|:---:|---:|---:|---:|:---:|
| `C5_V0` 基线 | 5 | −7.46 | **+5.21** | 7.03 | 2/3 |
| **`C5_V2` 仅尾部剔除** | 5 | +4.96 | **+9.31** | 12.42 | 2/3 |
| `C20_V0` 仅分散 | 20 | −2.96 | −3.28 | 9.69 | 1/3 |
| `C20_V2` 联合 | 20 | −6.00 | −5.49 | 1.69 | 0/3 |
| `C30_V2` 联合 | 30 | −5.54 | −5.51 | 2.22 | 0/3 |

**判读**：
1. **修复的影响集中在 5 股组合**（候选池扩大对"只取 top 5"影响最大）；`C20`/`C30` 几乎不变
2. **尾部剔除在修复后仍有效**（`C5_V2` 比 `C5_V0` 高 **+4.10pp**）
3. **分散度仍然拖累**，**负交互仍然存在**（`C20_V2` 比 `C5_V2` 差 **14.80pp**，与修复前同向）
4. **当前最佳配置 `C5_V2` = +9.31%，2/3 为正** ——
   ⚠️ 但 **sd 12.42 > 均值**，**与 0 无法区分，不构成 Alpha 结论**

详见 `COMBO_STUDY_REPORT.md` §八。


---

## 附：与桌面 `1.0` 的分支合并（2026-09-30）

> 详见 `BRANCH_MERGE_REPORT.md`。

### 背景

`C://Users//T430//Desktop//1.0`（原版）与本工作副本是**同一起点的两个独立仓库**，
在提交 **`ef0f5a9`** 处分叉，各自独立推进：

| | 桌面 `1.0` | 本工作副本 |
|---|---|---|
| 路线 | TDX 原生数据栈 + 产品化 | 口径修复 + 假设检验 |
| 假设编号 | H-F5/H-DECAY/H-F4/H-V2/H-ICX/H-SS/H-IMPACT/H-TC | H-D1~H-D4 |

**两套编号无重叠** ✓

### 本次合并（单向：`1.0` → 本副本）

| 类别 | 文件数 | 处置 |
|------|-------:|------|
| `1.0` 独有改动 | 40 | ✅ 直接搬入 |
| 两边都改、内容相同 | 15 | 无需处置 |
| 两边都改、内容不同 | 18 | 逐项判断 |

**关键冲突处置**：
- `portfolio_backtest.py` → 采用 `1.0` 版本（**超集**：含副本的 `position_scaler`、
  `_trade_cost(...,day)`、停牌不建仓，再加 `score_func`/`max_participation`/`impact_model`，默认值向后兼容）
- `mypy.ini` → **合并**（加入 `[mypy-pytdx.*]`）
- `risk/liquidity.py` → 采用 `1.0` 版本（纯新增 `sqrt_impact`）
- 文档类 → 保留副本版本

**搬入的关键内容**：
- `tdx_native/`（11 模块，TDX 原生数据读取 + 五因子推荐 + 回填 + 一键运行）
- `tests/test_tdx_native.py`（40 项守卫）
- **8 份事前登记**（H-F5/H-DECAY/H-F4/H-V2/H-ICX/H-SS/H-IMPACT/H-TC，均「待执行」）
- 5 个研究脚本 · `risk/liquidity.sqrt_impact` · `data/names.csv` · `run_daily.bat`

### ⚠️ 合并带来的三条重要结论

**1. 两条线独立发现同一件事（交叉验证）**
- `1.0` 的 H-TC 登记：「剩余最大的**确定性损耗**是换手成本」
- 本副本：「成本拖累 **16.58pp/年**，与唯一稳健 alpha(+7.17pp) 同量级」
→ **两个独立仓库得到同一结论**

**2. 本副本的结论直接回答了 `1.0` 的 H-DECAY 登记问题**

`1.0` 的 H-DECAY 登记动机原文：「T1（持有期 5→20）……**无法区分"省成本"与"信号仍在"**。」

本副本已做该实验（`FACTOR_HORIZON_DECAY_REPORT.md`）：
**慢变量 IC 随持有期单调增强至 40 日**（`amihud_20` 229% · `price` 253% ·
`log_amount_20` 173% · `vol_20` 139%）→ 结论是「**信号仍在**」，不只是省成本。

**3. ⚠️ `1.0` 没有 turnover 修复**

`1.0` 的 `load_certified_csv` **未包含 `turnover` 透传修复** →
其 T1 结论是在**「turnover 分项失效」口径**下得到的。
本副本已证明该缺陷使过线率从 18.71% 降到 6.65%（近 3 倍）。
故 `1.0` 的绝对数值**不可与本副本新口径直接比较**，但**方向性结论一致** ✓

### 合并后验证

| 项 | 结果 |
|------|------|
| `run_ci.py` | ✅ **6/6 全绿**（pytest **934 项**） |
| `tests/test_tdx_native.py` | ✅ 40 项通过 |
| `tdx_native.smoke_test` | ✅ 端到端通过 |
| `DIRECTORY_LAYOUT.md` | ✅ 重生成（793 → 818 行） |

### 未处置（需决策）

- 8 份 `1.0` 的事前登记**均未执行**（状态「待执行」）
- `1.0` 的 `HANDOVER.md`/`WORKLOG.md` 版本未吸收（避免覆盖本副本更新内容）
- `tdx_native` 需本机通达信客户端更新 `.day` 文件才能实跑

---

# 附：2026-10-14 收尾状态 —— PIT 快照 L3 收官 + P010 跨侧闭环

> **写入时 HEAD**：`ccf1cec`（**以 `git log` 实际为准**）。本附按「7 点交接要求」组织，
> 与上文（09-30 合并状态）叠加阅读；10-11~10-14 的逐日过程见 `.workbuddy/memory/2026-10-1*.md`。

## 1. 项目目标与进度

**主线（10-11~10-14）**：PIT 快照体系 L1/L2/L3 三层落地，其中 L3 全市场回填收官。
**验收标准（P3 §4，事前固定）与结果**：

| # | 标准 | 结果 |
|:--:|---|---|
| 1 | 退出码 0 / n_stocks≈5,667 / n_failed_codes=0 | ⚠️ 主跑退出码 **2**（601718 真截断，跑内全量恢复）；n_failed_codes=0 ✓；n_stocks=5,386=5,667−281（281 只源无覆盖，逐只定性） |
| 2 | `--rebuild-norm` 层间缺口 0 | ✅ 退出码 0，双向缺口 0（raw 5,386 = norm 5,386） |
| 3 | ingest_log 如实留痕 | ✅ FAIL/OK 双记录 |
| 4 | 对账 impossible=0 | ✅ n=60（P2 为 24）；**性质=逻辑一致性检查**（非统计代表性） |
| 5 | CI 六项全绿 | ✅ 6/6（pytest 1,163 项） |

**数据现状**：`D:/pit_snapshots` raw 11,060,152 行 / 5,386 只；norm 1:1 对齐；
281 只北交所 920 段 baostock 源不覆盖（本地 tdx 有数据；主干侧 tdx 实测 350 只可覆盖）
→ 清单 `meta/l3_zero_data_codes_2026-10-13.txt`，`--resume` 经边车排除（退出码 0）。

**跨侧状态**：P010（请求国内版独立评审）已闭环——主干四条建议全部采纳并落实
（`ccf1cec`），主干巡检 08:01 独立复现通过；**双方跨侧待办 0**；飞书群因租户策略
21001 瘫痪（**需人工重新授权**），信箱/台账通道正常。

## 2. 代码与仓库

- 仓库：`https://github.com/LCD9Z/L.git`（私有），分支 `main`；HEAD `ccf1cec`。
- 本批新增：`scripts/_study_common.py`（研究脚本共享 helper）·
  `scripts/_audit_l3_tail_gap.py`（零数据代码审计）· `tests/test_study_common.py` ·
  `tests/test_data_contracts_num.py` · `tests/test_mailbox_integrity.py`。
- **临时硬编码**：`scripts/run_pit_snapshot_ingest.py` 的 `_L3_SOCKET_TIMEOUT_S=120`
  （挂起防护，P3 §5 有实测依据）；无其他。
- **TODO/未落地**：920 段补数（**tushare daily_basic 源**，非 tdx——tdx 无估值字段，见 `PIT_L3_920_BACKFILL_FEASIBILITY.md`）· 审计 P3 同构 5 组参数化 ·
  L3 首个消费者前的流式读取已备好（`iter_normalized`），消费者尚未出现。

## 3. 环境与依赖

- 采集/对账：**系统 Python 3.13.15**（`baostock 0.9.3`；隔离 venv 无 baostock，勿用错）。
- 质量门禁：`run_ci.py` 6 项（syntax/ruff/mypy/compat/pytest/credentials）；
  ruff/mypy 走 `~/.workbuddy/binaries/python/envs/default/` 独立可执行文件。
- 数据根：`D:/pit_snapshots`（快照库）· universe `D:/tdx_dataset_v3`；
  baostock 端点只认 `sh./sz.` 前缀（`bj.` 报 10004011）。

## 4. 设计与文档

- 设计：`PIT_SNAPSHOT_DESIGN.md`；阶段报告：P0 / P2（对账）/ **P3（回填收官+韧性）**；
  证据索引 `EVIDENCE_INDEX.md`（58 份，由 `scripts/gen_evidence_index.py` 生成，
  守卫测试强制新证据必须登记）。
- 跨侧协议：`_AI协作信箱/README_协议.md`（P009 收敛规则等第十一节）· 台账 1,452 行。

## 5. 测试与已知缺陷

- **测试**：pytest 1,163 项 / CI 6/6；关键守卫：挂起超时顺序、零数据双形态、
  边车 resume 排除、层间双向缺口、等价性（_study_common）、行尾 LF、证据索引覆盖。
- **已知缺陷/限制（逐条）**：
  1. L3 缺 281 只 920 段（baostock 源不覆盖）——补数方案=换 tdx 源，未排期；
  2. `bs_symbol` 对 universe 外号段显式抛错（4/8 段）——bounded by 边车记账，非缺陷；
  3. 审计 P3 同构 5 组未收敛（LLM 输入，须专项冒烟）——缓做；
  4. 飞书通道 21001——通道层，待人工；
  5. **🔴 `backtest_engine._stamp_rate` 印花税分段失效**（2026-10-14 查出，主干已修我方未修）：
     `str(trade_date) >= str(change)` 在 `"20230825"` vs `"2023-08-28"` 下恒真
     （`'-' < '0'`）→ 2023-08-28 前的卖出按新税率 0.5‰ 计（应 1‰）→ **成本低估（乐观偏差）**；
     影响 `2023-07-03` / `2023-01-03` 起始的窗口；现有产物 verdict 不翻转但数字偏乐观。
     既有测试 `test_stamp_duty_is_piecewise_by_trade_date` 传带横杠日期故未抓到。
     处置待决：① 现在修 + 重算受影响产物，或 ② 随 A2 融合取主干版（含 `_norm_date` +
     `tests/test_execution_stress.py`）。
     **已定（双方 10-14 商定）= 方案③**：A2 合并取主干版代码 → 合并落定后统一重算。
     **受影响产物清单见 [`COST_BASELINE_PENDING_RECOMPUTE.md`](COST_BASELINE_PENDING_RECOMPUTE.md)**
     （Tier A 18 份待重算 / Tier B 1 份待核；重算完成前其超额数字不得作为有效结论引用）。

## 6. 踩坑记录与高风险模块

- **挂起不抛异常**（08:53 卡死 2h）→ `socket.setdefaulttimeout(120s)` 落入重试通道；
  全量回填生产检验 8 次网络错误全部恢复。
- **nohup 后台进程随工具壳层退出被静默 kill** → 长跑必须用受管后台任务。
- **Python `write_text` 在 Windows 文本模式写 CRLF**（832 处，被行尾守卫抓住）→
  跨文件改写必须 `write_bytes` 或显式 `newline=""`。
- **stdout 走管道是块缓冲** → 长跑进度看落盘文件增长，不看 tee 日志。
- **高风险模块**：`_fetch_l3`（backfill 主路径，改动影响 resume 语义）·
  `pit/pit_snapshot_store.py`（层语义：只追加不改写）· `real_alpha_pipeline.load_certified_csv`
  （认证加载，全研究脚本的地基）。

## 7. 剩余任务与预估工时

| # | 任务 | 预估 | 前置 |
|:--:|---|---|---|
| 1 | 920 段补数（**tushare daily_basic**，281 只 ≈ 4.7h API） | 0.5~1 人日 | **事前登记** + 价值确认（L3 尚无消费者，见可行性报告） |
| 2 | 审计 P3 同构收敛（generate_prompt×4 等 5 组） | 1~1.5 人日 | LLM 输入冒烟回归 |
| 3 | 9 个研究脚本的端到端等价回归（P2 收敛后） | 0.5 人日 | 需全量数据集 |
| 4 | ~~P006 两库 git 历史收敛~~ → ✅ **A2 已执行（10-15 合并提交 `86956c8`）** | 0.5~1 人日 | 见下方「A2 后状态」 |
| 4b | **成本口径统一重算（方案③下半场）** | 1.5~2 人日 | 机器规范集 24 份（`gen_evidence_index` 规则，主 12+副本 12）；修好代码后逐份重跑 + 对账；册子逐条标注 |
| 5 | 飞书群重新授权 | — | **人工**（租户数据安全策略） |

**A2 后状态（10-15 提交时）**：两库已并为单一 `main`（合并提交 `86956c8`，
双亲 = 我方 `f293d40` + 主干 HEAD）。pending recompute 的 24 份产物数字仍标注
「成本口径待核」（`reports/EVIDENCE_INDEX.md` ⚠️ 标记 + `COST_BASELINE_PENDING_RECOMPUTE.md`），
**方向性结论不受影响**（修复后成本升、收益降 ⇒「无 alpha」更稳）。
mypy 债务 6 文件/36 错已显式登记在 `mypy.ini` 尾段（主侧独有脚本的类型推断松散，
待逐项修复后移除）；`docs/external` 供应商代码三处门禁（ruff/mypy/冗余审计）均显式排除。
**下一个会话从「重算 24 份」继续**（判据与解除条件见登记册 §二/§五）。
