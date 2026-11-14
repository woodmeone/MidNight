# 01 — 开机清单：智能体开机就知道自己的长期内容

Issue: #9 ｜ Spec: `../spec.md` ｜ Blocked by: 无 ｜ 分支: `feat/self-index`

> **本文件自包含**。执行方不需要看任何对话历史，读完这份就能开工。
> 所有路径相对仓库根 `D:\Project\globalSkills-library\MidNight`。

---

## 用户故事

作为**刚醒来的智能体**，我想要会话第一条就看到「我是谁 + 我有哪些长期内容」，
以便不必每轮重复摸索自己，也不用等别人提醒才想起手里攒着什么。

---

## 什么是长期内容

**长期内容 = 智能体自己判断值得长期保留、下次能直接拿来用的东西。**

四个特征，缺一不算：

| 特征 | 含义 | 反例 |
|---|---|---|
| **自己判断** | 不是被动收到的消息，也不是外部塞给的资料 | 用户今天说的那段话（→ 记忆） |
| **长期保留** | 目标是几个月后还在、还能用 | 一次性的中间结果 |
| **能复用** | 下次遇到同类情况，能直接拿出来用 | 「今天做了什么」（→ 记忆） |
| **会增删改** | 被维护的活集合：会补新的、会改旧的、会淘汰废的 | 记忆只增不减，不需要维护 |

判据一句话：

> **「下次这活再出现，我能不能直接把它拿出来用？」**
> 能 → 长期内容。不能 → 记忆。

### 它可以是任何形态

只要满足上面四条，什么形态都行。按「**拿出来做什么**」看，同一个动作在三种活里长成三样：

| 动作 | 编程智能体 | 写作智能体 | 运营智能体 |
|---|---|---|---|
| 直接跑 | `tools/preflight.py` | — | `scripts/日报生成.py` |
| 直接抄 | `snippets/幂等片段.md` | `hooks/开头句式.md` | `scripts/话术模板.md` |
| 照铺 | `templates/三层骨架/` | `voices/长文结构.md` | `calendars/节点节奏表.md` |
| 逐条勾 | `checklists/上线前.md` | `checklists/发稿前.md` | `checklists/活动上线.md` |
| 改变判断 | `kb/失败与边界.md` | `kb/什么题材会凉.md` | `kb/平台流量规则.md` |
| 直接引用 | `refs/A13-poolsvc.md` | `refs/爆款拆解01.md` | `refs/竞品打法.md` |

**这不是模板，是同一个问题在三种活里的三种答案。**

- 分类判据是「拿出来做什么」（动词），不是「它是什么」（名词）
- **类别名、类别数、要不要这些类，全部由智能体自己定**——系统不预设、不推荐、不评分
- 三类的智能体和八类的智能体都对。照抄别人的分类反而错，因为那是别人的活逼出来的

这条不是我定的，见背景里的实证。

### 它和记忆的分工（最容易混的一处）

| | 记忆 | 长期内容 |
|---|---|---|
| 记的是 | **发生过什么** | **下次怎么办** |
| 消费方式 | 读进上下文 | 复制 / 执行 / 勾选 / 照铺 |
| 存在形式 | `recall.db` 里的 chunk | 文件系统里的文件 + 一份索引 |
| 怎么找到 | **联想召回**（按话题自己浮上来） | **扫描 + 三级加载**（主动翻） |
| 生命周期 | 只增不减，正文永不删 | 会建、会改、会退休 |

同一件事两处都有也正常，角色不同：

```
「上次用学情三段式做 2501 班备课，卡在迁移点写不出来」  → 记忆，走联想
「学情三段式框架本身」                                  → 长期内容，走索引
```

**记忆负责记住「我用过它」，长期内容负责「它本身」。**
单向依赖：记忆能指向长期内容，长期内容不依赖记忆——任一方被删，另一方的腿都断不了。

---

## 背景 / 为什么要变

### 实证：开编已经自己长出来了

`kaibian`（`~/.midnight/recall/kaibian/self.md`）里写着：

> 记忆（发生过什么）走 `dailynote/`；知识（下次怎么做）走 `kb/`；可复用的现成项目走 `refs/`。**三者不混。**

它自己分出的六类：`tools/`（能直接跑）、`snippets/`（能直接抄）、`templates/`（能照铺）、
`checklists/`（能逐条勾）、`kb/`（改变判断）、`refs/`（外部卡片），外加一份总索引。

它自己总结的判据：

> 分类标准不是「主题」，而是「**拿出来做什么**」。库大小不是成绩，命中率才是。

**这套东西就是长期内容。不是我设计出来的，是被真实需求逼出来的。**

### 但它看不见

