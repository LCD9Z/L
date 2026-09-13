# Phase 23 TuShare 真实数据验证记录

## 安全原则
Token 只通过 `TUSHARE_TOKEN` 环境变量提供，绝不写入源码、JSON、日志或压缩包。

## 真实验证协议
1. 先调用 `stock_basic` 探针验证网络、Token 和接口权限。
2. 探针成功后下载固定代码/固定日期区间的日线数据。
3. 保存原始数据和 SHA-256 元数据。
4. 与第二数据源交叉检查价格与交易日。
5. 通过 Point-in-Time、交易规则和 Alpha Gate 后才允许进入 Alpha 结论。

## 当前执行环境限制
本构建环境 DNS/互联网访问不可用，且未安装 tushare，因此无法向 TuShare API 发出真实请求。
这不能判定 Token 无效，也不能验证“123 积分”对应的实际接口权限。
项目已加入可在网络环境中直接运行的探针与数据接入模块。

运行方式：
`export TUSHARE_TOKEN='你的Token'`
`python -c "from tushare_provider import TuShareProvider; print(TuShareProvider().probe())"`
