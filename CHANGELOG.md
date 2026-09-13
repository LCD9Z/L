# CHANGELOG

AI股神团队 · A 股多 Agent 智能分析系统的版本演进记录。

> 本文件由 40+ 个 `PHASE*.md` 阶段文档归档合并而成（2026-09-11）。
> 原始阶段文档保留在 [`docs/archive/`](docs/archive/)，供追溯细节。

---

## 1.0 · 第四轮收紧（2026-09-13）

> 承接 1.0 的「遗留事项」清单逐条推进（详见 [MERGE_1.0_REPORT.md](MERGE_1.0_REPORT.md) 第六节）。
> 本轮的产出重点不是"把规则打开"，而是**收紧过程中暴露的既有缺陷**。

### 门禁与可复演性

- 新增 `run_ci.py`：**本地 CI 等价执行器**（零依赖），按工作流相同顺序跑完
  `syntax → ruff → mypy → compat → pytest → credentials` 六步，
  使「这次提交能否过 CI」在推送前即可知 —— 直接对应遗留事项 #1
- 新增 `credential_scan.py`：**凭据泄漏扫描器**（零依赖），CI 与本地共用同一实现
  - 替代此前工作流里的内联文本匹配：覆盖面从 3 个固定字面量扩展到
    「敏感变量被赋予非占位值」+「已知泄漏字面量」两类，文件类型扩展到
    `*.yml / *.yaml / *.toml / *.ini / *.sh / *.ps1 / *.cfg`
  - 显式放行模板（`<token>` / `$VAR` / `****` / `ou_xxxx` / 中文描述），
    避免误报导致检查被整体绕过
- 新增 `test_credential_scan.py`（19 例）与 `test_run_ci.py`（12 例）；
  后者含**漂移守护**：`ci.yml` 与 `run_ci.py` 任一方改了另一方没跟上即失败

### 类型检查收紧（mypy）

- 启用 `strict_optional = True` + `no_implicit_optional = True`，
  暴露并修复 **22 处**隐式 Optional 标注（`def f(x: str = None)`）
- **【严重】修正 `exclude` 模式误伤源文件**：`(?x)` 下的 `build` 片段未锚定，
  命中文件名子串，导致 `build_tdx_dataset.py` 与 `pit_universe_builder.py`
  **整个模块从未被类型检查**（目录模式 186 文件 vs 实际 188）。
  而项目内并无 `build/` / `dist/` 目录，该排除项从未用于其本意。
  已改为按路径段匹配，并补 `\.ruff_cache`
- `disallow_untyped_defs` 经评估**保持关闭**：开启会产生 569 处纯标注补全告警，
  无缺陷捕获收益（理由已写入 `mypy.ini`）
- 移除已成死配置的 `[mypy-pandas.*]` 节（代码库中已无 `import pandas`）

### 静态检查收紧（ruff）

逐点评审 `ignore` 中的 19 条挂起规则，**启用其中 9 条**并修复全部告警：

| 规则 | 含义 | 命中 |
|------|------|------|
| `F841` | 局部变量未使用 | 4 |
| `B905` | `zip()` 缺 `strict=` | 13 |
| `SIM115` | open 未用上下文管理器 | 10 |
| `B007` | 循环变量未使用 | 7 |
| `RUF100` | 未使用的 noqa | 6 |
| `RUF007` | 建议改用 `itertools.pairwise` | 5 |
| `RUF059` | 解包变量未使用 | 3 |
| `RUF013` | 隐式 Optional | 0（与 mypy 同源，作为回归守卫） |
| `RUF012` / `B904` | 可变类属性 / raise 链 | 0（回归守卫） |

其余（`RUF005` / `SIM102` / `SIM105` / `SIM108` / `UP028` / `C408` / `B008` /
`RUF100` / `RUF001-003`）逐条评审后**保留忽略并写明理由**，不再标记为"待办"。

`zip` 的 13 处按语义分流修复：确有等长不变量的加 `strict=True`（如
`factor_gate` / `factor_validation` 的 `_pearson`、`benchmark` 的收益配对），
连续配对模式 `zip(x, x[1:])` 改 `itertools.pairwise`（5 处）。

### 可选依赖纳入测试（遗留事项 #2）

- **重写 `test_tushare_provider.py`**：此前该文件因顶部 `import pandas` 被
  `pytest.ini` 整文件 `--ignore`，模块实为**零自动化覆盖**。现改用最小
  DataFrame 替身驱动纯逻辑，并用 `pytest.importorskip` 在装有 pandas 时
  追加真实 DataFrame 用例（3 例 → 14 例）
  - 明确不比对替身与 pandas 的**字节输出**：模块把 DataFrame 当作不透明对象，
    CSV 字节随 pandas 版本/平台变化，不属于契约
- **补 crawl4ai 启用分支**：原有测试只覆盖「依赖不可用 → 降级」，
  现补 6 例覆盖被启用的代码路径（正文替换、异常回退、空结果回退、
  无 URL 短路、环境变量开关、`cutoff_time` 透传）
- 相应从 `pytest.ini` 移除 `--ignore=test_tushare_provider.py`

### 发现的真实缺陷

