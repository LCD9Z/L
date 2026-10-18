# 自动化记忆 · 副本侧跨线成本口径重算 进度与验收

任务 ID: d7931b8d-2fcc-45ae-8e69-988c985c87dc
活主干: D:\hunhe\trunk（勿用 Desktop\1.0）
解释器: C:\Users\T430\.workbuddy\binaries\python\envs\default\Scripts\python.exe

## 判定分支（写死在任务里）
- 副本侧 15 个跨线窗口未齐 → 只追加当日日志一行进度，结束
- 已齐 → ①停用计划任务 ②V1~V5 验收（比照主侧 d312c51）③写回执到
  D:\hunhe\_AI协作信箱\02_回执\验收事由_主干_日期.md ④台账 00_提案台账.md 追加区块
  ⑤停用本自动化（automation_update status=PAUSED）

## 执行记录
| 日期 | 进度 | 分支 | 备注 |
|---|---|---|---|
| 2026-10-16 18:56 | 副本侧跨线 0/15（全量 0/52） | 仅记日志 | 任务 RecomputeCopyCrossing 仍在 Running（PID 15948，10:33 启动）；主侧 28/28 已齐；有 combo_study_h20_2023-07-03.json.partial 残留 |
| 2026-10-16 21:33 | 副本侧跨线 8/15（全量 8/52） | 仅记日志 | 推进正常（worker PID 17636）。验收预判：8 份精确对账 V1=0，V2 仅 2 份有差异且幅度 +26~37pp（=基线演进，非印花税）；6 份逐位零差异——因数据集日期带横杠，原 bug 未触发。另：checker 前缀 glob 有歧义（combo_study_h20/ tc_t2） |
| 2026-10-16 22:03 | 副本侧跨线 **9/15**（全量 9/52） | 仅记日志 | 本轮唯一新增 = `tc_t2_2023-07-03.json`（21:43）。9 份全部 @2023-07-03；剩余 6 个跨线窗口全在 3 个 rolling_eval 任务（各 2：2023-01-03、2023-07-03），产物目录尚无对应 json。未写回执/未动台账/未停任务/未停自动化。 |
| 2026-10-16 19:58 | 副本侧跨线 3/15（全量 3/52） | 仅记日志 | 新增 combo_study_h20 / combo_study_h20_fixed / cost_model_check @2023-07-03；任务仍 Running |
| 2026-10-16 21:00 | 副本侧跨线 6/15（全量 6/52） | 仅记日志 | 新增 five_factor_ab_v2 / horizon_study / horizon_study_turnover_fixed @2023-07-03；任务仍 Running；剩余 9 个（impact_cost/tc_t0/tc_t2 各 1，三个 rolling_eval 各 2） |
| 2026-10-16 23:05 | 副本侧跨线 **9/15**（全量 9/52） | 仅记日志 | 末份 tc_t2_2023-07-03 21:43 落盘，此后 82 min 无新增；任务仍 Running（23:04 重启，NextRun 23:34）；剩 6 个全在三个 rolling_eval 任务 |
| **2026-10-17 00:07** | 副本侧跨线 **9/15**（全量 9/52） | 仅记日志 | ⚠️ **剩 6 个是「跑不通」非「待跑」**：三个 rolling_eval 各 2 窗口全部 12~33s `exit=2`，阻断 = `preflight: LIMITED_OR_FAIL` / `['benchmark','insufficient_per_asset_history']`。写 2026-10-17.md。未写回执/未动台账/未停任务/未停自动化 |
| **2026-10-17 01:09** | 副本侧跨线 **9/15**（全量 9/52） | 仅记日志 | 与 00:07 无变化：01:07 那轮仍 6 窗 `exit=2` 空转，产物不增。追加日志第 ⑫ 条。**阻塞未解前本分支不可达**；连续 2 轮空转，建议人工定口径（是否给副本 rolling_eval 补 `--benchmark`）后再继续 |
| **2026-10-17 02:11** | 副本侧跨线 **9/15**（全量 9/52，失败 6） | 仅记日志 | 与上轮无变化：02:04 那轮仍 6 窗 `exit=2`（`preflight: LIMITED_OR_FAIL`），最新产物停在 10-16 21:43；任务 State=Ready、NextRun 02:34:34。追加日志第 ⑬ 条。**连续 3 轮空转，分支③仍不可达，建议人工定口径** |
| **2026-10-17 03:13** | 副本侧跨线 **9/15**（全量 9/52，失败 6） | 仅记日志 | 与上轮无变化：03:05 那轮仍 6 窗 `exit=2`，产物仍停在 10-16 21:43；任务 State=Ready、Last 03:04:04、NextRun 03:34:34。追加日志第 ⑭ 条。**连续 4 轮空转，分支③仍不可达** |
| **2026-10-17 04:15** | 副本侧跨线 **9/15**（全量 9/52，失败 6） | 仅记日志 | 与上轮无变化：04:06 那轮仍 6 窗 `exit=2`，产物仍停在 10-16 21:43；任务 State=Ready、Last 04:04:04、NextRun 04:34:34。追加日志第 ⑮ 条。**连续 5 轮空转，分支③仍不可达**；建议人工裁定口径后再恢复本自动化 |
| **2026-10-17 05:16** | 副本侧跨线 **9/15**（全量 9/52，失败 6） | 仅记日志 | 与上轮无变化：05:04 那轮仍 6 窗 `exit=2`，最新产物仍停在 10-16 21:43；State=Ready。追加日志第 ⑯ 条。**连续 6 轮空转，分支③仍不可达** |
| **2026-10-17 06:18** | 副本侧跨线 **9/15**（全量 9/52，失败 0） | 仅记日志 | **性质变化**：⑰ 段（06:1x 人工）已定位双根因并**停用计划任务**（State=Disabled），且 **06:16:28 起手工按主侧全套参数重跑**（`run_recompute.py --side copy --crossing-only --batch 4` + `run_tdx_rolling_eval.py … --max-stocks 400 --min-rows-asset 504 --benchmark D:/tdx_dataset_v2/benchmark_ew.csv --skip-audit @2023-01-03`，非计划任务触发）⇒ 空转序列终止，进入「修正参数重跑中」。巡检时该批**尚未落盘**，仍 9/52。未写回执/未动台账/未再动任务/未停自动化。追加日志第 ⑱ 条。**下一轮重点看 rolling_eval 是否落盘** |

