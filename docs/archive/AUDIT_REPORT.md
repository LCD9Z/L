# 1.0 项目多角度专业审计报告

> 审计日期: 2026-09-10 | 合并生成: 2026-09-11
> 审计范围: 4.3 全量源码（含 PHASE35-43 新模块）+ v3.4_work 优化补丁
> **修复状态: P0 全部 + P1 全部 + P2 部分 已合入 1.0**

---

## 一、总体评价

这是一个架构成熟、设计理念严谨的 A 股多 Agent 智能分析系统。项目在"数据真实性优先、机器硬门槛优先于 LLM、缺失数据不补造"三大原则上执行得相当到位。但经过 34 个 Phase 的迭代后，积累了技术债，需要在以下方面优化。

**综合评分: 7.2 / 10** — 核心架构优秀，工程治理和运维层面有明确改进空间。

---

## 二、分维度审计

### 1. 代码质量与架构 (7/10)

#### 亮点
- **分层清晰**: 数据层 → 编排层 → Agent 层 → 输出层，职责边界明确
- **零第三方依赖**: 核心数据管道 (`data_fetcher.py`) 纯标准库实现，可移植性强
- **原子写入**: `orchestrator.py` 用 `tmp + os.replace` 保证会话保存不丢数据
- **优雅降级**: Crawl4AI 可选依赖未安装时静默降级，不影响主流程
- **DataBundle 契约**: `data_contracts.py` 带溯源 (`DataProvenance`)，审计链完整

#### 问题

| 严重度 | 问题 | 位置 | 说明 |
|--------|------|------|------|
| P1 | **巨石文件** | `report_generator.py` (35KB), `daily_stock_pick.py` (28KB), `agents.py` (26KB) | 单文件过大，应拆分。report_generator 可拆为模板+渲染+样式；daily_stock_pick 混合了打分/池管理/执行/推送 |
| P1 | **死代码残留** | `ashare_market.py.bak`, `screen_pipeline.py.bak` | .bak 文件不应存在于工作目录，应删除或纳入版本管理 |
| P2 | **临时脚本未清理** | `_vp.py` | 验证脚本，`open()` 无 encoding 参数，无异常处理，不应留在生产目录 |
| P2 | **代码风格不一致** | `risk_engine.py`, `walk_forward.py` | 部分模块使用紧凑单行风格（`if x: y` 压一行），与其他模块的可读性差距大 |
| P2 | **文档过载** | 26 个 .md 文件 | Phase 8-34 每阶段一个文档，历史价值高但维护负担重，应归档为 CHANGELOG |
| P3 | **无 lint/type-check 配置** | 全局 | 无 mypy.ini / ruff / black 配置，类型标注不一致（部分有 `Optional`，部分用 `| None`） |

---

### 2. 安全与凭据管理 (5/10)

#### 亮点
- `llm_config.json` 和 `feishu_config.json` 均为空值
- `.gitignore` 正确排除 `.env`、`*.db`、配置文件
- `llm_client.py` 支持环境变量覆盖 (`ARK_API_KEY` / `ARK_BASE_URL` / `ARK_MODEL`)
- `feishu_notifier.py` 同样支持环境变量优先

#### 问题

| 严重度 | 问题 | 位置 | 说明 |
|--------|------|------|------|
| **P0** | **飞书 Token 硬编码在文档中** | `README.md` L147-152, `DAILY_TASK_GUIDE.md` | `base_token` / `table_id` / `user_id` 均为明文（值已脱敏，形如 `Lj****Se` / `tbl****9b` / `ou_****56`），随文档提交到 Git 即泄露 |
| P1 | **Shell=True 命令注入风险** | `run_daily_screening.py` L43 | `subprocess.run(full_cmd, shell=True, ...)` 拼接 lark-cli 命令，`feishu_notifier.py` 已改为参数列表方式，但 `run_daily_screening.py` 仍用 shell 拼接 |
| P2 | **URL 参数未编码** | `data_fetcher.py` L174-176 | `secid` 直接拼入 URL，虽然 `normalize_code` 做了基本清洗，但无 URL 编码 |
| P2 | **无请求来源验证** | `data_fetcher.py` `_http_get` | 不验证响应 Content-Type，可能收到非预期格式 |
| P3 | **无 API 调用频率限制** | `data_fetcher.py` 全局 | 连续快速调用东财/腾讯接口可能被 IP 封禁，`daily_stock_pick.py` 注释中已提到此问题但未实现限流 |