| # | 缺陷 | 发现方式 | 处置 |
|---|------|---------|------|
| 1 | `mypy.ini` 的 `exclude` 使两个模块逃过类型检查 | 对照"186 vs 188"文件数 | 已修复 + 3 条守卫 |
| 2 | `stock_scoring.pe_note` 全分支赋值却从未写入「核心逻辑」 | 启用 F841 | 已修复 + 1 条守卫；`else` 分支还专门构造了 "PE %.1f"，可见本意是要展示 |
| 3 | `report_generator._generate_cover` 中 11 行死代码 | 启用 F841 | 已移除（封面从未引用 `final_rec` / `verdict_class`），输出不变 |
| 4 | `tdx_lifecycle.load_observed_lifecycle` 对缺失行数抛 `TypeError` | 启用 `strict_optional` | 改为**跳过该行**而非补造 0（缺失数据不补造）+ 1 条守卫 |
| 5 | `test_tushare_provider.py` 被整文件排除，非"部分覆盖" | 复核遗留事项 | 已重写并纳入 |
| 6 | 22 处隐式 Optional 标注 | 启用 `strict_optional` | 已修复 |
| 7 | CI 凭据扫描覆盖面不足且无法本地复用 | 审计工作流 | 抽出 `credential_scan.py` 共用 |

> 教训与 1.0 一致：静态检查的"零告警"只有在**规则真正生效、覆盖面真正完整**时才有意义。
> 本轮 7 项缺陷里有 3 项（#1 #3 #5）都是"看起来在检查、实际没检查到"造成的静默失效。

### 质量基线

| 指标 | 本轮前 | 本轮后 |
|------|-------|-------|
| 语法校验 | 184 个 .py | **188 个 .py** |
| ruff | All passed | All passed（**规则收紧 9 条**） |
| mypy | 182 文件零错误 | **188 文件零错误**（含此前逃检的 2 个模块） |
| pytest | 275 passed | **329 passed, 1 skipped** |
| 测试文件 | 57 | 59 |
| 行尾 | 全部 LF | **全部 LF**（0 个 CRLF） |
| 凭据扫描 | 内联 grep | **254 个文件，共用实现** |
| CI | 仅配置文件 | 配置 + **本地等价执行器** |

### 远端 CI 首次通过（2026-09-13）

仓库推送至 `https://github.com/LCD9Z/L`（私有）后，GitHub Actions 首次运行
**CI #1 全部通过**：

| 任务 | 结果 |
|------|------|
| `test (py3.10)` · `(py3.11)` · `(py3.12)` · `(py3.13)` | ✅ 全部 success |
| `credential scan` | ✅ success |

至此遗留事项 #1「CI 未在远端实际跑通」**闭环**。多版本矩阵真实执行通过，
说明 1.0 修复的 PEP 701 语法不兼容确实生效 —— 项目在声明支持的 Python 下限
（3.10）上可正常导入与测试。

**新增 `.gitattributes`（`* text=auto eol=lf`）**：1.0 曾因 CRLF 污染引入
`test_line_endings_are_lf` 守卫，但 Git for Windows 默认 `core.autocrlf=true`，
Windows 克隆仍会产出 CRLF 使该守卫失败。用 `.gitattributes` 从仓库层锁死行尾，
比要求每台机器改 `core.autocrlf` 可靠。（本机实测 `core.autocrlf` 即为 `true`。）

---

## 1.0 · 研究完整性门禁接入运行时（2026-09-13）

**问题（由结构化体检发现）**：`release_gate` 与 `survivorship_guard`
**只被测试文件引用**，没有任何可执行路径会调用它们；而 README 声称
「已接到发布流程」。这是**文档层面的"看起来有"**——恰恰与本项目
「结论可追溯、不许自欺」的原则相悖，且测试全绿会制造虚假安全感。
（同类模块共 26 个、约 1,200 行仅被测试引用，本次先处理门禁这一对。）

**修复**：让门禁成为流水线出结论前的强制一步。

| 发布路径 | 接入位置 |
|---------|---------|
| `real_alpha_pipeline.run_real_alpha_pipeline` | 统计结论算出后交门禁裁决 |
| `run_tdx_rolling_eval`（多窗口滚动检验） | 每个窗口的 verdict 均经门禁裁决 |

**新增接口**（`release_gate.py`，原有 `evaluate_alpha_release` 保持不变）

| 函数 | 用途 |
|------|------|
| `gate_alpha_claim(statistical_verdict, audit)` | 核心：返回**可发布结论**，保留 `statistical_verdict`，被阻断时给出 `missing_evidence` |
| `build_survivorship_audit(evidence, *, pit_universe_verified=False)` | 从证据清单构造审计，**未声明即视为缺失** |
| `load_survivorship_evidence(path)` | 读取证据清单 JSON（含 `source` / `as_of` 等溯源字段） |
| `missing_evidence(audit)` | 列出尚缺证据项 |

两个评估脚本新增 `--survivorship-evidence <json>` 参数。

**设计取舍**：统计结论与可发布结论**必须分开**。
「统计上不显著」与「证据不足无法判定」是两回事，混为一谈会把"数据不够"
误读成"策略不行"。因此 `statistical_verdict` 字段永不改写。

**当前效果**：TDX 数据缺 `lifecycle` / `delisted_history` / `st_history` /
`suspension_history` / `corporate_actions` 五项（`pit_universe` 由流水线自行校验
后如实声明为已具备），故所有 Alpha 结论降级为 `INCONCLUSIVE` ——
这正是数据现状的真实反映，不是故障。

**守卫**：新增 `test_alpha_release_gate.py`（26 例）。除行为测试外含**接线守卫**，
防止再度退化成"import 了但没人调用"：
- 断言 `run_real_alpha_pipeline` 与 `run_tdx_rolling_eval.main` 的**函数体内**
  确实调用了 `gate_alpha_claim`（用 `inspect.getsource`）
- 断言 `EVIDENCE_KEYS` 与 `audit_survivorship` 的参数名一致（防静默漂移）
- 断言 `missing_evidence` 覆盖全部证据项

