---
name: recall
description: "让 AI 拥有长期记忆——自动写日记、联想式召回。当用户说“记住”、“还记得吗”、“帮我回忆”、“我上次说”或类似表达时触发。"
---

# midnight-recall

让 AI 拥有持久记忆。不需要你手动保存，不需要你提关键词——AI 会自动写日记、自动联想回忆。

## 核心能力

1. **自动写日记**：你聊完一段重要内容，AI 会在回复末尾写一份日记文件。Agent 用 `write_file` 工具写入 **当前 agent 专属目录** `~/.midnight/recall/<agent>/dailynote/`（`<agent>` 为当前智能体名，默认 `default`），`ingest.py` 自动入库。**不要写根级 `~/.midnight/recall/dailynote/`**——那是无主数据，不属于任何智能体。
2. **联想式召回**：不靠关键词命中，而是通过"标签共现网络"脉冲传播——你今天说"压力大"，昨天聊的"考试"会自动浮上来。
3. **时间感知**：最近的记忆有更高权重，新会话开头不空白。
4. **可配置**：召回数量（`--k`）、联想强度、时间权重、截断比例（`--truncate`，按条数比例裁剪）均可调。
5. **注入保留完整 + 预算控体积**：召回的记忆默认**保留完整正文、不拦腰截断**（语义优先）；若担心上下文/token 被撑爆，传 `--budget <字符数>` 按预算召回最高相关的那几条完整记忆即可。

## 检索通道铁律（默认走算法，不翻原文）

回答任何"你还记得…"的问题，只有三条合法通道，**默认且优先用第 1 条**：

| # | 通道 | 命令 | 什么时候用 |
|---|---|---|---|
| 1 | **联想通道**（默认） | `prep.py --message "..." --query "<你抽出的线索>" --identity <我的名字> --multi-scale` | 一切语义召回：聊过什么、当时怎么想、那个人是谁、那件事的前因后果 |
| 2 | **确定性通道** | `recall.py --timeline N --identity <名字>`（时间轴）／`--literal "词语"`（字面命中）／可加 `--since` `--until` | 结构性时间与精确字面问题：最新一条是哪天、记到哪一天、某个日期之后还有没有、有没有提过某个词 |
| 3 | **md 原文**（例外） | `read` / `grep` `dailynote/*.md` | **仅当用户明确说"读原文 / 看文件 / 把日记打开"** |

**铁律**：

- `dailynote/*.md` 是**源**（ingest 的输入、备份本体、人可读存档），**永远不是检索目标**。检索的索引只有 `recall.db`。
- 用了第 3 条通道，必须在回复里**明说**："这条是按你要求读的原文，不是联想召回"，并说明为什么算法不够用。
- **自检触发点**：一旦发现自己的下一步是 `ls` / `grep` / `read` `~/.midnight/recall/*/dailynote/`，**停手**，改跑第 2 条通道。想不出对应的确定性命令时，退回第 1 条并如实说"具体日期我记不清"——**编造不如承认**。
- 三条通道共享同一套约束：`--identity` 锁区（禁止跨 agent）、`[回忆]` 输出格式、去重与 `--budget` 预算。
- 每次 CLI 检索都会留一行痕（`<agent>/retrieval_ledger.jsonl`）：`prep.py`、`recall.py --query`、`--timeline`、`--literal` 全覆盖。用户可用 `recall.py --audit 10 --identity <名字>` 反查这一轮到底查没查——**不要试图绕过它，也不要用脚本伪造它**。

## 查询派生协议（"自主剖析关键词"怎么做）

召回质量的大头不在算法，在 **query**：

