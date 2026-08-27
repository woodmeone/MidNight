---
name: recall
description: "让 AI 拥有长期记忆——自动写日记、联想式召回。当用户说"记住"、"还记得吗"、"帮我回忆"、"我上次说"或类似表达时触发。"
---

# midnight-recall

让 AI 拥有持久记忆。不需要你手动保存，不需要你提关键词——AI 会自动写日记、自动联想回忆。

## 核心能力

1. **自动写日记**：你聊完一段重要内容，AI 会在回复末尾写一份日记文件。Agent 用 `write_file` 工具写入 `~/.midnight/recall/dailynote/`，`ingest.py` 自动入库。
2. **联想式召回**：不靠关键词命中，而是通过"标签共现网络"脉冲传播——你今天说"压力大"，昨天聊的"考试"会自动浮上来。
3. **时间感知**：最近的记忆有更高权重，新会话开头不空白。
4. **可配置**：召回数量、联想强度、时间权重、截断比例均可调。

## 触发条件

当用户表达以下意图时，你应当使用本 skill。**你不需要等用户主动要求回忆——每次回复前，先查一下记忆，看看当前话题有没有相关历史。**

| 触发词/情境 | 操作 |
|---|---|
| **每次回复用户前**（默认行为） | 运行 `recall.py --query "当前话题" --auto`，查当前话题的相关记忆，注入到回复开头 |
| "记住" / "记一下" / "帮我记住" | 写一份日记文件（见"写日记协议"） |
| "还记得吗" / "你记得" / "帮我回忆" | 运行 `recall.py` 做联想召回 |
| 新会话开始 | 运行 `recall.py` 带时间连续性，自动补最近记忆 |
| 用户说"我上次说" / "之前提到" | 运行 `recall.py` 做联想召回 |
| 沉默一段时间后用户发消息 | 先运行 `recall.py` 再回复 |

## 写日记协议

当需要写日记时，使用 `write_file` 工具把日记写到 `~/.midnight/recall/dailynote/` 目录下，文件名为 `YYYY-MM-DD_HHMMSS.md`。

日记格式采用 YAML frontmatter：

```yaml
---
maid: Nova
created: 2026-08-20T14:30:00
tags: [考试, 压力, 面试]
---
今天阿漂说下周要面试，有点紧张。他准备了三天，但觉得不够充分。
```

**字段说明**：
- `maid`：角色名（默认 default）
- `created`：ISO 格式时间戳（精确到秒）
- `importance`：重要性（high/medium/low），影响召回权重。high=1.5倍，medium=1.0倍，low=0.5倍
- `tags`：标签数组，用逗号分隔。**标签是联想的关键**——同一次日记中出现的标签会在共现矩阵中连线，未来任何一个标签被激活，关联标签的内容也会被召回。所以标签要准确、有区分度、有覆盖度。
- 正文：纯文本，记录核心事件、关键信息、情感状态。

**写日记的时机**：
- 用户明确要求"记住"时
- 聊天中产生了有价值的信息（重要偏好、个人经历、计划、关键决策、学习收获等）
- 注意：**不需要每次对话都写**，只在真正有保留价值的内容出现时才写。避免写琐碎的日常闲聊，保持日记的"信息密度"——精炼、聚焦核心。

## 召回调用

使用 `recall.py` 做联想召回：

```bash
# 最基本的召回
python recall.py --query "用户的问题或当前话题" --k 10

# 带联想和时间加权的召回
python recall.py --query "用户的问题" --k 10 --tag-weight 0.5 --time-ratio 0.3 --truncate 0.5
```

你也可以直接调用 `recall_associative` 函数（如果脚本作为模块导入）：

```python
from scripts.recall import recall_associative
results = recall_associative("用户的问题", "~/.midnight/recall/recall.db", embedding_client,
                             k=10, tag_weight=0.3, time_ratio=0.2, truncate=1.0)
```

## 路由表

按场景推荐参数组合：

| 场景 | k | tag_weight | time_ratio | truncate | 说明 |
|---|---|---|---|---|---|
| 新会话开头自动补忆 | 5 | 0.2 | 0.5 | 0.5 | 时间优先，先看看最近发生了什么 |
| 用户说"还记得吗" | 10 | 0.5 | 0.1 | 0.3 | 联想优先，找最相关的 |
| 用户说"帮我回忆上次XXX" | 10 | 0.3 | 0.2 | 0.5 | 平衡模式 |
| 沉默后回复 | 5 | 0.3 | 0.3 | 0.3 | 轻量召回，快速给上下文 |
| 用户明确说"记住"（不触发召回） | — | — | — | — | 只写日记，不做召回 |

## 首次使用

首次运行前，需要初始化数据库和配置：

```bash
## 安装依赖
pip install requests

## 初始化（可选，ingest 会自动创建）
## 设置 embedding API key（可选，默认使用假 embedding 离线可用）
# export SILICONFLOW_API_KEY="sk-..."
# export MIDNIGHT_DB_PATH="~/.midnight/recall/recall.db"
# export MIDNIGHT_DAILYNOTE_PATH="~/.midnight/recall/dailynote/"

## 入库已有的日记文件
python ingest.py ~/.midnight/recall/dailynote/

## 测试召回
python recall.py --query "写一条测试查询" --k 5
```

## 文件结构

```
skills/recall/
├── SKILL.md              # 本文件
├── scripts/
│   ├── ingest.py         # 日记入库（切块 → 向量化 → SQLite）
│   ├── recall.py         # 联想召回（向量 + 标签脉冲 + 时间）
│   ├── tag_network.py    # 标签共现矩阵 + 脉冲传播
│   ├── embedding.py      # embedding 客户端（可注入 fake）
│   └── schema.py         # SQLite schema
├── tests/
│   ├── conftest.py
│   ├── test_ticket01.py
│   ├── test_ticket02.py
│   ├── test_ticket03.py
│   └── test_ticket04.py
└── references/           # 按需加载的深度参考
```

## 参考资料

- 设计受 VCP(VCPToolBox) 的 TagMemo 算法和联想记忆理念启发
- 许可证：CC BY-NC-SA 4.0（详见根目录 LICENSE）