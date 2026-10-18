# 证据链三件预注册：A5 偏离登记 + A6 契约字段 + A12 拒绝实验入册

> **建立**：2026-10-18　**状态**：**已执行** —— 判定见
> [`EVIDENCE_CHAIN_VERDICT.md`](EVIDENCE_CHAIN_VERDICT.md)。
> 写于 2026-10-18，**先注册后动手**（AGENTS.md §2.2）。
> 判定落 [`EVIDENCE_CHAIN_VERDICT.md`](EVIDENCE_CHAIN_VERDICT.md)。
>
> 三项全部来自 `GITHUB_ASHARE_QUANT_SURVEY.md` §8.7 优先级表的**第 3 档**
> （「A5 + A6 + A12：偏离登记 / 契约字段 / 拒绝实验入册 —— 都是文档级改动，
> 但直接决定证据链能否被外人复核」）。第 1/2/6 档（A1 DSR 接线、A4 阳性对照、
> A11 embargo）已于 2026-10-18 上午完成；第 4/5 档（A2+A3、A7）另册登记。
>
> ⚠️ 本立项**不产生任何 alpha 结论，不改任何已归档研究的数字**。
> 产出是三条「让证据链可被外人复核」的机制及其守卫。

## 一、立项背景与三项的关系

| 项 | 缺口（survey 原文） | 本立项交付 |
|---|---|---|
| A5 | 预注册无偏离登记——一旦执行中调整了窗口/样本/阈值，**读者无从知道** | 每份 `*_PREREG*.md` 尾部固定五列偏离区块 + 结构守卫 |
| A6 | `data_contracts.py` 手写 dataclass 缺三个字段 | `DataProvenance` 补 `availability_lag` / `null_policy` / `source_version` + 来源注册器（缺字段即校验失败） |
| A12 | 拒绝的实验未系统入册 | 根目录 `REJECTED_EXPERIMENTS.md` 登记册，条目数与 `run_multiple_testing_audit.py` 的计数来源对账 |

三件共享同一条主线：**证据链的每个环节都要能被第三方独立复核**——
A5 管「执行是否忠于注册」、A6 管「数据何时可用/缺失怎么办」、A12 管「试过什么、拒了什么」。

## 二、作用对象检查（AGENTS.md §8 纪律，动手前必做）

| 检查项 | 命令 / 依据 | 结果 |
|---|---|---|
| PREREG 总量 | `ls *_PREREG*.md \| wc -l` | **27 份**（含 `ALPHA_HYPOTHESIS_PREREG_HD1~4` 四个变体） |
| 既有偏离区块 | `grep -l 偏离登记 *_PREREG*.md` | **0 份**——从零建立 |
| 偏离素材（今天三个立项） | 读三份 VERDICT | DSR：`args.out` 改指仓库外；COST：`embargo_days` 默认值改 0 + 改造 B 定位调整；DATA_CHANNEL：分三批抓取 + meta 修复增字段（逐条见 §三.3） |
| `DataProvenance` 现状 | 读 `data_contracts.py` | 有 `source/provider/retrieved_at/published_at/asof/source_url/content_hash`；**无** A6 三字段 |
| 契约构造点 | `grep -n "DataProvenance(" *.py` | 仅 `v3_data_bus.py` 两处，source 名**来自数据行**（动态爬取源）⇒ 无证据不伪造口径，入遗产集 |
| PIT 消费方口径 | 读 `pit/pit_fundamentals.py` | `resolve_availability`：公告日未知 ⇒ 法定截止日兜底 ⇒ 两个披露源的 `null_policy` 有代码依据 |
| A12 计数来源 | 读 `scripts/run_multiple_testing_audit.py` | `DISTINCT_STRATEGY_CONFIGS`（13）、`DECLARED_NON_IC_TESTS`（13）、`STRATEGY_SOURCES`（6 配置）、`SOURCES`（2 族）——登记册须与这四个清单对账 |
| 根 md 现状 | `tests/test_doc_layout.py` 登记值 | **68 份**；新增登记册 ⇒ 同步改 69 并在 AGENTS.md §4 记理由 |
| 路线级证伪素材 | README / deliverables / CROSS_DECADE_VERDICT | H-D1~H-D4 全部不成立；A10 中性化证伪；「信号真实但不可变现」；外部 `wangpage/quant-ashare` 独立复现 |

**关键判断**：A6 只注册**有代码依据**的源。通达信日线、baostock 等源的
滞后/缺失政策本轮不注册——没有证据的口径不写，入债务清单。

## 三、组件 A5：预注册偏离登记（判据 E 组）

### 1. 口径（事前固定）

- 每份 `*_PREREG*.md`（27 份）尾部追加固定节：

  ```
  ## 偏离登记

  | 项目 | 预注册值 | 实际值 | 理由 | 影响 |
  |---|---|---|---|---|
  | … |
  ```

