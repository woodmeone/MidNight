## 用户故事

作为记忆的使用者（赖老师），我想要 AI 回答「你还记得我吗 / 这事记到哪一天 / 有没有提过 X」时**只走 recall 的检索通道**，以便记忆的答案永远来自联想算法与记忆库（受身份隔离、标签网、时间加权、预算约束），而不是靠翻 `dailynote/*.md` 原文蒙对。

Closes #5

## 背景 / 为什么要变

真实事故（2026-10-21）：用户用纯检索指令考记忆并禁止读文档。结论合格，但暴露出结构漏洞：**md 源文件同时被当成"源"和"索引"**。

第一性拆解——为什么 AI 会去 grep/read dailynote：

1. **能力缺口**：联想召回是相关性排序，答不了三类问题——时间轴（"最新一条是哪天"）、精确字面（"有没有提过某词"）、边界（"某天之后全部"）。没有正解时，翻文件是唯一能答的路。
2. **成本错觉**：读文件一次调用确定；召回要拼 query 还赌相似度。
3. **无痕迹**：走没走算法不可验证，只能自述。

代价：绕过身份隔离（明文目录可跨 agent grep）、绕过标签共现网与时间加权（退回关键词匹配）、绕过去重/预算（长日记整篇灌入）、依赖文件系统可读（迁 hook 运行时/容器就不成立）。

### 两条实证

**实证一：联想通道答不准"最新"。** 同一句"你最新记忆是什么"：

| 通道 | 返回日期 |
|---|---|
| 联想 `prep.py --query "最新 今天 昨天 刚刚 最近"` | 09-29 / 10-01 / 10-09 / 09-07 / 08-31（**全旧**） |
| 确定性 `recall.py --timeline 5` | 10-21 / 10-21 / 10-20 / 10-17 / 10-16（**正确**） |

2026-10-21 那轮真实体检里我确实答错了（说停在 9/22，实际库里到 10/21）。这不是"AI 偷懒"，是**联想排序答不了聚合问题**。

**实证二：库比 md 更完整。** qinglan 区库内 508 条 file 记录 vs 磁盘 505 个 `.md`，其中 2 条记录的源 md 已被删除，`--timeline` 仍能返回其内容。md 是"写入当时"的源，不保证长期存在——检索依赖 md 就会随文件丢失而丢记忆。

追溯链（不变量 5）：检索侧既有设计意图见 `docs/associative-optimization-spec.md`（T1–T4：tag-first 门控、深联想阈值、衰减保序、倒排+缓存），全部在"库内联想"这条线上，**没有任何一票把 md 当索引**。本轮不推翻它们，只补盲区。

## 实现（三票，按序）

| 票 | commit | 内容 |
|---|---|---|
| 票1 检索留痕底座 | `a431e69` | 新增 `scripts/ledger.py`；CLI 出口留痕；`--audit [N]` |
| 票2 确定性通道 | `fb25d7e` | `timeline_recall` / `literal_recall` / `--timeline/--literal/--since/--until` |
| 票3 规则层与真相回写 | `38ec326` | SKILL.md 通道铁律+查询派生协议；ADR-0002；PROJECT/CONTEXT 回写；文档契约测试 |

### 审查后追加的修复（全是静默失败——不修就会骗人）

| commit | 修的是什么 |
|---|---|
| `5093997` | 日期比较漏当天（`'2026-09-22 10:00:00' > '2026-09-22'`）；非法日期静默返空 → 严格校验 + 退出码 2；倒序区间报错 |
| `dfb9580` | `--literal` 吞掉下一个 flag（PowerShell 丢空串时 `--literal "" --identity X` 会把 `--identity` 当搜索词）；MCP 暴露 timeline/literal/audit |
| `4254ad0` | 字面命中拼接非连续块时插 `…`（原来直接 `\n\n`，读者会以为两段正文相邻） |
| `de8d2a4` | 留痕并发追加丢行（Windows `O_APPEND` 非原子，8×10 实测丢 3~9 行）→ 进程内互斥 |
| `9d9b502` | `prep.py` 是 SKILL.md 推荐的默认入口，原先不写留痕 → "每次检索都留痕"是假话 |
| `7cfa1e1` | 超长字面触发 `LIKE or GLOB pattern too complex` 崩溃；坏库甩 `sqlite3.DatabaseError` → 都改成人话报错 |
| `ffd50fb` | ADR 补实证二 |

## 验收对照

