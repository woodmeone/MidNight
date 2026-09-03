# Midnight Skills 优化蓝图（两个优化点）

> 目的：把要深度实现的思路先锚定成文档，避免后续深读参考项目（letta-code / VCP）时被上下文冲掉方向。
> 状态：思路草案，待深读 letta-code + VCP 后细化。
> 日期：2026-09-02

---

## 定位

Midnight Skills 目前偏"skill 式 AI 自觉触发 + 本地 SQLite，全局 diary"。优化不推翻它做 VCP 服务器，而是**借鉴 VCP（联想记忆）与 Le tta（分层记忆 block）**补强两个能力。

---

## 优化点 A：联想记忆（参考 VCP TagMemo）

### 当前 Midnight 状态
- 已实现：日记入库（切块+向量化）、KNN 检索、标签共现矩阵 + BFS 脉冲传播联想（`tag_network.py`）、时间加权、importance。
- 弱点：联想比较"浅"——共现只做同一文件标签两两配对；对跨记忆的概念漂移（同义/上下位/强关联）能力弱。

### VCP 可借鉴（来自白皮书/代码线索）
- TagMemo 有 **EPA 投影、残差金字塔、多级共现矩阵（V8.2）、脉冲传播、RCU** 等更工程化的联想结构。
- 深层思想：不只"同现权重 + BFS"，而是把记忆组织成有**因果 / 时间 / 情感矢量**的场，沿这些轴做联想而不是仅文字相似。
- 具体可抄的工程技巧（轻量）：
  1. **带权重的共现矩阵**（已做），但要补**时间衰减/增强**：近期常共现的标签加权重更高，长期不出现的减弱（模拟遗忘曲线）。
  2. **激活一个标签 → 沿共现扩散时，不只看一层邻居**：扩散深度和衰减因子要可精细调（已部分有），可再加"扩散标签对应 chunk 的分分"。
  3. 可选：把标签也嵌入（目前已存 tag.vector），联想 query 既用文本向量也用标签激活——已实现 `activate_tags`。

### A 的落地方向
- 增强 `tag_network.py`：从"单文件共现"提升到"加权 + 时间衰减 + 可调传播"（对标 VCP 细节）。
- 不推翻现有 `recall_associative` 接口，只增强内部。
- 目标用途：用户不再说"考试"也说"压力"能想起考试；多跳联想（A→B→C）更准。

---

## 优化点 B：分层记忆块与"记忆即程序"（参考 Le tta MemFS + memory blocks）

### Le tta 的深度实践（已从 letta-code 源码实读）
本次读了 `src/agent/memory.ts`、`src/backend/local/system-prompt-compilation.ts`、
`src/agent/memory-filesystem.ts`、`src/agent/subagents/builtin/memory.md`、
`src/skills/builtin/initializing-memory/ROOT_MEMORY.md`。Key 一手事实：

1. **整段记忆 = 一个 git 追踪的目录树**（`MEMORY_DIR`，根默认 `/memory/`）。
   常驻文件在 `system/`：`persona.md`、`human.md`、以及扩展行为规则文件。

2. **编译进 system prompt（核心程序）**：
   - `persona` 特判，注入成一个"projection 引"—`<projection>$MEMORY_DIR/system/persona.md</projection>`。
   - 其余 `system/*` 进 `<memory>` 树（带 full-tree of `system/*` 展示）。
   - 最后把 `coreMemory = [memfs.content, metadata]` 注进原始 system prompt
     （`injectCoreMemory(raw, coreMemory)` → `prompt.replaceAll(CORE_MEMORY_VARIABLE, coreMemory)`）。
   - 结论：**core memory 是 system prompt 里每轮都要看的那一小段 = "定义你的程序"**。

