# midnight-recall 规格文档

> 发布者：to-spec（2026-08-20）
> 标签：`ready-for-agent`

---

## Problem Statement

AI 对话模型本质上是"无状态"的——每次对话都是一次新生，每次结束都是一次失忆。用户需要它记住几个月前的事，但它连上一轮说了什么都想不起来。传统 RAG 方案只能按用户**提的关键词**检索，做不到"你不提它也能联想起来"。

用户需要一个**长期记忆系统**，让 AI 拥有：
- 持久记忆：对话自动写入，不丢不散
- 联想召回：不靠关键词命中，靠因果/情感/共现脉络联想
- 时间感知：知道"最近发生了什么"，新会话开头不空白

## Solution

**midnight-recall** 是一个 Reasonix 原子 skill，包含：

1. **写入侧**：Agent 直接用文件工具写日记文件到 `~/.midnight/recall/dailynote/`，`ingest.py` 自动扫描入库（切块 → 向量化 → SQLite 索引）—— 不需要暗号协议，不需要服务端解析。
2. **存储侧**：SQLite 单文件数据库，含 chunks 向量表、tags 标签索引、tag_cooccurrence 共现矩阵。
3. **检索侧**：`recall.py` 接收当前会话上下文 → 向量化查询 → 最近邻检索 → 共现矩阵联想扩增 → 时间连续性召回 → 输出截断后的上下文片段，供 AI 注入。
4. **联想侧**：标签共现矩阵 + 脉冲传播算法 —— 激活标签沿共现网络扩散，使关联内容自动浮现。

## User Stories

1. 作为 AI 用户，我希望 AI 能自动记住我们的对话内容（不要求我手动保存），所以下次聊天时它不会"失忆"。
2. 作为 AI 用户，我几个月前提过一件事，几个月后我随口说一句相关的话，AI 能自己联想起来，而不是要我先提到关键词。
3. 作为 AI 用户，我希望新会话开始时，AI 能自动知道最近几天发生了什么，不需要我"补课"。
4. 作为 AI 用户，我希望 AI 能记住我个人的偏好、习惯和重要信息（如喜欢的颜色、生日、考试日期），并在需要时主动提及。
5. 作为 AI 用户，我希望记忆系统不需要我手动安装数据库或向量服务，能开箱即用。
6. 作为 AI 开发者，我希望记忆系统是模块化的，可以被其他 skill（如 midnight-core、midnight-pulse）复用。
7. 作为 AI 开发者，我希望 memory skill 的召回参数是可调节的（召回数量、联想深度、时间权重等），以便适配不同场景。
8. 作为 AI 用户，我希望在对话中对 AI 说"记住这个"或"把刚才说的记下来"，AI 能立刻写入记忆。
9. 作为 AI 用户，我希望记忆系统能区分"重要的长期记忆"和"日常闲聊"，不会让无关紧要的内容污染重要记忆。
10. 作为 AI 用户，我希望记忆数据的存储格式是开放的（SQLite），必要时我可以直接查看或导出。

## Implementation Decisions

### 写入侧

- **日记文件格式**：Agent 用 `write_file` 工具写入 `~/.midnight/recall/dailynote/`，文件名格式 `YYYY-MM-DD_HHMMSS.md`。内容包含标准的 YAML 前置元数据：
  ```yaml
  ---
  maid: Nova
  created: 2026-08-20T14:30:00
  tags: [考试, 压力, 面试]
  ---
  今天阿漂说下周要面试，有点紧张。他准备了三天，但觉得不够充分。
  ```
- **`ingest.py`**（CLI 入口）：
  - 扫描 `dailynote/` 下未入库的文件（基于 checksum 或文件时间戳判断）
  - 切块：按段落或每 512 字符切一块（可配置）
  - 提取标签：从 YAML frontmatter 的 tags 字段 + 内容中自动提取关键词
  - 向量化：调 embedding API（默认 SiliconFlow bge-m3，1024 维，可配置 apiUrl 和 apiKey）
  - 写入 SQLite：`chunks`（content + vector）、`files`（file path + checksum）、`tags`（tag name + vector）、`chunk_tags`（关联）
  - 更新共现矩阵：同一文件中的标签两两配对，`tag_cooccurrence` 表中权重 +1
  - 支持 `--watch` 模式：持续监听目录变化

### 存储侧

- **数据库路径**：`~/.midnight/recall/recall.db`（SQLite 单文件）
- **表结构**：
  ```sql
  CREATE TABLE files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path TEXT UNIQUE NOT NULL,
    diary_name TEXT NOT NULL DEFAULT 'default',
    checksum TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
  );

  CREATE TABLE chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER NOT NULL REFERENCES files(id),
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    vector BLOB,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(file_id, chunk_index)
  );

  CREATE TABLE tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    vector BLOB,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
  );

  CREATE TABLE chunk_tags (
    chunk_id INTEGER NOT NULL REFERENCES chunks(id),
    tag_id INTEGER NOT NULL REFERENCES tags(id),
    position INTEGER DEFAULT 0,
    PRIMARY KEY (chunk_id, tag_id)
  );

  CREATE TABLE tag_cooccurrence (
    tag1_id INTEGER NOT NULL REFERENCES tags(id),
    tag2_id INTEGER NOT NULL REFERENCES tags(id),
    weight REAL NOT NULL DEFAULT 1.0,
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (tag1_id, tag2_id),
    CHECK (tag1_id < tag2_id)
  );

  CREATE INDEX idx_chunks_vector ON chunks(vector);
  CREATE INDEX idx_tags_name ON tags(name);
  CREATE INDEX idx_tag_cooccurrence_weight ON tag_cooccurrence(weight DESC);
  ```
