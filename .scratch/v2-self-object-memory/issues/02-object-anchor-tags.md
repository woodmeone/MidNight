# T2: 对象规约（对象 = anchor tag）+ 对象联想召回集成测试

Status: ready-for-agent
Blocked by: 无

## Problem

V2 需要"对每个遇到的人建对象记忆、多对多缠绕"。已确认口径：**对象 = anchor tag**，不建独立库/子目录/diary_name 维度。需要把规约文档化，并用一条集成测试证明"对象作为一等节点可被联想召回"。

## Spec ref

OPTIMIZATION-SPEC.md §4.B.2、§5「对象联想召回」「多对多隔离」

## 交付物

- **对象规约**（写入 SKILL.md 写日记协议）：关于对象 X 的日记，frontmatter `tags` 必须含对象名 tag（如 `阿散`）。
- 集成测试 `tests/test_object_association.py`：
  - 唯一库中写入 阿散 日记 `tags:[阿散, 马拉松, 紧张, 雅思]`、乙 日记 `tags:[乙, 旅行, 美食]`
  - 验收 A：query `跑马拉松 紧张`（不含"阿散"）→ `recall_associative` 结果包含阿散日记 chunk
  - 验收 B：query 阿散主题时，乙的 chunk 排序不高于阿散的（相关性软隔离）

## 实施说明

- 测试用 `FakeEmbeddingClient`（SHA256 哈希向量），query 与 tag 的余弦相似度近似随机，种子选择可能不稳。若不稳，给测试/引擎加确定性种子注入（如 query 显式命中 tag 名时的直连，或让 `activate_tags` 支持 seed 覆写），保证验收 A/B 稳定。
- 验收 A 当前引擎应可部分通过；T3 深化后必须稳定通过（作为 T3 的回归护栏）。

## 验收

- [ ] 集成测试 A、B 全绿
- [ ] 158 旧测试保持绿
