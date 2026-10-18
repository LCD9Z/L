# 证据链三件判定：A5 偏离登记 + A6 契约字段 + A12 拒绝实验入册

> 预注册：[`EVIDENCE_CHAIN_PREREG.md`](EVIDENCE_CHAIN_PREREG.md)（2026-10-18 先注册后动手）。
> 对应 `GITHUB_ASHARE_QUANT_SURVEY.md` §8.7 第 3 档。
> **不产生任何 alpha 结论，不改任何已归档研究的数字。**

## 一、执行总览

| 组件 | 交付物 | 一句话结论 |
|---|---|---|
| A5 · 偏离登记 | 28 份 `*_PREREG*.md` 尾部固定区块 + `tests/test_prereg_deviations.py`（9 项） | 5 条真实偏离入册（今天三个立项）；24 份历史文件如实记「未逐份复核」——**不补写无据的「无偏离」** |
| A6 · 契约字段 | `data_contracts.py` 三字段 + 注册器 + `tests/test_data_contracts.py`（18 项） | 缺字段即 `IncompleteContractError`；3 个有代码依据的源注册；动态爬取源入显式遗产集，**不伪造口径** |
| A12 · 拒绝实验入册 | `REJECTED_EXPERIMENTS.md` + `tests/test_rejected_registry.py`（6 项） | 表一 25 行 / **58 组**，条目数与 `run_multiple_testing_audit.py` 清单逐项对账（import 不硬编码）；另发现**缺陷 #18**（审计标签引用腐烂） |

## 二、组件 A5：偏离登记（判据 E 组）

### 2.1 判据结果

| 编号 | 判据 | 结果 | 复算 |
|---|---|---|---|
| E-1 | 全覆盖 + 表头逐字一致 | ✅ | 28 份全部含行首零列 `## 偏离登记`；`pytest tests/test_prereg_deviations.py -k e1 或首测` |
| E-2 | 行完整（5 非空格、至少一行） | ✅ | `test_deviation_rows_are_well_formed` |
| E-3 | 真实记账（偏离行 ↔ VERDICT 同源） | ✅ | `test_deviations_are_backed_by_verdict`（3 份参数化，关键词交叉） |
| E-4 | 新文件自带 | ✅ | `test_self_carrying_prereg_has_nonempty_block` |

### 2.2 入册的 5 条真实偏离（逐条来源为对应 VERDICT）

| 文件 | 偏离 |
|---|---|
| `DSR_IC_FAMILY_PREREG.md` | `args.out` 改指 `D:/_ext_verify/`（避免覆盖归档证据） |
| `COST_AUTHORITY_AND_EMBARGO_PREREG.md` | ① `embargo_days` 默认值「取自 horizon」→ **0**（跑之前的校准）；② 改造 B 定位「主 pipeline 加 embargo」→「加固零调用方 API」 |
| `DATA_CHANNEL_PREREG.md` | ① 分三批抓取（本机前台上限教训）；② meta 修复增 `meta_repaired_at` 字段 |

未记入的两类（性质不同，不混记）：DSR 的 `caveats` 5→6 与新增 `dsr/psr` 键是
**预期新增键**（预注册 §3.3 要求）；`disclosure_dates_loaded` 176,841→176,830 是
**数据源漂移**（DSR_IC_FAMILY_VERDICT §五）。

### 2.3 过程记账：补登脚本的一个判据坑

补登脚本第一版用**子串**判断「节是否已存在」，被预注册正文里的格式示意
（代码块内缩进的 `## 偏离登记`）骗过 ⇒ `EVIDENCE_CHAIN_PREREG.md` 自身被假跳过；
第二版改 `strip()` 仍被同一行骗过（strip 掉了缩进）。最终判据：**行首零列锚定**
（`line == "## 偏离登记"`）。该判据已固化为守卫
`test_section_detection_is_line_anchored`（植入缩进示意必须判「无节」）——
**判据自身也要被验**。

