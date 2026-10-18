# CHANGELOG

AI股神团队 · A 股多 Agent 智能分析系统的版本演进记录。

> 本文件由 40+ 个 `PHASE*.md` 阶段文档归档合并而成（2026-09-11）。
> 原始阶段文档保留在 [`docs/archive/`](docs/archive/)，供追溯细节。

---

## Alpha 能力缺口补齐：P0 全 4 项 + P1 前 2 项（2026-09-19）

起点：[`ALPHA_CAPABILITY_GAP_ANALYSIS.md`](ALPHA_CAPABILITY_GAP_ANALYSIS.md) 指出项目
「验证 L3、其余 L1~L2」——**是精密的证伪机器，还不是 Alpha 生产机器**。
本轮执行其 P0（纯校准）与 P1（数据补齐）方案，详见
[`P0_P1_EXECUTION_REPORT.md`](docs/archive/P0_P1_EXECUTION_REPORT.md) 与
[`WORKLOG.md`](WORKLOG.md) 第十二节。

### P0（4/4 完成）

| 项 | 交付 | 实测结果 |
|----|------|---------|
| **等权全A基准** | `validation/benchmark.equal_weight_returns` + `run_tdx_rolling_eval` 第二基准 | 6/6 窗口 Δ **全为负**（中位 **−6.44pp**，区间 −1.33~−16.38pp）。等权超额中位 **−27.83%** vs 沪深300 的 −21.5%。**换基准后 2 个窗口从"不显著"变为"显著跑输"**（t −2.56 / −2.24） |
| **多重检验校正** | `validation/multiple_testing`（DSR/BH-FDR/Bonferroni/MinTRL/FWER）+ 审计脚本 | **8 个核心因子同时通过 BH 与 Bonferroni**；`dist_high_20` 降级为边缘；32 项检验的 FWER = **80.6%** |
| **因子正交化** | `factors/factor_ic_lab.orthogonalize_panel`（sequential + Löwdin） | 秩相关 **0.935 → 0.060**（sequential）/ **0.072**（Löwdin） |
| **ST 涨跌幅** | `exchange_rules.derive_limit_ratio` + 数据集 `limit_ratio` 列 + 加载层透传 `is_st` | **规则更正**：主板 ST 为**时变**（2026-07-06 前 ±5%、之后 ±10%） |

### P1（2 完成 / 2 受阻 / 1 待做）

* **P1-5 扩池至全A**：v3 **入选 5,667 只**（候选 5,807，短历史丢弃 140），在市覆盖 22.7% → **约 97.6%**。
* **P1-6 PIT 财务数据**：`fetch/fundamentals_source` + `pit/pit_fundamentals` +
  `scripts/fetch_fundamentals`。数据源 `stock_yjbb_em` 覆盖 **2016Q1~2026Q2（42 期）**。
  打开 `pb` / `roe` / `net_profit_growth` / `pe_ttm` 及新增 3 个因子。
* **P1-7 PIT 行业分类** ⛔ **受阻**：akshare 无行业变更历史接口 → 不产出伪 PIT 数据。
* **P1-8 指数成分历史** ⛔ **受阻**：免费源只给当前成分快照（`日期` 唯一值 2026-09-18）
  → 不产出伪历史成分表。替代方案 = 自建等权全A基准。
* **P1-9 数据集增量更新管线**：`scripts/update_certified_dataset.py`。
  前复权序列**不可盲目追加**（qfq 每次除权除息重新锚定）→ 用**重叠日校验**判定：
  偏差 ≤ 容差则追加、偏差 > 容差则**整体替换该股序列**、无重叠日则**不动并记入日志**。
  「无法判定」绝不当作「无需更新」。14 项测试覆盖三种判定分支。

### 额外修复的缺陷（4 个）

| # | 缺陷 | 性质 |
|:--:|------|------|
| 1 | 北交所 `920xxx` 被 `board_of` 误判为「其他A股」→ 涨跌幅 10% 而非 **30%** | 🔴 数据正确性（在线） |
| 2 | `load_certified_csv` 丢弃 `is_st` → P0-4 修复**无法生效** | 🔴 使修复失效 |
| 3 | `build_certified_dataset_v2.py` 引用未定义名 `prev_day` | 🟠 潜在 `NameError` |
| 4 | `_rows_iter` 闭包未绑定循环变量 `code` | 🟠 潜在串号 |
| 5 | **财务数据源公告日 88.4% 不可信**（2016-01~2025-06 系统性偏移 +1 年） | 🔴 数据质量（已用法定截止日兜底） |

### 质量基线