- **无偏离**时写一行 `| （无登记偏离） | — | — | 执行期未修改已登记判据 | 无 |`；
  **有偏离**逐行登记；本轮未逐份复核的历史文件写
  `| （历史执行） | — | — | 本轮未逐份复核；如执行期发生过口径修改，须在下次 touch 该文件时补登 | — |`。
- 本预注册建立时即含本区块（新文件自带，不做追溯补丁）。
- **偏离 ≠ 缺陷修复**：只登记「对已注册口径/判据的修改」；缺陷修复记 HANDOVER §5.3。
- 判据被**事前修改**（动手前发现设计问题并改判据）也算偏离，理由栏须写明
  「跑之前改的」（COST 立项 §四 即此形态）。

### 2. 判定标准（事前固定）

| 编号 | 判据 | 通过条件 |
|---|---|---|
| E-1 | 全覆盖 | 28 份 PREREG（27 既有 + 本预注册自身）全部含 `## 偏离登记` 节，表头五列逐字一致（守卫 `tests/test_prereg_deviations.py`） |
| E-2 | 行完整 | 每行恰好 5 个单元格且非空（`—` 为合法占位）；节内至少一行 |
| E-3 | 真实记账 | 今天三个立项的偏离逐条在册，且每条的关键词能在对应 VERDICT 正文找到同源记录（守卫做这三份的关键词交叉） |
| E-4 | 新文件自带 | 本 PREREG 的区块非空（自举） |

### 3. 已确认的三条真实偏离（本区块自记账，来源为各 VERDICT）

| 项目 | 预注册值 | 实际值 | 理由 | 影响 |
|---|---|---|---|---|
| DSR 接线 · `args.out` | 产物写 `reports/...` | 写 `D:/_ext_verify/...` | 刻意输出到仓库外，避免覆盖归档证据 | 无（归档证据未动） |
| COST/embargo · `embargo_days` 默认值 | 取自 horizon | **0**（启用时 `max(embargo_days, horizon)` 兜底） | 跑之前的作用对象检查发现主 pipeline 本就纯样本外，默认值是口径不是旋钮 | 默认值逐位不变（B-6 判据守住） |
| COST/embargo · 改造 B 定位 | 给主 pipeline 加 embargo | 加固零调用方的公开 API | `split_chronological` 零调用方；主 pipeline 无标签泄漏 | 无（判读不变，见 VERDICT §四） |
| DATA_CHANNEL · 抓取方式 | 按期抓取（未声明批次数） | 分三批抓取、可恢复 | 本机前台上限约 5 分钟的教训 | 无（43 期 0 失败，行数/指纹不变） |
| DATA_CHANNEL · meta 修复 | D-7 要求 meta 字段齐全 | 修复时增 `meta_repaired_at` 字段 | 缺陷 #17 的 provenance 修复需留痕 | 仅元数据；研究数字不动 |

> 注：DSR 立项的 `caveats` 5→6 条与新增 `dsr/psr` 键是**预期新增键**
> （预注册 §3.3 要求），不算偏离；`disclosure_dates_loaded` 176,841→176,830
> 是**数据源漂移**（DSR_IC_FAMILY_VERDICT §五），不是执行偏离——
> 两者性质不同，不混记。

## 四、组件 A6：数据契约三字段（判据 C 组）

### 1. 口径（事前固定）

- `data_contracts.py` 的 `DataProvenance` 增三个 `Optional[str]` 字段
  （默认 `None`，**不破坏现有构造点**）：
  - `availability_lag`：数据从「事实发生」到「可被研究使用」的滞后口径；
  - `null_policy`：缺失时怎么办（禁止交易 / 兜底 / 跳过）；
  - `source_version`：数据版本标识。
- 新增 `DataSourceContract`（五字段：name + 上述三者 + note）与
  `register_source(...)`：**三者任一为空 ⇒ 抛 `IncompleteContractError`**
  （survey 验收「缺字段时校验失败」的落地形态）。
- `SOURCE_REGISTRY`（模块级 dict）+ `contract_for(name)`（未注册抛
  `UnknownSourceError`）+ `validate_source_registered(name)`。
- `LEGACY_SOURCES`：显式遗产集。`v3_data_bus.py` 两处动态爬取源
  （source 名来自数据行，无滞后口径证据）入集——**不伪造口径**；
  `validate_all_sources()` 对遗产集只点名不抛错。
- 本轮注册三个有代码依据的源：

  | name | availability_lag | null_policy | source_version |
  |---|---|---|---|
  | `cninfo_disclosure` | 公告日当日可用 | 公告日未知 ⇒ 法定截止日兜底（`resolve_availability` 行为） | meta `fetched_at` |
  | `eastmoney_appointment` | 预约/实际公告日 | `ACTUAL_PUBLISH_DATE` 为空即缺失，不补造（模块 docstring） | meta `fetched_at` + 端点 |
  | `fundamentals_yjbb` | 报告期 → 公告日由披露日表决定 | 公告日未知 ⇒ 法定截止日兜底 | meta `fetched_at` |