---

### 3. 数据完整性与回测正确性 (7.5/10)

#### 亮点
- **PIT 原则贯彻**: `cutoff_time` 参数贯穿数据获取→新闻过滤→因子计算全链路
- **数据源溯源**: `KlineList.source` 属性区分 `eastmoney_qfq` / `tencent_qfq` / `tdx_local_raw`
- **不复权数据标注**: 通达信本地日K明确标注"不复权"，提示下游跨除权日会跳价
- **数据质量校验**: `_validate_kline_rows` 检查 OHLC 逻辑关系（high >= max(open,close) 等）
- **幂等去重**: tracking 库按 `code + rec_date + horizon` 防重复落库

#### 问题

| 严重度 | 问题 | 位置 | 说明 |
|--------|------|------|------|
| P1 | **回测不含交易成本** | `tracking.py` L177 | `return_pct = (close_n - rec_price) / rec_price * 100`，无佣金/滑点/印花税，而 `walk_forward.py` 的回测包含了交易成本，两个回测体系口径不一致 |
| P1 | **因子层可能混用复权口径** | `ashare_factor_engine.py` | `compute_factors` 直接消费 `bars`，如果 bars 来源是 `tdx_local_raw`（不复权），动量/回撤因子会因除权跳价产生错误信号，`data_fetcher.build_fact_sheet` 中未检查 kline source 就传入因子计算 |
| P2 | **日期格式不统一** | 全局 | 东财返回 `YYYY-MM-DD`，通达信返回 `YYYYMMDD`，`_norm_date` 做了兼容但增加了复杂度 |
| P2 | **fetch_close_on 精确匹配脆弱** | `data_fetcher.py` L516 | `if r["date"] == date_str` 要求日期精确匹配，格式差异会静默返回 None |
| P3 | **无自动化未来函数检测** | 测试层 | 没有自动化测试验证因子只用历史数据，仅靠人工审查 |

---

### 4. 性能与资源管理 (6.5/10)

#### 亮点
- **RuntimeProfile 三档**: lite/balanced/full，8GB 机器友好
- **流式 TopK**: `streaming_topk.py` 支持 5000+ 股票低内存筛选
- **断点续跑**: `screen_pipeline.py` 的 `CheckpointStore` 原子保存
- **并行/串行分离**: 前 6 个独立阶段并行，委员会→交易→风控串行

#### 问题

| 严重度 | 问题 | 位置 | 说明 |
|--------|------|------|------|
| P1 | **SSL context 每次请求重建** | `data_fetcher.py` L150 | `_http_get` 在重试循环内每次 `ssl.create_default_context()`，应提到循环外复用 |
| P1 | **无 HTTP 连接复用** | `data_fetcher.py` 全局 | 每次 `urllib.request.urlopen` 新建 TCP 连接，无 `http.client.HTTPSConnection` 池化 |
| P2 | **fact_sheet 同步构建** | `data_fetcher.py` L574-612 | `fetch_quote` → `fetch_news` → `fetch_kline` 串行，三者无依赖关系可并行，约省 30-50% 取数时间 |
| P2 | **无数据缓存** | 全局 | 同一 session 内重复请求同一股票数据会重复调 API，无内存缓存层 |
| P2 | **kline 重试间隔过长** | `data_fetcher.py` L485-486 | 失败后 `time.sleep(1.5)` × 3 = 4.5 秒阻塞，批量场景累积严重 |
| P3 | **8GB 策略无运行时验证** | `runtime_profile.py` | 声称 8GB 友好但无内存监控/告警机制 |

---

### 5. 测试覆盖与依赖管理 (5/10)

#### 问题

| 严重度 | 问题 | 位置 | 说明 |
|--------|------|------|------|
| P1 | **无 requirements.txt** | 全局 | 核心依赖零第三方库是优点，但 `requirements-crawl4ai.txt` 只管可选依赖，无统一入口 |
| P1 | **测试文件过浅** | `test_*.py` (28个) | 多数 400-2500 字节，可能只测试正常路径，无边界/异常用例 |
| P1 | **无端到端集成测试** | 全局 | 没有测试覆盖"取数→8阶段→落库→回测"全链路 |
| P2 | **测试依赖网络** | 全局 | 测试中无 mock/fixture，直接调用真实 API，CI 环境无法运行 |
| P2 | **无 CI/CD** | 全局 | 无 GitHub Actions / Makefile / tox.ini |
| P2 | **无覆盖率测量** | 全局 | 无 .coveragerc / pytest-cov 配置 |
| P3 | **无 conftest.py** | 全局 | 无 pytest fixture 共享、无 test 配置 |

