# 宿主 skill 双挂导致每轮注入两遍（白烧约 1 万 token）

## 用户故事

作为使用 DSH 的新手，我想要一次 `/recall` 只注入一份 SKILL.md，以便不白烧一半上下文。

## 背景 / 为什么要变

一次 `/recall` 触发时，同一份 SKILL.md（18963 字符，约 1 万 token）被连塞两遍，payload 指纹完全相同。用户的原话是「白花钱的毛病」。

**已测事实**（不是推测）：

1. 会话日志 `seq=10` / `seq=11` 两条 `skill-invocation`，`name=recall`、`length=18963`、`sha=d4a1bf3217c6` —— 逐字节相同。
2. 硬扫全部会话：**360 轮同轮重复，0 轮正常**。`recall` 154 轮、`ask-matt` 60 轮、`git-native-sop` 52 轮。
3. `dsh --profile web --dump-config` 显示：`tool-skill` 在 **顶层（host 层）启用 1 次 + 当前预设 standard 启用 1 次** = 生效 2 份。
4. 只有 `tool-skill` 有 `agent/pre-step` 监听器（第 181、217 行）；`skill-filesystem` 只在 `fs/observed` 上，**它不注入，只供货**。
5. 上游设计意图：host 层 `tool-skill` / `skill-filesystem` **应禁用**，由预设自己挂。`profiles/web/cordis.patch.yml` 写了 `disabled: false`，把 host 层那份重新打开了 —— 这是偏离。

## 验收标准

- [x] 一条命令能判定该 bug 红/绿：同轮同 skill 注入次数 >1 即红（`tools/skill_injection_doctor.py --sessions`）
- [x] 同一命令能定位成因层：报告「同时启用 host 层 + 预设层」的插件（`--config`）
- [x] 修掉 live profile 里的 `disabled: false`，`--dump-config` 复核 host 层为 `disabled: true`
- [ ] 重启后新会话日志里 `skill-invocation` 每轮只剩 1 条（**未验证 —— 需重启 DSH**）
- [x] 全量测试对基线无回归（基线 447 passed → 466 passed，+19 新测试）
- [x] 把「DSH profile 组合层的双挂陷阱」写进真相文档（PROJECT.md / CONTEXT.md / ADR-0006）

## 范围外（本轮不做）

- 不改上游 `@deepseek-ai/dsh-*` 包（`node_modules` 只读）
- 不处理 `time-context` 的多条注入 —— 每次内容不同，不是重复
- 不动 `skill-badge`、`ui-skill` 等无关插件
- 不清理 profile 里另外 4 条 `not found` 死条目（`dsh-purge*` ×3、`bili-humanism`）

## 真相影响

- **PROJECT.md**：模块地图加 `tools/` 一行；约束新增「宿主注入只许一份」（ADR-0006）
- **CONTEXT.md**：新增「运行环境（DSH 宿主）」一节 —— 注入 / 供货方vs注入方 / 层 / 双挂 / 生效预设 / 注入体检 / 死条目
- **ADR-0006**：`docs/adr/0006-skill-injection-owned-by-preset.md`

## Comments

**2026-11-24 — 实现记录**

分支 `fix/duplicate-skill-injection`，从 `origin/develop`（`9434354`）拉出，用独立 worktree
（`D:\Project\_wt\duplicate-skill-injection`）—— 因为 `~/.dsh/skills/recall` 是指向主工作区的
junction，切分会把活体 skill 抽掉。

**对抗式审查抓到的两个自身 bug**（都是先写错、被测试逼出来）：

1. 首版把三个预设都算作同时生效，报「被塞 4 份」，但日志实测是 2 份。真相是同一时刻只有
   一个 active preset。加了 `test_only_active_preset_counts_towards_duplication`。
2. `disabled: true` 解析失败 —— 我原以为子键缩进等于 `- id:` 的横线缩进，实际深 2 格。
   改成「第一个正文行的缩进才是键缩进」。加了 `test_disabled_true_is_parsed_not_assumed_false`。

**系统思维检查过的波及面**：`skill-filesystem` 也双层但无害（不注入），明确标为「提示」而非「红」；
`minimal` 预设 0 处挂载，说明「不要 skill」的语义靠预设层保住 —— 这是 ADR-0006 选择预设层
而非 host 层单点挂载的核心理由。

**差分闭环**：同一命令对真实 dump 判红（2 处）、对叠加 `disabled: true` overlay 的 dump 判绿（1 处）。