| **2026-10-17 07:21** | 副本侧跨线 **12/15**（全量 12/52） | 仅记日志 | **修复见效**：⑰ 段「补 `--benchmark`+`--min-rows-asset`+`--skip-audit`」实测解除 `exit=2`。新增 3 份 rolling_eval：`v2_rolling_eval_ew@2023-01-03`(06:25)、`@2023-07-03`(06:35)、`v3_rolling_eval_ew@2023-01-03`(07:00)。剩 3 窗在跑（batch 5，PID 18612，`v3_rolling_eval_ew@2023-07-03` 07:00 启动 + `v3_rolling_eval_ew_full` 两窗）。任务 `RecomputeCopyCrossing` 保持 Disabled。追加日志 ⑳ 段。分支③仍不可达 |
| **2026-10-17 08:3x** | 副本侧跨线 **15/15**（全量 15/52，失败 0） | **分支③完成** | 验收结果：**V1 缺键 6**（rolling_eval 的 `ew_*` 系列，属字段口径替换）· **V2 8/15 有差异**（7 窗口逐位零差异）· **V3 异常 15 处/8 窗口**（基准替换 + 基线演进）· **V4 过** · **V5 已标注**。已写回执 `02_回执/成本口径重算副本侧15跨线窗口验收_主干_2026-10-17.md` + 台账区块 + 登记册 §八；计划任务复核 Disabled 且无实例；**本自动化已 PAUSED**。⭐ **重大发现**：印花税缺陷因数据集 `date` 带横杠而**未触发**（全部差异实为 A2 基线演进，属「名义缺陷」）——详见回执 §五 |
| **2026-10-18 10:40** | 副本侧跨线 **15/15**（全量 **52/52**） | **复核（不重复交付）** | 自动化在 `PAUSED` 状态下被残余触发。只读复核结果：80 份聚合 md5 `471ac482…` 与回执 §20.5 **逐位相同**、15 份跨线 mtime 未变 ⇒ 同一批字节重跑判定。V1–V5 **全部与 §三 一致**（V1 缺键 6×9 键全 `ew_*` / V2 8/15 / V3 异常 15 处 8 窗 / V4 0 / V5 在册）。**未新建回执**，改在既有回执追加 §二十二；台账「2026-10-18（续十三）」。状态：任务 Disabled、实例 0、自动化 PAUSED、HEAD `7b32a34` 与远端同步。新发现仅卫生问题：`_recalc/` 下 9 个陈旧 `.partial`（未清理）。**下次若再触发，只需确认 52/52 与 md5 未变即可，勿重复写回执** |