`python run_ci.py` **6/6 通过**：ruff All checks passed · mypy **264** 文件零错误（此前 237）·
pytest **795 项**（此前 538，+257）失败 0 错误 0 · 凭据扫描通过 ·
新增测试文件 8 个 · 清理今日早前遗留的 20 处 ruff 告警与 25 处 mypy 错误。
## 研究结论归档（2026-09-14 ~ 2026-10-02）

> **补记于 2026-10-02**：本文件自 09-14 起停更，其间约 25 个提交（含 7 项
> 实验判定）未进版本记录。按项目纪律「负面结果必须归档」，补记如下。
> **每项的原始 JSON 证据见 [`reports/EVIDENCE_INDEX.md`](reports/EVIDENCE_INDEX.md)。**

### 负面结论（项目一半以上的资产，优先归档）

| 提交 | 实验 | 判定 | 预注册 | 结论文档 |
|---|---|---|---|---|
| `eb37509` | H-C1 复合反转 vs 沪深300 | ❌ **无 Alpha** | `ALPHA_HYPOTHESIS_PREREG.md` | `CONTRARIAN_HYPOTHESIS_REPORT.md` |
| `ea69623`~`eb37509` | 组合层 A/B 三阶段 | ❌ 未证出超额 | `PORTFOLIO_AB_PREREG{,_2,_3}.md` | `PORTFOLIO_AB_REPORT{,_2,_3}.md` |
| `c14d8c9` | H-F4 组合层五因子 | ❌ 1/5 窗口、Δ中位 −2.80pp | `FIVE_FACTOR_PREREG.md` | `STEP1_3_EXECUTION_REPORT.md` §18 |
| `ecdf625` | H-IC-DECAY | ⚠️ IC 虚高，衰减 16.75% | `IC_DIAGNOSIS_PREREG.md` | 同上 §二十 |
| `3b44d22` | Sequoia-X 六形态 | ❌ **不需要**（3/6 高冗余） | ⚠️ 无独立预注册 | `FORM_SCREEN_VERDICT.md` |
| `cbd918b` | N1 次新股偏好 | ❌ **不必要**（打分池次新 0.50%） | `CANDIDATE_FILTERS_PREREG.md` | `CANDIDATE_FILTERS_VERDICT.md` |
| `67dd619`~`4ef95e7` | N3 信号日涨停过滤 | ❌ **冗余**（5/5 窗口 Δ 全 +0.00pp） | 同上 | 同上 |

### 正面 / 存续结论

| 提交 | 实验 | 判定 |
|---|---|---|
| `ecdf625` | H-FACTOR-SUBSET（V2 组合层） | ✅ **有效**（5/5，Δ中位 +3.12pp） |
| `ecdf625` | H-IC 衰减五档 | ✅ 登记有效（0.0514→0.1302） |
| `c14d8c9`~ | H-T1 降换手 | ✅ +4.27pp |

### 工程与产品化

| 提交 | 内容 |
|---|---|
| `ecdf625` | TDX 原生推荐系统初版（`tdx_native/`） |
| `d7625ff` | 名称表 / 跟踪回填 / 一键运行 / 自选股导出 |
| `dbb198a` | 恢复质量门禁（ruff 51→0、mypy 57→0）+ tdx_native 40 项守卫测试 |
| `a0050f7` | 计划任务 TDXDaily 上线 + 运维手册 |
| `af21506` | 到期卖出提示（15 天逾期窗口） |
| `214fa4e` | 数据完整性预检 + 修卖出提示漏报 |
| `7d8722c` | 跟踪基准改为全市场等权 ⚠️ **证据不足，10-02 已撤回数字** |
| `5da770b` | `AGENTS.md` 项目说明书 |

### 2026-10-02 独立审计

见 [`AUDIT_2026_10_02_REPORT.md`](AUDIT_2026_10_02_REPORT.md)。修了 5 处静默失效
（顺延持仓漏报卖出、停牌误杀、复权误判、V2 死代码、bat 吞错误码），
放行 59 份研究证据入库，撤回 1 个基于冒烟数据的结论。

---

## 待办 #1/#2 处置与本地 CI 修复（2026-09-14）

承接 [`HANDOVER.md`](HANDOVER.md) 第五节待办清单。详见
[`MODULE_SPLIT_EVALUATION.md`](MODULE_SPLIT_EVALUATION.md)。

### 待办 #1：`crawl4ai_fetcher.py`（370 行）→ **结论：不拆**

按项目自身的拆分标准（WORKLOG 第六节）逐项核对后判定**不拆**：

