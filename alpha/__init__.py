# -*- coding: utf-8 -*-
"""Alpha 假设实验与存活实验室。

- `alpha_experiment`     —— 单一经济假设的因子检验入口
- `alpha_survival_lab`  —— Alpha 存活实验协议（预登记门槛、INCONCLUSIVE 兜底）

共同红线：
1. 假设须预先登记（样本外起点、显著性门槛），不得事后调参挑结论。
2. 不把工程/样本内实验结果包装成真实 Alpha 结论。
3. 数据不足或证据缺失时强制返回 `INCONCLUSIVE`，不补造、不推断为有效。
"""
