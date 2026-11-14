# 04 — 长期内容的自进化闭环

Issue: #12 ｜ Spec: `../spec.md` ｜ Blocked by: #9, #10 ｜ 分支: `feat/self-index`

> **本文件自包含**。执行方不需要看任何对话历史。
> 所有路径相对仓库根 `D:\Project\globalSkills-library\MidNight`。
> **依赖前置**：#9 已交付 `boot.py` 与 `scan_longterm()`；#10 已交付 `DEFAULT_TEMPLATE['mutable']['paths']`。

---

## 用户故事

作为**手里攒着一堆长期内容的智能体**，我想要知道「这些是我自己的东西，可以建、可以改、可以退休」，
并且有一个固定时机提醒我做这件事，以便长期内容不会变成只进不出的垃圾场。

---

## 背景 / 为什么要变

#9 只解决了「**看见**」。一个只在开机时被看见、却从没有人告诉它「你可以维护」的库，会长成垃圾场。

闭环需要四段，现在只有第一段：

| 段 | 问什么 | 现在 |
|---|---|---|
| **感知** | 我有什么？ | ✅ #9 已解决（开机清单扫目录） |
| **判断** | 什么值得留、什么该淘汰？ | ❌ 缺：没有准入门槛，也没有淘汰规则 |
| **动作** | 建 / 改 / 退休怎么做？ | ❌ 缺：`write` 能做，但没有约定和格式 |
| **触发** | 什么时候想起来做？ | ❌ 缺：完全靠偶然 |

**光"看见"不叫自进化，叫有个抽屉。**

---

## 关键判断：触发点是「用完那一刻」，不是「定期检查」

开编（`kaibian`）自己在 2026-11-14 的日记里写出了答案：

> 失：我还是先按文档思路做了一遍，是用户提醒才想到存可执行资产。
> **下次项目收尾时应当默认问一句：这次的哪些动作可以脚本化？**

对比两种触发：

| | 定期检查（每周扫一遍） | 收尾一问（用完那一刻） |
|---|---|---|
| 需要什么 | 额外的意志力 + 一个闹钟 | 素材还在手上 |
| 成本 | 要重新回忆「当时为什么这么写」 | 刚踩的坑还热着 |
| 会不会忘 | 会，而且是必然 | 写进流程就不会 |

**所以触发点是三个具体时刻，不是「定期」。**

---

## 实现规格

### 改动一：`skills/recall/SKILL.md` —— 新增「长期内容的维护」章节

放在「## 能力经验（skill 经验）」（#10 新增的）之后。

内容必须包含以下四块，**一字不减**（契约测试会锁）：

#### 1.1 准入门槛（四问）

```markdown
## 长期内容的维护

长期内容是你自己判断、自己留的东西。**怎么分类由你定——没有标准答案，也不该有。**

判据只有一条：

> **下次同类的事再来，它能替我省掉多少「重新想」和「重新做」？**

**不限于「动作」。** 一个工具、一套结构、一份检查表、一套范式判断、一个项目存档、一批参考图例、
一条能改判断的结论——都行。动作只是最容易看见的一类。

**我们不给你任何示例架构。** 类别名、类别数、要不要有类别，全是你的事。
开编那六类不是标准，是它一个月里被自己的活逼出来的——它一开始也没规划过。
照抄别人的分类是错的：**那是别人的活逼出来的，不是你的。**

### 一个东西配不配进来

只问一句：

> **下次同类的事再来，它能替我省掉多少「重新想」和「重新做」？**

省得多就收。省不下就写日记——那是记忆，不是长期内容。

配一条硬约束：**库大小不是成绩，命中率才是。**（这句是开编自己写的，收进来当纪律）

三类东西最容易混进来，先挡住：

- ❌ 一次性的排错记录 → 那是记忆，写日记
- ❌ 抄来的教程全文 → 记一条链接就够，别复制
- ❌ 「以后要努力」这类决心 → 不进库
```

