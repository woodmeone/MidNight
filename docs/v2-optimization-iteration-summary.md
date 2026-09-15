# Midnight 记忆系统 V2 优化迭代总结（feature/v2-self-object-memory vs main）

> 本文档总结 `main`（V1）→ `feature/v2-self-object-memory`（V2）这轮优化的整体迭代过程。
> 它把「优化了什么 → 怎么实现的 → 有什么用 → 怎么用 → 用户故事」整理成一份可复述的说明，
> 供撰写 build-in-public 视频脚本 / 复盘 / 交接复用。
> 相关细节文档见文末「8. 文档索引」。

---

## 0. 一句话总览

V2 把 Midnight 从「只会按标签匹配的记忆脚本」，升级为 **「记得我是谁（三层记忆）＋会联想召回（标签共现网络）＋多智能体物理隔离＋注入侧上下文不炸＋能自进化」** 的通用单机记忆底座。

**规模**：相对 `main`，**+3490 / -108 行，34 个文件**，5 个功能提交，测试 **127 → 157 全绿**。

---

## 1. 背景：为什么做这次迭代（V1 的痛点）

V1 的问题:

- **记忆取向只有"内容标签"**：记住的是琐碎片段，记不住"我是谁 / 我的身份锚"。
- **召回靠关键词**：得说出原词才想得起，不贴合人脑的"联想"。
- **多个智能体『看似隔离』**：日记/库文件会落到根级目录变无主孤儿，自动路由还串区——威胁隐私（恋爱区/教学区互相泄漏）。
- **上下文只是硬截断**：长记忆被拦腰砍到 200 字，丢掉因果；重复内容反复塞进上下文，token 会胀。
- **身份与记忆混在一起**，没有"不可变的锚 + 会进化的可动层"之分。

目标（来自 `OPTIMIZATION-SPEC.md`）：**keep context small**、**记得身份**、**联想而非精配**、**物理隔离**、**少而完整地注入**。

---

## 2. 整体是怎么迭代的（方法论）

这轮不是一次性堆功能，而是按工程化流程推进：

1. **文档先行**：先写 `OPTIMIZATION-SPEC`（规格）、`optimization-blueprint`（蓝图层），把两个优化主线钉死。
2. **拆成可交付单元**：`.scratch/v2-self-object-memory/` 下拆出 spec + 6 张 issue（01 自我锚 → 06 自进化）。
3. **TDD 每张切一片**：先写回归测试（红）→ 实现（绿）→ 全量回归。
4. **对抗式 / 逆向 / 系统思维反复审**：主动想"哪里会翻车"（如截断丢因果、隔离串区、token 爆炸），并用**第一性原理**决定取舍。
5. **临时库验证**：全程在临时 `MIDNIGHT_BASE_DIR` + pytest 临时目录复现，**绝不污染真实 `~/.midnight`**。
6. **分 5 个 commit 逐步合入**，每步都能独立回滚与 review。

---

## 3. 迭代了什么：`feature` vs `main` 全对照

### 3.1 提交路线图

| 提交 | 主题 | 核内容 |
|---|---|---|
| `bf31992` | V2 自我+对象记忆（合入口） | 三层记忆、联想引擎深化、session_start 上下文轻编译、自进化；127 测试 |
| `e88e1ca` | 隔离不彻底修复 | 孤儿数据处理 + auto 路由兜底 + 路径统一；138 测试 |
| `0d78a8c` | 身份优先路由 + 身份即开户 | 隔离墙不靠语义猜库 |
| `ae64f46` | 注入侧上下文控制 | 去重 + 预算收敛 + 去掉 200 字硬截断；CLI `--budget`；157 测试 |
| `5a2892c` | 身份摘要不硬截断 | 最基础信息能有多少给多少；删 MAX_CHARS |

### 3.2 代码/脚本改动对照

| 模块 | V1（main） | V2（feature） | 对应能力 |
|---|---|---|---|
| `self_model.py`（新） | 无 | 定海锚（name/anchor_tags）+ 可动层（persona/capabilities/position）+ 对象 anchor tag | A 三层记忆 |
| `schema.py` | chunks/tags | + `tag_edges` 表（标签共现方向边） | B 联想引擎 |
| `tag_network.py` | 简单共现 | Core/Ghost 预感应、方向边、log压缩、枢纽校正、传播预算守恒 | B 联想引擎 |
| `config.py` | 根级路径 | `get_dailynote_path(agent)`/`get_db_path(agent)` 每 agent 专属 + `ensure_agent` 开户 | C 隔离/开户 |
| `maintenance.py`（新） | 无 | 检测/迁移根级孤儿数据 | C 隔离修复 |
| `recall.py` | 精配召回 + 200 截断 | `recall_by_identity`、身份优先、`dedupe_results`、`fit_to_budget`、CLI `--budget/--register/--identity` | C/D |
| `session_start.py`（新） | 无 | 首轮身份编译；本次去硬截断 | A/F |
| `evolution.py`（新） | 无 | /evolution 可动层覆写 + 久不用衰减 | E 自进化 |
| `SKILL.md` | 旧指引 | 路由表、agent 日记路径、`--budget` 等操作指引 | — |
| 测试 | 旧 | +15 个新测试文件（self/object/identity/routing/inject/evolution/orphans/…） | 全 |

### 3.3 文档产出对照（`main` 无 → feature 新增）

- `docs/OPTIMIZATION-SPEC.md` —— 规格主线
- `docs/optimization-blueprint.md` —— 蓝色图层/实现清单
- `docs/ai-memory-product-report.md` —— 产品角度分析
- `docs/video-script-material.md` —— 视频素材稿
- `docs/server-side-plan.md` —— 未来服务端演进规划
- `.scratch/v2-self-object-memory/` —— spec + 6 张 issue

