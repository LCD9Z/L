# 🤖 AI股神团队 - 多维度智能股票分析系统

> **版本 1.0** — 由 `4.3`（功能基线，内部 v3.7）与 `v3.4_work`（工程优化）合并而成。
> 合并明细见 [`MERGE_1.0_REPORT.md`](MERGE_1.0_REPORT.md)，审计记录见 [`AUDIT_REPORT.md`](AUDIT_REPORT.md)。

> 由 8 个AI Agent组成的精英投资团队，通过多维度分析与结构化辩论，为您提供专业的股票研究报告。
>
> **本目录为 ai-stock-god Skill 的配套工作目录**

## 🚀 快速开始

```bash
# 1) 配置凭据（不要硬编码到文件）
cp .env.example .env && vi .env

# 2) 初始化运行时状态目录（股票池外置）
mkdir -p ~/.ai-stock-god
cp watchlist.example.json ~/.ai-stock-god/watchlist.json

# 3) 安装依赖（核心零依赖，可跳过）
pip install -r requirements.txt
pip install -r requirements-dev.txt   # 可选：测试与 lint 工具

# 4) 运行测试
pytest

# 5) 全市场筛选
python run_pipeline.py --universe universe.jsonl --profile lite
```

## 🎯 三大核心功能

| 功能 | 触发方式 | 输出 |
|------|---------|------|
| 单股深度分析 | 输入股票代码/名称/上传截图 | HTML研究报告 |
| PPT演示报告 | 输入"PPT + 股票名" | HTML格式PPT（10页） |
| 每日选股监控 | 输入"每日选股" | 飞书表格 + 飞书消息推送 |

## 🤖 团队成员（8位Agent）

### 分析师团队
- **📊 基本面分析师** — 财务报表、估值水平、危险信号识别
- **🗣️ 情绪分析师** — 市场舆情、恐惧贪婪指数、资金流向
- **📰 新闻分析师** — 宏观经济、行业动态、公司事件
- **📈 技术分析师** — K线形态、MACD/RSI、支撑阻力位

### 研究员团队
- **🐂 看多研究员** — 挖掘亮点、反驳空头、构建做多逻辑
- **🐻 看空研究员** — 寻找漏洞、反驳多头、构建避险逻辑

### 决策团队
- **🧑‍💼 交易员** — 综合研判、制定策略、确定时机
- **🛡️ 风控官** — 风险评估、一票否决、最终审批

## 📁 文件说明