### 2. 判定标准（事前固定）

| 编号 | 判据 | 通过条件 |
|---|---|---|
| C-1 | 向后兼容 | 现有两处构造点不传新字段可正常构造（`to_dict` 不含 None 新键的行为不变——与既有语义一致：`to_dict` 本就滤 None） |
| C-2 | 缺字段即失败 | `register_source` 对三个字段各缺一次抛 `IncompleteContractError`；空串同样抛 |
| C-3 | 注册非空 | `SOURCE_REGISTRY` 三个源字段全部非空；`null_policy` 含代码依据关键词（`法定截止日` / `不补造`） |
| C-4 | 遗产显式 | `LEGACY_SOURCES` 非空；`validate_all_sources()` 不抛错但输出含遗产点名 |

## 五、组件 A12：拒绝实验入册（判据 R 组）

### 1. 口径（事前固定）

- 新建根目录 `REJECTED_EXPERIMENTS.md`（第 69 份根 md；AGENTS.md §4 与
  `tests/test_doc_layout.py` 计数同步改 69 并注理由）。
- 两张表：
  - **表一 · 检验级**（逐条对应审计脚本清单）：列
    `| 实验 | 计数来源 | 判定文件 | 结论 | 参数组数 |`。
    行来自 `DECLARED_NON_IC_TESTS`（13）与 `DISTINCT_STRATEGY_CONFIGS`（13），
    **每标签一行**；「结论」列写负结论原文要义；
    「参数组数」写该实验实际跑过的独立参数配置数（如「集中度 C10/C20/C30」= 3）。
  - **表二 · 路线级**：列 `| 路线 | 预注册/来源 | 判定文件 | 结论 |`。
    行：H-D1~H-D4（`ALPHA_HYPOTHESIS_PREREG_HD*.md`）、A10 中性化证伪、
    「信号真实但不可变现」（`CROSS_DECADE_VERDICT.md`）、
    外部独立复现（`wangpage/quant-ashare`，survey §二.1）。
- **只登记不改**：登记册不改任何已归档结论；发现对不上只登记差异。

### 2. 判定标准（事前固定）

| 编号 | 判据 | 通过条件 |
|---|---|---|
| R-1 | 文件落地 | `REJECTED_EXPERIMENTS.md` 存在且通过根 md 白名单/计数守卫 |
| R-2 | 覆盖 | `DECLARED_NON_IC_TESTS` 与 `DISTINCT_STRATEGY_CONFIGS` 的**每个标签**都在表一出现（守卫 import 脚本清单逐项匹配） |
| R-3 | 条目数对账 | 表一中来源=声明族的行数 == `len(DECLARED_NON_IC_TESTS)`；来源=策略配置族的行数 == `len(DISTINCT_STRATEGY_CONFIGS)`（「条目数 = n_trials 来源」） |
| R-4 | 参数组数自洽 | 每行参数组数为 ≥1 整数；文档声明的合计值与各行相加一致 |
| R-5 | 反向验证 | 从表一删一行 ⇒ R-2/R-3 红；改一个标签 ⇒ R-2 红 |

## 六、禁止项

1. **不改任何已归档研究数字**；A12 表内的「结论」列只转写既有判定的要义，
   不重新判读。
2. **不伪造数据口径**：无代码/文档依据的源不进 `SOURCE_REGISTRY`
   （入 `LEGACY_SOURCES` 或债务清单）。
3. **不把缺陷修复记成偏离**（性质不同，台账分开）。
4. **不给历史 PREREG 补写未经复核的「无偏离」断言**——无记录的写「未逐份复核」。
5. 不引入第三方依赖（A6 是纯 dataclass + 注册器）。
6. 不动 PIT 主口径（`resolve_availability` / `load_disclosures`）——
   A6 只读其行为作为 `null_policy` 的填写依据。

## 七、验收合并判据

1. E-1~E-4、C-1~C-4、R-1~R-5 全绿（`pytest tests/test_prereg_deviations.py
   tests/test_data_contracts.py tests/test_rejected_registry.py -q`）；
2. 全量测试 rc=0（三项各带守卫，总数只增不减）；
3. `ruff check .` / `mypy . --config-file mypy.ini` 全绿；
4. 三组反向验证（删偏离节 / 缺字段注册 / 删登记行）均「因对的理由红」后还原复绿；
5. 判定写入 `EVIDENCE_CHAIN_VERDICT.md`，含「守卫证明了什么、没证明什么」
   （E-3 只覆盖今天三份；其余 24 份的偏离状态是**未复核债务**，如实登记）。

## 偏离登记

| 项目 | 预注册值 | 实际值 | 理由 | 影响 |
|---|---|---|---|---|
| （无登记偏离） | — | — | 建立时点，执行未开始 | 无 |
