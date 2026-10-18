# 数据通道建设预注册：A8 公告日第二源 + ② 证券代码映射表 + dataset_fingerprint

> **建立**：2026-10-18　**状态**：**已执行** —— 判定见
> [`DATA_CHANNEL_VERDICT.md`](DATA_CHANNEL_VERDICT.md)。
> 写于 2026-10-18，**先注册后动手**（AGENTS.md §2.2）。
>
> 三项工程件，全部来自 `GITHUB_ASHARE_QUANT_SURVEY.md`：
> ① **A8**（§8.4）财务数据 PIT 外接公告日 —— 落一张「报告期 → 公告日」表；
> ② **10.3-②**（§十）借 `QuantConnect/Lean` 的 MapFile 建证券代码映射表
>    （§10.3 原注：「10.3-② 涉及数据表建设，宜等公告日接入（A8）一起规划」
>    —— 本立项即该规划的实现）；
> ③ **dataset_fingerprint** —— `DSR_IC_FAMILY_VERDICT.md` §五的建议
>    （「本轮不做」的那条，本轮做）。
>
> ⚠️ 本文件只登记**数据通道的口径与判定**，不产生任何 alpha 结论，
> 不改变任何已归档研究的数字，也不得被引用为「策略有效性」证据。

## 一、立项背景与三项的关系

| 项 | 缺口 | 本立项的交付 |
|---|---|---|
| A8 | PIT 首选依据只有巨潮一个源；12.8% 记录退法定截止日；表本身无指纹 | 东财预约披露表（第二源）+ 双源交叉校验 + 量化补缺潜力 |
| ② | 裸 6 位代码在沪深命名空间重叠（000905 = SZ 厦门港务 / SH 中证500），静默取一个就是错 | `pit/security_map.py`：带市场解析、歧义必报错、000905 阳性对照 |
| ③ | 归档产物无数据集指纹，「重跑 = 同一数据集」无法自证 | `fetch/fingerprint.py`：一次 md5 + 行数 + 字节数，接入因子研究产物 |

三项共享同一条主线：**让「数据从哪来、什么时候可用、是哪一个」变成可验证的属性**。

## 二、作用对象检查（AGENTS.md §8 纪律，动手前必做）

| 检查项 | 命令 / 依据 | 结果 |
|---|---|---|
| 巨潮表现状 | `wc -l D:/tdx_dataset_v3/disclosure_dates.jsonl` | **176,830** 行；`load_disclosures` 消费它（`pit/pit_fundamentals.py:179`） |
| 财务表现状 | `wc -l fundamentals.jsonl` | **331,432** 行 |
| 巨潮表真实出处 | 读 `scripts/fetch_fundamentals.py` + 比对字段 | 实际由 `fetch_all_disclosures`（**巨潮** `stock_report_disclosure`）产出 —— 但磁盘 meta 写的是东财 yjbb，**出处缺陷 #17**（见 §五.3） |
| 东财接口可用性 | `curl datacenter-web.eastmoney.com/.../RPT_PUBLIC_BS_APPOIN` | **HTTP 200**，字段含 `ACTUAL_PUBLISH_DATE` / `FIRST_APPOINT_DATE` / `SECUCODE`（带市场后缀） |
| akshare 是否可用 | venv `import akshare` | **未安装** ⇒ 第二源走**直连 HTTP**（项目自有 `fetch/transport.py` 限流重试），不引入依赖 |
| 股票池元数据 | `ls D:/tdx_dataset_v3/stocks/*.metadata.json` | **5,667** 个，含 `list_date` / `delist_date` / `is_delisted` —— 映射表的本地来源 |
| 000905 实体 | `stocks/000905.metadata.json` | **厦门港务（SZ）**，listed 1999-04-29；而 `000905.SH` 是中证500 ⇒ 阳性对照成立 |
| PIT 主口径调用方 | `grep -rn resolve_availability --include=*.py` | `pit_fundamentals` + 6 个使用方（见下）⇒ **本轮不准动**（禁止项） |

**关键判断**：A8 的表**不接线**也能交付全部验收判据（抽样、分布、交叉校验）；
接线（改 `resolve_availability` 优先级）会变更有框研究产物的 `availability_basis_counts`
——那是口径变更，须另立预注册。本立项只量化「接线会改变什么」，不接线。