---

## 1.0 · 目录分层第一轮（2026-09-13）

**背景**：根目录平铺 188 个 `.py`（18,607 行），**零子目录**。其中 59 个测试
+ 17 个 `run_*` 脚本 = 76 个（40%）并非库代码。1.0 曾花大力气拆"巨石文件"，
但目录层面从未分层。

**本轮做法**：先迁出**不需要门面**的部分（测试与脚本），库模块留在根目录。

| 位置 | 内容 | 数量 |
|------|------|------|
| 根目录 `*.py` | 库模块（导入路径完全不变） | 188 → **114** |
| `tests/` | `test_*.py` | 60 |
| `scripts/` | `run_*.py`（`run_ci.py` 除外） | 16 |

**为什么不动库模块**：若把 `data_fetcher` 等移入子包并保留 root 门面重新导出，
门面数量会与模块数量相当，等于没减少文件；若不留门面，则要改动上百处 import。
两者都不是本轮该承担的风险，故留待后续按家族逐个推进。

**关键约束与处理**

1. **pytest 导入路径**：测试下移一层后，`sys.path` 里只有 `tests/`。
   新增根级 `conftest.py` 把项目根加入 `sys.path`；
   少数用例需要审视脚本本身（`test_alpha_release_gate` 检查
   `run_tdx_rolling_eval` 是否真调用了门禁），故也把 `scripts/` 加入。
2. **脚本的 `sys.path`**：原先位于根目录时，Python 会把脚本所在目录（即项目根）
   加入 `sys.path`，因此"碰巧"能导入库模块；下移后失效。
   - 8 个本就有 `sys.path.insert` 的脚本：改为指向**父目录**
   - 8 个没有的：补上引导（其中 `run_pipeline.py` 的引导必须整体放在
     `from __future__` 之后，否则 SyntaxError）
   - **这一步靠测试是发现不了的**——脚本无测试覆盖。本轮用
     「逐个 `--help` 冒烟」验证，16/16 可导入。
3. **`run_ci.py` 自身**：`step_syntax` 原只扫根目录 `*.py`，分层后会静默缩水。
   改为递归扫描（跳过缓存/版本库目录），覆盖面由 188 → **190**；
   `step_compat` 的路径同步更新为 `tests/test_python_compat.py`。
4. **CI 工作流**：`pytest test_python_compat.py` → `tests/test_python_compat.py`。
   这一处被 `test_run_ci.py` 的漂移守卫**当场抓出**——正是当初加它的目的。

**踩坑**：新建 `conftest.py` 时用了 `Set-Content -Encoding UTF8`，产出 **BOM + CRLF**，
同时触发 `test_line_endings_are_lf` 失败与 `run_ci.py` 语法检查报 `U+FEFF`。
已剥离 BOM 并确保 LF。

---

## 1.0 — 综合版本（2026-09-11）

由 `4.3`（功能基线，内部 v3.7）与 `v3.4_work`（工程优化）合并而成。详见 [MERGE_1.0_REPORT.md](MERGE_1.0_REPORT.md)。

**新增工程能力**
- 飞书凭据脱敏：文档硬编码 → 环境变量（`.env.example`）
- `run_daily_screening.py`：`shell=True` → 参数列表调用（防命令注入）
- `data_fetcher.py`：模块级 SSL context 复用、30s TTL 线程安全缓存、行情/K线并行取数、K线重试 1.5s→0.5s
- `data_fetcher.py`：**令牌桶限流器**（默认 8 req/s、突发 16，`FETCH_RATE_PER_SEC=0` 可关闭）
- `tracking.py`：`TrackingCosts` 交易成本模型（佣金 0.03% / 最低 5 元 / 印花税 0.05% / 滑点 0.05%），回测口径与 `walk_forward` 统一
- `ashare_factor_engine.py`：复权口径安全检查（`raw` / `tdx_local_raw` 触发告警）
- `log_utils.py`：统一结构化日志（`LOG_LEVEL` / `LOG_FILE`）
- `requirements.txt` / `requirements-dev.txt` / `ruff.toml` / `mypy.ini` / `pytest.ini`：依赖声明与质量工具基线
- `.github/workflows/ci.yml`：多 Python 版本矩阵 + lint + 类型检查 + 兼容性守卫 + 测试 + 凭据扫描

**静态分析发现的真实缺陷修复**
- **PEP 701 版本不兼容（严重）**：`agents.py` / `data_fetcher.py` 共 10 处 f-string 替换字段内复用外层同引号，
  该语法仅 Python 3.12+ 支持，导致项目在声明支持的 3.10 / 3.11 上直接 `SyntaxError`
- **`_I0` 未定义名**：`cycle_price_action.py` 的 `locate_cycle_phase` 抽取成模块时漏带常量定义
- **可变类属性共享**：`WorkflowOrchestrator.STAGES` 由 `list` 改为 `tuple`
- 清理 57 处死导入 + 19 处安全自动修复 + 10 余处类型标注补全

**质量基线**：`ruff` 零告警 · `mypy` 139 文件零错误 · `pytest` 141 通过

**巨石文件拆分**（对外 API 与产物字节级不变）
- `agents.py` 658 行 → `agents_base` / `agents_analysts` / `agents_researchers` / `agents_decision` + 门面
- `daily_stock_pick.py` 664 行 → `runtime_env` / `stock_scoring` / `pool_manager` / `industry_context` / `lark_notify` + 编排
- `report_generator.py` 1029 行 → `report_styles` / `report_markdown` + 生成器本体
- 新增 `test_module_splits.py`（17 用例）守护拆分兼容性

