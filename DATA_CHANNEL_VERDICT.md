# 数据通道建设判定：A8 公告日第二源 + ② 证券代码映射表 + dataset_fingerprint

> 预注册：[`DATA_CHANNEL_PREREG.md`](DATA_CHANNEL_PREREG.md)（2026-10-18 先注册后动手）。
> 本文件按该预注册的判据逐条填写。**先有判据、后跑**；每个数字都可用一条命令复算。
>
> 三项均来自 `GITHUB_ASHARE_QUANT_SURVEY.md`：A8（§8.4 外接公告日）、
> 10.3-②（Lean/MapFile 代码映射）、`DSR_IC_FAMILY_VERDICT.md` §五
> （dataset_fingerprint 建议）。
>
> ⚠️ 本立项**不产生任何 alpha 结论**，不改任何已归档研究的数字，
> 不接线 PIT 主口径。产出是三条数据通道与其自证能力。

## 一、执行总览

| 组件 | 交付物 | 一句话结论 |
|---|---|---|
| A · dataset_fingerprint | `fetch/fingerprint.py` + 因子研究产物接入 | 一次 md5 0.49s；产物从此自证「重跑 = 同一数据集」 |
| B · 证券代码映射表（②） | `pit/security_map.py` + `security_map.json` | 5,667 条；裸码 000000–000999 歧义区**必报错**；与东财 SECUCODE **零分歧** |
| C · A8 公告日第二源 | `fetch/disclosure_eastmoney.py` + `disclosure_eastmoney.jsonl` | 43 期 185,809 行；与巨潮表一致率 **99.99%**；但补缺潜力仅 **1.12%** ⇒ **不建议接线** |

另：发现并修掉**缺陷 #17**（披露表 meta 出处被覆盖），登记 `HANDOVER.md` §5.3。

## 二、组件 A：dataset_fingerprint（判据 F 组）

### 2.1 做法

`fetch/fingerprint.py`：流式分块（1 MiB）md5 + 字节数 + 行数（`wc -l` 口径，
末行无换行补 1）。缺失即缺失：可选文件记 `{"missing": True}`，必需文件抛
`FileNotFoundError`。接入 `scripts/run_fundamental_factor_study.py` 的产物
payload（新增 `dataset_fingerprint` 键，覆盖 `--fundamentals` 与
`--disclosures` 两个入参）。

### 2.2 判据结果

| 编号 | 判据 | 结果 | 复算 |
|---|---|---|---|
| F-1 | md5/bytes/lines 与独立实现一致 | ✅ | `pytest tests/test_dataset_fingerprint.py -k f1`（4 项）；真实文件另对 `wc -l`/`ls -la` |
| F-2 | 内容变更可检出 | ✅ | `-k f2`（2 项：改字节 / 加行） |
| F-3 | 缺失不补造 | ✅ | `-k f3`（2 项） |
| F-4 | 确定性、字段集固定 | ✅ | `-k f4` + 批量接口测试 |
| F-5 | **只增键** | ✅ | 静态（AST 提取 payload 键 vs 归档 18 键）+ **动态**：小规模实跑 `--max-stocks 40 --min-cross-section 5`，新键集 − 归档键集 = `{dataset_fingerprint}`，归档键集 − 新键集 = ∅ |

### 2.3 真实数据集的指纹（复算命令见下）

```
fundamentals:      md5=3b67037f0492ac93e018728c9e20864c  120,861,920 B  331,432 行
disclosure_dates:  md5=1a0cbd38495536dd311b160e32375ae5   23,341,560 B  176,830 行
```

```bash
python -c "from fetch.fingerprint import fingerprint_datasets as f; \
import json; print(json.dumps(f({'fundamentals':'D:/tdx_dataset_v3/fundamentals.jsonl',\
'disclosure_dates':'D:/tdx_dataset_v3/disclosure_dates.jsonl'}), indent=1))"
```

⇒ 2026-09 那次「归档 176,841 → 重跑 176,830」的漂移，今后从产物 md5 **一眼可辨**。

### 2.4 反向验证

