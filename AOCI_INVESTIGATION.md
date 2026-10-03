# AOCI 调研报告：能否引入本机并用于后期项目（2026-10-04）

> **触发**：用户「在 GITHUB 中检索 AOCI 看是否可以引用到这台电脑，应用到后期项目」
> **方法**：GitHub REST API 检索 + 仓库元信息/许可证/README/Releases 原文核对
> **结论**：**技术上可引入；法律上「内部使用」明确允许，「对外商用」受限；建议先小规模试点，不建议直接全量接入**

---

## 一、检索结果：AOCI 在 GitHub 上是什么

**检索**：`api.github.com/search/repositories?q=AOCI` → **148 个**仓库。

**头号结果（断层第一）**：

| 项 | 值 |
|----|----|
| 仓库 | **`aoci-spec/aoci-code`** |
| ★ / fork | **932 / 136** |
| 语言 | Go |
| 创建 / 最后推送 | 2026-08-08 / **2026-10-02**（活跃） |
| 描述 | 「A persistent, Git-versioned map of your whole codebase and database schema that coding agents read before they touch anything. **Local-first MCP server + CLI in Go**」 |
| topics | `agent-memory` `agents-md` `ai-coding` `claude-code` **`code-indexing`** `code-intelligence` `codex` `context-engineering` `cursor` **`database-schema`** **`local-first`** **`mcp-server`** `repo-map` |

**其余 147 个基本是噪声** —— Advent of Code（`AoCIntcodeCompiler`）、巴西高校课程
（`ProjetoAOCI`/`AOCI5`/`AOCII`）、无描述空仓库等。
金融语境二次检索（`AOCI + finance/accounting/quant`，228 条）**未发现**会计科目
「其他综合收益累计额」相关的可用代码库 —— **AOCI 在本轮语境下 = `aoci-code`**。

---

## 二、它做什么（中文 README 原文要点）

AOCI-CODE 是**给编码 Agent 用的「代码库认知层」**，四条能力（README §1）：

| # | 能力 | 原文 |
|:--:|------|------|
| 1.1 | **持续迭代开发** | 「Agent 始终带着 AOCI 索引提供的整体系统认知工作，**而不是每个任务都重新搜索、重读整个代码库**」 |
| 1.2 | **一键理解已有系统** | 「对 50 万行以内的现有系统，一句话让 Agent 建立整体认知……实测已支持 **70 万行**商业系统的开发，对应索引约 **300K token**」 |
| 1.3 | **换人/换 Agent/换对话，认知不丢** | 「索引随代码保存在仓库里，由 **Git 版本化**……读一次索引即可立刻接上」 |
| 1.4 | **自动维护** | 「MCP 自动发现代码变化并签发需要更新的条目，Agent 在完成开发任务时顺手补齐」 |

**工作机制**：`init`（写入宿主 MCP 配置 + 生成认知资产）→ `scan`（按 git 忽略规则取文）
→ **Agent 逐文件撰写索引条目** → `aoci ui` 起本地面板。

**产物落在项目根**：`aoci.txt` · `aoci.meta.txt` · `aoci.code.txt` · `AGENTS.md` · `.aoci/`

**隐私设计（README §2.3 原文）**：
> 「**只读你的系统，不联网，不存凭据。** ……它不访问互联网、不上传任何内容，
> 唯一会打开的连接是你声明的数据库（只取表结构）和它自己的本机回环状态页。
> 数据库凭据只通过环境变量名引用，**从不保存**。」

→ **与本项目「凭据不外泄」原则一致** ✓

---

## 三、⚠️ 许可证：决定「能否引用」的核心

**GitHub API 返回 `license: NOASSERTION`** —— 但 `LICENSE` 原文是：

> **Functional Source License, Version 1.1, MIT Future License（`FSL-1.1-MIT`）**
> Copyright 2026 **Liu JinShi**

**这是 Fair Source / source-available，不是 OSI 开源许可证。**

### 关键条款