**拆分中发现的缺陷修复**
- **裸文件名崩溃**（4.3 遗留）：`save()` / `save_session()` 的 `os.makedirs(os.path.dirname(path))`
  在路径无目录部分时抛 `FileNotFoundError`，模块自带 `__main__` 演示即触发
- **`F821` 未定义名**：拆分 `daily_stock_pick` 时 `save_unified_report` 漏带 `import json`
- **`_I0` 悬空引用**：`stock_scoring` / `pool_manager` 抽取时漏带模块级常量（同类问题第 2、3 次）
- **行尾污染**：Windows 文本模式写入把 20 个文件变成 CRLF，已全部归一化为 LF 并加测试守卫

**回测口径缺陷修复（2026-09-12）**
- **【严重】tracking 收益率把「每股价格」当计费名义金额**：使 5 元最低佣金在 1500 元股价上
  被放大到 0.333%（应为 0.03%），每笔收益率偏差约 0.6 个百分点 —— 足以让正收益策略显示为亏损。
  改为以 `position_notional`（默认 10 万，与 `backtest_engine` 一致）为基准，成本率与股价解耦
- **【严重】`--gross` 开关完全失效**：`costs or TrackingCosts()` 把 `None` 赋回默认成本，
  导致"毛收益"实际仍扣费，且 CLI 仍打印"口径=毛收益"。改用显式 `apply_costs` 布尔参数
- **【中】`--dry-run` 会写入 tracking.db**：试运行推荐进入校准样本，污染胜率统计。已改为跳过持久化
- 新增 `test_tracking_costs.py`（14 用例）+ `test_dry_run_safety.py`（5 用例）守卫上述口径

**类型检查收紧 + 元数据修复（2026-09-12）**
- **启用 `check_untyped_defs`**：此前 mypy 只检查带标注的函数，未标注函数体（占多数）完全不查。
  启用后暴露 **31 个问题**并全部修复，现在 142 个文件零错误
- **KlineList 切片丢失元数据（潜在缺陷）**：`adjust` / `quality_ratio` / `data_quality`
  为运行时动态挂载，`__getitem__` 切片只复制 `source`。当前因读取方均用 `getattr` 兜底
  而不可达，但属静默降级风险。已声明为类属性并在切片时完整复制
- 修正 3 处**类型标注与实际结构不符**（`provider_router.errors` 实为 dict 列表、
  `tracking.by_bucket` 实为嵌套 dict）
- 新增 `test_kline_metadata.py`（6 用例）

**真实数据接入与首次实证（2026-09-12）**
- 新增 `tdx_csv_adapter.py`：通达信日线适配器。**关键是用 `code + market` 联合消歧**
  —— `000001` 在 sh 是上证指数、在 sz 是平安银行，仅按代码过滤会把指数当股票买入
- 新增 `build_tdx_dataset.py`：原始 CSV → 认证数据集（品种过滤 9,438→5,584 只真实股票、
  OHLC 清洗、sha256 元数据、PIT 股票池）
- 新增 `run_tdx_evaluation.py` + `repair_tdx_metadata.py`
- 新增 `TDX_DATA_ASSESSMENT.md`：数据性质评估，确认**两项严重缺陷**
  —— ① 幸存者偏差（抽样 15 只已知退市股，**全部缺失**）② 不复权价（13,696 行 >21% 跳空）
- 新增 `TDX_EVALUATION_REPORT.md`：**首次端到端真实数据实证**

**实证结论：`ALPHA_NOT_ESTABLISHED`**

| 指标 | 策略 | 沪深300 |
|------|------|---------|
| 样本外区间（652 交易日） | 2024-01-02 ~ 2026-09-10 | 同左 |
| 区间收益 | **-23.20%** | **+34.32%** |
| 年化收益 | -9.70% | +12.06% |
| 胜率 / 交易数 | 43.26% / 645 | — |
| 最大回撤 | 44.37% | — |
| 年化超额 | **-19.43%**（t=-1.19, p=0.233, bootstrap CI 跨零） | — |

**结论方向稳健**：数据集存在幸存者偏差（**高估**策略表现），即便在此偏乐观的数据上策略仍大幅落后。
统计上超额不显著，严格表述为「未能证明存在 Alpha」，而非「证明不存在 Alpha」。

**多窗口稳健性检验（新增 `run_tdx_rolling_eval.py`，2026-09-13）**

在 5 个样本外起点上重复评估**同一策略**（未调整任何参数）：

| 起点 | 对齐日 | 策略 | 基准 | 年化超额 |
|------|-------|------|------|---------|
| 2023-07-03 | 776 | -31.49% | +16.84% | -15.13% |
| 2024-01-02 | 652 | -15.71% | +34.32% | -16.23% |
| 2024-07-01 | 535 | -4.30% | +30.77% | -13.21% |
| 2025-01-02 | 410 | -16.14% | +19.06% | -19.77% |
| 2025-07-01 | 293 | -4.70% | +15.36% | -13.46% |

**5 个窗口全部负超额（0/5），中位数 -15.13%，区间 [-19.77%, -13.21%]** ——
负结果跨窗口稳定，排除单窗口偶然。基准 5 窗口全涨、策略 5 窗口全亏。

**失败机制已定位**：`walk_forward.score_history` 的构造决定了该策略是
**纯短期动量追高**（要求当日上涨 + 5 日趋势向上 + 突破前 5 日高点 + 换手活跃才买入，
T+1 开盘进场、持有 5 日）。这与 A 股显著的**短期反转效应**相悖。
胜率 43.26%、盈亏比 0.971 与该机制解释一致。**不是实现 bug，也不是调参能解决的问题。**

