# 08 — SKILL.md 与实现对齐（文档纠错）

Issue: #17 ｜ Spec: `../spec.md` ｜ Blocked by: 无 ｜ 分支: `feat/self-index`

> 本文件自包含。**全是文档与实现不符的硬错**，没有设计争议，照着改即可。
> 每一条都附了实测证据与原文行号。

---

## 实测证据

```console
$ python recall.py --identity seagull --query "test" --tag-weight 0.5
Unknown option: --tag-weight

$ python prep.py --message "test" --identity seagull --truncate 0.5
Unknown option: --truncate

$ python prep.py --message "test" --identity seagull --time-ratio 0.5
Unknown option: --time-ratio
```

```console
$ ls skills/recall/scripts/*.py
boot.py  cache.py  config.py  download_bge_m3.py  embedding.py  evolution.py
harvest.py  ingest.py  ledger.py  maintenance.py  ngrams.py  paths.py  prep.py
recall.py  reembed.py  schema.py  self_model.py  session_start.py  tag_network.py
```

```console
$ test -d skills/recall/references && echo yes || echo no
no
```

---

## 问题清单

### A. 路由表整张是假的（最严重）

`SKILL.md:379-390` 的路由表，表头就是 `k | tag_weight | time_ratio | truncate`。

**`tag_weight` / `time_ratio` / `truncate` 这三个参数，`recall.py` 和 `prep.py` 的 CLI 都不认。**
它们只存在于库函数 `recall_associative()` 的签名里，CLI 从没暴露。

照着这张表敲命令，一律 `Unknown option` 退出 2。

同样问题还在：

| 行号 | 原文 | 问题 |
|---|---|---|
| 366 | `recall.py --identity qinglan --query "..." --k 10 --tag-weight 0.5 --time-ratio 0.3 --truncate 0.5` | 后三个参数不存在 |
| 15 | 「联想强度、时间权重、截断比例（`--truncate`，按条数比例裁剪）均可调」 | 从 CLI **不可调**；且 `prep_for_reply()` 连 `truncate` 形参都没有 |

### B. 文件结构漏了 7 个脚本

`SKILL.md:465-491` 的树里缺：

```
boot.py  cache.py  config.py  download_bge_m3.py  ngrams.py  paths.py  reembed.py
```

其中 **`boot.py` 是这次 feature 的核心产出**，却没进文件结构——新人读文档根本不知道它存在。

tests 列表也全是旧的（`test_ticket01~04` 等），现在实际有 20+ 个测试文件。

### C. `references/` 目录不存在

`SKILL.md:490` 写着 `└── references/  # 按需加载的深度参考`，实际没这个目录。

### D. `session_start.py` 的描述已过期

`SKILL.md:476` 写 `# 首轮上下文轻编译（身份摘要 ≤200 字）`。

实现早已改成**不截断**（`session_start.py:42` 原文：「不设长度上限、不截断：身份是最基础的，短则尽短，长则完整」）。
「≤200 字」是旧规格，留在文档里会让人以为超长会被砍。

### E. `ingest.py` 的用法让人困惑

`SKILL.md:457` 写 `python ingest.py ~/.midnight/recall/default/dailynote/`（位置参数）。

`ingest.py` 的 CLI 是 `[file_or_dir] [--agent NAME] [--db PATH] [--diary PATH]`。
位置参数给绝对目录时，**库路径仍按 `--agent`（或 env/default）推导**——两者可以指向不同的 agent，
文档没说清。应改成推荐写法 `--agent`，位置参数只作显式覆盖。

---

## 用户故事

作为**第一次读这个 skill 的人**，我想要文档里每条命令都能直接复制粘贴跑通，
以便不用先踩一遍坑才知道哪些是过期的。

---

## 实现规格

### 改动一：重写路由表（379-390）

删掉参数矩阵，改成「场景 → 命令」，**只列 CLI 真能用的参数**：

```markdown
## 场景路由

按场景选命令，参数都是 CLI 真支持的：

| 场景 | 命令 |
|---|---|
| 每次回复前（默认） | `prep.py --message "用户原话" --identity <名字>` |
| 新会话开始 | `boot.py --identity <名字>` 一次 + `prep.py` 补最近记忆 |
| 「还记得吗」类，要更多条 | `prep.py --message "..." --identity <名字> --k 20` |
| 要多样、别重复 | `prep.py --message "..." --identity <名字> --mmr 0.5` |
| 长句里藏线索 | `prep.py --message "..." --identity <名字> --multi-scale` |
| 控注入体积 | `prep.py --message "..." --identity <名字> --budget 2000` |
| 时间 × 语义 | `prep.py --message "..." --query "备课 教案" --identity <名字> --since 2026-10-01` |
| 只写日记不召回 | 不跑命令，直接写 md |

**`--k` / `--budget` / `--mmr` / `--multi-scale` / `--since` / `--until` 都在 `prep.py` 上。**
`tag_weight` / `time_ratio` / `truncate` 只存在于库函数 `recall_associative()`，
CLI 不暴露——**要用就走 Python API，别在命令行试**。
```