## 关键事实（复用）
- `--list` 默认 side=copy，读的是 COPY_TASKS；主侧需 `--side main`
- 跨线窗口 = 起点 < 2023-08-28（CROSSING_CUT）
- 副本 12 份 / 52 窗口，其中跨线 15 个；主侧 12 份 / 28 窗口
- 产物 reports/_recalc/<name>_<window>.json（`_` 前缀命中 reports/_*.json 忽略规则）
- 缺陷 #15：_stamp_rate 字符串比较判日期

## ⚠️ 已知阻塞（2026-10-17 定位，勿重复排查）
剩 6 个跨线窗口全在三个 rolling_eval 任务（v2_rolling_eval_ew / v3_rolling_eval_ew /
v3_rolling_eval_ew_full，各 2 窗口：2023-01-03、2023-07-03），**永久失败**：
`scripts/run_tdx_rolling_eval.py:140` 的 `audit_research_evidence(...,min_rows_per_asset=min_periods*2)`
判 `LIMITED_OR_FAIL`，issues = `['benchmark','insufficient_per_asset_history']`（`return 2`，12~33 s 退出）。
- `'benchmark'` 来自 `professional_audit.audit_pipeline` 对 `<dataset>/benchmark.csv` 的 `audit_csv` 不过。
- 主侧同类 `v2_ew_bench_part1` 显式传 `--benchmark D:/tdx_dataset_v2/benchmark_ew.csv` 且跑通。
- **但改 args 会改变实验口径**（纪律 2.2）→ 必须人工定口径后再改，自动化不得自行修改。
- 结论：在阻塞解除前，副本侧跨线**永远停在 9/15**，分支③（验收/回执/停任务）不可达；
  下一个 30 min 触发周期只会再空转。日志：`runtime_logs/recompute_copy.log`。

**2026-10-17 06:18 更新**：阻塞已进入人工修复通道 —— 计划任务已停用（Disabled），
用户已裁定「照主侧全套参数（含 `--skip-audit`）」并手工重跑（06:16 起）。
**阻塞根因实为两条**（⑰ 段新增）：① `benchmark.csv.metadata.json` 命名不对称；②
`min_rows_asset` 未预过滤。仅补 `--benchmark` 不够，须同时补 `--min-rows-asset`。
⇒ 下一轮巡检若 15/15 达成，即走分支③（先确认无运行实例再验收）。

**2026-10-17 06:3x 更新（人工执行侧）**：修复已**落地**，非仅「重跑」——
- `scripts/run_recompute.py` 的 COPY_TASKS 三个 rolling_eval 任务已改写（还原
  `--max-stocks 400/1000 --min-rows-asset 504 --survivorship-evidence … --benchmark … --skip-audit`）；
- 已**新建** `D:/tdx_dataset_v3/benchmark_ew.csv`(+`.metadata.json`, strict+sha256)，依
  `P005_3_3_BENCHMARK_PREREG.md` §六（v3 无 benchmark_ew.csv 的补法），未动 v3 既有文件；
- 首窗 `v2_rolling_eval_ew@2023-01-03` 已 `exit=0`（537 s，池 400 只，基准字段为 benchmark_ew.csv）。
- ⚠️ **单窗约 9 min**（v3 千只更久）⇒ 6 窗或需 ~1 h；后台任务可能被 25–40 min 窗口截断，
  但**每窗各自落盘 + 默认 resume**，重跑同命令即续。
- ⚠️ 「v3 基准写入数据集目录」按预注册须**另行登记**，尚未补。