| 文件 | 说明 |
|------|------|
| `agents.py` | 8位Agent的定义与完整提示词（门面，实现在 `agents_*.py`） |
| `agents_base.py` | Agent 基类 / `DATA_RULES` / `pack_data` / `AnalysisResult` |
| `agents_analysts.py` · `agents_researchers.py` · `agents_decision.py` | 分析师 / 研究员 / 决策三组角色定义 |
| `orchestrator.py` | 工作流编排器，管理分析进度 |
| `report_generator.py` | HTML报告生成器（样式见 `report_styles.py`，Markdown 转换见 `report_markdown.py`） |
| `run_daily_screening.py` | 每日选股执行脚本（写飞书表格 + 推送） |
| `daily_stock_pick.py` | 每日选股主流程（打分见 `stock_scoring.py`，池维护见 `pool_manager.py`） |
| `stock_god.py` | 快速入口脚本 |
| `main.py` | 交互式分析主程序 |
| `data_fetcher.py` | **【L2】数据管道**：抓取真实行情/新闻，输出事实清单（零依赖） |
| `prompt_engine.py` | **【L2】提示词引擎**：把数据包注入 8 角色提示词 + JSON 输出约束 |
| `run_analysis.py` | **【L2】新分析入口**：取数→提示词→分阶段执行/回填 |
| `L1_分析模板.md` | **【L1】可直接复制给模型的优化模板** |
| `tracking.py` | **【L3】回测闭环存储层**：SQLite 记录推荐、N日回填、胜率/评分校准统计 |
| `run_tracking.py` | **【L3】回测 CLI**：log 记录 / backfill 回填 / stats 统计 / report 出报告 |
| `tracking.db` | **【L3】推荐记录数据库**（SQLite，自动创建） |
| `llm_client.py` | **【L4】大模型 API 客户端**：火山方舟 Doubao API（纯标准库，OpenAI 兼容） |
| `llm_config.json` | **【L4】模型配置**：api_key / base_url / model（勿提交到公开仓库） |
| `DAILY_TASK_GUIDE.md` | 每日选股完整执行指南 |
| `feishu_config.json` | 飞书配置文件 |
| `reports/` | 分析报告输出目录 |
| `CHANGELOG.md` | **版本演进记录**（已归并 40+ 个 PHASE 文档） |
| `MERGE_1.0_REPORT.md` | 1.0 合并明细（4.3 + v3.4_work） |
| `AUDIT_REPORT.md` | 多角度代码审计报告 |
| `log_utils.py` | 统一结构化日志（`LOG_LEVEL` / `LOG_FILE`） |
| `tdx_csv_adapter.py` | 通达信日线 CSV 适配器（品种过滤 / code+market 消歧 / 导出契约） |
| `build_tdx_dataset.py` | 原始 CSV → 认证数据集（清洗 + sha256 + PIT 股票池） |
| `run_tdx_evaluation.py` | 在 TDX 数据集上运行真实 Alpha 评估（单窗口） |
| `run_tdx_rolling_eval.py` | 多窗口滚动样本外稳健性检验（审计复用，不调参） |
| `factor_ic_lab.py` | 横截面因子 IC 检验引擎（秩相关 / 无未来函数 / 分位组） |
| `run_factor_study.py` | 9 个经济假设的因子检验 + 子期间稳定性 |
| `run_signal_diagnosis.py` | 策略因子暴露诊断（因果闭环） |
| `run_tail_exclusion_study.py` | 尾部剔除实验（事前设定变体 + 毛净成本对照） |
| `run_universe_replication.py` | 多股票池独立重复验证（分位阈值在完整池上定义） |
| `run_concentration_study.py` | 持仓分散度研究（只改集中度，测量离散度） |
| `survivorship_guard.py` | 幸存者偏差门禁（v4.9 移植，**已接入发布路径**） |
| `corporate_actions.py` | 除权除息调整层（v4.9 移植，向后兼容） |
| `release_gate.py` | 发布门禁裁决层（v4.9 移植，向后兼容；**已接入发布路径**） |
| `pit_event_master.py` · `pit_trading_filter.py` · `pit_research_rows.py` | PIT 事件与交易资格（v4.9 移植） |
| `tdx_lifecycle.py` · `lifecycle_event_evidence.py` · `tdx_inventory.py` | 生命周期证据（v4.9 移植） |
| `factor_blind_test.py` | 因子盲测（v4.9 移植） |
| `repair_tdx_metadata.py` | 重建数据集 sha256 元数据（修复工具） |
| `requirements.txt` · `requirements-dev.txt` | 运行依赖与开发/CI 依赖 |
| `ruff.toml` · `mypy.ini` · `pytest.ini` | lint / 类型检查 / 测试配置 |
| `.github/workflows/ci.yml` | CI：lint + 类型 + 测试 + 凭据扫描 |
| `run_ci.py` | **本地 CI 等价执行器**（零依赖）：按工作流相同顺序跑完 6 项检查 |
| `credential_scan.py` | **凭据泄漏扫描器**（零依赖）：CI 与本地共用同一实现 |
| `watchlist.example.json` | 股票池样例（复制到 `~/.ai-stock-god/watchlist.json`） |
| `docs/archive/` | PHASE8–43 原始阶段文档存档 |

## ✅ 质量校验

```bash
pip install -r requirements-dev.txt
python run_ci.py                # 一条命令跑完全部 6 项检查（与 CI 同一套命令）
```

也可逐项执行：

```bash
ruff check .                    # All checks passed
mypy . --config-file mypy.ini   # Success: no issues found in 188 source files
pytest                          # 329 passed, 1 skipped
python credential_scan.py       # 凭据扫描通过：已扫描 254 个文件
```

> `run_ci.py` 是 **CI 的本地等价执行器**。工作流位于 `.github/workflows/ci.yml`，
> 二者由 `test_run_ci.py` 守护一致性（步骤漂移会让用例失败）。

## 🧩 模块拆分说明（1.0）

原三个巨石文件已按职责拆分，**对外 API 与生成产物字节级不变**：

| 原文件 | 拆分后 |
|--------|--------|
| `agents.py` (658 行) | `agents_base` / `agents_analysts` / `agents_researchers` / `agents_decision` + 门面 |
| `daily_stock_pick.py` (664 行) | `runtime_env` / `stock_scoring` / `pool_manager` / `industry_context` / `lark_notify` + 编排 |
| `report_generator.py` (1029 行) | `report_styles` / `report_markdown` + 生成器本体 |

