# Spec — 联想优先检索（associative-first retrieval）

> Issue: [#5](https://github.com/woodmeone/MidNight/issues/5)
> 分支：`feat/issue-5-associative-first` ｜ fixed point：`bd55672` ｜ 测试基线：265 passed / 6 skipped

## 1. 问题到什么程度（第一性）

不是"AI 手贱去读文件"，是**能力缺口 + 成本错觉 + 无痕迹**三者叠加：

| 缺口 | 表现 | 结果 |
|---|---|---|
| 能力 | 联想召回是相关性排序，答不了"最新一条 / 记到哪天 / 有没有提过某词" | 没有正解 → 翻文件成了唯一理性选择 |
| 成本 | grep 一次调用确定性命中；召回要拼 query、赌相似度 | 翻文件更"划算" |
| 可见性 | 走没走算法无记录 | "我走了联想"只能靠自述 |

所以只写"禁止"没用：**禁令压不住一个没有替代方案的需求**。本轮的解法是"补路 + 立规 + 留痕"三件套。

## 2. 设计

### 2.1 三条通道，一个数据源

```
                 ┌──────────── recall.db（唯一检索数据源，按 agent 物理隔离）
                 │
聊天上下文 ──► 联想通道（默认，自动）        prep.py / recall.py --query
        │        └─ 向量 KNN + 标签脉冲 + 时间加权 + tag-first 扩增 + MMR
        │
        ├──► 确定性通道（结构性时间/字面问题） recall.py --timeline/--literal/--since/--until
        │
        └──► md 原文（仅用户显式授权）        read/grep dailynote/*.md
                 └─ 例外，且必须在回复里声明"这是你授权的原文通道"
```

三条通道的共同约束：身份隔离、输出格式（`[回忆]` 块）、预算/去重、留痕。

**为什么确定性通道也必须存在**：如果"记到哪天"只能靠翻文件答，规则就是一张废纸。把这类问题变成库内一次 SQL，禁读才有意义——**消除动机优于增加禁令**。

**为什么 md 仍然留在原地**：`dailynote/*.md` 是真相源（ingest 的输入、备份本体、人可读的存档）。真相源不能删，但它**不是索引**——索引是 `recall.db`。

### 2.2 检索留痕（ledger）

`<agent_dir>/retrieval_ledger.jsonl`，一次 CLI 检索一行：

```json
{"ts": "2026-10-21T14:01:02", "agent": "qinglan", "channel": "associative",
 "query": "当老师 教师 教学", "hits": 8, "chunk_ids": [12, 15, 19], "extra": {"multi_scale": true}}
```

- **旁路性质**：写入失败必须吞掉异常，绝不影响检索返回（磁盘满/只读挂载下检索照常）。
- **只读接口**：`--audit [N]` 打印最近 N 行；不做统计聚合（那是人/工具的事）。
- **只写入口**：留痕写在 CLI 层，不写进 `recall_associative`/`prep_for_reply` 这类库函数——库函数保持纯净、单测不污染真实目录。

### 2.3 查询派生协议（"自主剖析关键词"的落点）

抽词是**上层 AI 的职责**（它读上下文），脚本只提供注入点。协议固化成 SKILL.md 的一节：

1. 从用户这句 + 当前会话上下文里抽 **2–5 个名词性线索**（人、事、术语、地点），不要抽"今天/压力/帮我"这类泛词；
2. 把**当前对话的对象 anchor** 带上（如 `赖老师`、`学生`），对象标签规约（V2）在检索侧自然生效；
3. 拼成空格分隔的 `--query`，默认加 `--multi-scale`（整句/关键词/短语三尺度各自感应标签种子）；
4. 原话本身不是好 query——寒暄和指代会稀释向量。

## 3. API（增量，不破默认）

### `recall.py`

| flag | 语义 | 默认 |
|---|---|---|
| `--timeline N` | 最近 N 篇日记（按 `diary_date` 倒序，file 级去重，块按 `chunk_index` 拼接） | 关闭 |
| `--since YYYY-MM-DD` | 日期下限（含） | 无 |
| `--until YYYY-MM-DD` | 日期上限（含） | 无 |
| `--literal "词语"` | 字面命中（`LIKE`，转义 `% _ \`），file 级去重 | 关闭 |
| `--audit [N]` | 打印最近 N 行留痕，默认 20 | 关闭 |

- `--timeline/--literal` **必须**显式带 `--identity/--agent`，缺失 → usage + exit 2（不静默落 env/default 库）。
- 结果 dict 沿用 `{chunk_id, content, date, score, file_path, importance}`，直接复用 `dedupe_results` / `fit_to_budget` / `format_recall_output`。
- `format_recall_output` 增加可选 `header` 参数，默认 `None` → 输出与改动前逐字节一致。

### `ledger.py`（新）

```python
append_entry(channel, query, results=None, agent=None, extra=None, now=None) -> bool
read_entries(agent=None, limit=20) -> list[dict]
ledger_path(agent=None) -> str
```

## 4. 对抗清单（测试必须覆盖）

| 攻击面 | 断言 |
|---|---|
| 有人把 `dailynote/` 移走 | `--timeline`/`--literal` 仍能答（证明不依赖 md） |
| 跨 agent 偷看 | A 的 timeline/literal/ledger 不含 B 的内容 |
| 不显式声明身份 | 退出码 2，不落任何库 |
| 多块日记 | 同一 file 只出现一次，正文按块序拼接 |
| 空库 / 不存在日期 | 输出"暂无相关记忆"，不崩 |
| `--literal "%"` / `"_"` | 按字面匹配，不退化成通配符 |
| ledger 只读 / 损坏行 | 检索正常返回；坏行跳过，不抛 |
| 默认路径回归 | 不带新 flag 的输出与改动前逐字节一致 |

## 5. 非目标

- 物理隔离 md（加密/移走）：破坏"md 是真相源、永不删"，ingest/备份要重写。
- `prep.py` 自动追加时间轴：隐藏行为变更，违反"关闭时逐位等于旧行为"。
- 服务端检索通道：另议（`docs/server-side-plan.md`）。
