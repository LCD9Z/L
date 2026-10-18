# 收据升级判定：A7 receipt（输入 + 生成器 + 参数 + 全部产物一起哈希）

> 预注册：[`RECEIPT_PREREG.md`](RECEIPT_PREREG.md)（2026-10-18 先注册后动手）。
> 对应 `GITHUB_ASHARE_QUANT_SURVEY.md` §8.4-A7（§8.7 第 5 档，也是 §8.7 最后一项）。
> **不改任何已归档研究数字。**

## 一、执行总览

| 交付 | 内容 | 一句话结论 |
|---|---|---|
| `runtime/receipt.py` | `canonical_bytes` / `build_receipt` / `receipt_digest` / `verify_receipt` / `render_markdown` + 5 个异常类 | 摘要覆盖**生成器源码 + 参数 + 输入 + 产物**；时间戳/主机/绝对路径**不进摘要**（也不存储） |
| `scripts/gen_receipt.py` | CLI：`--generator/--param/--input/--artifact/--root/--out/--md-out/--verify` | 路径必须落在 root 内，越界即报错（不静默截断）；md 表哈希由产物算出 |
| `tests/test_receipt.py` | 18 项（T-1~T-12） | 三组反向验证「因对的理由红」，其中一组首轮**抓的是真 bug**（见 §四） |
| 真实双跑 | `run_fundamental_factor_study.py` 在**两个镜像根**各跑一次 | 两份收据 **`receipt_sha256 = b5dcccef…`，字节级相同** |

## 二、判据结果

| 编号 | 判据 | 结果 | 证据 |
|---|---|---|---|
| T-1 | 确定性 | ✅ | 同输入两次 `build_receipt` ⇒ 摘要逐位相同 |
| T-2 | 路径无关 | ✅ | 同内容放 `alpha_root/` 与 `beta_root_deeper/` ⇒ 摘要相同；条目里无绝对路径、无根目录名 |
| T-3 | 参数序无关 / 值敏感 | ✅ | `{a,b}` 与 `{b,a}` 同摘要；`b:2→3` 摘要变 |
| T-4 | 生成器变更 ⇒ 旧收据失效 | ✅ | 改生成器 1 字节 ⇒ `GeneratorChangedError`；断言**不是** `ReceiptIntegrityError`（两类问题不合并） |
| T-5 | 产物篡改 ⇒ 失效 | ✅ | 真跑：改 `out/run.json` 1 字节 ⇒ `ReceiptIntegrityError`「artifacts: out/run.json」 |
| T-6 | 输入篡改 ⇒ 失效 | ✅ | 同上（`in/data.txt`）；另测「参数被改而收据未重出」⇒ 摘要自洽性检查抓到 |
| T-7 | 路径安全 | ✅ | root 外绝对路径 / `..` 越界 ⇒ `ReceiptPathError`；root **内部**的 `..` 正常放行 |
| T-8 | 易变量不入摘要 | ✅ | 带/不带 `notes` 摘要相同；收据全文无 `generated_at`/`hostname`/`mtime`/`argv` 等键 |
| T-9 | 文档哈希可复算 | ✅ | md 表每个 sha256 == `file_entry` 重算值；手改 1 位即在重算中暴露 |
| T-10 | 零第三方依赖 | ✅ | 模块只用 `hashlib/json/os/pathlib` |
| T-11 | 干净目录端到端 | ✅ | 见 §三 |
| T-12 | 版本变更强制重出 | ✅ | 改生成器后重出 ⇒ 摘要变；新生成器 verify 旧收据 ⇒ 失败 |

补充判据（写进守卫）：`canonical_bytes` 键序稳定且分隔符写死
（`{"a":[2,3],"b":1}`）——项目历史上正是栽在「分隔符差一个空格」上；
摘要不自我指涉（改 `receipt_sha256` 字段本身不改重算值）。

## 三、T-11 真实双跑（判定的核心证据）

