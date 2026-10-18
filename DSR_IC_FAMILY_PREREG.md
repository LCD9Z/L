# DSR 接线的口径预注册（A1）+ 统计层阳性对照（A4）

> **提出**：2026-10-18　**执行**：2026-10-18
> **状态**：**已执行** —— 判定见 `DSR_IC_FAMILY_VERDICT.md`
> 来源：`GITHUB_ASHARE_QUANT_SURVEY.md` §8.4 清单 A1 / A4

---

## 一、要解决的问题（含本轮最重要的项目侧发现）

### 1.1 「能力已实现」≠「能力在生效」

`validation/multiple_testing.py` 里 **已有**：

| 函数 | 当前调用方 |
|---|---|
| `benjamini_hochberg` / `bonferroni` / `family_wise_error_rate` | 生产（`scripts/run_multiple_testing_audit.py`、`scripts/run_fundamental_factor_study.py`） |
| `deflated_sharpe_ratio` / `probabilistic_sharpe_ratio` / `minimum_track_record_length` / `expected_max_sharpe` | **只有 `tests/`**，生产零调用 |

判据（可复现）：

```
grep -rn "deflated_sharpe_ratio|probabilistic_sharpe_ratio|minimum_track_record_length|expected_max_sharpe" \
     --include=*.py . | grep -v "^./validation/multiple_testing.py" | grep -v "^./tests/"
→ 空
```

⇒ **p 值校正做了，夏普比率校正没做**。且 `pytest` 全绿 ——
因为**测试就是唯一调用者**。这与「读磁盘能通过 ≠ 文件入库」同族：
**验证者与被验证者是同一个对象时，全绿不构成证据。**

⚠️ 排除测试时**不能**用 `grep -v test`：`multiple_testing.py` 文件名含
`testing`，会被一起滤掉（本轮已踩）；必须用 `grep -v "^./tests/"`。

### 1.2 为什么这件事对本项目是实质缺口

本项目累计跑了远多于 1 次统计检验，而**全部按单次检验的 t / p 门槛判定**。
p 值族校正（BH/Bonferroni/FWER）已接进生产，但：

- **p 值校正不处理「挑最优」**：在 m 次试验里取最大 ICIR 的那个因子，
  即使每次试验的 p 都各自 < 0.05，也不构成证据 —— 这是**选择偏差**，
  只有 DSR（以 `E[max SR]` 为基准）能量化。
- `reports/v3_fundamental_factor_study.json` 的 `multiple_testing` 记的是
  `m=7, bh_rejected=4, bonferroni_rejected=2, fwer_uncorrected=0.3017`
  —— 全是 p 值族口径，**没有一条夏普比口径的紧缩**。

---

## 二、落点选择：为什么接在因子研究脚本，而不是审计脚本

`run_multiple_testing_audit.py` **不能**接 DSR，原因是结构性的：

```
DSR / PSR / MinTRL 的入参是「逐期收益率序列」（returns: Sequence[Any]），
不是汇总统计量。
```

而全仓扫描 `reports/**/*.json`：**含 ≥20 长度数值序列的产物 = 0 个**
（复算命令见 VERDICT §二）。所有归档产物都只存聚合值
（ic_mean / icir / t / p / n_periods）⇒ 审计脚本手里根本没有序列。

真正持有序列的地方是 **`scripts/run_fundamental_factor_study.py`**：

| 位置 | 内容 |
|---|---|
| L221 | `series: Dict[str, List[float]] = {k: [] for k in HYPOTHESES}` —— 逐期 IC 序列在内存里 |
| L287 | `ics = series[k]` —— `summarize()` 就从它算出 ic_mean / icir / t / p |
| 产物 | `reports/v3_fundamental_factor_study.json`（已入库） |
| 数据集 | `D:/tdx_dataset_v3`（本地存在，280 MB） |

⇒ **A1 的正确落点是「序列的产生处」**，而不是「聚合值的消费处」。
本预注册只改前者；审计脚本**明确不做**（见 §五 禁止项）。

---

## 三、改造 A1：口径（事前固定）

