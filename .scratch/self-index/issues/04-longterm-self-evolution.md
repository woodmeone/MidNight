# 04 — 长期内容的自我维护

Issue: #12 ｜ Spec: `../spec.md` ｜ Blocked by: #9, #10 ｜ 分支: `feat/self-index`

> **本文件自包含**。执行方不需要看任何对话历史。
> **依赖前置**：#9 已交付 `boot.py`；#10 已交付 `DEFAULT_TEMPLATE['mutable']['paths']`。

---

## 用户故事

作为**手里攒着一堆长期内容的智能体**，我想要知道「这些是我自己的东西，想留就留、想扔就扔」，
并且有一个固定时刻提醒我，以便长期内容不会变成只进不出的垃圾场。

---

## 背景 / 为什么要变

#9 只解决了「**看见**」。四段闭环现在只有一段：

| 段 | 问什么 | 现在 |
|---|---|---|
| **感知** | 我有什么 | ✅ #9 |
| **判断** | 什么值得留 | ❌ 缺 |
| **动作** | 建 / 改 / 退休 | ❌ 缺（`write` 能做，但没约定） |
| **触发** | 什么时候想起来 | ❌ 缺 |

**光「看见」不叫自进化，叫有个抽屉。**

### 关键判断：不加判据，只给意识

给判据（准入四问、90 天退休算法）是**替它判断**，违背「智能体自己判断」这条根。
而且规则会过时——120 字对写作智能体太多、对代码智能体太少。

**所以：只给一个问句 + 一句提醒。**

### 触发点是三个时刻，不是「定期」

开编自己在日记里写出了答案：

> 下次项目收尾时应当默认问一句：**这次的哪些动作可以脚本化？**

定期检查靠额外的意志力；收尾那一刻素材还在手上。

---

## 实现规格

### 改动一：`skills/recall/SKILL.md` —— 新增「## 长期内容的维护」章节

放在「## 能力经验（skill 经验）」（#10 新增）之后。**内容四块，一字不减**（契约测试锁第三块与第四块的关键句）。

#### 1.1 什么时候收

```markdown
## 长期内容的维护

**不用判断标准。就问自己一句：**

> **当下有什么，是我想要长期留下来的？**

想到了就收，顺手在 `LONGTERM.md` 里加一行。

**别先问「这个够不够格」——想留就留。** 真没用上，下次你自己会想扔。

（开编自己写过「库大小不是成绩，命中率才是」。这句留着当提示，不当标准。）

### 不限于「动作」

一个工具、一套结构、一份检查表、**一套范式判断**、**一个项目存档**、**一批参考图例**、
一条能改判断的结论——都行。动作只是最容易看见的一类。

**我们不给你任何示例架构。** 类别名、类别数、要不要有类别，全是你的事。
开编那六类不是标准，是它一个月里被自己的活逼出来的——它一开始也没规划过。
照抄别人的分类是错的：**那是别人的活逼出来的，不是你的。**
```

#### 1.2 token 和上下文很宝贵

```markdown
### token 和上下文很宝贵

开机清单每一轮都要占 context。**清单越长，能留给正事的越少。**

上下文有物理上限：塞满了，正事就没地方放。这不是比喻，是真会断。

觉得挤了就合并或退休几项。**这个取舍由你判断，系统不替你定数。**
```

#### 1.3 三个触发点

```markdown
### 什么时候做

**① 建的那一刻** —— 新建任何长期内容，同一次动作里把索引行写进 `LONGTERM.md`。
索引没写等于没建，下次开机看不见它。

**② 收尾那一刻（最重要）** —— 每完成一个项目或一段活，先问一句：

> **这次的哪些动作可以留着下次用？**

不是问「学到了什么」（那是写日记），是问「哪个动作可以脚本化 / 模板化 / 清单化」。
这个问句不必等用户提醒，收尾时默认执行。

**③ 发现索引指空时** —— 打开 `LONGTERM.md` 发现某条指向的文件已经没了，
当场修掉或退休，别让它继续骗人。
```

#### 1.4 退休 + 自进化边界

