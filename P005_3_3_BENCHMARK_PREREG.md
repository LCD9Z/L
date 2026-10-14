# P005 §3.3 基准口径根因治疗 · 事前登记（benchmark_mode）

> **登记时间**：2026-10-14 14:0x　**状态**：**待双方确认（v2）**
> ⚠️ **v2 补正（2026-10-14 17:2x）**：依主干 16:45 复核回执的 **C1–C5** —— F1–F8 此前
> **全部是副本侧实测却未标侧别**，而治疗执行在主干侧 → 已按侧别重述（§一）、
> 补主干侧实测节、F6/R6/V4 按两侧实情改写、R5 采纳对方 2 条。**v1 的侧别混淆是本登记自身的缺陷**，
> 依 AGENTS「跨侧断言须在**断言对象所在侧**执行命令」自纠。
> **对象**：P005 §3.3「把默认基准从隐式兜底改为显式可控」（方案① 显式必填）+
> 10-11 台账「有条件放行」的三项硬前置 + 我方修订版 5 条独立意见（对方已全部接受）
> **依据**：`P005_主干侧基准代次缺口.md` §3.3/§3.4 · 台账 10-11 区块 ·
> `BENCHMARK_ALIGNMENT.md`（副本版，2026-10-08 建立）· `02_回执/P005修订_reply_海外版_2026-10-08.md` ·
> `02_回执/P011复核结论_主干_2026-10-14.md`（v2 补正依据）
> **性质**：**只登记口径与字段机制**。不改任何回测数字、不重跑实验、不改写历史产物。
> 治疗代码的执行在双方确认后由主干侧进行（P005 §3.3 原提案约定），本登记是其前置。

---

## 〇、本案根因（两侧同形，位置不同）

**基准的选择是一次隐式的、产物里查不到的兜底** —— 且**两侧各有各的兜底点**：

| 侧 | 兜底点 | 形态 |
|---|---|---|
| 〔副本〕 | `run_five_factor_ab.py:252` `bench_path = args.benchmark or os.path.join(ds, "benchmark_ew.csv")` | 空串 ⇒ 兜底到**等权**基准 |
| 〔主干〕 | `run_five_factor_ab.py:310`（`--benchmark` 默认在 `:277`）**同一行同形**；**另有** `run_tdx_rolling_eval.py:128` `bench = args.benchmark or os.path.join(dataset, "benchmark.csv")` | 空串 ⇒ 兜底到**沪深300** |

**直证**：〔副本〕`reports/five_factor_ab_v2.json` 的 `args.benchmark=""`（空串 ⇒ 走兜底）。
〔主干〕**该文件不存在**（见 §一.3）→ 主干侧直证须另找（C3，见 §一.4 待办）。
只要「不传就默默用某个基准」的路径存在，下一个新产物仍会再犯（P005 §3.3 原文判断，本登记认同）。

---

## 一、现状事实（**分侧别** + 命令 + 截止时点 —— 兑现意见 5 与 C1）

> ⚠️ **侧别纪律**（AGENTS）：跨侧断言须在**断言对象所在侧**执行命令。
> 本节的每个数字都带〔副本〕/〔主干〕标记；**两侧数字不可混用**——
> 治疗执行在主干侧，故**主干侧数字是治疗的直接依据**，副本侧数字仅作对照。
> 计数口径：`reports/*.json` **顶层、非递归**，排除 `_` 前缀与 `.partial`。

### 1.1 〔副本〕实测（HEAD `e779fdd`，截止 10-14 14:01 / 17:1x）