### 改动二：修第 366 行的示例

```bash
# 改成 CLI 真支持的
python recall.py --identity qinglan --query "用户的问题" --k 10
```

并在下面补一句：`--tag-weight / --time-ratio / --truncate` 只在
`recall_associative()` 的 Python 签名里，CLI 调不到。

### 改动三：修核心能力第 4 条

```markdown
4. **可配置**：召回数量 `--k`、注入预算 `--budget`、多样性 `--mmr`、
   多尺度线索 `--multi-scale`、时间窗 `--since/--until` 都是 CLI 参数。
   联想强度 / 时间权重 / 截断比例属库函数层（`recall_associative`），CLI 不暴露。
```

### 改动四：更新文件结构（465-491）

按实际 19 个脚本重写，补上 `boot.py` / `paths.py` / `cache.py` / `ngrams.py` /
`config.py` / `reembed.py` / `download_bge_m3.py`，每个一句话职责。

`boot.py` 的说明要写清它是**开机清单**（三级加载第一级），别只说文件名。

tests 部分改成「按主题分文件，见 `tests/` 目录」+ 几个关键文件的说明，不逐个列（会再次过期）。

删掉 `references/` 那一行。

### 改动五：修 session_start 描述

`# 首轮上下文轻编译（身份摘要 ≤200 字）` → `# 首轮上下文轻编译（身份摘要，不截断）`

### 改动六：修 ingest 用法

```bash
# 推荐：显式指定 agent（库路径按 agent 推导，最不容易错）
python ingest.py --agent default

# 显式覆盖目录（位置参数），库仍是 --agent 的那个
python ingest.py /path/to/diary --agent default
```

---

## 测试

`test_skill_contract.py` 目前**没有**锁这些内容，可自由改。但要新增**反向锁**，
防止以后再写回假参数：

| # | 测试名 | 断言 |
|---|---|---|
| 50 | `test_skill_md_has_no_fake_cli_flags` | `SKILL.md` 的命令行代码块里，**不得出现** `--tag-weight` / `--time-ratio` / `--truncate` 作为 CLI 参数 |
| 51 | `test_skill_md_lists_all_scripts` | 实际存在的每个 `scripts/*.py` 都在文件结构里出现 |
| 52 | `test_skill_md_no_phantom_dir` | 不出现 `references/` |

第 50 条是关键：它把「文档教了不存在的参数」这件事**变成测试失败**，而不是靠人记得。

### 跑法

```bash
cd D:\Project\globalSkills-library\MidNight\skills\recall
python -m pytest tests/test_skill_contract.py -q
python -m pytest tests -q
```

---

## 验收标准

- [ ] 路由表里每条命令都能直接跑通（无 `Unknown option`）
- [ ] 全文不再把 `--tag-weight` / `--time-ratio` / `--truncate` 当 CLI 参数教
- [ ] 文件结构含全部 19 个脚本，`boot.py` 说明是「开机清单」
- [ ] `references/` 一行已删
- [ ] `session_start.py` 描述不再说「≤200 字」
- [ ] `ingest.py` 用法改为 `--agent` 优先
- [ ] 新增 3 条反向锁测试全绿；全量失败 0

## 票（垂直切片）

- [ ] 票1：路由表 + 第366行 + 核心能力第4条（三处假参数一起改）｜ Blocked by: 无
- [ ] 票2：文件结构 + references + session_start 描述 ｜ Blocked by: 无
- [ ] 票3：ingest 用法 + 3 条反向锁测试 ｜ Blocked by: 票1

## 范围外（本轮不做）

- **不给 CLI 新增 `--tag-weight` 等参数**——那是功能需求，另开 Issue 评估
- 不动 `recall.py` / `prep.py` 的代码
- 不重写整份 SKILL.md（只改这 6 处，其余保留）

## 真相影响

- **PROJECT.md**：不用改（文件结构在 SKILL.md 里，PROJECT 的模块地图已同步）
- **CONTEXT.md**：不用改
- **ADR**：无