`agents.py` 仍重新导出全部历史符号，`from agents import FundamentalAnalyst` 等既有写法完全不变。

## 📉 真实数据实证结果（重要）

项目已接入通达信全市场历史数据并完成**首次端到端实证**。

> **结论：内置基线策略在样本外显著跑输基准，未建立 Alpha。**

| 指标 | 策略 | 沪深300 |
|------|------|---------|
| 样本外区间 | 2024-01-02 ~ 2026-09-10（652 交易日） | 同左 |
| 区间收益 | **-23.20%** | **+34.32%** |
| 年化收益 | -9.70% | +12.06% |
| 胜率 / 交易数 | 43.26% / 645 笔 | — |
| 最大回撤 | 44.37% | — |
| 年化超额 | **-19.43%**（t=-1.19, p=0.233, CI 跨零） | — |

**判定**：`ALPHA_NOT_ESTABLISHED`

> ⚠️ **该结果不可外推（2026-09-13 更正）**
>
> 上述数字来自**一个股票池**。跨 4 个独立随机抽样后，基线策略的年化超额区间为
> **[-41.91%, +8.14%]，跨度 50.05pp，标准差 16.02pp** ——
> 策略表现几乎完全由股票池决定。
>
> 根因：持仓仅 5 只、单仓 25%，**抽样噪声主导结果**。
> 此前"负结果跨窗口稳定"的表述已撤回。
>
> 📄 详见 [`UNIVERSE_REPLICATION_REPORT.md`](UNIVERSE_REPLICATION_REPORT.md)

### 多窗口稳健性检验（5 个样本外起点，未调整任何参数）

| 起点 | 对齐日 | 策略 | 基准 | 年化超额 |
|------|-------|------|------|---------|
| 2023-07-03 | 776 | -31.49% | +16.84% | **-15.13%** |
| 2024-01-02 | 652 | -15.71% | +34.32% | **-16.23%** |
| 2024-07-01 | 535 | -4.30% | +30.77% | **-13.21%** |
| 2025-01-02 | 410 | -16.14% | +19.06% | **-19.77%** |
| 2025-07-01 | 293 | -4.70% | +15.36% | **-13.46%** |

**5 个窗口全部负超额（0/5），中位数 -15.13%** —— 负结果跨窗口稳定，非单窗口偶然。
基准在 5 个窗口全部上涨，而策略全部亏损。

**失败机制已定位**：该策略是**纯短期动量追高**（要求当日上涨 + 近期上涨 + 突破新高才买入），
与 A 股显著的**短期反转效应**相悖。这不是实现 bug，也不是调参能解决的问题。

## 🛡️ 研究完整性门禁（v4.9 移植，2026-09-13）

从 v4.9 参考包选择性移植了**代码级门禁**，把此前只能写在文档里的限制变成了强制约束。

### 幸存者偏差门禁

`survivorship_guard.py` 定义 6 项必需证据，**缺失即阻断**：

```python
SurvivorshipAudit(
    pit_universe_ok, lifecycle_ok, delisted_history_ok,
    st_history_ok, suspension_history_ok, corporate_actions_ok)
# 全部为 True 才 ok；否则 status = "INCONCLUSIVE"
```

设计原则：**"Missing evidence is not inferred to be valid."**

对当前 TDX 数据的实测输出：

```
审计结果: INCONCLUSIVE
原因: SURVIVORSHIP DATA INCOMPLETE
是否允许 Alpha 结论: False
```

### 门禁已接入运行时发布路径（2026-09-13）

门禁不只是"有测试覆盖的模块"，而是**流水线出结论前的强制一步**：

| 发布路径 | 接入位置 |
|---------|---------|
| `real_alpha_pipeline.run_real_alpha_pipeline` | 算出统计结论后、返回前，交门禁裁决 |
| `run_tdx_rolling_eval`（多窗口滚动检验） | 每个窗口的 verdict 均经门禁裁决 |

裁决由 `release_gate.gate_alpha_claim()` 完成，它把**统计结论**与**可发布结论**分开：

```python
# 证据不完整 —— 这正是当前 TDX 数据的真实情况
{"statistical_verdict": "ALPHA_NOT_ESTABLISHED",   # 统计结论，原样保留
 "verdict": "INCONCLUSIVE",                        # 可发布结论，被降级
 "alpha_status": "INCONCLUSIVE",
 "missing_evidence": ["lifecycle", "delisted_history", "st_history",
                      "suspension_history", "corporate_actions"]}
```