1. **单一职责** —— 全模块只做一条流水线（抓 URL → 清洗 → 输出 news 列表）。
   内部分组是**同一流水线的阶段**，不是独立职责；与 `tracking.py`（成本模型 +
   持久化 + 统计）和 `data_fetcher.py`（传输 + 行情 + K线 + 新闻）有本质区别。
2. **拆分会让认知负担上升** —— 从"读一个文件就懂流程"变成"拼 5 个文件才还原流程"。
3. **叶子节点** —— 全仓库仅 2 处引用，拆分不改善任何调用方的负担。
4. **关键逻辑已有测试** —— PIT 相关的 `_before_cutoff` 与去重均有断言。

顺带核实：`requirements-crawl4ai.txt` 确实存在（错误提示非笔误）。

### 待办 #2：`main.py`（402 行）→ **已补冒烟 + 已拆分去重**

**前置条件「需先补冒烟」已完成**：新增 `tests/test_main_smoke.py`（**15 项**），
覆盖输出安全（含越界进度条）、输入契约（重试/放行/EOF 干净退出）、
`ask_yes_no` 全组合解析、`main()` 控制流（新建/续跑/未完成/飞书失败）。
**不触发**任何 LLM 调用或网络请求。

**评估发现：真正的缺陷不是"文件大"，而是重复** —— 三个 `run_*_team` 合计 164 行，
结构约 90% 相同，差异仅在阶段列表与提示文案。任何修复都要写三遍。

**处置**：新增 `console/` 包

| 模块 | 职责 |
|------|------|
| `console/display.py` | 终端颜色、打印辅助、输入辅助（纯展示/交互） |
| `console/teams.py` | 阶段规格 `StageSpec` + 统一执行器 `run_team` |

`main.py` **402 → 169 行**，通过门面重导出保持全部既有符号可用。
三个团队函数从 164 行收敛为 3 个一行包装 + 一个 46 行统一实现。

行为保持：阶段顺序/文案/路径/进度/提交时机逐项核对一致。
唯一防御性改动：`reports/` 目录改为**无条件**创建。

### 发现并修复的缺陷

**① 包名冲突：`cli` 已被 `fetch/cli.py` 占用**（守卫拦截）

首次命名为 `cli/`，结构守卫 `test_no_bare_legacy_imports` 立即失败。
根因是 `fetch/cli.py` 的模块名与新建顶层包同名。**处置**：改名 `console/`。

> 与 HANDOVER 踩坑第 1 条同源（包名不能与既有顶层模块同名），
> 区别是这次被守卫**在提交前**拦下，未流到运行期。

**② `run_ci.py` 工具解析缺陷 —— 本地 CI 一直不可用**

`_module()` 固定用 `sys.executable -m <tool>`，而 ruff/mypy 装在**隔离 venv**，
系统 Python 里没有 → 本地 CI 因**环境**原因假失败（ruff / mypy 两步必然失败）。

**处置**：增加回退链 —— ① 当前解释器模块 → ② `WORKBUDDY_PY_ENV`
→ ③ 两个已知 venv 路径 → ④ `PATH`；全部落空时**明确报错并返回非零**。

**结果：本地 CI 6/6 全部通过。**

### 质量基线

| 指标 | 交接时 | 现在 |
|------|-------:|-----:|
| 根目录 `.py` | 59 | 59 |
| 子包数 | 18 | **19**（+`console`） |
| pytest | 470 passed + 1 skipped | **502 passed** |
| mypy | 219 文件 | **223 文件** |
| 本地 CI | ruff/mypy 两步失败 | **6/6 通过** |

---

## 复权数据接入与因子对比（2026-09-14）

### 新增能力

- **`scripts/fetch_corporate_actions.py`** —— 从东方财富数据中心
  `RPT_SHAREBONUS_DET` 抓取 A 股分红送股数据（公开接口，无需凭据）。
  输出 CSV 与 `corporate_action_ingest` 的摄入格式兼容。
  实测抓取 **21,212 条记录、覆盖 4,741 只股票**（池内覆盖率 88.1%）。
- **`corporate.corporate_action_provider.consolidate_actions()`** —— 合并同一
  `(代码, 除权日)` 的**多报告期**分红方案。
  必要性：实测 7 组记录属此情形（如 `600720 20240613` 同时实施 2023 与 2022 年报分红），
  对价格复权而言当日影响是**合计**的现金与送转。配套 **10 个测试**。
- **`scripts/run_adjusted_factor_study.py`** —— 复权 vs 原始价格的因子对比。

### 核心发现：预测未获支持

