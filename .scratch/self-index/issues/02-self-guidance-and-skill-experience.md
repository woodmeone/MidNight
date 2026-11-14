# 02 — self.md 路径指路 + 能力经验日记约定

Issue: #10 ｜ Spec: `../spec.md` ｜ Blocked by: 无 ｜ 分支: `feat/self-index`

## 用户故事

作为**一个遇到不会的活儿的智能体**，我想要记得「先查技能库」这个动作，也记得「哪个 skill 用起来什么感觉」，
以便不用每会话被告知一遍有什么可选，还能把踩过的坑变成下次的判断。

## 背景 / 为什么要变

Issue 01 只解决了资产。能力和同伴呢？讨论的结论是**都不进开机清单**：

- **能力**：存在性写进 `self.md` 一句就永久有效；经验靠记忆积累（已跑通——`prep.py` 现在就会召回
  「`recall.py` 没有 `--tag-weight`，传了直接 exit 1」这类教训）。
- **同伴**：遗漏代价低（想不起 mira 还能自己干，想不起 image-gen 是真不知道怎么做——两件事不对称），
  且「该问谁」联想能带出来（实测：查「协作」时库自己把贸贸/kaka/阿散带了回来）。

但现在 `self.md` **没有地方放这两句话**，也没有约定把 skill 经验写成可召回的日记。

## 验收标准

- [ ] `self_model.py` 的 `DEFAULT_TEMPLATE` 增加可动层字段 `paths`（字符串或列表），默认值：
      「遇到不会的活，先查技能库——那里有现成的做法，别自己从零造。」
      「有事可以问同伴，别一个人硬扛。」
- [ ] `self_model.py --init` 对新智能体写入 `paths`；**对已有 self.md 幂等不动**（缺字段也不自动补，
      避免改写别人的自我认知）
- [ ] 新增显式命令 `self_model.py --add-paths [--agent X]`，让人/智能体自愿把这一段补进老 self.md
- [ ] `session_start.compile_identity_summary()` 的摘要里带上 `paths` 的**极短形式**
      （例：`路径:先查技能库·有事问同伴`，≤15 字）；预算与 Issue 01 共用 120 字
- [ ] `SKILL.md` 新增「能力经验」章节：标签约定 `skill经验`，难受时必带 `踩坑`；
      正文写三层（什么场合好用 / 什么场合不好用 / 判断标准）
- [ ] 契约测试锁住：`SKILL.md` 里「skill经验」「踩坑」两句不可被删除；
      `DEFAULT_TEMPLATE['mutable']` 里 `paths` 不可被删除
- [ ] 全量测试与 G1 基线一致（**343 passed / 6 skipped**，2026-11-14 实测）

## 票（垂直切片，按序实现）

- [ ] 票1：`DEFAULT_TEMPLATE` + `--init` 写入 + 幂等测试 ｜ Blocked by: 无
- [ ] 票2：`--add-paths` 显式补写 + 老库不动测试 ｜ Blocked by: 票1
- [ ] 票3：`compile_identity_summary` 带极短 paths + 预算测试 ｜ Blocked by: 票1
- [ ] 票4：`SKILL.md` 能力经验章节 + 契约测试 ｜ Blocked by: 票1

## 范围外（本轮不做）

- **不自动改任何已存在的 `self.md`**——自我认知是智能体自己的，只能在它自愿时补
- **不做技能库扫描**（存在性靠一句指路，不扫）
- **不做同伴扫描/名单**（同 Spec 被否决方案）
- **不给 skill 打分**、不建熟练度字段
- 不改任何 `~/.midnight/recall/*/recall.db`

## 对抗式自检（写测试时问自己）

- 老 self.md 有 `mutable` 但没 `paths` → `--init` 会不会覆盖？必须不动
- `mutable` 是坏 JSON → 崩不崩
- `paths` 写成列表还是字符串，两种都要能读
- 摘要超预算时，paths 这一句会不会被整句砍掉？砍了等于白写——它应该比风格描述更优先保留
- 被演化（`evolution.py --apply`）改掉 `paths` 怎么办？它是可动层，允许改，但要在日志里留痕

## 真相影响

- **CONTEXT.md**：新增术语 **能力经验（skill experience）**
- **PROJECT.md**：`self_model.py` 职责补一句「含路径指路（paths）」；"核心业务流程·自我模型"补 `--add-paths`
- **ADR**：无新增（并入 ADR-0004 的「能力/同伴为什么不进清单」一节）