分开是必要的：**"统计上不显著"与"证据不足无法判定"是两回事**，
混为一谈会把"数据不够"误读成"策略不行"。

> ⚠️ **门禁会主动阻断"基线策略 Alpha"类结论 —— 这是设计意图，不是故障。**
> 它正确反映了数据证据的完备程度。

### 如何提供证据

证据需**显式声明**（键名见 `release_gate.EVIDENCE_KEYS`），未声明即视为缺失：

```json
{
  "pit_universe": true,
  "lifecycle": true,
  "delisted_history": true,
  "st_history": true,
  "suspension_history": true,
  "corporate_actions": true,
  "source": "数据供应商", "as_of": "2026-09-13"
}
```

```bash
python run_tdx_evaluation.py --dataset D:/tdx_dataset \
    --survivorship-evidence evidence.json
python run_tdx_rolling_eval.py --dataset D:/tdx_dataset \
    --survivorship-evidence evidence.json
```

`pit_universe` 由流水线自行校验后如实声明为已具备（否则前面已提前返回）；
其余五项必须来自真实数据源，缺一即降级为 `INCONCLUSIVE`。
额外的溯源字段（如 `source` / `as_of`）不影响判定，会原样保留。

### 除权调整层

`corporate_actions.py` 提供完整公司行动处理（现金分红 / 送股 / 配股 / 拆并股），
可推导后复权因子。实测（10 派 3 元 + 10 送 2 股，前收盘 100 元）：

```
除权参考价 = 80.8333 = (100-3)/1.2   ✓
后复权因子 = 0.808333                ✓
```

### 其他新增能力

| 模块 | 用途 |
|------|------|
| `pit_event_master` / `pit_trading_filter` / `pit_research_rows` | PIT 事件与交易资格 |
| `tdx_lifecycle` / `lifecycle_event_evidence` / `tdx_inventory` | TDX 生命周期证据 |
| `corporate_action_provider` / `corporate_action_ingest` | 公司行动数据接入 |
| `factor_blind_test` | 因子盲测（流式，无未来函数） |
| `public_daily_source` | 公开日线数据源 |

📄 详见 [`V49_REFERENCE_ASSESSMENT.md`](V49_REFERENCE_ASSESSMENT.md)

## 🔬 因子假设检验（经济逻辑驱动）

在真实数据上检验了 9 个**有经济逻辑支撑**的因子假设（横截面 Spearman 秩 IC，
每 5 日调仓 / 前瞻 5 日 / 无重叠，242 期，平均截面 1,431 只）。

**7 个假设获强支持（|t| ≥ 3.36）**：

| 因子 | IC均值 | t | 假设 |
|------|--------|---|------|
| `max_ret_20` 20日最大单日涨幅 | -0.0734 | **-7.64** | MAX 效应（博彩偏好） |
| `log_amount_20` 均成交额 | -0.0697 | **-7.07** | 规模/流动性溢价 |
| `vol_20` 20日波动率 | -0.0733 | **-6.03** | 低波动异象 |
| `ret_20` 20日收益 | -0.0549 | **-5.59** | 中期反转 |
| `vol_ratio` 量能放大 | -0.0346 | **-5.46** | 换手异象（Miller 1977） |
| `amihud_20` 非流动性 | +0.0387 | **+3.78** | 非流动性溢价 |
| `ret_5` 5日收益 | -0.0300 | **-3.36** | 短期反转 |

**因果闭环 —— 已完整解释策略为何失败**：

策略选股落在 `ret_5` 的 **0.863** 分位、`ret_20` 的 **0.801** 分位，
即精确买在两个负 IC 因子的**最差尾部**。选股组合每期跑输全池 **0.53 个百分点**
（年化约 -27%，未扣成本），与实测的 -15%~-20% 年化超额方向一致。

**两个结构性发现**：

1. 反转/波动类因子是**尾部效应**（Q1~Q4 全为正，仅 Q5 转负），
   而规模与非流动性因子**严格单调**且价差最大（Q5-Q1 达 -0.763% / +0.565%）
2. 策略的波动率、规模、非流动性暴露**接近中性**（0.42~0.49）——
   **问题不是"买了高波动股"，而是纯粹的动量追高**

**子期间稳定性**：两个互不重叠窗口（2021-08~2023-12 / 2024-01~2026-09）
全部 6 个因子符号一致，多数在两期均显著。

