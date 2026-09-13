# 1.0 版本合并报告

> 生成时间：2026-09-11
> 合并来源：`Desktop/4.3`（功能新版，内部版本号 v3.7） + `Desktop/v3.4_work`（工程优化版）

---

## 一、为什么这样合并

两个文件夹是同一项目（AI股神团队 · A股多 Agent 分析系统）的两条演进线：

| 文件夹 | 定位 | 优势 | 短板 |
|--------|------|------|------|
| **4.3** | 功能持续迭代到 PHASE43，内部版本号已到 **v3.7** | 模块最全：因子注册/门控/验证、PIT 完整性、Stage2 打分与消融、真实数据工作台 | 工程治理薄弱：文档硬编码飞书凭据、`shell=True` 命令注入、无缓存/并行/日志/依赖声明 |
| **v3.4_work** | 一次深度工程审计后的优化版 | 安全与性能修复到位：凭据脱敏、参数列表调用、SSL 复用、TTL 缓存、并行取数、回测含成本、结构化日志、lint/type-check 配置 | 功能版本较旧，缺少 4.3 的因子体系与 PIT 加固 |

**结论**：以 **4.3 为功能基线**，把 v3.4_work 的工程优化**移植上去**，而不是反过来。
这样既不丢新功能，又拿到全部工程改进。

---

## 二、1.0 = 4.3 全量 + v3.4_work 优化补丁

### 2.1 完整保留 4.3 的新增能力（v3.4_work 中不存在）

**新模块（12 个）**
`factor_registry.py` · `factor_gate.py` · `factor_lab.py` · `factor_validation.py`
`stage2_scoring.py` · `stage2_ablation.py`
`pit_integrity.py` · `pit_universe_builder.py`
`cycle_price_action.py` · `daily_csv_adapter.py`
`phase41_data_workbench.py` · `recon_price_factor_lab.py`

**新测试（7 个）**
`test_factor_registry_gate.py` · `test_factor_validation.py` · `test_phase39_factor_lab.py`
`test_phase40_pit.py` · `test_phase41_workbench.py` · `test_phase42_integrity.py`
`test_phase43_real_data_adapter.py`

**新文档**：`PHASE35` ~ `PHASE43`、`DATA_HYGIENE_AUDIT.md`

**架构升级（已在 1.0 生效）**
- `screen_pipeline.py`：v3.4 → v3.7，Stage2 改走 `stage2_scoring.rank_stage2_candidates`
- `real_alpha_pipeline.py`：接入 `pit_integrity.audit_pit_rows` + `point_in_time_universe`
- `daily_stock_pick.py`：运行时状态外移到 `~/.ai-stock-god/`，禁止项目内静态股票池
- `walk_forward.py`：`locate_cycle_phase` 从 `cycle_price_action` 独立成模块
- `portfolio_backtest.py`：新增 `start_signal_date` 参数（避免冷启动偏差）
- `ashare_factor_engine.py`：因子扩展至 10+ 个

### 2.2 从 v3.4_work 移植的优化（已合入 1.0）

| # | 优化项 | 落地文件 | 验证 |
|---|--------|---------|------|
| 1 | 飞书凭据脱敏（文档 → 环境变量） | `README.md` `DAILY_TASK_GUIDE.md` `AUDIT_REPORT.md` | 全量 grep 无残留 ✓ |
| 2 | `shell=True` → 参数列表（防命令注入） | `run_daily_screening.py` | 无 `shell=True` 调用 ✓ |
| 3 | 模块级 SSL context 复用 | `data_fetcher.py` | 仅 1 处 `create_default_context()` ✓ |
| 4 | 行情 30s TTL 内存缓存（线程安全） | `data_fetcher.py` | 读写测试通过 ✓ |
| 5 | 行情 + K线并行取数 | `data_fetcher.py` | `ThreadPoolExecutor` 已接入 ✓ |
| 6 | K线重试间隔 1.5s → 0.5s | `data_fetcher.py` | — |
| 7 | 回测净收益口径（佣金/印花税/滑点） | `tracking.py` `run_tracking.py` | ⚠️ 见 2.7——此口径曾存在两处严重缺陷，已于 2026-09-12 修复 |
| 8 | 因子层复权口径安全检查 | `ashare_factor_engine.py` | raw 数据触发 warning ✓ |
| 9 | 结构化日志 | `log_utils.py` `run_pipeline.py` | 可用 ✓ |
| 10 | 依赖声明 + lint/type-check 配置 | `requirements.txt` `ruff.toml` `mypy.ini` | — |

