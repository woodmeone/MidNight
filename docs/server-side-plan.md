# Midnight Skills — 服务端扩展规划（Future / 留档）

> 目的：**记忆**。记录"什么情况下、为什么、怎么给 Midnight 加服务端"。供后续 AI 会话在决定"要不要上服务、上什么服务"时直接参考，无需重推来龙去脉。
> 日期：2026-09-02　状态：future / 未实施（当前保持纯 skill 形态，无服务端）
> 相关：`docs/OPTIMIZATION-SPEC.md`（§4.B.6、§6 Out of Scope）、`docs/optimization-blueprint.md`

---

## 0. 当前形态（为什么现在没有服务端）

- **单机、单人、按需触发**：AI（模型）当大脑，脚本当手，SQLite 当"永远在线的服务"（数据常驻磁盘，无需守护进程）。
- **明确边界（SPEC §6）**：不做 VCP 服务端/插件放大；不做 letta 桌面/app；不做云端 SaaS。
- **收益**：零部署、零守护进程、零鉴权、零端口冲突，任何环境可跑（README 明写"完全自包含：Python + SQLite，零数据库服务"）。

核心结论：微服务解决的三件事（多客户端并发、常驻内存状态共享、后台持续运行），当前需求一个都不满足。

---

## 1. 触发条件（满足任一 → 值得上服务端）

1. **真实本地 embedding 模型常驻**：bge / text-embedding 等数百 MB 模型逐次调用现加载太慢。
   - 注：`embedding.py` 已有 `SiliconFlowEmbeddingClient`（远程 API 版真模型）。若远程可接受，本地常驻可推迟。
2. **后台自动行为**：定时衰减（`evolution.py --decay`）、定时自省演化（`/evolution`）、流式、后台归档。
3. **多客户端并发访问同一记忆库**：多个 agent / 多会话 / 多设备同时读写。
4. **多设备 / 云端同步**：配合 MemFS 式 memory 目录 git 化（SPEC §4.B.6）。
5. **开放给第三方系统调用**：非 git / 非 AI 的系统也要读写记忆（提供 API）。

---

## 2. 服务端职责边界（只做记忆，不做 Agent 推理）

| 职责 | 说明 |
|---|---|
| Embedding 服务 | 模型常驻，对外只暴露 `embed(texts) -> list[vector]` |
| 记忆读写 API | 包装现有 scripts：ingest / recall / session_start / evolution，对外 REST / JSON-RPC / MCP |
| 后台任务 | 定时 decay、自省演化、归档（原 CLI 手动 → 定时） |
| 并发串行化 + 缓存 | 多客户端安全、热点查询缓存 |
| 多 agent 会话管理 | 可选 |

**禁区**：不做 Agent 推理 / 工具系统（那是 letta 的活儿，Midnight 保持 skill 边界）。

---

## 3. 现有代码如何复用（改造路径，几乎不用重写）

- **scripts/ 已是纯函数 + SQLite**，天然可被服务包裹，内部逻辑基本不动。
- **embedding.py 可注入**：已定义统一接口 `EmbeddingClient.embed(texts)` + 工厂 `load_embedding_client(config)`。
  - 本地常驻模型只需**新实现同一个接口**并注册进工厂即可；
  - 现有：`FakeEmbeddingClient`（离线）/ `SemanticFakeEmbeddingClient`（测试）/ `SiliconFlowEmbeddingClient`（远程 API）。
- **schema.py / ingest.py / recall.py / evolution.py** 全部是函数级 API，服务端可直接 import 调用。
- **mcp_server.py（项目根）已是 MCP 封装雏形** → 服务端 API 层可复用它作为入口之一。
- **数据层不变**：仍是 SQLite（并发可开 WAL；`decay_stale_edges` 已按连接操作，天然可服务化）。

---

## 4. 建议架构形态（Phase 路线，向后兼容）

```
Phase 1：Embedding 服务化
  本地模型常驻，仅暴露 embed()；改动最小 = 新增一个 client + 一个常驻进程。
  （若接受 SiliconFlow 远程 API，本阶段可跳过）

Phase 2：记忆 API 层
  把 scripts 暴露为 REST / JSON-RPC，或扩展 mcp_server.py；
  多客户端可用；现有 skill 的 CLI/函数调用保持不变。

Phase 3：后台任务 + 同步
  定时 decay / evolution；MemFS 式 memory 目录 git 化；
  可选云同步 / 多设备。
```

每阶段都向后兼容：**skill 调用仍走 CLI/函数，服务只是新增的另一个入口**，不破坏现有形态。

---

## 5. 明确不做（避免跑偏）

- 不做 Agent 推理 / 工具系统 / 常驻对话循环（letta 定位）。
- 不做 VCP 的 multi-embedding 重排 / Flow lock / 插件放大（SPEC §6）。
- 不做 EPA / Residual Pyramid 复杂算法（SPEC §6，A-二阶 future；若未来做，放服务端合适）。
- 不做付费 SaaS 变现（除非后续单独立项）。

---

## 6. 上线前置检查清单（供未来决策）

- [ ] 单机按需是否已不够用？（量化：模型加载耗时 / 并发数 / 共享需求）
- [ ] embedding 选本地常驻还是远程 API？（SiliconFlow 已可用则先不常驻）
- [ ] 服务进程退出后状态是否无损？（SQLite 保证，仍要确认无未落盘缓存）
- [ ] 端口 / 鉴权 / 开机自启 / 日志方案。
- [ ] 是否与 MemFS git 化（跨机版本追）一起做，还是只做本地 API。