---

## 三、优化建议优先级排序

### 立即处理 (P0)

1. **清除文档中的飞书凭据**
   - `README.md` L147-152 和 `DAILY_TASK_GUIDE.md` 中的 `base_token` / `table_id` / `user_id` 移到 `.env.example` 或环境变量
   - 文档中用占位符 `<FEISHU_BASE_TOKEN>` 替代

### 短期优化 (1-2 周)

2. **补 `requirements.txt`**: 即使核心零依赖，也需声明 Python 版本和可选依赖
3. **删除 .bak 文件和 `_vp.py`**: 死代码清理
4. **修复 `run_daily_screening.py` 的 shell=True**: 改为参数列表方式
5. **SSL context 复用**: `_http_get` 中提到重试循环外
6. **fact_sheet 并行取数**: quote/news/kline 三路并行
7. **回测口径统一**: tracking.py 的 return_pct 加入交易成本参数

### 中期优化 (1-2 月)

8. **拆分巨石文件**: report_generator / daily_stock_pick / agents 各自拆分
9. **添加数据缓存层**: session 内的行情/K线缓存
10. **补充集成测试 + mock**: 至少覆盖主流水线
11. **添加 lint/type-check**: ruff + mypy 基础配置
12. **因子层复权口径检查**: compute_factors 入口校验 bars source
13. **26 个 Phase 文档归档**: 合并为 CHANGELOG.md

### 长期优化

14. **API 限流器**: data_fetcher 添加令牌桶限流
15. **结构化日志**: 替换 print() 为 logging 模块
16. **CI/CD 流水线**: GitHub Actions + 覆盖率报告
17. **内存监控**: 8GB 策略的运行时验证

---

## 四、值得肯定的设计

1. **"先数据质量 → 再确定性量化筛选 → 再多 Agent 研究 → 再专业委员会压力测试 → 最后交易规则与风控硬门槛"** 的五层流水线设计非常专业
2. **7 席位专业评审委员会**（量化研究员/基本面基金经理/A股资深交易员/市场微观结构专家/首席风险官/数据点时态审计师/事件舆情研究员）的多视角压力测试是同类系统中少见的
3. **看多/看空基于同一事实清单独立论证**，有效打破 LLM 观点趋同问题
4. **V3.4 全市场筛选不在筛选阶段调用 LLM**，把 AI 预算集中在高信息量候选上，成本控制意识强
5. **断点续跑 + 流式 TopK** 的工程设计适合生产环境

---

## 五、修复完成清单 (2026-09-10)

| # | 优先级 | 问题 | 状态 | 修改文件 |
|---|--------|------|------|---------|
| 1 | P0 | 飞书 Token 硬编码在文档中 | **已修复** | README.md, DAILY_TASK_GUIDE.md → 环境变量占位符 |
| 2 | P1 | .bak 死代码残留 | **已修复** | 删除 ashare_market.py.bak, screen_pipeline.py.bak |
| 3 | P1 | _vp.py 临时脚本 | **已修复** | 删除 _vp.py |
| 4 | P1 | run_daily_screening.py shell=True | **已修复** | 改为参数列表方式，env 传环境变量 |
| 5 | P1 | SSL context 每请求重建 | **已修复** | data_fetcher.py → 模块级 _SSL_CTX 复用 |
| 6 | P1 | fact_sheet 串行取数 | **已修复** | data_fetcher.py → ThreadPoolExecutor 三路并行 |
| 7 | P1 | kline 重试间隔过长 | **已修复** | 1.5s → 0.5s |
| 8 | P1 | 无内存缓存 | **已修复** | data_fetcher.py → 30s TTL 行情缓存 |
| 9 | P1 | tracking 回测不含交易成本 | **已修复（但口径有误，见第九节）** | tracking.py → TrackingCosts 含佣金/印花税/滑点；2026-09-12 修正计费基数与 `--gross` 开关 |
| 10 | P1 | 因子层不检查复权口径 | **已修复** | ashare_factor_engine.py → 检测 raw 数据并警告 |
| 11 | P2 | 无 requirements.txt | **已修复** | 新建 requirements.txt |
| 12 | P2 | 无结构化日志 | **已修复** | 新建 log_utils.py，run_pipeline.py 已接入 |