### 2.3 新增文件（v3.4_work 独有）

`log_utils.py` · `requirements.txt` · `ruff.toml` · `mypy.ini` · `AUDIT_REPORT.md`
`watchlist.example.json`（用户 72 只股票池的示例，供复制到 `~/.ai-stock-god/watchlist.json`）

### 2.4 合并后第二轮加固（2026-09-11）

| # | 内容 | 落地文件 | 验证 |
|---|------|---------|------|
| 1 | **API 令牌桶限流器**（默认 8 req/s、突发 16，`FETCH_RATE_PER_SEC=0` 可关闭） | `data_fetcher.py` | 突发/补充/并发/超时 6 项测试 ✓ |
| 2 | **修复 PEP 701 版本不兼容**：10 处 f-string 替换字段内复用外层同引号，导致 3.10/3.11 下 SyntaxError | `agents.py` `data_fetcher.py` | ruff py310 零告警；提示词内容零差异 ✓ |
| 3 | **修复 `_I0` 未定义名**：`locate_cycle_phase` 抽取成模块时漏带常量 | `cycle_price_action.py` | F821 清零 ✓ |
| 4 | **清理 57 处死导入** + 19 处安全自动修复 | 全项目 | 编译 + 127 测试通过 ✓ |
| 5 | **RUF012 可变类属性**：`WorkflowOrchestrator.STAGES` list → tuple | `orchestrator.py` | 用法均为只读 ✓ |
| 6 | **补齐类型标注**：`data_fetcher` / `screen_pipeline` / `feishu_notifier` / `real_alpha_pipeline` 等 | 多个核心模块 | mypy 127 文件零错误 ✓ |
| 7 | **Phase 文档归档**：32 个 PHASE*.md → `CHANGELOG.md` + `docs/archive/` | 文档层 | — |
| 8 | **CI/CD 流水线**：多 Python 版本矩阵 + lint + 类型 + 兼容性守卫 + 测试 + 凭据扫描 | `.github/workflows/ci.yml` | YAML 结构校验 ✓ |
| 9 | **主流水线集成测试**：11 个端到端用例 | `test_integration_pipeline.py` | 全通过 ✓ |
| 10 | **Python 版本守卫测试** | `test_python_compat.py` | 4 项通过 ✓ |
| 11 | pytest 配置 + 开发依赖清单 | `pytest.ini` `requirements-dev.txt` | — |

### 2.5 巨石文件拆分（2026-09-11 第三轮）

按职责拆分 3 个超大文件，**保持对外 API 与生成产物字节级不变**：

| 原文件 | 行数 | 拆分后 | 最大模块 |
|--------|------|--------|---------|
| `agents.py` | 658 | 5 个模块 | `agents_analysts.py` (209) |
| `daily_stock_pick.py` | 664 | 6 个模块 | `daily_stock_pick.py` (231) |
| `report_generator.py` | 1029 | 3 个模块 | `report_generator.py` (506) |

**agents.py → 按角色分层**

```
agents_base.py        基类 / DATA_RULES / pack_data / AnalysisResult
agents_analysts.py    基本面 · 情绪 · 新闻 · 技术（4 位）
agents_researchers.py 看多 · 看空（独立论证）
agents_decision.py    交易员 · 风控官
agents.py             门面：re-export + 工厂（`from agents import X` 不变）
```

**daily_stock_pick.py → 按职责分层**

