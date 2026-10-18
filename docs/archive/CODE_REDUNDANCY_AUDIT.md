# 代码冗余审计报告（CODE_REDUNDANCY_AUDIT）

**日期**：2026-10-13 · **范围**：本仓库（海外版/副本）全部 git 跟踪 Python
**工具**：`scripts/audit_code_redundancy.py`（只读，AST 归一化重复检测）
**基线守卫**：`tests/test_code_redundancy_baseline.py`（新增完全重复不过评审无法入库）

---

## 0. 结论（先答问题）

**问：代码是否冗余太多？—— 不是。**
321 个受跟踪文件 / 45,529 行（生产 167 个 / 18,595 行 · scripts 62 个 / 15,706 行 · tests 92 个 / 11,228 行）。
对一个含 62 个一次性研究脚本、92 个测试文件、跨 6 个月迭代的量化项目，这是正常规模。

**问：有没有值得处理的重复？—— 有，按严重度四档：**

| 级别 | 发现 | 性质 |
|:--:|------|------|
| **P0 正确性风险** | `_num` 有 **10 个实现、2 种 NaN 语义**（5 个过滤 NaN、5 个不过滤） | 同一输入在不同模块可能一个得 `None`、一个得 `nan` —— 唯一可能造成「算错但不报错」的重复 |
| **P1 模式性重复** | `scripts/` 62 个研究脚本各自搬运同一批 helper：`_load`×6、`_load_universe`×4、`_tstat`×3、`_pool_codes`/`_load_codes`/`_make_filter`/`_ma`/`_day_files`/`_ema`/`_client` 各 ×2 | 精确重复函数体共 13 组 203 行（占 0.45%），搬运即可消 |
| **P2 同文件复制** | `agents_analysts.py` 4 个 `generate_prompt`（40/32/32/32 行）、`orchestrator.py` 的 `_get_agent_name`/`_get_agent_emoji`、`fetch/fundamentals_source.py` 的 `fetch_all_periods`/`fetch_all_disclosures` | 同构不同值 7 组 233 行，参数化收敛收益最高 |
| **P3 结构性债务** | `tdx/tdx_csv_adapter.py` 与 `tdx_native/day_reader.py` 双实现（`board_of` 等相同、`is_a_share_stock` 有差异），**两边都有活跃消费者** | 不合并（大重构），但须固定「新代码用哪套」的规则 |

**不建议动的（说明理由）**：scripts 的 `main()` 长函数（146~401 行 ×15 个）——
每个 main 对应一份已登记实验证据（事前阈值→报告 JSON），拆分改变「可逐行复现」的性质，
收益低于风险；`DEFAULT_WINDOWS`/`DIRECTIONS`/`FACTORS` 等「同名不同值」常量——
它们是各研究的**事前登记参数**，集中化会改动已登记实验的参数语义；`ROOT`/`REPO_ROOT`
自包含模式——可移植性收益，且 tests 依赖 `ROOT` 注入；`reports/` 与 `D:/pit_snapshots`
数据层——证据本体。

---

## 1. 方法与可复现性

```
python scripts/audit_code_redundancy.py           # 人类可读报告
python scripts/audit_code_redundancy.py --json    # 机器可读
```

判定流程：`git ls-files *.py` → AST 解析 → **标识符归一化**（变量名/参数名→占位符、
剥 docstring、去装饰器、函数名归一）→ sha1 分组。两个口径：

* **完全重复**（归一化标识符、**保留常量**）：字节级等价（除命名）的复制粘贴，合并风险最低；
* **同构不同值**（连常量一起归一化）：复制后改造参数的痕迹，多半可参数化。

阈值集中在模块常量（`MIN_LINES_EXACT=8` / `MIN_LINES_ISOMORPHIC=12` / `HELPER_MAX_LINES=40`）。
**调整阈值 = 改变判定标准**，因此基线守卫测试只允许组数**下降**（合并旧重复永远安全），
上升必须先在本报告留痕 —— 与项目「判定标准事前固定、不得事后调整」的纪律一致。

已知边界：解析失败的文件记入 `parse_errors` 并**明确报错**（退出码 1），不静默跳过。

---

## 2. 规模盘点

