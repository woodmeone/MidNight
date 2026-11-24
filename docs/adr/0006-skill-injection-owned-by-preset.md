# ADR-0006 — 宿主 skill 注入的所有权归预设层，host 层保持禁用

## 背景

本项目是**技能包**，由宿主（DeepSeek Harness）发现并加载。宿主侧的配置是分层
叠加的：host 层一份，每个 agent preset 各一份。同一个插件名在两处都启用，就是
两个实例、两个 `agent/pre-step` 监听器。

实测到的后果：一次 `/recall` 触发的 `skill-invocation` 消息在会话日志里出现两条，
`length=18963`、`sha=d4a1bf3217c6` **完全相同** —— 逐字节一样的同一份正文被塞两遍。
硬扫 393 个历史会话，**360 轮**存在同轮重复、0 轮正常。`recall` 占 154 轮、
`ask-matt` 60 轮、`git-native-sop` 52 轮。

成因定位到两层：`dsh-base` 在 host 层挂 `tool-skill`，`dsh-web-app` 把它默认禁用
并在注释里写明「由预设自己挂」，三个预设各挂了一份 —— 但用户的
`profiles/web/cordis.patch.yml` 里写了 `disabled: false`，把上游关掉的那份重新
打开了。结果就是 host + 当前预设 = 两份同时生效。

关键区分：`skill-filesystem` 只在 `fs/observed` 上有监听器，**不写上下文**；
只有 `tool-skill` 有 `agent/pre-step` 的两个监听器。所以「重复注入」只可能来自
注入方被启用了多次，供货方重复只是目录多扫一遍。

## 决策与取舍

**决策**：`tool-skill` 的所有权定在**预设层**，只允许启用一处；host 层保持
`disabled: true`。`skill-filesystem` 同理（它虽不注入，但双层会让目录扫描翻倍，
且与本决策同源，一起归位）。

放弃了什么：

- **放弃「host 层单点挂载」这条路**。它看起来更省事——写了一处就全局生效，不必
  每个预设备一份。但预设的作用域隔离会被破坏：`minimal` 预设（0 处挂载，明确
  表示「这个预设不要 skill 能力」）会被 host 层强行塞进来。上游选择在预设层挂，
  是为了让「要不要 skill 能力」成为预设自己的事。
- **放弃在 profile 里覆盖 `disabled: false`**。profile 是最后一层、优先级最高，
  写上去就赢，但赢的代价是把上游的防双挂设计作废。以后遇到类似「上游默认关掉
  但我想开」的情况，正确做法是确认它**确实没有任何一层开着**（用
  `--dump-config` 数），而不是闭眼写 `disabled: false`。

为什么难以逆转：这条约束改变的是**配置层的语义**（哪一层拥有所有权），一旦按
「host 层也能开」写下去，后续每个新预设都会再多一份，且症状是静默的
——不报错、不崩、只是慢和贵。改回来需要重新理解整条叠加链。

## 后果

- 新预设不会意外继承双份注入；`minimal` 预设「不要 skill」的语义保住了。
- 想给某个 agent 单独开关 skill 能力，改的是**那个预设**，不是 profile。
- 判据可执行：`python tools/skill_injection_doctor.py --config` 必须报
  「`tool-skill` 只在 preset:<name> 启用一次」；`--sessions` 必须报绿。
  只看配置不看日志不够 —— `--config` 绿而 `--sessions` 红，说明还有一条
  未识别的注入路径。
- 顺带发现：profile 里 5 条 `- id:` 指向不存在的条目（`skill-badge`、
  `dsh-purge*` ×3、`bili-humanism`），dump 会报 `not found` 但不影响启动。
  它们不影响本 ADR 的结论，本轮不动，留待后续清理。
