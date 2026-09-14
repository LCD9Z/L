# 工作交接文档

> **项目**：AI股神团队 1.0 · A股多 Agent 智能分析系统
> **仓库**：`https://github.com/LCD9Z/L.git`（**私有**）　**分支**：`main`　**HEAD**：`d76c96b`
> **交接范围**：2026-09-13 ~ 2026-09-14 的工程改造（目录分层 4 轮 + 巨石拆分 3 次 + 数据研究 4 项）
> **配套阅读**：[`WORKLOG.md`](WORKLOG.md)（做了什么）· [`CHANGELOG.md`](CHANGELOG.md)（版本演进）· [`DIRECTORY_LAYOUT.md`](DIRECTORY_LAYOUT.md)（结构全景）

---

## 一、一句话现状

仓库已从「188 个 `.py` 全部平铺在根目录」重构为 **19 个子包 / 67 个入包模块 / 根目录仅 59 个**；
`data_fetcher.py`(807 行)、`tracking.py`(308 行)、`main.py`(402 行) 三个巨石已用**门面模式**拆解，对外 API 零变更。
数据集已修正幸存者偏差（并入 180 只退市股），四项研究全部重跑完成。
**质量门禁全绿**：ruff 全通过 · mypy 228 文件零错误 · pytest 502 passed · 本地 CI 6/6。

---

## 二、环境准备（本机已验证）

