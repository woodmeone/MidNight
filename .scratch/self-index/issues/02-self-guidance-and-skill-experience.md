# 02 — self.md 路径指路 + 能力经验日记约定

Issue: #10 ｜ Spec: `../spec.md` ｜ Blocked by: 无 ｜ 分支: `feat/self-index`

> **本文件自包含**。执行方不需要看任何对话历史。
> 所有路径相对仓库根 `D:\Project\globalSkills-library\MidNight`。

---

## 用户故事

作为**一个遇到不会的活儿的智能体**，我想要记得「先查技能库」这个动作，
也记得「哪个 skill 用起来什么感觉」，以便不用每会话被告知一遍有什么可选，
还能把踩过的坑变成下次的判断。

---

## 背景 / 为什么要变

Issue #9 只解决了**长期内容**。能力和同伴呢？讨论结论是**都不进开机清单**：

- **能力**：存在性写进 `self.md` 一句就永久有效；经验靠记忆积累（已跑通——
  `prep.py` 现在就会召回「`recall.py` 没有 `--tag-weight`，传了直接 `exit 1`」这类教训）。
- **同伴**：遗漏代价低（想不起 mira 还能自己干，想不起 image-gen 是真不知道怎么做——两件事不对称），
  且「该问谁」联想能带出来（实测：查「协作」时库自己把贸贸/kaka/阿散带了回来）。

但现在 `self.md` **没有地方放这两句话**，也没有约定把 skill 经验写成可召回的日记。

### 第一性：为什么是「指路」而不是「清单」

| | 谁生出来的 | 会变吗 | 怎么知道它存在 |
|---|---|---|---|
| 长期内容 | 自己建、会增删改 | 快（周/月） | **只能扫**，写死人设就过期 |
| 能力 | 外部给（技能库） | 随版本 | **一句指路**，一次成本永久有效 |
| 同伴 | 外部给（目录） | 少 | **一句指路** |

**自己长出来的要扫，外面给的只要一句指路。**

---

## 实现规格

### 改动一：`skills/recall/scripts/self_model.py`

#### 1.1 新增常量

放在 `DEFAULT_TEMPLATE` 上方：

```python
# 路径指路的两句默认文案。可动层字段，允许演变，但不该被静默删除。
DEFAULT_PATHS = [
    '遇到不会的活，先查技能库——那里有现成的做法，别自己从零造。',
    '有事可以问同伴，别一个人硬扛。',
]
```

#### 1.2 扩展 `DEFAULT_TEMPLATE`

```python
DEFAULT_TEMPLATE = {
    'name': 'midnight-agent',
    'anchor_tags': ['midnight'],
    'mutable': {
        'persona_style': '冷静、高效、务实的助手',
        'capabilities': ['记忆', '联想', '执行'],
        'paths': DEFAULT_PATHS,          # ← 新增这一行
    },
    'description': (...)                  # 原样不动
}
```

#### 1.3 新增函数 `add_paths`

```python
def add_paths(agent: str = None) -> dict:
    """给已有 self.md 补 paths。幂等：已有 paths（非空）则原样不动。

    返回 {'added': bool, 'paths': list}
    """
```

行为：

| 情况 | 动作 | 返回 |
|---|---|---|
| 无 `self.md` | 先 `ensure_self(agent)`（会带上默认 paths） | `{'added': True, 'paths': DEFAULT_PATHS}` |
| 有 `self.md`，`mutable.paths` 缺失或为空 | 用 `update_self(agent, {'paths': DEFAULT_PATHS})` 补上 | `{'added': True, 'paths': DEFAULT_PATHS}` |
| 有 `self.md`，`mutable.paths` 已有内容 | **不动一个字节** | `{'added': False, 'paths': 现有值}` |

**关键**：`ensure_self` 现有语义是「无则建，已有则幂等不动」，本 Issue **不改这个语义**。
所以老用户的 self.md 不会被 `--init` 悄悄改写。

#### 1.4 CLI 新增 `--add-paths`

```
python self_model.py --add-paths [--agent X]
```

- 成功时打印 `{"status": "ok", "added": true|false, "path": "<self.md 绝对路径>"}`（JSON，`ensure_ascii=False`）
- 退出码 0；`self.md` 读写失败时退出码 1 并给 stderr 人话

用法文档要写进 docstring：**这是自愿动作，AI 或人显式调用才补，不自动跑。**

---

### 改动二：`skills/recall/scripts/session_start.py`

#### 2.1 摘要带上 paths 的极短形式

`compile_identity_summary()` 里，在 `capabilities` 那段之后追加：