#### 1.2 三个触发点

```markdown
### 什么时候做

**① 建的那一刻** —— 新建任何长期内容，同一次动作里把索引行写进 `LONGTERM.md`。
索引没写等于没建，下次开机看不见它。

**② 收尾那一刻（最重要）** —— 每完成一个项目/一段活，先问一句：

> **这次的哪些动作可以留着下次用？**

不是问「学到了什么」（那是写日记），是问「哪个动作可以脚本化/模板化/清单化」。
这个问句不必等用户提醒，收尾时默认执行。

**③ 发现索引指空时** —— 打开 `LONGTERM.md` 发现某条指向的文件已经没了，
当场修掉或退休，别让它继续骗人。
```

#### 1.3 退休规则

```markdown
### 什么时候该淘汰

长期内容会过时。**记忆只增不减，长期内容不是。**

判据是引用痕迹——「我上次用它是什么时候」：

```bash
python skills/recall/scripts/longterm.py --stale --days 90 --workspace <工作区> --identity <名字>
```

列出来的项，二选一：

- **真没用了** → 移进 `<工作区>/archive/`（不删，只是不再出现在索引和开机清单里）
- **还有用但很久没碰** → 写一条日记说明它为什么还留着，那条日记就是它下次被联想带出来的门

**不许因为「扔了可惜」留着。** 一个你自己都想不起来是什么的东西，正在占用开机清单的预算。
```

#### 1.4 自进化的边界

```markdown
### 你能改什么，不能改什么

| 对象 | 谁能改 | 边界 |
|---|---|---|
| 长期内容（你自己分的那些类） | **你自己** | 自由建、改、退休 |
| `self.md` 可动层（风格/能力/路径） | 你自己（`evolution.py --apply`） | 每次改在 `evolution.log` 留证据 |
| `self.md` 定海锚（name/锚标签/自描述） | **只读** | 改写被拒，防跑飞 |
| 把长期内容提升成 skill（进全局技能库） | **要人点头** | 一提升就进了所有会话的能力清单，责任不同 |
```

### 改动二：`skills/recall/scripts/self_model.py` —— `DEFAULT_TEMPLATE` 加 `evolution`

在 `mutable` 里新增一个字段（**不并入 `paths`**，#10 的测试锁着 `paths` 长度 2）：

```python
DEFAULT_EVOLUTION = (
    '长期内容是我自己的：建它、改它、退休它，我说了算。'
    '每次收尾先问一句——这次的哪些动作可以留着下次用？'
)
```

```python
'mutable': {
    'persona_style': ...,
    'capabilities': [...],
    'paths': DEFAULT_PATHS,
    'evolution': DEFAULT_EVOLUTION,      # ← 新增
},
```

`add_paths()` 的行为**不改**（它只管 `paths`）。新增一个对称函数：

```python
def add_evolution(agent: str = None) -> dict:
    """给已有 self.md 补 evolution。幂等：已有非空值则不动。
    返回 {'added': bool, 'evolution': str}"""
```

CLI 加 `--add-evolution`，与 `--add-paths` 并列，输出 JSON 同格式。

### 改动三：`session_start.py` —— 摘要带一句演化提示

`compile_identity_summary()` 在 `paths` 那句之后追加：

```python
evo = mutable.get('evolution')
if evo:
    parts.append('长期内容可自维护')
```

7 个字，固定串。预算优先级与 `路径:` 同级（倒数第二才砍）。

### 改动四：新建 `skills/recall/scripts/longterm.py`

