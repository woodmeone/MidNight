# T2 — 确定性通道（时间轴 / 字面命中）

Issue: #5 ｜ Spec: `../spec.md` ｜ Blocked by: 票1

## 目标

把"记到哪一天 / 最新一条 / 有没有提过 X"变成**库内一次查询**，从根上消掉"去 grep md"的动机。

## 落点

- `recall.py`：`timeline_recall(db_path, since, until, k)`、`literal_recall(db_path, text, since, until, k)`
- CLI：`--timeline N`、`--since`、`--until`、`--literal "词语"`
- `format_recall_output(results, header=None)`：新增可选 header，默认不变

## 验收（可直接写测试）

- [ ] `--timeline 3` 返回最近 3 篇，按 `diary_date` 倒序（同日按 file id 倒序）
- [ ] 同一篇日记被切成多块时 **file 级去重**，正文按 `chunk_index` 顺序拼接
- [ ] `--since/--until` 为闭区间，只影响这两条通道，可单用也可与 `--timeline/--literal` 组合
- [ ] `--literal "中立不追究"` 命中；`--literal "%"` 按字面匹配不退化成通配符；无命中输出「暂无相关记忆」
- [ ] `--timeline/--literal` 缺 `--identity/--agent` → usage + 退出码 2，不落任何库
- [ ] **对抗**：把 agent 的 `dailynote/` 目录整体移走后，两条通道仍返回同样结果
- [ ] **对抗**：A 的库只返回 A 的内容（B 的内容不可见）
- [ ] 不带新 flag 时 `--query` 输出与改动前逐字节一致
- [ ] 两条通道各写一行留痕（channel=timeline / literal）

## 边界（不做）

- 不做 FTS5 索引（中文分词 + 迁移成本，`LIKE` 在这个量级够用；要快再说）
- 不做跨 agent 的全局时间轴（违反身份隔离）