**因子假设检验（经济逻辑驱动，2026-09-13）**

新增 `factor_ic_lab.py`（横截面 IC 引擎）+ `run_factor_study.py` + `run_signal_diagnosis.py`。

**方法论**：用横截面 Spearman 秩 IC 而非组合回测。理由：幸存者偏差影响收益**水平**、
不影响**横截面排序**；秩相关还抗除权跳空离群值。每 5 日调仓 / 前瞻 5 日 / 无重叠。

**9 个经济假设，7 个获强支持（|t| ≥ 3.36）**：

| 因子 | IC均值 | t | 假设 |
|------|--------|---|------|
| `max_ret_20` | -0.0734 | **-7.64** | MAX 效应（Bali-Cakici-Whitelaw） |
| `log_amount_20` | -0.0697 | **-7.07** | 规模/流动性溢价 |
| `vol_20` | -0.0733 | **-6.03** | 低波动异象 |
| `ret_20` | -0.0549 | **-5.59** | 中期反转 |
| `vol_ratio` | -0.0346 | **-5.46** | 换手异象（Miller 1977） |
| `amihud_20` | +0.0387 | **+3.78** | 非流动性溢价（Amihud 2002） |
| `ret_5` | -0.0300 | **-3.36** | 短期反转 |

**因果闭环**：策略选股落在 `ret_5` 的 **0.863** 分位、`ret_20` 的 **0.801** 分位 ——
精确买在两个负 IC 因子的最差尾部。选股组合每期跑输全池 **0.53pp**（年化约 -27%，未扣成本），
与实测 -15%~-20% 年化超额方向一致。**策略失败由因子暴露决定，非运气。**

**两个结构性发现**：
1. 反转/波动类因子是**尾部效应**（Q1~Q4 全正，仅 Q5 转负）；
   规模与非流动性**严格单调**且价差最大（-0.763% / +0.565%）
2. 策略的波动率/规模/非流动性暴露**接近中性**（0.42~0.49）→
   **问题不是"买高波动股"，而是纯粹的动量追高**

**子期间稳定性**：两个互不重叠窗口（2021-08~2023-12 / 2024-01~2026-09）
6 个因子符号全部一致。

**尾部剔除实验（事前设定，2026-09-13）**

新增 `portfolio_backtest` 的 `candidate_filter` 钩子（**向后兼容**，默认 None 行为不变，
6 个测试守卫）+ `run_tail_exclusion_study.py` + `TAIL_EXCLUSION_REPORT.md`。

**3 个事前设定变体**（不扫参数、不改阈值、不改持仓周期）：

| 变体 | 修改 |
|------|------|
| V0 | 基线（对照） |
| V1 | 剔除 `ret_20` 最高 20% 的候选 |
| V2 | V1 + 剔除 `vol_ratio` 最高 20% |

**主口径结果（PIT 股票池，5 个窗口）**：

| 变体 | 年化超额均值 | 为正窗口 | 回撤均值 | 胜率均值 |
|------|------------|---------|---------|---------|
| V0 基线 | -15.56% | **0/5** | 38.97% | 43.91% |
| **V1** | **+4.40%** | **5/5** | **22.58%** | 47.90% |
| V2 | +8.44% | 5/5 | 15.81% | 51.89% |

**关键：做了两个股票池口径的对照（仅 54/400 重合），意外构成稳健性检验**

| 指标 | PIT 口径 | 全目录口径 | 一致性 |
|------|---------|-----------|--------|
| V1 超额改善 | +19.96pp | +3.37pp | ✅ 同号 |
| **V1 回撤改善** | **-16.39pp** | **-14.34pp** | ✅ **同号且幅度接近** |
| **V2 超额 vs V1** | **+4.04pp（更好）** | **-4.32pp（更差）** | ❌ **方向相反** |

- **可复现**：V1 优于 V0（超额/回撤/胜率三维度全部改善）；回撤降幅 14~16pp 最稳健
- **不可复现**：V2 的相对优劣随股票池**翻转** → 此前"叠加剔除有害"的结论**已撤回**

**成本拖累 25~36pp**（毛 17.7~73.8% → 净 -15.7~+39.5%）→ 策略对成本极度敏感，
毛收益无参考价值。

**重要限定**：因子与规则在同一数据上识别+验证，属**样本内结果**，不能作为策略有效性证据；
量级（V2 +8.44%）与数据的两项缺陷不相容。

**多股票池重复验证（2026-09-13，方法论关键一课）**

新增 `run_universe_replication.py` + `UNIVERSE_REPLICATION_REPORT.md`。

在 **3 个额外独立随机抽样**（共 6 组对照）上复现尾部剔除实验。
**分位阈值改为在完整 PIT 池（1,500 只）上定义**，避免样本内定义阈值。

| 种子 | 窗口 | V0 超额 | V1 超额 | 改善 | 回撤改善 |
|------|------|--------|--------|------|---------|
| 11 | 2024-01-02 | -17.29% | -17.78% | **-0.49pp** | -2.88pp |
| 11 | 2024-07-01 | -24.73% | -19.68% | +5.05pp | -11.60pp |
| 22 | 2024-01-02 | -6.06% | +1.47% | +7.53pp | -18.31pp |
| 22 | 2024-07-01 | **+8.14%** | +10.62% | +2.48pp | -6.62pp |
| 33 | 2024-01-02 | -27.82% | -16.05% | +11.77pp | -17.85pp |
| 33 | 2024-07-01 | -41.91% | -20.91% | +21.00pp | -21.68pp |