此前预测"复权后反转因子 \|IC\| 应当下降"（因假下跌被人为放大）。
**实测不成立**：

| 反转因子 | 原始 \|IC\| | 复权 \|IC\| | 变化 |
|---------|-----------|-----------|------|
| `ret_1` | 0.0046 | 0.0055 | 上升 |
| `ret_5` | 0.0300 | 0.0287 | 下降 0.0014 |
| `ret_20` | 0.0549 | 0.0543 | 下降 0.0005 |

全部 10 个因子中 **3 个 \|IC\| 下降、7 个上升**；
**最大 \|IC\| 变化仅 0.0030（最大 \|IC\| 的 4.1%）**；显著性结论完全不变。

**原因**：除权事件仅占全部观测的 **0.315%**（5,860 / 1,860,000），
而 Spearman 秩相关只看排序、对少数离群值稳健。

### 精确结论

> **复权修正收益水平（绝对值），但不改变横截面排序（相对值）。**

分位组收益水平全部上移（Q5 上移最多，约 +0.07~0.09pp/5日），
这正是"假下跌被移除"的体现；但 Q5-Q1 价差几乎不变。

### 认知修正

| 此前表述 | 修正后 |
|---------|--------|
| 不复权价"污染趋势类信号"，是严重缺陷 | **缺陷存在，但对横截面因子结论影响 <5%** |
| 复权是补齐数据缺口的前置条件 | 仍是**工程正确性**要求，但**不是**因子结论可信度的主要威胁 |

**优先级排序调整为：幸存者偏差 >> 不复权价。**

复权仍重要的场景（不受本结论影响）：回测绝对收益、长周期复利、
单只股票价格连续性（涨跌停判定）、事件研究窗口。

📄 详见 [`ADJUSTED_FACTOR_REPORT.md`](docs/archive/ADJUSTED_FACTOR_REPORT.md)

**质量基线**：`ruff` 零告警 · `mypy` 219 文件零错误 · `pytest` 481 passed + 1 skipped

---

## 1.0 · 第四轮收紧（2026-09-13）

> 承接 1.0 的「遗留事项」清单逐条推进（详见 [MERGE_1.0_REPORT.md](docs/archive/MERGE_1.0_REPORT.md) 第六节）。
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

## 1.0 · 目录分层第二轮 —— 库模块分包（2026-09-13）

**背景**：第一轮把测试与脚本迁走后，根目录仍有 114 个库模块平铺。
上轮末「留待后续按家族逐个推进」的部分在本轮完成。

**选型依据（不是按目录感觉，而是按依赖图）**：用 AST 建全仓库 import 图，
统计每个候选家族的**外部入边**（谁 import 它）与**外部出边**（它 import 谁），
按耦合从低到高依次下沉：

| 子包 | 模块数 | 外部入边 | 外部出边 | 生产侧引用方 |
|------|-------|---------|---------|-------------|
| `pit/` | 5 | 9 | **0** | `phase41_data_workbench`、`real_alpha_pipeline` |
| `tdx/` | 3 | 3 | **0** | `build_tdx_dataset` |
| `corporate/` | 3 | 6 | **0** | `scripts/run_adjusted_factor_study` |
| `ashare/` | 6 | 23 | **0** | `data_fetcher`、`screen_pipeline`、`stage2_enrichment`、`v3_data_bus` 等 9 个 |
| `factors/` | 6 | 12 | 2 | 5 个研究脚本 + `stage2_ablation` |

根目录 `.py`：**114 → 91**（累计 188 → 91，-52%）。

**导入约定**：子包内同族引用用**相对导入**（`from .pit_event_master import ...`），
包外一律**绝对导入**（`from pit.pit_integrity import audit_pit_rows`）。
相对导入使整包可整体改名/移动而不必改内部 import。

**为什么文件名不去掉前缀**：`git mv` 保持可追溯的重命名检测；改动纯机械
（只重写 import 路径），diff 易审、易回滚。代价是 `pit.pit_integrity` 读起来
略有冗余，可接受。

**`agents_*` 刻意不动**：根目录已有门面 `agents.py`，再建 `agents/` 包会
产生同名冲突与导入歧义。这条理由已写进守卫测试，避免后来者误判为遗漏。

**新增 `tests/test_package_layout.py`（35 例）**，把分层约定固化成断言：

