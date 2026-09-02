---
name: recall
description: "让 AI 拥有长期记忆——自动写日记、联想式召回。当用户说"记住"、"还记得吗"、"帮我回忆"、"我上次说"或类似表达时触发。"
---

# midnight-recall

让 AI 拥有持久记忆。不需要你手动保存，不需要你提关键词——AI 会自动写日记、自动联想回忆。

## 核心能力

1. **自动写日记**：你聊完一段重要内容，AI 会在回复末尾写一份日记文件。Agent 用 `write_file` 工具写入 **当前 agent 专属目录** `~/.midnight/recall/<agent>/dailynote/`（`<agent>` 为当前智能体名，默认 `default`），`ingest.py` 自动入库。**不要写根级 `~/.midnight/recall/dailynote/`**——那是无主数据，不属于任何智能体。
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

当需要写日记时，使用 `write_file` 工具把日记写到 **当前 agent 专属目录** `~/.midnight/recall/<agent>/dailynote/`（`<agent>` 为当前智能体名，默认 `default`），文件名为 `YYYY-MM-DD_HHMMSS.md`。**不要写到根级 `~/.midnight/recall/dailynote/`**——那不在 `list_agents()` 覆盖内，不会被任何智能体召回。

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

**对象标签规约（V2）**：Midnight 只维护**一个记忆库**（单 agent 单库）。每个遇到的人/组织是一个"对象"——对象不是一个独立库，而是一组 anchor tag：凡是关于对象 X 的日记，`tags` 里必须带上 `X`（如 `阿散`）。对象与对象、对象与话题靠共现网自然缠绕，无需建子目录或分库。
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
# 注意：db 路径是当前 agent 专属库 ~/.midnight/recall/<agent>/recall.db，不是根级 recall.db
results = recall_associative("用户的问题", "~/.midnight/recall/default/recall.db", embedding_client,
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

## init 引导（首建自我 + 认识你）

V2：每个 agent 是一个有独立自我的个体。首次运行做**轻引导**——先建 self 锚，再问对方怎么称呼，把名字当作对象 anchor tag 写进后续日记。引导只 1–2 句话 + 默认值，不打断主流程。

**首建自我（第一次对话时）**：调用 `self_model.py --init` 自动生成 self.md（无则建，已有则幂等不动）：

```bash
python self_model.py --init
```

若尚无 self，用 1–2 句话引导用户"给自己定位"，例如：
> 你还没给自己定位——想要怎样的性格/能力/边界？不说的话我先用默认值（冷静高效的助手），随时可改。

默认值见 `self_model.py` 的 `DEFAULT_TEMPLATE`（name=midnight-agent，persona_style=冷静高效务实）。

**认识使用者（对象锚）**：
- 主动问对方称呼，例如：> 我该怎么称呼你？之后关于你的事我都会记进日记。
- 得到名字（如"阿散"）后，凡涉及该使用者的日记，`tags` 里都要带上这个名字（见"对象标签规约"）。
- 对方不回答就继续用默认值，不纠缠。

## 自进化（/evolution）

Agent 会基于新交互/调研/**镜像反馈**（自己回看自己的表现）评估并改写 self 的**可动层**；**定海锚只读**，改 name/anchor_tags/description 会被拒绝——防跑飞。规则不固化：高频纠正靠日记共现自然强化关联；长期不用的关联可显式衰减。

```bash
# 应用一次演化（可动层 patch；定海锚字段自动被拒）
python evolution.py --apply --feedback "用户纠正：Windows 用 py" --patch '{"position": "Windows 工程师"}' --source user

# 久不用衰减：90 天未触碰的关联降权，弱边删除
python evolution.py --decay --stale-days 90 --factor 0.5

# 查看演化历史
python evolution.py --log
```

## 多智能体物理隔离与孤儿数据

每个智能体有自己独立的 `recall.db` 与 `dailynote/`（`~/.midnight/recall/<agent>/`），互不读取、互不写入。`--auto` 路由时非 default agent 需与查询有词面锚定才会被选中，泛化/情绪化查询回落到 `default`，避免跨库误取私密记忆。

早期单库时代残留的数据（根级 `~/.midnight/recall/recall.db`、根级 `~/.midnight/recall/dailynote/`）不属于任何 agent，也不会被 `list_agents()` 识别。用 `maintenance.py` 检测并归并：

```bash
## 只报告，不修改
python maintenance.py --scan

## 把根级孤儿数据迁移进指定 agent（默认 default），并自动重新入库
python maintenance.py --migrate --agent default
```

## 首次使用

首次运行前，需要初始化数据库和配置：

```bash
## 安装依赖
pip install requests

## 初始化（可选，ingest 会自动创建）
## 设置 embedding API key（可选，默认使用假 embedding 离线可用）
# export SILICONFLOW_API_KEY="sk-..."
# export MIDNIGHT_BASE_DIR="~/.midnight"        # 记忆根目录（默认 ~/.midnight）
# export MIDNIGHT_AGENT="default"               # 当前智能体（决定写入哪个子区）
# 注意：MIDNIGHT_DB_PATH / MIDNIGHT_DAILYNOTE_PATH 已废弃，路径一律按 agent 从 BASE_DIR 推导

## 入库当前 agent 的日记（按 agent 子目录，勿指向根级 dailynote）
python ingest.py ~/.midnight/recall/default/dailynote/

## 测试召回
python recall.py --query "写一条测试查询" --k 5
```

## 文件结构

```
skills/recall/
├── SKILL.md              # 本文件
├── scripts/
│   ├── ingest.py         # 日记入库（切块 → 向量化 → SQLite + 方向边）
│   ├── recall.py         # 联想召回（向量 + 标签脉冲 + 时间 + 深联想扩增）
│   ├── tag_network.py    # 标签方向边 + 脉冲传播（压缩/枢纽校正/预算/Core-Ghost）
│   ├── self_model.py     # self 锚生成/读取/演化（定海锚 + 可动层）
│   ├── evolution.py      # 自进化（可动层覆写 + 演化日志 + 久不用衰减）
│   ├── session_start.py  # 首轮上下文轻编译（身份摘要 ≤200 字）
│   ├── maintenance.py    # 根级孤儿数据检测/迁移（--scan / --migrate）
│   ├── embedding.py      # embedding 客户端（可注入 fake）
│   └── schema.py         # SQLite schema
├── tests/
│   ├── conftest.py
│   ├── test_ticket01.py  ~ test_ticket04.py
│   ├── test_self_model.py
│   ├── test_object_association.py
│   ├── test_t3_deep_association.py
│   ├── test_session_start.py
│   ├── test_diary_isolation.py / test_auto_routing.py / test_end_to_end.py
│   └── test_adversarial.py / test_features_adversarial.py / test_base_dir.py
└── references/           # 按需加载的深度参考
```

## 参考资料

- 设计受 VCP(VCPToolBox) 的 TagMemo 算法和联想记忆理念启发
- 许可证：CC BY-NC-SA 4.0（详见根目录 LICENSE）