### 3.1 新增纯函数 `validation/multiple_testing.py::deflated_family`

单一入口，供生产脚本调用；内部才去调 DSR / PSR / MinTRL。

```python
deflated_family(series_by_factor: Dict[str, Sequence[Any]],
                alpha: float = 0.05) -> Dict[str, Any]
```

| 编号 | 口径 | 理由 |
|---|---|---|
| C1 | 喂给函数的「returns」= **该因子逐期 IC 序列**；得到的 `sr` 即 **ICIR**（单期、**不年化**） | 模块 docstring 明确要求单期口径；年化会放大 √252 并使判定失真 |
| C2 | `n_trials` = 族内**有效假设数** = 通过 `sharpe_moments`（≥4 个观测且 sd>0）的试验数 | 无法计算矩的试验不构成「试过」 |
| C3 | `sr_variance` = 族内各有效试验 ICIR 的**总体方差**（`pstdev²`） | 与 `expected_max_sharpe` docstring「各次试验夏普比率的方差」一致 |
| C4 | 每个试验报 `psr`（基准 0）、`dsr`（基准 `max(0, E[max SR])`）、`expected_max_sr`、`min_trl_required` / `min_trl_sufficient`（基准取 **deflated 基准**） | DSR 的意义就是「扣掉选择偏差后还剩多少把握」 |
| C5 | `n_trials < 2` 或 `sr_variance <= 0` ⇒ `expected_max_sr = 0.0` 且 `selection_bias_corrected = False`，并在 `notes` 里声明「未校正选择偏差」 | 没有离散度就没有选择偏差；不可静默当作已校正 |
| C6 | **纯加法**：不改任何已有字段的值；新字段一律新增键 | 保证与归档产物可比（见 §四 A-1） |

### 3.2 接线到 `scripts/run_fundamental_factor_study.py`

- 在 `summarize()` 之后、打印之前调用 `deflated_family({k: series[k] for k in HYPOTHESES})`；
- 每个因子的结果并入 `results[k]`（新增键，不动旧键）；
- 产物 JSON 的 `multiple_testing` 块内**新增** `deflated` 子块；
- 打印表新增 `DSR` 列。

### 3.3 必须随产物声明的局限（写进 `notes`）

| 编号 | 局限 | 方向 |
|---|---|---|
| L1 | `E[max SR]` 公式假设各次试验**独立**；本族试验同数据、同窗口、因子相关 ⇒ 用独立公式会把基准抬得**偏高** ⇒ DSR **偏保守**（安全方向，但仍是近似） | 保守 |
| L2 | `sr_variance` 只由 7 个试验估计，本身噪声大 | 近似 |
| L3 | 喂入的是 **IC 序列而非收益率序列**，`sr` 是信息比率不是夏普比率 | 口径声明 |
| L4 | `n_periods` 有限时 MinTRL 可能超过可用历史 | 由 C4 的 `sufficient` 标志体现 |

---

## 四、改造 A4：统计层阳性对照（借 `microalpha` 的方法论）

`MateoBodon/microalpha` 的做法是**植入四种已知缺陷让回测可见地失败**，
并附阳性对照（p=0.001）证明「该通过时能通过」。本项目已有的是
**代码层**反向验证；A4 把它投影到**统计层**。

全部用例：**合成数据 + 固定种子 + 确定性**，不依赖任何归档产物。

| 编号 | 类型 | 构造 | 通过条件 |
|---|---|---|---|
| S-0 | **阳性对照** | 单试验，真实 IR=0.4，n=250，正态噪声 | `psr > 0.99` 且 `dsr > 0.99` 且 `min_trl_sufficient = True`。**这条不过 ⇒ 测试环境坏了，后面全部不成立** |
| S-1 | 阴性注入 · **挑最优** | 30 个纯噪声试验（IR=0，n=250），取 ICIR 最大者 | ① 注入是**真的**：至少一个试验未校正 `p < 0.05`；② 但该最优者的 `dsr < 0.95` ⇒ 选择偏差被抓到 |
| S-2 | 阴性注入 · **样本不足** | 真实 IR=0.15，n=40 | `min_trl_required > n`（`sufficient = False`）⇒ 「太短不能下结论」被抓到 |
| S-3 | 阴性注入 · **非正态** | 与阳性对照同 mean/sd，但掺入稀有大幅负跳（负偏） | `psr` **严格小于**同参数下的正态近似概率 `Φ(sr·√(n-1))` ⇒ 高阶矩被真正计入 |

