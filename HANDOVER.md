# 工作交接文档

> **项目**：AI股神团队 1.0 · A股多 Agent 智能分析系统
> **仓库**：`https://github.com/LCD9Z/L.git`（**私有**）　**分支**：`main`
> **HEAD**：`7a3d005`（**写入本文件时的值；每次提交都会变，以 `git log` 实际为准**）
> **交接范围**：2026-09-13 ~ 2026-09-16 的工程改造与量化研究
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
| 质量门禁 | ruff 零告警 · mypy 236 文件零错误 · pytest 516 项 · 本地 CI 6/6 | ✅ |
| 数据接入 | 通达信日线 → 认证数据集（清洗 + sha256 + PIT 股票池） | ✅ |
| 数据修正 | **幸存者偏差**（180 只窗口内退市股并入）· **不复权价**（分红送股复权因子） | ✅ |
| 因子研究 | 横截面 IC 检验引擎、9 个经济假设检验、多窗口滚动样本外 | ✅ |
| 组合研究 | 采样敏感性、持仓分散度、尾部剔除、多股票池重复验证 | ✅ |
| 假设检验 | 复合反转 H-C1（事前登记 → IC 强支持 → 组合层面 → 基准对照） | ✅ |
| 外部集成 | 飞书 notify 真实凭据验收通过 | ✅ |

### 1.3 待完成功能

| 项 | 说明 |
|----|------|
| **新的经济逻辑假设** | 现有 7 因子上已判定无 Alpha；需**新假设**（禁止调权重/阈值） |
| ARK 付费模型凭据验收 | 需用户提供凭据 |
| `disallow_untyped_defs` 收紧 | 569 处纯标注告警，收益递减，暂缓 |
| 无直接测试覆盖模块补测 | 见 [6.2](#62-高风险模块) |

### 1.4 验收标准

**工程验收**（一条命令）：

```bash
cd C:/Users/T430/Desktop/1.0 && python run_ci.py     # 期望 6/6 PASS
```

| 检查 | 通过标准 |
|------|---------|
| syntax | 全部 `.py` 可编译（含 BOM/编码检查） |
| ruff | `All checks passed` |
| mypy | `no issues found in 236 source files` |
| compat | Python 3.10 语法兼容 |
| pytest | 失败 0、错误 0（跳过 ≤1） |
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
├── <19 子包>/     每个都有 __init__.py（写「管什么 + 共同红线」）
├── scripts/       35 个可执行脚本（研究 / 数据准备 / 验收）
├── tests/         65 个测试文件
└── conftest.py    把项目根 + scripts/ 加入 sys.path
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

---

## 五、测试与已知缺陷

### 5.1 测试脚本

`tests/` 共 **65 个测试文件 / 516 项**。除常规单测外，**7 个为守卫测试**
（防止已修缺陷回退）：

| 守卫测试 | 守住什么 |
|---------|---------|
| `test_package_layout.py` | 包结构不回退：无平铺副本、无裸包名导入、包内相对导入、数据脚本不得散落根目录 |
| `test_python_compat.py` | Python 3.10 兼容；mypy `exclude` 不误伤真实源文件 |
| `test_layout_doc_in_sync.py` | `DIRECTORY_LAYOUT.md` 与仓库结构一致（含反向守卫） |
| `test_annualization_conventions.py` | 年化口径单一来源；禁止重新内联；算术≠几何 |
| `test_study_regressions.py` | 等距抽样塌缩、成本拖累窗口硬编码（**含缺陷复现**） |
| `test_survivorship_guard.py` | 幸存者偏差门禁 |
| `test_credential_scan.py` | 凭据扫描器自身正确性 |

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
| 1 | **`tdx_ab_stage2_summary.json` 的 verdict 与一阶段完全相同** —— 改滑点模型时未同步更新结论文案 | **未修**（数据正确，仅文案） | 打开该 JSON，对比 `tdx_ab_stage1_summary.json` 的 `verdict` 字段 → 文本一致，但 `annualized_pct` 已变（B 从 +23.21% 降至 +12.54%） |
| 2 | 研究脚本**绝对数字不可引用** —— 策略对采样数极度敏感 | 已记录，未根治 | 同窗口 `2023-07-03`：`--max-stocks 400` → V0 −83.06%；`800` → −28.34%（差 54.72pp） |
| 3 | `orchestrator.py`（337 行）**无直接测试引用** | 未修 | `grep -rn "orchestrator" tests/` → 仅 `test_module_splits.py` 检查拆分，无行为测试 |
| 4 | 10 个根目录模块无直接测试引用 | 未修 | 见 [6.2](#62-高风险模块) |
| 5 | `disallow_untyped_defs` 未开启（569 处纯标注告警） | 刻意暂缓 | `mypy.ini` 中该项为 `False` |

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
| `orchestrator.py` | 🟠 中高 | 337 行核心类，**无直接行为测试** |
| `console/`（`main.py`） | 🟡 中 | 程序入口；`main.py` 曾 402 行无测试，现补了 15 项冒烟 |
| `notify/feishu_notifier.py` | 🟡 中 | `WORK_DIR = dirname(__file__)`；发送参数曾用错（`--content` 应为 `--text`） |
| 无直接测试引用（10 个） | 🟡 中 | `agents_base` · `cycle_price_action` · `llm_client` · `log_utils` · `market_universe_provider` · `pool_manager` · `professional_committee` · `prompt_engine` · `stock_god` · `v3_data_bus`（可能被间接覆盖） |

---

## 七、剩余任务与预估工时

> 工时按**熟悉本项目的单人**估算，含自测与提交；不含等待外部凭据的时间。
> 研究类任务的工时**不可压缩**（须跑多窗口回测，单次 40 分钟以上）。

| 优先级 | 任务 | 预估工时 | 假设与说明 |
|:---:|------|:---:|------|
| — | 缓存备份处置 | **已完成待确认** | 已核验为零信息损失，但被环境批量删除护栏拦截，需用户确认 |
| **1** | **新的经济逻辑假设（追求 Alpha）** | **3~5 天** | 含：逻辑调研 0.5 天 → 事前登记 0.5 天 → 因子实现 1 天 → IC 检验 0.5 天 → 组合层面 + 基准对照 1~2 天（多窗口回测）。**前提：必须提出新逻辑，禁止调现有 7 因子权重/阈值** |
| 2 | ARK 付费模型凭据验收 | **0.5 天** | 阻塞于用户提供凭据；含接通 + 一次真实调用 + 结果留档 |
| 3 | 修复 `tdx_ab_stage2` verdict 文案 | **0.2 天** | 改脚本结论文案并重跑一次（或直接更正 JSON 并注明） |
| 4 | 为 10 个无直接覆盖模块补单测 | **1.5~2 天** | 优先 `orchestrator`（0.5 天）、`pool_manager`、`v3_data_bus`；纯标注类（`log_utils`）可略 |
| 5 | `disallow_untyped_defs` 全量收紧 | **2~3 天** | 569 处纯标注补全，**无缺陷捕获收益**，建议最后做 |
| 6 | 其余外部集成验收 | **1 天** | 需凭据；每项含真实调用 + 留档 |
| 7 | 补齐数据库迁移机制 | **0.5 天** | 当前无迁移脚本；若 schema 需变更则必须先做 |

**建议顺序**：3 → 2 → 1（主攻方向）→ 4 → 7 → 6 → 5。

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