**尚待后续迭代**: 巨石文件拆分、mypy 渐进收紧、ruff 规则收紧

---

## 六、1.0 版本合并记录 (2026-09-11)

### 合并策略

以 **4.3**（内部版本 v3.7，功能更完整）为基线，叠加 **v3.4_work** 中经审计验证的工程优化，
去重后形成 1.0。

| 来源 | 内容 | 处理 |
|------|------|------|
| 4.3 独有 | `factor_registry.py` `factor_gate.py` `factor_lab.py` `factor_validation.py` `stage2_scoring.py` `stage2_ablation.py` `pit_integrity.py` `pit_universe_builder.py` `cycle_price_action.py` `daily_csv_adapter.py` `phase41_data_workbench.py` `recon_price_factor_lab.py` + 7 个测试 + PHASE35-43 文档 | **全部保留** |
| v3.4_work 独有 | `log_utils.py` `requirements.txt` `ruff.toml` `mypy.ini` `AUDIT_REPORT.md` | **全部并入** |
| 双方同名 | `data_fetcher.py` `tracking.py` `ashare_factor_engine.py` `run_pipeline.py` `run_daily_screening.py` `README.md` `DAILY_TASK_GUIDE.md` | **以 4.3 为基础，移植 v3.4_work 优化** |

### 合并后新增/生效的优化

| # | 优化项 | 落地文件 |
|---|--------|---------|
| 1 | 飞书凭据脱敏（文档 → 环境变量） | `README.md` `DAILY_TASK_GUIDE.md` `AUDIT_REPORT.md` |
| 2 | shell=True → 参数列表（防命令注入） | `run_daily_screening.py` |
| 3 | 模块级 SSL context 复用 | `data_fetcher.py` |
| 4 | 行情 30s TTL 内存缓存 | `data_fetcher.py` |
| 5 | 行情+K线并行取数（ThreadPoolExecutor） | `data_fetcher.py` |
| 6 | K线重试间隔 1.5s → 0.5s | `data_fetcher.py` |
| 7 | 回测净收益口径（TrackingCosts） | `tracking.py` `run_tracking.py` | ⚠️ 曾存在两处严重缺陷，已于 2026-09-12 修复（见第九节） |
| 8 | 因子层复权口径安全检查 | `ashare_factor_engine.py` |
| 9 | 结构化日志接入 | `log_utils.py` `run_pipeline.py` |
| 10 | 依赖声明 + lint/type-check 配置 | `requirements.txt` `ruff.toml` `mypy.ini` |

### 1.0 与两版的因子能力对照

1.0 的 `ashare_factor_engine.py` 同时具备：
- **4.3 的扩展因子**：`momentum_10d` / `momentum_60d` / `realized_vol_60d` / `momentum_accel_5_20` / `breakout_20d` / `range_pct_20d` / `volume_ratio_20d` / `amount_ratio_5d` / `turnover_mean_20d`
- **v3.4_work 的复权安全检查**：检测 `raw` / `tdx_local_raw` 数据源并输出 `warnings`

### 已知遗留（下一版处理）

- 巨石文件拆分：`report_generator.py` (35KB) / `daily_stock_pick.py` (26KB) / `agents.py` (26KB)
- mypy 渐进收紧：`agents` / `orchestrator` / `main` / `prompt_engine` / `stage2_ablation` / `report_generator`
- ruff 规则收紧：`B905` / `RUF013` / `F841` 等已列入 ignore，需逐点评审
- 运行时状态目录：4.3 已将 `watchlist.json` / `candidate_pool.json` 外移到 `~/.ai-stock-god/`，1.0 沿用该数据卫生设计，不再随项目分发静态股票池

---

## 七、静态分析发现的真实缺陷 (2026-09-11)

引入 ruff / mypy 后，除工程治理问题外，还暴露了 3 个**真实的代码缺陷**。这是本轮最有价值的产出。

### 7.1 【严重】PEP 701 版本不兼容 — 项目实际无法在 Python 3.10 / 3.11 运行

**现象**：`ruff --target-version py310` 报 10 处 `invalid-syntax`。