```python
paths = mutable.get('paths')
if paths:
    parts.append('路径:先查技能库·有事问同伴')
```

- **固定短串**，不动态截取 `paths` 内容（动态截取容易产出半句，违背「不拦腰硬截」）
- 全角间隔号 `·`，无空格
- 追加位置：在 `能力:` 之后、`CAPABILITY_ANCHOR_TEXT` 之前
- 整段约 14 字

#### 2.2 预算

Issue #9 的开机清单硬预算是 120 字。本句约 14 字，必须**优先于「风格」保留**——
被砍顺序是：资产条目 → 能力类目 → 风格 → **路径（倒数第二才砍）** → 姓名（永不砍）。

这个顺序写进 Issue #9 的 `boot.py` L1–L6 裁剪表。本 Issue 只在 `session_start.py` 里加这一句，
不动裁剪逻辑（那是 #9 的活）。

---

### 改动三：`skills/recall/SKILL.md`

新增一节，放在「写日记协议」之后、「身份绑定」之前：

```markdown
## 能力经验（skill 经验）

用 skill 时顺手或难受，都要记一条日记。**这条日记比 skill 本身更值钱**——skill 会换，踩过的坑不会。

约定：

- `tags` 必带 `skill经验`；难受时**必带** `踩坑`（顺手的不必提醒，踩过的才需要）
- 正文写三层：什么场合好用 / 什么场合不好用 / **判断标准**
- **不打分**。「tdd = 3.2 分」什么都说明不了，「tdd 在没测试的代码上会卡」直接可行动
- 存在性不写日记——技能库是外部真相，用 `self.md` 的「路径」指路，现查现用

样例：

```yaml
---
maid: kaibian
created: 2026-11-14T21:08:55
importance: medium
tags: [skill经验, tdd, 重构, 老代码, 踩坑]
---
核心概念：遗留代码库做重构，tdd skill 要求先补测试，卡在「没有测试可跑」。
关键原理：它假设已有测试骨架；遗留代码里这个前提不成立。
应用场景：新项目、已有测试覆盖的模块很顺；遗留代码先补测试再上。
反思与洞察：不是它不好，是我用错了场合。判断标准看有没有测试基线。
```
```

---

### 改动四：`skills/recall/tests/test_skill_contract.py`

新增契约测试（该文件已有 `REPO_ROOT` 与 `_read` 工具，直接复用）：

| # | 测试名 | 断言 |
|---|---|---|
| 17 | `test_skill_md_has_skill_experience_section` | `SKILL.md` 含 `## 能力经验`、`skill经验`、`踩坑`、`不打分` |
| 18 | `test_skill_md_says_paths_not_catalog` | `SKILL.md` 含「一句指路」或「现查现用」，且**不含**「开机清单里列 skill」这类表述 |
| 19 | `test_default_template_keeps_paths` | `DEFAULT_TEMPLATE['mutable']['paths']` 非空，且两句话各含「技能库」「同伴」 |

---

### 改动五：`skills/recall/README.md`

「它能做什么」下加一条：

```
- **路径指路**：能力与同伴不进开机清单——`self.md` 写两句，一次成本永久有效
```

---

## 测试

新建 `skills/recall/tests/test_self_paths.py`。fixture 照抄 `tests/test_session_start.py`：

```python
@pytest.fixture
def basedir():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        old_base = cfg.BASE_DIR
        cfg.BASE_DIR = tmp
        yield tmp
        cfg.BASE_DIR = old_base
```

### 必须有的用例

| # | 测试名 | 断言 |
|---|---|---|
| 1 | `test_default_template_has_paths` | `DEFAULT_TEMPLATE['mutable']['paths']` 长度 2，含「技能库」与「同伴」 |
| 2 | `test_init_writes_paths` | 新 agent 调 `ensure_self` → 写出的 self.md 里 `mutable.paths` 是那两句 |
| 3 | `test_init_does_not_touch_existing_self` | 已有 self.md（无 paths）→ `ensure_self` 后文件内容**逐字节不变** |
| 4 | `test_add_paths_fills_missing` | 已有 self.md 无 paths → `add_paths` 返回 `added=True`，文件里出现那两句 |
| 5 | `test_add_paths_noop_when_present` | 已有自定义 paths → `add_paths` 返回 `added=False`，文件内容不变 |
| 6 | `test_add_paths_creates_when_absent` | 无 self.md → `add_paths` 建出带 paths 的 self.md |
| 7 | `test_summary_contains_path_hint` | `compile_identity_summary` 输出含 `路径:先查技能库·有事问同伴` |
| 8 | `test_summary_without_paths_omits_hint` | self.md 的 mutable 无 paths → 摘要**不含** `路径:`，且不报错 |
| 9 | `test_summary_keeps_no_truncation` | 超长 persona_style 仍完整保留，不出现 `…`（复用现有行为） |
| 10 | `test_cli_add_paths_json_output` | `main(['--add-paths','--agent',a])` → 退出码 0，输出可 `json.loads` |
| 11 | `test_evolution_can_still_patch_paths` | `evolution.update_self(agent, {'paths': ['自定义']})` 生效（paths 是可动层，不被 protected） |
| 12 | `test_evolution_rejects_immutable` | `update_self(agent, {'name': 'x'})` 被拒（现有行为不回归） |

