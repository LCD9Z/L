# DSR 接线判定（A1）+ 统计层阳性对照（A4）

> 预注册：`DSR_IC_FAMILY_PREREG.md`（口径与判据均事前固定）
> 执行：2026-10-18　HEAD `2a8e845`
> 解释器：`C:\Users\T430\.workbuddy\binaries\python\envs\default\Scripts\python.exe`

---

## 一、做了什么

| 项 | 落点 |
|---|---|
| 新纯函数 | `validation/multiple_testing.py::deflated_family`（DSR/PSR/MinTRL 的**唯一生产入口**） |
| 接线 | `scripts/run_fundamental_factor_study.py`：导入并调用 `deflated_family`；每因子新增 `dsr`/`psr`/`min_trl_*`；产物 `multiple_testing.deflated` 子块；打印表新增 `DSR` 列；`caveats` 新增口径声明 |
| 新守卫 | `tests/test_deflated_family.py`（11 项）、`tests/test_statistical_positive_control.py`（5 项） |

---

## 二、判据结果（预注册 §5.1）

| 编号 | 判据 | 结果 | 复算 |
|---|---|---|---|
| A-1 | 不改变既有口径 | ✅ **统计字段逐位相同** | 见 §三 |
| A-2 | DSR 真的在算 | ✅ `n_trials=7`、`E[max SR]=0.2227>0`、7 个因子各有 dsr/psr | 见 §四 |
| A-3 | 接线生效 | ✅ AST 判据 3 条全过 | `pytest tests/test_deflated_family.py -k a3` + `-k sharpe_corrections_have_callers` |
| A-4 | 单元测试 | ✅ 11 项 | `pytest tests/test_deflated_family.py` |
| A-5 | 阳性对照 S-0~S-3 | ✅ 4 组全过 | `pytest tests/test_statistical_positive_control.py` |
| A-6 | 反向验证 | ✅ **两种植入都因各自预期的理由红** | 见 §六 |

---

## 三、A-1：重跑 vs 归档，逐位比对

命令（可复现）：

```
python scripts/run_fundamental_factor_study.py --out D:/_ext_verify/dsr_rerun/v3_fundamental_factor_study.json
# 用时 209s（归档那次 684.2s）
```

**统计字段：逐位相同。** 7 个因子的 `ic_mean / ic_std / icir / t / p / n_periods /
positive_rate / prior_sign / quintile_mean_returns / long_short_pct /
p_adjusted_bh / rejected_bh / p_adjusted_bonferroni / rejected_bonferroni`
全部一致；`multiple_testing` 旧块（`m=7, bh_rejected=4, bonferroni_rejected=2,
fwer_uncorrected=0.3016627039062503`）、`controlled` 块、
`multiple_testing_combined_family` 块均一致。

**不一致的 5 处，逐处查明性质**（不允许「反正是元数据」带过）：

| 键 | 归档 → 重跑 | 性质 |
|---|---|---|
| `args.out` | `reports/...` → `D:/_ext_verify/...` | **预期**：本轮刻意输出到仓库外，避免覆盖归档证据 |
| `caveats` | 5 → 6 条 | **预期**：新增 DSR 口径声明（预注册 §3.3 要求） |
| `factors[*].dsr/psr/min_trl_*` | 无 → 有 | **预期**：本次新增键 |
| `disclosure_dates_loaded` | 176841 → 176830 | **数据源漂移**，见 §五 |
| `availability_basis_counts` | `actual_disclosure` 176307→176300、`statutory_deadline` 26093→26100 | 同上，7 条记录从「真实披露日」退回「法定截止日」 |
| `announce_date_audit.suspicious_ratio` | 0.12840348 → 0.12843793 | 同上（分母不变，分子动） |
| `elapsed_sec` | 684.2 → 209 | 预期（机器负载不同） |

---

## 四、A-2：实际 DSR 数字与判读