1. 每个子包有 `__init__.py` 且有包级 docstring（说明「管什么 + 共同红线」）
2. 已下沉模块**不得**在根目录留平铺副本 —— 两套导入路径并存是最难查的失效
3. 全仓库**不得**再有裸的旧顶层导入（`from pit_integrity import ...`）
4. 子包内同族引用必须是相对导入
5. 每个包及其模块**真实可导入** —— 目录建了但 import 断了是最常见的假分层
6. `agents_*` 保持平铺（把「不做什么」的原因固化下来）

**本轮发现的真实缺陷**

| # | 缺陷 | 发现方式 | 处置 |
|---|------|---------|------|
| 1 | `scripts/run_daily_screening.py` 把 `argv[1]` 直接当股票 JSON，`--help` 被当成数据去 `json.loads`，报「STOCKS_DATA 不是合法 JSON」 | 分包后重跑 16 个脚本的 `--help` 冒烟 | 显式先处理 `-h/--help` 并打印用法；定时任务的既有调用方式不受影响 |

**质量基线**

| 指标 | 本轮前 | 本轮后 |
|------|-------|-------|
| 根目录 `.py` | 114 | **91** |
| 语法 / mypy 覆盖 | 190 文件 | **196 文件**（+5 个包 `__init__.py`、+1 个新测试） |
| 子包数 | 0 | **5**（含 23 个模块） |
| pytest | 356 | **391 passed, 1 skipped**（+35 守卫） |
| 脚本 `--help` 冒烟 | 16/16 | **16/16** |
| 本地 CI | 6/6 PASS | **6/6 PASS** |

---

## 1.0 · 目录分层第三轮 —— 报告 / 运行时 / 风险 / 验证（2026-09-13）

第二轮之后根目录仍有 91 个库模块。本轮再下沉四个家族：

| 子包 | 模块数 | 外部出边 | 外部入边（生产） | 说明 |
|------|-------|---------|----------------|------|
| `reporting/` | 3 | 1（`orchestrator`） | 1（`main`） | 报告生成器三件套（含最大的 501 行 `report_generator`） |
| `runtime/` | 2 | **0** | 6 | 运行环境 + 8GB 资源画像 |
| `risk/` | 4 | **0** | 3 | A 股风控 / 组合引擎 / 仓位预算 / 流动性 |
| `validation/` | 8 | 1（`data_quality`） | 0 | 绩效 / 基准 / bootstrap / 稳健性 / 压力 / 红队 / 健康度 |

根目录 `.py`：**91 → 74**（累计 188 → 74，**-61%**）。
九个家族共 40 个模块已入包。

**两处值得记录的处理**

1. **`validation/` 的边界不是按前缀划的。** `validation_suite` 依赖
   `performance` 与 `phase13_risk`，所以这三个必须同包；
   否则包内会留下指向根目录的导入，等于把耦合搬了个位置而已。
   划包时先看依赖边，再看名字。
2. **守卫测试的判定方式从「前缀」改为「模块名」。** `risk/` 里的
   `a_share_risk` / `liquidity` / `risk_engine` 没有共同前缀，
   按前缀判定会漏检平铺副本与裸导入。现由 `PACKAGES` 单一来源推导出
   已迁移模块名全集，两类检查都基于它。

**本轮发现的真实缺陷**

| # | 缺陷 | 发现方式 | 处置 |
|---|------|---------|------|
| 1 | `tests/test_module_splits.py` 用**字符串字面量**硬编码源码路径（`open("runtime_env.py")`）与模块名，分包后 `FileNotFoundError` / `ModuleNotFoundError` | 全量 pytest | 改为从模块对象取 `__file__`（`open(_runtime_env.__file__)`），使测试不再与文件位置耦合 |

> 教训：前两轮排查"动态引用"时只搜了 `import_module` / `importlib` /
> `__import__` / `importorskip`，**漏了 `open("xxx.py")` 这类以源码文件为
> 对象的引用**。它们同样是隐式的路径耦合。

**剩余的风险点（刻意未动）**

`data_fetcher`（807 行，13 个生产引用方）、`real_*`（8 条出边）、
`daily_*`（9 条出边）、`agents_*`（与门面 `agents.py` 同名冲突）——
这些要么入边过多、要么出边过多，收益不抵改动风险。

**质量基线**

| 指标 | 本轮前 | 本轮后 |
|------|-------|-------|
| 根目录 `.py` | 91 | **74** |
| 子包数 | 5 | **9**（含 40 个模块） |
| 语法 / mypy 覆盖 | 196 文件 | **200 文件** |
| pytest | 391 | **415 passed, 1 skipped**（+24 守卫） |
| 脚本 `--help` 冒烟 | 16/16 | **16/16** |
| 本地 CI | 6/6 PASS | **6/6 PASS** |

---

