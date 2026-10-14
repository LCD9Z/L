# tdx_native — 五因子选股 × 通达信原生数据 测试包

把五因子研究成果（ret20 / vol20 / amihud20 / loga20 / maxret20，方向冻结）
直接接到**通达信本地 `.day` 二进制日线**上，在本机跑出当日 Top-N 选股清单。
**零第三方依赖**（纯标准库 `struct`/`csv`/`math`/`statistics`），只读每只股票
文件**尾部 80 根**，适配低配机器（i5-3320M / 7.8GB）。

## 快速开始

```bash
# 自测（不依赖真实数据，生成合成 .day 验证整条链路）
python -m tdx_native.smoke_test

# 真实运行（通达信安装目录的 vipdoc）
python -m tdx_native.screen --vipdoc D:/new_tdx/vipdoc --top 20

# 带 V1 尾部剔除（剔除当日 ret20 最高 20%，对应研究中已验证的 V1 改善）
python -m tdx_native.screen --vipdoc D:/new_tdx/vipdoc --top 20 --exclude-ret20-top 0.20

# 启用前复权（推荐）：先用 pytdx 建一次权息缓存，之后跑分全程零依赖
python -m tdx_native.gbbq_reader --build \
    --gbbq D:/new_tdx/T0002/hq_cache/gbbq --out-cache data/gbbq_events.csv
python -m tdx_native.screen --vipdoc D:/new_tdx/vipdoc --top 20 \
    --events-cache data/gbbq_events.csv --out reports/tdx_native_screen.json

# 带名称映射（启用名称显示 + ST 剔除）
python -m tdx_native.screen --vipdoc D:/new_tdx/vipdoc --top 20 \
    --names data/names.csv --events-cache data/gbbq_events.csv
```

> `--build` 需要 `pytdx`（gbbq 是 3DES 加密），只做一次；跑分全程纯标准库。

## 每日一键运行（推荐方式）

```bash
# 一次性准备（已完成可跳过）：
#   1) 权息缓存：python -m tdx_native.gbbq_reader --build ...
#   2) 名称表：python -m tdx_native.fetch_names --out data/names.csv

# 每个交易日收盘后（15:05 之后）一条命令：
python -m tdx_native.run_daily
# 可选推送到飞书群机器人：
python -m tdx_native.run_daily --feishu-webhook https://open.feishu.cn/...
```

`run_daily` 一次完成四件事（固定执行配置 C20+V1+V2+前复权+ST 剔除）：
`run_daily` 一次完成五件事（固定执行配置 C20+V1+V2+前复权+ST 剔除）：

1. **生成推荐报告** `reports/daily/recommend_{日期}.md`（含雪球链接、风险标签）
2. **导出通达信自选股** `selected_stocks_{日期}.txt`（客户端 Ctrl+D → 批量导入）
3. **登记跟踪样本** 到 `tracking.csv`（幂等：同日重复运行只补新增）
4. **回填到期样本** 到 `tracking_filled.csv`（T+5/T+20 真实收盘收益 + 胜率统计）
4. **回填到期样本** 到 `tracking_filled.csv`（T+5/T+20 真实收盘收益 + 胜率统计
   + **全市场等权基准**对照）
5. **到期卖出提醒** `exits_{日期}.md`（持有 20 日到期的持仓清单——
   补上"何时离场"这一半闭环）

内置**未收盘保护**：检测到今日 bar 而时间未过 15:05 时拒绝运行，
避免半日数据污染口径。

**Windows 自动调度**（可选）：项目根有 `run_daily.bat`（日志落
`reports/daily/run.log`）。注册每日 15:30 任务：

```
schtasks /create /tn TDXDaily /tr "C:\Users\T430\Desktop\1.0\run_daily.bat" /sc weekly /d MON,TUE,WED,THU,FRI /st 15:30
```

前提：交易日盘中至少开一次通达信客户端让它把 `.day` 下载到最新（或手动盘后下载）。
**Windows 自动调度**：✅ **已注册**（2026-10-01）——计划任务 `TDXDaily`，
每周一至周五 **15:30** 自动运行 `run_daily.bat`。
运维细节（查看结果 / 手动操作 / 故障排查）见 **[`DAILY_OPERATION.md`](../DAILY_OPERATION.md)**。

