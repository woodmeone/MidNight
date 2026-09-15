# Midnight Skills 优化交接 Spec

> 目的：给"下一个 AI 会话"的交接规范。读完本文件即可从 to-spec/tickets 继续实现，无需重看讨论过程。
> 参考母档：`docs/optimization-blueprint.md`（讨论稿，含全部来龙去脉 + 一手源码依据）。
> 结论优先级：本 Spec 为准。若与 blueprint 冲突，以本 Spec 的"V2 + 自进化"定稿口径为准。
> 日期：2026-09  Version: handoff-1

---

## 1. Problem Statement（用户痛点）

Midnight Skills（recall/core/pulse/compass）当前是"skill 式 AI 自觉触发 + 本地 SQLite 平铺日记"。
与目标形态相比，它缺：
- AI 没有"自我模型"：只是"帮你检索日记的过滤网"，不是"有独立人格、会服务多人、会自进化的个体"。
- 记忆平铺无结构：一个 agent 的 diary 全糊在一层，无法区分"my self / 某个人(person diary) / 泛化规则"，无法多对多关联。
- 联想太浅：共现+BFS，缺 VCP 的方向性/log压缩/枢纽校正/归一化；跨概念(马拉松→阿散)联想易断或跑偏。
- 规则写死就硬、靠持续检索常驻就塞上下文——无"渐进、按需、演化"的中间态。
背景：用户对标两个参考项目——**VCP**(TagMemo V9.1 联想算法)与 **Le tta/letta-code**(MemFS 记忆文件树 + system-prompt 编译 + agent 自我改写)，并反复确认"要的是**AI 独立自我 + 对物联想记忆**，非 letta 的 persona/human 档案(P2) 那套"。

---

## 2. Solution（目标形态，按 V2 定稿）

Midnight 把一个普通 Agent 提升为一个**有独立自我、会对每个遇到的人建"对象日记"、靠联想而非档案检索跨会话跨模型延续、并能自我演化调整定位**的长期个体。

三层记忆结构（替代旧 B 节 persona/human 常驻块 vs 检索的二分）：
1. **Self 层（基础，固定入记忆防忘，但可动态演化）**：Agent 的定位 = 人设/能力/价值观/身份连续性。
2. **Object 层（动态，一个对象=一本 diary，含 anchor tag）**：默认对象"使用者"，可多个他人/组织。对象与对象、对象与话题、对象与 self **多对多**缠绕（复用共现网）。
3. **Event/泛化层（动态）**：具体事件与"从经历提炼的稳定模式"。规则不固化文件，靠**高频纠正强化 tag 权重 / 长期不用自然衰减**（Generalize-not-memorize by 记忆演化，不靠 rules.md）。

示例（Mira/阿散/马拉松）：Mira 建 self="助理Mira, 帮阿散跑腿/分析, 用Python/懂DSH"；给阿散 diary 锚 tag{阿散,马拉松,Python,深夜,...}。新会话问"我提过跑马拉松吗"→ 联想 energy 马拉松↔阿散 被激活 → 记得"你说过，赛前紧张还跟雅思撞期"。换模型/换机仍是那个 Mira。self 与所有 person 都**活**：Mira 会在交互中学、上网调研学，自我画像随之评估/改写（底层定海锚：身份/价值基线保留，可动层=偏好/风格/能力边界可调）。

---

## 3. User Stories（扩展版，含 A/B/自进化）

as an <actor>, I want <feature>, so that <benefit>

1. As 使用者(阿散), I want Mira 开场就知道我叫什么、我做过哪些项目（不靠我复述）, so that 新会话无缝。
2. As 使用者, I want Mira 有稳定独立人格（工程师/助理自画像), so that 换个会话/模型她还是同一个她,而不是白板。
3. As 使用者, 我随口提"跑马拉松", I want Mira 想起我(阿散)和我相关的事(紧张/雅思撞期), even 这句没出现"阿散"——对象作为一等节点,跨会话被联想。
4. As 使用者, 我反复纠正她"Windows 用 py 别用 python", I want 她记住且不每个会话重教, 靠高频强化该 tag 而非写死 rules.md。
5. As 使用者, 让 Mira 主动学习、上网调研, I want 她能更新自己的定位/能力/立场(可动层), so that 她随我成长也成长, 且不会跑飞(底而定海锚保留)。
6. As 使用者, 我与不同人分别对话, I want 每人有独立 diary（多对多、互不混淆), so that 与甲的联想不串到乙。
7. As 开发者, the 核心能力克制为 联想+记忆/上下文两件, I want 本 skill 可直接拼装进其他 skill, so that 生态可叠加。
8. As 使用者, 上下文不因记忆膨胀而塞爆(keep context small), so that 注意力不涣散。

---

## 4. Implementation Decisions（按 V2 落 recall，已定/待实现分两类）

A. **联想深(引擎层，参考 VCP TagMemo V9.1)**，锁 `tag_network.py`/schema，不动 `recall_associative` 接口。
   实现要点：
   1. 有序双向边：同文件 tag 按出现序建 顺流/逆流，权重=序位势能·exp(-位置距离/λ)·方向阻尼(顺流>逆流, guard 限制逆流比例)。
   2. 累计证据压缩：边权存 `e=log(1+λ*W)`；防高频标签垄断。
   3. 入流枢纽校正：按目标节点全图幂律缩降，抑制泛泛枢纽词。
   4. 归一化/预算守恒传播：节点出流受限，虫洞增益只争既定预算，不无限累。
   5. Core/Ghost tag 预感应：query 先用 embedding 感应 n 个候选 tag(不只1种子)，补 ghost 后进传播。
   6. 二阶(可选)：EPA 语义状态/Residual Pyramid。
   Notes: EPA/金字塔可不做 MVP；先 1-5。