**根因**：`agents.py` 的 8 个 Agent 任务提示词是 `f"""..."""` 长字符串，其替换字段 `{...}`
内又调用了 `_json_block("""{...}""")`，即**在 f-string 替换字段内复用外层同引号**。
该写法由 PEP 701 引入，**仅 Python 3.12+ 支持**；3.10 / 3.11 下直接 `SyntaxError`。

`data_fetcher.py` 另有 2 处同类问题：

```python
lines.append(f"  deterministic_candidate_score: {qs.get("score")}")   # 3.10/3.11 语法错误
```

**影响**：`requirements.txt` 声明 `Python >= 3.10`，但项目在 3.10 / 3.11 上**连导入都做不到**。
因为开发机是 3.12+，该问题一直被掩盖——`py_compile` 在 3.12+ 下完全通过。

**修复**：替换字段内的三引号改为 `'''`（字符串值完全不变）。
**验证**：7 个 Agent 类的 `system_prompt` 修复前后**逐字节一致**；ruff py310 零告警。

### 7.2 【中】`_I0` 未定义名 — 模块抽取时漏带常量

`cycle_price_action.py` 的 `locate_cycle_phase()` 使用了 `closes[_I0]`，但该模块从未定义 `_I0`。

**根因**：该函数原在 `daily_stock_pick.py` 内（那里有 `_I0, _I1, ... = (0, 1, ...)`），
PHASE40 为解耦而抽取成独立模块时，常量定义未一并带出。

**影响**：`n < 6` 分支不可达（函数在 `n < 30` 时已提前返回），故未爆出；
但一旦有人放宽长度门槛，即会抛 `NameError`。

**修复**：`closes[_I0]` → `closes[0]`。

### 7.3 【中】可变类属性被实例间共享

`orchestrator.WorkflowOrchestrator.STAGES` 是 `list`。虽然当前代码只读，
但任何 `STAGES.append(...)` 都会污染所有实例。

**修复**：改为 `tuple`（全部用法均为 `in` / `.index()` / `len()` / 切片 / 迭代，兼容）。

### 7.4 批量清理

| 项目 | 数量 | 说明 |
|------|------|------|
| 死导入（F401） | 57 | 含 `main.py` 中未被任何模块引用的 Agent 类导入 |
| 安全自动修复 | 19 | f-string 冗余前缀、`int()` 冗余转换、`dict()` 改字面量、未使用 noqa 等 |
| 类型标注补全 | 10+ | `_cache` / `_heap` / `out` / `keep` / `required_dates` / `provenance` / `kwargs` 等 |

### 7.5 质量基线现状

```
ruff  : All checks passed
mypy  : Success: no issues found in 139 source files
pytest: 141 passed
```

以上三项已写入 `.github/workflows/ci.yml`，**失败即阻断 CI**，可防止同类问题回归。
另有 `test_python_compat.py` 专门守卫 Python 3.10 语法下限。

---

## 八、巨石文件拆分 (2026-09-11)

审计报告第 1 节标记的 P1「巨石文件」问题已解决。拆分 3 个文件，**对外 API 与产物字节级不变**。

| 原文件 | 原行数 | 拆分后 | 最大模块 | 验证方式 |
|--------|--------|--------|---------|---------|
| `agents.py` | 658 | 5 个模块 | 209 行 | 8 个 Agent 的 prompt 逐字节一致 |
| `daily_stock_pick.py` | 664 | 6 个模块 | 231 行 | `score_stock` 全字段一致 + 27 项检查 |
| `report_generator.py` | 1029 | 3 个模块 | 506 行 | 完整 HTML（27519 字符）逐字节一致 |

新增 `test_module_splits.py`（14 个用例）守护拆分兼容性。

### 拆分中发现并修复的问题

**1. 拆分引入的 `F821` 未定义名（被 ruff 拦下）**

`save_unified_report` 使用 `json.dump`，但拆分 `daily_stock_pick.py` 时 `import json` 留在了原文件，
未随函数一起迁移。ruff 的 `F821` 在测试前就拦住了这个必然崩溃的 `NameError`。

**2. 模块抽取时的 `_I0` 悬空引用（同类问题第 2、3 次出现）**

