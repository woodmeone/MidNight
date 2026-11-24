# Duplicate skill injection — 同一个 skill 每轮被注入两遍

Status: ready-for-agent

## 用户故事

作为使用 DSH 的新手，我想要一次 `/recall` 只注入一份 SKILL.md，以便不白烧一半上下文。

## 背景 / 为什么要变

一次 `/recall` 触发时，同一份 SKILL.md（18963 字符，约 1 万 token）被连塞两遍，payload 指纹完全相同。用户的原话是「白花钱的毛病」。

**追溯链（不变量 5）**：本轮是新问题，仓库内没有历史意图。但根因在仓库外的 DSH profile 组合层，仓库此前从未记录过这层知识 —— 这是本条 Issue 要补的。

**已测事实**（不是推测）：

1. 会话日志 `seq=10` / `seq=11` 两条 `skill-invocation`，`name=recall`、`length=18963`、`sha=d4a1bf3217c6` —— 逐字节相同。
2. 硬扫全部会话：**357 例同轮重复，0 例正常**。`recall`×2 占 153 轮、`ask-matt`×2 占 60 轮、`git-native-sop`×2 占 52 轮。
3. `dsh --profile web --dump-config` 显示：`tool-skill` 在 **顶层（host 层）出现 1 次 + 三个预设各挂 1 次**；当前 agent 用 `standard` 预设 → 实际生效 2 份。
4. 只有 `tool-skill` 有 `agent/pre-step` 监听器（第 181、217 行）；`skill-filesystem` 只在 `fs/observed` 上，**它不注入，只供货**。所以重复来自 `tool-skill` 挂了两次，不是 `skill-filesystem`。
5. 上游设计意图（`dsh-web-app/cordis.patch.yml` 第 542–555 行注释）：host 层 `tool-skill` / `skill-filesystem` **应禁用**，由预设自己挂。`profiles/web/cordis.patch.yml` 第 6–11 行写了 `disabled: false`，把 host 层那份重新打开了 —— 这是偏离。

## 验收标准

- [ ] 一条命令能判定该 bug 红/绿：同轮同 skill 注入次数 >1 即红（`tools/skill_injection_doctor.py --sessions`）
- [ ] 同一命令能定位成因层：报告「同时启用 host 层 + 预设层」的插件（`--config`）
- [ ] 修掉 live profile 里的两行 `disabled: false`，`--dump-config` 复核 host 层为 `disabled: true`
- [ ] 重启后新会话日志里 `skill-invocation` 每轮只剩 1 条
- [ ] 全量测试对基线无回归（基线：447 passed, 6 skipped）
- [ ] 把「DSH profile 组合层的双挂陷阱」写进真相文档，后来者不必重踩

## 票（垂直切片）

小需求，票层留空 —— 本 Issue 对应一个 commit 切片（诊断工具 + 测试 + 真相回写）。

## 范围外（本轮不做）

- 不改上游 `@deepseek-ai/dsh-*` 包（`node_modules` 只读）
- 不处理 `time-context` 的多条注入 —— 那是每个 print 一条，内容各不相同，不是重复
- 不动 `skill-badge`、`ui-skill` 等无关插件
- 不重构 profile 其余内容

## 真相影响

- **PROJECT.md**：新增一节「运行环境：DSH profile 组合层」，说明本仓库的 skill 如何被 DSH 发现、以及双挂会怎样；模块地图加 `tools/` 一行
- **CONTEXT.md**：新增术语 —— 注入（skill-invocation）、双挂（double-mount）、host 层 / 预设层、供货方 vs 注入方
- **ADR-0006**：要不要把 `tool-skill` 的所有权定在预设层？—— 满足三条件（难以逆转：改了组合层行为；真实取舍：host 层挂载简单但会双份，预设层挂载每预设一份但作用域干净；后来者会问为什么不能在 profile 里 `disabled: false`）

## Comments

（暂无）