同一篇日记里：

> 失：我还是先按文档思路做了一遍，是用户提醒才想到存可执行资产。

它踩了七个坑、花三轮修好一个功能、把经验整理成 60 条清单——**然后下一次开工时这份清单不在它眼前**。

那一声「用户提醒」，就是本 Issue 要消掉的东西。

### 现在为什么没有

`skills/recall/scripts/session_start.py` 里有 `compile_identity_summary()`，只编译 self.md 的字段，
**没有任何流程调用它，也不含长期内容**。零件有，没装上。

---

## 为什么长期内容不进数据库

三条理由，任何一条都足够否决：

1. **形态不对**：脚本、图片、模板不是「正文」。灌进 `chunks` 既不能执行也不能显示，召回了也没用。
2. **语义冲突**：`importance` 权重和 `--decay` 是「印象淡出」语义。套到长期内容上会变成
   「我的代码过时了所以它消失了」——荒谬。
3. **生命周期相反**：`chunks` 没有删除语义（只增不减是第一性质），长期内容必须能建、能改、能退休。

**所以：长期内容归文件系统，数据库里只留记忆。**

---

## 实现规格

### 文件

新建 `skills/recall/scripts/boot.py`。**不改任何现有文件。**

### import 头（照抄现有模式）

```python
import os
import sys

_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _SCRIPTS_DIR)                      # 让 from embedding 可用
sys.path.insert(0, os.path.dirname(_SCRIPTS_DIR))     # 让 from scripts.xxx 可用
from scripts.config import get_agent_dir  # noqa: E402
from scripts.self_model import read_self  # noqa: E402
```

### 公共接口

```python
DEFAULT_BUDGET = 120          # 字符数硬上限
INDEX_FILENAME = 'LONGTERM.md'  # 长期内容总索引的默认文件名
ENTRY_SWITCH = 5              # 条目总数 ≤ 此值时直出条目名，否则给类目计数

def scan_longterm(roots: list[str]) -> dict:
    """扫长期内容根。

    返回 {
      'categories': {类目名: 文件数},   # 按类目名升序，便于确定性输出
      'entries':    [文件名(去扩展名)],  # 全部条目，按路径升序
      'index_file': 绝对路径 | None,     # 找到的第一个 LONGTERM.md
      'unavailable': [不存在的 root],    # 供失败态文案使用
    }
    """

def compile_boot_manifest(identity: str, workspace: str = None,
                          budget: int = DEFAULT_BUDGET) -> str:
    """编译开机清单。返回可直接注入上下文的文本块（含末尾换行）。"""

def main(argv=None) -> int:
    """CLI: python boot.py --identity NAME [--workspace PATH] [--budget N]"""
```

### 扫描算法（`scan_longterm`）

对每个 root 依次：

1. root 不存在或不是目录 → 加入 `unavailable`，跳过。
2. root 下若有 `INDEX_FILENAME`（`LONGTERM.md`）→ 若 `index_file` 仍为 `None`，记为它。
3. 遍历 root 的**直接子目录**（不递归进子目录再当类目）：
   - 每个直接子目录 = 一个**类目**，类目名 = 子目录名
   - 该类目的计数 = 该子目录下**递归**的文件数（含更深层子目录里的文件）
   - 跳过以 `.` 开头的隐藏目录
4. 遍历该子目录下**递归**的所有文件 → 文件名去扩展名后放入 `entries`
   - 跳过以 `.` 开头的隐藏文件
5. root 直接放着的文件（不在任何子目录里）→ 也算 `entries`，但**不产生类目**

多 root 时合并：`categories` 同名累加，`entries` 去重后合并。

**确定性要求**：`categories` 按 key 升序返回，`entries` 按路径升序。

### 默认扫描根

```python
roots = [os.path.join(get_agent_dir(identity), 'longterm')]
if workspace:
    roots.insert(0, workspace)      # 工作区优先，索引文件先找到它
```

即：**工作区在前，agent 目录在后**。

### 渲染格式（逐字）

输出两块，中间一个空行：

**第一块 · 人设**

```
[开机] 我是{name}｜{style}｜边界:{boundary}
```

- 分隔符是**全角竖线 `｜`**，不是 `|`
- `name` ← `read_self(identity)['name']`；缺失时用 `identity` 本身
- `style` ← `read_self(identity)['mutable']['persona_style']`；缺失时**整段省略**（连 `｜` 一起）
- `boundary` ← `read_self(identity)['mutable']['boundary']`；缺失时**整段省略**
- `self.md` 完全不存在 → 只输出 `[开机] 我是{identity}`，**不报错、不退出非零**

**第二块 · 长期内容**（四种情形，按优先级判定）