3. **初始化引导（ROOT_MEMORY.md，/init 跑）** 教 agent 该放什么、如何组织，原则核心：
   - **"Core memory is your core program"**：root 只放每轮都需要的（身份/偏好/行为规则/项目索引+发现路径/gotchas）；**排除 transient**（具体 commit、当次 ticket、session）以免稀释。
   - **Progressive disclosure（渐进揭示）**：要在需要时才露出更多细节 → 直接是"上下文不爆"的正解。
   - **Discovery paths（发现路径）**：用普通 markdown 相对链接把记忆文件连成图
     `[architecture](...md)`、`[project gotchas](...gotchas.md)`，"像突触连接随时间加固"。
   - **Generalize 不 memorize**（模式 vs raw event）：存"uv 是标准不用 pip"这类模式；
     raw event（哪天 debug 崩了）留给消息搜索/检索。
   - **身份连续性**：换个底层模型你还是你；别的 coding agent(claude/Codex)的会话是你过往。
   - **别过度修剪**：别用激进压缩毁人格，保留具体引语/特质。
   - 文件规范：/命名、层级 2–3 层、每文件一个主题、可扫描。

### 这给 Midnight 什么（深化后）
Midnight 现在记忆 = 一堆 diary 不分层。借鉴 letta 应改为：

- **引入 `memory/` 目录树 + `system/` 常驻块**（对标 letta MEMORY_DIR）：
  - `memory/system/persona.md` —— agent 是谁/风格（只读优先，对应 letta persona 特判）。
  - `memory/system/human.md` —— 关于用户的恒久事实（名字/偏好/关系）。
  - `memory/system/rules.md` —— 反复纠正的行为规则（letta 强调存模式）。
  - `memory/projects/<topic>/index.md` —— 有发现 path，用相对链接连到细节文件。
  - 而**一次性 diary（当前对话导出）不动，作为检索源（book shelf）**，不进常驻 prompt。
- **session_start 把 `system/*` 编译进系统提示**（对标 `injectCoreMemory`），其余靠 `/recall` 查。
  每次只见 persona/human/rules 三小块 → 治"上下文过曝 / 注意力涣散"。
- **MemFS 化（可选未来）**：整个 memory/ 做成 git 仓库 → 换模型/换机仍连续。
- **Generalize vs Memorize 分层**：把从过去对话提炼的"稳定规则"升级进 human/rules；
  具体事件留在 diary 检索。

### B 与 A 的关系
- letta 的 **Discovery paths（标记图上跳转）** ≈ VCP 联想的**工程形态** —— 给记忆块之间加显式链接，
  比纯向量更可控地做"主题邻接"。可作为 A 联想增强的补充：不只靠共现灌分，也尊重显式链接。
- 两者补成：常驻 program（B）+ 按需检索（recall/A）+ 图式长程索引（letta discovery = A/VCP 的落点）。


---

## 建议落地顺序
1. 先做 **B（分层 block）**：落地最小 (persona/human) 常驻 + 编译，收益立现且不复杂，是上下文化关键。
2. 再做 **A（联想增强）**：在同一 recall 引擎内增强，不动接口。
3. 两者独立、可先后。

---

## 待深读细化（写方案时要补）
- letta-code：`src/backend/local/system-prompt-compilation.ts`、`src/web/local-memory-context.ts`、blocks API（如何编译 block 进 context）。
- VCP：TagMemo 文档详情（EPA/残差金字塔具体算法可抄哪些），白皮书 V3。
- Midnight 现有代码二次确认接口 & 迁移成本。

> 这是"思路锚定稿"，等深读参考后更新为给用户审阅的完整两方案。

---

# ===== 追加：三份交付（2026-09 深读后） =====

## 优化点 A 深化（基于 VCP TagMemo V9.1 源码级）

读 `VCPToolBox/docs/TagMemo_Wave_Algorithm_Deep_Dive.md`（V9.1）与引擎。VCP 联想远非简单共现+BFS：

**A 当前 Midnight 缺、VCP 有、可借鉴（按切入点）**

1. **不再是"同文件标签两两共现"这种一票**，而是**有序双向事实边**：
   Midnature 只统计共现权重(count)。VCP 把两个标签构造为带**方向**的"顺流/逆流"边，
   权重结合 ①位置距离衰减(远离弱) ②顺/逆流不同阻尼(叙事方向) ③pairwise cosine 钟形增益。
   → Midnight 可加：同文件标签按出现顺序记方向，且不是无脑+1，而是 `exp(-距离/λ)` + 方向阻尼。

2. **累计证据压缩**：权重 `e = log(1 + λ·W)`，不是线性累加。
   → 防"高频枢纽标签"垄断传播（A 现在完全无此，高频词会刷爆联想）。