📄 详见 [`FACTOR_HYPOTHESIS_REPORT.md`](FACTOR_HYPOTHESIS_REPORT.md)

## 🔧 建设性验证：尾部剔除实验（事前设定）

把因子结论转化为**单一、事前设定**的修改（不扫参数、不改阈值、不改持仓周期）：

| 变体 | 修改 | 年化超额均值 | 为正窗口 | 回撤均值 |
|------|------|------------|---------|---------|
| V0 基线 | — | -15.56% | 0/5 | 38.97% |
| **V1** | 剔除 `ret_20` 最高 20% | **+4.40%** | **5/5** | **22.58%** |
| V2 | V1 + 剔除 `vol_ratio` 最高 20% | +8.44% | 5/5 | 15.81% |

**并做了两个股票池口径的对照（仅 54/400 重合），意外构成稳健性检验：**

| 指标 | PIT 口径 | 全目录口径 | 一致性 |
|------|---------|-----------|--------|
| V1 超额改善 | +19.96pp | +3.37pp | ✅ 同号 |
| **V1 回撤改善** | **-16.39pp** | **-14.34pp** | ✅ **幅度接近** |
| **V2 超额 vs V1** | **+4.04pp** | **-4.32pp** | ❌ **方向相反** |

**可复现**：V1 优于 V0（超额/回撤/胜率全部改善），**回撤降 14~16pp 最稳健**
**不可复现**：V2 的相对优劣随股票池翻转 → 已撤回此前"叠加剔除有害"的结论

⚠️ **成本拖累 25~36pp**（毛 17.7~73.8% → 净 -15.7~+39.5%）→ 毛收益无参考价值。

⚠️ **这是样本内结果**（因子与规则在同一数据上识别+验证），**不能作为策略有效性证据**。

📄 详见 [`TAIL_EXCLUSION_REPORT.md`](TAIL_EXCLUSION_REPORT.md)

## 🔁 多股票池重复验证（方法论上的关键一课）

在 **3 个额外独立随机抽样**（共 6 组对照）上复现后，结论需收窄：

| 结论 | 复现情况 | 处置 |
|------|---------|------|
| **回撤改善** | **6/6 成立，均值 -13.16pp** | ✅ **保留** |
| 超额改善 | 5/6 为正，区间跨 21.5pp | ⚠️ 不可依赖 |
| 胜率改善 | 未做独立复现 | ⚠️ 降级为观察 |

**更根本的发现**：基线 V0 在 4 个独立抽样上的超额区间为
**[-41.91%, +8.14%]（跨度 50pp）** —— 策略表现几乎完全由股票池决定。

**根因**：持仓仅 5 只、单仓 25% → **抽样噪声主导结果**，
策略逻辑的贡献被淹没。一个具有真实稳健 Alpha 的策略不会因换抽样而变动 50pp。

**教训**：同一时段的多个"窗口"**共享同一股票池**，不构成稳健性检验。
真正的检验必须更换股票池。报告结论前应在 ≥3 个独立抽样上复现，
并报告**离散度**而非仅均值。

📄 详见 [`UNIVERSE_REPLICATION_REPORT.md`](UNIVERSE_REPLICATION_REPORT.md)

## 🎯 持仓分散度研究（转折点）

既然集中度是抽样噪声的根因，直接验证：**提高分散度能否降低噪声？**
（只改集中度，信号/阈值/周期/成本全部不变）

| 变体 | 持仓/单仓 | 超额均值 | **标准差** | **区间跨度** | 回撤均值 | 交易数 |
|------|----------|---------|-----------|------------|---------|--------|
| C5（基线） | 5 / 25% | -30.39% | **14.22** | **33.89pp** | 48.40% | 612 |
| C10 | 10 / 10% | -20.45% | **1.15** | 2.81pp | 33.24% | 1,142 |
| **C20** | 20 / 5% | -14.68% | **1.03** | **2.24pp** | 21.68% | 1,903 |
| C30 | 30 / 3.3% | -12.74% | 2.69 | 6.32pp | **16.71%** | 2,392 |

**核心发现**：

1. **集中度确实是抽样噪声的根因** —— 5 只扩到 10 只，离散度降 **12 倍**（14.22 → 1.15）
2. **分散后结果恢复可解释性** —— 标准差降到 1~3pp，小于典型效应量
3. **基线策略在分散配置下稳定跑输约 12~15%（年化）**
4. **回撤随分散度单调下降** —— 48.40% → 16.71%（**-31.69pp**）
5. **最优分散度在 C20 附近**；C30 反而略回升（小池过度分散会带来新不稳定）

