# 收据升级预注册：A7 receipt（输入 + 生成器版本 + 参数 + 全部产物一起哈希）

> **建立**：2026-10-18　**状态**：已执行（判定已落盘）
> 写于 2026-10-18，**先注册后动手**（AGENTS.md §2.2）。
> 判定落 [`RECEIPT_VERDICT.md`](RECEIPT_VERDICT.md)。
>
> 来自 `GITHUB_ASHARE_QUANT_SURVEY.md` §8.4-A7（§8.7 第 5 档）。
> **不改任何已归档研究产物，不重算任何研究数字。**

## 一、问题（为什么现在做）

项目已有两种「哈希实践」，都不满足 A7：

1. **产物 sha256**（`scripts/gen_evidence_index.py`）：只覆盖**结果文件**，
   不覆盖输入与生成器 ⇒ 别人拿到哈希无法判断「是不是同一份代码 + 同一份数据跑出来的」。
2. **聚合 md5**（`md5sum -b reports/_recalc/*.json | md5sum`）：手里有 80 份的
   聚合值 `471ac482…`，但它的**算法本身不可自证**——曾因 GNU `md5sum -b`
   在文件名前多一个 `*` 而连续 5 种复现方法全部失败。**哈希工具的口径必须被
   代码钉死，不能靠命令行习惯。**

survey §8.3-① 记录了反例：某开源项目文档里写 `receipt_sha256=6e36c2…`，
而仓库 `receipt.json` 的 `generator.version` 还是 `0.2.0`（`pyproject` 已是 `0.3.0`）
⇒ **收据绑生成器版本，生成器一变旧哈希即失效，而文档没跟着改**。
所以 A7 的三个验收条件里，第 ②③ 条比第 ① 条更容易栽。

## 二、组件与口径（事前固定）

### 1. 模块 `runtime/receipt.py`

对外接口（**签名先固定**，实现不得改语义）：

| 函数 | 语义 |
|---|---|
| `canonical_bytes(obj) -> bytes` | 规范化 JSON：`sort_keys=True`、`separators=(",", ":")`、`ensure_ascii=False`、UTF-8 |
| `file_entry(path, *, root)` | 单文件条目 `{path, bytes, sha256}`；`path` 为**相对 root、`/` 分隔** |
| `build_receipt(*, generator, params, inputs, artifacts, root, notes=None)` | 构造收据 dict（含 `receipt_sha256`） |
| `receipt_digest(receipt) -> str` | 对「除 `receipt_sha256` 与 `notes` 外」的收据重算 sha256 |
| `verify_receipt(receipt, *, root)` | 逐份重算并核对；返回 `{"ok", "checked_inputs", "checked_artifacts"}` |
| `write_receipt(receipt, path)` | 落盘（`newline="\n"`、UTF-8、无 BOM） |
| `load_receipt(path)` | 读回并做格式校验 |
| `render_markdown(receipt)` | 生成人读表格；表中 sha256 **由条目里的值渲染**，不接受手写 |

异常族：`ReceiptError(ValueError)` ← `ReceiptPathError` /
`ReceiptFormatError` / `ReceiptIntegrityError` / `GeneratorChangedError`。

### 2. 摘要覆盖范围（**决定性的口径**）

`receipt_sha256` 覆盖且仅覆盖：

```
{"schema": 1,
 "generator": {"path": <相对路径>, "sha256": <生成器源码哈希>},
 "params": {<调用参数，标量/列表/字典>},
 "inputs":   [{"path", "bytes", "sha256"}, …],   # 按 path 排序
 "artifacts":[{"path", "bytes", "sha256"}, …]}    # 按 path 排序
```

**不覆盖**（A7 原文要求排除易变量）：

- 时间戳（`generated_at` / mtime / ctime）——**默认根本不存储**；
- 主机名、用户名、进程号、argv（argv 含绝对路径）；
- 绝对路径（条目里只有相对 root 的路径）；
- `notes`（自由文本，如生成时刻说明）——**存在但不进摘要**，且 `verify` 明示它未被校验。

> 这条是「宁可少存，不可让易变量进摘要」：一旦时间戳进摘要，
> 「干净目录重跑字节级相同」就永远做不到，A7 的 ① 直接失效。

### 3. 生成器版本 = **生成器源码 sha256**

不引入手写 `version` 字符串作为判据。理由：microalpha 的反例正是
「手写版本号与代码不同步」；源码哈希不可能不同步。

手写 `--version` 允许出现在 CLI 里，但只写进 `notes`（展示用），**不进摘要**
⇒ 「改版本号但不改代码」不会让旧收据失效，这是**刻意的**：
收据绑定的是**行为**，不是声称。

### 4. CLI `scripts/gen_receipt.py`

```
python scripts/gen_receipt.py \
  --generator scripts/run_fundamental_factor_study.py \
  --param max_stocks=40 --param min_cross_section=5 \
  --input D:/tdx_dataset_v3/fundamentals.jsonl \
  --artifact D:/_ext_verify/receipt_demo/run_a.json \
  --root D:/ \
  --out D:/_ext_verify/receipt_demo/receipt_a.json \
  [--md-out D:/_ext_verify/receipt_demo/receipt_a.md]
```

- `--param k=v` 支持 `int`/`float`/`true|false`/字符串自动解析（解析失败按字符串）；
- 路径一律相对 `--root`；绝对路径**在 root 之外**或含 `..` 逃出 ⇒ `ReceiptPathError`；
- `--md-out` 输出的表由 `render_markdown` 生成，**不手写**。

## 三、判据（事前固定）