植入「`fingerprint_file` 恒返回同一 md5」：F-2 两测红（AssertionError，无假红信号），
还原后复绿。脚本 `D:/_ext_verify/reverse_verify_data_channel.py`。

## 三、组件 B：证券代码映射表（②，判据 M 组）

### 3.1 做法

`pit/security_map.py`：`(market, code) → {listed, delisted, successor, name}`。
`scripts/build_security_map.py` 从 `stocks/*.metadata.json`（5,667 个）建表，
落 `D:/tdx_dataset_v3/security_map.json`（+ meta 含指纹）。

**规则是扫出来的，不是拍脑袋的**：全库代码段扫描发现两段「单票段」——
`302132` 中航成飞（SZ）、`689009` 九号公司（SH 科创板 CDR）。若只写常识段，
这两条会被误判为未知市场。

### 3.2 判据结果

| 编号 | 判据 | 结果 | 复算 |
|---|---|---|---|
| M-1 | **阳性对照 000905** | ✅ | `resolve("000905")` 抛 `AmbiguousCodeError`（信息含 sh/sz 两个命名空间 + 「不静默取一个」）；`resolve("000001")` 同样抛；`get()` 返回 None。`pytest -k m1` |
| M-2 | 显式市场可解析 | ✅ | `resolve("000905","sz")` → 厦门港务，`listed=1999-04-29` |
| M-3 | 非歧义区裸码可解析 | ✅ | `600000→sh`、`300001→sz`、`920000→bj`、`302132→sz`、`689009→sh` |
| M-4 | 未知/传错市场可区分 | ✅ | `UnknownCodeError` / `MarketMismatchError` / `UnknownMarketError` 三类；未知段条目**在表内**（market 空）且进异常计数，不静默丢弃 |
| M-5 | secid 双格式 | ✅ | 东财 `1.600000`/`0.000001`/BJ `0.430047`（沿用 `fetch.common.normalize_code` 口径）；baostock `sh.600000`/`sz.000001`/`bj.430047`；市场传错即抛 |
| M-6 | 市场交叉校验 | ✅ | 对东财 `SECUCODE`：比对 5,830 码，**一致 5,428（93.10%），分歧 0**；402 个「映射表缺失」经查全部是 B 股（200/900）、新三板老代码（43/83，东财 SECUCODE 已带 920 新码）、新上市（001xxx）——**无一是 A 股主板冲突** |
| M-7 | delisted 自检 | ✅ | 全量 5,667 条：`active_ok 5,416` / `match 239` / `stale_but_active 12`。**12 条全部是停牌中**（其中 6 条被 `pit_event_master.VERIFIED_EVENTS` 直接解释，另 6 条不在该窄样本内）；矛盾只登记不改 |
| M-8 | 确定性 | ✅ | 同 fixture 构建两次逐位相同 |

### 3.3 真实建表结果

```
映射表 5,667 条：sh 2,380 · sz 3,006 · bj 281
successor_known_count = 0（预期 0 —— 无本地来源，不硬凑）
security_map.json：798,615 B / md5=f60dad3680ecbd3b246808160533cfbb（末次构建）
```

**successor 为什么是 0**：数据集里没有可靠来源。实测两个易误判实例：
`002190` 成飞集成与 `302132` 中航成飞**是两家不同公司**（同属成飞集团系），
行情区间重叠**不构成** successor 证据；`300114` 中航电测（→换码 302132）
**不在数据集内**，无从观测。猜错一条映射比没有映射更危险。

### 3.4 反向验证

植入「歧义区静默返回 SZ 条目」：M-1 两测红（`DID NOT RAISE`），还原复绿。

## 四、组件 C：A8 东财预约披露第二源（判据 D 组）

### 4.1 做法

`fetch/disclosure_eastmoney.py`：**直连**东财数据中心
`RPT_PUBLIC_BS_APPOIN`（akshare 未安装，不引入依赖；akshare 侧对应函数
`stock_yysj_em`，对照记录在模块 docstring）。`scripts/fetch_disclosure_eastmoney.py`
分三批抓取（本机 5 分钟前台上限的教训），按期追加、可恢复。

