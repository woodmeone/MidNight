# V2 自我+对象记忆 优化规格

> 权威母档：`docs/OPTIMIZATION-SPEC.md`（handoff-1）。本文件记录 V2 定稿后的增量确认口径，与母档冲突时以本节为准。
> 发布者：to-tickets（2026-09-02）  标签：`ready-for-agent`

## 确认口径（2026-09-02 用户定稿）

1. **单 agent 单库**：自始至终只有一个 Agent、一个记忆库（如 mira 的 `recall.db`），不新增物理/逻辑分区。
2. **对象 = anchor tag**：关于某对象（人/组织）的日记写进唯一库，frontmatter `tags` 带对象名（如 `阿散`）。不建独立库/子目录/diary_name 维度。
3. **多对多缠绕**：对象与对象、对象与话题的关联 = 共现网内节点天然可达；跨概念联想（马拉松↔阿散）由 T3 联想深化保证。
4. **T6 自进化本轮不做**，推到下一轮。

## Ticket 清单（blocking 关系）

| 票 | 内容 | Blocked by |
|---|---|---|
| 01 | self 锚生成（self.md：定海锚只读 + 可动层可写） | 无 |
| 02 | 对象 anchor tag 规约 + 对象联想召回集成测试 | 无 |
| 03 | 联想深化 A1–5（方向边/log压缩/枢纽校正/预算/Core-Ghost） | 02 |
| 04 | SKILL.md /init 引导首建 self+对象 | 01, 02 |
| 05 | session_start.py 上下文轻编译 | 01 |

## 约束（贯穿全部票）

- 158 旧测试保持绿（recall 95 + core 21 + pulse 26 + compass 16，实测基线）。
- `recall_associative` 对外签名不变；A 深化全部锁在引擎层（tag_network.py + schema）。
- 原创实现，不摘抄 VCP/letta 函数（ADR-0001）。
