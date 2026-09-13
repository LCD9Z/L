# Phase 34 — 全市场两级筛选与可恢复批处理

## 目标

将 AI 深度分析从“逐股调用”改成：

`全A股数据快照 → 机器硬过滤 → 基础流动性/风险 → 截面多因子排序 → 300 → 资金流/事件 → 50 → AI委员会 → 10~20 → 交易/风控`

## 8GB 设计

- JSONL 流式读取，不把全市场一次载入内存。
- Top-K/阶段结果只保留少量候选。
- checkpoint 原子写入，异常或手动停止后可 `--resume`。
- 单行错误隔离，超过错误预算才终止。
- AI 不参与全市场初筛。

## PIT

`--universe` 必须是指定研究时点已经截断的数据快照。V3.4 不会把当前行情倒填到历史时点。

## 数据源边界

本阶段提供的是**筛选框架与 provider contract**，不是虚构的“已连接全A股实时数据”。Tushare/TDX/其他合规数据源应在上游生成 JSONL 快照后接入。Crawl4AI 继续负责网页正文抓取/清洗，不承担股票全市场行情枚举。

## 命令

```bash
python run_pipeline.py --universe universe.jsonl --mode overnight --profile lite
python run_pipeline.py --universe universe.jsonl --mode overnight --profile lite --resume
```