**抓取结果**：2016Q1–2026Q3 共 **43 期、185,809 行、0 期失败**
（`2026-09-30` 为在抓期，`actual_publish` 正确留空、`is_publish="0"`）。
表指纹：`md5=141da286962d3e8c5fb4dd45e7836495`，64,559,712 B。

### 4.2 判据结果

| 编号 | 判据 | 结果 | 复算 |
|---|---|---|---|
| D-1 | 结构与解析 | ✅ | `pytest tests/test_disclosure_eastmoney.py`（18 项：字段映射/补零/市场取自 SECUCODE/分页/坏 JSON/无响应/schema 异常全部抛错；`"NaT"` 等垃圾日期归空） |
| D-2 | 抽样 100 条公告日 ≥ 报告期 | ✅ | 0 条早于报告期 |
| D-3 | 滞后分布合理 | ✅ | n=176,764：min=2 · p25=28 · **中位 31** · p75=62 · p90=114 · max=257 天；零滞后 0、负滞后 0、**非全 0** |
| D-4 | 双源交叉 ≥ 95% | ✅ | `first_scheduled↔FIRST_APPOINT_DATE`：一致 **176,762/176,764 = 99.9989%**（冲突 2）；`actual_disclose↔ACTUAL_PUBLISH_DATE`：一致 **176,757/176,764 = 99.9960%**（冲突 7）。冲突均为 1–2 天差异（如 `000995 2019Q1`：巨潮 04-26 vs 东财 04-27），逐条列于 `disclosure_crosscheck.json`；仅巨潮有 66 键（0.04%，薄摊各期）、仅东财有 9,045 键（含 2026Q3 在抓期 5,581） |
| D-5 | 补缺潜力（只量化） | ✅ | 池内 203,211 条；现走法定兜底 **26,100（12.84%）**——与归档研究的 26,093（12.84%）只差 7 条，正是已知的 176,841→176,830 漂移；其中东财表有日期的仅 **292（1.12%）** |
| D-6 | PIT 主口径未动 | ✅ | `resolve_availability`/`load_disclosures` 零改动（`pytest -k d6` 两条断言 + `git diff` 为空）；冲突两列并存 |
| D-7 | 出处真实 | ✅ | 新表 meta 写明端点/字段/fetched_at/行数/指纹；**缺陷 #17** 登记并修复（见 §六） |

### 4.3 关键结论：第二源**不值得接线**

D-4 证明巨潮表本身很硬（99.99% 一致率）——这是 A8 最大的收获：
**首选依据获得了独立验证**。但 D-5 同时证明：12.8% 的法定兜底缺口
**不是换个源能补的**（只有 1.12% 可补）——缺口在两个源都缺的那些
`(code, period)` 上（早年覆盖不足）。⇒ 「接线换首选依据」的预期收益
接近于零，而口径变更成本（重跑全部有框研究）不为零。
**建议：不接线，维持巨潮首选；东财表留作独立证据与市场校验源。**

### 4.4 反向验证

植入「空 `actual_publish` 冒充合法日期」：D-1 两测红（AssertionError），还原复绿。

## 五、全量测试与门禁

**最终轮（本判定依据）**：

```
命令：python -m pytest tests/ -q --basetemp=D:/_ext_verify/ptmp_dc3
HEAD：8fa8402（工作区含本轮未提交改动，清单见 git status）
时刻：16:16 起，2m13s
结果：rc=0，1,661 项全部通过
      （进度点 23×72+5 与 `pytest --co` 收集数 1,661 一致；输出落盘
       D:/_ext_verify/full_suite_final.txt）
```

另跑：`ruff check .`（全仓 **All checks passed**）、
`mypy . --config-file mypy.ini`（**393 文件无问题**）。

**16:06 首跑 6 项失败，全部是本轮新产出与既有守卫之间的登记缺口
（非代码缺陷），逐条处置后复跑全绿**：