### 2.4 反向验证

植入「删一份 PREREG 的偏离节」：`test_prereg_deviations` 红，失败信息含
「以下预注册缺少 `## 偏离登记` 节」（特征串命中，无假红信号）；还原复绿。

## 三、组件 A6：契约字段（判据 C 组）

### 3.1 判据结果

| 编号 | 判据 | 结果 | 复算 |
|---|---|---|---|
| C-1 | 向后兼容 | ✅ | `DataProvenance("tdx","pytdx")` 不传新字段可构造；`to_dict` 输出与旧版逐键相同（新字段默认 None 被既有滤 None 语义滤掉） |
| C-2 | 缺字段即失败 | ✅ | 三字段 × {None, 空串} 6 组参数化全抛 `IncompleteContractError`；重复注册抛 `ContractError` |
| C-3 | 注册非空 + 有据 | ✅ | 3 个源字段全非空；`null_policy` 含代码依据关键词（`法定截止日` / `不补造`，与 `resolve_availability` / `disclosure_eastmoney` 行为对应）；未注册查询抛 `UnknownSourceError` |
| C-4 | 遗产显式 | ✅ | `LEGACY_SOURCES` 非空；`validate_all_sources()` 不抛错但出具遗产点名 |

### 3.2 本轮注册的三个源

| name | availability_lag | null_policy |
|---|---|---|
| `cninfo_disclosure` | 公告日当日可用 | 公告日未知 ⇒ 法定截止日兜底 |
| `eastmoney_appointment` | 预约/实际公告日 | `ACTUAL_PUBLISH_DATE` 为空即缺失，不补造 |
| `fundamentals_yjbb` | 报告期 → 公告日由披露日表决定 | 公告日未知 ⇒ 法定截止日兜底 |

**没有注册的**：通达信日线、baostock、腾讯行情——本轮找不到代码/文档依据的
滞后与缺失政策，按预注册禁止项「不伪造数据口径」不入册，留作债务。
`v3_data_bus.py` 两处动态爬取源（source 名来自数据行）同理入 `LEGACY_SOURCES`。

### 3.3 反向验证

植入「`_require_text` 的抛错改成放行」：C-2 参数化红（`DID NOT RAISE`，6 组
一致）；还原复绿。

## 四、组件 A12：拒绝实验入册（判据 R 组）

### 4.1 判据结果

| 编号 | 判据 | 结果 | 复算 |
|---|---|---|---|
| R-1 | 文件落地 + 白名单 | ✅ | `REJECTED_EXPERIMENTS.md` 入 `ROOT_ALLOWED`；根 md 计数 68→71 同步（含本立项预注册+判定） |
| R-2 | 覆盖 | ✅ | `DECLARED_NON_IC_TESTS`（12）与 `DISTINCT_STRATEGY_CONFIGS`（13）**每个标签**都在表一（守卫 import 脚本清单逐项匹配，标签主干去括号） |
| R-3 | 条目数对账 | ✅ | 声明族行数 12 = `len(DECLARED_NON_IC_TESTS)`；策略配置族行数 13 = `len(DISTINCT_STRATEGY_CONFIGS)` |
| R-4 | 参数组数自洽 | ✅ | 25 行均为 ≥1 整数；文档合计 **58** = 各行相加（37+21） |
| R-5 | 反向验证 | ✅ | 见 4.3 |

### 4.2 登记册概况与一条硬结论

- 表一 25 行 = 12 声明族 + 13 策略配置族；表二 7 条路线级证伪
  （H-D1~H-D4、A10、「信号真实但不可变现」、外部复现）。
- 归档审计数值（`reports/multiple_testing_audit.json`）：`n_hypotheses = 23`、
  `n_executions = 32`、策略族 BH(m=6) **拒绝 0**；6 个可机读策略配置的
  中位 p 为 **0.094~0.521**——「负超额是方向性结论，不是统计显著结论」
  从此有逐条可点的登记册。