## 三、组件 A：dataset_fingerprint（判据 F 组）

### 1. 口径（事前固定）

- 函数：`fetch/fingerprint.py` 的 `fingerprint_file(path)` → `{path, bytes, lines, md5}`；
  `fingerprint_datasets({名: 路径})` → `{名: fingerprint_file(...)}`。
- **一次 md5**：流式分块读（1 MiB），不整文件入内存（ fundamentals 120 MB，
  本机 7.8 GB 内存但核心管道按「8 GB 机器可跑」设计）。
- `lines` = 换行符计数（末行无换行则 +1），与 `wc -l` 口径一致。
- **缺失即缺失**：`required=True` 抛 `FileNotFoundError`；`required=False` 返回
  `{"path":…, "missing": True}` —— 不补造空指纹。
- 接入点：`scripts/run_fundamental_factor_study.py` 产物 payload 增
  `dataset_fingerprint` 键，覆盖 `--fundamentals` 与 `--disclosures` 两个入参文件；
  同时打印一行摘要。**只增键，不改任何既有键**（旧字段逐位相同）。

### 2. 判定标准（事前固定）

| 编号 | 判据 | 通过条件 |
|---|---|---|
| F-1 | md5 正确 | 与 `hashlib.md5` 对同一 fixture 逐位相同；`bytes` = 文件大小；`lines` = `wc -l` |
| F-2 | 内容变更可检出 | 改 fixture 一个字节 ⇒ md5 变、行数按预期变（阳性对照） |
| F-3 | 缺失文件 | `required=False` 时记 `missing`；`required=True` 时抛 `FileNotFoundError`（不是返回空指纹） |
| F-4 | 确定性 | 同文件两次调用结果逐位相同；无时钟/主机/绝对路径之外的字段 |
| F-5 | 只增键 | 接入后产物除 `dataset_fingerprint` 外与接入前逐位相同（用既有产出的键集合比对） |

## 四、组件 B：证券代码映射表（②，判据 M 组）

### 1. 口径（事前固定）

- 模块：`pit/security_map.py`。表由 `stocks/*.metadata.json` 构建：
  `code → {market, listed, delisted, successor, name}`。
- **market 来源**：代码段规则（`600/601/603/605/688→sh`，`000/001/002/003/300/301→sz`，
  `430/830/870/920→bj`，`900→sh`、`200→sz` 为 B 股段）。未知代码段抛
  `UnknownMarketError`，**不猜**。
- **裸码歧义区（本组件核心）**：`000000–000999` 同时属于 SH 指数命名空间与
  SZ 股票命名空间（`000001.SH`=上证指数 vs `000001.SZ`=平安银行）。该区间内
  `resolve(code)` **必须抛 `AmbiguousCodeError`**，错误信息列出两个候选命名空间；
  调用方须显式 `resolve(code, market=…)`。**不静默取一个**。
- `resolve(code, market)` 三重校验：market 已知、代码段属于该 market、条目存在 ——
  分别抛 `UnknownMarketError` / `MarketMismatchError` / `UnknownCodeError`。
- `successor`：**无本地来源**（`corporate_actions.csv` 只有复权因子，不含换股/吸并）。
  一律留空串并在表级统计 `successor_known_count`（预期 0）。**不硬凑**。
- secid 双格式：东财 `1.600000`/`0.000001`/`2.<bj>`，baostock `sh.600000`/`sz.000001`
  /`bj.<code>` —— 两库格式不同，**不得互抄**（项目记忆既有判据）。
- 落盘：`scripts/build_security_map.py` → `D:/tdx_dataset_v3/security_map.json`
  + `.meta.json`（真实来源目录、条数、fingerprint）。仓库内只有构建器与测试。

### 2. 判定标准（事前固定，含阳性对照）