```python
DEFAULT_STALE_DAYS = 90

def scan_entries(workspace: str) -> list[dict]:
    """扫长期内容条目。返回 [{'name','rel_path','category','mtime'}]，按 rel_path 升序。

    复用 boot.scan_longterm 的目录遍历规则（子目录套子目录算一类），
    但这里要**条目级明细**，不是计数。
    """

def find_stale(entries: list[dict], identity: str, days: int = DEFAULT_STALE_DAYS,
               db_path: str = None) -> list[dict]:
    """对每个条目，查最近 days 天的记忆正文里是否出现过它的名字。

    实现：
    1. 取 `db_path`（缺省 get_db_path(identity)）里 diary_date >= today-days 的全部 chunk 正文
    2. 对每个条目，检查其 `name`（去扩展名的文件名）是否作为子串出现在任一正文中
    3. 一次都没出现 → 加进 stale，附 {'last_seen': 最近一次出现日期 | None}

    注意：只 SELECT，不写库。
    """

def main(argv=None) -> int:
    """CLI: python longterm.py --stale [--days 90] [--workspace PATH] [--identity NAME]"""
```

输出格式（stdout）：

```
[久未引用] 12 项长期内容中 3 项 90 天内没被提起：

  tools/old_preflight.py          最后提及：2026-08-01（105 天前）
  kb/S3-旧框架.md                  最后提及：从未
  templates/v1骨架/                最后提及：2026-07-12（125 天前）

建议：确认无用 → 移进 archive/；还有用 → 写一条日记说明它为什么留着。
```

- 一条都没有时：`[久未引用] 12 项长期内容全部在 90 天内被提起过。`
- `--workspace` 缺省 → 用当前工作目录
- `--identity` 缺省 → `MIDNIGHT_AGENT` 或 `default`
- 长期内容目录不存在 → `[久未引用] 长期内容目录不可用（{path} 不存在）`，退出码 0（不是错误，是还没建）
- **只读**：不写库、不写 ledger

---

## 测试

新建 `skills/recall/tests/test_longterm_evolution.py`。

fixture 照抄 `tests/test_session_start.py`（`cfg.BASE_DIR = tmp`）+ 用 `FakeEmbeddingClient` 入库。

### 必须有的用例

| # | 测试名 | 断言 |
|---|---|---|
| 1 | `test_default_template_has_evolution` | `DEFAULT_TEMPLATE['mutable']['evolution']` 非空，含「收尾」与「下次用」 |
| 2 | `test_paths_length_still_two` | `DEFAULT_TEMPLATE['mutable']['paths']` 仍为 2 项（**#10 不回归**） |
| 3 | `test_add_evolution_fills_missing` | 老 self.md 无 evolution → `add_evolution` 返回 `added=True` |
| 4 | `test_add_evolution_noop_when_present` | 已有自定义 evolution → 返回 `added=False`，文件不变 |
| 5 | `test_summary_contains_evolution_hint` | 摘要含 `长期内容可自维护` |
| 6 | `test_summary_without_evolution_omits_hint` | 无该字段 → 摘要不含该串，不报错 |
| 7 | `test_scan_entries_lists_files` | 建 `tools/a.py`、`kb/S1/b.md` → 返回 2 条，类目分别是 `tools`、`kb` |
| 8 | `test_find_stale_detects_never_mentioned` | 条目名从没进过记忆 → 进 stale，`last_seen=None` |
| 9 | `test_find_stale_respects_window` | 条目在 200 天前的日记里出现过、最近 90 天没有再提 → 进 stale（`last_seen` 是那天的日期） |
| 10 | `test_find_stale_skips_recent` | 条目在 10 天前的日记里出现 → 不进 stale |
| 11 | `test_cli_stale_output_format` | stdout 含 `[久未引用]`、`最后提及`、`建议` |
| 12 | `test_cli_missing_dir_message` | 目录不存在 → 含 `不可用`，退出码 0 |
| 13 | `test_cli_readonly` | 跑前后 `recall.db` checksum 不变 |
| 14 | `test_contract_skill_md_has_evolution_section` | `SKILL.md` 含 `## 长期内容的维护`、`准入门槛`、`收尾那一刻`、`退休`、`要人点头` |

第 **14** 条是契约测试，锁住这四块不能被人「顺手简化」掉。

### 跑法