- **结构性缺口如实标**：策略层面多数实验无 p 值归档，只能逐项声明、
  无法逐项校正（审计 notes 自记）；登记册结论列如实写「无 p 值归档」，
  不伪装成已检验。

### 4.3 反向验证 + 意外收获：缺陷 #18

反向验证：删表一一行 ⇒ R-2/R-3 红（特征串「未入册」命中）；还原复绿。

**意外收获**：R-2 对账时发现 6/12 声明族标签按**旧裸名**引用报告
（`PORTFOLIO_AB_REPORT.md` 等），而这些文件已归档到 `docs/archive/`——
按图索骥会断链。标签无可执行加载 ⇒ 审计数值不受影响；已登记
**HANDOVER §5.3 缺陷 #18**，脚本标签的路径更新须另立小预注册
（改标签会动审计输出文本）。登记册表一已按现实路径登记。

## 五、全量测试与门禁

**终轮（本判定依据）**：

```
命令：python -m pytest tests/ -q --basetemp=D:/_ext_verify/ptmp_ec4
HEAD：e603dd0 之后的工作区（本轮改动未提交，清单见 git status）
时刻：17:1x 起，2m12s
结果：rc=0，1,694 项全部通过（进度点计数 1,694、F/E 字符 0；
      较 DATA_CHANNEL 终轮 1,661 增 33 = 三个新守卫文件 9+18+6）
      输出落盘 D:/_ext_verify/full_suite_ec4.txt
```

另跑：`ruff check .`（**All checks passed**）、
`mypy . --config-file mypy.ini`（**396 文件无问题**，较上轮 +3 新模块）。

**两轮中间失败的处置**（全部是登记/状态滞后，非代码缺陷）：

| 轮次 | 失败项 | 原因 | 处置 |
|---|---|---|---|
| 第 1 轮 | `test_md_relative_links_resolve` | 预注册悬空链接指向尚未落盘的判定 | 写本文件 |
| 第 1 轮 | `test_scripts_registry` ×2 | 新守卫引用 ⇒ `run_multiple_testing_audit.py` 从 `one-off` 升 `active` | 重跑 `gen_scripts_registry.py`（今早同型第二例） |
| 第 2 轮 | `test_root_count_is_reported` | 判定落盘后根 md 70→71，登记值滞后 | 同步 71 + AGENTS.md §4 |
| 第 2 轮 | `test_pending_prereegs_have_no_verdict` | 预注册状态仍是「待执行」但判定已存在 | 状态改「已执行」 |

## 六、守卫证明了什么、没证明什么

**证明了**：结构全覆盖（28/28）、字段强制（缺即抛）、条目对账（12/13 逐项）、
三组反向验证因对的理由红。

**没证明**（如实记账）：

1. **24 份历史 PREREG 的偏离状态是未复核债务**——区块里写的是「未逐份复核」，
   不是「无偏离」。E-3 只覆盖今天三份。
2. **A6 的政策正确性**——守卫只证明「填了且与代码关键词对应」，
   不证明滞后口径本身测准（如「公告日当日可用」是设计口径而非实测）。
3. **A12 结论列的转写保真**——逐条转写自来源文件，但守卫不校验转写是否失真；
  复核者应按「判定/证据文件」列回查。
4. 表二的 H-D1~H-D4 判定引自圆桌报告（deliverables），非独立复算。

## 七、遗留

1. 24 份历史 PREREG 的偏离复核（建议下次 touch 各自文件时顺带补登）。
2. 缺陷 #18：审计标签路径更新（另立小预注册）。
3. A6 剩余源的契约注册（tdx/baostock/腾讯——需先有依据，不伪造）。
4. 下一档：§8.7 第 4 档 A2+A3（PBO + StepM/SPA）、第 5 档 A7（收据升级），
   按用户指示按顺序推进。
