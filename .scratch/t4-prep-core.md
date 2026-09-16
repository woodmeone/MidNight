## Parent

#2

## What to build

一个与运行时无关的可移植核心函数 prep_for_reply：门控（这轮要不要召回）→ 取 query（调用方可显式声明"AI 判断的语义"，否则用原话）→ 联想召回（复用现有引擎，可透传票2/票3开关）→ 去重 → MMR 重排 → 预算收敛 → 输出可直接注入的文本块。

配一个薄 CLI（prep.py）供 skill 形态调用：SKILL.md 的召回指引从"多命令+参数表"瘦身为"回复前跑一条 prep 命令"。未来迁移到有 hook 的运行时，核心函数一字不改、只换调用入口。

## Acceptance criteria

- [ ] prep_for_reply 纯编排、不 import 任何运行时/框架代码；参数含 identity/query/budget/multi_scale/mmr/λ 及门控阈值
- [ ] 门控：触发词命中必召回；纯寒暄短消息不召回；可注入时钟/历史轮数做确定性测试
- [ ] query=None 用原话；显式 query 优先（AI 定语义的 A 左接口）
- [ ] 输出为格式化文本块 + 结构化结果（供未来 hook 直接消费）
- [ ] 端到端测试：临时库写入→prep_for_reply 召回→预算内完整注入；SKILL.md 更新接入说明
- [ ] 全量测试绿

## Blocked by

- 票2（多尺度线索提取）
- 票3（MMR 多样性重排）