### 跑法

```bash
cd D:\Project\globalSkills-library\MidNight\skills\recall
python -m pytest tests/test_self_paths.py tests/test_skill_contract.py -q
python -m pytest tests -q
```

**G1 基线：343 passed / 6 skipped。**
本 Issue 完成后应为 **358 passed / 6 skipped**（+12 新测试 +3 契约测试 = +15；
若 `test_skill_contract.py` 的 3 条并入现有文件计数，按实际数字核对，**失败数必须为 0**）。

---

## 验收标准

- [ ] `DEFAULT_PATHS` 常量存在，两句文案与规格一致
- [ ] `DEFAULT_TEMPLATE['mutable']['paths'] = DEFAULT_PATHS`
- [ ] `add_paths(agent)` 幂等：已有 paths 不动；缺失才补
- [ ] `ensure_self` **语义不变**：已有 self.md 不被改写
- [ ] CLI `--add-paths` 可用，输出 JSON，退出码 0
- [ ] `compile_identity_summary` 含 `路径:先查技能库·有事问同伴`
- [ ] `SKILL.md` 有「## 能力经验（skill 经验）」章节，含标签约定与「不打分」
- [ ] `test_skill_contract.py` 加 3 条契约测试且全绿
- [ ] 新增 12 个测试全绿；全量失败数为 0
- [ ] **不碰任何 `~/.midnight/recall/*/recall.db`**

## 票（垂直切片，按序实现）

- [ ] **票1：模板与初始化** —— `DEFAULT_PATHS` + `DEFAULT_TEMPLATE` + `add_paths` + `--add-paths`，覆盖测试 1–6、10 ｜ Blocked by: 无
- [ ] **票2：摘要带路径** —— `compile_identity_summary` 追加极短路径提示，覆盖测试 7–9、11、12 ｜ Blocked by: 票1
- [ ] **票3：文档与契约** —— `SKILL.md` 能力经验章节 + `README.md` + 契约测试，覆盖测试 17–19 ｜ Blocked by: 票1

每张票 = 一个 commit，message 带 `(#10)`。

## 范围外（本轮不做）

- **不自动改任何已存在的 `self.md`**——自我认知是智能体自己的，只能在它自愿时补
- **不做技能库扫描**（存在性靠一句指路，不扫）
- **不做同伴扫描/名单**
- **不给 skill 打分**、不建熟练度字段
- 不改 `boot.py` 的裁剪逻辑（Issue #9 的活）
- 不改任何 `~/.midnight/recall/*/recall.db`

## 对抗式自检（写测试时问自己）

- 老 self.md 有 `mutable` 但没 `paths` → `--init` 会不会覆盖？**必须不动**
- `mutable` 是坏 JSON → `_parse_self` 返回 `{}`，崩不崩
- `paths` 写成列表还是字符串，两种都要能读（`add_paths` 判空时两者都算「有」）
- 摘要超预算时这条路径句会不会被整句砍掉？砍了等于白写——它应比风格描述更优先保留
- 被 `evolution.py --apply` 改掉 `paths` 怎么办？可动层允许改，`evolution.log` 已留痕
- 中文/英文混排的两句文案 → 摘要里固定短串，不受影响
- `--add-paths` 在无 self.md 且无 agent 名时（环境变量兜底）→ 不崩

## 真相影响

- **CONTEXT.md**：新增术语 **能力经验（skill experience）**——某个 skill/工具「什么场合好用、
  什么场合不好用」的判断；存在形式是日记，靠联想召回，不打分。
- **PROJECT.md**：`self_model.py` 职责补「含路径指路（paths）」；"核心业务流程·自我模型"补 `--add-paths`。
- **ADR**：无新增（并入 ADR-0004 的「能力/同伴为什么不进清单」一节）。
