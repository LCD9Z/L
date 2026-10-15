# 正式入口清单（ENTRYPOINTS）

> **验收标准（整改清单 P2-1）**：**只有一个正式运行入口、一套正式配置和一份权威交接文档。**
> **建立**：2026-10-13　**状态**：首版（**收敛前盘点**）

---

## 一、盘点：当前入口有多发散

| 位置 | 可执行入口数 |
|---|---|
| 项目根目录（含 `__main__`） | **15** |
| `scripts/` 下脚本 | **52** |
| **合计** | **67** |

→ **这是「发散」而非「收敛」**。本文件的目标是**给定权威清单**，
使「哪些是正式的、哪些是一次性的」不再靠猜。

## 二、正式入口（**三个**）

| # | 入口 | 用途 | 触发方式 |
|:--:|---|---|---|
| **E1** | `python -m tdx_native.run_daily` | **每日推荐系统全流程**（生产） | 计划任务 `TDXDaily`（周一~周五 15:30）走 `run_daily.bat` |
| **E2** | `python run_ci.py` | **本地 CI**（syntax/ruff/mypy/compat/pytest/credentials） | 手工，或 CI 工作流 |
| **E3** | `python -m augment.cli` | **可选增强模块**（A 线 LLM 能力：解释/假设/呈现） | 手工；生产侧 `run_daily --with-augment`（**默认关闭**） |

> **规则**：除以上三个之外，**任何脚本都不得被当作「日常要跑的东西」**。
> 需要新增正式入口时，须在本表登记并说明理由。

> **E3 登记理由**（2026-10-15 用户拍板）：E3 与 E1/E2 同属**确定性、可重复调用**的
> 正式能力，但它**不产出结论**——只产出旁注（`claim_tier` 恒为 `non-evidence`），
> 且生产侧默认关闭、失败隔离（不改 E1 退出码）。隔离契约见
> `augment/__init__.py` 红线说明与 `CODE_WIKI/08_A线可选增强模块接入设计.md`。
> 注意：E3 **不得**出现在 `run_daily.bat` 中，除非另行拍板（Q4 当前结论：默认关）。

## 三、研究脚本（**按实验调用，非常规运行**）

| 脚本 | 对应预注册 | 状态 |
|---|---|---|
| `scripts/run_tdx_universe_ic.py` | `CROSS_DECADE_PREREG.md` | 已执行 |
| `scripts/run_factor_orthogonality.py` | `FACTOR_ORTHOGONALITY_PREREG.md` | 已执行 |
| `scripts/run_factor_correlation.py` | （同上，H-ORTH 附属） | 已执行 |
| `scripts/run_w1_split.py` | `W1_SPLIT_PREREG.md` | 已执行 |
| `scripts/run_five_factor_ab.py` | `FIVE_FACTOR_PREREG.md` | 已执行 |
| `scripts/run_portfolio_ab.py` | `PORTFOLIO_AB_PREREG*.md` | 已执行 |
| `scripts/run_xsrc_ic.py` | **`XSOURCE_VALIDATION_PREREG.md`** | **进行中**（P0-1） |
| `scripts/run_adx_*` | `ALPHA_HYPOTHESIS_PREREG.md` | 已执行 |

> **纪律**：研究脚本**必须先有预注册**才允许运行（`AGENTS.md` §2.2）。

## 四、诊断 / 审计脚本

`scripts/diagnose_newstock_pref.py` · `run_cost_model_check.py` ·
`run_ic_diagnosis.py` · `run_signal_diagnosis.py`

## 五、数据拉取脚本

| 脚本 | 用途 | 备注 |
|---|---|---|
| `scripts/fetch_delisted_full.py` | 腾讯 K 线（含退市股） | ⚠️ 单位分板块（`sh688`=股，其余=手） |
| `scripts/fetch_baostock_xsrc.py` | baostock K 线 | 日期分段规避「一页陷阱」 |
| `scripts/fetch_baostock_klines.py` | baostock 早期版 | 已被上者取代 |
| `scripts/run_xsrc_fetch.py` | 分片协调器 | 内部起分片并 join |
| `scripts/run_xsrc_daemon.py` | 低频重试守护 | 应对 IP 级限流 |
| `scripts/fetch_corporate_actions.py` | 权息事件 | — |

## 六、一次性 / 历史工具（**不建议复用**）

### 6.1 根目录历史入口（14 个，全部为「非正式」）