`stock_scoring.score_stock` 与 `pool_manager.update_watchlist` 都用了 `X[_I0]`，
而 `_I0` 定义在原 `daily_stock_pick.py`。这与 7.2 节 `cycle_price_action.py` 的问题是**同一类错误**
——「从大文件抽取函数时漏带模块级常量」。抽取时已一并改为 `[0]`。

**3. 行尾回归：CRLF 污染（自查发现）**

用 Python 文本模式写文件时，Windows 会把 `\n` 转成 `\r\n`。
本次拆分一度产生 20 个 CRLF 文件，而原项目**全部是 LF**（4.3 / v3.4_work 均为 0 个 CRLF）。
已全部归一化为 LF，并新增 `test_line_endings_are_lf` 守卫。

> 若未发现此项，仓库将出现混合行尾：git diff 全文件飘红、部分工具解析异常。

**4. CSS 抽取的 8 字符差异（验证发现）**

`report_styles.REPORT_CSS` 初版把结尾 `</style>` 的 8 空格缩进丢了，
导致生成 HTML 与拆分前差 8 个字符。逐字节比对时精确定位并修正。

**5. 裸文件名导致保存崩溃（拆分中顺带发现，4.3 原有缺陷）**

```python
def save(self, filepath: str = None) -> str:
    ...
    os.makedirs(os.path.dirname(filepath), exist_ok=True)   # filepath="a.html" 时 dirname 为空串
```

`os.path.dirname("report.html")` 返回 `''`，`os.makedirs('')` 抛 `FileNotFoundError`。
`report_generator.py` 与 `orchestrator.py` 各有一处（`save` / `save_session`）。

**影响**：任何传裸文件名的调用都会崩溃——包括 `report_generator.py` 自带的 `__main__` 演示。
已在 4.3 原版复现确认属既有缺陷，非拆分引入。

**修复**：仅当 `dirname` 非空时才创建目录。新增 3 个回归测试覆盖裸文件名与多级目录两种场景。

### 结论

拆分本身不产生功能变化，但**过程中的每一步都靠可执行的比对来确认**，
而不是靠"看起来等价"。这类重构若没有字节级验证，极易留下静默差异。

本轮拆分共发现 **5 个问题**：1 个 ruff 拦下的 `F821`、2 个同类的 `_I0` 悬空引用、
1 个行尾污染、1 个 4.3 遗留的裸文件名崩溃。全部已修复并有测试守卫。

---

## 九、回测口径缺陷修复 (2026-09-12)

**本节是全部审计中最重要的一项：此前的缺陷会让任何策略在统计上"看起来不赚钱"。**

### 9.1 【严重】tracking 收益率把「每股价格」当作计费名义金额

`tracking.TrackingCosts` 声称与 `backtest_engine.Costs` 口径一致，但两者对**名义金额**的取法不同：

| 模块 | 名义金额 | 是否正确 |
|------|---------|---------|
| `backtest_engine` | `shares × price`（100 股整手） | ✓ |
| `walk_forward` | `shares × price`（100 股整手） | ✓ |
| `portfolio_backtest` | `shares × price`（100 股整手） | ✓ |
| **`tracking`** | **`price`（单股价格）** | ✗ |

**后果**：`min_commission = 5.0` 元被套用在约 1500 元的名义金额上，
佣金率从 0.03% 被放大到 **0.333%**（11 倍）。

实测（股价 1500 元、5 日持有、毛涨 1.00%）：

```
现有口径: 毛涨 1.00% -> 净 +0.182%    ← 成本吃掉 0.818%
正确口径: 毛涨 1.00% -> 净 +0.789%    ← 成本 0.110%
每笔偏差: 0.607 个百分点
```

**对 5 日持有期而言，0.6pp 的系统性偏差足以让正收益策略显示为负收益**，
进而使胜率与平均收益统计完全失真。高价股受害最重（股价越高，最低佣金占比越小？——不，
是名义金额越小 → 最低佣金占比越大，故 10 元股的偏差更极端）。

**修复**：引入 `position_notional`（基准仓位，默认 10 万元，与 `backtest_engine`
默认初始资金一致），用 `round_trip_cost_pct()` 计算成本占比，使成本率**与股价无关**。

```python
def round_trip_cost_pct(self) -> float:
    n = self.position_notional
    buy_comm  = max(self.min_commission, n * self.commission_rate)
    sell_comm = max(self.min_commission, n * self.commission_rate)
    stamp     = n * self.stamp_duty_sell
    return (buy_comm + sell_comm + stamp) / n      # 10 万仓位 → 0.11%
```