## 1.0 · 目录分层第三轮 —— 报告 / 运行时 / 风险 / 验证（2026-09-13）

第二轮之后根目录仍有 91 个库模块。本轮再下沉四个家族：

| 子包 | 模块数 | 外部出边 | 外部入边（生产） | 说明 |
|------|-------|---------|----------------|------|
| `reporting/` | 3 | 1（`orchestrator`） | 1（`main`） | 报告生成器三件套（含最大的 501 行 `report_generator`） |
| `runtime/` | 2 | **0** | 6 | 运行环境 + 8GB 资源画像 |
| `risk/` | 4 | **0** | 3 | A 股风控 / 组合引擎 / 仓位预算 / 流动性 |
| `validation/` | 8 | 1（`data_quality`） | 0 | 绩效 / 基准 / bootstrap / 稳健性 / 压力 / 红队 / 健康度 |

根目录 `.py`：**91 → 74**（累计 188 → 74，**-61%**）。
九个家族共 40 个模块已入包。

**两处值得记录的处理**

1. **`validation/` 的边界不是按前缀划的。** `validation_suite` 依赖
   `performance` 与 `phase13_risk`，所以这三个必须同包；
   否则包内会留下指向根目录的导入，等于把耦合搬了个位置而已。
   划包时先看依赖边，再看名字。
2. **守卫测试的判定方式从「前缀」改为「模块名」。** `risk/` 里的
   `a_share_risk` / `liquidity` / `risk_engine` 没有共同前缀，
   按前缀判定会漏检平铺副本与裸导入。现由 `PACKAGES` 单一来源推导出
   已迁移模块名全集，两类检查都基于它。

**本轮发现的真实缺陷**

| # | 缺陷 | 发现方式 | 处置 |
|---|------|---------|------|
| 1 | `tests/test_module_splits.py` 用**字符串字面量**硬编码源码路径（`open("runtime_env.py")`）与模块名，分包后 `FileNotFoundError` / `ModuleNotFoundError` | 全量 pytest | 改为从模块对象取 `__file__`（`open(_runtime_env.__file__)`），使测试不再与文件位置耦合 |

> 教训：前两轮排查"动态引用"时只搜了 `import_module` / `importlib` /
> `__import__` / `importorskip`，**漏了 `open("xxx.py")` 这类以源码文件为
> 对象的引用**。它们同样是隐式的路径耦合。

**剩余的风险点（刻意未动）**

`data_fetcher`（807 行，13 个生产引用方）、`real_*`（8 条出边）、
`daily_*`（9 条出边）、`agents_*`（与门面 `agents.py` 同名冲突）——
这些要么入边过多、要么出边过多，收益不抵改动风险。

**质量基线**

| 指标 | 本轮前 | 本轮后 |
|------|-------|-------|
| 根目录 `.py` | 91 | **74** |
| 子包数 | 5 | **9**（含 40 个模块） |
| 语法 / mypy 覆盖 | 196 文件 | **200 文件** |
| pytest | 391 | **415 passed, 1 skipped**（+24 守卫） |
| 脚本 `--help` 冒烟 | 16/16 | **16/16** |
| 本地 CI | 6/6 PASS | **6/6 PASS** |

---

## 1.0 · 目录分层第四轮 —— 七个库模块家族下沉为子包（2026-09-13）

第三轮之后根目录仍有 74 个库模块。本轮用与二/三轮相同的依赖图方法
（AST 建 import 图，按「外部出边」排序），再找出 7 个**内部闭合**的家族下沉，
根目录 74 → **59**（累计 188 → 59，−69%）。

| 子包 | 模块数 | 外部出边（到根目录其他模块） | 说明 |
|------|:---:|:---:|------|
| `stage2/` | 3 | 0 | Stage-2 消融 / 富集 / 打分 |
| `alpha/` | 2 | 0 | alpha 实验 + 存活实验室 |
| `phase62/` | 2 | 0 | v4.9 移植的 PHASE62 TDX 指数 |
| `regime/` | 2 | 0 | 市场状态回测报告 / 验证 |
| `tushare_client/` | 2 | 0 | TuShare 接入（原名 `tushare/`，因遮蔽第三方库已改名） |
| `notify/` | 2 | 0 | 飞书 / Lark 通知 |
| `router/` | 2 | 0 | provider / quant_skill 路由 |

「内部闭合」指这些家族的成员**不反向 import 根目录其他模块**（出边只指向已入包模块或各自包内），
因此下沉不会制造「包 → 根」的反向依赖。

**两处值得记录的处理**

