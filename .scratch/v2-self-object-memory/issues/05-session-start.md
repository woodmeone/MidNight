# T5: session_start.py 上下文轻编译

Status: done
Blocked by: 01

## Problem

新会话要不空白（记住 self + 本次对象），但不能像 letta 那样把 persona 全档常驻塞爆上下文。V2 只要：短 self 身份摘要编译进首轮 system/user 简述，其余靠联想。

## Spec ref

OPTIMIZATION-SPEC.md §4.C、§5「self 锚生成」「上下文不爆」

## 交付物

- `skills/recall/scripts/session_start.py`：
  - 读 `self.md` → 编译 ≤200 字身份摘要（定海锚 + 可动层概要）
  - 输出可注入首轮 system prompt 的文本：`[身份] ...（其余记忆靠联想召回）`
  - CLI：`python session_start.py [--agent X]`
- 不改变任何现有接口/存储。

## 验收

- [x] 输出含 self 摘要、长度受限（≤ 约 200 字）
- [x] 无 `self.md` 时输出空/引导文案，不报错
- [x] 158 旧测试保持绿

## 落地记录

`session_start.py`：读 self.md → `compile_identity_summary()` 编译 ≤200 字摘要（name + 锚标签 + 可动层概要），CLI 包装为 `[身份] ...（其余记忆靠联想召回）`；无 self 输出 GUIDANCE_TEXT 不报错。配套 `tests/test_session_start.py` 5 例。另修复 self_model.py 直接 CLI 运行时缺父目录 sys.path 的 bug（冒烟测试发现）。