1. **从上下文抽 2–5 个名词性线索**：人（刘晓平、张娜）、事（备课模块、头发检查）、术语（盒子模型、中立不追究）、地点/班级（2501 班）。不要抽"今天 / 压力 / 帮我 / 那个"这类泛词。
2. **带上对象 anchor**：当前对话的主角（如 `赖老师`、某个学生名）必须进 query——对象标签规约要在检索侧生效，靠的就是这个。
3. **拼成空格分隔的字符串**传给 `--query`，并加 `--multi-scale`：整句/关键词/短语三尺度各自感应标签种子，藏在句子角落的线索也能成为种子。
4. **不要把用户原话直接当 query**：寒暄、指代、语气词会稀释向量，把最相关的那条压下去。
5. **允许迭代一次**：先用粗线索召回，再从结果里的标签拼第二轮 query（通常一轮就够，别无限自我联想）。

## 触发条件

当用户表达以下意图时，你应当使用本 skill。**你不需要等用户主动要求回忆——每次回复前，先查一下记忆，看看当前话题有没有相关历史。**

| 触发词/情境 | 操作 |
|---|---|
| **每次回复用户前**（默认行为） | 运行 `prep.py --message "用户原话" --identity <我的名字>`，一条命令完成门控+召回+去重+预算控制，直接把 `[回忆]` 文本块注入回复开头 |
| "记住" / "记一下" / "帮我记住" | 写一份日记文件（见"写日记协议"） |
| "还记得吗" / "你记得" / "帮我回忆" | 运行 `prep.py`（触发词命中必召回） |
| 新会话开始 | 运行 `prep.py` 带时间连续性，自动补最近记忆 |
| 用户说"我上次说" / "之前提到" | 运行 `prep.py` 做联想召回 |
| "最新一条是哪天" / "记到哪一天" / "某天之后还有吗" | 运行 `recall.py --timeline N --identity <名字>`（可加 `--since/--until`）——**不要 ls/grep dailynote** |
| "有没有提过 X" / "我说过某句话没" | 运行 `recall.py --literal "X" --identity <名字>`（通配符按字面处理） |
| 用户要核对"你到底查没查记忆" | 运行 `recall.py --audit 10 --identity <名字>` |
| 沉默一段时间后用户发消息 | 先运行 `prep.py` 再回复 |

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
- `created`：ISO 格式时间戳（精确到秒）。**必须是真实时间，从用户消息末尾的当前时间提取，严禁臆造或猜测**——召回用时间加权，"最近记忆优先"，捏造时间会污染排序。
- `importance`：重要性（high/medium/low），影响召回权重。high=1.5倍，medium=1.0倍，low=0.5倍
- `tags`：标签数组，用逗号分隔。**标签是联想的关键**——同一次日记中出现的标签会在共现矩阵中连线，未来任何一个标签被激活，关联标签的内容也会被召回。所以标签要准确（有区分度）、成体系（有覆盖度）、能连联想（多为名词性话题，少用"今天""压力"这类泛词）。

**硬性写日记规则（必须遵守）**：

1. **一事一记**：一条日记只记**一个**核心事件/主题。话题讨论、规则设定、知识学习必须**拆成独立日记**，严禁混写。混写会让向量切成"语义糊"，召回精度下降。
2. **时间取真**：`created` 用真实时间；正文首行可标注时段（如 `[14:30]。下午。`），但权威时间戳以 `created` 为准。
3. **Tag 必填**：标签必须写在 **frontmatter 的 `tags`** 里（见"字段说明"）。**不要把 `Tag:` 写进正文**——入库只从 frontmatter 提取 `tags`，正文按纯文本切块，正文里的 `Tag:` 行不会被解析成标签，会导致标签丢失、联想网络断裂。
4. **信息密度**：记录有保留价值的核心信息，避免琐碎闲聊；能从对话/文件重新推导的细节不写（学习到的**泛化规则/经验/洞察**比单条事实更有长期价值）。

**对象标签规约（V2）**：Midnight 只维护**一个记忆库**（单 agent 单库）。每个遇到的人/组织是一个"对象"——对象不是一个独立库，而是一组 anchor tag：凡是关于对象 X 的日记，`tags` 里必须带上 `X`（如 `阿散`）。对象与对象、对象与话题靠共现网自然缠绕，无需建子目录或分库。
- 正文：纯文本，记录核心事件、关键信息、情感状态。