| 验收标准 | 实现位置 | 测试 |
|---|---|---|
| SKILL.md 通道铁律（默认联想 / md 永不作检索目标 / 显式授权例外） | `SKILL.md:18-34` | `test_skill_contract.py` 4 条 |
| 查询派生协议（2–5 名词性线索 + anchor + `--multi-scale`） | `SKILL.md:36-44` | `test_skill_has_query_derivation_protocol` |
| 确定性通道 `--timeline/--literal/--since/--until` | `recall.py` `timeline_recall` / `literal_recall` | `test_timeline_channel.py` 26 条 |
| 必须显式身份，缺则退出码 2、不落库 | `recall.py:main` 确定性分支 | `test_timeline_requires_explicit_identity` / `test_literal_requires_explicit_identity` |
| file 级去重 + 块序拼接 | 两个 recall 函数 | `test_timeline_dedupes_by_file_and_keeps_chunk_order` / `test_literal_marks_gap_between_non_adjacent_chunks` |
| 留痕 + `--audit`；写失败不影响检索；覆盖 prep.py | `ledger.py` + `_ledger_append` + `prep.py` | `test_ledger.py` 15 条 + `test_ledger_concurrency.py` 2 条 |
| 留痕按 agent 隔离 | `ledger_path(agent)` | `test_ledger_is_per_agent` / `test_concurrent_appends_across_agents_do_not_interfere` |
| 默认行为逐位不变 | `format_recall_output(header=None)` / `_date_clause` | `test_default_format_output_is_byte_identical`；全量 265→320 passed 无回归 |
| 移走 `dailynote/` 仍能答 | 两条通道只查 `recall.db` | `test_channels_survive_dailynote_removal` + 真库副本手工验证 |

## 测试

- G1 基线：**265 passed / 6 skipped**（`bd55672`）
- G2 终态：**320 passed / 6 skipped**（+55，全为新增，零回归）
- 手工对抗探针：`tests/probe_adversarial.py` 全绿（LIKE 注入面 / 日期边界 / 超大规模 k / 坏库 / 孤儿 chunk）
- 真库对抗：只复制 `recall.db`、无 `dailynote/` 目录 → 两条通道正常返回

## 真相回写

- `docs/adr/0002-md-is-source-not-index.md`（新增 ADR，含两条实证）
- `PROJECT.md`：模块地图 +`ledger.py`；核心流程新增"检索通道选择"；关键数据结构 +`retrieval_ledger.jsonl`；约束新增"检索只走库"；功能清单更新
- `CONTEXT.md`：术语表新增 检索通道 / 联想通道 / 确定性通道 / 检索留痕 / md 源文件
- `SKILL.md`：新增「检索通道铁律」「查询派生协议」，触发条件表补三行，召回调用补确定性通道示例

## 范围外（本轮不做）

- 物理隔离 md（加密/移出可读区）：md 仍需可读可备份，本 ADR 只剥夺它的索引角色
- `prep.py` 自动追加时间轴：隐藏行为变更，违反"关闭时逐位等于旧行为"
- 服务端检索通道（`docs/server-side-plan.md` 另议）
- 关键词抽取模型化：抽词是上层 AI 的职责，脚本只提供 `--query` 注入点
- **既有测试的临时库泄漏**：`TemporaryDirectory(ignore_cleanup_errors=True)` 在 Windows 上会漏掉 `recall.db`（跑一轮全量泄漏 ~35MB，本次开发中曾把 C 盘塞满触发 `database or disk is full`）。属既有问题，建议单开一票

## 决策点清单（无人值守裁决留痕）

1. **不加"物理隔离 md"**：破坏"md 可读可备份"的既有使用方式，且 ingest/备份/人工查阅链路要重写；用户选择"规则 + 确定性通道"路线。
2. **不给 `prep.py` 自动加时间轴**：避免隐藏行为变更，保住"关闭时逐位等于旧行为"。
3. **`--timeline/--literal` 强制显式身份**：宁可报错也不静默落到 env/default 库——这是隔离墙，不是便利性。
4. **`LIKE` 而非 FTS5**：中文分词 + 迁移成本，当前量级（508 files / 736 chunks）`LIKE` 足够。
5. **留痕只记 `chunk_ids` 前 50 个**：留痕用于"证明查过"，不用于复现召回全集。
6. **字面命中上限 200 字**：超过必然触发 SQLite LIKE 上限，与其崩溃不如报错。
7. **跨进程并发追加未覆盖**：`threading.Lock` 只锁进程内；多进程同时写同一 ledger 仍可能丢行。当前使用场景是单 CLI 进程，够用；要并发需上文件锁。
8. **审查由我自己完成**：两次派出的独立审查 subagent 都因环境问题（C 盘满 / 子代理自身崩溃）未产出报告，改为逐行自审 + 对抗探针覆盖。
