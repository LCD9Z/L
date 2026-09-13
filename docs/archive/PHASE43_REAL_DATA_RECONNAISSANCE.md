# PHASE 43 — 真实 A 股日线数据接入与价格因子侦察

## 本阶段目标

把“按交易日一个 CSV 文件、每行一个证券”的公开 A 股日线格式接入项目，并提供适合 8GB 机器的流式价格因子侦察路径。

## 支持的源格式

`symbol,date,open,close,high,low,volume,amount`

典型来源包括 `guidebee/china-stock-data`：其仓库说明该数据为每日交易后自动更新的中国股票日线，目录按 `data/price/YYYY/MM/stock_price_YYYY_MM_DD.csv` 组织；股票类型同时包含 A 股、B 股、科创板和北交所。因此接入层显式排除 B 股，并保留 92xxxx 北交所代码。

## 新增模块

- `daily_csv_adapter.py`：源格式解析、代码规范化、B 股过滤。
- `recon_price_factor_lab.py`：逐股票滚动窗口、逐文件处理、JSONL 增量输出；不需要把全市场历史矩阵一次性装入内存。
- `test_phase43_real_data_adapter.py`：覆盖真实源字段形状、B 股过滤、滚动窗口输出。

## 因子侦察范围

沿用当前 bar-only 因子：

- 5/10/20/60 日动量
- 5/20 动量加速度
- 20 日突破
- 20/60 日实现波动率
- 20 日回撤/区间
- 5/20 日成交量比
- 5 日成交额比
- 20 日平均换手率（仅在源数据提供 turnover 时）

## 研究边界

本阶段 **不是 Alpha 结论**。公开日线源本身不等于 PIT 证券主表、历史 ST/停牌状态、完整退市历史、公司行为调整或真实交易成本数据。`recon_price_factor_lab.py` 仅用于确认真实源数据能够顺利进入因子计算，并侦察价格/成交量因子的横截面形态。

最终 Alpha 仍必须经过：

1. 认证数据与 SHA-256 清单
2. PIT 历史证券宇宙
3. 历史 ST/停牌/退市状态
4. 公司行为与复权一致性
5. Walk-Forward / OOS
6. A 股执行规则与交易成本
7. 基准比较

## 外部数据依据

- guidebee/china-stock-data README：公开中国 A 股/B 股/科创板/北交所日线数据及字段说明。
- irachex/open-stock-data：公开 CN A-share daily bars 数据发布方案，可作为后续第二数据源交叉验证候选。