前提：交易日盘后至少开一次通达信客户端让它把 `.day` 下载到最新。
未更新时脚本会检测到并打印跳过信息退出（不会用过期数据产出像今天的报告）。

内置**数据未更新保护**与**未收盘保护**：前者避免节假日重复产出，
后者避免把半日数据写入 `tracking.csv` 污染样本。

```bash
# 数据未更新时如需强制重跑
python -m tdx_native.run_daily --force

# 手动操作计划任务
Disable-ScheduledTask -TaskName TDXDaily      # 暂停
Unregister-ScheduledTask -TaskName TDXDaily -Confirm:$false   # 删除
```

## 目录

| 文件 | 作用 |
|------|------|
| `day_reader.py` | `.day` 二进制解析（`<IIIIIfII`，价格÷100）、股票过滤、尾部/全量读取、板块涨跌停 |
| `five_factor.py` | 五因子引擎（冻结口径）+ 横截面分位合成 |
| `gbbq_reader.py` | 权息（gbbq）解密与缓存（`--build` 需 pytdx）+ 纯标准库读取 |
| `adjust.py` | 前复权（基于权息事件，纯标准库） |
| `screen.py` | 入口：扫描 → 过滤 → 复权 → 打分 → Top-N 输出 |
| `fetch_names.py` | 从通达信行情服务器拉代码→名称表（pytdx，容忍空页全量扫描） |
| `daily_report.py` | 日度推荐报告（md + json + tracking.csv 幂等登记） |
| `backfill.py` | L3 跟踪回填：T+5/T+20 真实收盘收益、胜率、指数参照 |
| `run_daily.py` | 每日一键：推荐 + 自选股导出 + 回填 +（可选）飞书推送 |
| `smoke_test.py` | 冒烟自测（.day 往返 / 因子精确值 / 端到端） |
| `_smoke/` | 自测生成的合成数据（不删除） |

## 五因子口径（与 v2 研究一致）

| 因子 | 定义 | 方向 |
|------|------|------|
| ret20 | close[-1]/close[-21] − 1 | **-1**（反转） |
| vol20 | 20 日日收益标准差 | **-1**（低波） |
| amihud20 | mean(\|ret\|/amount, 20) | **+1**（非流动性溢价） |
| loga20 | log1p(mean(amount,20)) | **-1**（规模） |
| maxret20 | max(日收益, 20) | **-1**（MAX/博彩） |

流动性门槛：20 日均成交额 ≥ 1 亿。得分 = 五因子方向化分位均值。

## 必须知晓的局限（如实声明）

1. **不复权价（已验证影响很小）**：不提供 `--events-cache` 时为原始价。
   实测（全市场 5613 只、245 个不重叠截面）原始价与复权价的因子 IC 差异 ≤0.001，
   即**在 20 日横截面因子层面影响可忽略**；但回测 P&L 与个股权息仍必须复权
   （案例：000028 在 2026-06-24 原始 -13.70% 的"暴跌"，复权后仅 -2.47%）。
2. **幸存者偏差**：本地 TDX 通常只含存续标的，不含已退市股。
3. **名称/ST 依赖 names.csv**：`.day` 不存名称。已生成 `data/names.csv`
   （2026-09-30，47,846 条，universe 覆盖 93.4%，未命中多为已退市股）。
   **北交所在测试的 20 台行情服务器上均不可用** → 北交所标的无名称、
   不做 ST 剔除（已知局限）；沪深 ST 剔除正常（209 只 ST 中当日剔除 198 只）。
   名称表变化缓慢，约每季度重跑 `fetch_names` 一次。
4. **数据区间**：本机 TDX 覆盖约 2021-08 ~ 至今（约 1250 个交易日）。
5. **不构成投资建议**：五因子是统计特征，非收益承诺；本包从不宣称 alpha 或跑赢基准。

## 全市场复检结论（reports/tdx_ic_full.json）