> ⚠️ 这些文件含 `__main__`（技术上可执行），**但不是正式入口**。
> 守卫 `test_entrypoints.py` 要求它们**必须在此登记** ——
> 防「悄悄新增一个入口而不说明」。

| 文件 | 定位 | 备注 |
|---|---|---|
| `agents.py` · `agents_base.py` · `orchestrator.py` · `prompt_engine.py` | **多 agent 框架**（历史） | 与当前 `tdx_native/` 生产链**无关** |
| `llm_client.py` | LLM 调用封装 | 需 `llm_config.json`（不入库） |
| `main.py` · `stock_god.py` | 早期总入口 | **已被 `tdx_native.run_daily` 取代** |
| `crawl4ai_fetcher.py` · `data_fetcher.py` · `public_daily_source.py` | 外部数据抓取 | 一次性/实验 |
| `daily_stock_pick.py` | 早期每日选股 | **已被 `tdx_native.run_daily` 取代** |
| `tracking.py` | 跟踪脚本 | 当前跟踪走 `run_daily` 内部 |
| `credential_scan.py` | 凭据扫描 | 与 P2-2 相关，工具 |
| `phase41_data_workbench.py` | 阶段 4.1 工作台 | 历史 |
| `recon_price_factor_lab.py` | 价格因子实验室 | 历史（`recon_` 前缀=侦察） |

**判定规则**（与 §6.2 同）：

- 名字含 **`agents_*` / `stock_god` / `main` / `orchestrator`** 且
  **不在 §二 表中** → **历史框架，不得当作入口**
- 被 `tdx_native.run_daily` 取代的（`main.py` / `stock_god.py` /
  `daily_stock_pick.py`）**明确标注取代关系**，防止误用旧版

### 6.2 `scripts/` 下一次性工具（34 个）

`scripts/` 下另有 **34 个**，多为**建库 / 转换 / 迁移**类，
属**历史一次性**（如 `build_tdx_dataset.py`、`csv_to_tdx_day.py`）。

**判定规则**：

- 名字含 **`build_` / `migrate_` / `convert_` / `backfill_`** 且
  **不在 §二~§五 表中** → 默认视为一次性
- 一次性脚本**允许存在**（它们是历史凭据），但**不得被当作入口引用**

## 七、正式配置（一套）

| 配置 | 用途 | 是否入库 |
|---|---|---|
| `pytest.ini` | 测试配置 | ✅ |
| `ruff.toml` | 代码风格 | ✅ |
| `mypy.ini` | 类型检查 | ✅ |
| `llm_config.example.json` | LLM 配置**模板** | ✅ |
| `llm_config.json` | LLM 配置**实值** | ❌ **已忽略**（含凭据） |
| `feishu_config.json` | 飞书配置 | ⚠️ 见 P2-2 说明 |

> **规则**：**实值配置一律不入库**，只入库 `.example` 模板。

## 八、权威交接文档（一份）

| 文档 | 定位 |
|---|---|
| **`AGENTS.md`** | ⭐ **唯一权威交接入口**（项目约定 / 纪律 / 禁区 / 目录导航） |

**其余文档的定位**（避免"看起来都权威"）：

| 文档 | 定位 | 是否结论源 |
|---|---|---|
| `STEP1_3_EXECUTION_REPORT.md` | 14 项实验判定正本 | ✅ 结论源 |
| `DAILY_OPERATION.md` | 运维手册 | 操作指引 |
| `DAILY_TASK_GUIDE.md` | 每日任务说明 | 操作指引 |
| `PERFORMANCE_PROTOCOL.md` | 绩效口径规范 | 规范 |
| `DATA_ASSET_REGISTRY.md` | 数据资产登记 | 规范 |
| `*_PREREG.md` / `*_VERDICT.md` | 各实验登记与判定 | ✅ 结论源（按实验） |

> **规则**：新人接手**只读 `AGENTS.md`**，其余按需深入。
> **`AGENTS.md` 必须始终指向最新的结论源**（它已有目录导航节）。

---

## 九、已知缺口（如实记录）

- **67 个入口是历史积累的结果**，本文件**没有删除任何脚本**
  （它们是历史凭据，删除会破坏可追溯性）
- 本文件的作用是**给定权威清单 + 判定规则**，使新增入口必须显式登记
- 守卫 `tests/test_entrypoints.py` 检查：
  ① 正式入口存在且可导入；② 清单覆盖根目录所有 `__main__` 文件

---

**本文件不构成投资建议。**