| # | 事实 | 命令 | 值 |
|:--:|---|---|---|
| F1c | 顶层 JSON 数 / `.partial` 数 | `ls reports/*.json \| wc -l`；`ls reports/*.json.partial \| wc -l` | 59 / **6** |
| F2c | 含 `benchmark` 字样 / `"benchmark"` 键 | `grep -l benchmark reports/*.json \| wc -l` | 22 / 7 |
| F3c | `five_factor_ab_v2.json`（根因直证载体） | `ls` | **存在**（`args.benchmark=""`） |
| F4c | `ew_benchmark_v3.json`（等权基准本体） | `ls` | **存在** |
| F5c | 数据集 v2 有 `benchmark.csv` + `benchmark_ew.csv`（后者 2,598 行，与 1,240 根区间错配） | BENCHMARK_ALIGNMENT §四.3 | 成立 |
| F6c | `run_tdx_rolling_eval.py` 等权机制 | 脚本 `:149` `--ew-benchmark` **默认 True** | **现算机制**（池内现算 / `--ew-series` 外喂） |
| F8c | 已跟踪 JSON 数 / 未跟踪 | `git ls-files 'reports/*.json' \| wc -l` | **58** / 1（`_turnover_fix_probe.json`，`_` 前缀规则内） |
| F9c | `.gitignore` 白名单行号 | `grep -n reports .gitignore` | **28–30**（无逐子目录白名单） |
| F10c | 根因行号 | 脚本内 | `run_five_factor_ab.py` **:252**（默认在 `:226`） |
| F7c | 未标注口径的报告 | `BENCHMARK_ALIGNMENT.md` §三 + `ls` | **5 份**（`TAIL_EXCLUSION` / `CONCENTRATION` / `MARKET_RISK_GATE` / `HORIZON_NET_EFFECT` / `EXPERT_FILTER_AND_HF4_HV2`） |

### 1.2 〔主干〕实测（HEAD `70d96be`，截止 10-14 17:1x）

> 主干侧由对端执行、**我方经 `FETCH_HEAD` 独立复现**（`git ls-tree`/`git show` 逐条核对，
> 结果**逐条一致**）——两侧互证，符合「跨侧断言须在断言对象所在侧执行」。

| # | 事实 | 命令 | 值 |
|:--:|---|---|---|
| F1m | `.partial` 数 | `git ls-tree -r --name-only FETCH_HEAD \| grep -c 'reports/.*\.json\.partial'` | **0** |
| F2m | `reports/*.json`（非 `_` 前缀）数 / 含 `benchmark` 数 | 逐文件 `git show` 扫 | 81 / **35** |
| F3m | `five_factor_ab_v2.json` | `git cat-file -e FETCH_HEAD:reports/five_factor_ab_v2.json` | **不存在** |
| F4m | `ew_benchmark_v3.json` | 同上 | **不存在** |
| F6m | `run_tdx_rolling_eval.py` 等权机制 | `git show FETCH_HEAD:scripts/run_tdx_rolling_eval.py \| grep -c ew-benchmark` | **0 —— 主干该脚本无此参数**；其 `:128` 为 `bench = args.benchmark or …/benchmark.csv`（**同形兜底，指向沪深300**） |
| F8m | 已跟踪 JSON 数 | `git ls-tree -r --name-only FETCH_HEAD \| grep -c '^reports/.*\.json$'` | **82** |
| F9m | `.gitignore` 白名单行号 | `git show FETCH_HEAD:.gitignore \| grep -n reports` | **34–52**（**逐子目录白名单**：`!reports/*.json` / `!reports/*.md` / `!reports/EVIDENCE_INDEX.md` / `!reports/external_v3/`…） |
| F10m | 根因行号 | 脚本内 | `run_five_factor_ab.py` **:310**（默认在 `:277`） |
| F7m | 未标注口径的报告 | `git cat-file -e FETCH_HEAD:<f>` 逐份 | **2 份**（`TAIL_EXCLUSION_REPORT.md` / `CONCENTRATION_REPORT.md`）；另 3 份**主干不存在**（`MARKET_RISK_GATE` / `HORIZON_NET_EFFECT` / `EXPERT_FILTER_AND_HF4_HV2`） |

### 1.3 两侧差异对照（**v1 缺失的关键表**）