```markdown
### 什么时候该淘汰

长期内容会过时。**记忆只增不减，长期内容不是。**

判据很简单：**打开 `LONGTERM.md` 挑东西时，如果某一条你自己都想不起来是什么了——当场处理。**

二选一：

- **真没用了** → 移进 `<工作区>/archive/`（不删，只是不再出现在索引和开机清单里）
- **还有用但很久没碰** → 写一条日记说明它为什么还留着，那条日记就是它下次被联想带出来的门

**不许因为「扔了可惜」留着。** 一个你自己都想不起来是什么的东西，正在占开机清单的位置。

### 你能改什么，不能改什么

**人设也是长期内容**（第 0 类，最核心那类）。所以这张表其实是「长期内容里，哪些能自己改」：

| 对象 | 谁能改 | 边界 |
|---|---|---|
| 长期内容 · 工作区目录（你自己分的那些类） | **你自己** | 自由建、改、退休 |
| 长期内容 · 人设可动层（风格 / 能力 / 路径） | 你自己（`evolution.py --apply`） | 每次改在 `evolution.log` 留证据 |
| 长期内容 · 人设定海锚（name / 锚标签 / 自描述） | **只读** | 改写被拒，防跑飞 |
| 把长期内容提升成 skill（进全局技能库） | **要人点头** | 一提升就进了所有会话的能力清单，责任不同 |

**定海锚只读不是「它不算长期内容」，而是「长期内容里唯一禁止自改的那一段」——身份不能漂。**
```

### 改动二：`skills/recall/scripts/self_model.py` —— `DEFAULT_TEMPLATE` 加 `evolution`

```python
# 长期内容的自我维护意识。可动层字段，允许演化，但不该被静默删除。
DEFAULT_EVOLUTION = (
    '长期内容是我自己的：想留就留，不想留就扔，我说了算。'
    '每次收尾先问一句——这次的哪些动作可以留着下次用？'
    'token 和上下文都很宝贵，清单越长，能留给正事的越少。'
)
```

```python
'mutable': {
    'persona_style': ...,
    'capabilities': [...],
    'paths': DEFAULT_PATHS,
    'evolution': DEFAULT_EVOLUTION,      # ← 新增，别并进 paths
},
```

**别并进 `paths`**：#10 的测试锁着 `paths` 长度 2，加第三句会直接红。

新增对称函数：

```python
def add_evolution(agent: str = None) -> dict:
    """给已有 self.md 补 evolution。幂等：已有非空值则不动。
    返回 {'added': bool, 'evolution': str}"""
```

CLI 加 `--add-evolution`，与 `--add-paths` 并列，输出 JSON 同格式。

### 改动三：`session_start.py` —— 摘要带一句提示

`compile_identity_summary()` 在 `paths` 那句之后追加：

```python
evo = mutable.get('evolution')
if evo:
    parts.append('长期内容可自维护')
```

7 个字，固定串。

---

## 测试

新建 `skills/recall/tests/test_longterm_evolution.py`。fixture 照抄 `tests/test_session_start.py`（`cfg.BASE_DIR = tmp`）。

| # | 测试名 | 断言 |
|---|---|---|
| 1 | `test_default_template_has_evolution` | `DEFAULT_TEMPLATE['mutable']['evolution']` 非空，含「收尾」与「下次用」 |
| 2 | `test_paths_length_still_two` | `DEFAULT_TEMPLATE['mutable']['paths']` 仍为 2 项（**#10 不回归**） |
| 3 | `test_add_evolution_fills_missing` | 老 self.md 无 evolution → `add_evolution` 返回 `added=True` |
| 4 | `test_add_evolution_noop_when_present` | 已有自定义 evolution → 返回 `added=False`，文件逐字节不变 |
| 5 | `test_add_evolution_creates_when_absent` | 无 self.md → 建出带 evolution 的 self.md |
| 6 | `test_summary_contains_evolution_hint` | 摘要含 `长期内容可自维护` |
| 7 | `test_summary_without_evolution_omits_hint` | 无该字段 → 摘要不含该串，不报错 |
| 8 | `test_contract_skill_md_has_evolution_section` | `SKILL.md` 含 `## 长期内容的维护`、`想长期留下来的`、`token 和上下文很宝贵`、`收尾那一刻`、`要人点头`、`身份不能漂` |
| 9 | `test_contract_skill_md_has_no_entry_bar` | `SKILL.md` **不含**「准入」「判据表」「反例清单」「90 天」——那些是替它判断 |

第 **8、9** 条是一对：一条锁住该有的，一条锁住不该有的。

### 跑法

```bash
cd D:\Project\globalSkills-library\MidNight\skills\recall
python -m pytest tests/test_longterm_evolution.py -q
python -m pytest tests -q
```

**基线不是固定数字**——执行本 Issue 前先跑一次全量，把当时的 `passed / skipped` 记下来当基线，
本 Issue 完成后应为「基线 + 9」，**失败数必须为 0**。

