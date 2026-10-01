# 每日运行手册（TDXDaily）

> 建立时间：2026-10-01　状态：**已注册并验证通过**

---

## 一、当前状态

| 项 | 值 |
|----|----|
| 计划任务名 | `TDXDaily` |
| 触发时间 | 每周一至周五 **15:30** |
| 状态 | Ready（已启用） |
| 执行链路 | 任务计划程序 → `run_daily.bat` → `python -m tdx_native.run_daily` → `reports/daily/run.log` |
| 链路验证 | ✅ 2026-10-01 19:46 手动触发，返回码 **0**，日志正常落盘 |
| 上次运行 | 2026-10-01 19:46（显示"数据未更新"跳过——节假日期正常） |

---

## 二、每天自动做什么

`run_daily` 一次完成四件事（固定执行配置：C20 + V1 尾部剔除 + V2 跳空过滤 + 前复权 + ST 剔除 + 持有 20 日）：

1. **生成推荐报告** → `reports/daily/recommend_{日期}.md`（含股名、雪球链接、风险标签）
2. **导出通达信自选股** → `reports/daily/selected_stocks_{日期}.txt`
3. **登记跟踪样本** → `reports/daily/tracking.csv`（幂等：同日重复只补新增）
4. **回填到期样本** → `reports/daily/tracking_filled.csv`（T+5 / T+20 真实收盘收益 + 胜率）

---

## 三、唯一需要你做的事

**交易日盘后（15:00 之后）至少开一次通达信客户端**，让它把当日的 `.day` 数据下载到本机。

如果没开：任务会检测到"数据未更新"，打印一条跳过信息就退出——**不会报错、不会写脏数据**，
只是当天没有新推荐。

> 设计如此：宁可跳过，也不要用过期数据产出看起来像今天的报告。

---

## 四、怎么看结果

| 想看什么 | 打开 |
|---------|------|
| 当日候选清单 | `reports/daily/recommend_{日期}.md` |
| 导入通达信自选股 | `reports/daily/selected_stocks_{日期}.txt` → 通达信里 **Ctrl+D → 批量导入** |
| 推荐的历史跟踪表现 | `reports/daily/tracking_filled.csv` |
| 任务运行日志 | `reports/daily/run.log` |

---

## 五、手动操作

```bash
# 手动跑一次（等价于任务触发）
#   方法1：双击项目根目录的 run_daily.bat
#   方法2：命令行
python -m tdx_native.run_daily

# 数据未更新也想强制重跑（例如调了参数）
python -m tdx_native.run_daily --force

# 附加飞书群机器人推送（需自备 Webhook URL）
python -m tdx_native.run_daily --feishu-webhook https://open.feishu.cn/...
```

```powershell
# 暂停 / 恢复 / 删除计划任务
Disable-ScheduledTask -TaskName TDXDaily
Enable-ScheduledTask  -TaskName TDXDaily
Unregister-ScheduledTask -TaskName TDXDaily -Confirm:$false

# 查看下次运行时间与上次结果
Get-ScheduledTaskInfo -TaskName TDXDaily
```

---

## 六、故障排查

| 现象 | 原因 | 处理 |
|------|------|------|
| 日志显示"跳过：数据未更新" | 通达信客户端没更新数据 | 开通达信下载数据 → 手动跑一次 |
| 报告日期还是旧的 | 同上 | 同上 |
| 到点没运行 | 电脑关机 / 休眠 | 任务设了 `StartWhenAvailable`，**开机后会自动补跑** |
| 运行日志没有内容 | `run_daily.bat` 里的路径变了 | 检查 bat 内的项目路径与 python 路径 |
| 报告里出现 ST 股票 | `data/names.csv` 过期 | 重跑 `python -m tdx_native.fetch_names` |

---

## 七、跟踪数据什么时候有意义

`tracking.csv` 现在有 20 条待回填样本（0928 推荐）。每条需要等 **T+5 / T+20** 个交易日才能回填真实收益。

- 每天跑一次 → 样本自动积累；
- 积累 **1-2 个月**后，`tracking_filled.csv` 会有初步的胜率与收益分布；
- 积累 **3-6 个月**后，才有统计上可参考的跟踪结论。

这是本项目 L3 校准闭环的**唯一真实数据来源**——它比任何回测都更能说明这套推荐的质量。

---

## 八、必须记住的前提

- 推荐结果**不构成投资建议**。五因子是统计特征，本项目已用 15 项实验验证：
  它在 2021-08~2026-09 无法产生可实现的超额收益（详见 `STEP1_3_EXECUTION_REPORT.md`）。
- 本系统的定位是「**透明、可解释、可跟踪校准的候选清单**」，
  它不宣称 alpha，也不承诺跑赢基准。
- 正因为如此，**跟踪数据（第三节→第七节）才是这个系统最重要的产出**——
  它是用来检验推荐质量、而不是用来赚钱的。