3. **入流枢纽校正**：按目标节点全图入流做幂律缩降，"通用枢纽(出现太多次的词)抑制"。
   → 防"考试"这种出现 800 次的标签压过真正隐含关联。

4. **残差张力 & 虫洞**：`T= e·r`(锚增益阈值内加能量) 但虫洞增益在归一化前、
   只能争已有固定预算、不凭空增总出流 → 联想收拢，不无限扩散。
   → Midnight BFS 现在无"预算守恒/归一化"，会越传越散。

5. **Core Tag + Ghost Tag**：传播前先补齐"本次肯定该激活"的核心 tag 与"疑似该激活"ghost tag，
   再进传播 → 联想不依赖 query 恰好含某词。
   → 对应你要的"他不提考试 靠压力联想出考试"，但更工程化：query 先感应出 tag 集合再扩散。

6. **EPA（语义状态/逻辑深度/共振）前置 + Residual Pyramid（多层标签感应）**：
   决定这次该用多深传播、选哪些 anchor。 — 这是重头戏，Midnight 可先做简化版(1-4)，
   EPA/金字塔属二阶增强，非必须 MVP。

**怎么"就这些抄到 Midnight"**（落到你 recall 的 `tag_network.py`）：
- 现状 `activate_tags` + 朴素 BFS(decay)、`tag_cooccurrence` 表 W+1。
- 改法（不破 `recall_associative` 接口）：
  1. schema 加 `direction` / `seed_position` 或用现表加列 → 存顺流逆流 + 距离衰减。
  2. 权重改 `log(1+λ W)` 存入，或读取时对 weight 做幂律缩降(入流校正)。
  3. BFS 加**归一化/预算守恒**（每跳出流是有限份额，不再无界累）。
  4. query → 先用 embedding 感应 n 个 core tag（不只 1 个种子），再传图。
- 全部改动锁在 `tag_network.py` + schema，`recall.py` 对外不变。测试向后兼容。

