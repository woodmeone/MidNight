# Midnight Skills — PROJECT（当前真相）

> 本文件只回答"项目现在是什么样"。
> 为什么变 → Issue/PR/Git 历史；术语 → `CONTEXT.md`；决策理由 → `docs/adr/`；进度与下一步 → `ROADMAP.md`。

## 项目目标

给 AI 装上持久记忆和生命——记得你、会办事、不用催、懂选择。四个原子化 Reasonix skill，补齐 AI 的四个核心缺陷（无记忆、跨端不认人、只能被动回复、不管什么题都用同一个模型）。

## 模块地图

| 模块 | 代码区域 | 核心入口 | 职责 |
|---|---|---|---|
| `midnight-recall` | `skills/recall/scripts/` | `prep.py`（回复前记忆准备，**推荐入口**）、`recall.py`（联想召回）、`ingest.py`（日记入库） | 自动写日记 + 联想式召回 + 自我模型 |
| `midnight-core` | `skills/core/scripts/` | `append.py`（追加事实）、`timeline.py`（合并时间线） | 跨端/跨会话统一事实时间线 |
| `midnight-pulse` | `skills/pulse/scripts/` | `pulse.py`（心跳循环） | AI 自主定闹钟，干完活自己醒来继续 |
| `midnight-compass` | `skills/compass/scripts/` | `route.py`（语义路由） | 按问题难度自动选模型 + 容灾切换 |

recall 内部模块分工：

| 文件 | 职责 |
|---|---|
| `prep.py` | 可移植核心：门控→取 query→召回→去重→MMR→预算→格式化文本；薄 CLI |
| `recall.py` | 向量 KNN + 标签脉冲合并 + 时间加权 + tag-first 扩增 + `mmr_rerank` + 反馈强化 `feedback_reward` |
| `tag_network.py` | 标签方向边 + 脉冲传播（压缩/枢纽降温/Core-Ghost 门控/多尺度线索提取） |
| `embedding.py` | 嵌入客户端三后端：本地 bge-m3 ONNX / SiliconFlow API / Fake（离线兜底），三级模型自动解析 |
| `ingest.py` / `schema.py` | 日记切块入库 / SQLite schema |
| `self_model.py` / `evolution.py` | self 锚（定海锚只读 + 可动层）/ 自进化与久不用衰减 |
| `session_start.py` / `maintenance.py` / `reembed.py` | 首轮身份摘要 / 孤儿数据迁移 / 非破坏式重嵌入 |
| `cache.py` / `ngrams.py` / `config.py` | 召回结果缓存 / 倒排 n-gram / agent 物理隔离路径 |

## 核心业务流程

1. **写日记**：Agent 按写日记协议（一事一记、时间取真、tags 进 frontmatter）写 md 到 `~/.midnight/recall/<agent>/dailynote/` → `ingest.py` 切块、向量化、写入 SQLite，同文件标签建方向边（tag_edges）与共现（tag_cooccurrence）。
2. **回复前召回**：`prep.py --message "用户原话" --identity <名字>` → 门控（触发词必召回/寒暄跳过/冷却可注入时钟）→ 取 query（AI 语义优先，缺省用原话）→ `recall_associative`（向量 KNN + 标签脉冲 + 时间加权 + tag-first 有界扩增）→ 去重 → 可选 MMR 重排 → 预算收条（完整注入不截半句）→ 输出 `[回忆]` 文本块 + 结构化 results。
3. **身份隔离**：显式 `--identity/--agent` = 确定性查自己区（声明即自动开户）；`--auto` 仅兜底，非 default 需词面锚定 ≥2 字才可选，防跨区泄漏。
4. **自我模型**：`self_model.py --init` 首建 self 锚；`evolution.py --apply` 只改可动层，定海锚字段拒绝；`--decay` 压冷边。

## 关键数据结构

每个 agent 一个物理隔离区 `~/.midnight/recall/<agent>/`：

- `recall.db`（SQLite）：`files`（日记源）、`chunks`（切块 + vector BLOB + importance + access_count）、`tags`（+vector）、`chunk_tags`、`tag_cooccurrence`（无向共现）、`tag_edges`（方向边，脉冲传播底座）、`chunk_ngrams`（倒排预筛）、`meta`、`recall_cache`
- `agent.json`：身份（description + keywords，list_agents 依据）
- `dailynote/`：日记 md 源文件（真相源，永不删）
- `self.md`：自我锚（frontmatter 含 read_only 定海锚）

## 必须遵守的约束

- **记忆物理隔离**：一区一库，跨区读写禁止；auto 猜库不得戳破隔离墙。
- **非破坏铁律**：任何维护/演化操作只 UPDATE 既有字段与边，绝不删除、重建、重灌记忆数据；动真实库前先备份。
- **定海锚只读**：self 的 name/anchor_tags/description 改写被拒，防跑飞。
- **零外部服务**：Python + SQLite 标准库自包含；embedding 默认本地 bge-m3 ONNX（1024 维，三级模型解析），无模型无 key 时 Fake 兜底可离线跑。
- **默认关闭新行为**：多尺度、MMR、深联想等能力开关默认关闭，关闭时逐位等于旧行为。
- **许可**：CC BY-NC-SA 4.0；不复制 VCP 代码、不引用 VCP 品牌（ADR-0001）。

## 当前支持功能（一行清单）

- recall：日记入库 / 联想召回（脉冲传播+枢纽降温+Core-Ghost+多尺度+MMR）/ 身份隔离与 auto 兜底 / 检索反馈强化 / 倒排预筛与结果缓存 / 本地 ONNX 真向量化与非破坏重嵌入 / self 锚与自进化 / 孤儿数据迁移 / 首轮上下文轻编译
- core：跨端事实时间线 append / merge（时间戳 + 去重）
- pulse：`[[Pulse::*]]` 心跳协议自主续命
- compass：语义模型路由 + 主模型容灾降级

## 演进方向

见 `ROADMAP.md`（进度追踪与下一步计划）。