S-1 的 ① 是本项目「反向验证要验**为什么红**」纪律的落实：
若注入不真实（没有任何试验未校正显著），那条断言本身就是假的。

---

## 五、判定标准与禁止项

### 5.1 判定表

| 编号 | 判据 | 通过条件 |
|---|---|---|
| A-1 | **不改变既有口径** | 重跑脚本，`reports/v3_fundamental_factor_study.json` 的旧字段（ic_mean / ic_std / icir / t / p / p_adjusted_bh / rejected_bh / quintile / multiple_testing 旧块）与归档值**逐位相同**；`multiple_testing` 旧块 m / bh_rejected / bonferroni_rejected / fwer 不变 |
| A-2 | DSR 真的在算 | 产物含 `multiple_testing.deflated`，且对 7 个因子各有 `dsr` / `psr` / `expected_max_sr`；`expected_max_sr > 0`（族内有离散度） |
| A-3 | **接线生效**（不是只有函数存在） | AST 判据：`scripts/run_fundamental_factor_study.py` 引用并调用 `deflated_family`，且 `deflated_family` 内部调用 `deflated_sharpe_ratio` / `probabilistic_sharpe_ratio` / `minimum_track_record_length`；调用方不在 `tests/` 下 |
| A-4 | 单位测试 | `tests/test_deflated_family.py`：覆盖 C1~C5 的边界（单试验 / 零方差 / 无效序列 / 负 ICIR / alpha 取值） |
| A-5 | 阳性对照 S-0~S-3 全过 | `tests/test_statistical_positive_control.py` 4 项全绿 |
| A-6 | 反向验证 | 把 `deflated_family` 的 `n_trials` 恒置 1（= 关闭选择偏差校正）后，S-1 必须**因断言失败而红**，且失败信息里出现该用例特征串 |

### 5.2 禁止项

1. **禁止**把 DSR 当作新的显著性门槛去否定或推翻已有结论 ——
   它只作证据强度参考；已有 BH 结论不变（P013 口径：重算/校正产物只作独立证据）。
2. **禁止**改 `run_multiple_testing_audit.py`（它没有序列，接了就是造假）。
3. **禁止**年化 `sr`，禁止把 IC 序列说成「收益率」。
4. **禁止**在 `n_trials < 2` 时把 `expected_max_sr` 报成非 0
   （那等于假装校正过选择偏差）。
5. **禁止**用 `grep -v test` 这类会滤掉自己的排除式判据。

---

## 六、产物

| 产物 | 位置 |
|---|---|
| 预注册 | 本文件 |
| 判定 | `DSR_IC_FAMILY_VERDICT.md` |
| 新纯函数 | `validation/multiple_testing.py::deflated_family` |
| 新守卫测试 | `tests/test_deflated_family.py`、`tests/test_statistical_positive_control.py` |
| 重跑产物 | 写入**仓库外临时路径**，与归档值逐位比对后才决定是否更新归档文件 |

> ⚠️ `reports/` 是白名单制：若最终要更新 `reports/v3_fundamental_factor_study.json`，
> 它已入库故不需补白名单；但若新建子目录，必须先补
> `!reports/<子目录>/` 与 `!reports/<子目录>/*` 两条并跑 `gen_evidence_index.py`
> 确认份数增加（2026-10-13 踩过：不补则文件静默不入库）。

## 偏离登记

| 项目 | 预注册值 | 实际值 | 理由 | 影响 |
|---|---|---|---|---|
| `args.out` 产物路径 | 写 `reports/...` | 写 `D:/_ext_verify/...` | 刻意输出到仓库外，避免覆盖归档证据 | 无（归档证据未动） |