| 维度 | 〔副本〕 | 〔主干〕 | 影响 |
|---|---|---|---|
| 根因直证载体 | `five_factor_ab_v2.json` 存在 | **不存在** | C3：主干侧直证须重定位 |
| 等权基准本体 | `reports/ew_benchmark_v3.json` | **不存在** | C3：F4c 仅副本成立 |
| `run_tdx_rolling_eval` 等权 | `--ew-benchmark` 默认 True（现算） | **无该参数**，`:128` 同形兜底 | **C2：R6 主干行 = 两脚本均显式必填** |
| 已跟踪 JSON | 58 | **82** | C4：V4 按侧取值 |
| `.gitignore` 白名单 | 28–30（简） | **34–52**（逐子目录） | C5②：R5 须两侧分述 |
| 根因行号 | :252（默认 :226） | :310（默认 :277） | 引证须带侧别 |

### 1.4 待办（C3 的落地方式）

〔主干〕侧的**根因直证**与**等权基准本体位置**须重定位：建议对端以
`git log -S 'benchmark' --oneline -- reports/` 或直接扫 `reports/*.json` 的
`args.benchmark` 字段取值，找主干侧的「空串直证」样本；
等权基准本体则须查主干侧 `benchmark_ew` 的落盘形式（CSV/JSON/现算）。
**本登记不代对端断言**——列为 A2-1 的执行项之一。

**待对账项 D-1（不掩盖）**：三方计数口径差异 —— 主干 `EVIDENCE_INDEX.md:177`
「42 份仅 3 份可辨」（10-08 前口径）；副本 `BENCHMARK_ALIGNMENT.md` §2.3「46 / 4 / 38」（10-08）；
本登记「59 / 22 / 7」（副本 10-14 14:01）与「81 / 35」（主干 10-14 17:1x）。
**以「侧别 + 命令 + 口径 + 时点」四要素复现为准**进 A2 对账清单。

**勘误项 D-2（本登记自纠）**：`BENCHMARK_ALIGNMENT.md` §四.4「`reports/` 未纳入
版本控制（`.gitignore:22` 忽略 `reports/`）」在 10-08 写成时**准确**，但
**2026-10-11 23:02 `b2af7ac`（P0 证据入库策略）起已过期** —— 现行
`.gitignore:28-30` 为白名单制，`reports/*.json` **已被 git 跟踪**（F8c 实测 58/59）。
该节「无回退点、无变更追溯」的结论对 `*.json` **不再成立**（仅对 `_` 前缀探针类
与非 JSON 产物成立）。A2 合并权威版时按 F8c + 本时点修正该节。

---

## 二、登记项（本体）

### R1 · `benchmark_mode` 字段（兑现意见 2）

| 元素 | 定义 |
|---|---|
| 落点 | 组合层 A/B 产物 JSON **顶层**；研究报告头部口径标签 |
| 取值 | `explicit`（显式传入且通过代次断言）· `legacy_fallback`（治疗前产物/兜底形态）· `dual_report`（双基准并报，如 `v3_alpha_gap_probe*`） |
| 伴生字段 | `benchmark_source`（文件绝对路径或 `computed:pool` / `external:<path>`）· `effective_commit`（产出该文件的 commit，供 R2 定界） |

**与 §3.4 标注机制复用同一字段**（意见 2 原建议）：历史产物不补写 `benchmark_mode`，
其「legacy」语义由 R2 的时点定界隐含成立。

### R2 · 生效时点（兑现意见 2）

- 时点 = **本登记经双方确认、合并落定的 commit**（记为 `E`）。
- `E` 之后生成的组合层产物：**必须** `benchmark_mode ∈ {explicit, dual_report}`；
  缺失即视为**未完成任务**，不得作为结论凭据入库。
- `E` 之前的产物：全部按 `legacy_fallback` 语义对待 —— **不补写字段、不改写文件**
  （§四）。杜绝「治疗前旧兜底与治疗后显式混存且无法区分」的第三类产物
  （意见 2 原论证）。

### R3 · 代次匹配断言（兑现意见 1 + 主干硬前置）

- 每个组合层脚本**声明自身代次**（`dataset_generation` 由数据集目录判定：
  含 `benchmark.csv`(000300)→旧代；组合层结论按新代口径声明→须显式等权基准）；
