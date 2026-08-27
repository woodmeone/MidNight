# 01 — 存储层与最小入库循环（schema + ingest 基础）

**What to build:** 一条完整的"日记文件 → 入库"路径第一次跑通：项目首次运行能初始化 SQLite（files/chunks/tags/chunk_tags 五张表），一份标准格式的日记文件能被解析（YAML frontmatter 的 maid/created/tags + 正文）、切块、向量化后写入数据库，且重复入库同一文件被幂等跳过（checksum 去重）。

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [ ] `init`: 运行后创建 `recall.db` 及全部表（schema 与 spec 一致）
- [ ] `ingest <file>`: 解析标准日记（frontmatter + 正文），切块（默认 512 字符），写入 files/chunks/tags/chunk_tags
- [ ] 向量化通过可注入的 embedding 客户端完成（测试可用确定性伪向量，不依赖外网）
- [ ] 同一文件重复 ingest 幂等：checksum 相同则跳过
- [ ] 测试 `test_ingest_basic.py`：入库后 SQLite 记录存在且切块正确