| 用途 | 路径 / 命令 |
|------|-------------|
| 项目根 | `C:\Users\T430\Desktop\1.0` |
| 运行 / pytest 用 Python | `C:\Users\T430\AppData\Local\Programs\Python\Python313\python.exe` |
| **ruff / mypy 在隔离 venv 内**（系统 python 里没有） | `C:\Users\T430\.workbuddy\binaries\python\envs\default\Scripts\` |
| 完整本地 CI | `python run_ci.py`（syntax → ruff → mypy → compat → pytest → credentials） |
| 凭据扫描 | `python credential_scan.py`（与 CI 共用同一实现） |
| 推送（绕过失效代理 + GCM 静默失败） | `python <skill>/git_auth_run.py push --remote origin --branch main --no-proxy` |

> ⚠️ **分包这类改动必须在本地跑完 ruff + mypy 再推送**。曾只跑 pytest 就推，
> 结果 `tushare/` 遮蔽第三方库的缺陷是远端 CI 的 mypy 抓出来的，白跑一轮。

---

## 三、目录与导入约定（改动前必读）

```
项目根/
├── *.py          59 个：入口 / 门面 / 核心编排 / 门禁工具 / 未成族单例
├── <19 个子包>/   每个都有 __init__.py（写「管什么 + 共同红线」）
├── scripts/       run_*.py（22 个）
├── tests/         test_*.py（62 个）
└── conftest.py    把项目根 + scripts/ 加入 sys.path
```

- **子包内**同族引用用**相对导入**（`from .schema import ...`）；**包外**一律**绝对导入**（`from track.store import ...`）。
- 文件名**保留族前缀**（`pit/pit_integrity.py`）—— 为 `git mv` 可追溯，改动机械易审。
- 门面包（`fetch/`、`track/`、`console/`）**不要直接依赖**，请继续用 `from data_fetcher import ...` / `import tracking` / `import main`。
- **防回退守卫**：`tests/test_package_layout.py`，由 `PACKAGES` 单一来源推导，新增子包时**只需往 `PACKAGES` 加一行**，其余断言（无根目录平铺副本、无裸旧导入、包内相对导入、真实可导入）自动覆盖。

---

## 四、已完成改造（快速索引）

### 目录分层与巨石拆分

| 类别 | 内容 | 提交 |
|------|------|------|
| 目录分层 | 第一轮：测试/脚本迁出（188→114） | `7c0198e` |
| 目录分层 | 第二轮：5 个低耦合家族入包（→91） | `9a59516` |
| 目录分层 | 第三轮：reporting/runtime/risk/validation（→74） | `98074b5` |
| 目录分层 | 第四轮：7 个内部闭合家族入包（→59） | `4ec6386` |
| 缺陷修复 | `tushare/` 包遮蔽第三方库 | `f92c4ef` |
| 巨石拆分 | `data_fetcher.py` → `fetch/` + 门面 | `9df28ea` |
| 巨石拆分 | `tracking.py` → `track/` + 门面 | `393b352` |
| 巨石拆分 | `main.py` → `console/` + 门面 | `6ea19d2` |
| 文档 | `DIRECTORY_LAYOUT.md`（脚本生成，防漂移） | `9df28ea` |

### 数据质量研究

| 研究 | 结论 | 文档 |
|------|------|------|
| 幸存者偏差量化 | 180 只退市股并入数据集；影响是不复权的 30 倍 | `SURVIVORSHIP_IMPACT_REPORT.md` |
| 四项研究修正重跑 | 基线策略负 Alpha 结论不变；V1 尾部剔除改善不成立 | `RERUN_CORRECTED_REPORT.md` |
| 采样敏感性 | 分散化降标准差 4.2 倍，但不改"无 Alpha"结论 | `SAMPLING_SENSITIVITY_REPORT.md` |
| 口径不一致排查 | 根因是采样数差异；修复硬编码窗口 bug | `CALIBRATION_DISCREPANCY_REPORT.md` |

---

## 五、待办事项（按优先级）

| 优先级 | 事项 | 说明 |
|:---:|------|------|
| 1 | **真实 Alpha 假设（进行中）** | H-C1：IC 层面**强支持**（+0.0913 / t=10.38）；组合层面 A/B：B 在 600/1000 样本两窗口均**显著优于基线**（+16~+41pp，扣费后为正）。**但固定滑点高估 B（偏好小盘+非流动性）、且无基准指数** → **仍未判定存在可实现 Alpha**，对外维持 `ALPHA_NOT_ESTABLISHED`；确定性结论为「反转优于动量」。下一步（另行登记）：动态滑点 + 沪深300 + 多宇宙。禁止参数网格搜索。 |
| 2 | 外部集成真实凭据验收 | 飞书 / 付费模型，需用户提供凭据 |
| 3 | 缓存备份处置 | 9.06 MB 已移出到 `_1.0_cache_backup_20260914-071155/`（**用户决定先观察，暂不删**） |
| 4 | `disallow_untyped_defs` | 569 处纯标注告警，收益递减；当前 `check_untyped_defs` 已覆盖 |
| — | `orchestrator.py`（312 行） | **建议不拆**：核心是 278 行类，拆需 mixin，1.0 已评估「收益递减」 |

---

## 六、踩坑清单（最有价值的部分，务必先看）

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
   WorkBuddy 的 `safe-delete` 钩子清理临时目录超时会污染退出码并吞掉摘要。
   判断真过：**看进度条点号数**，或单独跑一个文件看 `exit=0`。

7. **Edit 工具偶发「返回成功但内容未落盘」**
   关键改动请改用脚本做精确替换 + **回读校验**，不要只信返回值。

8. **PowerShell 特性**
   无 heredoc（`git commit -F -` 不可用，先写文件再 `-F <path>`）；
   `Set-Content -Encoding UTF8` 会加 **BOM + CRLF**（用 Write 工具代替）。

9. **推送链路**
   `.git/config` 里的 `http.proxy=127.0.0.1:10808` 常失效但**直连可用**；
   git ↔ GCM 在私有仓库上会**静默退出 128 且零输出** → 用 `git_auth_run.py --no-proxy` 注入认证头绕过。
   **避免使用 `git rebase`**（曾观测到异常退出后 `.git` 目录消失）。

10. **目录体积疑云**
    「10 MB」里约 8.3 MB 是工具缓存（`.mypy_cache` 占 7.5 MB），**项目真实内容仅 1.11 MB / 284 文件**。
    判断方法：`git ls-files` 统计受控文件体积 = 真实大小，差额即被忽略的本地产物。

11. **等距抽样在旋转下可能不变 —— 又一次静默失效**
    `run_sampling_sensitivity_study.py` 初版用等距抽样 + 偏移量，当 `len/size` 与偏移成整数倍时，
    5 个子样本**完全相同**（对称差 0）。会输出"标准差=0，离散度完美"的假结论。
    改用带种子的确定性洗牌；验证修复后样本间重合约 90/300，真正独立。

12. **退市股数据存在但需主动合并**
    TDX 本地数据只含存活股，退市股数据在 `D:/tdx_dataset/delist/` 下已单独获取。
    运行研究前需确认是否调用 `merge_delisted_into_dataset.py` 合并，否则结果含幸存者偏差。

---

## 七、交接验收清单（接手后先跑一遍）

```powershell
# 1) 静态检查
C:\Users\T430\.workbuddy\binaries\python\envs\default\Scripts\ruff.exe check .        # 期望 All checks passed
C:\Users\T430\.workbuddy\binaries\python\envs\default\Scripts\mypy.exe --config-file mypy.ini .   # 期望 228 文件零错误

# 2) 测试
python -m pytest -q                 # 期望 502 passed

# 3) 完整本地 CI（**推荐：一条命令覆盖全部**）
python run_ci.py                    # 期望 6/6 PASS

