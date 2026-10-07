# AOCI 接入执行报告（2026-10-07）

> **前置**：`AOCI_INVESTIGATION.md`（可行性调研）
> **本次**：按调研报告的建议路径**实际执行**第 1–4 步 + 注册 MCP
> **结论**：**接入成功，零冲突** —— 既有 CI 6/6 全绿，未修改任何既有文件

---

## 一、执行清单（按调研建议的六步）

| 步 | 内容 | 状态 | 结果 |
|:--:|------|:---:|------|
| 1 | 先在**副本仓库**试点（不动原版 `1.0`） | ✅ | 在 `1.0 - 副本` 执行 |
| 2 | 下载 → **SHA256 校验** → 解压到稳定路径 | ✅ | 校验**通过**；`D:\tools\aoci\aoci.exe` |
| 3 | 只跑 `init` + `scan`，**不建索引**，观察写入 | ✅ | 新增 6 项，**未修改任何既有文件** |
| 4 | 实测既有守卫是否被触发 | ✅ | **3 个守卫全部通过**；CI **6/6 全绿** |
| 5 | 建索引（364 条目 / 13 轮） | ⏸ **未做** | **需重启 Agent 后经 MCP 工具撰写** |
| 6 | 重启后验证 MCP 生效 | ⏸ 待用户重启 | 已注册 + 冒烟测试通过 |

---

## 二、第 2 步：校验与安装

| 项 | 值 |
|----|----|
| 包 | `aoci_0.1.0-rc17_windows_amd64.zip`（9,480,587 字节） |
| **SHA256（本机实测）** | `722658c95146aae8ad63765af334cfb2afb41d7c201f68a3f381c6bb480d65a0` |
| **SHA256（官方 SHA256SUMS）** | `722658c95146aae8ad63765af334cfb2afb41d7c201f68a3f381c6bb480d65a0` |
| 校验 | ✅ **完全一致 —— 包完整未篡改** |
| 可执行文件 | `aoci.exe` **24,709,120 字节**，头部 `4d5a` = **MZ → Windows PE** ✓ |
| 版本 | `aoci version 0.1.0-rc17 (commit 93d6ad5a87fd9624a51cae61b2134d33944501fb, built 2026-09-28T19:15:07Z)` |
| **安装路径** | **`D:\tools\aoci\aoci.exe`**（稳定绝对路径） |

> ⚠️ 用户最初下载的是 `darwin_amd64`（**macOS**）包，与本机 Windows AMD64 不符；
> 后已补下正确的 `windows_amd64` 包。

---

## 三、第 3 步：`init` + `scan` 实际写入

### 3.1 `aoci init --locale zh-CN`（未带 `--agent` / `--hooks`，最小 footprint）

**新增 6 项，未修改任何既有文件**：

| 文件 | 大小 | 作用 |
|------|-----:|------|
| `aoci.txt` | 301 B | 根清单（Volume 注册表） |
| `aoci.meta.txt` | 1,989 B | **FRAS 协议 + 五维标签字典**（机器契约） |
| `aoci.code.txt` | 21 B | 代码索引卷 —— **空骨架**（不伪造条目） |
| `AGENTS.md` | 13,258 B | 宿主接入说明（**已被 IDE 注入项目上下文**） |
| `.aoci/config.json` | 5,579 B | 配置（`locale=zh-CN` · `automation.mode=auto` · **`ai.enabled=false`**） |
| `.aoci/.gitignore` | 362 B | 运行时忽略 + 正式资产白名单 |

**Scope 提案（`init` 输出）**：
`git_tracked=462` · `index=372` · `observe=91` · `exclude=171` · `safety_excluded=117`
· **`estimated_whole_index_tokens=42,720`** · `human_decisions=0`

### 3.2 `aoci scan`（建立基线）

```
基线已建立: 466 个文件, 耗时 6757ms
8 个 index 文件没有模型可读的内容、不需要 Entry(二进制 7、空文件 0、超限 1)
364 个 index 文件需要写条目：约 13 轮 Maintain（每轮最多 50 条、响应预算 24 KiB）
```

**`scan --dry-run` 关键指标**：

| 项 | 值 |
|----|----|
| `final_managed_candidates` | **521** |
| `builtin_sensitive_excluded` | **0** ✓ |
| `required_human_review` / `auto_blocker_count` | **0 / 0** ✓ |
| `authoring_estimate` | **targets 365 · rounds 13 · batch_limit 50** |

