# 工作日志

> **项目**：AI股神团队 1.0 · A股多 Agent 智能分析系统
> **仓库**：`https://github.com/LCD9Z/L.git`（私有）　**分支**：`main`
> **记录区间**：2026-09-13 17:25 ~ 2026-09-14 07:27（11 次提交）
> **性质**：本文件记录**本次工程改造**做了什么、为什么这么做、以及验证结果。
> 更早的版本演进（PHASE1~43、v4.9 移植等）见 [`CHANGELOG.md`](CHANGELOG.md)。

---

## 一、总览：起点 → 现在

| 指标 | 起点（初始提交） | 现在 |
|------|---:|---:|
| 根目录 `.py` | **188**（全部平铺，零子目录） | **59** |
| 子包数 | 0 | **18** |
| 已入包模块 | 0 | **65** |
| `tests/` 测试文件 | 57 | **61** |
| `scripts/` 可执行脚本 | 16 | **16** |
| pytest | 275 passed | **470 passed + 1 skipped** |
| mypy | 180 文件 | **219 文件零错误** |
| ruff | 19 条规则挂起待评审 | **All checks passed** |
| 远端 CI | 从未在远端跑通 | **5/5 全绿**（py3.10~3.13 + 凭据扫描） |
| 本地 CI 等价器 | 无 | `run_ci.py`（6 步，与 CI 同序） |

---

## 二、提交时间线

| # | 提交 | 时间 | 主题 | 改动量 |
|---|------|------|------|---:|
| 1 | `5f286de` | 09-13 17:25 | Initial commit | 1 file |
| 2 | `4eea44a` | 09-13 17:49 | 初始提交 —— AI股神团队 1.0 | 257 files, +26,078 |
| 3 | `024d482` | 09-13 18:48 | 记录远端 CI 首次通过（遗留事项 #1 闭环） | 2 files, +35 |
| 4 | `2955e9a` | 09-13 20:09 | 研究完整性门禁接入运行时发布路径 | 7 files, +518 |
| 5 | `7c0198e` | 09-13 20:52 | **目录分层第一轮** —— 测试与脚本迁出根目录 | 81 files, +195 |
| 6 | `9a59516` | 09-13 21:34 | **目录分层第二轮** —— 五个库模块家族下沉为子包 | 71 files, +500 |
| 7 | `98074b5` | 09-13 22:20 | **目录分层第三轮** —— reporting/runtime/risk/validation 入包 | 42 files, +303 |
| 8 | `4ec6386` | 09-13 23:08 | **目录分层第四轮** —— 七个库模块家族下沉为子包 | 44 files, +191 |
| 9 | `f92c4ef` | 09-14 00:02 | **修复 `tushare/` 包名遮蔽第三方库的严重缺陷** | 10 files, +47 |
| 10 | `9df28ea` | 09-14 00:35 | **拆分 `data_fetcher.py` 巨石**为 `fetch/` 包 + 门面，并生成目录全景 | 14 files, +1,802 |
| 11 | `393b352` | 09-14 07:27 | **拆分 `tracking.py` 高耦合核心**为 `track/` 包 + 门面 | 12 files, +517 |

> 提交 3、4 属遗留事项清理（CI 远端首跑、门禁接入）；提交 5~11 为本次目录结构改造主体。

---

## 三、四轮目录分层

**方法（贯穿始终）**：用 AST 建全仓库 import 图，统计每个候选家族的**外部入边 / 外部出边**，
按耦合从低到高依次下沉。**划包先看依赖边，再看名字** —— 只选"内部闭合"
（成员不反向 import 根目录其他模块）的家族，避免制造「包 → 根」的反向依赖。

| 轮次 | 下沉家族 | 模块数 | 根目录 `.py` |
|------|---------|---:|---:|
| 第一轮 | 测试 → `tests/`、脚本 → `scripts/` | 76 | 188 → **114** |
| 第二轮 | `pit` `tdx` `corporate` `ashare` `factors` | 23 | 114 → **91** |
| 第三轮 | `reporting` `runtime` `risk` `validation` | 17 | 91 → **74** |
| 第四轮 | `stage2` `alpha` `phase62` `regime` `tushare_client` `notify` `router` | 15 | 74 → **59** |

**约定（已固化为守卫测试）**
- 子包内同族引用用**相对导入**；包外一律**绝对导入**（`from pit.pit_integrity import ...`）。
- 文件名保留族前缀（`pit/pit_integrity.py`）：`git mv` 可追溯，改动机械易审。
- 每个 `__init__.py` 必须写「管什么 + 共同红线」。
- 防回退守卫：`tests/test_package_layout.py`，由 `PACKAGES` 单一来源推导，随包数自动增长。

---

## 四、两次巨石拆分（门面模式）

沿用 1.0 拆分 `agents.py`(658) / `daily_stock_pick.py`(664) / `report_generator.py`(1029) 的既有模式。

### `data_fetcher.py`（807 行）→ `fetch/` 包
| 子模块 | 职责 | 行数 |
|--------|------|---:|
| `transport` | HTTP 传输：SSL 复用 / 缓存 / 令牌桶限流 / 统一 GET | 141 |
| `common` | 公共常量与纯函数 | 132 |
| `quote` | 实时行情（东财 + 腾讯兜底） | 148 |
| `kline` | 历史日K（东财 / 腾讯 / 通达信本地） | 264 |
| `news` | 新闻与事实数据包（含 Crawl4AI 可选增强） | 249 |
| `cli` | 命令行入口 | 47 |
| **`data_fetcher.py`** | **门面**（重导出 29 符号） | 102 |