---

## 实现思路（给执行方）

### 这玩意儿几乎没有代码

两张票都是**改文本**（`SKILL.md`）和一个常量（`DEFAULT_EVOLUTION`）+ 一个四行函数。
没有新文件、没有新命令。

**先写测试 9（不该有的东西）**，再写章节。它会逼你把「准入四问」这种冲动挡在门外。

### 陷阱一：别把章节写成规章

写 `SKILL.md` 时最大的诱惑是"写全"：四问、评分、注意事项、反例清单。
**这些全砍掉了，而且测试 9 会盯着你。**

章节越短，智能体越可能真的照做；越长，越像一份会被跳过的制度文件。

一句话问 + 一句 token 提醒 + 三个时刻 + 一张边界表，够了。

### 陷阱二：`evolution` 字段别和 `paths` 混

#10 的测试锁着 `paths` 长度 2。往 `paths` 里加第三句会直接红。
`add_evolution()` 与 `add_paths()` 并列，互不影响。

### 陷阱三：`add_evolution` 判断空值

`mutable` 来自 `json.loads`，`evolution` 可能是 `None` / `''` / 不存在的 key。
一律 `if (data.get('mutable') or {}).get('evolution'):`，别写 `is not None`。

---

## 验收标准

- [ ] `SKILL.md` 有「## 长期内容的维护」章节，四块齐全
- [ ] 明写「**别先问这个够不够格——想留就留**」与「**系统不替你定数**」
- [ ] 明写「**身份不能漂**」（定海锚只读的理由）
- [ ] **不含**「准入」「判据表」「反例清单」「90 天」（测试 9 锁）
- [ ] `DEFAULT_EVOLUTION` 常量存在并被 `DEFAULT_TEMPLATE['mutable']['evolution']` 引用
- [ ] `paths` 仍为 2 项（#10 不回归）
- [ ] `add_evolution()` 幂等；CLI `--add-evolution` 输出 JSON
- [ ] `compile_identity_summary` 含 `长期内容可自维护`
- [ ] 9 个新测试全绿，全量失败数为 0
- [ ] **不新建任何脚本文件**（本 Issue 无新命令）

## 票（垂直切片，按序实现）

- [ ] **票1：self.md 演化字段** —— `DEFAULT_EVOLUTION` + `add_evolution` + `--add-evolution`，覆盖测试 1–5 ｜ Blocked by: 无
- [ ] **票2：摘要提示** —— `session_start.py` 追加一句，覆盖测试 6、7 ｜ Blocked by: 票1
- [ ] **票3：文档与契约** —— `SKILL.md` 章节 + 测试 8、9 ｜ Blocked by: 无

每张票 = 一个 commit，message 带 `(#12)`。

## 范围外（本轮不做）

- **不做自动维护**：不给「自动删 / 自动改」任何能力，所有动作由智能体或人显式发起
- **不做定期调度**：触发靠流程里的三个时刻，不装闹钟（`midnight-pulse` 是另一个 skill 的事）
- **不做「久未引用」扫描命令**：那是替它判断。判断发生在它打开 `LONGTERM.md` 的那一刻
- **不做提升成 skill 的实现**：只写「要人点头」这条边界
- **不改 `evolution.py` 现有行为**：`--apply` / `--decay` 原封不动
- **不动任何 `~/.midnight/recall/*/recall.db`**

## 对抗式自检

- `evolution` 是空字符串 / 空列表 / 缺失 → `add_evolution` 三种都要判成「缺失」
- 章节里不小心留下「建议」「最好」这类软规定 → 测试 9 抓不到措辞，自己读一遍
- `#10` 并行执行中 → `paths` 长度 2 的测试会互相打架吗（不会，测试在各自文件里）
- `--add-evolution` 在无 self.md 且无 agent 名时 → 不崩
- 摘要里 `路径:` 和 `长期内容可自维护` 同时出现 → 会不会太长（不会，共 20 字）

## 真相影响

- **CONTEXT.md**：新增 **退休（retire）**——长期内容移进 `archive/` 的动作，不删除；
  **长期内容的自我维护**——收 / 触发 / 退休 / 边界四件事的总称
- **PROJECT.md**：「核心业务流程」加第 7 条「维护」；功能清单加「长期内容自我维护」
- **ADR**：并入 `docs/adr/0004-long-term-content-as-files.md` 新增一节
  「为什么只给意识不给判据」（取舍：可控性 vs 判断权归属）
