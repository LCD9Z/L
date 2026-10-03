# AOCI-CODE 接入评估与操作手册

> **状态**：已下载并校验，**尚未 init / 尚未建索引**
> 引入日期：2026-10-04
> 来源：`D:\aoci_0.1.0-rc17_windows_amd64.zip`（用户下载）

---

## 一、它是什么、解决什么问题

**AOCI-CODE = AI-Oracle Continuous Intelligence（CODE）**
Oracle 牵头的开源项目，`v0.1.0-rc17`，Go 编写，MCP stdio 服务端（9 个工具）。

**它解决的问题**：给 AI Agent 建立**代码库的全局认知索引**，随代码一起存进 git，
让 Agent 换人、换工具、换对话后**不用重新通读整个代码库**。

**和本项目已有的 `AGENTS.md` 是什么关系**——这是最重要的一点：

| | `AGENTS.md`（已有） | AOCI-CODE（拟引入） |
|---|---|---|
| 解决 | 让 agent 知道**纪律与禁区** | 让 agent 掌握**代码结构与数据流** |
| 内容 | 137 行，8 个大节，全是人写的约定 | 由 agent 逐文件撰写、机器校验的索引条目 |
| 维护 | 人工维护，会过期 | 代码变更时自动签发待更新条目 |
| 回答 | "能不能做 / 不许做什么" | "这段逻辑在哪 / 数据从哪来到哪去" |

**一句话**：`AGENTS.md` 管**该不该**，AOCI 管**是什么**。两者不重叠，都需要。

### 为什么本项目值得用（不是跟风）

本项目有 268 个 `.py`、44,015 行（含 md）。2026-10-02 的独立审计里，
两路子 agent 都需要**通读大量代码**才能定位问题（`backfill.py` 的顺延态、
`screen.py` 的跨月相减都不是一眼可见）。这份成本每次会话都要重付。

---

## 二、已做的安全检查（2026-10-04）

| 检查项 | 结果 |
|--------|------|
| 二进制来源 | 官方发布包 `D:\aoci_0.1.0-rc17_windows_amd64.zip` |
| **exe SHA256 vs SBOM** | ✅ 完全一致 `4013002f...5c67`（**文件未被篡改**） |
| SBOM 内容 | 26 个 Go 依赖、Go 1.26.6，许可证均已声明 |
| `aoci doctor` 输出 | **「AI status: disabled (fully offline)」「no endpoint is configured; no source is sent anywhere」** |
| 是否执行 | ✅ 已执行 `--version` / `--help` / `doctor` 三条**只读**命令 |

**未验证的部分（诚实记录）**：
- 建索引时若配置 AI endpoint，**源码会发送给该 endpoint**。README 声称
  "只读取源码和数据库表结构，不读业务数据"，但这是项目方的声明，
  **本项目无法独立验证**。
- 因此**建议的 endpoint 是本机 WorkBuddy 通道**，不指向任何第三方服务。

### 许可
FSL-1.1（Functional Source License）。允许内部使用与修改，
但**分发/对外提供需注意条款**。本项目只自用，不分发，符合要求。

---

## 三、为什么只索引 `tdx_native/`（而非全库）

`AGENTS.md` 第八节记录的规律：**结构化过滤器会互相覆盖**。同一条规律适用在索引上。

全库 44,015 行中，md 占 13,461 行，且多为**过程记录与已作废结论**
（`AUDIT_REPORT.md`、`STEP1_3_EXECUTION_REPORT.md` 早期章节等）。
把这些编进索引，Agent 可能被历史结论误导——**这正是本项目最警惕的静默失效**。

`tdx_native/` 的理由：
- 11 个文件、1,705 行，是**每天自动运行的生产代码**
- 2026-10-02 审计发现的 4 个高危缺陷，3 个在这个目录
- 规模小（README 称 20 万行≈1 小时，1,705 行约 **2~5 分钟**）

---

## 四、操作步骤（国庆后执行）

### 步骤 1：init（会写项目根目录文件）

