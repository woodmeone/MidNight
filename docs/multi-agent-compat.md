# Midnight Skills 多平台 AI Agent 适配指南

> 让 Midnight Skills（recall / core / pulse / compass）不只服务于 Reasonix，而是能被市面上主流 AI Agent 平台调用。
> 适配状态：2026-08-27

---

## 一、平台适配总览

| 平台 | 适配方式 | 状态 |
|---|---|---|
| **Anthropic Claude (Agent Skills)** | SKILL.md 原生格式 | ✅ 已兼容（无需改） |
| **MCP (Model Context Protocol)** | `mcp_server.py` 封装 | ✅ 已提供 |
| **OpenAI (function calling)** | `openai_functions.json` 定义 | ✅ 已提供 |
| **Reasonix** | SKILL.md + scripts 原生 | ✅ 原生 |
| **Cursor / Cline / Continue** | 通过 MCP | ✅ 已提供 |
| **DeepSeek harness** | 通过 MCP 或脚本 | ✅ 可接入 |

---

## 二、Anthropic Claude Agent Skills（原生兼容）

我们的 SKILL.md 格式**已经符合** Anthropic Agent Skills 规范，无需任何修改：

```
skills/recall/
├── SKILL.md          # frontmatter: name + description ✅
├── scripts/          # 可执行脚本 ✅
├── references/       # 按需加载的参考 ✅
└── tests/            # 测试 ✅
```

**接入方式**：把 `skills/` 下的目录（recall/core/pulse/compass）复制到 Claude 的 skills 目录，或在 Claude Code 中 `claude add-skill` 添加。

**Anthropic 规范确认**（primary source: Anthropic Agent Skills 文档）：
- `SKILL.md` 必需，位于 skill 目录根部
- YAML frontmatter 必须含 `name` 和 `description`
- 可选目录：`scripts/`、`references/`、`examples/`、`tests/`
- 我们的结构完全匹配

---

## 三、MCP (Model Context Protocol) —— 跨平台标准

**文件**：`mcp_server.py`（项目根目录）

MCP 是当前最主流的跨平台 Agent 工具协议，Claude Desktop、Cursor、Cline、Continue、VS Code、Raycast 等均支持。我们把 4 个 skill 的命令行封装成 7 个 MCP tools。

### 3.1 已封装的 Tools

| Tool | 对应 skill | 功能 |
|---|---|---|
| `recall_ingest` | recall | 日记向量化入库 |
| `recall_search` | recall | 联想式记忆召回 |
| `recall_auto` | recall | 语义自动路由召回 |
| `core_append` | core | 写入跨端时间线 |
| `core_timeline` | core | 读取跨端时间线 |
| `pulse_loop` | pulse | 自主心跳循环 |
| `compass_route` | compass | 语义模型路由 |

### 3.2 运行 MCP server

```bash
pip install mcp requests

# stdio 模式（MCP 客户端默认，本地）
python mcp_server.py

# Streamable HTTP 模式（远程，需 uvicorn）
pip install uvicorn
python mcp_server.py --http
```

### 3.3 各客户端接入配置

**Claude Desktop**（`claude_desktop_config.json`）：
```json
{
  "mcpServers": {
    "midnight-skills": {
      "command": "python",
      "args": ["D:/Project/DSH/midnight-skills/mcp_server.py"]
    }
  }
}
```

**Cursor**（`.cursor/mcp.json`）：
```json
{
  "mcpServers": {
    "midnight-skills": {
      "command": "python",
      "args": ["D:/Project/DSH/midnight-skills/mcp_server.py"]
    }
  }
}
```

**Cline / Continue / VS Code**：同样在各自的 MCP 配置里注册上面的 stdio server。

### 3.4 MCP server 内部实现

```python
from mcp.server.mcpserver import MCPServer

server = MCPServer(name="midnight-skills", ...)

@server.tool(name="recall_search", title="联想式记忆召回",
             description="根据当前话题召回相关记忆...")
async def recall_search(query: str, agent: str = "default", k: int = 10) -> str:
    # 内部调用 skills/recall/scripts/recall.py
    return _run_py("recall", "recall.py", [...])

server.run(transport="stdio")   # 或 "streamable_http"
```

---

## 四、OpenAI function calling

**文件**：`openai_functions.json`

OpenAI 风格的 7 个 function 定义，可直接用于 `tools` 参数：

```python
import json, openai

with open("openai_functions.json", encoding="utf-8") as f:
    tools = json.load(f)["tools"]

client = openai.OpenAI(api_key=...)
resp = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "帮我回忆上次聊的考试"}],
    tools=tools,  # ← 直接使用
    tool_choice="auto",
)
```

当模型选择调用 `recall_search` 时，解析 tool call 参数，然后执行对应脚本并把结果作为 `tool` 消息返回。

---

## 五、其他平台接入方式

### Cursor / Cline / Continue
通过 MCP（见 3.3 节），无需额外适配。

### DeepSeek harness
- 通过 MCP 接入
- 或直接在 agent 预设中调用脚本（`python skills/recall/scripts/recall.py --query ...`）

### 任意 OpenAI 兼容 API
`openai_functions.json` 适用于任何支持 OpenAI function calling 的模型（GPT、Claude via API、DeepSeek、Qwen 等）。

---

## 六、脚本级接入（零依赖方式）

不依赖 MCP/OpenAI，任何 Agent 只要有 shell 权限就能直接调用：

```bash
# 记忆：写日记 → 入库 → 召回
python skills/recall/scripts/ingest.py --agent Nova
python skills/recall/scripts/recall.py --query "焦虑" --agent Nova
python skills/recall/scripts/recall.py --query "代码" --auto

# 跨端
python skills/core/scripts/append.py --content "..." --session s1 --source web
python skills/core/scripts/timeline.py --limit 10

# 心跳
python skills/pulse/scripts/pulse.py --prompt "..." --api-url ... --api-key ...

# 路由
python skills/compass/scripts/route.py --query "今天天气"
```

---

## 七、修复记录（2026-08-27）

适配过程中发现并修复了 3 个此前测试掩盖的问题：

1. **脚本 CLI 直接运行失败**：`recall.py`/`tag_network.py`/`ingest.py`/`route.py` 用了 `from scripts.xxx import ...` 但只把 `scripts/` 加入 `sys.path`，缺少父目录。修复：同时插入 `scripts/` 和其父目录。
2. **数据库目录不存在时崩溃**：`recall()` 直接 `sqlite3.connect` 不存在的路径。修复：先 `init_db` 并关闭（避免 Windows 文件锁），再连接。
3. **Windows 编码乱码**：子进程脚本输出 GBK，`subprocess` 按 UTF-8 解码失败。修复：`PYTHONIOENCODING=utf-8` + `(result.stdout or "").strip()` 容错。

修复后全量测试：**155 passed**（recall 92 + core 21 + pulse 26 + compass 16）。

---

## 八、测试验证

```bash
# 全量测试
cd skills/recall && python -m pytest tests/ -q   # 92 passed
cd skills/core && python -m pytest tests/ -q      # 21 passed
cd skills/pulse && python -m pytest tests/ -q     # 26 passed
cd skills/compass && python -m pytest tests/ -q   # 16 passed

# MCP server 导入与 tool 调用
python -c "import mcp_server; print('OK')"
```

---

*参考：Anthropic Agent Skills 规范、MCP SDK 文档、OpenAI function calling 文档。*