- **向量检索**：SQLite 不支持原生向量索引，通过 Python 加载全部向量到内存做余弦相似度（数据量 < 10 万条时性能可接受）。未来可接入本地向量库（如 `usearch`、`faiss`）。

### 检索侧

- **`recall.py`**（CLI 入口）：
  - 接收参数：`--query "查询文本"`、`--k 10`（召回数量）、`--tag-weight 0.3`（联想权重）、`--time-ratio 0.2`（时间权重）、`--truncate 0.25`（截断比例）
  - 流程：
    1. 查询向量化 → 在 chunks 中做余弦相似度最近邻检索 → 初始候选集
    2. 如果启用联想（`--tag-weight > 0`）：提取查询中的标签 → 沿共现矩阵脉冲传播（广度优先，深度可配置）→ 关联标签的 chunk 也加入候选集
    3. 如果启用时间连续性（`--time-ratio > 0`）：最近 N 天内的 chunk 获得额外权重
    4. 合并去重 → 按综合得分排序 → 截断 → 输出上下文片段（纯文本）
  - 输出格式：供直接注入到 AI 上下文的一段文字，格式为：
    ```
    [回忆] 以下是相关记忆（来源于你的日记，按相关度排序）：
    
    （2026-08-15）你提到下个月要参加考试，准备了复习计划。
    （2026-08-10）你最爱的颜色是蓝色。
    ```

### 联想侧（共现矩阵 + 脉冲传播）

- **共现矩阵构建**：`ingest.py` 在入库时更新 `tag_cooccurrence` 表。同一文件出现的标签两两配对，weight + 1。
- **脉冲传播算法**：
  1. 从查询中提取或感应标签（通过向量相似度找到最匹配的标签）
  2. 为每个激活标签赋予初始脉冲强度（1.0）
  3. 广度优先扩散：对每个已激活标签，找到与其共现的标签，脉冲强度递减（乘以衰减因子，默认 0.5）
  4. 深度限制：默认 2 层（激活标签 → 直接关联标签 → 次关联标签）
  5. 强度低于阈值（默认 0.1）的剪枝不传播
  6. 被传播到的标签获得综合强度，用于召回关联 chunk

### 配置

- 配置文件：`~/.midnight/recall/config.toml`，可配置：
  ```toml
  [embedding]
  api_url = "https://api.siliconflow.cn/v1"
  api_key = ""
  model = "BAAI/bge-m3"
  dimension = 1024
  
  [recall]
  default_k = 10
  default_tag_weight = 0.3
  default_time_ratio = 0.2
  default_truncate = 0.25
  pulse_decay = 0.5
  pulse_max_depth = 2
  pulse_threshold = 0.1
  
  [store]
  db_path = "~/.midnight/recall/recall.db"
  dailynote_path = "~/.midnight/recall/dailynote/"
  ```

## Testing Decisions

### 测试策略

- **只测外部行为，不测实现细节**。测试关心的是"输入一份日记能不能检索到它"、"联想扩散是否生效"，不关心"SQLite 的 INSERT 语句发了多少次"。
- **最高缝优先**：端到端测试覆盖主要流程，模块级测试覆盖核心算法。

### 测试模块

| 测试 | 类型 | 描述 |
|---|---|---|
| `test_ingest_and_recall.py` | 端到端 | 写测试日记 → 运行 ingest.py → 运行 recall.py 用相关查询 → 验证召回结果包含原始内容 |
| `test_cooccurrence.py` | 模块 | 构建共现矩阵 → 脉冲传播 → 验证标签扩散正确 |
| `test_similarity_search.py` | 模块 | 入库几条不同内容的 chunk → 查询 → 验证相似度排序正确 |
| `test_time_continuity.py` | 模块 | 入库新旧日记 → 验证时间权重参数排序效果 |
| `test_truncation.py` | 模块 | 大量召回结果 → 验证截断比例生效 |

### 测试数据

- 测试日记文件放在 `skills/recall/tests/fixtures/` 下，包含：
  - 简单日记（1 个 tag，1 段内容）
  - 复杂日记（多个 tag，多段内容）
  - 时间跨度日记（模拟多个日期）
  - 联想场景日记（"考试"和"压力"在同一篇中出现）

## Out of Scope

- **前端 UI**：不提供管理面板或可视化界面，纯 CLI + SKILL.md 使用。
- **Rust 向量内核**：不实现 Rust 向量索引，用 Python 余弦相似度（SQLite 规模足够）。
- **多模态记忆**：不支持图片、音频等非文本内容。
- **分布式**：不涉及跨机器同步。
- **记忆编辑/删除**：第一期不提供主动编辑或删除记忆的接口（可通过直接操作 SQLite 实现）。
- **加密/隐私**：第一期不实现记忆内容加密。

## Further Notes

- 设计受 VCP（VCPToolBox）的 TagMemo 浪潮算法和 RiverMemo 拓扑记忆启发，但`ingest.py`、`recall.py`、`tag_network.py` 等全部原创实现，不复制 VCP 代码（详见 ADR-0001）。
- embedding 默认使用 SiliconFlow 的 BAAI/bge-m3（1024 维，免费），可在 config 中切换为任意 OpenAI 兼容的 embedding API 或本地模型。
- 标签共现矩阵是 VCP 的简化版——VCP 的 TagMemo 有 EPA 投影、残差金字塔、脉冲传播算法，我们第一期实现"共现计数 + 广度优先传播"作为最小可行版本。后续可升级算法，不改变接口。
- 第一期目标：`ingest.py` + `recall.py` + `tag_network.py` 三个脚本 + `SKILL.md`。Skill 的 SKILL.md 定义 AI 何时写日记、如何写日记、如何调用召回。