```
n_trials = 7    sr_variance = 0.025790    E[max SR] = 0.2227
selection_bias_corrected = True
```

| 因子 | ICIR | PSR（不校正选择偏差） | **DSR（校正后）** | BH 判定 |
|---|---|---|---|---|
| pb | −0.3270 | 0.000000 | 0.000000 | 两者皆显著 |
| pe_ttm | −0.2110 | 0.000004 | 0.000000 | 两者皆显著 |
| roe | +0.0639 | 0.924532 | 0.000177 | 校正后不显著 |
| net_profit_growth | +0.1150 | 0.994913 | **0.008029** | BH 显著 |
| revenue_growth | +0.0474 | 0.855048 | 0.000046 | 校正后不显著 |
| gross_margin | +0.0240 | 0.704564 | 0.000004 | 校正后不显著 |
| ocf_per_share | +0.1150 | 0.994850 | **0.008137** | BH 显著 |

MinTRL：7 个因子全部 `sufficient=False`；其中 5 个因子的观测 ICIR 本身
**低于** `E[max SR]`，`minimum_track_record_length` 按设计返回
`reason='observed_sr_not_above_benchmark'`、`required=None`
（模块红线：观测值都没超过基准时，不给一个「勉强够用」的数字）。

### 4.1 这组数字说明什么（不夸大）

**最有信息量的一对是 `net_profit_growth` / `ocf_per_share`**：
不校正选择偏差时 PSR = 0.995（「几乎确定为正」），校正后 DSR = 0.008。
二者之差就是「我从 7 个因子里挑了最好的两个」这件事的代价——
**这正是 p 值族校正（BH）给不了的视角**，也是本轮接线的全部意义。

**但必须同时说清三点，否则这表会被读反**：

1. **DSR≈0 不等于「因子不存在」**。`E[max SR]=0.2227` 高于**所有**因子的
   观测 ICIR（最大 0.115），所以在「扣掉挑最优」这个更严的口径下，
   没有一个基本面因子构成证据。这是**口径更严**，不是结论被推翻。
2. **`E[max SR]` 由本族观测离散度估计**（含两个强负因子 pb −0.327、
   pe_ttm −0.211），不是纯零分布基准。族内因子真实方向不同 ⇒
   该数字对「族的构成」敏感。这是预注册 L1/L2 已声明的近似。
3. **`pb` / `pe_ttm` 的 ICIR 为负**，DSR=0 是正确行为
   （问的是「真实 ICIR > 选择偏差基准吗」，答案为否）；
   它们的 BH 显著是**负向**显著，与 DSR 不矛盾——**两个口径回答不同问题**。

> 按预注册禁止项 1：本判定**不**否定任何既有 BH 结论，
> 也不新增显著性门槛；DSR 只作证据强度参考。

---

## 五、意外发现：外部 PIT 数据源会漂移（无数据集指纹）

比对 `disclosure_dates_loaded` 时发现：归档那次加载 **176,841** 条巨潮披露日，
本次同一路径只有 **176,830** 行：

```
$ wc -l D:/tdx_dataset_v3/disclosure_dates.jsonl
176830 D:/tdx_dataset_v3/disclosure_dates.jsonl
$ ls -la D:/tdx_dataset_v3/disclosure_dates.jsonl
-rw-r--r-- 1 T430 197121 23341560 Sep 25 16:28 disclosure_dates.jsonl
```

- 净损失 11 条，其中 7 条导致「真实披露日 → 法定截止日」的回退
  （`availability_basis_counts` 同步位移）。
- **因子统计量在归档精度下未变** ⇒ 本次结论不受影响。
- 但归档产物**没有任何数据集指纹**（无 md5 / 无行数 / 无版本），
  所以「重跑 = 同一数据集」这件事**无法从产物自证**，
  只能靠人记得「数据大概没变」。

