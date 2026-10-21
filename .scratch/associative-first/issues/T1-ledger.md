# T1 — 检索留痕底座（ledger）

Issue: #5 ｜ Spec: `../spec.md` ｜ Blocked by: 无

## 目标

让"这一轮走了哪条检索通道"从自述变成**可审计的事实**：每次 CLI 检索追加一行 jsonl，`--audit` 能读回来。

## 落点

- 新增 `skills/recall/scripts/ledger.py`（append / read / path，全部按 agent 隔离）
- `recall.py`：CLI 在「联想召回」与「auto 路由」两条已有出口追加留痕；新增 `--audit [N]`

## 验收（可直接写测试）

- [ ] `append_entry` 写一行 JSON 到 `<base>/<agent>/retrieval_ledger.jsonl`，字段含 `ts/agent/channel/query/hits/chunk_ids`
- [ ] `read_entries(agent, limit)` 返回最近 N 条，**坏行跳过不抛**，文件不存在返回 `[]`
- [ ] 不同 agent 的 ledger 物理隔离
- [ ] `append_entry` 内部异常全部吞掉并返回 False（只读目录/路径非法时检索照常）
- [ ] CLI：`recall.py --query ... --identity X` 落一行 `channel=associative`；`--audit 5` 打印出这行
- [ ] **留痕不进库函数**：直接调 `recall_associative` / `prep_for_reply` 不产生任何留痕文件
- [ ] 既有 265 passed 不回归

## 边界（不做）

- 不做聚合统计（hits 分布、命中率）——那是人的事
- 不做轮转/清理——jsonl 追加成本极低，留给人按需 truncate
