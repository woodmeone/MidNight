# 04 — 时间连续性召回 + 截断 + 综合排序

**What to build:** 把另外两个维度加入召回管线：时间连续性（新会话开头自动补最近内容，`--time-ratio` 控制权重）和截断（`--truncate` 比例控制输出量）。合并向量分 + 联想分 + 时间分，按综合得分排序输出。这是"新会话不空白"和"召回量可控"的来源。

**Blocked by:** 02 — recall vector knn, 03 — tag cooccurrence pulse

**Status:** ready-for-agent

- [ ] 时间连续性：最近 N 天内的 chunk 获得额外权重（N 由 `--time-ratio` 折算）
- [ ] 截断：`--truncate 0.25` 从完整召回集中按比例截取（取相似度最高的前 25%）
- [ ] 综合排序：`score = vector_score + tag_score + time_score`，可配置权重
- [ ] 测试 `test_time_continuity.py`：新旧日记排序受 `--time-ratio` 影响
- [ ] 测试 `test_truncation.py`：20 条召回结果，`--truncate 0.25` 只输出 5 条