```bash
cd D:\Project\globalSkills-library\MidNight\skills\recall
python -m pytest tests/test_longterm_evolution.py -q
python -m pytest tests -q
```

**G1 基线（#9/#10 完成后）**：343 + 16 + 15 = **374 passed / 6 skipped**。
本 Issue 完成后 +14，失败数必须为 0。

---

## 验收标准

- [ ] `SKILL.md` 有「## 长期内容的维护」章节，四块齐全：准入门槛四问 / 三个触发点 / 退休规则 / 自进化边界
- [ ] 章节里明写「**库大小不是成绩，命中率才是**」与「**不许因为扔了可惜留着**」
- [ ] `DEFAULT_EVOLUTION` 常量存在；`DEFAULT_TEMPLATE['mutable']['evolution']` 指向它
- [ ] `paths` 仍为 2 项（#10 不回归）
- [ ] `add_evolution()` 幂等；CLI `--add-evolution` 输出 JSON
- [ ] `compile_identity_summary` 含 `长期内容可自维护`
- [ ] `longterm.py --stale` 可用，输出格式与规格一致，**只读不写库**
- [ ] 14 个新测试全绿，全量失败数为 0

## 票（垂直切片，按序实现）

- [ ] **票1：文档四块** —— `SKILL.md` 新增章节，覆盖测试 14 ｜ Blocked by: 无
- [ ] **票2：self.md 演化字段** —— `DEFAULT_EVOLUTION` + `add_evolution` + CLI，覆盖测试 1–4 ｜ Blocked by: 无
- [ ] **票3：摘要提示** —— `session_start.py` 追加，覆盖测试 5、6 ｜ Blocked by: 票2
- [ ] **票4：退休信号** —— `longterm.py`（`scan_entries` / `find_stale` / CLI），覆盖测试 7–13 ｜ Blocked by: #9

每张票 = 一个 commit，message 带 `(#12)`。

## 范围外（本轮不做）

- **不做自动维护**：不给「自动删/自动改」任何能力。所有动作由智能体或人显式发起
- **不做定期调度**：触发靠流程里的三个时刻，不装闹钟（`midnight-pulse` 是另一个 skill 的事）
- **不做提升成 skill 的实现**：只写「要人点头」这条边界，落地是后续 Issue
- **不改 `evolution.py` 现有行为**：`--apply` / `--decay` 原封不动
- **不动任何 `~/.midnight/recall/*/recall.db`**：`longterm.py` 只 SELECT

## 对抗式自检（写测试时问自己）

- 条目名极短（`a.py`）→ 会不会在几乎所有日记里都「出现过」导致永不 stale（子串匹配的假阳性）
- 条目名含中文 → LIKE/子串匹配正常吗（这里是 Python `in`，不是 SQL）
- 同一名字出现在两个类目（`tools/a.py` 与 `kb/a.md`）→ stale 判断会不会串
- `archive/` 目录本身会不会被当成类目扫进来
- 记忆库为空（新智能体）→ 所有条目都 stale，输出会不会爆炸（要不要限条数）
- `--days 0` → 语义是什么
- 目录全空 → `scan_entries` 返回 `[]`，CLI 说什么
- 跑两次 → 输出确定吗

**已知假阳性风险**（写测试时明确接受）：子串匹配会让「名字出现在无关上下文里」也算「被提起」。
这是**故意偏向保守**——宁可漏报 stale（留着），不可错报（误导淘汰）。

## 真相影响

- **CONTEXT.md**：新增术语 **准入门槛（entry bar）**——一个东西配不配进长期内容的四问；
  **退休（retire）**——长期内容移进 `archive/` 的动作，不删除
- **PROJECT.md**：「核心业务流程」加第 7 条「维护」；功能清单加「长期内容自维护闭环」
- **ADR**：并入 `docs/adr/0004-long-term-content-as-files.md` 新增一节
  「为什么触发是收尾一问而不是定期检查」