- **断言**：`assert_generation_match(benchmark_generation, dataset_generation)`
  —— 不一致即**非零退出**（不是 warning）。
- 跨代使用（如以沪深300 基准跑新代口径实验）= **显式传参 + 引用本登记编号**
  （`--benchmark` 显式传 + 产物记 `benchmark_mode=explicit` + 报告引用本 PREREG）。
- ⚠️ 断言语义按意见 1：**「传了」≠「传对」**——断言比的是**代次**，不是非空。

### R4 · 推断必须附依据（兑现意见 3）

- 历史产物标注**只允许**格式：`推断=脚本默认值（当时指向 benchmark.csv/沪深300，
  依据：<脚本名+版本/commit+行号+截止时点>）`；
- **空串 ≠ 沪深300 直证**（`args.benchmark=""` 只证明「未显式传入」——
  意见 3 原论证，本项目「推断当确认」已自纠过一次，不再犯）；
- 无依据的裸推断**禁止入表**（BENCHMARK_ALIGNMENT §五.2 同款纪律）。

### R5 · `BENCHMARK_ALIGNMENT.md` 权威版本（兑现意见 4 + C5，**待双方确认项**）

- 现状：两份同名文件内容不同（副本 11,169B/166 行 vs 主干 7,976B/155 行，
  10-11 台账已确认），**本身已是 add/add 冲突**；
- 本登记**不建议单方裁定**，提出待确认方案：以**副本版为底**
  （含「覆盖区间/标注状态」列、46→59 口径演进），主干版内容**并入**；
  A2 合并时按本登记执行。**未确认前，双方各自维护不得再互抄**（意见 4 教训：
  双方各自补标注反而制造新冲突）。
- **C5 采纳（主干 16:45 两条）**：
  1. **主干版独有段落显式列清单并入**（防「并入」变成静默丢弃）——
     并入前先 `git diff FETCH_HEAD:BENCHMARK_ALIGNMENT.md` 逐段点清主干独有内容，
     清单随 A2 执行记录留痕；
  2. **`.gitignore` 按两侧实况分述**：〔副本〕`28-30`（简式三行）/〔主干〕`34-52`
     （**逐子目录白名单**：`!reports/*.json` / `!reports/*.md` / `!reports/EVIDENCE_INDEX.md` /
     `!reports/external_v3/`…）——合并时取**并集**且以主干逐子目录形态为骨架
     （更细粒度，能覆盖副本三行的语义；副本独有行须逐条确认无遗漏）。

### R6 · 治疗范围（方案①，**按侧别** —— C2 修正）

**v1 只列了副本形态（1 行），在主干不可执行**；按两侧实情扩为两行：

| 侧 | 对象 | 现状 | 治疗后 |
|---|---|---|---|
| 〔副本〕 | `scripts/run_five_factor_ab.py:252` | `--benchmark` default="" → 兜底 `benchmark_ew.csv` | **删除默认空串**：缺失即报错退出，错误信息列出 `benchmark_mode` 合法取值 |
| 〔副本〕 | `scripts/run_tdx_rolling_eval.py:149` | `--ew-benchmark` 默认 True（现算机制，F6c） | 保留现算为 `dual_report`，产物**必须落** `benchmark_mode` + `benchmark_source=computed:pool` |
| 〔主干〕 | `scripts/run_five_factor_ab.py:310`（默认 `:277`） | 同形兜底（兜底到 `benchmark_ew.csv`） | 同上：**删除默认空串**，缺失即报错退出 |
| 〔主干〕 | `scripts/run_tdx_rolling_eval.py:128` | **无 `--ew-benchmark` 参数**；`bench = args.benchmark or …/benchmark.csv` —— **同形根因，兜底到沪深300** | **两脚本均显式必填**（`--benchmark` 无默认；缺失报错退出）；主干若要保留「沪深300 默认」的历史行为，须改为**显式** `--benchmark <path>` 传参，不得保留 `or` 兜底 |

