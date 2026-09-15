## 用户故事
作为 qinglan/mira 这类私人助理 Agent 的开发者，我想要一个「AI 定语义、算法做联想」的记忆召回核心——Agent 回复前自己判断查询语义并给出 query，由标签脉冲网络算法完成联想召回——以便既保留 AI 对语境的深层理解（跨语境跳跃联想），又不依赖 Agent 现场决定怎么查、查多少，且核心可整体迁移到未来任何有 hook 的运行时。

## 背景 / 为什么要变
- 现状：召回流程散在 SKILL.md 提示词 + recall.py CLI 里，agent 要「自觉」判断查什么、传什么参数、控多少预算；注入侧已有 dedupe/fit_to_budget，但没有统一编排入口。
- 外部评审（对 VCP 的分析）对照后确认：枢纽降温/脉冲传播/门控已原创落地；**缺两块**——①多尺度线索提取（残差金字塔落地）②多样性去噪（MMR 重排，Ω 门控落地）。
- 架构定论：A 旋钮（谁定 query）保留 AI 判断；流程下沉为与运行时无关的可移植核心 `prep_for_reply`，skill 只作薄跳板，未来迁移只换调用入口。
- 顺带修复：SKILL.md frontmatter description 内嵌 ASCII 双引号导致 YAML 解析失败、技能库导入后详情空白（已本地修复，随本 Issue 提交）。

## 验收标准
- [ ] `prep.py` 提供 `prep_for_reply(user_msg, identity, query=None, budget=..., ...)`：门控→取 query→recall_associative→dedupe→MMR 重排→fit_to_budget→格式化文本，全程不依赖 SKILL.md 提示词逻辑
- [ ] 多尺度提取：query 拆为整句/关键词/短语多粒度向量，各自激活标签后合并传播；默认关闭、显式开启，关闭时逐位等于旧行为
- [ ] MMR 重排：注入结果在相关度与彼此差异度间取平衡；默认关闭、显式开启，关闭时行为不变
- [ ] 非破坏：不动任何既有记忆数据与 schema；全量测试通过且新增对抗测试覆盖三个新能力
- [ ] skill 导入修复：四个 SKILL.md frontmatter 均可被 yaml.safe_load 解析
- [ ] SKILL.md 瘦身指引：写日记协议不变，召回调用改为推荐 `prep.py` 一条命令

## 票（垂直切片，按序实现）
- [ ] 票1：SKILL.md frontmatter YAML 修复（4 个 skill） ｜ Blocked by: 无
- [ ] 票2：多尺度线索提取（query 分解 + 合并激活） ｜ Blocked by: 无
- [ ] 票3：MMR 多样性重排（注入前精排） ｜ Blocked by: 无
- [ ] 票4：prep_for_reply 可移植核心 + CLI + SKILL.md 接入 ｜ Blocked by: 票2、票3

## 范围外（本轮不做）
- 不做运行时 hook/每轮强制自动注入（skill 形态无注入点，留待迁移阶段）
- 不为酒馆场景做任何适配
- 不改写日记协议、不动 ingest/schema/记忆库数据
- 不引入新依赖

## 真相影响
- README/AGENTS.md：recall 模块增加 prep 入口一行
- CONTEXT.md：新术语「多尺度线索提取」「多样性重排」「可移植核心」
- ADR：不立（无难以逆转取舍）