| 因子 | 全市场 IC / t | v2 研究 | 判定 |
|------|--------------|---------|------|
| maxret20 | -0.0787 / -7.78 | -0.0752 / -12.19 | ✅ 稳健 |
| vol20 | -0.0823 / -6.32 | -0.0773 / -9.91 | ✅ 稳健 |
| ret20 | -0.0739 / -7.23 | -0.0488 / -7.48 | ✅ 稳健（更强） |
| loga20 | -0.0373 / -4.99 | -0.0676 / -10.28 | ✅ 方向一致（较弱） |
| amihud20 | **-0.0210 / -2.26** | **+0.0325 / +5.23** | ⚠️ **符号翻转，不稳健** |

另：剔除"窗口内含超涨跌停跳空"的样本后各因子 IC 下降 **18%~28%**，
即约两成 IC 来自最难交易的那批样本。

## 格式备忘（复用知识，实测确认）

**日线 `.day`**（`vipdoc/{sh,sz,bj}/lday/{market}{code}.day`）
- 32 字节/条，`struct <IIIIIfII` = date(int YYYYMMDD), open, high, low, close（int，**÷100** 得元）,
  amount(**float32**，元), volume(int, 股), reserved(int)
- 按日期升序排列 → 只读尾部即可拿到最近 N 根（本包默认 80 根，省内存）
- 常见坑：把 OHLC 按 float32 读会得到 1e-44 量级的假价格

**权息 `gbbq`**（`T0002/hq_cache/gbbq`）
- **3DES 加密**：前 24 字节加密、后 5 字节明文；头部 4 字节为记录数，其后 29 字节/条
- 记录布局：`market(1) code(7, ASCII 含结尾 0) date(4) category(1) d1..d4(各 4 字节 float)`
- `category=1` 为除权除息：d1 分红、d2 配股价、d3 送转股、d4 配股（**均按每 10 股**）
- 解密需密钥表 → 用 `pytdx.reader.gbbq_reader.GbbqReader`（本包 `gbbq_reader.py --build` 调用一次，
  结果缓存为 CSV，之后主流程零依赖）

**前复权**
- `k = (前收盘 − 每股派息 + 配股价×每股配股) / (前收盘 × (1 + 每股送转 + 每股配股))`
- 前复权 = 事件日**之前**的价格乘以该事件及之后所有事件的 k 连乘
- 验证方法：找一只近期除权的股票，对比事件日原始涨跌与复权涨跌
  （本包实测 000028 @2026-06-24：原始 **-13.70%** → 复权 **-2.47%**）

## 与本项目其余资产的关系

- 因子方向与判定证据：`reports/v2_factor_study.json`（五因子 t≥5）
- 已验证的最稳组合配置：C20 + V1 尾部剔除 + 跳空过滤 + 持有 20 日（见 `STEP1_3_EXECUTION_REPORT.md` §11/§18/§25）
- 本包是「推荐系统」定位下的**选股侧引擎**，L3 跟踪校准即 `backfill.py`（T+5/T+20）

## 借鉴来源（2026-09-30 GitHub 产品化调研，详见 GITHUB_ASHARE_QUANT_SURVEY.md 续篇）

| 来源 | 借鉴点 |
|------|--------|
| sngyai/Sequoia-X（7.6k★） | 收盘后一键运行；飞书 Webhook 卡片格式；雪球个股链接；名称表思路（其用 baostock，本包改 pytdx 零新增依赖） |
| oficcejo/tdx-local2 | 直接读 `.day` 不转储（验证本包架构方向）；通达信自选股 txt 导出 |
| ArvinLovegood/go-stock（7.7k★） | 「AI 分析工具」定位中对推送报警的产品化形态（参考，未采用 AI 生成——预注册纪律禁止随意生成策略） |

工程上刻意**未借鉴**的部分：Sequoia-X 的策略集（海龟/旗形等 6 种技术形态策略）
没有引入——本项目的纪律是预注册 + 证伪，不新增未经验证的策略；tdx-local2 的
AI 生成选股代码同理。
