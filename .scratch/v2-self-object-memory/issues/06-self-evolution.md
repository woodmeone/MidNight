# T6: 自进化（/evolution 覆写可动层、定海锚只读 + 久不用衰减）

Status: done
Blocked by: 01, 03

## Problem

Agent 要有独立自我且能自我演化：基于新交互/调研/镜像反馈，评估并覆写 self 的**可动层**；**定海锚只读**（防跑飞）。同时 §4.B.4「规则不固化」要求"久不用衰减"——旧关联自然淡出，不写死 rules.md。

## Spec ref

OPTIMIZATION-SPEC.md §4.B.4、§4.B.5、§5「self 演化」

## 交付物

- `skills/recall/scripts/evolution.py`：
  - `apply_evolution(agent, feedback, patch, source)`：把 patch 应用到可动层；定海锚字段拒绝；每次尝试（含被拒）记录到 `<agent_dir>/evolution.log`（JSONL：ts/source/feedback/applied/rejected）
  - `read_evolution_log(agent)`：读演化历史
  - `decay_stale_edges(db_path, stale_days, factor, floor)`：对 `updated_at` 过旧的 tag_edges/tag_cooccurrence 降权，弱边删除（无 schema 改动）
  - CLI：`--apply --feedback ... --patch '{json}' [--source user|mirror|research]` / `--decay [--stale-days 90] [--factor 0.5]` / `--log`
- SKILL.md 新增「自进化」小节（可选 /evolution 命令用法）
- 不改变任何现有接口/存储语义（decay 仅显式调用时生效）。

## 验收

- [x] 调整可动层后定海锚未变；改定海锚字段被拒且日志记录
- [x] 无 self 时 --apply 自动先建 self 再应用
- [x] 演化历史可读（多次追加）
- [x] 久不用衰减：新鲜边不动、过期边降权、过期弱边删除
- [x] 119 旧测试保持绿

## 落地记录

`evolution.py`：`apply_evolution`（可动层覆写 + 定海锚只读 + evolution.log JSONL 记录）、`read_evolution_log`、`decay_stale_edges`（tag_edges/tag_cooccurrence 久不用降权、弱边删除，复用 updated_at 无 schema 改动）。CLI `--apply/--decay/--log`，并因 Windows PowerShell 剥内嵌双引号，新增 PowerShell 安全的 `--set key=value`（点号嵌套 + 裸列表 `[a,b,c]`）。配套 `tests/test_evolution.py` 8 例。SKILL.md 新增「自进化」小节。全量 127 测试绿。