两个**镜像根**（收据身份 = 相对路径 + 内容，故布局必须同构）：

```
D:/_ext_verify/rcpt/A/   gen/  data/  out/
D:/_ext_verify/rcpt/B/   gen/  data/  out/     # 不同绝对路径、不同磁盘深度
```

每根内跑一次：
`python gen/run_fundamental_factor_study.py --fundamentals data/fundamentals.jsonl
--disclosures data/disclosure_dates.jsonl --max-stocks 40 --min-cross-section 5
--out out/run.json`（`--dataset` 仍指真实 `D:/tdx_dataset_v3`，见 §六.2 覆盖缺口）

收据（`--root . --verify`）：

| 字段 | 值（A 与 B **完全相同**） |
|---|---|
| `receipt_sha256` | `b5dcccef542bc1c710d271f48ed6760a7032a33ad3f3df450fedf5a40444eb52` |
| 生成器 | `gen/run_fundamental_factor_study.py`，sha256 `3fb06708730f23faee637018b0733fdeb0d7d0ba3f538550df3a664c307890d4` |
| 输入 · fundamentals | 120,861,920 B，sha256 `d5353a81d975210ae9a5dea591cb063125440dc121ccce52700329855e21915c` |
| 输入 · disclosures | 23,341,560 B，sha256 `61f241855089275d9f5e1880d9cd932017d7ab5425d53f2e04134a686c4c5fec` |
| 产物 · out/run.json | 15,514 B，sha256 `67a4cc83b9f165c798fd139cf670122f54c44d0b…`（见注） |
| 参数 | `{"control":"log_amount_20","horizon":5,"max_stocks":40,"min_cross_section":5,"step":5}` |

判据：`cmp -s A/receipt.json B/receipt.json` ⇒ **IDENTICAL**；人读表
`A/receipt.md` 与 `B/receipt.md` 亦 **IDENTICAL**；产物 `A/out/run.json` 与
`B/out/run.json` 亦 **IDENTICAL**（第一次跑**不是**这样，见 §四）。

> 注：产物 sha256 与完整值见 `D:/_ext_verify/rcpt/A/receipt.json`（不入 git）。
> 该目录属于**机制验证的现场**，不是研究产物，不归档进 `reports/`。

## 四、收据抓到的第一个真问题（缺陷 #19）

**第一次双跑，产物字节不同**：两份 15,536 B，唯一差异是
`"elapsed_sec": 26.8` vs `25.6` —— 其余全部逐位相同。

这不是收据的毛病，是**生成器把墙钟写进了产物**：只要它还在，A7 的
「干净目录重跑字节级相同」就永远不可能成立。处置：

- `scripts/run_fundamental_factor_study.py` 产物 payload 去掉 `elapsed_sec`
  （耗时仍由 stdout 打印 `用时 Ns`，诊断信息不需要进产物）；
- **研究数字零变化**：删的是元数据键，不参与任何统计量；重跑后产物
  其余字段与首跑逐位一致（15,536 → 15,514 B 的差额就是该键）；
- 守卫 `tests/test_receipt.py::test_t11c_generator_payload_has_no_wallclock`
  锁住「T-11 生成器不得再把墙钟写回产物」；
- 另 3 个同型脚本（`run_disclosure_factor_study.py` /
  `run_limit_structure_study.py` / `run_st_reversal_study.py`）**不在本立项改**
  ——它们各有归档产物，改产物 schema 须各自验证「数字不变」，按纪律另立预注册。
  已登记 HANDOVER 缺陷 #19（1 处已修 / 3 处欠账）。

> 方法论：**A7 的价值不在于「生成一个哈希」，而在于它会逼出所有让人无法复现的东西。**
> 这条是收据第一次真正跑起来就抓到的，靠读代码是看不出来的。

## 五、反向验证（三组，均「因对的理由红」）

