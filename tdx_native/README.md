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
    --names D:/names.csv --events-cache data/gbbq_events.csv
```

> `--build` 需要 `pytdx`（gbbq 是 3DES 加密），只做一次；跑分全程纯标准库。

## 目录

| 文件 | 作用 |
|------|------|
| `day_reader.py` | `.day` 二进制解析（`<IIIIIfII`，价格÷100）、股票过滤、尾部/全量读取、板块涨跌停 |
| `five_factor.py` | 五因子引擎（冻结口径）+ 横截面分位合成 |
| `gbbq_reader.py` | 权息（gbbq）解密与缓存（`--build` 需 pytdx）+ 纯标准库读取 |
| `adjust.py` | 前复权（基于权息事件，纯标准库） |
| `screen.py` | 入口：扫描 → 过滤 → 复权 → 打分 → Top-N 输出 |
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
3. **无名称/ST 信息**：`.day` 不存名称与 ST 标记；不提供 `--names` 时**不做 ST 剔除**。
4. **数据区间**：本机 TDX 覆盖约 2021-08 ~ 至今（约 1250 个交易日）。
5. **不构成投资建议**：五因子是统计特征，非收益承诺；本包从不宣称 alpha 或跑赢基准。

## 全市场复检结论（reports/tdx_ic_full.json）

| 因子 | 全市场 IC / t | v2 研究 | 判定 |
|------|--------------|---------|------|
| maxret20 | -0.0787 / -7.78 | -0.0752 / -12.19 | ✅ 稳健 |
| vol20 | -0.0823 / -6.32 | -0.0773 / -9.91 | ✅ 稳健 |
| ret20 | -0.0765 / -7.51 | -0.0488 / -7.48 | ✅ 稳健（更强） |
| loga20 | -0.0373 / -4.99 | -0.0676 / -10.28 | ✅ 方向一致（较弱） |
| amihud20 | **-0.0210 / -2.26** | **+0.0325 / +5.23** | ⚠️ **符号翻转，不稳健** |

另：剔除"窗口内含超涨跌停跳空"的样本后各因子 IC 下降 **18%~28%**，
即约两成 IC 来自最难交易的那批样本。

## 与本项目其余资产的关系

- 因子方向与判定证据：`reports/v2_factor_study.json`（五因子 t≥5）
- 已验证的最稳组合配置：C20 + V1 尾部剔除 + 持有 20 日（见 `STEP1_3_EXECUTION_REPORT.md` §11/§18）
- 本包是「推荐系统」定位下的**选股侧引擎**，配套的 L3 跟踪校准见 `tracking.py`