| 条款 | 原文 | 对本项目的含义 |
|------|------|--------------|
| **Permitted Purpose** | 「any purpose **other than a Competing Use**」 | 非竞争用途都可以 |
| **明确允许**（原文列举） | ① **for your internal use and access**；② 非商业教育；③ 非商业研究；④ 向被许可方提供的专业服务 | ✅ **本机自用、内部项目使用：明确允许** |
| **Competing Use（禁止）** | 把软件**提供给他人**作为**商业产品或服务**，且：① 替代本软件；② 替代其现有产品/服务；③ 提供**相同或实质相似的功能** | ❌ **若「后期项目」是对外发布的 Agent 产品且功能相似 → 越线** |
| **Grant of Future License** | 「**自软件发布之日起满两周年**，不可撤销地额外授予按 **MIT** 使用的权利」 | ⏳ **2028-08-08 起自动转 MIT，届时无限制** |

### 判定

| 使用场景 | 判定 |
|---------|:---:|
| 装到本机、给自己/本项目用（内部开发辅助） | ✅ **允许** |
| 作为本项目（AI股神团队）的开发工具链 | ✅ **允许**（内部使用） |
| 写进对外发布的商业 Agent 产品、且提供相似功能 | ❌ **禁止**（Competing Use） |
| 2028-08-08 之后 | ✅ **MIT，无限制** |

> **建议**：若后期项目有对外商业化意图，**现在就应把「AOCI 属于 FSL 而非 MIT」写进依赖清单**，
> 并规划 2028-08-08 后的替换/转正路径。

---

## 四、技术可行性：本机（Windows AMD64）能否装

| 检查项 | 结果 |
|--------|------|
| 本机架构 | **Windows AMD64**（`Windows AMD64 10`） |
| 预编译包 | ✅ **`aoci_0.1.0-rc17_windows_amd64.zip`（9.5 MB，下载 1,012 次 —— 全平台最多）** |
| 是否需要 Go | ✅ **不需要** —— README §0：「使用已验证的 Release 二进制**本身不需要 Go 或 make**」 |
| 本机 Go 环境 | ❌ 未安装（**不影响**，走二进制路线即可） |
| 供应链校验 | ✅ 提供 `SHA256SUMS` + `SHA256SUMS.sigstore.json` + `*.sbom.json` + `RELEASE-MANIFEST.json` |
| MCP 宿主 | ✅ **标准 stdio MCP server** → WorkBuddy 支持 MCP（本会话已有 3 个连接器）→ **理论可接入** |

**⚠️ 但版本是 `v0.1.0-rc17`，`prerelease=true`，尚未 GA。**
README 自己也标注「**当前 RC**」。

**⚠️ 接入需重启 Agent** —— README 明确：「`init` 刚写入的 MCP server 在当时那个会话里还没有加载，
所以建立索引必须放在**重启之后**」。

### 4.1 ⚠️ 实测：本环境**无法可靠下载** Release 资产（重要）

我没有停在静态调研，实际尝试了下载 —— **结果是本环境不可靠**：

| 步骤 | 结果 |
|------|------|
| `api.github.com`（仓库元信息/README/LICENSE/Releases 接口） | ✅ 可用（本报告全部数据来源） |
| `github.com/aoci-spec/aoci-code/releases`（网页） | ⚠️ 间歇可用 |
| **302 重定向目标 `release-assets.githubusercontent.com`** | ❌ **不稳定** |
| 下载 `aoci_..._windows_amd64.zip`（9.5 MB） | ❌ **多次失败**（curl exit 52/56；Python `URLError: Tunnel connection failed: **502 Bad Gateway**`） |
| 下载 `SHA256SUMS`（2 KB） | ❌ 同样失败 |

**根因**：本环境经**隧道代理**出网，`release-assets.githubusercontent.com` 在隧道侧返回
**502 Bad Gateway**；同域名偶发成功（曾有一次完整收到 9,480,587 字节），说明是**间歇性**而非硬封锁。

**结论**：
- **这是本沙箱环境的限制，不是你机器的限制** —— 你用浏览器直接打开
  `https://github.com/aoci-spec/aoci-code/releases` 下载即可
- 若要在本环境接入，**需先解决 Release CDN 的可达性**（换网络 / 配代理），
  或**从源码构建**（但那样需要装 Go 工具链）
- ⚠️ **不要**因为"下载失败"就跳过 **SHA256SUMS 校验** —— 官方提供了
  `SHA256SUMS` + `SHA256SUMS.sigstore.json` + SBOM，**校验是必须步骤**

