# PIT 快照 P3 报告：全市场 L3 回填 —— 崩溃事故、韧性补丁与重启方案

**日期**：2026-10-13 · **关联**：`PIT_SNAPSHOT_DESIGN.md` / `PIT_SNAPSHOT_P0_REPORT.md` / `PIT_SNAPSHOT_P2_REPORT.md`
**任务**：用户指令 ③「全市场回填」（2016-01-01 ~ 今 · 5,667 只 · baostock 不复权估值）

---

## 1. 事故（2026-10-12 20:44 ~ 21:15 local）

`scripts/run_pit_snapshot_ingest.py --dataset l3_valuation --root D:/pit_snapshots
--universe D:/tdx_dataset_v3 --start 2016-01-01 --end 2026-10-12 --date 2026-10-12
--resume --flush-every 100`

* **进程**：跑到约 456/5,667 只（31 分钟），raw 层增量落盘 **1,153,699 行 / 239MB**（`--flush-every` 机制验证有效）。
* **崩溃**：`sz.001206` 命中 baostock `10002007 网络接收错误` → `_fetch_one_l3` 直接
  `raise RuntimeError`（run_pit_snapshot_ingest.py:359，旧代码）→ **整轮终止**，
  规范化一步未做。
* **连带发现（两个静默污染/缺口）**：
  1. **短窗口冒烟数据混入正式命名空间**：19:28 的冒烟测试（5 只 × 约 3 个月窗口）
     写入同一 `(source, endpoint, ingest_date=2026-10-12)`，`--resume` 将其计为
     「已完成 5 只」—— 若不处理，这 5 只将**永远只有 3 个月窗口**。
  2. **跨层缺口**：崩溃点在采集阶段，raw 有 456 只而 norm 一只未写；若此后只按
     `--resume` 续跑，这 456 只**永远不会进入规范层**，消费方读 norm 即**静默缺 8% 的股票**。

## 2. 根因与修补（scripts/run_pit_snapshot_ingest.py）

| # | 缺陷 | 修补 | 守卫测试 |
|--:|------|------|------|
| 1 | 单只瞬时网络错误终止整轮 6 小时任务 | `_query_with_retry()`（纯函数）：3 次尝试、退避 2/5/10s、重试前重登录；query 自身抛异常也按一次失败折算 | test_query_with_retry_*（3 项） |
| 2 | 失败即全局中止 | `_fetch_l3` 单只 try/except：重试后仍败 ⇒ 记入 `failed` 并**跳过**，本轮其余照常；结束以 WARN + `metrics.failed_codes` 全量呈现（不静默），`--resume` 可补采 | test_fetch_l3_skips_code_that_fails_after_retry |
| 3 | raw/norm 跨层缺口不可见 | `_layer_gap()`：落盘后比对两层代码覆盖，缺口进 metrics + WARN；`_rebuild_norm_l3()`：从 raw **幂等**补建缺失 code（按 code 粒度，流式读，全市场 1,400 万行不吃内存）；CLI `--rebuild-norm` | test_layer_gap_* / test_rebuild_norm_*（4 项） |

> 「单个 --flush-every/--resume 增量机制」经事故验证**有效**（239MB 已落盘成果可续跑），
> 本轮未改动其语义，只补上「失败不致命」与「缺口显式化」。

## 3. 数据层处理（2026-10-13 执行）

* **归档而非删除**：受污染的 `raw/.../2026-10-12.jsonl`（456 只完整 + 5 只短窗口）
  与 `normalized/l3_valuation/2026-10-12.csv`（290 行短窗口）移入各自 `_archive/`
  子目录（`landed_dates`/`read_raw_keys` 均按精确文件名/`*.csv` 非递归 glob，**不受影响**），
  保留字节以便复核；`meta/ingest_log.jsonl` 追加一条 `action=archived` 留痕。
* **新命名空间重采**：`--date 2026-10-13 --start 2016-01-01 --end 2026-10-13 --resume
  --flush-every 100`。选择新日期而非改写旧文件，是为守住「原始层只追加、不改写」纪律
  （重写 239MB raw = 破坏证据层不可变性）。

## 4. 验收标准（可判定）

1. 回填进程退出码 0；`metrics.n_stocks` ≈ 5,667，`n_failed_codes` = 0（若 >0，`--resume` 补采至 0）。
2. `--rebuild-norm` 报告 `层间缺口…仍缺 0 只`（raw/norm 代码集合一致）。
3. `meta/ingest_log.jsonl` 该 run 条目 `status=OK`，`action=write`。
4. 抽样对账（`scripts/run_l3_valuation_reconciliation.py`）在更大样本上复跑，
   `impossible` 判据仍为 0（PIT 判据不因全量数据变化）。
5. CI 六项全绿（提交门禁）。

## 5. 已知残留风险