---

## 4. 每个能力：怎么实现 / 有什么用 / 怎么用

### A. 三层自我 + 对象记忆
- **实现**：`self.md` 作为「定海锚」（不会忘的 name + 锚标签），外加「可动层」（风格/能力/立场）；对象用 anchor tag 挂接。
- **用处**：AI 记住"我是谁"，而非只记住"聊过啥"；身份是记忆的地基。
- **怎么用**：`python session_start.py --agent <名字>` → 首轮自动注入身份摘要。

### B. 联想召回引擎
- **实现**：每篇日记标签按顺序建方向边 → query 预感应出 Core/Ghost 种子标签 → 激活沿网络脉冲传 2 跳 → 结合向量 top-k 加权打分；用 log压缩/枢纽校正/预算守恒防走偏爆炸。
- **用处**：不用说出关键词也能回忆（"压力大"→"考试"）。
- **怎么用**：`python recall.py --query "压力大" --identity <名字>`

### C. 多智能体物理隔离 + 身份即开户 + 身份优先路由
- **实现**：路径层每 agent 独立目录（`config`）；`maintenance.py` 迁历史孤儿；`--identity` 身份优先，ambiguous 回退默认区 + 词面锚定；`ensure_agent` 即开即用。
- **用处**：一个引擎同时当"多个脸的管家"，隐私不串号。
- **怎么用**：`recall.py --register '<描述>' --identity nova` 开户；`recall.py --query "..." --identity nova` 只查它自己；`list_agents()` 即刻可见 `nova`。

### D. 注入侧上下文控制（去重 + 预算收敛 + 不截断）
- **实现**：`dedupe_results`（chunk_id + 规范化正文去重）；`fit_to_budget`（预算内按相关度取**完整**条目，单条超预算仍保留最相关一条）；`format_recall_output` 默认不再 200 字硬截。
- **用处**：关键信息不丢、重复不占坑、token 有硬上限——"少而完整"优先于"多而残破"。
- **怎么用**：`recall.py --query "..." --identity <名字> --budget 800`（预算=字符数；缺省则语义优先全量注入）。

### E. 自进化
- **实现**：`evolution.py` 在用户允许下覆写可动层、对久不用锚做衰减重估；不可变锚 vs 可变可动层分离。
- **用处**：记忆会随相处"长大"，而非一成不变。
- **怎么用**：`/evolution` 对话触发覆写与衰减评估。

### F. 身份摘要不硬截
- **实现**：删去 `session_start.MAX_CHARS=200` 与 `[:199]+"…"`；只靠"字段选择"控量（只取 name/锚/风格/能力），不按字符硬砍。
- **用处**：身份含关键基础内容，能有多少给多少、绝不丢。
- **怎么用**：无需额外命令，`session_start.py` 首轮摘要即完整保留。

---

## 5. 用户故事（多轮，可用作脚本剧情）

> 主角：你与记忆体「Nova」。

- **Day1｜写长记忆**：聊"为什么不敢报周六雅思"，一条 400 字日记完整入库（旧版会截断丢后半句因果）。
- **Day2｜联想召回**：你说"我还是报了周六那场"→ Nova 自动联想回那条，接住"全马复原期"关键信息，回：*"上次你不是因为全马刚恢复才状态崩的吗？这次前两周别上强度。"* —— 旧版截断时会反问"那场怎么了"，**答非关键**。
- **Day3｜上下文不炸**：一次 query 触发联想召回 14 条（含 3 条重复措辞）→ 去重成更少、预算只放最相关几条**完整**记忆；上下文不臃肿、不跑偏。
- **贯穿｜隔离墙**：mira（恋爱）/ qinglan（教学）/ nova 各自一座墙，互不串号——"爱聊恋爱的 LM 和推行礼貌的 LM 可以是同一个底座养出的不同脸"。

---

## 6. 验证与质量

- `pytest tests/` 在 `feature` 顶端 = **157 passed**（V1 全程保留 + 15 个新测试文件覆盖新能力）。
- 冲突/回归测试重点：`test_identity_routing.py`、`test_identity_provisioning.py`（隔离+开户）、`test_inject_control.py`（去重+预算）、`test_maintenance_orphans.py`、`test_object_association.py`、`test_evolution.py`。
- **干净复现**：演示与验证均在**临时目录**执行，真实 `~/.midnight` 未被污染。

---

## 7. 意义与后续

- 单机 skill + SQLite 足够支撑当前单用户按需使用；向**服务端集成**演进的方向已由 `server-side-plan.md` 画出（未来再考虑 embedding 模型常驻、多设备同步、微服务化）。
- 演进顺序可理解为：**先"记得对"（身份/联想）→ 再"记得安全"（隔离）→ 再"记得不炸"（注入预算）→ 最后"记得会长大"（自进化）**。

---

## 8. 文档索引

| 文档 | 作用 |
|---|---|
| `docs/OPTIMIZATION-SPEC.md` | 迭代规格主线（T1–T6） |
| `docs/optimization-blueprint.md` | 蓝图 / 实现清单 |
| `docs/ai-memory-product-report.md` | 产品化视角分析 |
| `docs/video-script-material.md` | 视频素材稿（如需最新总结，可基于本文档更新） |
| `docs/server-side-plan.md` | 服务端演进规划 |
| `.scratch/v2-self-object-memory/` | spec + 6 张 issue 单元 |