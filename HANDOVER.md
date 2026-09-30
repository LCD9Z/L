# 工作交接文档

> **项目**：AI股神团队 1.0 · A股多 Agent 智能分析系统
> **仓库**：`https://github.com/LCD9Z/L.git`（**私有**）　**分支**：`main`
> **HEAD**：`dbb198a`（**写入本文件时的值；每次提交都会变，以 `git log` 实际为准**）
> **交接范围**：2026-09-13 ~ 2026-09-30（工程改造 + 量化研究 + TDX 原生数据/推荐系统）
> **配套阅读**：[`WORKLOG.md`](WORKLOG.md)（过程与证据）· [`CHANGELOG.md`](CHANGELOG.md)（版本演进）· [`DIRECTORY_LAYOUT.md`](DIRECTORY_LAYOUT.md)（结构全景，脚本生成）

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
| **TDX 原生数据** | `tdx_native/`：`.day` 二进制直读、`gbbq` 3DES 解密→权息缓存、前复权（零第三方主路径） | ✅ |
| **全市场复检** | 5,613 只 / 632,968 样本 / 245 个不重叠截面（2021-08~2026-09）；五因子 IC 稳健性成立 | ✅ |
| **执行层改善** | C20 + 持有 20 日 + V2 跳空过滤（**唯二经组合层验证有效的参数**） | ✅ |
| **推荐系统产品化** | `tdx_native/`：日度推荐 + 名称表 + L3 跟踪回填 + 一键运行 + 自选股导出 | ✅ |
| **质量门禁** | ruff 0 · mypy 265 文件 0 错 · pytest **620 项** · 本地 CI 6/6 | ✅ |

### 1.3 待完成功能

| 项 | 说明 |
|----|------|
| **新的经济逻辑假设** | 现有 7 因子上已判定无 Alpha；需**新假设**（禁止调权重/阈值） |
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
| `reports/decay_h1.json` · `decay_h5.json` · `decay_h10.json` · `decay_h20.json` · `decay_h60.json` | IC 衰减曲线原始结果 |
| `reports/f4_p1~p3.json` · `reports/v2_p1~p3.json` | H-F4 / H-V2 组合层结果 |

---

## 五、测试与已知缺陷

### 5.1 测试脚本

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

| 优先级 | 任务 | 预估工时 | 假设与说明 |
|:---:|------|:---:|------|
| — | 缓存备份处置 | **已结案（保留）** | 2026-09-16 已核验 `_1.0_cache_backup_…`（9.8M，纯缓存）与 `_backup_1.0`（9.1M，完全冗余）均为零信息损失；因环境批量删除护栏拦截，**用户决定保持现状**。其中的研究证据已抢救入库（`AB_STUDIES_EVIDENCE.md`） |
| — | ~~门禁欠账（ruff 51 / mypy 57 / pytest 2）~~ | **✅ 已完成（2026-09-30）** | 根因是 `d7625ff` 未过门禁即入库。已清零并补 `tdx_native` 守卫测试 40 项；见 [5.3](#53-已知缺陷与复现步骤) 第 6~8 条 |
| — | ~~`tdx_native` 零测试覆盖~~ | **✅ 已完成（2026-09-30）** | `tests/test_tdx_native.py`（40 项），覆盖 4 个高风险模块 |
| **1** | **新的经济逻辑假设（追求 Alpha）** | **3~5 天** | 含：逻辑调研 0.5 天 → 事前登记 0.5 天 → 因子实现 1 天 → IC 检验 0.5 天 → 组合层面 + 基准对照 1~2 天（多窗口回测）。**前提：必须提出新逻辑，禁止调现有 7 因子权重/阈值** |
| 2 | ARK 付费模型凭据验收 | **0.5 天** | 阻塞于用户提供凭据；含接通 + 一次真实调用 + 结果留档 |
| 3 | ~~修复 `tdx_ab_stage2` verdict 文案~~ | **✅ 已完成** | 根因是 `params` 未记录 `slip_mode`。已修脚本 + 加守卫测试（见 [5.3](#53-已知缺陷与复现步骤) 第 1 条） |
| 4 | ~~为 10 个无直接覆盖模块补单测~~ → **剩余 9 个** | **1~1.5 天** | ✅ `orchestrator` 已完成（21 项，并修掉一个严重缺陷）。剩余优先 `pool_manager`、`v3_data_bus`、`professional_committee`；纯标注类（`log_utils`）可略 |
| 5 | `disallow_untyped_defs` 全量收紧 | **2~3 天** | 569 处纯标注补全，**无缺陷捕获收益**，建议最后做 |
| 6 | 其余外部集成验收 | **1 天** | 需凭据；每项含真实调用 + 留档 |
| 7 | 补齐数据库迁移机制 | **0.5 天** | 当前无迁移脚本；若 schema 需变更则必须先做 |
| 8 | **L3 跟踪样本积累（非工时类）** | **持续** | `tracking.csv` 当前 20 行全 pending（TDX 客户端数据停在 0928）。需**每交易日 15:05 后**开一次通达信更新 `.day`，再 `python -m tdx_native.run_daily`。样本到期后才能校准推荐质量 |
| 9 | 北交所数据接入 | **0.5~1 天** | 阻塞于 pytdx：`get_security_list` 的 `market=2` 在 20 台服务器均不可用。备选：从本地 `bj/lday` 目录直接扫（`scan_stocks` 已支持 `bj`） |

**建议顺序**：2 → 1（主攻方向）→ 8（并行，每日维护）→ 4 → 7 → 9 → 6 → 5。

> **运行前提（重要）**：`tdx_native` 的日度推荐与回填都依赖**本地 TDX 客户端数据**
> （`D:/new_tdx/vipdoc`）。若客户端未更新，`run_daily` 会因**未收盘保护**或
> `as_of_not_in_calendar` 而拒绝/标记，**不会产出假数据**（这是刻意设计）。

---

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