**汇总**：超额改善 5/6 为正（区间跨 21.5pp）；**回撤改善 6/6，均值 -13.16pp**。

**⚠️ 三处结论更正（此前表述已撤回）**

1. **"基线策略 5 窗口全负、负结果跨窗口稳定"** —— **撤回**。
   那 5 个窗口来自**同一股票池**且时间重叠，非独立观测。
   跨 4 个独立抽样后，V0 超额区间 **[−41.91%, +8.14%]，跨度 50.05pp，标准差 16.02pp**。
   "稳定跑输基准"不成立。
2. **"V1 能改善超额收益"** —— **收窄**。独立抽样下 1/6 为负，区间跨 21.5pp，不可依赖。
3. **"V2 叠加剔除有害"**（更早已撤回）—— 随股票池翻转。

**保留的唯一稳健结论**：剔除 `ret_20` 最高 20% 可**稳定降低最大回撤**
（三个独立来源一致：-13 ~ -16pp）。

**根因**：持仓仅 5 只、单仓 25% → **抽样噪声主导结果**。
一个具有真实稳健 Alpha 的策略不会因更换随机抽样而变动 50pp。

**下一步优先级调整**：**先解决持仓集中度**（改为 20~30 只、单仓 3~5%），
再重做全部实验 —— 否则结果仍会被抽样噪声淹没。

**持仓分散度研究（2026-09-13，转折点）**

新增 `run_concentration_study.py` + `CONCENTRATION_REPORT.md`。

既然多股票池验证证明「集中度是抽样噪声的根因」，直接验证之。
**只改集中度**，信号 / 阈值 / 持仓周期 / 成本模型全部不变。
3 个独立随机种子 × 300 只，窗口 2024-01-02。

| 变体 | 持仓/单仓 | 超额均值 | **标准差** | **区间跨度** | 回撤均值 | 交易数 |
|------|----------|---------|-----------|------------|---------|--------|
| C5（基线） | 5 / 25% | -30.39% | **14.22** | **33.89pp** | 48.40% | 612 |
| C10 | 10 / 10% | -20.45% | **1.15** | 2.81pp | 33.24% | 1,142 |
| **C20** | 20 / 5% | -14.68% | **1.03** | **2.24pp** | 21.68% | 1,903 |
| C30 | 30 / 3.3% | -12.74% | 2.69 | 6.32pp | **16.71%** | 2,392 |

**核心发现**：
1. **集中度确实是抽样噪声的根因** —— 5 只扩到 10 只，离散度降 **12 倍**
2. **分散后结果恢复可解释性** —— 标准差 1~3pp，小于典型效应量
3. **基线策略在分散配置下稳定跑输约 12~15%（年化）**
4. **回撤随分散度单调下降** —— 48.40% → 16.71%（**-31.69pp**）
5. **最优分散度在 C20 附近**；C30 略回升（小池过度分散带来新不稳定）

**代价**：交易数增加 **3.91 倍** → 成本敏感性加剧（此前测得成本拖累 25~36pp）。

**意义（转折点）**：此前噪声（33.89pp）远大于任何策略改进的效应量，
继续做策略实验无意义；现在噪声压到 1~3pp，**信噪比首次可用**。

**后续**：默认改用 **C20（20 只 / 单仓 5%）**；此前基于 C5 的结论
（尾部剔除降回撤、成本拖累幅度）需在分散配置下重新检验。

**v4.9 参考包选择性移植（2026-09-13）**

评估 `AI-Stock-God-Ashare-Unified-v4.9-...zip` 后执行方案 A（选择性移植）。

**关键判断**：1.0 与 v4.9 是**分歧分支，互不包含**。140 个共同模块中 80 个相同、
60 个不同（多为 1.0 更完整）。已核实 **v4.9 不含 1.0 的任何修复**：

| 1.0 的修复 | 1.0 | v4.9 |
|-----------|-----|------|
| `tracking.py` 成本口径修复 | 4 处 | **0 处** |
| `portfolio_backtest` 的 `candidate_filter` 钩子 | 3 处 | **0 处** |
| `data_fetcher` 的 `KlineList` 元数据修复 | 1 处 | **0 处** |

→ **不能整体切到 v4.9**，只移植 1.0 缺失的部分。

**移植内容（13 核心模块 + 2 研究脚本 + 12 测试）**：
- `survivorship_guard.py` + `release_gate.py`（替换，向后兼容）—— **代码级门禁**
- `corporate_actions.py`（替换 630B 桩 → 7KB 完整版，向后兼容）—— **除权调整层**
- `corporate_action_provider/ingest.py`、`pit_event_master/research_rows/trading_filter.py`
- `tdx_lifecycle.py`、`lifecycle_event_evidence.py`、`tdx_inventory.py`
- `public_daily_source.py`、`factor_blind_test.py`、`phase62_series.py`、`phase62_tdx_index.py`

**未移植（已记录原因）**：
- `phase60_reversal_stream.py` —— 依赖 Unix `sort`，Windows 不可用（实测失败）
- `phase62_reversal_*.py` / `phase63_reversal_robustness.py` —— 依赖 numpy/scipy，
  违反 1.0「核心管道零第三方依赖」原则。**但其结论已独立复现**

**适配改动（最小必要）**：`tdx_csv_adapter.py` 新增 `classify_instrument` 兼容别名
（v4.9 的 `tdx_inventory` 依赖该名，其同名适配器只有粗分类）；
另修 2 处 ruff + 2 处 mypy（均在移植代码内）。