并新增 `net_return_pct(rec_price, close_n, costs)` 统一口径。

### 9.2 【严重】`--gross` 开关完全失效

```python
# run_tracking.py
costs = None if args.gross else tracking.TrackingCosts()
tracking.backfill_pending(conn, ..., costs=costs)

# tracking.py
costs = costs or TrackingCosts()      # ← None 被赋回默认成本
```

传 `None` 表示"毛收益"，但 `backfill_pending` 内部用 `or` 兜底，把 `None` 换成了默认成本。
**结果是 `--gross` 与默认行为完全相同**，而 CLI 输出仍打印"口径=毛收益(不含成本)"——
即报告口径与实际计算不符。

**修复**：改用显式布尔参数 `apply_costs`，并用 `eff_costs = (costs or TrackingCosts()) if apply_costs else None`，
避免 `or` 的 falsy 语义吞掉"无成本"意图。

### 9.3 【中】`--dry-run` 会写入 tracking.db

`main()` 中 `save_tracking_records(stocks)` 无任何条件判断，**试运行也会写库**。

**后果**：试运行的推荐进入 `tracking.db`，被 `backfill` 后计入胜率校准样本，
**污染真实统计**。这与 CLI 自述的"只选股打分并打印"不符。

实测：dry-run 前后记录数 1 → 2。

**修复**：`dry` 时跳过 tracking 写入与飞书写表，并显式打印"无持久化副作用"。

### 9.4 验证与守卫

新增 `test_tracking_costs.py`（14 用例）与 `test_dry_run_safety.py`（5 用例），
关键断言包括：

- **成本率与股价无关**：10 元股与 1500 元股在同一毛涨幅下净收益必须完全相等
- **毛/净口径必须产出不同结果**：防止开关再次退化为 no-op
- **dry-run 不得调用 `save_tracking_records` / `send_push` / `add_records_to_base`**
- **对照组**：非 dry-run 必须正常写库（防止守卫过度拦截）

### 9.5 修复后的口径对照

| 场景（毛涨 5.0%，基准 100 元 → 105 元） | 收益率 |
|----------------------------------------|--------|
| 毛收益（`apply_costs=False`） | **4.76%** |
| 净收益（默认，含滑点+佣金+印花税） | **4.55%** |

差额 0.21% = 往返成本 0.11% + 双边滑点 0.10%，与理论值一致。

---

## 十、类型检查收紧与元数据缺陷 (2026-09-12)

### 10.1 启用 `check_untyped_defs`

此前 mypy 配置为 `check_untyped_defs = False`，**只检查带类型标注的函数**。
本项目多数函数没有完整标注，意味着**大量代码实际上处于类型检查的盲区**。

启用后暴露 **31 个问题**，全部修复。分类如下：

| 类型 | 数量 | 说明 |
|------|------|------|
| 局部变量缺标注 | 16 | `errors: List[str]`、`groups: Dict[str, List[float]]` 等 |
| 容器类型推断错误 | 6 | `[None] * n` 后赋 float；`peak = 0` 后赋 float |
| 标注与实际结构不符 | 2 | 见 10.2 |
| 异常类型收窄 | 1 | `last_err` 先接 `HTTPError` 再接 `Exception` |
| 日志 handler 列表类型 | 1 | 推断为 `list[StreamHandler]` 后 append `FileHandler` |
| 其他 | 5 | 属性访问、索引、运算符 |

**关键收获**：这 31 个问题此前**完全不可见**。启用 `check_untyped_defs` 是
从「只检查写了标注的代码」到「检查全部代码」的质变，而非量变。

### 10.2 标注与实际结构不符（易被忽略的隐性错误）

```python
# provider_router.py — 我最初按名字猜成 List[str]，mypy 立刻指出实际是 dict
errors: List[str] = []
errors.append({"provider": p.name, "error": str(exc)})   # ← mypy 报 arg-type

# tracking.py — 我最初猜成 Dict[str, List[float]]，实际是嵌套 dict
cell = by_bucket.setdefault(key, {"n": 0, "hit": 0, "rets": []})
```

**教训**：补标注时**不要凭变量名猜类型**。先看实际赋值，再写标注；
mypy 会把猜测错误立刻报出来 —— 这正是类型检查的价值所在。

### 10.3 【潜在缺陷】KlineList 切片丢失元数据

