# T3: 联想深化 A1–5（方向边 / log压缩 / 枢纽校正 / 预算守恒 / Core-Ghost 预感应）

Status: ready-for-agent
Blocked by: 02

## Problem

现状 `tag_cooccurrence` 无向、线性 +1；BFS 无预算/无枢纽校正、种子只取 top-N 无 ghost。高频枢纽词垄断传播，跨概念联想（马拉松↔阿散）易断或跑偏。需把"粗糙共现+BFS"升级为受 VCP TagMemo 思想启发的联想场——**完全原创实现，`recall_associative` 接口不变**。

## Spec ref

OPTIMIZATION-SPEC.md §4.A.1–5、§5「深联想回归」

## 交付物

全部锁在 `skills/recall/scripts/tag_network.py` + `schema.py`（+`ingest.py` 写边）。`recall_associative` 签名不变。

1. **有序双向边**：新增有向表 `tag_edges`（`tag_from_id, tag_to_id, weight, distance, direction`）；ingest 按同文件 tag 出现序建顺流/逆流边；权重 = 序位势能 · `exp(-位置距离/λ)` · 方向阻尼（顺流>逆流，guard 限制逆流比例）。
2. **累计证据压缩**：边权重以 `e = log(1 + λ·W)` 存储/读取，防高频标签垄断。
3. **入流枢纽校正**：传播入目标节点时按该节点全图入流幂律缩降（`(1+inflow)^-α`），抑制泛泛枢纽词。
4. **预算守恒传播**：每节点出流受限、总激活预算固定，虫洞增益只争既定预算，不无限累加。
5. **Core/Ghost 预感应**：query → embedding 感应 top-n core 候选 tag；对低分但有语义/共现关联的 tag 补为 ghost；core+ghost 一起进传播。
6. 保留 `tag_cooccurrence` 表与写入（向后兼容旧测试）；`activate_tags` 对外参数兼容（可新增可选参数）。

## 验收（行为测试）

- [ ] **深联想回归**（SPEC §5）：库中含 紧张↔雅思 关联且"考试"为高频词；query `压力大怕考砸` 能深联想出雅思（不被"考试"吞）
- [ ] T2 对象联想测试稳定通过
- [ ] 旧 test_ticket03 共现/脉冲测试仍绿
- [ ] 158 旧测试保持绿

## 实施说明

- 分步实现（1→2→3→4→5），每步配一个行为测试，逐步收紧。
- 参照母档 `docs/optimization-blueprint.md`（A 深化节）与一手源码路径回溯 VCP/letta 细节。