| 植入 | 应当红的判据 | 实测 |
|---|---|---|
| ① `verify_receipt` 里产物比对被跳过 | T-5 | ✅ rc=1，`DID NOT RAISE`，无假红 |
| ② 生成器变更检查被跳过 | T-4 | ✅ rc=1，`DID NOT RAISE`，无假红 |
| ③ `render_markdown` 输出写死的 `0`×64 假哈希 | T-9 | ✅ rc=1，报出具体文件；无假红 |

基线先绿、植入后红、还原后复绿；三组失败输出均不含
`SyntaxError` / `ImportError` / `FileNotFoundError`。
脚本 `D:/_ext_verify/reverse_verify_receipt.py`（不入 git）。

> 第一版脚本的植入③把 md 结构写坏了（反引号位置错），导致红的原因是
> 「解析不出一行」而不是「哈希不符」——**红得不对也是假红**，改对替换文本后重跑。

## 六、没证明什么（比证明了什么更重要）

1. **只证同一性，不证正确性**：收据能证明「这份产物 = 这份代码 + 这批数据 +
   这组参数跑出来的」，**不能**证明数字算对了。正确性仍靠各研究的预注册 + 判定 +
   阳性对照。
2. **覆盖缺口：TDX 日线树未纳入**。本轮 inputs 只声明了 2 份 JSONL +
   生成器 + 产物；`--dataset` 指向的 1,000+ 个 `.day` 文件**不进收据**。
   所以「日线数据换了一批」这件事，本收据**看不见**——那部分的同一性仍由
   `security_map` / 数据目录版本管理承担。这是刻意的取舍（体积与文件数），
   不是遗漏。
3. **`notes` 未校验**：它不进摘要，`verify_receipt` 返回值里显式
   `notes_verified: False`。不要把 `notes` 当证据字段。
4. **跨解释器/跨平台的字节相同未验证**：T-11 是**同一台机器、同一 Python
   3.13.12** 的两个目录。浮点 `repr` 在 Python 3.1+ 最短往返稳定，但跨版本、
   跨平台 CPU 浮点差异**没有测**。要跨机器复现须另立验证。
5. **不替代既有两种实践**：
   - `scripts/gen_evidence_index.py` 的 sha256 是**人读清单**（谁引用了谁），
     收据不提供这层信息；
   - 80 份聚合 md5 `471ac482…` 是**历史口径**，仍可用；
     但它不可自证（GNU `-b` 的 `*` 前缀那件事），而收据把口径写进了代码。
     两者**并存**，谁也不是谁的超集。

## 七、全量测试与门禁

```
命令：python -m pytest tests/ -q --basetemp=D:/_ext_verify/ptmp_rc2
HEAD：dd82811 之后的工作区（本轮改动未提交，清单见 git status）
时刻：2026-10-18 18:29:57 起（终轮 2m35s，18:32 结束）
结果：rc=0，1,728 项全部通过（上轮 1,709 + 收据守卫 18 项 + 新增 F-5 复核 1 项）
```

计数方式（可复算）：`-q` 进度点按行累加 = **1,728**，全文 `F`/`E` 计数均为 **0**。
`ruff check .` 全仓 **All checks passed**；`mypy . --config-file mypy.ini`
**401 文件无问题**（较上轮 398 + 收据模块与两个新脚本）。

> 首跑 **1 项失败**，且**不是**登记缺口——是既有守卫抓到了本轮的真实改动：
> `tests/test_dataset_fingerprint.py::test_f5_payload_keys_are_archived_plus_fingerprint`
> 报「payload 丢了归档键：`['elapsed_sec']`」。这正是 F-5 的设计意图
> （防「顺手改口径」），说明删键这件事**确实被看见了**。
> 处置：在该守卫里加**显式白名单** `RETIRED_KEYS = {"elapsed_sec"}`（带缺陷号理由），
> 断言改为「丢失的键必须 ⊆ 白名单」——删任何**别的**键仍然红；
> 另加 `test_f5_retired_keys_stay_retired` 防「顺手加回来」。