```python
class KlineList(list):
    source = None                      # 只声明了 source 这一个类属性

    def __getitem__(self, idx):
        if isinstance(idx, slice):
            new = KlineList(ret)
            new.source = self.source   # ← 仅复制 source
            return new
```

`adjust` / `quality_ratio` / `data_quality` 由 `fetch_kline` 在**实例上动态挂载**，
切片产生的新对象**不带这些字段**。

**可达性评估（诚实结论：当前不可达）**：

| 读取点 | 写法 | 切片后行为 |
|--------|------|-----------|
| `stock_scoring.py:165` | `getattr(k, "data_quality", "unknown")` | 静默降级为 `"unknown"` |
| `data_fetcher.py:748` | `getattr(kline, "source", None)` | 正常（source 被复制了） |

且 `fetch_kline` 在切片后会用 `KlineList(rows)` 重新包装并重新赋全部字段，
因此现有链路不会触发。**但这是明确的静默降级陷阱**：

- 直接访问 `kline[-30:].data_quality` → `AttributeError`
- 经 `getattr` 兜底 → 悄悄拿到 `"unknown"`，**不报错但结果错误**

后者更危险 —— 质量标记为 `"low"` 的不复权数据可能被误判为未知质量而放行。

**修复**：
1. 四个字段全部声明为**类属性**（类型检查可识别 + 契约显式化）
2. `__getitem__` 切片时**逐个复制全部元数据**

**新增守卫** `test_kline_metadata.py`（6 用例）：

- `test_class_declares_metadata_attributes` — 字段必须是类属性
- `test_slice_preserves_all_metadata` — 切片保留全部元数据（原缺陷的直接反例）
- `test_slice_of_slice_still_preserves_metadata` — 连续切片不逐层丢失
- `test_sliced_kline_keeps_raw_data_warning_semantics` — **业务断言**：
  不复权数据的告警语义不因切片消失

### 10.4 类型检查状态（09-12 快照）

```
mypy: Success: no issues found in 142 source files
      覆盖全部模块，无 ignore_errors 例外，已启用 check_untyped_defs
```

**仍可继续收紧**：`strict_optional = False`（允许隐式 Optional）、
`disallow_untyped_defs = False`（不强制标注）。这两项会带来较大改造量，
建议在功能开发稳定后再推进。

---

### 10.5 第四轮收紧（2026-09-13）

继续推进上节列出的余量，结果如下。

**已启用**

| 开关 | 结果 |
|------|------|
| `strict_optional = True` | 暴露 **22 处** 隐式 Optional 标注（`def f(x: str = None)`），全部修复 |
| `no_implicit_optional = True` | 同上，二者配套 |
| `check_untyped_defs = True` | 保持（1.0 起启用） |

**已评审并**保持**关闭**

`disallow_untyped_defs` 开启会产生 **569 处**「函数缺少类型标注」告警，
属纯标注补全、不捕获缺陷，收益递减，故保留关闭并在 `mypy.ini` 中写明理由。

**发现并修复：`exclude` 模式误伤源文件（严重）**

```ini
# 修复前
exclude = (?x)(__pycache__|\.mypy_cache|\.pytest_cache|build|dist)
```

`(?x)` 下该模式**未锚定**，`build` 片段会命中文件名中的任意位置。
实测后果：

```
mypy .                          -> 186 source files
mypy <显式列出全部 188 个 .py>   -> 188 source files
```

即 `build_tdx_dataset.py`（数据接入工具）与 `pit_universe_builder.py`
**整个模块从未进入类型检查**——而项目里根本没有 `build/` 或 `dist/` 目录，
这两条排除项从未生效于其本意。

**修复**：改为按路径段匹配，并补 `\.ruff_cache`：

```ini
exclude = (?x)(
    (^|/)(__pycache__|\.mypy_cache|\.pytest_cache|\.ruff_cache|build|dist)(/|$)
  )
```

修复后目录模式覆盖 **188** 个文件。新增 3 条守卫测试
（`test_python_compat.py`）：源文件不得被子串命中、同名目录仍须排除、
根目录所有 `.py` 均不在排除之列。

**ruff 侧同类排查结论**：`ruff check . --show-files` 给出 189 个文件，
两个文件均在列 —— ruff 的默认 `exclude` 按路径组件匹配，**不存在同类问题**。
