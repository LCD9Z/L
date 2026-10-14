# 项目长期记忆

## 本项目的「接口契约」坑（踩过 ≥2 次，务必先查）

### `tdx_native.day_reader.scan_paths()` 返回三元组顺序是 **(code, market, path)**

```python
for code, mkt, p in day_reader.scan_paths('D:/new_tdx/vipdoc'):   # ✅
```

**⚠️ 已踩两次**：
- 2026-10-12：解包顺序写成 `(market, code, path)` → 数据错
- 2026-10-13：`for mkt, code, p in ...` → `code` 实为 `'sh'`，
  筛选 `code.startswith('600')` **恒 False** → 早年股票筛选得 **0 个**（实际 1067 个）
  - **且第一次排查时误以为是 `.day` 文件格式问题**，白费一轮

**教训**：**用任何函数的返回值前，先 `print` 一次样例**确认字段顺序。
「函数名/参数名看起来像什么」≠「返回顺序是什么」。

### 其他已踩过的接口/格式坑

| 项 | 坑 | 正确做法 |
|---|---|---|
| 通达信 `.day` | 32 字节/条，`<IIIIIfII`，价格 ÷100 | **首条=最早**，末条=最新（可直接 seek 读） |
| `.day` 首条日期 | 无「读首根」API，`read_day_tail` 读的是**尾部** | 直接二进制读前 32 字节 |
| 腾讯 secid | 东财是 `1.600000`；**baostock 是 `sh.600000`** | 两库格式不同，勿互抄 |
| 腾讯 volume | **分板块**：`sh688`=股，其余=手（须 ×100） | 见 `AGENTS.md` |
| baostock volume | 与通达信**逐位相同**（都是股） | 不需换算 |
| JSON 落盘 | `open(p,'w')` 在 Windows 会转 **CRLF** → `test_line_endings_are_lf` 失败 | 必须 `newline='\n'` |
| baostock 2000 | 是「**一页**」不是上限；`next()` 失败会**静默返回 False** | 判据 `n % 2000 == 0` ⇒ 须复核 |

## 本项目的「静默失效」坑

### `reports/` 是**白名单制**：新建子目录不补白名单 → 文件**永远不入库**

`.gitignore` 结构是 `reports/*` + 逐条 `!reports/<子目录>/` 白名单。
**新建 `reports/<新子目录>/` 时，若不补
`!reports/<新子目录>/` 与 `!reports/<新子目录>/*`，
该目录下所有 JSON/MD 会被静默忽略 —— 从未 `git add`、也不在 `EVIDENCE_INDEX.md`。**

**⚠️ 2026-10-13 踩到**：`reports/xsource/XSRC.json`（**P0-1 正式结论**）
因此**从未入库**；而 `tests/test_data_asset_registry.py` 只从**磁盘**读该文件
→ **测试全部通过**，完全发现不了「文件根本没进版本库」。
`EVIDENCE_INDEX.md` 由 `git ls-files` 生成，校验用例又比对「索引 vs git」——
两者**一致地缺失**，反而无告警。**这就是静默失效的典型形态。**

**教训**：
- 新建 `reports/` 子目录后，**必须**补两条白名单，
  并跑 `gen_evidence_index.py` 确认**证据份数增加**
- **「读磁盘能通过」≠「文件入库」**：判定类产物的守卫必须查 `git ls-files`
  （已加 `test_official_verdict_artifacts_are_git_tracked`）

## 「跨侧断言须在对象所在侧执行」——**对预注册同样适用**（2026-10-14）

**教训**：一份写得再细的预注册，只要**事实基取自「非执行侧」**，
就会在治疗执行的那一刻**全部失效**（行号、参数、引证文件都对不上）。

实例（P011 / P005 §3.3 预注册）：
| 事实基 | 副本（撰写侧） | **主干（治疗执行侧）** |
|---|---|---|
| 根因行号 | `run_five_factor_ab.py:252` | **`:310`** |
| `run_tdx_rolling_eval.py` | 有 `--ew-benchmark`（现算机制） | **无此参数**（同形隐式兜底） |
| 引证 JSON | `five_factor_ab_v2.json` 存在 | **不存在** |
| `git ls-files reports/*.json` | 58 | **82** |
| `.gitignore` 白名单 | `28-30` | **`34-52`**（逐子目录） |

→ **后果**：预注册判「治疗范围 = 1 个脚本」，**实为 2 个**
（主干 `run_tdx_rolling_eval.py:128` 与 five_ab 同形根因）。

**做法**：
- 预注册里凡引用**代码行号 / 参数名 / 产物文件 / 计数**，
  必须标**侧别**（〔主干〕/〔副本〕/〔两侧同〕）并附**该侧**命令+输出+HEAD
- 治疗执行方 ≠ 事实采集方时，**执行方必须自行复测并回执差异**，
  不得默认「来件数字可直接用于本侧」
- 两份同名脚本**内容可能不同**（冲突文件）→ 用 `git hash-object` 比对，别按名字假设一致