B. **自我+对象记忆(记忆形态层，替代旧 persona/human 常驻块)**
   现状: recall 已支持 multi-agent(diary_name)+共现+脉冲——**天然支持"一个对象=一个 diary_name"多对多**。
   落地新增，暂不建议 schema 大改：
   1. **self 锚**: 给 default(或某 diary_name, 例"mira")一个轻量 identity 文件（`agent.json` 同类的 `self.md`, anchor tag + 自描述），作"自我入口"，首次运行生成；含"定海锚"与"可动层"标注。
   2. **对象 diary_name 规约**: 每遇新的人建独立 diary(如 `mira/objects/ashan/`)，锚一组 tag 表示主体。默认使用者=ashan。
   3. **skill 引导首次建自我/对象**: /init 或会话首语引导："给自己定位了吗？要我认识你怎么称呼？" 但不可太重。
   4. **规则不固化**: 高频纠正 → 该 person diary 或 self 附近 anchor tag 权重升(天然在 cooccurrence 里); 久不用衰减。
   5. **动态自进化(自省)**: 提供可选 `/evolution` 或 periodic 自省(T° 参考 letta /doctor/sleeptime), 基于新交互/调研/镜像反馈, 评估并覆写 self 的可动层; 定海锚高门槛或只读。
   6. 可选项(后期): 让 memory 目录 git 化(MemFS 式), 支持跨机/跨模型版本追。

C. **上下文编排(session_start, 轻)**
   目的: 保根(small)但仍能取对象。
   - 可选开发一个 `session_start.py`: 把 self 锚(identity 摘要)+本次对象 anchor tag 编译进首轮 system/user 简述(参考 letta `system-prompt-compilation.ts` 的 projection/memory 拼接; 但只注入少量、其余进 /recall)。
   注意区分: 不是 letta persona 全档常驻; 是短的 self 身份摘要 → 其余靠联想。

D. **外键/文件**:
   - scripts 保持可被 MCP/editor skill 调(已做 mcp_server.py / install-skills.sh)。
   - 旧 person "human.md" 概念丢弃(回归"对象=diary+anchor")。

---

## 5. Testing Decisions

- 行为测试(不测内部): 给一个对象日记(ashan/马拉松 tag), 用不含"阿散"的 query("跑马拉松 紧张")联想召回涉阿散 chunk, 视为 pass。
- 深联想回归: "压力大怕考砸" 应经 log压缩+枢纽校正 深联想 雅思(而非被'考试'高频词吞), 断言含雅思。
- 多对多隔离: 甲乙各有 diary, query 甲话题不召回乙。
- self 锚生成: init 无 self 时自动建; 已有 self 幂等不覆盖锚。
- self 演化: 调整可动层后定海锚未变; 可动层 tag 权重随纠正上升; 久不用可降(视实现)。
- 兼容: 全部旧测试(recommend 保留 155 red/green)，recall_associative 接口不变。
  建议先补"对象联想召回"集成用例；再加 self/对象 init 用例; 后加自进化用例(可 mock)。

---

## 6. Out of Scope（一期不做）
- 不做 letta 风格的 persona.md/human.md 常驻全档(被用户否决)。
- 不做 VCP 服务端/插件放大(工具系统/multi-embedding重排/Flow lock etc.)——Midnight 保持 skill 边界。
- 不做 MemFS git 全量(仅作 P2 可选 future)。
- 不做 EPA/Residual Pyramid 复杂算法(作 A-二阶 future)。
- 不做云端 SaaS(仍本地起可) 与 letta 桌面/app。

---

## 7. 面向下一个 AI 的开工建议(顺序)
1. 先读本 Spec + `docs/optimization-blueprint.md`(母档, 尤其 V2/V2.1 节).
2. 走 /grill-with-docs(如需敲 user story), 然后 /to-spec 已可省；直接 .scratch 建 feature → /to-tickets → 一个个 tracer bullet:
   T1: self 锚生成(identity file + init) + 测试。
   T2: 对象规约: "一个对象=diary+anchor 主体", 加对象联想召回集成测(ashan example)。
   T3: A 联想 1-5(方向边/log压缩/枢纽校正/预算/核心ghost) 分步, recall_associative 接口不变。
   T4: skill 引导首建 self+对象("/init" 引导)。
   T5: 可选 session_start.py 上下文简入 + 缩上下文测。
   T6: 自进化(自省可写可动层、定海锚只读) P1 或推后。
3. 每 ticket 记得原有 155 测试仍绿；每步实读 VCP/letta 母档细节。
4. 结束后走 /code-review, commit。

## Further context
- blueprint 里用户故事的马拉松/自进化例可直接当验收用例.
- 参考母档含 一手源码路径(letta-code/src/agent/memory.ts 等、VCP docs/TagMemo_Wave_Algorithm_Deep_Dive.md) 供实现者回溯。