| 分区 | 文件数 | 行数 | 说明 |
|------|------:|------:|------|
| 生产包（根 + 各包） | 167 | 18,595 | 引擎 / 因子 / PIT / 风险 / 取数 |
| scripts/ | 62 | 15,706 | 一次性研究脚本（每个对应一份证据） |
| tests/ | 92 | 11,228 | 测试:生产 ≈ 0.6:1 |
| **合计** | **321** | **45,529** | 行数含空行与注释 |

测试/生产比 0.6 偏低但可接受（研究脚本本身大量逻辑由对账报告承载）。

---

## 3. 重复全景

### 3.1 完全重复函数体（13 组 · 203 行 · 合并风险最低）

| # | 函数 | 位置 | 行数 | 建议落点 |
|--:|------|------|-----:|------|
| 1 | `_load` | run_expert_filter_study:68 / run_industry_ic_attribution:123 / run_stop_loss_ab:56 / run_valuation_weight_ab:63 | 18×4 | `scripts/_study_common.py` |
| 2 | `fetch_all_periods` / `fetch_all_disclosures` | fetch/fundamentals_source.py:186 / :282 | 33/26 | 同文件内提取 `_fetch_one_period()`（见 3.2） |
| 3 | `_load` | run_contrarian_portfolio:59 / run_contrarian_study:55 | 18×2 | 同 #1 |
| 4 | `_rank` | factors/factor_ic_lab.py:143 / scripts/run_tdx_universe_ic.py:76 | 14/13 | 先比对口径（见 4.5） |
| 5 | `board_of` | tdx/tdx_csv_adapter.py:123 / tdx_native/day_reader.py:96 | 13×2 | 固定主实现后单向 import（见 P3） |
| 6 | `_num` | factors/factor_gate.py:8 / factor_validation.py:14 / stage2/stage2_ablation.py:15 | 8×3 | **先定标准语义再合并**（见第 4 节） |
| 7 | `_rank` | ashare/ashare_cross_section.py:14 / stage2/stage2_scoring.py:20 | 11×2 | 同 #4 |
| 8 | `_pool_codes` | run_concentration_study:64 / run_universe_replication:47 | 10/11 | `scripts/_study_common.py` |
| 9 | `_pct_rank` | run_contrarian_portfolio:79 / run_contrarian_study:75 | 9/10 | 同 #8 |
| 10 | `_load_codes` | run_concentration_study:76 / run_universe_replication:60 | 9×2 | 同 #8 |
| 11 | `_ema` | cycle_price_action.py:8 / stock_scoring.py:17 | 8/9 | `scripts/_study_common.py` 或保留（跨包，见 4.5） |
| 12 | `_client` | corporate/corporate_action_provider.py:78 / tushare_client/tushare_ashare_events.py:19 | 8×2 | 先定主实现（第 4 节） |
| 13 | `_make_filter` | run_tail_exclusion_study:148 / run_universe_replication:102 | 8×2 | 同 #8 |

**另有跨文件同名但实现相同**（第 5 节列全）：`_load_universe`×4（读 `pit_universe.json`
的 `snapshots`，单行 helper）、`_tstat`×3、`_ma`×2、`_day_files`×2。

### 3.2 同构不同值函数体（7 组 · 233 行 · 可参数化）

| 函数 | 位置 | 行数 | 收敛方式 |
|------|------|-----:|------|
| `generate_prompt` ×4 | agents_analysts.py:26 / :82 / :130 / :178 | 40/32/32/32 | 提「模板 + agent 配置表」，四个分析师变一行配置 |
| `_load` ×4 | （同 3.1 #1，常量不同） | 18×4 | 参数化（schema / 路径） |
| `fetch_all_periods` / `fetch_all_disclosures` | fetch/fundamentals_source.py:186 / :282 | 33/26 | 提取 `_fetch_one(url_builder)` |
| `_load` ×2 | run_contrarian_*:59 / :55 | 18×2 | 同 #1 |
| `_rank` ×2 | factor_ic_lab:143 / run_tdx_universe_ic:76 | 14/13 | 定主实现 |
| `_get_agent_name` / `_get_agent_emoji` | orchestrator.py:170 / :184 | 13×2 | 合并为单表 `{type: (名称, emoji)}` |
| `board_of` ×2 | tdx/tdx_csv_adapter.py:123 / day_reader.py:96 | 13×2 | P3 结构性债务 |

### 3.3 模块级常量重复定义