---

## 四、第 4 步：⚠️ 守卫冲突实测 —— **全部通过**

调研阶段我预判了 3 个冲突点，**实测结果全部否证**：

| 预判冲突 | 实测结果 | 原因 |
|---------|:---:|------|
| **① `test_line_endings_are_lf` 会因 CRLF 失败** | ✅ **通过** | AOCI 生成的 6 个文件**全是 LF**（Go 在 Windows 上写 `\n` 而非 `\r\n`；且 `config.json` 有 `line_ending_tolerance: true`） |
| **② `test_layout_doc_in_sync` 需重生成布局文档** | ✅ **通过** | `gen_layout_doc.py` **只扫 `*.py`**（`rglob("*.py")`），AOCI 产物全是 `.md`/`.txt`/`.json` → **天然不受影响**（我最初误以为是"未跟踪"导致，已用 `git add` 后复测否证） |
| **③ `credential_scan.py` 可能误报** | ✅ **通过** | 扫描 455 个文件（447 → 455），未发现明文凭据 |

**完整验收**：`run_ci.py` → **6/6 全绿**（syntax / ruff / mypy / compat / pytest / credentials）

---

## 五、第 5–6 步：MCP 注册与冒烟测试

### 5.1 MCP 注册

写入 `~/.workbuddy-ai/mcp.json`（此前**不存在**，本次新建）：

```json
{
  "mcpServers": {
    "aoci": {
      "command": "D:/tools/aoci/aoci.exe",
      "args": ["mcp"]
    }
  }
}
```

### 5.2 冒烟测试（stdio 握手）

```
protocolVersion: 2024-11-05
serverInfo: {'name': 'aoci-code', 'version': '0.1.0-rc17'}
capabilities: ['logging', 'tools']
```

→ **MCP server 可正常启动并完成握手** ✓

### 5.3 ⏸ 待用户操作

1. **在连接器管理页右上角的「自定义连接器」入口点「信任」** 启用新增的 aoci server
2. **重启 Agent** —— `init` 写入的 MCP server 在当前会话尚未加载（README 明确要求）
3. 重启后即可让 Agent 经 `aoci_rules` → `aoci_overview` → `aoci_maintain` 建索引
   （364 条目 / 约 13 轮，预计 10–20 分钟）

---

## 六、分工约定（避免两套认知来源冲突）

调研阶段已识别「与既有三层文档体系功能重叠」的风险。**确立分工**：

| 文档 | 管辖范围 | 不碰 |
|------|---------|------|
| **AOCI**（`aoci.txt`/`AGENTS.md`/`.aoci/`） | **代码结构**：文件职责、依赖关系、对外契约、关键约束（工程语义） | 业务口径、研究结论、假设登记 |
| `DIRECTORY_LAYOUT.md` | 包/模块的**目录布局**（由 `gen_layout_doc.py` 从 `.py` 自动生成） | 语义解释 |
| `HANDOVER.md` | **现状、约定、踩坑、待办**（业务语义） | 代码结构细节 |
| `WORKLOG.md` | **做了什么、为什么、验证结果**（append-only 日志） | — |

> **硬约束**：**不得把 AOCI 索引作为唯一认知来源** —— 它管工程语义，`HANDOVER.md` 管业务语义，**不可互替**。

---

## 七、⚠️ 遗留风险（登记在案）

| # | 风险 | 说明 |
|:--:|------|------|
| 1 | **许可证 FSL-1.1-MIT** | 内部使用允许；**做成对外商用竞品禁止**；**2028-08-08 后自动转 MIT** |
| 2 | **RC 版本**（v0.1.0-rc17） | 非 GA；不宜作为唯一认知来源 |
| 3 | **索引维护成本** | 364 条目需 Host 模型撰写；每次代码大改后需增量维护 |
| 4 | **token 预算** | 全索引预计 **42,720 token**；`config.json` 的 `cognition_budget` 上限 400,000 |
| 5 | **MCP 未启用前不可建索引** | 需用户手动「信任」+ 重启 |

---

## 八、口径声明

- 本报告所有数字均为**实测**（`aoci init`/`scan` 输出、`sha256sum`、CI 输出），非推断
- **未运行** `aoci index`/`aoci_maintain`（即未建索引）—— 符合「先观察再建」的建议
- 未修改任何既有项目文件；AOCI 产物全部为**新增**
- **本报告不构成法律意见**