**代价**：交易数增加 **3.91 倍** → 成本敏感性加剧，采用高分散前须做成本敏感性分析。

**这是本系列实验的转折点**：此前噪声（33.89pp）远大于效应量，继续做策略实验无意义；
现在噪声压到 1~3pp，**信噪比首次可用**。

📄 详见 [`CONCENTRATION_REPORT.md`](CONCENTRATION_REPORT.md)

📄 详见 [`TDX_EVALUATION_REPORT.md`](TDX_EVALUATION_REPORT.md)（评估 + 稳健性检验 + 机制分析）
与 [`TDX_DATA_ASSESSMENT.md`](TDX_DATA_ASSESSMENT.md)（数据性质与四项局限）。

### 数据接入工具

```bash
# 原始 CSV → 认证数据集（过滤品种 + 清洗 + sha256 + PIT 股票池）
python build_tdx_dataset.py --src D:/tdx_daily_all.zip --out D:/tdx_dataset \
    --min-rows 600 --max-stocks 1500 --benchmark 000300

# 单窗口评估
python run_tdx_evaluation.py --dataset D:/tdx_dataset --oos-start 2024-01-01

# 多窗口稳健性检验（审计只做一次后复用数据）
python run_tdx_rolling_eval.py --dataset D:/tdx_dataset --max-stocks 400
```

## 🚀 L1/L2 优化用法（推荐）

系统底层的模型调用方式已升级，核心原则：**先喂真实数据、再要模型判断**，杜绝"凭记忆编数字"。

### L1 · 零代码：用优化模板对话

```bash
python data_fetcher.py 600519          # 先取真实数据包
```
把输出的数据包粘贴进 `L1_分析模板.md` 的模板，发给模型即可获得
带来源标注、JSON 结构化、多空对抗的分析结果。

### L2 · 数据管道 + 提示词引擎

```bash
python run_analysis.py 600519          # 自动取数 + 生成 8 阶段提示词
python run_analysis.py 600519 --stage analyst_fundamental     # 单阶段提示词
python run_analysis.py 600519 --stage decision_trade --results 结果.json  # 裁决阶段引用前序结果
```

特点：
- `data_fetcher.py` 自动抓取实时行情（东财/腾讯双源降级）+ 近期新闻，无需任何第三方库；
- 每个角色提示词内置【数据包】+【铁律】（禁止编造、标注来源、强制 JSON 输出）；
- 看多/看空基于同一事实清单**独立**论证（含证伪条件），打破观点趋同；
- 交易员/风控以数据包为事实基准，对引用不存在数据的观点标注【数据存疑】。

## 🔄 L3 · 回测闭环（校准模型有效性）

把每一次模型推荐记录入库，N 个交易日后自动用**真实收盘价**回填，按月统计胜率、
按建议档位/评分区间校准——验证"模型到底准不准、什么档位/评分更可信"。

### ① 记录推荐

```bash
# 手动记录一条推荐
python run_tracking.py log --code 600519 --horizon 5 --stance 看多 --score 7 --logic "多空独立论证后看多"

# 从风控/交易决策 JSON 自动提取（08_risk.json / 07_trade.json）
python run_tracking.py log --json reports/xxx/08_risk.json --horizon 5

# 分析入口直接落库（做完全流程后）
python run_analysis.py 600519 --track --results reports/xxx/结果.json --horizon 5
```

### ② 回填真实涨跌

```bash
python run_tracking.py backfill          # 自动拉取推荐日后 N 个交易日真实收盘价
```

### ③ 统计与校准

```bash
python run_tracking.py stats             # 按 周期×档位 胜率 / 按 评分档 平均收益
python run_tracking.py report --out reports/tracking_report.json   # 输出校准报告 JSON
```

数据口径：
- 回填价格来自**东方财富历史日K**（前复权），失败自动兜底**腾讯历史K线**，均为真实行情；
- 胜率：看多（含强烈看多）N 日收益>0 命中；看空（含强烈看空）N 日收益<0 命中；中性不计；
- 样本至少 20~30 条再下结论，样本过少时只作参考。

## 🤖 L4 · 全自动（API 化）

把"人工粘贴给模型"升级为**直接调用大模型 API**，一条命令跑完
「取数 → 8 阶段分析 → 汇总落盘 → 决策落库(回测)」全自动流水线。

### 前置：开通模型