**功能验证（实测）**：
- 门禁对当前 TDX 数据正确返回 `INCONCLUSIVE` / `SURVIVORSHIP DATA INCOMPLETE`
- 除权参考价 `(100-3)/1.2 = 80.8333` ✓，后复权因子 0.808333 ✓
- 向后兼容：`adjust_execution_price(100,{split_ratio:2,cash_dividend:3}) = 47.0` ✓

**交叉验证（本次评估最大收获）**：v4.9 的 PHASE59 在**同一份数据**上独立做了动量因子研究，
结果与我的因子研究高度吻合：

| 因子 | v4.9 RankIC | 我的 IC |
|------|------------|--------|
| 5 日动量 T+5 | **-0.03163** | **-0.0300** |
| 20 日动量 T+5 | **-0.05828** | **-0.0549** |

→ 我的因子结论通过独立实现验证。

**质量门禁对比**：

| 指标 | 移植前 | 移植后 |
|------|-------|-------|
| Python 文件 | 157 | **182** |
| ruff | All passed | **All passed** |
| mypy | 155 文件零错误 | **180 文件零错误** |
| pytest | 244 passed | **275 passed（+31）** |
| 行尾 | 全部 LF | **全部 LF** |

**无回退确认**：移植未触碰任何共同模块的实现（仅 `tdx_csv_adapter.py` 追加别名），
1.0 的全部工程加固保留。

**质量基线**：`ruff` 零告警 · `mypy` 180 文件零错误 · `pytest` 275 通过

**保留 4.3 的全部功能**：因子体系、PIT 加固、Stage2 打分、真实数据工作台（见下方 PHASE35–43）

---

## PHASE43 — 真实 A 股日线数据接入与价格因子侦察

把「按交易日一个 CSV、每行一个证券」的公开 A 股日线格式接入项目，提供适合 8GB 机器的流式价格因子侦察路径。

- 支持源格式：`symbol,date,open,close,high,low,volume,amount`
- 新增 `daily_csv_adapter.py`、`recon_price_factor_lab.py`

## PHASE41 — Real A-share Data Workbench

把认证过的历史行情文件与 PIT 股票池接成增量、内存受限的因子数据集。

- 硬边界：**绝不用今天的股票列表替代历史**
- 新增 `phase41_data_workbench.py`

## PHASE40 — PIT / 隐性数据泄漏加固

1. `walk_forward.py` 不再导入 `daily_stock_pick.py`，改依赖纯历史模块 `cycle_price_action.py`
2. 每日选股的 watchlist / candidate pool / pool state 外移到 `~/.ai-stock-god/`
3. 发布包不再携带静态股票池与运行日志
4. 缺外部 watchlist 时明确报错，**不回退**到项目内静态样例
5. 历史回测强制要求 PIT 股票池

- 新增 `pit_integrity.py`、`pit_universe_builder.py`
- 测试记录：101 passed（`PHASE40_PIT_TEST_REPORT.md`）

## PHASE39 — 因子经验验证执行链

把「候选因子注册 + 预筛门」接到可执行的经验验证链路：

1. 只验证数据中真实存在且达覆盖率门槛的因子
2. 用 `factor_validation.validate_factor`，严格按 t 日因子、未来 t+h 收益计算，避免未来函数
3. 输出 1/3/5/10/20 日的 IC、RankIC、ICIR、RankICIR、正 IC 比例、Top-Bottom spread 与胜率
4. 由 `factor_gate` 做 5 日预筛与高相关因子去冗余
5. 不填充、不伪造缺失数据，也不把工程测试结果包装成真实 Alpha

## PHASE38 — 候选因子池与证据门

在不盲目堆叠相关信号的前提下扩展因子搜索空间。

- `factor_registry.py`：24 个候选因子，覆盖动量、风险、流动性、估值、质量、成长、A 股特有事件/持仓
- 规则：只有具备真实 PIT 输入的因子才可参与验证；缺失源报 `missing_source`，**不做合成填充**

## PHASE37 — Stage-2 Alpha 消融实验框架

验证 Stage-2 的资金流、龙虎榜、微观结构、事件风险是否对 Stage-1 提供**独立增量信息**，而非仅因增加复杂度而「看起来更强」。

- 实验模型：`stage1` / `stage1 + flow` / … 逐层叠加
- 新增 `stage2_ablation.py`

## PHASE36 — A 股因子验证实验台

- `factor_validation.py`：轻量、无第三方依赖的截面因子验证器
- 严格按代码分组、按交易日排序；因子用 `t` 日观测值，收益只用 `t+1/3/5/10/20` 之后收盘价
- 输出 IC、RankIC、ICIR、RankICIR、IC 正向比例

## PHASE35 — Stage-2 Alpha 重排

让 Stage-2 的资金流、龙虎榜、涨跌停/炸板微结构与事件风险真正参与候选排序，而非仅作附加信息。

- `stage2_scoring.py`：对 Stage-1 候选做确定性横截面二次排序
- 正向：资金流均值、资金流为正比例、龙虎榜净买为正比例、龙虎榜净买总额、涨停高度
- 负向：跌停天数、炸板代理次数、高风险事件数量

## PHASE34 — 全市场两级筛选与可恢复批处理

把 AI 深度分析从「逐股调用」改成批处理流水线：

```
全A股数据快照 → 机器硬过滤 → 基础流动性/风险 → 截面多因子排序 → 300
  → 资金流/事件 → 50 → AI委员会 → 10~20 → 交易/风控
```

- 8GB 设计：JSONL 流式读取，不把全市场一次载入内存
- 断点续跑 + 流式 TopK

## PHASE33 — 8GB 运行时优化

在不牺牲 A 股数据约束、PIT 与交易规则的前提下，降低 8GB RAM 机器的峰值资源与等待时间。