# 4) 结构守卫
python -m pytest tests/test_package_layout.py -q    # 覆盖全部 19 个子包
```

预期结果全部通过即表示环境与代码状态一致，可安全继续开发。

> **注**：`run_ci.py` 会自行处理 ruff/mypy 不在系统 Python 的情况
> （回退到隔离 venv，见第九节）。若该回退也失败，设 `WORKBUDDY_PY_ENV`
> 指向装有这些工具的 venv。

---

## 七之二、中断后如何接上（会话恢复流程）

长任务可能在任意时刻中断。按以下顺序重建状态，**不要凭印象继续**：

```bash
cd C:/Users/T430/Desktop/1.0

# ① 看最后提交，确认做到哪一步
git log --oneline -8

# ② 看有无未提交变更（有则说明上次中断在提交前）
git status --short

# ③ 一条命令验证状态是否绿
python run_ci.py
```

然后按顺序读：

| 顺序 | 文档 | 回答什么 |
|:---:|------|---------|
| 1 | 本文件 `HANDOVER.md` | 现状、约定、**踩坑清单**、待办 |
| 2 | [`WORKLOG.md`](WORKLOG.md) | 上一次改造做了什么、为什么 |
| 3 | [`CHANGELOG.md`](CHANGELOG.md) | 版本演进与历次收紧 |

**关键提醒**：

- **本文件的 HEAD 可能已过期** —— 以 `git log` 实际结果为准。
- **踩坑清单（第六节）务必先读** —— 本次已有实例：`cli` 包名与
  `fetch/cli.py` 冲突，被结构守卫在提交前拦下；而"包名不能与既有顶层模块同名"
  这条早在第六节第 1 条写着。
- **未提交变更 = 中断风险**。若 `git status` 非空，先判断这些改动是否完整
  （跑 `python run_ci.py`），再决定提交还是回退。

### 降低中断损失的做法

1. **分小步提交** —— 每完成一个可验证的小改动就跑门禁并提交，
   不要攒成一次大提交。
2. **提交信息写清"为什么"** —— 中断后看提交信息即可重建意图，
   不必重新推理。
3. **改动前先确认工作区干净** —— 否则中断后无法区分"我的改动"与"上次的残留"。

---

## 八、文档索引

| 文档 | 用途 |
|------|------|
| [`README.md`](README.md) | 项目概览、目录树、快速上手 |
| [`WORKLOG.md`](WORKLOG.md) | **本次工程改造的工作日志**（时间线、决策、缺陷、基线） |
| [`CHANGELOG.md`](CHANGELOG.md) | 版本演进（含 PHASE1~43 归档、v4.9 移植、历次收紧） |
| [`DIRECTORY_LAYOUT.md`](DIRECTORY_LAYOUT.md) | 目录全景（脚本生成，含各包红线与留根理由） |
| [`AUDIT_REPORT.md`](AUDIT_REPORT.md) | 静态分析审计报告与风险项 |
| [`MERGE_1.0_REPORT.md`](MERGE_1.0_REPORT.md) | 1.0 合并报告与遗留事项清单 |
| `TDX_DATA_ASSESSMENT.md` / `TDX_EVALUATION_REPORT.md` | 数据性质评估与首次端到端实证 |
| `SAMPLING_SENSITIVITY_REPORT.md` | 采样敏感性 × 持仓分散度实验 |
| `RERUN_CORRECTED_REPORT.md` | 四项研究修正后重跑汇总 |
| `CALIBRATION_DISCREPANCY_REPORT.md` | 口径不一致排查与根因分析 |
| `SURVIVORSHIP_IMPACT_REPORT.md` | 幸存者偏差对因子研究的影响 |
| `DELISTED_UNIVERSE_REPORT.md` | 180 只退市股识别与数据集修正 |
| `ADJUSTED_FACTOR_REPORT.md` | 复权因子对比研究 |
| `ALPHA_HYPOTHESIS_PREREG.md` | 复合反转假设 H-C1 的事前登记（假设/方向/判定标准固定） |
| `CONTRARIAN_HYPOTHESIS_REPORT.md` | H-C1 检验结果与五条限定 |
| `PORTFOLIO_AB_PREREG.md` | 组合层面 A/B 事前登记（口径/窗口/判定标准） |
| `PORTFOLIO_AB_REPORT.md` | A/B 结果与两个推翻性隐患 |
| `MODULE_SPLIT_EVALUATION.md` | `main.py` 拆分评估与决策记录 |
| `docs/archive/` | 历史阶段文档（PHASE*） |