1. **守卫测试判定的单一来源继续生效。** `test_package_layout.py` 的
   `PACKAGES` 增加这 7 个包后，`test_no_flattened_copies_in_root` 与
   `test_no_bare_legacy_imports` 自动覆盖新模块——无需为它们单独写断言。
2. **又一处字符串动态引用。** `tests/test_module_splits.py` 用
   `importlib.import_module("lark_notify")` 动态加载，裸改名会漏。
   本轮把 `"lark_notify"` → `"notify.lark_notify"`（同一列表里还出现在
   `forbidden` 依赖方向断言中），并把这类 `open("x.py")` / `import_module("x")`
   的隐式路径耦合纳入改名脚本的排查范围。

**本轮发现的真实缺陷**

| # | 缺陷 | 发现方式 | 处置 |
|---|------|---------|------|
| 1 | `tests/test_module_splits.py` 用 `importlib.import_module("lark_notify")` 动态加载，`notify/` 改名后裸名失效 | 全量 pytest（ModuleNotFoundError） | 改为 `import_module("notify.lark_notify")`，`forbidden` 列表同步更新 |
| 2 | **【严重】新建 `tushare/` 包遮蔽了第三方 `tushare` 库**：`import tushare as ts; ts.pro_api()` 解析到本项目空包而非真实依赖 → 运行期 `AttributeError`。影响 3 个文件（含 `corporate/corporate_action_provider.py`，说明遮蔽是全局生效的） | **远端 CI 的 mypy**（本机当时未装 mypy；pytest 与守卫测试均未捕获——惰性导入且只在调用时触发） | 包重命名为 `tushare_client/`；新增守卫 `test_no_bare_import_of_package_names` |

**剩余的风险点（刻意未动）**

`data_fetcher`（807 行，13 个生产引用方）、`agents`/`agents_*`（与门面 `agents.py` 同名冲突）、
`real_*` / `daily_*`（出边过多）仍留在根目录——收益不抵改动风险。

**质量基线**

| 指标 | 本轮前 | 本轮后 |
|------|-------|-------|
| 根目录 `.py` | 74 | **59** |
| 子包数 | 9 | **16**（含 55 个模块） |
| pytest（本地） | 415 passed, 1 skipped | **456 passed, 1 skipped** |
| 语法 / mypy 覆盖 | 200 文件 | **200 文件**（ruff/mypy 本机未装，由远端 CI 覆盖） |
| 脚本 `--help` 冒烟 | 16/16 | **16/16** |
| 本地 CI | ruff/mypy 本机未装，由远端 CI 覆盖 | 同左 |

> **备注（本轮最重要教训）**：本机隔离 venv（`~/.workbuddy/binaries/python/envs/default`）
> 内**已装有 ruff / mypy**，分包这类改动必须在本地跑完整 CI 再推送。
> 本轮最初只跑了 pytest 与 `py_compile` 就推送，结果 `tushare/` 遮蔽第三方库的缺陷
> （见缺陷 #2）是**远端 CI 的 mypy** 抓出来的 —— 白跑一轮 CI，且该缺陷是运行期
> `AttributeError`，pytest 根本抓不到。
> 现已补守卫 `test_no_bare_import_of_package_names`，并恢复本地 mypy/ruff 校验。

---

## 巨石拆分 · `data_fetcher.py`（807 行）→ `fetch/` 包 + 门面

延续 1.0 对 `agents.py`(658) / `daily_stock_pick.py`(664) / `report_generator.py`(1029)
的既有门面拆分模式，处理最后一个巨石 `data_fetcher.py`（807 行，全项目入边最多）。

| 子模块 | 职责 | 行数 |
|--------|------|-----:|
| `fetch/transport.py` | HTTP 传输：SSL 复用 / 内存缓存 / 令牌桶限流 / 统一 GET | 141 |
| `fetch/common.py` | 公共常量与纯函数（字段表、代码规范化、数值解析、日期工具） | 132 |
| `fetch/quote.py` | 实时行情（东财 + 腾讯兜底） | 148 |
| `fetch/kline.py` | 历史日K（东财 / 腾讯 / 通达信本地，不复权） | 264 |
| `fetch/news.py` | 新闻与事实数据包（含 Crawl4AI 可选增强） | 249 |
| `fetch/cli.py` | 命令行入口 | 47 |
| `data_fetcher.py` | **门面**，重新导出 29 个符号 | 102 |

**依赖方向无环**：`transport`/`common` → `quote`/`kline` → `news` → `cli`。