* **norm 层规模**：全量约 1,400 万行 / ~1.5GB CSV。`PitSnapshotStore.read_normalized()`
  为全量入内存 —— **当前无 L3 消费者**（对账脚本实时查 baostock），暂无触发路径；
  首个消费者出现前必须先改流式读取（已在审计报告 P5 之外单列）。
* **半个 code 残留**：`--rebuild-norm` 按 code 粒度判定完整性，前提是 norm 里不存
  「同一 code 只有部分日期」的行。本次归档已清除该类残留；**今后任何写入 norm 的
  故障都可能重新引入**，`--rebuild-norm` 遇到「raw 有、norm 无」之外的异常只报不猜。
* **吞吐**：实测约 4.1s/只（含 2,533 行/只），全量约 6.5 小时；期间任何崩溃均可
  `--resume` 续跑 + `--rebuild-norm` 补齐。
* **挂起（hang）原不在韧性覆盖内** —— 2026-10-13 10:55 实测：进程自 08:53 卡死
  2 小时（baostock 连接 Established 但无响应，CPU 6%），**挂起不抛异常 → 重试绕过**。
  已修复（commit `d228865`：`_fetch_l3` 抓取前 `socket.setdefaulttimeout(120s)`，
  挂起改抛 `TimeoutError` 落入既有重试通道 + 3 项守卫测试）。
  **2026-10-13 12:0x 机制验证**：独立探针进程实测 `setdefaulttimeout(120)` + 登录后
  `default_socket.gettimeout() == 120.0`（baostock 0.9.3 为纯 Python 包、走 stdlib socket，
  超时对其有效）；挂起最坏耗时 ≈ 120s×3 次尝试 + relogin 二次等待 ≈ **~12.5 min/只**
  后被跳过（WARN 记账，`--resume` 补采）。
  **14:16 生产检验**：全量回填途中 3 次 `timed out` + 3 次 WinError 10054 + 2 次 utf-8
  解码错均自动恢复，无一码跳过 —— 韧性三层修补（重试/跳过/缺口显式化）有效。
  **残留**：若 120s 超时后 3 次尝试全败，该只被跳过（WARN 记账），需 `--resume` 补采；
  relogin 中 `logout` 在死 socket 上提前返回不关连接，每次挂起泄漏 ≤3 个僵连（规模可接受）。
* **北交所 920 段：baostock 源不覆盖（≠ 数据不存在）**：universe 5,667 中 281 只 920 段
  （北交所新代码段）代码 baostock 全部返回 success+0 行（12/12 抽样实测；L1 快照
  920/4/8 段同为 0 只）→ **本侧 PIT 快照（baostock 源）不含该段**。
  **2026-10-14 主干 P010 评审修正（Q1(b)）**：主干侧通达信 vipdoc **实测覆盖 920 段
  350 只、全部有历史**（`920000`=1,403 条等）→ 正确表述是「**baostock 源不覆盖，
  该段数据需改用其他源**」，**不得**写成「永久缺失」
  （「源覆盖差」与「数据不存在」是两件事，按「空结果 ≠ 无对象」纪律分开）。
  ⚠️ **2026-10-15 补正（可行性调研）**：**「改用通达信」不成立** —— 通达信 `.day`
  只有 OHLCV，而 L3 的核心是**估值比率**（`L3_FIELDS` = close/peTTM/pbMRQ/psTTM/
  pcfNcfTTM/turn/tradestatus/isST）⇒ 该源**无法提供 L3 所需字段**。
  可行源实测为 **tushare `daily_basic`**（BSE 350 只覆盖、含 pe_ttm/pb/ps_ttm/
  turnover_rate；频率限制 1 次/分钟）→ 详见 `PIT_L3_920_BACKFILL_FEASIBILITY.md`。
  清单：`D:/pit_snapshots/meta/l3_zero_data_codes_2026-10-13.txt`。
  **两种零数据形态分开记账**（P010 Q1.3）：`sh./sz.` 前缀 success+0 行 = 源无数据；
  `bj.` 前缀 `10004011` = 源不接受符号格式 —— `_fetch_l3` 的
  `zero_data` / `zero_data_prefix_rejected` 双清单即此分工（号段映射保持 `9→sh`：
  baostock 本端点只认 sh/sz，改发 bj. 只会把静默空响应变成 loud failed）。
  连带效应：零数据代码永不落 raw → 任何后续 `--resume` 都会重试它们并在 `min_rows`
  上**假性 FAIL**（0 < 1000）；已由零数据边车清单 + `--resume` 排除解决
  （`420232d`，实测排除 281 只后退出码 0）。

## 6. 执行记录（2026-10-13 06:4x，实际操作结果）