```
runtime_env.py       路径 / 日志 / 配置加载（无项目内依赖，避免循环导入）
stock_scoring.py     透明规则打分（纯函数，无落盘/推送副作用）
pool_manager.py      股票池自动维护（方案A）
industry_context.py  行业相对强度集成（Phase 8）
lark_notify.py       飞书写表 + 消息推送
daily_stock_pick.py  编排 + 深析 + 落盘 + 入口
```

**report_generator.py → 按关注点分层**

```
report_styles.py     REPORT_CSS（原占本文件 450+ 行的 CSS）
report_markdown.py   markdown_to_html()（原为方法，实为纯函数）
report_generator.py  HTMLReportGenerator 本体（各章节生成 + 保存）
```

**等价性验证方式**（不是"看起来没问题"，而是逐字节比对）：

- `agents.py`：8 个 Agent 的 `system_prompt` 与 `generate_prompt`（含完整数据包注入）逐字节一致
- `daily_stock_pick.py`：`score_stock` 在相同输入下的**全部输出字段**一致；27 项常量/函数/行为检查通过
- `report_generator.py`：用同一会话生成的**完整 HTML 报告（27519 字符）逐字节一致**，`save()` 落盘文件逐字节一致
- 新增 `test_module_splits.py`（14 个用例）守护拆分后的兼容性

---


### 2.6 mypy 全模块覆盖（2026-09-11 第四轮）

此前 `mypy.ini` 用 `ignore_errors` 挂起了 6 个模块。本轮全部纳入检查，**现在 139 个源文件零错误、零例外**。

修复的 21 个类型问题（含 2 个真实缺陷）：

| 文件 | 问题 | 性质 |
|------|------|------|
| `agents_base.py` | 可选导入 `fact_sheet_to_text` 未标注；`pack_data` 参数应为 `Optional[dict]` | 类型标注 |
| `agents_analysts/researchers/decision.py` | 9 处 `pack_data(None)` 调用告警 | 由上一项连带解决 |
| `orchestrator.py` | `get_next_prompt` 用同一个 `agent` 变量承载 5 种不同 Agent 类型 | **接口不一致**（见下） |
| `orchestrator.py` | `analyst_reports: Dict[...] = None` 可变默认值 | **真实缺陷**（见下） |
| `main.py` | `prompt` 可能为 `None` 却直接 `f.write(prompt)` ×3 | **潜在崩溃** |
| `main.py` | `load_existing_session` 返回 `None` 但标注为 `WorkflowOrchestrator` | 类型标注 |
| `stage2_ablation.py` | `sum(list[float \| None])` 未收窄 ×2 | 类型标注 |
| `tushare_ashare_events.py` | `os.getenv` 返回 `str \| None` 未兜底 | 类型标注 |

#### 顺带发现的两个真实缺陷

**① `analyst_reports` 用可变默认值（dataclass 陷阱）**

```python
analyst_reports: Optional[Dict[str, AnalysisResult]] = None   # ✗ 每次访问都要判空
```

原代码靠 `__post_init__` 补救，但类型上仍是 `Optional`，下游 `report_generator` 直接索引该字段——
一旦 `__post_init__` 被绕过（如 `dataclasses.replace`、反序列化）就会 `TypeError`。

**修复**：改用 `field(default_factory=dict)`，从类型上消除 `Optional`，并新增测试确认实例间不共享。

**② `main.py` 对 `Optional[str]` 直接写文件**

```python
prompt = orch.get_next_prompt()      # 返回 Optional[str]
...
f.write(prompt)                      # ✗ 若为 None 直接 TypeError
```

三处同样写法。**修复**：加 `if not prompt: continue` 守卫并给出提示。

#### 一个配置陷阱

mypy.ini 的**值后面不能跟行内注释**：

```ini
check_untyped_defs = False       # 未标注函数体暂不检查   ← mypy 报 "Not a boolean" 并忽略该项
```

mypy 会静默回退到默认值，行为"看起来正常"但配置未生效。已把注释移到独立行。

