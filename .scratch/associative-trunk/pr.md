## 用户故事

作为记忆的使用者（赖老师），我想要「**十月以后关于备课的进展**」这种**时间 × 语义**的混合问题一次问出口，以便不用先查时间轴、再查联想、再自己对齐两个结果。

Closes #7

## 背景 / 为什么要变

#5 把检索拆成"三条并列通道"，拆过头了：它把同一件事的两个维度（相关性 vs 时间范围）误当成两种不同的东西。后果是 CLI 直接拒绝 `--query --since` 组合，"十月以后关于备课的"只能两次调用再人工对齐，而且语义那条腿的候选池**不受时间窗约束**——会越界捞回八月的记忆。

**实证（qinglan 真库，同一句"十月以后关于备课的有哪些"）**：

| 调用 | 结果 |
|---|---|
| 两次调用（`--timeline --since` + `--query` 不设窗） | 语义腿全被 09-17 的备课模块记忆占满，十月的进不来 |
| 一次调用（`--query "备课 教案 学情 授课" --since 2026-10-01`） | 10-01 / 10-08 / 10-09 / 10-10 / 10-12 / 10-13 / 10-15，**全部在窗内** |

## 实现（三票，按序）

| 票 | commit | 内容 |
|---|---|---|
| 票1 时间窗进主干 | `8bfdc84` | `recall` / `recall_associative` / `recall_by_identity` / `auto_recall` / `expand_tag_candidates` 全链路透传；窗口压在**候选池阶段**（不是排完再筛）；缓存键含窗口；CLI `--query --since/--until` |
| 票2 默认入口 | `ccf0125` | `prep_for_reply` / `prep.py` 支持窗口；日期校验与 recall.py 同口径（共享 `normalize_date`）；留痕 `extra.since/until` |
| 票3 形态收敛 | `a2ad4bb` | SKILL.md 重写为「一条主干 + 两个约束」；ADR-0003；PROJECT/CONTEXT 回写；契约测试锁定新表述 |
| 探针 | 8d8f5f3 | 时间窗 × prefilter / multi_scale / MMR / cache 组合矩阵 + "窗口必须真的收窄"断言 |

### 审查后追加的修复（"报错不指参数"类静默失败）

| commit | 修的是什么 |
|---|---|
| `6a82620` | **CLI 参数解析统一收口**：`--since --budget 500`（PowerShell 丢空串时）会把 `--budget` 当日期、`500` 报 Unknown option——报错指向错误的参数；`--timeline --identity X` 直接 `int()` 崩出裸 traceback。现在 `take_value / take_int / take_float` 共享口径，缺值/非数字一律 `Usage: --xxx 缺少值` 退出码 2，`recall.py` 与 `prep.py` 同修。#5 曾给 `--literal` 修过同款，这次把其余参数全部收进同一防线；红→绿测试 `test_window_flag_does_not_swallow_next_flag[recall/prep]` 锁定 |
| `51d0d5b` | MCP `recall_search` 暴露 `since/until`——工具面与 CLI 主干对齐，走 MCP 的运行时也能一次问"时间 × 语义" |
| `9149436` | **审计行显示窗口**：`--audit` 输出新增 `window=[起, 止]`。窗内只命中 1 条是正确答案，但审计者看不见窗口就会误判"检索坏了"；顺带清掉 SKILL.md 残留的"两条确定性通道"旧表述 |

**核心设计**（ADR-0003）：约束 ≠ 排序。时间窗过滤候选池（"在哪些记忆里找"），联想主干在其内排序（"哪条最像"）。窗口必须同时压两处——向量层 SQL 和 tag-first 扩增的元数据查询；只压一处，窗外记忆会从标签后门溜回来。`--timeline` / `--literal` 保留，重新定位为"约束的退化形态"（只要过滤、不要排序）。

## 验收对照

| 验收标准 | 实现 | 测试 |
|---|---|---|
| `--query --since/--until` 可用，窗口在候选池阶段过滤 | `recall()` SQL `{filter}{window}` | `test_recall_window_filters_candidates` 等 3 条 |
| 窗口同样约束 tag-first 扩增 | `expand_tag_candidates(since, until)` | `test_tag_expansion_cannot_leak_outside_window` |
| 缓存键含窗口（带窗/不带窗不互串） | `_cache_key(..., since, until)` | `test_cache_does_not_conflate_windowed_and_unwindowed` / `test_cache_key_differs_by_window` |
| 闭区间；非法格式/倒序区间报错退出码 2 | `normalize_date` 共享口径 | `test_cli_query_window_rejects_bad_dates` + 探针矩阵 |
| `prep.py` 支持窗口 | `prep_for_reply(since, until)` | `test_prep_for_reply_accepts_window` 等 3 条 |
| 留痕记录窗口 | `extra.since/until` | `test_cli_query_window_logs_window_in_ledger` / `test_prep_cli_with_window_writes_ledger_with_window` |
| 不给窗口逐位不变 | 默认 None → SQL 片段为空串 | 全量 339 passed 零回归（基线 320 + 新增 19） |
| `--auto` 下窗口生效 | `auto_recall(since, until)` | `test_auto_recall_passes_window` |
| 文档收敛为"主干+约束" | SKILL.md 重写 + ADR-0003 | `test_skill_declares_trunk_plus_constraints` 等 4 条契约测试 |

## 测试

- G1 基线：**320 passed / 6 skipped**（`6a95f4e`）
- G2 终态：**343 passed / 6 skipped**（+23，零回归）
- 对抗探针：`tests/probe_adversarial.py` 全绿（新增窗口矩阵 10 项，含"窗口反而变宽"与"窗外混入"两条硬断言）
- 真库验证：见上方实证表

## 真相回写

- `docs/adr/0003-associative-trunk-with-constraints.md`（新增，修订 ADR-0002 的"三通道"表述）
- `SKILL.md`：「检索铁律（一条主干 + 两个约束）」+ 触发条件表新增"时间 × 语义"行 + 召回示例
- `PROJECT.md`：核心流程 4 重写；模块表、数据结构、功能清单同步
- `CONTEXT.md`：术语改为 联想主干 / 时间窗约束 / 字面约束，「检索通道」定义修正并引用 ADR-0003

## 范围外（本轮不做）

- 相对日期解析（"上周""国庆后"由上层 AI 换算成绝对日期再传，脚本不猜）
- 多时间窗 OR 组合
- FTS5 / 跨 agent 窗口查询

## 决策点清单（自主裁决留痕）

1. **窗口压 SQL 而非排完再筛**：排完再筛会少返回甚至空（top-k 被窗外占满）。
2. **`--timeline/--literal` 保留不合并**：它们是"只要过滤不要排序"的退化形态，硬套主干反而多算一遍向量。
3. **日期校验共享 `normalize_date`**：prep.py 与 recall.py 同口径，避免两处漂移。
4. **缓存键必须含窗口**：否则带窗查询命中不带窗的缓存 = 脏读，窗口形同虚设。
5. **时间窗只认 `YYYY-MM-DD`**：猜错时间窗比不设窗更糟，相对日期交给上层 AI。