| 编号 | 判据 | 通过条件 |
|---|---|---|
| M-1 | **阳性对照（000905）** | `resolve("000905")` 抛 `AmbiguousCodeError`，错误信息含 `sh` 与 `sz` 两个命名空间；`resolve("000001")` 同样抛（同为歧义区）。**若返回厦门港务而不报错，本判据红** |
| M-2 | 显式市场可解析 | `resolve("000905", "sz")` → 厦门港务、`listed=1999-04-29` |
| M-3 | 非歧义区裸码可直接解析 | `600000→sh`、`300001→sz`、`920000→bj`（fixture） |
| M-4 | 未知码 | 不存在的代码抛 `UnknownCodeError`，不返回 None/空 dict |
| M-5 | secid 双格式 | 东财/baostock 各自格式正确；BJ 段格式有实测依据 |
| M-6 | market 交叉校验 | 与东财 `SECUCODE` 后缀（A8 抓取副产物）逐码比对：一致率、分歧清单。分歧**登记不静默改** |
| M-7 | delisted 自检 | metadata `delist_date` 与 CSV 末条日期一致（抽样 300 只）；矛盾计数并登记 |
| M-8 | 确定性 | 同一 fixture 目录构建两次，表逐位相同 |

## 五、组件 C：A8 东财预约披露第二源（判据 D 组）

### 1. 口径（事前固定）

- 模块：`fetch/disclosure_eastmoney.py`；脚本 `scripts/fetch_disclosure_eastmoney.py`。
- 端点（实测可用，**真实出处**，写进 meta）：
  `https://datacenter-web.eastmoney.com/api/data/v1/get?reportName=RPT_PUBLIC_BS_APPOIN`
  `&columns=ALL&pageSize=5000&pageNumber=N&filter=(REPORT_DATE='YYYY-MM-DD')`
  —— 即 akshare `stock_yysj_em`（预约披露时间）的底层数据源；akshare 未装，
  直连并记录「akshare 函数名 ↔ 端点」对照。
- 抓取范围：**2016Q1–2026Q2 共 42 期**（与巨潮表对齐；2026Q3 当前多数未披露，
  `ACTUAL_PUBLISH_DATE` 为 null 的期只作附带抓取，单独标注）。
- 字段映射（每行）：
  `code`（zfill 6）、`report_period`（ISO 季度末）、`market`（SECUCODE 后缀）、
  `first_appoint`（FIRST_APPOINT_DATE）、`actual_publish`（ACTUAL_PUBLISH_DATE）、
  `appoint_publish`（APPOINT_PUBLISH_DATE）、`revisions`（三个 CHANGE_DATE 非空计数）、
  `is_publish`、`report_type_name`。
- **缺失即缺失**：`actual_publish` 为空（未披露）的行**不产出日期**，只可附带
  `appoint` 字段；不许把预约日当成实际披露日。
- 分批落盘（本机 5 分钟前台上限教训）：每期一次请求组，**按期追加**，`--resume`
  跳过已抓期；失败期记 `failed`，不静默跳过。
- 交叉校验脚本 `scripts/crosscheck_disclosure_sources.py`：逐 `(code, period)` 比对
  巨潮表 vs 东财表 —— `first_scheduled ↔ FIRST_APPOINT_DATE`（同语义），
  `actual_disclose ↔ ACTUAL_PUBLISH_DATE`（同语义）；输出一致/冲突/单侧缺三类计数
  + 抽样 100 条明细 + 滞后分布。

### 2. 判定标准（事前固定）

| 编号 | 判据 | 通过条件 |
|---|---|---|
| D-1 | 表结构与解析 | 每行 6 位代码 + 合法季度末报告期；null/NaT 日期不产出；`report_period` 与 `REPORT_DATE` 一致；fixture 替身测试（不联网） |
| D-2 | 抽样 100 条 | 公告日 ≥ 报告期（无未来公告）；100 条全过 |
| D-3 | 滞后分布合理 | `actual_publish − report_period` 天数分布：中位数落在 10~60 天，且**非全 0**（全 0 说明字段其实是报告日本身） |
| D-4 | 双源交叉 | `first_scheduled` 一致率、`actual_disclose` 一致率**均 ≥ 95%**；冲突与单侧缺逐类计数；冲突样本逐条列出（前 20 条） |
| D-5 | 补缺潜力（只量化） | 池内现走 `statutory_deadline` 兜底的记录中，东财表有日期的比例 —— 记数，**不接线** |
| D-6 | PIT 主口径未动 | `grep` 证明 `resolve_availability` / `load_disclosures` 无改动（diff 为空）；双源冲突时两列并存 |
| D-7 | 出处真实 | 新表 meta 写明端点/字段/ fetched_at / 行数；**缺陷 #17** 登记（见下） |