#### 说明：一次不可复现的测量结果

排查过程中出现过一次「临时配置报 0 错误、正式配置报 21 错误」的矛盾。
已逐一排除缓存失效、CRLF 解析、ini 语法三种可能，均非原因。
**处理方式**：以可稳定复现的结果为准（清缓存后多次运行一致），并修正配置中的内联注释问题。
记录在此以免后人重复踩坑。

### 2.7 回测口径缺陷修复（2026-09-12）

> **重要更正**：2.2 节曾把「回测净收益口径」标记为已验证通过。该结论不成立——
> 当时的验证只确认了代码"能跑通"，没有校验成本模型的**数值正确性**。
> 本轮补做数值审计，发现两处严重缺陷。

| # | 缺陷 | 影响 | 状态 |
|---|------|------|------|
| 1 | `TrackingCosts` 用「每股价格」当计费名义金额 | 5 元最低佣金在 1500 元股价上放大到 **0.333%**（应 0.03%），每笔收益率偏差 **0.6 个百分点**——足以让正收益策略显示为亏损 | 已修复 |
| 2 | `--gross` 开关被 `costs or TrackingCosts()` 静默覆盖 | 毛收益实际仍扣费，且 CLI 仍打印"口径=毛收益"，**报告与实际不符** | 已修复 |
| 3 | `--dry-run` 无条件下调用 `save_tracking_records` | 试运行推荐进入 `tracking.db`，被回填后**污染胜率校准样本** | 已修复 |

**修复方式**：

- 引入 `position_notional`（基准仓位，默认 10 万元，与 `backtest_engine.initial_capital` 一致），
  用 `round_trip_cost_pct()` 计算成本占比 → **成本率与股价解耦**（10 元股与 1500 元股口径一致）
- 新增 `net_return_pct(rec_price, close_n, costs)` 统一毛/净两种口径
- `backfill_pending` 改用显式 `apply_costs` 布尔参数，避免 `or` 的 falsy 语义吞掉"无成本"意图
- `main()` 在 dry-run 下跳过 tracking 写入与飞书写表，并打印"无持久化副作用"

**修复后实测**（基准 100 → 105，毛涨 5.0%）：

```
毛收益口径: 4.76%
净收益口径: 4.55%     差额 0.21% = 往返成本 0.11% + 双边滑点 0.10% ✓
```

**新增守卫**：`test_tracking_costs.py`（14 用例）+ `test_dry_run_safety.py`（5 用例）。
其中最关键的一条断言是「**同一毛涨幅下，10 元股与 1500 元股的净收益必须完全相等**」——
这正是原缺陷的直接反例。

**教训**：口径类代码的"验证通过"必须是**数值级**的，不能只看能否运行。
建议后续为所有成本/收益计算补充"手算对照"测试。

### 2.8 类型检查收紧 + KlineList 元数据修复（2026-09-12）

#### 启用 `check_untyped_defs`

此前 mypy 只检查**带标注**的函数，未标注函数体（项目里占多数）完全不查。
启用后暴露 **31 个问题**，全部修复，现在 142 个文件零错误。

其中值得记录的几类：

| 文件 | 问题 | 性质 |
|------|------|------|
| `data_fetcher.py` | `KlineList` 的 `adjust` / `quality_ratio` / `data_quality` 未声明为类属性 | **潜在缺陷**（见下） |
| `stage2_scoring.py` / `ashare_cross_section.py` | `out = [None] * n` 后赋值 float | 类型收窄（与 `stage2_ablation` 同类） |
| `health_monitor.py` | `peak = 0` / `mdd = 0` 后赋值 float | 类型收窄 |
| `llm_client.py` | `last_err` 先接 `HTTPError` 再接 `Exception` | 类型收窄 |
| `log_utils.py` | `handlers` 推断为 `list[StreamHandler]` 后 append `FileHandler` | 类型收窄 |
| `provider_router.py` | `errors` 实际存 dict，原推断为 str | 标注修正 |
| `tracking.py` | `by_bucket` 实际存嵌套 dict，非 float 列表 | 标注修正 |
| 其余 16 处 | 局部变量缺标注（`List[str]` / `Dict[str, Any]` 等） | 标注补全 |