- `runtime_profile.py`：`lite / balanced / full` 三档
- `balanced` 默认：4 并发、60 日因子窗口
- 前 6 个独立阶段并行；`review_committee → decision_trade → decision_risk` 串行
- 并发上限强制 ≤ 4

## PHASE32 — A 股资金与事件数据层

把「行情/技术」之外的 A 股特有信息变成可审计的结构化输入。

- 覆盖：资金流、龙虎榜、业绩预告/快报、解禁、股东交易、回购、其他公告
- 核心原则：点时态优先、数据语义不扩大、事件与价格分离、A 股交易约束优先、**缺失即缺失**
- 可选数据源：TuShare（`TUSHARE_TOKEN`）

## PHASE31 — V3 量化数据与 A 股执行结构

- **31.1**：板块识别（沪主板/深主板/创业板）、候选预筛增强，把研究系统锁定在 A 股真实交易约束上
- **31.0**：新增 A 股 Data Bus / Quant Skill / Deterministic Factor 架构层
- 新增 `v3_data_bus.py`、`quant_skill_router.py`、`provider_router.py`、`candidate_prefilter.py`

## PHASE30 — 专业评审委员会 + Crawl4AI 主链路

- Crawl4AI 从「独立模块」升级为 `data_fetcher → Fact Sheet → Agent` 可选主链路（`CRAWL4AI_ENABLED=1`）
- **7 席专业评审委员会**：量化研究员 / 基本面基金经理 / A股资深交易员 / 市场微观结构专家 / 首席风险官 / 数据点时态审计师 / 事件舆情研究员
- 交易员阶段自动接收委员会报告，避免只做「分析师平均分」
- 交易规则不再仅凭 `is_st` 硬编码 5%，优先要求逐日真实 `limit_ratio`

## PHASE26–27 — 端到端真实 Alpha 验证链

- `real_alpha_pipeline.py`：把严格认证的数据文件直接接入组合回测
- 每个数据文件运行前重新校验 metadata、认证标记、行数与 SHA-256；数据被改则拒绝继续
- 使用预先指定的 OOS 起点做时间顺序切分，禁止训练/样本外重叠
- 样本不足强制返回 `INCONCLUSIVE`
- Phase 27：用公开 GitHub CSV 数据（300750 宁德时代，2024-11-14 ~ 2025-03-11，77 行）实跑

## PHASE21–23 — Alpha 生存实验协议与真实数据纪律

- **诚实状态**：项目未打包足以支持最终 Alpha 结论的完整真实 PIT 长期数据集，故默认结论必须为 `INCONCLUSIVE`
- 预注册门槛：≥252 个完全样本外交易日、超额收益均值为正、Block Bootstrap 95% 下界 > 0、p < 0.05
- Phase 22：禁止凭模拟数据/当前股票池/未审计数据宣称 Alpha 存活
- Phase 23：TuShare Token 只经 `TUSHARE_TOKEN` 环境变量提供，绝不写入源码/JSON/日志

## PHASE14–20 — 数据质量、PIT 与风险预算

- **Phase 14**：`data_quality.py` — OHLC 完整性、日期顺序、重复日期、未来发布日期检查
- **Phase 15**：`corporate_actions.py` — 拆分/现金分红保守价格调整接口
- **Phase 16**：`risk_budget.py` — 逆波动率权重、单仓上限、HHI 集中度
- 其余阶段：治理、发布闸门、稳健性工具

## PHASE13 — 机构级验证升级

- PIT 股票池集成：组合回测可接收 `universe_snapshot_map`
- 基准分析：共同期策略/基准收益、超额收益、年化 alpha 代理、beta、信息比率
- 稳健性工具包：确定性 bootstrap、滚动训练/测试窗口、参数曲面
- 策略健康监控：回撤与连亏检测

## PHASE11–12 — 安全与交易真实性修复

- **密钥安全**：移除发布包真实 API Key，运行时优先读 `ARK_API_KEY` / `ARK_BASE_URL` / `ARK_MODEL`
- **成交真实性**：到期日遇一字跌停不再强制按收盘价成交，递延到首个可卖交易日
- Walk-Forward 采用相同的不可成交递延逻辑
- 新增防回归测试：跌停递延退出、未来数据隔离
- 组合回测改为按各股自身下一交易日执行 T+1；新增 20 日均额 ≥ 1 亿的流动性过滤

## PHASE10 — 系统集成版

把此前独立模块真正接入每日主流程：

1. 市场环境判断（STRONG / RANGE / WEAK）
2. 行业强度调整个股评分
3. 个股透明规则打分 + 周期阶段识别
4. 风控：建议仓位与风控说明，数据不足时安全降级
5. 推荐自动写入 `tracking.db`，后续 `run_tracking.py backfill` 回填真实表现
6. 统一日报 `reports/daily/screening_*.json`
7. 飞书多维表格写入 + 每日消息推送

## PHASE8–9 — 行业强度与回测验证

- **Phase 8**：`rank_industries(data, industry_map, as_of=日期)` — 输出 5/20/60 日收益、综合强度、排名与百分位
  - 关键约束：行业分类必须用**历史时点分类**，不能用今天的归属回填历史（避免幸存者偏差与分类漂移）
- **Phase 9**：回测验证框架

---

## 研究边界声明

本项目所有测试套件验证的是**工程机制与泄漏控制**，不等同于投资实证结论。

真实 A 股 Alpha 结论仍需要：认证过的历史全市场数据、历史 ST/停复牌/退市状态、公司行为与复权口径、基准数据、交易成本模型，以及预先登记的样本外评估区间。