**正文结构模板（按日记属性择一）**：

**知识类日记**（学习到新知识/方法时）按结构化字段写，让 embedding 语义纯净、可检索：
```
核心概念：一句话定义它是什么。
简明释义：用通俗语言解释内涵与边界。
关键原理：它如何工作、背后的逻辑链条。
应用场景：能用在哪儿，给具体例子。
关联节点：与哪些知识点相关（构建知识图谱的关键）。
反思与洞察：独到思考或我的判断。
信源/出处：来源，方便溯源。
```
**事件类日记**（发生了什么时）必须包含"事件理解层"，而非只记流水账：
```
发生了什么：时间线/经过、参与方、关键动作。
关键信息：核心事实、数据、决策。
事件的意义与影响：这件事对谁/对后续意味着什么（Why it matters）。
得与失 / 经验教训：成功的、踩坑的、值得复用的。
情绪与状态：我当时/当下的感受。
```

**写日记的时机**：
- 用户明确要求"记住"时
- 聊天中产生了有价值的信息（重要偏好、个人经历、计划、关键决策、学习收获等）
- 注意：**不需要每次对话都写**，只在真正有保留价值的内容出现时才写。避免写琐碎的日常闲聊，保持日记的"信息密度"——精炼、聚焦核心。
- **写入时机**：日记放在**回复末尾统一记录**，完成所有交互和思考后再写；不要在对话中途或消息开头穿插。每日原则上主动记一篇；确有重大事件需追加时，先向用户请示。

## 身份绑定（强制前置，V3）

**每次会话开工前，AI 必须先确定"我是谁"，然后全会话的写/查都显式绑到自己的记忆区。** 这是隔离墙的第一道守卫：

1. **声明身份**：会话开始时识别本 AI 的角色名（如 `qinglan`=主助理、`mira`=社交管家）。
2. **开户（可选）**：若这是一个新智能体，先 `python recall.py --register '<身份描述>' --identity <名字>` 立身份、建记忆区。
3. **写日记用 `--agent`**：`python ingest.py --agent <我的名字> <日记路径>`（会自动开户）。
4. **召回用 `--identity <我的名字>`**：`python recall.py --query "..." --identity <我的名字> --k 10`（也会自动开户）。
5. **`--auto` 只作兜底**：仅当"我这个会话确实不知道该查哪个区"时才用；一旦身份已知就禁用 auto，**绝不让语义猜库戳破记忆隔离墙**。

> **身份即开户**：只要显式给出 `--identity/--agent/--register <名字>`，recall 就会自动为该智能体建目录 + agent.json，
> 立即出现在 `list_agents()` 中——无需先写过日记。`default` 是兜底槽位，不会生成身份文件。

> 原理（第一性）：身份是会话持有者（上层 AI）声明的事实，不是该由 embedding 去猜的东西。
> `--identity` 让召回永远落在自己区；只有从未声明身份时，auto 的字面锚定兜底才接管。

## 召回调用

**推荐：回复前跑一条 `prep.py`**（可移植核心，门控+召回+去重+预算一步到位）：

```bash
# 回复前准备记忆：命中触发词/实质消息才召回，输出可直接注入的 [回忆] 文本块
python prep.py --message "用户原话" --identity qinglan --budget 2000

# AI 已判断出要查的语义时，显式传 --query（优先于原话，保留 AI 深层理解）
python prep.py --message "用户原话" --query "焦虑 睡眠" --identity qinglan

# 高级开关：多尺度线索提取 / MMR 多样性重排（默认关闭）
python prep.py --message "..." --identity qinglan --multi-scale --mmr 0.5
```

`prep.py` 被门控挡下（纯寒暄/短消息且无触发词）时不打印任何内容——据此跳过注入即可。