#### 【潜在缺陷】KlineList 切片丢失元数据

```python
class KlineList(list):
    source = None                      # 只声明了 source

    def __getitem__(self, idx):
        if isinstance(idx, slice):
            new = KlineList(ret)
            new.source = self.source   # ← 只复制 source
            return new
```

`adjust` / `quality_ratio` / `data_quality` 是**运行时动态挂载**的实例属性，
切片产生的新对象**完全不带这些字段**。

**影响评估（诚实结论）**：当前**不可达**。读取方均用 `getattr(..., default)` 兜底：
- `stock_scoring.py` 用 `getattr(k, "data_quality", "unknown")`
- `data_fetcher.py` 用 `getattr(kline, "source", None)`

且 `fetch_kline` 在切片后会用 `KlineList(rows)` 重新包装并重新赋全部字段。
但一旦有人写 `kline[-30:].data_quality` 就会拿到 `AttributeError`，
或经 `getattr` 兜底静默降级为 `"unknown"` —— 属于**静默错误**。

**修复**：
1. 四个字段全部声明为类属性（类型检查可识别 + 契约显式化）
2. `__getitem__` 切片时逐个复制全部元数据

**新增守卫**：`test_kline_metadata.py`（6 用例），含"连续切片不逐层丢失"与
"不复权数据告警语义不因切片消失"两条业务断言。


---


## 三、关键设计：1.0 的因子层同时具备两版能力

`ashare_factor_engine.py` 在 1.0 中合并后：

**4.3 的扩展因子（保留）**
`momentum_5d` / `momentum_10d` / `momentum_20d` / `momentum_60d`
`realized_vol_20d` / `realized_vol_60d`
`momentum_accel_5_20` / `breakout_20d` / `range_pct_20d`
`volume_ratio_5d` / `volume_ratio_20d` / `amount_ratio_5d` / `turnover_mean_20d` / `drawdown_20d`

**v3.4_work 的复权安全检查（新增）**
检测 `bars.source` / `bars.adjust` 为 `raw` / `tdx_local_raw` 时，
输出 `warnings: ["raw_unadjusted_data: 因子可能因除权跳价失真，仅供形态参考"]`

---

## 四、验证结果

**当前状态（2026-09-12，全部五轮工作完成后）：**

```
语法校验   : 143 / 143 个 .py 文件编译通过
ruff       : All checks passed
mypy       : Success: no issues found in 142 source files
             （无 ignore_errors 例外；已启用 check_untyped_defs）
pytest     : 173 passed
Python 3.10: 0 处语法不兼容（ruff --target-version py310）
行尾       : 全部 LF
凭据扫描   : 4 组真实 token/user_id 全量 grep → 0 残留
```

