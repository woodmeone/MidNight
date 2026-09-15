# T4: SKILL.md /init 引导首建 self + 对象

Status: done
Blocked by: 01, 02

## Problem

新 agent 首次运行不知道自己是谁、不认识使用者。V2 需要轻量引导：先建 self 锚，再问"怎么称呼你"→ 把名字当对象 anchor tag 写入后续日记。不可太重。

## Spec ref

OPTIMIZATION-SPEC.md §4.B.3、§5「self 锚生成」

## 交付物

- SKILL.md 新增「首次使用 / init 引导」小节：
  - 首次对话调用 `self_model.py --init`；无 self 则引导"给自己定位"（人设/能力/价值观）
  - 问对方称呼 → 把名字写入后续日记 tags（对象 anchor tag 规约）
- 引导要轻：1–2 句话 + 默认值，不打断主流程。

## 验收

- [x] SKILL.md 含 init 引导文案（文档行为，人工 review）
- [x] 158 旧测试保持绿

## 落地记录

SKILL.md 新增「init 引导（首建自我 + 认识你）」小节：首建 self（`self_model.py --init`，幂等）+ 问称呼写对象 anchor tag；1–2 句话 + 默认值，不打断主流程。另更新「文件结构」小节补齐 self_model.py / session_start.py 等。