**「同名同值」= 纯重复（可合并）**：
`_STOCK_PREFIXES` / `_BJ_OLD_RANGES` / `_TDX_INDEX_PREFIXES`（tdx 两套各一份）、
`ROLES`×3、`SKIP_DIRS`×4、`OUT_COLUMNS`×3、`VERDICT_MAP`×3、`SUBWINDOWS`×3、
`HEADERS`×2、`INDEX`×2、`SOURCES`×3（部分同值，需逐个核对）。

**「同名不同值」= 事前参数，勿合并**：
`DEFAULT_WINDOWS`×10（每个研究的窗口集本就不同：`["2024-01-02"]` vs 5 窗口）、
`FACTORS`×4、`DIRECTIONS`×4、`MIN_HISTORY`×4、`HORIZON`×2、`WINDOWS`×2。

**自包含路径常量**：`ROOT`/`REPO_ROOT` 在约 10 个文件各算一次 —— 这是**可移植性收益**
（脚本可独立拷贝运行），且 tests 依赖 `ROOT` 注入，**不建议集中**。

---

## 4. ⚠️ 行为不一致风险（本审计的真正产出）

### 4.1 `_num`：10 个实现、2 种 NaN 语义（P0）

十处 `_num` 对「空值三态」的处理实际一致（`None`/`""`/`"-"` 都落到 `None`），
但 **NaN 处理分裂为两派**：

| 语义 | 实现 | 后果 |
|------|------|------|
| **过滤 NaN**（`x != x` 检查） | factor_gate:8 · factor_validation:14 · stage2_ablation:15 · risk/valuation_weight.py:56 · fetch/fundamentals_source.py:85 | NaN → `None`（fail-safe：缺失即缺失） |
| **不过滤** | ashare_cross_section:7 · ashare_event_engine:24 · stage2_scoring:13 · pit_fundamentals.py:371 · pit_quarterly.py:60 | NaN 原样流出，参与排序/求和/IC 计算 |

**风险场景**：东财/baostock 的数值列几乎不给 NaN（空值给 `""`），NaN 主要来自
**上游计算**（0/0、inf-inf）。一旦产生，因子引擎与估值模块的处置相反：
一边当缺失、一边当数值 —— 同一条数据在不同模块参与计算的结果不同，**且不报错**。
这正是本项目反复对抗的「静默失效」类别。

**建议（P1）**：定唯一标准实现 `to_float_or_none(v)` —— `None`/`""`/`"-"`/非数值/NaN
一律 `None`，落点 `data_contracts.py`（数据契约模块，语义最贴切）；10 处逐个替换，
每处一个行为测试锁定；替换后跑全量 CI + 重跑对账脚本确认结论不变。
**预估 0.5~1 人日**（含回归）。

### 4.2 `_sha256`：6 处、4 个字节级相同 + 1 个一次性读

`build_tdx_dataset:43` / `merge_delisted_into_dataset:51` / `repair_tdx_metadata:24`
（+`tdx/tdx_csv_adapter.py:220`）是**同一份分块实现**的复制；`patch_limit_ratio:49`
用 `Path.read_bytes()` 一次性读（元数据文件小，暂无实际 OOM，但不一致即隐患）。
**库函数已存在**：`pit.pit_snapshot_store.sha256_of_file`（分块读、大文件安全）。
scripts 已 `sys.path.insert(ROOT)`，直接 import 即可。**预估 0.25 人日**。

### 4.3 `tdx/` vs `tdx_native/`：双实现，`is_a_share_stock` 有差异（P3）

`board_of` 两边字节级相同，但**同对文件里 `is_a_share_stock` 归一化后仍有差异**
（tdx_csv_adapter:101 vs day_reader:32）→ 同一代码可能在一个模块判「股票」、
另一个判「非股票」。两边都有活跃消费者（`tdx/` 服务 build/merge/enumerate 三脚本，
`tdx_native/` 服务 run_astock_reconciliation / run_tdx_universe_ic），**合并=大重构，
本轮不做**。建议改为**规则固定**：新代码只用 `tdx_native/`，`tdx/` 冻结并注明服务对象。

### 4.4 `_atomic_write` 两处有差异