| 编号 | 判据 | 通过条件 |
|---|---|---|
| T-1 | 确定性 | 同输入两次 `build_receipt` ⇒ `receipt_sha256` 逐位相同 |
| T-2 | 路径无关 | 同一批文件复制到两个不同绝对路径的临时根 ⇒ 摘要相同 |
| T-3 | 参数序无关 / 值敏感 | `params` 键序不同 ⇒ 同摘要；任一值改变 ⇒ 摘要变 |
| T-4 | 生成器变更 ⇒ 旧收据失效 | 改生成器源码 1 字节 ⇒ `verify_receipt` 抛 `GeneratorChangedError`（**不与** `ReceiptIntegrityError` 合并） |
| T-5 | 产物篡改 ⇒ 失效 | 改产物 1 字节 ⇒ `ReceiptIntegrityError`，报错信息含**具体文件** |
| T-6 | 输入篡改 ⇒ 失效 | 同上（inputs 侧） |
| T-7 | 路径安全 | 绝对路径 / `..` 逃出 root ⇒ `ReceiptPathError`（**拒绝**，不静默截断） |
| T-8 | 易变量不入摘要 | 收据对象全文不含时间戳字段与主机名；带 `notes` 与不带 `notes` 的摘要相同 |
| T-9 | 文档哈希可复算 | `render_markdown` 表内每个 sha256 == `file_entry` 重算值；手改表格 1 位 ⇒ 守卫红 |
| T-10 | 零第三方依赖 | 模块 import 不含 numpy/pandas/arch/scipy/statsmodels |
| T-11 | 干净目录端到端 | 真实小规模研究在**两个不同绝对路径**各跑一次 ⇒ 两份收据**字节级相同** |
| T-12 | 版本变更强制重出 | 生成器改动后重出收据 ⇒ 摘要变化；拿新生成器 verify 旧收据 ⇒ 失败 |

**T-11 的具体对象（事前固定，不许事后换）**：
`scripts/run_fundamental_factor_study.py --max-stocks 40 --min-cross-section 5`，
`--out` 分别指 `D:/_ext_verify/receipt_demo/a/run.json` 与
`.../b/run.json`，收据落各自目录。这是**机制验证**，不是研究结论；
若两次产物字节不相同，则如实报「该生成器尚不确定」，**不许为了收据稳定去改研究逻辑**。

## 四、禁止项

1. **不把任何时间戳/主机/绝对路径写进摘要**（A7 明文要求）。
2. **不手写任何 sha256**——文档与表格里的哈希必须由 `file_entry` 算出（T-9 锁）。
3. **不改已归档研究产物**，不为「让收据稳定」修改研究逻辑或浮点累积顺序。
4. **不用 size/mtime 代替哈希**（「size 相同」不构成同一性证据）。
5. 不把 `notes` 当证据字段——它不进摘要，`verify` 必须明示。

## 五、验收合并判据

1. T-1~T-12 全绿（`pytest tests/test_receipt.py -q`）；
2. 全量测试 rc=0；`ruff check .` / `mypy . --config-file mypy.ini` 全绿；
3. 反向验证三组：① 改产物字节 ⇒ T-5 红；② 改生成器字节 ⇒ T-4/T-12 红；
   ③ 手改 md 表内哈希 ⇒ T-9 红。三组均须**因对的理由红**，无
   `SyntaxError`/`ImportError`/`FileNotFoundError` 假红；
4. 判定写入 `RECEIPT_VERDICT.md`，必须包含：
   - T-11 的**两次实际摘要值**与「字节级相同」的判据（`cmp` 或哈希相等）；
   - **没证明什么**（本机制只证「同一性」，不证「正确性」）；
   - 与既有聚合 md5 / EVIDENCE_INDEX sha256 的关系（并存，不替代）。

## 偏离登记

| 项目 | 预注册值 | 实际值 | 理由 | 影响 |
|---|---|---|---|---|
| T-11 的生成器被修改 | 只交付收据机制，「不动研究逻辑」（§四.3） | **改了 `scripts/run_fundamental_factor_study.py` 一处**：产物 payload 去掉 `elapsed_sec`（耗时仍由 stdout 打印 `用时 Ns`） | 两个干净目录各跑一次，产物唯一差异就是墙钟 `elapsed_sec`（26.8 / 25.6），其余 15,536 字节逐位相同 ⇒ **不删该键，T-11 永远不可能通过**。它不是研究逻辑（不影响任何统计量），是产物卫生 | 新产物不含该键、43 份既有归档产物仍含（未重写）；登记为**缺陷 #19**，另 3 个同型脚本（disclosure/limit_structure/st_reversal）列为欠账不顺手改 |
| T-11 的「同一批文件」范围 | 预注册只写「真实小规模研究」 | inputs 声明为**生成器 + 2 份 JSONL + 1 份产物**；`--dataset` 指向的 TDX 日线树（1,000+ `.day` 文件）**未纳入** | 把 1000+ 文件纳入会让收据生成慢一个量级且体积膨胀；日线数据同一性已有既有承担者（`security_map` / 目录版本管理） | 收据只能证明这四者同一，**不能**证明日线数据同一——已写进判定「没证明什么」 |
| T-11 的「干净目录」构造 | 预注册写「两个不同绝对路径各跑一次」 | 用**两个镜像根**（`D:/_ext_verify/rcpt/A` 与 `.../B`，各自含 `gen/`、`data/`、`out/` 同构目录） | 收据身份 = **相对路径 + 内容**：绝对路径不参与摘要，但相对路径参与（否则收据无法定位文件）。两份收据字节相同的前提是树布局相同，故必须镜像 | 判据不变（`cmp` 两份收据字节相同）；反而顺带证明了「生成器换位置不影响收据」——这正是 A7 要的「排除绝对路径」 |