情形 1 —— 所有 root 都不可用：

```
长期内容  不可用（{第一个 unavailable 的路径} 不存在）
```

情形 2 —— 可用 root 存在但一条内容都没有（`categories` 与 `entries` 全空）：

```
长期内容  无
```

情形 3 —— 条目总数 ≤ `ENTRY_SWITCH`（5）：

```
长期内容  {entry1} · {entry2} · {entry3}
          → {index_file 绝对路径}
```

- 条目间用 ` · `（空格 + 中点 + 空格）
- 第二行行首缩进 **10 个半角空格**（与「长期内容  」对齐）
- `index_file` 为 `None` 时，第二行整行省略

情形 4 —— 条目总数 > 5：

```
长期内容  {cat1} {n1} · {cat2} {n2} · {cat3} {n3}
          → {index_file 绝对路径}
```

- 类目间同样用 ` · `
- 类目按名字升序
- `index_file` 为 `None` 时，第二行整行省略

### 预算裁剪（`budget` 默认 120）

按下面的顺序**逐级降级、重新渲染**，每次渲染后检查 `len(text) <= budget`，满足即返回：

| 级别 | 动作 |
|---|---|
| L0 | 全量渲染（按上面的格式） |
| L1 | 类目/条目列表只保留前 3 项，尾部加 ` · …` |
| L2 | 类目/条目列表只保留前 1 项 |
| L3 | 砍掉人设的「边界:」段 |
| L4 | 砍掉人设的「风格」段 |
| L5 | 长期内容只留 `长期内容  {总数} 项` |
| L6 | 只留 `[开机] 我是{name}` |

**硬规则**：
- **绝不截断半句**——不允许 `text[:budget]` 这种切法。每一级都是完整渲染。
- `[开机]` 标记和 `我是{name}` **永不砍**（L6 是地板）。
- 若 L6 仍超预算（例如 name 超长），允许超预算返回 L6 的完整输出——**宁超不残**。

### CLI

```
python boot.py --identity NAME [--workspace PATH] [--budget N]
```

| 情况 | 退出码 | 行为 |
|---|---|---|
| 正常 | 0 | stdout 打印清单 |
| 缺 `--identity` | 2 | stderr: `Usage: boot.py --identity NAME [--workspace PATH] [--budget N]` |
| `--budget` 非整数 | 2 | stderr 人话报错，可照抄 `recall.py` 的 `take_int` 写法 |
| 未知参数 | 2 | stderr: `Unknown option: {arg}` |

### 只读保证

`boot.py` **不得**：创建任何文件、写 `recall.db`、写 `retrieval_ledger.jsonl`、
修改任何 `mtime`。它只读文件系统。

---

## 测试

新建 `skills/recall/tests/test_boot.py`。**照抄 `tests/test_session_start.py` 的 fixture 模式**：

```python
import scripts.config as cfg
from scripts.self_model import ensure_self

@pytest.fixture
def basedir():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        old_base = cfg.BASE_DIR
        cfg.BASE_DIR = tmp
        yield tmp
        cfg.BASE_DIR = old_base
```

构造长期内容：直接在 `get_agent_dir(agent)/longterm/` 下建目录和空文件即可。

### 必须有的用例

| # | 测试名 | 断言 |
|---|---|---|
| 1 | `test_manifest_contains_identity_and_category` | 有 self.md + `longterm/tools/` 2 个文件 → 输出含 name 与 `tools 2` |
| 2 | `test_entries_shown_when_few` | 共 3 个文件（≤5）→ 输出含文件名，不含「`{类目} {数}`」形态 |
| 3 | `test_categories_shown_when_many` | 共 6 个类目 → 输出含类目计数，不含具体文件名 |
| 4 | `test_index_file_path_shown` | 有 `LONGTERM.md` → 输出含该绝对路径 |
| 5 | `test_missing_longterm_reports_unavailable` | 无 longterm 目录 → 含「不可用」与路径 |
| 6 | `test_empty_longterm_says_none` | 目录存在但空 → 含「无」，不含「不可用」 |
| 7 | `test_missing_self_degrades` | 无 self.md → 不抛异常，含 `[开机] 我是{identity}` |
| 8 | `test_nested_subdir_counts_as_one_category` | `kb/S1/x.md` → 类目 `kb` 计数为 1，不出现类目 `S1` |
| 9 | `test_budget_hard_limit` | `budget=60` + 超长输入 → `len(out) <= 60` |
| 10 | `test_budget_never_truncates_mid_sentence` | 裁剪后不以残缺字符结尾；只允许以 `…`、`）`、`{n}` 或换行收尾 |
| 11 | `test_budget_floor_keeps_name` | `budget=1` → 仍含 `我是{identity}` |
| 12 | `test_deterministic` | 连跑两次，输出逐字节相同 |
| 13 | `test_readonly_no_mtime_change` | 跑前记录 longterm 下所有文件 mtime，跑后完全一致 |
| 14 | `test_cli_requires_identity` | 无参数 → 返回 2 |
| 15 | `test_cli_prints_manifest` | 正常调用 → stdout 含 `[开机]` |
| 16 | `test_workspace_root_priority` | `--workspace` 下有 LONGTERM.md → index_file 指向它而非 agent 目录 |