```bash
cd C:\Users\T430\Desktop\1.0
tools\aoci\aoci.exe init
```

产出：
| 路径 | 说明 |
|------|------|
| `aoci.txt` | 索引主体（**需 git 版本化**） |
| `aoci.meta.txt` | 元信息 |
| `.aoci/` | 治理状态、配置、Baseline |
| `AGENTS.md` | **它会追加一个 AOCI 策略块** ← 注意备份 |

⚠️ **务必先备份 `AGENTS.md`**。AOCI 会往里写内容，而那份文件是本项目
最重要的纪律文档。

### 步骤 2：scan 建立 Baseline（全离线，不调 AI）

```bash
tools\aoci\aoci.exe scan
```

### 步骤 3：限定 scope —— 只管 tdx_native/

```bash
tools\aoci\aoci.exe scope rule --help   # 先看规则语法
tools\aoci\aoci.exe scope show          # 确认当前 managed 范围
```

用 scope rule 把 `tdx_native/**` 设为受管、其余排除。
**这一步不能跳过**，否则会回到全库索引的问题。

### 步骤 4：接 MCP（重启后生效）

AOCI 需要在 WorkBuddy 的 MCP 配置里注册。推荐写入
`~/.workbuddy/mcp.json`：

```json
{
  "mcpServers": {
    "aoci": {
      "command": "C:\\Users\\T430\\Desktop\\1.0\\tools\\aoci\\aoci.exe",
      "args": ["mcp"]
    }
  }
}
```

⚠️ 写完**不会自动激活**——需在连接器管理页右上角的自定义连接器入口
点「信任」，才会在后续会话生效。

### 步骤 5：建索引

重启会话后由我调用 AOCI 的 MCP 工具逐文件撰写条目（约 2~5 分钟）。
**注意本机 5 分钟前台 SIGTERM 限制**，需分批或挂后台。

### 步骤 6：面板

```bash
tools\aoci\aoci.exe ui --detach --json
```

---

## 五、随时可查的命令

```bash
tools\aoci\aoci.exe status            # 只读，看对齐状态
tools\aoci\aoci.exe verify            # 校验（不改索引）
tools\aoci\aoci.exe index score       # 索引质量九维打分
tools\aoci\aoci.exe index inventory   # 列出未进索引的文件
tools\aoci\aoci.exe doctor            # 环境诊断（不加 --net 不联网）
tools\aoci\aoci.exe capabilities      # 机器能力清单
```

---

## 六、待决与风险

| # | 事项 | 状态 |
|---|------|------|
| 1 | **`AGENTS.md` 会被 AOCI 追加内容** | ⚠️ init 前必须备份 |
| 2 | 建索引会调 AI endpoint，源码随之发送 | 建议指向本机通道，不指第三方 |
| 3 | 索引文件需进 git（它按设计就该版本化） | 但 `.gitignore` 需放行 `aoci.txt` |
| 4 | 首次索引依赖我逐条撰写 | 非全自动，AI 通道断了就做不了 |
| 5 | **索引质量未经真实检验** | 建成后需 `index score` 验证，别默认它有用 |

> **纪律提醒**：本项目第一条是「不宣称 alpha」，第五条是「结论必须有证据」。
> 引入 AOCI 同样适用——**它装上了不等于有用**。
> 建成后必须用 `index score` 与「不用 AOCI 时能否正确理解 `tdx_native/`」
> 做一次对照，否则就是又一个「看起来在跑」的东西。

---

## 附：可参考的原始资料

- 项目地址：https://github.com/aoci-spec/aoci-code
- 本地完整文档：`tools/aoci/README.zh-CN.md`（67,381 字节，含完整命令与
  数据库索引、面板、宿主集成说明）
- 变更记录：`tools/aoci/CHANGELOG.md`（103,143 字节）
- SBOM：`D:\aoci_0.1.0-rc17_windows_amd64.zip.sbom.json`
- 源码包（未解压使用）：`D:\aoci-code-0.1.0-rc17.tar.gz`