> **已过时（2026-09-13）**：上面是 09-12 的状态快照，保留作为演进记录。
> 当晚完成第四轮收紧后的基线为：**188 个源文件零错误 · 329 passed, 1 skipped**，
> 详见下方 [第六节 · 第四轮推进](#第四轮推进2026-09-13遗留事项逐条处置)。

**分项守卫测试：**

| 测试文件 | 用例数 | 覆盖内容 |
|---------|--------|---------|
| `test_rate_limiter.py` | 6 | 令牌桶：突发/补充速率/关闭/并发/超时/配置一致性 |
| `test_integration_pipeline.py` | 11 | 全市场筛选链路端到端 |
| `test_module_splits.py` | 21 | 模块拆分兼容性（门面 API、CSS 唯一来源、行尾） |
| `test_python_compat.py` | 4 | Python 3.10 语法下限 |
| `test_tracking_costs.py` | 14 | **成本口径数值正确性（含股价无关性）** |
| `test_dry_run_safety.py` | 5 | **`--dry-run` 无持久化副作用** |
| `test_kline_metadata.py` | 6 | **KlineList 元数据在切片中不丢失** |

复现命令：

```bash
cd "C:/Users/T430/Desktop/1.0"
pip install -r requirements-dev.txt
ruff check .
mypy . --config-file mypy.ini
python -m pytest
```

> 注：`pytest.ini` 已配置 `--ignore=test_tushare_provider.py`（该测试依赖 pandas 可选包），
> 因此直接运行 `pytest` 即可，无需手动排除。

> **口径说明**：以上验证的是**工程机制与数值正确性**，不代表策略有效性。
> 真实投资结论仍需认证过的历史数据与预注册的样本外评估（见 2.7 与第六节）。

---

## 五、使用须知

### 5.1 运行时状态目录（4.3 的数据卫生设计）

1.0 沿用 4.3 设计：**股票池与候选池不再放在项目内**，而是外移到用户目录。

```bash
mkdir -p ~/.ai-stock-god
cp watchlist.example.json ~/.ai-stock-god/watchlist.json   # 首次初始化
```

可用环境变量覆盖：
- `AI_STOCK_WATCHLIST_FILE` — 指定股票池路径
- `AI_STOCK_STATE_DIR` — 指定状态目录
- `AI_STOCK_LOG_DIR` — 指定日志目录

### 5.2 凭据配置

```bash
export FEISHU_BASE_TOKEN="<your_base_token>"
export FEISHU_TABLE_ID="<your_table_id>"
export FEISHU_BASE_URL="https://my.feishu.cn/base/<your_base_token>"
export FEISHU_NOTIFY_USER_ID="ou_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
export ARK_API_KEY="<your_volcengine_ark_key>"   # 豆包模型
```

### 5.3 回测口径

`run_tracking.py backfill` 默认按**净收益**（含佣金+印花税+滑点）回填；
如需与旧数据对比，加 `--gross` 走毛收益口径。

---

### 5.4 数据源限流

`data_fetcher.py` 内置令牌桶限流，默认 **8 req/s、突发 16**。如遇接口封禁可下调：

```bash
export FETCH_RATE_PER_SEC=4     # 保守值
export FETCH_RATE_BURST=8
export FETCH_RATE_PER_SEC=0     # 完全关闭限流（不建议用于生产抓取）
```

---



## 六、遗留事项

### 本轮已完成（2026-09-11 ~ 09-12）

- ~~API 令牌桶限流器~~ ✅
- ~~集成测试 + mock~~ ✅（`test_integration_pipeline.py` 11 用例 + `test_dry_run_safety.py` 5 用例）
- ~~CI/CD 流水线~~ ✅（`.github/workflows/ci.yml`，含凭据扫描）
- ~~PHASE 文档归档为 CHANGELOG~~ ✅（32 个文档 → `CHANGELOG.md` + `docs/archive/`）
- ~~lint/type-check 基线~~ ✅（ruff + mypy 零告警，且 mypy 已覆盖全部模块）
- ~~巨石文件拆分~~ ✅（3 个文件 → 14 个模块，字节级等价验证）
- ~~mypy 渐进收紧~~ ✅（移除全部 `ignore_errors`，141 文件零错误）
- ~~回测口径数值审计~~ ✅（修复 3 处缺陷，见 2.7）
- ~~启用 check_untyped_defs~~ ✅（修复 31 处问题，142 文件零错误，见 2.8）
- ~~KlineList 元数据切片丢失~~ ✅（潜在缺陷，已修复并加守卫）

### 第四轮推进（2026-09-13）：遗留事项逐条处置

| # | 遗留事项 | 处置 | 结论 |
|---|---------|------|------|
| 1 | CI 未在远端实际跑通 | 新增 `run_ci.py` 本地等价执行器（与工作流同一套 6 项命令） | ✅ 本地全通过；**远端首跑仍需把仓库推上去** |
| 2 | 可选依赖未纳入测试 | 重写 `test_tushare_provider.py`（替身驱动，不再依赖 pandas）+ 补 crawl4ai **启用分支** 6 例 | ✅ 已从 `pytest.ini` 移除 `--ignore` |
| 3 | 外部集成未做真实凭据验收 | 需真实飞书/方舟凭据，本地无法替代 | ⏸ **仍需用户提供凭据** |
| 4 | mypy / ruff 可继续收紧 | 启用 `strict_optional` + `no_implicit_optional`；启用 9 条挂起的 ruff 规则 | ✅ 见下 |
| 5 | `report_generator.py` 仍 506 行 | 未推进 | ⏸ 收益递减，保留 |
| 6 | 真实投资结论缺失 | 需认证 PIT 数据 | ⏸ 保留 |

**质量基线变化**

| 指标 | 1.0（本轮前） | 本轮后 |
|------|--------------|--------|
| ruff | All passed | All passed（**规则收紧**，非放宽） |
| mypy | 182 文件零错误 | **188 文件零错误**（覆盖面扩大） |
| pytest | 275 passed | **329 passed, 1 skipped** |
| 测试文件 | 57 | 59 |
| CI | 仅配置文件 | 配置文件 + 可执行的本地等价器 |

### 第四轮附带发现的真实缺陷

本轮最大产出不是"把规则打开"，而是收紧过程中暴露出的既有缺陷：

| # | 缺陷 | 发现方式 | 影响 |
|---|------|---------|------|
| 1 | **`mypy.ini` 的 `exclude` 未锚定**，`build` 片段命中文件名 | 目录模式报 186 个文件，而根目录实有 188 个 `.py` | `build_tdx_dataset.py` 与 `pit_universe_builder.py` **整个模块**从未被类型检查 |
| 2 | **`stock_scoring.pe_note` 计算后被静默丢弃** | 启用 F841 | 估值注记全分支赋值却从未写入「核心逻辑」，与注释「仅标注」不符 |
| 3 | **`test_tushare_provider.py` 被整文件 `--ignore`** | 复核"可选依赖未纳入测试" | 该模块实为零自动化覆盖，而非"部分覆盖" |
| 4 | **22 处隐式 Optional 标注** `def f(x: str = None)` | 启用 `strict_optional` | 标注与实际语义不符，调用方按标注传值即可能崩 |
| 5 | **CI 凭据扫描覆盖面不足** | 审计工作流 | 只匹配 3 个固定字面量、不扫 `*.yml/*.toml/*.ini`，且内联实现无法本地复用 |
| 6 | **`_generate_cover` 中 11 行死代码** | 启用 F841 | `final_rec` / `verdict_class` 计算后从未用于封面输出 |
| 7 | **`load_observed_lifecycle` 对缺失行数会抛 `TypeError`** | 启用 `strict_optional` | 表头分支的 `int(None)`；已改为**跳过该行**而非补造 0 |

修复 2/6/7 均附了守卫测试；1/3/5 附了配置层的一致性断言。

---

### 仍待处理（截至 2026-09-13）

1. **CI 尚未在远端实际跑通**：本地等价器已全绿，但多版本矩阵（3.10–3.13）的**真实**
   执行结果仍需把仓库推到远端后才可知。这是唯一"只能由部署动作解决"的项。
2. **外部集成未做真实凭据验收**：飞书推送、付费模型调用仍只验证了降级分支。
3. **`report_generator.py` 仍 506 行**：类内 14 个 `_generate_*` 方法可再拆 mixin，收益递减。
4. **`disallow_untyped_defs` 未启用**：开启会产生 **569 处**「函数缺少类型标注」告警，
   属纯标注补全、无缺陷捕获收益，留待功能稳定后再推进（已在 `mypy.ini` 注明）。
5. **真实投资结论缺失**：现有测试验证的是工程机制与数值正确性，**不等于策略有效**。
   真实 Alpha 结论仍需认证过的历史全市场数据与预注册的样本外评估。