**「① 只保证传了、不保证传对」的已知边界**：由 R3 代次断言补齐（意见 1 全链）。

---

## 三、历史 JSON 处置（P005 §3.4，兑现意见 3/4）

**不回填、不改写、mtime 不动**（R2）。三层分类：

| 层 | 判据 | 处置 |
|---|---|---|
| L1 自证可辨 | 产物内含双基准对象（`v3_alpha_gap_probe*`）或 ew 字段（4 份，F2c 子集） | 在 BENCHMARK_ALIGNMENT §2.1 登记，**不补字段** |
| L2 可推断 | 数据源目录唯一基准文件 + 脚本默认值链路可复原 | 按 R4 格式带依据标注，进 §2.3 待确认区 |
| L3 完全不可辨 | 无 `args.dataset`、无字段、无日志（如 `contrarian_ab_with_p.json`，数据源亦缺） | **保持待确认**；用作反证样本，禁推断 |

D-1（§一计数分歧）随 L1/L2/L3 逐份过表自然消解或坐实。

---

## 四、验收标准（**事前固定，可判定**）

| # | 判据 | 检验方式 |
|:--:|---|---|
| V1 | 两脚本缺失 `--benchmark`（five_ab）⇒ **非零退出**且报错含 `benchmark_mode` 合法取值 | 单测 mock argparse |
| V2 | `assert_generation_match` 存在；代次不一致抛错、一致通过 | 单测（正/反两例） |
| V3 | `E` 之后新产物 100% 含 `benchmark_mode ∈ {explicit, dual_report}` | 守卫测试扫 `reports/*.json` 的 `effective_commit > E` 子集 |
| V4 | 历史产物**内容不变**（**按侧取值**：〔副本〕59 份 / 已跟踪 58；〔主干〕81 份 / 已跟踪 82） | git 证明：治疗后 `git status --porcelain reports/` 在**该侧**必须为空；未跟踪的 `_` 前缀探针类单独 sha256 快照 |
| V5 | BENCHMARK_ALIGNMENT 按 §五规则追加治疗后代次行；未标注报告（F7c 5 份 / F7m 2 份）**在基准确认前保持未标注** | 人审 + 清单核对 |

**V4 的可证明性**：`reports/*.json` 已入 git（F8c/F8m）⇒ 治疗执行期只需
`git status --porcelain reports/` 为空即可机械证明「未改写」（比 sha/mtime 快照更强：
mtime 可伪造、git 内容哈希不可）。A2 前若双方统一放行 `_` 前缀探针类，另行登记。

---

## 五、明确禁止

1. **禁止**用默认值推断填表而不附 R4 依据（「推断当确认」是本登记要修的病灶）；
2. **禁止**跨 `benchmark_mode` 的数字直接比较（AGENTS §〇 0.3 同款纪律的字段化）——
   确需比较时，先做口径敏感性检验并在产物引用本登记编号；
3. **禁止**在本登记经双方确认前先行治疗代码（10-11 主干不放行 A2 的理由①：
   防「治疗与合并互相污染」）；
4. **禁止**把 V4 的「不改写」执行成「静默补字段」——补字段即改写。

---

## 六、风险与边界

| 风险 | 处置 |
|---|---|
| 治疗代码在主干侧执行，与 P006 A2 合并时序耦合 | 本登记确认前不治疗；A2-1 步骤按 15_ 文件执行序 |
| `benchmark_ew.csv` 在 v3 缺失（F4c，**主干侧对应物待定位**）→ 方案①后 v3 上跑新代口径将直接报错 | **预期行为**（显式必填的目的即暴露缺口）；补法 = 把 `reports/ew_benchmark_v3.json` 写回数据集目录为认证 CSV（builder 已存在），属治疗执行期工作，另行登记 |
| 两份 BENCHMARK_ALIGNMENT 的权威争议 | R5：待双方确认，本登记不单方裁定 |

---

**回退点**：本登记合并前的 commit（治疗执行前的任何时点，git revert 即回到隐式兜底旧态）。
**本登记不构成投资建议。**