| 失败项 | 原因 | 处置 |
|---|---|---|
| `test_package_layout::test_package_contains_expected_modules[fetch]` | `PACKAGES` 预期清单未列新模块 | 补 `fingerprint`/`disclosure_eastmoney` |
| 同上 `[pit]` | 同上 | 补 `security_map` |
| `test_package_layout::test_no_bare_import_of_package_names` | 新测试文件 `tests/test_disclosure_eastmoney.py` 用了 `import fetch.disclosure_eastmoney as de`（守卫禁裸 import 本项目包名，仓库惯例是 `from fetch import x`） | 改导入形态 |
| `test_layout_doc_in_sync` | `DIRECTORY_LAYOUT.md` 未反映三个新模块 | 重跑 `scripts/gen_layout_doc.py` |
| `test_doc_layout::test_md_relative_links_resolve` | 首跑时判定/预注册文稿与产物处于半成品状态 | 补齐后通过；复跑两次均绿 |
| `test_experiment_status::test_executed_prereegs_have_artifacts` | 同上 | 同上 |

> ⚠️ 本轮另清掉**今早前两个立项留下的门禁欠账**：ruff 10 项（未用导入 /
> 未用解包变量 / 无占位符 f-string）、mypy 18 项（Optional 索引 / 容器标注 /
> loader None 检查）——那两个提交显然没跑仓库级 ruff/mypy。清理均为机械修复，
> 触碰的既有测试修后复跑全绿。其中 `cost_model.py:87` 的修法顺带消除一条
> **运行时不可达**的 `None >=` 路径（行为经探针验证逐例不变：坏 change_date
> 仍走原字典序回退）。

## 六、缺陷 #17（本轮发现并修复）

`scripts/fetch_fundamentals.py` 循环后的收尾 `_write_meta` **硬编码** yjbb 版
source/caveats，`--mode disclosure` 运行时把循环内刚写对的巨潮出处覆盖掉。
磁盘 `disclosure_dates.meta.json`（`fetched_at=2026-09-25 16:28:40`）即为受害者。

* 发现方式：A8 作用对象检查——meta 声明「akshare stock_yjbb_em」，
  但表的字段（`actual_disclose`/`first_scheduled`/`revisions`）只可能来自
  巨潮 `stock_report_disclosure`。**声明与形态不符即为出处缺陷**。
* 修复：抽 `_meta_for_mode(mode, …)` 单一来源，循环内/收尾共用；
  磁盘 meta 仅重写 `source`/`caveats` 两字段（`fetched_at`/`rows_by_period`/
  `failed` 原样，加 `meta_repaired_at`）。
* 守卫：`tests/test_fundamentals_source.py::test_meta_source_is_mode_aware`。
* 影响面：仅 provenance 元数据，不动任何研究数字；但「出处不可信」
  本身是证据链缺陷。

## 七、一次必须记账的近失（near-miss）

交叉校验脚本 D-5 首跑得到「法定兜底 **89.00%**」——与研究归档的 12.84%
差一个量级。根因：改函数签名加 `cn_disc` 参数时，**函数体仍在传 `None`**——
参数被接受却被忽略，产出似真幻数。靠「与归档产物的已知数值对账」抓出
（单看脚本输出完全「正常」）。这与项目记忆里的「静默失效族」同型：
**验证者与被验证者是同一个对象时，全绿不构成证据**；跨数字对账才是。
已修为 `resolve_availability(r, cn_disc)` 并复跑确认（26,100 / 12.84%）。

## 八、遗留与后续建议

1. **不接线**（§4.3）：东财表留作独立证据；若未来要接线，须另立预注册
   （会改 `availability_basis_counts` 口径），且先回答「补 1.12% 值不值」。
2. `security_map.json` 在数据集目录、**不入 git**（与 `disclosure_dates.jsonl`
   同规矩）；仓库内承载构建器 + 测试 + 判定。
3. `fetch/common.py::normalize_code` 对裸码**静默取一个**（`000905`→SZ）、
   未知前缀默认沪 —— 与本立项的严格层并存。它是行情路径的在用品，
   改它须另立预注册（涉及生产引用），本轮只登记不改。
4. 2026Q3（在抓期）数据已入库，可作下次披露季结束后的回归对照。