---

## 五、⚠️ 与本项目既有机制的冲突点（实测核对）

| 冲突 | 详情 | 影响 |
|------|------|:---:|
| **① 行尾守卫** | `tests/test_module_splits.py::test_line_endings_are_lf` **扫全仓 `.md`/`.txt`**；AOCI 会在根目录新增 `AGENTS.md`/`aoci.txt`/`aoci.code.txt`/`aoci.meta.txt` | **若含 CRLF → CI 直接红**（本项目已被此坑咬过 3 次） |
| **② 布局文档守卫** | `test_layout_doc_in_sync` 比对 `DIRECTORY_LAYOUT.md` 与实际树；AOCI 新增根文件 | 需重跑 `scripts/gen_layout_doc.py` |
| **③ 凭据扫描** | `credential_scan.py` 用 `ROOT.rglob("*")` 扫**全树** | 会扫 AOCI 索引文件；预计不误报，但需实测 |
| **④ 平铺副本守卫** | `test_no_flattened_copies_in_root` | ✅ **不受影响**（只查 `.py`） |
| **⑤ 文档体系重叠** | 项目已有 `DIRECTORY_LAYOUT.md`(32 KB) + `HANDOVER.md`(57 KB) + `WORKLOG.md`(78 KB) | **功能重叠**，需明确分工，否则两套认知来源会不一致 |

**规模估算**：本项目 Python **38,896 行**。按 README 比例（20 万行 ≈ 1 小时），
**首次索引约 10–15 分钟**；索引本身 token 成本按比例估算约 **15–20K token**（远低于其 300K 上限）。

---

## 六、结论与建议

### 结论

**可以引用到本机，用于本项目的内部开发** —— 法律（FSL 明确允许内部使用）与技术
（有 Windows AMD64 预编译包、无需 Go、标准 MCP）**两条路都通**。

**但有三条硬约束**：

1. **许可证是 FSL-1.1-MIT，不是 MIT** —— **内部用可以，做成对外竞品不行**（2028-08-08 后才转 MIT）
2. **当前是 RC 版本**（`v0.1.0-rc17`）—— 不宜作为唯一认知来源
3. **会新增一套需维护的产物 + 触发 3 个既有守卫** —— 需先处理

### 建议路径（由低风险到高）

| 步骤 | 内容 | 风险 |
|:--:|------|:---:|
| **1** | **先在副本仓库试点**（`1.0 - 副本`），不动原版 `1.0` | 低 |
| **2** | 下载 `windows_amd64.zip` → **校验 SHA256SUMS** → 解压到稳定绝对路径 | 低 |
| **3** | 先只跑 `init` + `scan`，**不建索引**，观察它会写哪些文件 | 低 |
| **4** | 实测 3 个守卫是否被触发；必要时补 `.gitignore` / 重生成布局文档 | 中 |
| **5** | 建索引（10–15 分钟），**与既有 `HANDOVER.md` 明确分工**（AOCI 管代码结构，HANDOVER 管口径与结论） | 中 |
| **6** | 重启 Agent 后验证 MCP 生效 | 低 |

### 明确不建议

- ❌ **不建议把 AOCI 索引作为唯一认知来源** —— 本项目的 `HANDOVER.md` 承载的是
  **口径、踩坑、假设登记**（业务语义），AOCI 承载的是**代码结构**（工程语义），**两者不可互替**
- ❌ **不建议在未核实许可证边界前，把它写进任何对外产品的依赖** —— 若后期项目要发布，
  先确认是否构成 Competing Use

---

## 七、口径声明

- 检索时间：**2026-10-04**；数据源：GitHub REST API（`/search/repositories`、`/repos/...`、
  `/readme`、`/license`、`/releases`、`/contents`）
- 许可证判定依据 **`LICENSE` 原文**（4,210 字符，`FSL-1.1-MIT`），非 GitHub 的 `NOASSERTION` 标签
- 本报告**未下载、未安装、未运行**任何 AOCI 二进制 —— 以上均为**静态调研**结论
- **本报告不构成法律意见**；对外商用前请自行确认许可条款