### 3. 缺陷 #17（本轮登记并修代码）

`scripts/fetch_fundamentals.py` L145-157：循环后的 `_write_meta` **硬编码**
`"akshare stock_yjbb_em（东方财富业绩报表）"` 与 yjbb 版 caveats，`--mode disclosure`
运行时把循环内刚写对的巨潮出处**覆盖掉**。磁盘 `disclosure_dates.meta.json` 即为受害者。
⇒ 修为 mode 条件化；磁盘 meta 的 `source`/`caveats` 两字段按巨潮模式重写
（`fetched_at`/`rows_by_period`/`failed` 原样保留，加 `meta_repaired_at`）。
登记 `HANDOVER.md` §5.3 #17。

## 六、明确不做的事

| 不做 | 理由 |
|---|---|
| 不改 `resolve_availability` / PIT 主口径（A8 不接线） | 会变更已框研究的 `availability_basis_counts`，属口径变更，须另立预注册 |
| 不装 akshare / pandas | 核心管道零第三方依赖是既定纪律；东财端点直连已实测可用 |
| 不重抓巨潮表 | 本轮只读它；重抓会动 PIT 首选依据的存量 |
| successor 不留空以外任何值 | 无本地来源；硬凑等于伪造映射 |
| 不引入 DSR/PBO/SPA | §8.4 A1~A4 已由 `DSR_IC_FAMILY` 立项覆盖 |
| 不用东财表「抢救」任何已归档结论 | AGENTS.md §2.2 |

## 七、验收判据（合并，事前固定）

1. F-1 ~ F-5、M-1 ~ M-8、D-1 ~ D-7 全过。
2. **反向验证**（2026-10-18 记忆纪律）：每个组件植入已知缺陷，确认它**因为对的
   理由红**，且失败信息含本文件判据编号；不允许 `SyntaxError` /
   `ImportError` / `FileNotFoundError` 之类的假红：
   - F 组：`fingerprint_file` 恒返回同一 md5 ⇒ F-2 必须红；
   - M 组：`resolve` 对歧义区静默返回 SZ 条目 ⇒ M-1 必须红；
   - D 组：解析器把空 `actual_publish` 当成合法日期 ⇒ D-1 必须红。
3. 全量测试套件跑一次，**记录当时 HEAD**（仓库有并发提交，不记 HEAD 的绿不可比）。
4. 若 D-4 一致率 < 95%：**不得**挑选「好看」的子集交差 —— 如实报冲突率并
   逐条列冲突样本，A8 表降级为「仅交叉校验用途」，补缺结论作废。
5. 若 M-6 出现前缀规则与 SECUCODE 的真实分歧：登记并逐条列，**不静默改规则**。

## 八、产物与登记

| 产物 | 位置 |
|---|---|
| 预注册 | 本文件 |
| 判定 | `DATA_CHANNEL_VERDICT.md` |
| 指纹模块 | `fetch/fingerprint.py` |
| 映射模块 | `pit/security_map.py` |
| 东财披露模块 | `fetch/disclosure_eastmoney.py` |
| 脚本 | `scripts/build_security_map.py`、`scripts/fetch_disclosure_eastmoney.py`、`scripts/crosscheck_disclosure_sources.py` |
| 守卫测试 | `tests/test_dataset_fingerprint.py`、`tests/test_security_map.py`、`tests/test_disclosure_eastmoney.py` |
| 数据产物（仓库外） | `D:/tdx_dataset_v3/security_map.json`、`disclosure_eastmoney.jsonl`（各带 meta） |

> 数据产物在数据集目录（与 `disclosure_dates.jsonl` 同规矩），**不进 git**；
> 仓库内承载构建器、测试与判定。`reports/` 本轮**不新增 JSON**（判据全部由
> pytest + 可复跑脚本承载，数字写进判定文档）。