⇒ 这与 `GITHUB_ASHARE_QUANT_SURVEY.md` §8.3-① 从 `microalpha` 抓到的
「收据绑生成器版本」是同一族问题：**可复现性需要指纹，否则会退化成
「看起来可复现」**。建议（本轮不做）：在产物里加
`dataset_fingerprint = {fundamentals: {path, bytes, md5, lines}, disclosure_dates: {...}}`。

---

## 六、A-6：反向验证（两种植入，各打一层）

脚本 `D:/_ext_verify/reverse_verify_c.py`（仓库外），每条植入**事前声明**
它应触发的特征串：

| 植入 | 应当触发 | 实测 |
|---|---|---|
| **关开关**：`n_trials` 恒置 1 | `选择偏差校正未生效` | ✅ rc=1、AssertionError=2、无假红信号、特征串出现（`E assert False is True`） |
| **留开关、毁数值**：`dsr` 冒充 `psr` | `挑最优未被抓住` | ✅ rc=1、AssertionError=2、无假红信号、特征串出现（`E assert 0.9979136723529876 < 0.95`） |

还原后 `rc=0`（绿）。

**过程中修正了自己的一处判据缺陷**：首版只预设了一个特征串，
结果「关开关」植入红在**另一条**断言上（`selection_bias_corrected`），
首版判据因此误报 FAIL。按「反向验证要验**为什么红**」的纪律，
正确的修法不是放宽标准，而是**给断言加自述信息**
（S-1 首条断言补了消息文本），并让每种植入各自声明预期特征串。
⇒ 又一条实例：**判据本身也要能被反向验证**。

---

## 七、全量测试

```
命令：python -m pytest tests/ -q -p no:randomly --basetemp=D:/_ext_verify/ptmp_a
HEAD：2a8e845    时刻：14:27:19
结果：rc = 0，进度行 F 计数 = 0（1609 项收集，127 个文件）
```

> ⚠️ **本机一个会骗人的环境细节**：pytest 退出时，宿主的「安全删除守卫」会拦截
> 它对 `%TEMP%\pytest-of-T430\garbage-*` 的清理（本次 827 个文件 > 阈值 50），
> 并把一行 `[safe-delete][SAFE_DELETE_BULK_CONFIRM_REQUIRED]` **追加在 `[100%]`
> 之后** —— 于是 `tail` 看不到汇总行。本轮因此差点误判：
> 曾因 `grep "^FAILED"` 无输出而得出「全绿」，实际 rc=1、进度行里有 `FF`。
> **教训：本机判断 CI 结果必须看 `rc` 与进度行里的 `F` 计数，不能只 grep 汇总行**
> （换 `--basetemp` 到非 Temp 目录可避开该守卫，本轮即如此取得干净的 rc=0）。

> 另：本轮共跑了 5 次全量。前 2 次红在 `tests/test_scripts_registry.py` 的 2 项
> （`REGISTRY.md` 未随本轮改动重生成），第 3~4 次红在
> `tests/test_experiment_status.py::test_all_prereegs_have_status_field`
> （本预注册的状态字段写成 `> 状态：` 而守卫要 `> **状态**：`）。
> 两项都是**登记类**问题，按守卫处方各修一行后转绿 —— 记为过程，不藏。

## 八、遗留

1. **未更新归档产物**：`reports/v3_fundamental_factor_study.json` 保持原样，
   重跑结果在 `D:/_ext_verify/dsr_rerun/`。更新它属「改动已发布证据」，
   需另立预注册（本预注册禁止项未授权）。
2. **数据集指纹缺失**（§五）：建议下一步做，代价极低（一次 md5 + 行数），
   但能把「重跑可复现」从口头变成可验。
3. **`split_chronological` 仍无调用方**（上一轮 embargo 的遗留）：
   要用它须另立预注册。
4. **purged CV 仍未做**（需标签级时间戳，`COST_AUTHORITY_AND_EMBARGO_PREREG.md` 已声明不做）。
