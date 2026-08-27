# 02 — 向量最近邻检索（recall 基础）

**What to build:** 一条完整的"查询 → 召回"路径第一次跑通：`recall.py --query "..."` 把查询向量化，在已入库的 chunks 中做余弦相似度最近邻检索，按相似度从高到低返回 Top-K 条记忆（每条带来源日期和内容摘要），输出为可注入上下文的纯文本片段。暂不涉及联想扩增和时间加权。

**Blocked by:** 01 — storage and ingest

**Status:** ready-for-agent

- [ ] `recall --query "..." --k N` 返回 Top-N 条相似记忆，按相似度排序
- [ ] 输出格式为纯文本上下文片段（含来源日期，形如 `（2026-08-15）你提到…`）
- [ ] 查询向量化复用与 ingest 相同的 embedding 客户端（可注入伪向量测试）
- [ ] 空库查询返回友好空结果提示，不崩溃
- [ ] 测试 `test_similarity_search.py`：入库多条不同主题内容，查询能正确召回最相关条目且排序正确