1. 打开火山方舟控制台 https://console.volcengine.com/ark
2. 「开通管理」中开通一个模型（如 Doubao-Seed-1.6 / 1.5-Pro 系列）
3. 把 API Key 写入 `llm_config.json` 的 `api_key`，`model` 填你开通的模型名
   （也可创建「在线推理」接入点，把 `ep-xxx` 填到 model 字段）

### 使用

```bash
# 单股全自动（取数→调模型→8阶段→落盘→决策落库）
python run_analysis.py 600519 --auto

# 多股票并行顺序执行 + 落库
python run_analysis.py 000017 --auto --codes 600519,000017 --horizon 5

# 不落库 / 换模型 / 调整温度
python run_analysis.py 600519 --auto --no-track --model doubao-1-5-pro-32k-250115 --temp 0.5
```

产物：`reports/{code}_auto_{时间戳}/`（00_数据包.txt、01~08 各阶段 JSON、results.json 汇总）。

幂等：同一 代码+推荐日+周期 不会重复落库；决策结果自动进 `tracking.db` 参与 L3 回测。

## 🔧 飞书配置

所有凭据通过环境变量注入（见 `.env.example`），**不要**把真实 token 写进代码或提交到 Git。

- **多维表格**：AI股神-每日股票监控（链接从 `FEISHU_BASE_URL` 读取）
- **Base Token**：从环境变量 `FEISHU_BASE_TOKEN` 读取
- **Table ID**：从环境变量 `FEISHU_TABLE_ID` 读取
- **定时任务**：每天 08:30 自动执行
- **推送用户**：从环境变量 `FEISHU_NOTIFY_USER_ID` 读取

```bash
export FEISHU_BASE_TOKEN="<your_base_token>"
export FEISHU_TABLE_ID="<your_table_id>"
export FEISHU_BASE_URL="https://my.feishu.cn/base/<your_base_token>"
export FEISHU_NOTIFY_USER_ID="ou_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
```

## 📊 分析评分标准

| 评分区间 | 等级 | 说明 |
|---------|------|------|
| 9-10分 | 极佳 | 非常优秀，强烈推荐 |
| 7-9分 | 优秀 | 表现良好，建议关注 |
| 5-7分 | 中性 | 好坏参半，观望为主 |
| 3-5分 | 较差 | 问题较多，谨慎对待 |
| 0-3分 | 极差 | 严重问题，坚决回避 |

### 风险等级
| 评分 | 等级 |
|------|------|
| 1-3分 | 低风险 |
| 4-6分 | 中风险 |
| 7-8分 | 高风险 |
| 9-10分 | 极高风险 |

## 🎨 输出风格

- **HTML报告**：深色主题 + 卡片布局 + 量化评分系统
- **PPT报告**：Privy Editorial金融编辑风格 + 数据可视化
- **飞书表格**：15个字段完整记录 + 5类选股板块

## 🚀 Phase 31 / V3：专业数据与量化增强

V3 在 V2 的 Crawl4AI、PIT、A股交易规则和专业评审委员会之上，增加统一 Data Bus、Provider 降级、Quant Skill 路由和确定性因子层。第三方项目只作为能力参考，不直接复制运行时代码。

核心模块：
- `data_contracts.py`：统一行情/新闻/数据溯源契约；
- `provider_router.py`：数据源优先级与故障降级；
- `quant_skill_router.py`：量化技能路由；
- `ashare_factor_engine.py`：LLM 前确定性因子计算；
- `v3_data_bus.py`：把现有 V2 数据管道转换为统一 DataBundle；
- `PHASE31_V3_QUANT_DATA_UPGRADE.md`：本轮升级说明（见 `docs/archive/`）。

V3 原则：**先数据质量 → 再确定性量化筛选 → 再多 Agent 研究 → 再专业委员会压力测试 → 最后交易规则与风控硬门槛。**

## ⚠️ 免责声明

本系统生成的所有分析报告仅供研究参考，不构成任何投资建议。
投资有风险，入市需谨慎。

---

**Skill名称**：ai-stock-god
**工作目录**：/Users/wudengyao/ai-stock-god/

## Phase 5: Portfolio-level historical validation

New modules:
- `historical_universe.py`: explicit point-in-time universe helpers; does not silently treat today's universe as historical.
- `portfolio_backtest.py`: multi-stock portfolio walk-forward backtest with T+1 open execution, 100-share lots, transaction costs, position limits, limit-up buyability checks, cash accounting and portfolio equity curve.
- `run_portfolio_backtest.py`: CLI runner.