**做法（保证可审计）**
- 用 AST 行区间**机械抽取**，不手工誊抄 —— 实现代码字节级不变。
- 跨组依赖由**实际引用**推导（不是"全部互导"），因此不成环。
- 各子模块先带上完整导入，再由 `ruff --select F401 --fix` 裁掉未使用项（共裁 82 处）。

**等价性验证**
- 顶层符号 34 个：**无重复、无丢失**（脚本对比拆分前备份）。
- 对外 API：12 个公开名全部可达，关键函数签名逐一比对一致。
- ruff 全通过；mypy **214 文件零错误**；pytest **457 passed**（exit 0）；CLI 冒烟通过。

**唯一需要适配的地方（门面拆分的固有代价）**
`tests/test_crawl4ai_adapter.py` 原先用 `patch.object(data_fetcher, "_crawl4ai_fetch_news_sync", ...)`
打补丁。拆分后该实现位于 `fetch/news.py`，函数从**自己模块**的全局读取该名字，
因此补丁必须打到实现所在模块 —— 已改为 `patch.object(news, "_crawl4ai_fetch_news_sync", ...)`。
> 教训：**monkeypatch 要打在"名字被查找的那个模块"上**。门面只能保证
> `from data_fetcher import X` / `data_fetcher.X` 仍然可用，不能让补丁穿透到子模块内部。

**新增**：`DIRECTORY_LAYOUT.md` —— 由 `gen_layout_doc.py` 从真实仓库状态生成
（17 个包 / 61 个入包模块 / 根目录 59 个的分类与留根理由），避免文档与结构漂移。

---

## 巨石拆分 · `tracking.py`（308 行）→ `track/` 包 + 门面

高耦合核心中下一个可安全分解的目标（`import tracking` + `tracking.X(...)` 被
`daily_stock_pick` / `run_analysis` / `run_tracking` / 测试广泛使用）。

| 子模块 | 职责 | 行数 |
|--------|------|-----:|
| `track/costs.py` | 交易成本模型（TrackingCosts）与净收益率换算 | 69 |
| `track/schema.py` | 常量与表结构（默认库路径、建表语句、立场映射） | 50 |
| `track/store.py` | SQLite 持久化（连接 / 建表 / 写入 / 查重 / 列举） | 72 |
| `track/stats.py` | 校准统计（命中判定 / 回填 / 胜率与平均收益） | 167 |
| `tracking.py` | **门面**，重新导出 17 个符号 | 74 |

依赖无环：`costs`/`schema` → `store` → `stats`。

**本轮最重要的坑：`_DB_PATH` 会静默搬家**
`_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tracking.db")`
—— 一旦实现下沉到子包，`__file__` 变成 `<root>/track/schema.py`，数据库路径会
悄悄从 `<root>/tracking.db` 迁到 `<root>/track/tracking.db`。
**后果是旧记录"消失"且不报任何错**，属典型静默失败。
处置：表达式改为取两层父目录（包位于项目根下一层），并新增守卫
`test_db_path_stays_at_project_root` 断言其仍指向项目根。
> 教训：拆分时凡是用 `__file__` / 相对路径定位资源（数据库、配置、数据目录）的
> 常量，都必须重新核对落点并加守卫 —— 这类问题类型检查和测试通常都抓不到。

**验证**
- 顶层符号 17 个经门面全部可达；`_DB_PATH` 实测仍为 `<root>/tracking.db`。
- ruff All checks passed / mypy **219 文件零错误** / pytest **470 passed**（exit 0）。
- 全景图重新生成：18 个包 / 65 个入包模块 / 根目录 59 个。

**刻意未动**：`orchestrator.py`（312 行）—— 其核心是**一个 278 行的类**，
拆类需改为 mixin 组合；1.0 对 `report_generator.py` 做过同类评估，结论是
「收益递减」（只是把方法换个文件，认知负担未降），故本轮不拆。

---

## 1.0 — 综合版本（2026-09-11）

由 `4.3`（功能基线，内部 v3.7）与 `v3.4_work`（工程优化）合并而成。详见 [MERGE_1.0_REPORT.md](docs/archive/MERGE_1.0_REPORT.md)。

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


> ⚠️ **基线口径注（2026-10-18）**：本表数值为旧基线产物（2026-10-17 前代码口径）。2026-10-17 已按新基线全量重算 80 份（main `8db1c65` / copy `2b9f97d`→`da7f6ac`），新值见 `reports/_recalc/`；差异已 100% 归因为 D2 代码基线演进（非印花税修复）。详见 `_AI协作信箱/02_回执/成本口径重算副本侧15跨线窗口验收_主干_2026-10-17.md` §二十。

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