**确定性通道（问日期/问"有没有提过"时用，不需要 embedding、不读 md）**：

```bash
# 时间轴：最近 3 篇，按 diary_date 倒序（file 级去重，多块正文按块序拼回）
python recall.py --timeline 3 --identity qinglan

# 时间区间（闭区间，可与 --timeline / --literal 组合）
python recall.py --timeline 10 --since 2026-09-17 --until 2026-09-22 --identity qinglan

# 字面命中：正文包含该词（% 和 _ 按字面处理，不当通配符）
python recall.py --literal "中立不追究" --identity qinglan
```

**留痕审计**（反查"这一轮到底走没走算法"）：

```bash
python recall.py --audit 10 --identity qinglan
# → 2026-10-21T16:47:05  channel=timeline  hits=3  query='最近 3 篇'  ids=770,726,796
```

两条确定性通道都**必须显式带 `--identity/--agent`**（缺了直接退出码 2），因为它们回答的是"我的记忆"，静默落到 env/default 库会串号。

## 拉取式沉淀（harvest）

**手写日记是主动渠道，本渠道只做补充。** AI Coding 工具（如 Trae）会把会话摘要自动落盘到磁盘，但不会主动喂给 recall（无生命周期 hook）。`harvest.py` 定时/手动扫盘，把这些摘要的**精华**（intent/outcome/learned）转换成遵守日记协议的 `.md` 并入库，让联想召回能命中"手写没记、但工具记了"的基础设施决策与踩坑。

```bash
# 干跑：只预览生成的日记样例，不写任何盘
python harvest.py --agent qinglan --project TeacherPipeLine --dry-run

# 增量导入：水位线去重，重跑只补新增
python harvest.py --agent qinglan --project TeacherPipeLine
```

- **作用域控制**：`--project <子串>` 只取匹配项目的摘要，避免跨域（如自媒体/爬虫）记忆污染本智能体的标签共现网。
- **拉取式 vs 推送式**：工具不留 hook 就拉它的落盘文件；对方无需配合。新增工具只写一个薄适配器（回答"文件在哪、怎么解析"），转换内核不动。
- **权重让位手写**：拉取日记 `importance: low`，召回天然排在手写（medium/high）之后，只在手写未覆盖时补位。
- **幂等三重保险**：确定性文件名 + `message_id` 水位线（`<agent>/harvest_state.json`）+ ingest 的 checksum。

底层仍可直接用 `recall.py` 做联想召回：

```bash
# 最基本的召回（强烈建议带身份：显式指定记忆区）
python recall.py --identity qinglan --query "用户的问题" --k 10

# 不带身份时的联想召回（无身份 → 可用 --auto 兜底，但可能跨区）
python recall.py --query "用户的问题" --k 10

# 带联想和时间加权的召回
python recall.py --identity qinglan --query "用户的问题" --k 10 --tag-weight 0.5 --time-ratio 0.3 --truncate 0.5
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
│   ├── recall.py         # 联想召回（向量 + 标签脉冲 + 时间 + 深联想扩增）+ 确定性通道（时间轴/字面）
│   ├── ledger.py         # 检索留痕（jsonl 追加 / 读取 / 格式化，旁路不拖累检索）
│   ├── prep.py           # 可移植核心：回复前记忆准备（门控→召回→去重→MMR→预算→文本）
│   ├── tag_network.py    # 标签方向边 + 脉冲传播（压缩/枢纽校正/预算/Core-Ghost）
│   ├── self_model.py     # self 锚生成/读取/演化（定海锚 + 可动层）
│   ├── evolution.py      # 自进化（可动层覆写 + 演化日志 + 久不用衰减）
│   ├── session_start.py  # 首轮上下文轻编译（身份摘要 ≤200 字）
│   ├── harvest.py        # 拉取式沉淀（AI 工具落盘摘要 → 日记，补充渠道）
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