Important limitation: a valid all-market historical test still requires point-in-time constituent/universe data, including delisted stocks and historical ST/suspension status. Do not interpret results from a current watchlist as a full-market proof of statistical edge.

## 📬 Phase 6：飞书分析结果自动推送

Phase 6 保留并升级了飞书功能。每日选股仍可写入飞书多维表格；单股多 Agent 深度分析完成后，`main.py` 会自动发送分析摘要到飞书。

### 安全配置

不要再把真实 Token 或 User ID 打包进项目。复制 `.env.example` 为 `.env`，或在运行环境中设置：

- `FEISHU_NOTIFY_USER_ID`：接收分析结果的飞书用户 ID
- `FEISHU_NOTIFY_CHAT_ID`：可选，发送到群聊
- `FEISHU_BASE_TOKEN`、`FEISHU_TABLE_ID`：每日选股写入多维表格时使用
- `FEISHU_BASE_URL`：完整表格链接

系统优先读取环境变量，旧版 `feishu_config.json` 仅作为非敏感配置兼容入口。

### 推送内容

- 股票名称与代码
- 基本面、情绪面、消息面、技术面评分
- 交易建议与信心评分
- 风控结论与风险评分
- 关键分析摘要
- 本地 HTML 报告生成状态

> 飞书推送失败不会中断分析和报告生成。

## Phase 8 + Phase 9（行业强度与真实回测验证）
- `industry_strength.py`：基于截至评估日可获得的价格数据，对行业进行 5/20/60 日相对强度排名；不使用未来数据。
- `regime_backtest_report.py`：补充 CAGR、波动率、Sortino、基准超额收益，以及强势/震荡/弱势市场分段表现。
- 行业映射必须使用历史时点（point-in-time）分类；若使用今天的行业分类回测历史，会引入分类幸存者偏差。
- 回测报告应把“样本外表现”和“全样本表现”分开，且不能把年化、夏普等统计指标误解为未来收益保证。
- 飞书推送模块继续保留；生产环境请仅使用环境变量保存凭据。

## Phase 13 validation additions
See `docs/archive/PHASE13_AUDIT_AND_UPGRADE_REPORT.md`. New modules: `benchmark.py`, `strategy_validation.py`, and `health_monitor.py`. Portfolio backtests optionally accept `universe_snapshot_map` for point-in-time candidate filtering.


## Phase 14–20
See `docs/archive/PHASE14_TO_PHASE20_REPORT.md` for continuous validation upgrades.

## Phase 31.1 / V3.1：A股交易结构与候选预筛

V3.1 进一步锁定中国 A 股市场：板块识别、分层涨跌幅、T+1、停牌硬门槛、涨停/跌停与炸板结构、确定性候选预筛，并修正 V3 数据总线对 K 线字段的读取。

原则：**逐日交易状态优先，机器硬门槛优先于 LLM，数据不足不补造。**


## Phase 32 / V3.2：A股资金与事件数据层

已加入 A 股资金流、龙虎榜、公告/业绩、解禁/股东交易、回购的统一事件层、PIT 过滤、全市场候选预筛接口，以及可选 TuShare 真实数据适配器。缺失数据保持缺失，不生成虚假数字。

## Phase 33：8GB 运行时优化（2026-09-06）

本项目默认按 **8GB RAM 级别电脑**设计运行时策略：
- `balanced` 为默认档：最多 4 个并发 LLM HTTP 请求，不启本地大模型进程；
- 前 6 个相互独立的分析阶段并行执行，委员会→交易→风控保持串行依赖；
- 分析师/研究员/委员会/决策阶段分别设置较小的结构化输出上限，避免无意义长输出；
- 因子窗口默认 60 日，`lite` 可降到 40 日；
- Crawl4AI 仍保持可选，不启用时不会拉起浏览器；
- 可用 `--profile lite` 进一步压缩耗时/资源，`--profile full` 才扩大分析预算。

推荐：8GB 电脑直接使用 `balanced`；如果同时开着浏览器、IDE、数据库等程序，使用 `lite`。


## Phase 43
Supports real daily-file source adaptation for one-file-per-trading-day OHLCV datasets and a memory-bounded reconnaissance path. Final Alpha claims still require certified PIT data and OOS validation.


Current release: v4.3 — real daily-file adapter + memory-bounded price-factor reconnaissance. Final Alpha claims remain blocked until PIT and OOS requirements are satisfied.