依赖无环：`transport`/`common` → `quote`/`kline` → `news` → `cli`。

### `tracking.py`（308 行）→ `track/` 包
| 子模块 | 职责 | 行数 |
|--------|------|---:|
| `costs` | 交易成本模型与净收益率换算 | 69 |
| `schema` | 常量与表结构 | 50 |
| `store` | SQLite 持久化 | 72 |
| `stats` | 校准统计（命中判定 / 回填 / 胜率） | 167 |
| **`tracking.py`** | **门面**（重导出 17 符号） | 74 |

依赖无环：`costs`/`schema` → `store` → `stats`。

**做法（保证可审计）**：AST 行区间**机械抽取**（实现字节级不变）→ 跨组依赖按**实际引用**推导
（第一版图省事"全量互导"，直接制造 `transport ↔ quote` 循环导入，已修正）→
各子模块先带完整导入，再由 `ruff --select F401 --fix` 裁掉未使用项（两次共裁 103 处）。

---

## 五、本次发现并修复的缺陷

| # | 缺陷 | 发现方式 | 处置 |
|---|------|---------|------|
| 1 | `run_daily_screening.py` 把 `argv[1]` 当股票 JSON，`--help` 被 `json.loads` 报错 | 脚本 `--help` 冒烟 | 显式处理 `-h/--help` |
| 2 | `test_module_splits.py` 硬编码 `open("runtime_env.py")` 源码路径 | 全量 pytest | 改为从模块对象取 `__file__` |
| 3 | **【严重】`tushare/` 包遮蔽第三方 `tushare` 库**：`import tushare as ts; ts.pro_api()` 命中本项目空包 → 运行期 `AttributeError`（影响 3 个文件） | **远端 CI 的 mypy** | 包改名 `tushare_client/`；新增守卫 `test_no_bare_import_of_package_names` |
| 4 | `tracking._DB_PATH` 由 `__file__` 推导，拆分后会静默迁到 `<root>/track/tracking.db`（旧记录"消失"且不报错） | 拆分前主动审查 `__file__` 派生路径 | 表达式改取两层父目录；新增守卫 `test_db_path_stays_at_project_root` |
| 5 | 门面拆分后 `monkeypatch` 不穿透：`patch.object(data_fetcher, "_crawl4ai_fetch_news_sync")` 失效 | 拆分后全量 pytest | 补丁改打到实现模块 `fetch.news` |
| 6 | 第一版拆分制造循环导入（`transport ↔ quote`） | 导入即失败 | 跨组依赖改为按实际引用推导 |

> 缺陷 1、2 之外，1.0 阶段的静态分析缺陷（mypy `exclude` 未锚定致 2 模块逃检、`stock_scoring.pe_note`
> 死代码等）见 [`CHANGELOG.md`](CHANGELOG.md) 与 `AUDIT_REPORT.md`。

---

## 六、关键决策：刻意未做的事（含理由）

| 项 | 决定 | 理由 |
|----|------|------|
| `orchestrator.py`（312 行） | **不拆** | 核心是**一个 278 行的类**，拆类需改 mixin；1.0 对 `report_generator.py` 做过同类评估，结论「收益递减」（方法换个文件，认知负担未降） |
| 零出边单例（如 `point_in_time`、`log_utils`） | **不强行凑包** | 彼此无依赖边，按名字硬凑属「名义分组」，制造虚假内聚，与项目「不许自欺」原则相悖 |
| `agents_*` | 保持平铺 | 根目录已有门面 `agents.py`，建 `agents/` 包会同名冲突 |
| `real_*` / `daily_*` / `data_fetcher` | 留根目录 | 出/入边过多；其中 `data_fetcher` 已用门面模式拆实现（文件仍在根，但只剩 102 行） |
| 新包命名 | 避开第三方库名 | `tushare/` 遮蔽事故后确立：建包前确认不与第三方/标准库顶层模块同名 |

---

## 七、当前质量基线（复现方式）

```powershell
# 完整本地 CI（与远端同序）：syntax → ruff → mypy → compat → pytest → credentials
python run_ci.py

# 单独执行
C:\Users\T430\.workbuddy\binaries\python\envs\default\Scripts\ruff.exe check .
C:\Users\T430\.workbuddy\binaries\python\envs\default\Scripts\mypy.exe --config-file mypy.ini .
python -m pytest -q
python credential_scan.py
```

| 检查 | 结果 |
|------|------|
| ruff | **All checks passed** |
| mypy | **219 文件零错误** |
| pytest | **470 passed + 1 skipped** |
| 凭据扫描 | 通过 |
| 脚本 `--help` 冒烟 | 16/16 |
| 远端 CI（`393b352`） | **5/5 success** |

---

## 八、遗留事项

1. **未拆的巨石候选**：`main.py`（402，入口，无测试覆盖）、`crawl4ai_fetcher.py`（370，测试覆盖好）—— 按优先级待评估。
2. **缓存备份待处理**：9.06 MB 的缓存/日志已移出项目到 `_1.0_cache_backup_20260914-071155/`（**用户决定先观察，暂不删除**）。
3. **外部集成真实凭据验收**（飞书 / 付费模型）需用户提供凭据。
4. **真实 Alpha 结论**仍缺失：需认证过的全市场 PIT 数据（当前 TDX 数据有幸存者偏差与不复权两项缺陷）。
5. `disallow_untyped_defs` 仍未开启（569 处纯标注告警，收益递减）。
