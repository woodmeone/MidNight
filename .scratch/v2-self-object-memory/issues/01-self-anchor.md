# T1: self 锚生成（self.md）

Status: ready-for-agent
Blocked by: 无

## Problem

Midnight 目前 agent 只有 `agent.json`（description 字段）当"自我"，无结构化身份锚。V2 需要 agent 有独立自我 = 人设/能力/价值观/身份连续性，且区分**定海锚（只读，防跑飞）**与**可动层（可写，随经历演化）**。

## Spec ref

OPTIMIZATION-SPEC.md §4.B.1、§5「self 锚生成」

## 交付物

- `skills/recall/scripts/self_model.py`：
  - `get_self_path(agent) -> str`（`<agent_dir>/self.md`）
  - `ensure_self(agent, defaults=None) -> dict`：无 `self.md` 时用默认模板自动建；有则幂等返回已解析内容，**不覆盖既有锚**
  - `read_self(agent) -> dict`
  - `update_self(agent, patch, mutable_only=True)`：只允许改可动层，改定海锚字段被拒绝（值不变）
  - CLI：`python self_model.py --init [--agent X]`
- `self.md` 格式：YAML frontmatter 含 `anchor_tags`（对象/身份锚标签）+ `mutable`（可动层 dict），正文 = 自描述；字段级区分定海锚与可动层。
- `config.py` 暴露 `get_self_path`。

## 验收（行为测试，`tests/test_self_model.py`）

- [ ] 无 `self.md` 时 `ensure_self` 自动生成文件，含 `anchor_tags` 与 `mutable` 块
- [ ] 已有 `self.md` 时 `ensure_self` 幂等：不覆盖既有 anchor_tags/自描述
- [ ] `read_self` 能解析回 dict
- [ ] `update_self(mutable_only=True)` 改可动层成功；改定海锚字段被拒绝（值不变）
- [ ] 158 旧测试保持绿