`public_daily_source.py:30` vs `research_artifacts.py:48` —— 原子写语义
（临时文件+rename？fsync？）需逐行核对；这是**证据落盘**路径，语义分歧的后果是
「崩溃时留半个文件」。建议合并到一份并加「写坏文件不得替换原文件」的测试。

### 4.5 反例：没有漂移的好实践

`bs_symbol`（号段→baostock 前缀，未知号段抛错）在 `run_pit_snapshot_ingest.py:328`
**单点定义**，对账脚本 import 使用而非复制 —— 「对象标识」类逻辑单点化，正是应对
本项目「跨市场重号」风险的范本。`_rank`/`_pearson`/`_returns`/`_pct_rank` 等
「同名不同义」多数是**口径适配**（服务上下文不同），统一反而要把适配逻辑塞进分支，
可读性下降 —— 列入「逐个评审、不排期」。

---

## 5. 长函数与职责混杂

Top 20 长函数中 **15 个是 scripts 的 `main()`**（146~401 行）：
`run_fundamental_factor_study.main`(401)、`build_certified_dataset_v2.main`(387)、
`run_tdx_rolling_eval.main`(308)、`run_five_factor_ab.main`(307) … 另有
`run_pit_snapshot_ingest._ingest_one`(219，本轮回填韧性补丁后增长)、
`stock_scoring.score_stock`(146)、`tdx_native/backfill.run`(146)。

**判断：不建议拆。** 这些 main 是「argparse → 数据加载 → 事前阈值 → 输出证据 JSON」
的线性流水线，每个对应一份已登记实验；拆分会把「一条命令复现一份证据」变成
跨文件跳转，损害可追溯性。真正值得参数化的是第 3.2 节的**同文件复制**（那里拆分
不改变外部行为）。

---

## 6. 分级建议（按投入产出排序）

| 优先级 | 事项 | 动作 | 预估工时 | 风险 |
|:--:|------|------|--------:|------|
| **P1** | `_num` NaN 口径统一 | `data_contracts.to_float_or_none` + 10 处替换 + 行为测试 + 全量回归 | 0.5~1 人日 | 中（改解析=改因子输入，须跑对账回归） |
| **P2** | scripts helper 提取 | 新建 `scripts/_study_common.py`：`_load`×6、`_load_universe`×4、`_tstat`×3、`_pool_codes`/`_load_codes`/`_make_filter`/`_ma`/`_day_files` 各×2 | 0.5 人日 | 低（纯函数搬运；搬运用等价性测试逐字节锁行为） |
| **P3** | 同文件参数化 | agents_analysts 4×`generate_prompt` → 模板+配置表；orchestrator 2×`_get_*` → 单表；fundamentals_source 2×`fetch_all_*` → `_fetch_one()` | 1~1.5 人日 | 中（agent prompt 是 LLM 输入，改动须冒烟回归） |
| **P4** | `_sha256` 收敛到库函数 | 6 处改 import `pit.pit_snapshot_store.sha256_of_file` | 0.25 人日 | 低 |
| **P5** | tdx 双实现 / `_atomic_write` / 其余同名不同义 | 先定规则（新代码只用 tdx_native）；`_atomic_write` 合并+测试；其余逐个评审 | 不排期 | 高（结构性地动） |
| **P0** | 基线守卫 | ✅ 本轮已建 `tests/test_code_redundancy_baseline.py`（完全重复 ≤13 组、同构 ≤7 组） | — | — |

**总收益量化**：P1+P2+P3+P4 全部落地可消除约 **430~590 行**（精确 203 + 同构 233 + 同名同值 helper 约 60~150），
并使 `_num` 的 NaN 口径唯一化 —— 后者是**正确性**收益，无法用行数衡量。

---

## 7. 本轮已完成的配套动作

1. **工具入库**：`scripts/audit_code_redundancy.py`（只读；`--json` 可机器消费）。
2. **基线守卫**：`tests/test_code_redundancy_baseline.py` —— 组数上升即失败；
   调基线必须改本报告留痕（防「判定标准事后调整」）。
3. **归一化器行为锁定**：仅改名⇒同哈希；常量不同⇒精确口径下不同；docstring 差异不影响判定。

> 注：本报告数字为 2026-10-13 提交前对 321 个已跟踪文件测得；审计工具与其测试
> （约 460 行）入库后计入下一次运行，届时完全重复/同构组数不应因此上升
> （守卫测试会验证这一点）。