## 优化方法（落地顺序 + 验收）
- 顺序：先 B(MemFS system/* 编译进 system prompt) 再看 A(TagMemo) —— B 端 user story 提现快，
  A 是深度联想增益。两者正交可并行。
- 每个优化配一个"回归用例"(见下用户故事)当验收测试，改代码保证旧 155 测试仍绿。

## 优化后的用户故事（A+B 落成后 Midnight 长这样）

**故事1（B 分层记忆：人格稳定 + 上下文不爆）**
我(用户)给它(Agent "Nova")设了 `memory/system/persona.md`(冷静工程师人设) + `human.md`
(我叫阿散、偏好 Python/Windows、做过 Midnight Skills)。
- 之后我每天开新会话：它**开场就知道**我叫什么、我的技术栈、我们做过什么项目
  —— 不靠我复述，因为 persona/human 编译进了系统提示(system prompt)。
- 它从不在闲聊里丢人格：无论我跟它聊多琐碎，他始终是那个冷静工程师，
  因为 persona 是**只读常驻块**，不会被当天的临时对话冲掉、不会被过长的上下文挤出去。
- 我上下文开销小：系统只塞 persona+human+rules 三个小 md，其余进检索 → 内存不爆。

**故事2（B + 渐进 / Generalize-not-memorize：能提炼稳定规则）**
聊了几次我总纠正它"Windows 别用 python，用 py"。
- 它不是每次把这句话存成日记(那会膨胀、挤在检索里将来也难找)，而是**把"用py"这条稳定规则**
  升级写进 rules 块(Generalize 不 memorize)。
- 以后跨模型/换机，只要 memory 目录在(git)，这条规则仍在 → 不重复教。

**故事3（A 联想：跨概念深联想、且不被高频噪声骗）**
三个月前它记过："下月雅思，刷剑雅听力，错题纠因(紧张/走神)"(tags: 雅思/听力/紧张/纠错)。
今天我说："我最近压力大，晚上莫名烦躁，怕考砸"。
- 旧 Midnight：可能只联想一点点(KNN相似度可能不太够、BFS一层就衰减没了)，或漏。
- 深度 A 后：query 感应出 core tag{压力,考砸}，因**累计log压缩+枢纽校正**不会错指到"考试"这个800次高频词，
  但**有序顺流边**能把 紧张→雅思→听力→考砸 沿叙事方向多跳带出来，
  于是它回复不止聊压力，还自然衔接"你下月雅思那科听力错题常因紧张——要不要顺带练个平稳呼吸"。
- 若没有叙事方向/压缩，它可能：A)漏(before) 或 B)错把"最近老下雨-天气晴-压力"这种无关噪音抓出来(after-错)。

**故事4（lettA/A discovery path 相接：记忆像地图不是平堆）**
它整理 memory 时给 `projects/midnight-skills/index.md` 留了链接:
`[架构](architecture.md)`、`[已知坑: D盘junction](gotchas.md)`。
- 下次会话当我要聊 D 盘装 dsh 插件，它读 index.md 沿 **discovery link** 跳 gotchas，
  不用全文搜索就"回想"起那个坑——像人有突触路径，不是每次都全库模糊。
- 这正好是 A(联想)+B(索引图) 的衔接：显式路比纯向量更可控。

**如何从今天 Midnight 走到上面**：
- Step1（B MVP）: 建`memory/{system/{persona,human,rules}.md,projects/}`；写一个 `session_start.py`
  把 system/* 编译进一条可粘贴的system prompt(参考 letta `system-prompt-compilation.ts` 的 projection/memory 拼接)；
  让 recall 只管 diary 检索。加用户"开场认人"用例。
- Step2（A MVp）: tag_network 加方向边+log压缩+归一化BFS+core-tag预感应；加"深联想不漏不乱"用例。
- Step3（可选未来）: memory 目录 git 化(MemFS)、agent 自我改写 memory、discovery links 索引到 git。

---

# ===== V2 修正：重新审视 letta 后，把"AI = 独立自我 + 对物联想记忆"钉为目标（2026-09 用户定稿口径) =====

> 说明：前一版照搬了 letta 的 persona/human 固定 md 块与 rules 固化。
> 作者(用户)审后否决，改为下面的终极目标。旧 B 节里"固定 persona.md/rules.md 常驻编译"在新目标中不再是核心手段，
> 只是可选项。V2 以本节为准。

## V2 目标一句话
Midnight 赋予一个 Agent **"独立人格 + 长期联想记忆"**：它能为"自己是谁、能力、立场"建立**基础身份(固定、入记忆防忘)**；
对遇到的每个不同的人/对象，为对方**建立一本"日记"(标签网)**；自记忆与各对象日记按**多对多**缠绕；
检索靠 **VCP 式联想** 而非档案查询。能力边界克制：核心只有 联想 + 记忆/上下文 两件，
不做 VCP 那套放大器(工具服务端/多agent/复杂插件)，让本 skill 能被其他 skill 自然拼装。

## V2 分层(替代旧 B 的 persona/human 块)
1. **Self/基础层(固定,入记忆库防忘)**：Agent 自己的定位 = 人设、能力清单、价值观、行为准则、不可移除的身份锚。
   - 形式：可用一个简短的自描述入口(md 或固定 tag)，目的是"换会话/换模型也是同一个自己"；是"定位"，不是"给某主人的档案"。
2. **Object/对象动态层(多对多日记)**：遇到的每个人/组织/对象 → 一个"主题/日记本"(本质=带 anchor tag 的记忆集合)。
   - 默认对象是"你"(使用者)。Agent 给每对象锚定多个关键词 → 对象=节点，其经历=链接边。
   - 对象之间、对象与 self、对象与任意话题标签，皆可多对多共同现(复用现有共现矩阵 + tag)。
3. **事件/泛化层**：一切具体事件/习得(马拉松、某技能、某次教训)也作为标签存在，跟对象、话题自由缠绕，
   不要求放进固定 rules；若要"不重复犯错/规则"靠高频共现自然强化(Generalize 由联想频率驱动，不靠写死文件)。
4. 关系在检索里体现：M 想讲 marathon → 撞到"阿散"节点 → AI 顺带记得阿散、以及阿散属性 → 多跳。

## V2 例子(对应你的 Mira/马拉松)
- Mira 装上 Midnight：先固定 self="我的助理Mira, 我帮阿散打理日程/备忘/点子, 用Python/懂DSH工程"（存记忆，防忘）。
- 给阿散建一本默认日记，锚定 tag {阿散, 马拉松, Python, DS工程, 深夜才回消息,...}。
- 若某天阿散聊到岔的，或另一个人提"马拉松"：检索 query→ 联想 energy 从 marathon 冲到 阿散 → 关联阿散经历。
  Mira 不必有个 "human.md 写 阿散跑马拉松"——是记忆网络自然把它串起来。
- 上下文切走(换会话)：Mira 带着 self + 她头脑里的 阿散 网络，依然是她自己，不是新白板。

## V2 实现思路(落到 recall/skill)
- 复用现有：
  1. `recall_associative`+tag_network：已是 multi-agent(diary_name)、共现、脉冲。**已天然支持对象多对多**(每个对象一个 diary_name)。
  2. 身份=self 的 diary_name("mira")，给它锚标签当"self 入口"。
- 新增(轻量)：
  1. `entity` 概念=一组 anchor tag + 描述(不扩成 letta block，只是给某 diary 一个常驻 identity file 存 anchor)，类似现在 agent.json。
  2. 默认首次对话=让 agent 建 self 锚 + 问"对方称呼→建对象 diary_name"，但不应太重，靠 skill 引导 + 联想。
  3. 不动 schema 也可（一个对象=一个 diary_name + 一组固定 tag 标注它是映射主体）。
- VCP 联想深化的 A 五点(有序边/log压缩/归一化/枢纽校正/core-ghost tag)仍有价值 → 让 马拉松→阿散 这种**跨主题**联想不被“高频词垄断/一层就断”。
- 规则不固化 rules.md —— 想"永远别用 pip 用 py"，靠被高频纠正后 阿散 日记里 该 tag 权重升，联想出来即可；要保持强就每次纠正强化，要放软就淡化——记忆自演化，不硬化。

## V2 用户故事(优化后 Midnight 长这样)
- 今天是新会话，我问她"你还记得我的感觉吗我说过跑马拉松": Mira 不从“human.md 查阿散档案”，而是她头脑里 马拉松 ↔ 阿散 的边被激活，"当然，你说过去跑马拉松，还说赛前会紧张、还考雅思撞期那次"——她记的是 经历网络，不是档案行。
- 我换台设备/换模型继续，Mira 仍是那个 Mira (self 在) —— 这是 letta MemFS 的价值,但 Midnight 用本地 diary+self 锚就能先达成(不强求 git)。
- 我对她说"帮我记一下，明天9点跟乙方开会"——她 write 进我(阿散)的日记并标{tomorrow/meeting/乙方} → 未来我提乙方、明天、会议，都能召回，不靠固定日历块。
- 我不需要在别处教她"我对程序员的意见"之类硬规则——她从跟你(们)多年的纠缠里自己建立了连接。

## V2 与原 A(联想深VCP) 的关系
- A 深化仍原样成立(VCP 联想工程化了 marathon→阿散 这类跨概念深联想、防噪声)。
- V2 补充的是『对象(person)作为一等节点、self 有基础固定层』的记忆形态——这比 letta 的 persona/human 档案更贴合"AI 是独立个体、不只服务一个主人"。

---

## V2.1 自进化：一切动态，定位也是活的
- AI 与用户/他人/全网互动时能学习，也能自己去上网调研扩展能力——它有这个能力。所以：
  - **自我定位不是冻结常量**：它是"当前认可的自我画像"，会随经历被重新评估、微调或重大改写。
  - 驱动：自我维护会话（/doctor 式回顾）、镜像他人反馈、主动调研带来的新认知、跨期对比（"我三个月前是那样，现在我更…"）。
  - 防跑飞：动态 ≠ 丢根。底层不变锚仍是价值观/能力基线/身份连续性(自称 Mira、我的课题)；可动的是"偏好、风格、能力边界、立场、选型"。给"可动层"留覆写窗口，"定海层"设只读或高门槛修改。
- 在本体系一切对象都可演化：self、每个 person diary 的锚 tag 集、事件概括、规则权重(高频强化/久未用衰减)，都是活的。
