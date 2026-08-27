"""MCP server for Midnight Skills — 让任意支持 MCP 的 AI Agent 调用 4 个 skill。

将 recall/core/pulse/compass 的命令行脚本封装为 MCP tools。
支持：Claude Desktop / Cursor / Cline / Continue / VS Code 等所有 MCP 客户端。

用法：
    pip install mcp requests
    python mcp_server.py          # stdio 传输（MCP 客户端默认方式）
    python mcp_server.py --http   # Streamable HTTP 传输（远程）
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from mcp.server.mcpserver import MCPServer

# skill scripts 根目录
SCRIPTS_DIR = Path(__file__).resolve().parent / "skills"

server = MCPServer(
    name="midnight-skills",
    title="Midnight Skills — AI 持久记忆与生命",
    description="给 AI 装上记忆（recall）、跨端时间线（core）、自主心跳（pulse）、语义路由（compass）",
    version="1.0.0",
)


def _run_py(skill: str, script: str, args: list[str]) -> str:
    """运行 skill 的 Python 脚本，返回 stdout。"""
    script_path = SCRIPTS_DIR / skill / "scripts" / script
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"  # 强制脚本用 UTF-8 输出，避免 Windows GBK 乱码
    cmd = [sys.executable, str(script_path), *args]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", env=env, timeout=120)
    if result.returncode != 0:
        return f"[ERROR] {result.stderr.strip() or result.stdout.strip()}"
    return (result.stdout or "").strip()


# ============================================================
# recall — 记忆
# ============================================================

@server.tool(
    name="recall_ingest",
    title="写日记入库",
    description="把日记目录中的新文件向量化入库。Agent 先写日记文件，再调用此工具让 AI 拥有记忆。",
)
async def recall_ingest(agent: str = "default", diary_dir: str = "") -> str:
    """入库指定 agent 的日记。diary_dir 为空则用默认目录。"""
    args = ["--agent", agent]
    if diary_dir:
        args += ["--diary", diary_dir]
    return _run_py("recall", "ingest.py", args)


@server.tool(
    name="recall_search",
    title="联想式记忆召回",
    description="根据当前话题召回相关记忆，支持联想（共现脉冲传播）、时间加权、多智能体隔离。返回可注入上下文的记忆片段。",
)
async def recall_search(
    query: str,
    agent: str = "default",
    k: int = 10,
    tag_weight: float = 0.3,
    time_ratio: float = 0.2,
    truncate: float = 1.0,
) -> str:
    """在指定 agent 的记忆库中做联想召回。"""
    args = ["--query", query, "--agent", agent, "--k", str(k)]
    return _run_py("recall", "recall.py", args)


@server.tool(
    name="recall_auto",
    title="自动路由记忆召回",
    description="自动判断查询属于哪个 agent（语义匹配 agent 描述），再在该 agent 的记忆库中召回。",
)
async def recall_auto(query: str, k: int = 10) -> str:
    """自动路由：按语义匹配 agent，再召回。"""
    return _run_py("recall", "recall.py", ["--query", query, "--auto", "--k", str(k)])


# ============================================================
# core — 跨端时间线
# ============================================================

@server.tool(
    name="core_append",
    title="写入跨端时间线",
    description="把一条消息追加到跨端时间线，带会话名、来源、角色。用于跨会话共享上下文。",
)
async def core_append(
    content: str,
    session_id: str = "default",
    source: str = "unknown",
    role: str = "user",
) -> str:
    """追加消息到时间线。"""
    args = ["--content", content, "--session", session_id, "--source", source, "--role", role]
    return _run_py("core", "append.py", args)


@server.tool(
    name="core_timeline",
    title="读取跨端时间线",
    description="获取其他会话的最近消息，跨端补充上下文。自动排除当前会话。",
)
async def core_timeline(session_id: str = "", limit: int = 10, hours: int = 24) -> str:
    """读取其他会话的时间线。"""
    args = ["--limit", str(limit), "--hours", str(hours)]
    if session_id:
        args += ["--session", session_id]
    return _run_py("core", "timeline.py", args)


# ============================================================
# pulse — 自主心跳
# ============================================================

@server.tool(
    name="pulse_loop",
    title="自主心跳循环",
    description="启动一个自主任务循环：AI 自己输出 [[Pulse::Start/Next/Complete]] 指令，脚本负责定时唤醒继续执行，直到任务完成或达到轮数上限。",
)
async def pulse_loop(
    prompt: str,
    system_prompt: str = "",
    api_url: str = "",
    api_key: str = "",
    model: str = "deepseek-v4-flash",
    rounds: int = 15,
    timeout: int = 300,
) -> str:
    """运行自主心跳循环。需提供模型 API 地址和 key。"""
    args = ["--prompt", prompt, "--model", model, "--rounds", str(rounds), "--timeout", str(timeout)]
    if system_prompt:
        args += ["--system", system_prompt]
    if api_url:
        args += ["--api-url", api_url]
    if api_key:
        args += ["--api-key", api_key]
    return _run_py("pulse", "pulse.py", args)


# ============================================================
# compass — 语义路由
# ============================================================

@server.tool(
    name="compass_route",
    title="语义模型路由",
    description="判断当前问题应该用哪个模型：日常闲聊用轻量模型，复杂推理用重量模型。返回推荐模型和备选。",
)
async def compass_route(query: str, preset: str = "") -> str:
    """语义路由。"""
    args = ["--query", query]
    if preset:
        args += ["--preset", preset]
    return _run_py("compass", "route.py", args)


# ============================================================
# 入口
# ============================================================

if __name__ == "__main__":
    if "--http" in sys.argv:
        # Streamable HTTP transport — 需额外依赖 uvicorn/starlette
        try:
            import uvicorn  # noqa: F401
        except ImportError:
            print("HTTP transport 需要: pip install uvicorn", file=sys.stderr)
            sys.exit(1)
        server.run(transport="streamable_http")
    else:
        server.run(transport="stdio")