| 步 | 动作 | 结果与证据 |
|---|---|---|
| 1 | 归档 raw `2026-10-12.jsonl` | 239,080,703 B → `raw/baostock/query_history_k_data_plus/_archive/`；sha256 `d4d4183e…` **移前移后逐位一致** |
| 2 | 归档 norm `2026-10-12.csv` | 33,701 B → `normalized/l3_valuation/_archive/`；sha256 `146b16f7…` **移前移后逐位一致** |
| 3 | `meta/ingest_log.jsonl` 留痕 | 追加 2 条：`action=archived`（含 from/to/bytes/sha256/next）· `action=note, status=ANOMALY` |
| 4 | **发现孤立日志缺口** | 条目 `20261012-2042`（ts 2026-10-12T20:42:48，3 只/174 行，raw/norm sha256 俱全）声称写入 `ingest_date=2026-10-13`，但两文件实测均不在（全盘搜索无其他快照根）；bash 历史不可用，去向无法重建 → 已显式留痕 **不静默跳过**。归档清点确认 2026-10-13 命名空间为空，不影响重采 |
| 5 | 全市场回填重启 | `--dataset l3_valuation --root D:/pit_snapshots --date 2026-10-13 --universe D:/tdx_dataset_v3 --start 2016-01-01 --end 2026-10-13 --resume --flush-every 100`（5,667 只；实测约 6.5h；日志 `meta/l3_backfill_2026-10-13.log`） |
| 6 | **回填完成（14:16，历时 3h07m）** | 续采 2,367 只 → 落盘 2,086 只 / 3,999,734 行；raw 累计 **11,060,152 行 / 5,386 只**；**韧性修复生产检验**：`timed out`×3 + WinError 10054×3 + utf-8 解码错×2 全部经重试恢复，`n_failed_codes=0`（无一只跳过）；**自检 FAIL 退出码 2**：601718 真截断（2000→2614 行，按预案取全量 2,614 行落盘，raw 中恰为 2000 行的 code 现存 0 只） |
| 7 | 层间缺口闭合（`--rebuild-norm`，14:26，退出码 0） | 从 raw 幂等补建 **3,300 只 / 7,060,418 行**（与 08:53 跑落盘数一致）→ 层间缺口 raw 5,386 vs norm 5,386 = **0**；ingest_log 记 `action=rebuild-norm, status=OK` |
| 8 | **281 只缺口定性**（不静默） | universe 5,667 − raw 5,386 = 281，**全部为 920 段（北交所新代码段）**；12/12 抽样直查 baostock：`error_code=0` 且 0 行（success 空响应），本地 tdx 每只 431~1,523 行 → **baostock 匿名源不覆盖 920 段**（L1 快照 920/4/8 段同为 0 只），系源覆盖差而非采集失败；清单存 `meta/l3_zero_data_codes_2026-10-13.txt`。**2026-10-14 P010 修正**：主干侧 tdx 实测覆盖该段 350 只 → 定性改述为「baostock 源不覆盖、该段需换源」（非「永久缺」，见 §5） |
| 9 | 对账复跑（n=60，2023-2025） | `impossible = 0`（P2 为 n=24）；bps 中位相对差 0.0、≤1% 占 93.85%；结果 `reports/l3_reconciliation_n60_2026-10-13.json`。**性质标注（P010 Q3.1）**：此为**逻辑一致性检查**（判据为逻辑判据，无需大样本即可证伪），**不是统计代表性检查**（n=60 对 1% 错误率检出概率仅 ~45%） |
| 10 | 回填后验收 | §4 五条：① ❌ 见下「退出码说明」② ✅ 缺口 0（rebuild 退出码 0）③ ✅ FAIL/OK 均如实留痕 ④ ✅ impossible=0（n=60）⑤ 见 CI 运行结果 |

**退出码说明（验收①的诚实偏差）**：采集主跑退出码为 2（非 0），唯一 FAIL = 601718 真截断——
其数据影响已在跑内按预案消除（全量 2,614 行落盘），且 `n_failed_codes=0`。未做「收官
resume 跑」的原因：剩余 281 只零数据代码永不落 raw，收官跑必然 `n=0 < min_rows=1000`
触发**假性 FAIL**（阈值只为拦「整体抓取失败」），且每次 `--resume` 都会重试它们。
→ 建议后续修：resume 侧读取零数据代码边车文件（本次已生成清单）或 universe 侧
排除无覆盖代码段；在修复前，任何 L3 `--resume` 都会重复此假 FAIL。

**环境备忘**：采集必须用**系统 Python 3.13.15**（`C:/Users/T430/AppData/Local/Programs/Python/Python313/python.exe`，
baostock 0.9.3）；隔离 venv 无 baostock。**后台运行必须用受管后台任务**——
`nohup … &` 分离的进程会随工具壳层退出被静默 kill（日志无 traceback，2026-10-13 06:44 实测）。