### 跑法

```bash
cd D:\Project\globalSkills-library\MidNight\skills\recall
python -m pytest tests/test_boot.py -q            # 只跑新测试
python -m pytest tests -q                         # 全量回归
```

**G1 基线：343 passed / 6 skipped**（2026-11-14 实测于 `feat/self-index` @ `develop`）。
加完本 Issue 后应为 **359 passed / 6 skipped**（+16）。

---

## 验收标准

- [ ] 新增 `skills/recall/scripts/boot.py`，接口与上面「实现规格」逐条一致
- [ ] 渲染格式**逐字符**符合四种情形（含全角 `｜`、` · `、10 空格缩进）
- [ ] 硬预算 ≤120 字；裁剪按 L1–L6 逐级降级，**绝不截断半句**
- [ ] 条目总数 ≤5 直出条目名；>5 按子目录给类目计数
- [ ] 扫描根：`<agent_dir>/longterm/` + `--workspace`（工作区优先）
- [ ] 四种失败/空态文案与规格一致
- [ ] `self.md` 缺失时降级不崩
- [ ] **只读**：不建文件、不写库、不改 mtime
- [ ] 现有 `prep.py` / `recall.py` / `session_start.py` 行为**逐位不变**
- [ ] 新增 16 个测试全绿；全量 **359 passed / 6 skipped**
- [ ] 仓库内**不出现「资产」二字**（引用开编日记原文的除外）

## 票（垂直切片，按序实现）

- [ ] **票1：扫描 + 渲染** —— `scan_longterm` + `compile_boot_manifest`（不限预算），覆盖测试 1–4、5–8、12、16 ｜ Blocked by: 无
- [ ] **票2：预算裁剪** —— L1–L6 逐级降级，覆盖测试 9、10、11 ｜ Blocked by: 票1
- [ ] **票3：CLI + 只读** —— `main()` + 参数校验，覆盖测试 13、14、15 ｜ Blocked by: 票2

每张票 = 一个 commit，message 带 `(#9)`。

## 范围外（本轮不做）

- **不做能力扫描**（技能库清单）——Issue #10 用一句指路替代
- **不做同伴扫描**（`list_agents()`）——同上
- **不做自动注入**：本轮只交付命令 + 文档纪律，不碰 harness 的 session-start hook
- **不做长期内容的写入/编辑/退休**——本轮只让它们「被看见」
- **不动 `~/.midnight/recall/*/` 下任何数据**：只读
- 不做开机清单的持久化/缓存（每次现扫）
- 不建 `longterm/` 目录本身（不存在时按情形 1 报「不可用」）

## 对抗式自检（写测试时问自己）

- 长期内容目录存在但全空 → 情形 2，不许是空串
- 条目 5 条 / 6 条边界 → 切换点是否精确
- 类目名超长（30 字）→ 预算怎么处理
- 子目录里套子目录（`kb/S1/x.md`）→ 算一类
- self.md 的 frontmatter 坏掉 → `read_self` 会返回什么，崩不崩
- `--budget 10` → 还剩什么，还是空
- 同一秒跑两次 → 输出是否确定性一致
- 索引文件存在但指向的目录已删 → 报什么（应当照常按目录扫，索引只是路径展示）
- Windows 路径反斜杠 → 输出里怎么显示（照 `os.path` 原样）
- 中文文件名 → 预算按字符数还是字节数（**按字符数 `len()`**）

## 真相影响

- **PROJECT.md**：模块地图加 `boot.py`；"核心业务流程"加第 6 条「开机」；
  "关键数据结构"说明**长期内容是目录不是表**，与记忆分家
- **CONTEXT.md**：新增术语 **长期内容（long-term content）**（含四特征定义、与「记忆」的区分）、
  **开机清单（boot manifest）**、**三级加载**
- **ADR**：`docs/adr/0004-long-term-content-as-files.md`——记录
  「长期内容为什么不进库 / 为什么不走向量 / 为什么能力与同伴不进清单」
  （三条件全中：难逆转、有真实取舍、后来者会问为什么）
