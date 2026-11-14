# 01 — 开机清单：智能体开机就知道自己的长期内容

Issue: #9 ｜ Spec: `../spec.md` ｜ Blocked by: 无 ｜ 分支: `feat/self-index`

> **本文件自包含**。执行方不需要看任何对话历史，读完就能开工。
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
| **会增删改** | 被维护的活集合：会补新的、会改旧的、会淘汰废的 | 记忆只增不减 |

### 它可以是什么，不由我们规定

四特征齐了就收，**形态不限**：

- 一个能直接跑的工具
- 一套能照铺的结构
- 一份能逐条过的检查表
- **一套想清楚了的范式判断**（为什么这么分层、为什么不用 X）
- **一个做完的项目存档**（下次直接 fork）
- **一批参考图例/示意图**
- 一条能改判断的结论

判据只有一句，由智能体自己答：

> **下次同类的事再来，它能替我省掉多少「重新想」和「重新做」？**

**类别怎么切、切几类、要不要切——你自己定。系统不预设、不推荐、不给示例架构。**

理由：分类是被活逼出来的，不是开局设计的。开编那六类是它一个月里陆续长出来的——
它自己的日记写的是「用户提醒才想到存可执行资产」，说明最初根本没规划过。
**开局给一份模板，它就会长成模板的样子，而不是自己的样子。**

### 它和记忆的分工

| | 记忆 | 长期内容 |
|---|---|---|
| 记的是 | **发生过什么** | **下次怎么办** |
| 消费方式 | 读进上下文 | 复制 / 执行 / 勾选 / 照铺 |
| 存在形式 | `recall.db` 里的 chunk | 文件系统里的文件 + 一份索引 |
| 怎么找到 | **联想召回**（按话题自己浮上来） | **扫描 + 三级加载**（主动翻） |
| 生命周期 | 只增不减，正文永不删 | 会建、会改、会退休 |

同一件事两处都有也正常，角色不同。**单向依赖**：记忆能指向长期内容，
长期内容不依赖记忆——任一方被删，另一方的腿都断不了。

---

## 背景 / 为什么要变

`kaibian` 的 `self.md` 里写着「记忆走 dailynote/、知识走 kb/、外部资产走 refs/，三者不混」，
并已经建出自己的六类目录 + 一份总索引。它自己的判据：

> 分类标准不是「主题」，而是「拿出来做什么」。**库大小不是成绩，命中率才是。**

**这套东西就是长期内容。不是我设计出来的，是被真实需求逼出来的。**

但它看不见——同一篇日记里：

> 失：我还是先按文档思路做了一遍，是用户提醒才想到存可执行资产。

它踩了七个坑、修了三轮、整理出 60 条清单——**下一次开工时这份清单不在它眼前。**

现在 `session_start.py` 只编译 self.md 字段，**没有任何流程调用它，也不含长期内容**。零件有，没装上。

---

## 为什么长期内容不进数据库

1. **形态不对**：脚本、图片、范式文档不是「正文」。灌进 `chunks` 既不能执行也不能显示。
2. **语义冲突**：`importance` 和 `--decay` 是「印象淡出」语义。套上去会变成「我的代码过时了所以它消失了」。
3. **生命周期相反**：`chunks` 没有删除语义，长期内容必须能建、能改、能退休。

**所以：长期内容归文件系统，数据库里只留记忆。**

---

## 实现规格

### 文件

新建 `skills/recall/scripts/boot.py`。**不改任何现有文件。**

### import 头

```python
import os
import sys

_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _SCRIPTS_DIR)
sys.path.insert(0, os.path.dirname(_SCRIPTS_DIR))
from scripts.config import get_agent_dir  # noqa: E402
from scripts.self_model import read_self  # noqa: E402
```

### 公共接口

```python
INDEX_FILENAME = 'LONGTERM.md'   # 长期内容总索引的默认文件名

def scan_longterm(roots: list[str]) -> dict:
    """扫长期内容根。

    返回 {
      'categories': {类目名: 文件数},   # 按类目名升序，确定性输出
      'index_file': 绝对路径 | None,
      'unavailable': [不存在的 root],
    }
    """

def compile_boot_manifest(identity: str, workspace: str = None) -> str:
    """编译开机清单。返回可直接注入上下文的文本块（含末尾换行）。"""

def main(argv=None) -> int:
    """CLI: python boot.py --identity NAME [--workspace PATH]"""
```

**没有 `budget` 参数，没有字数上限。** 见下面的「不设上限」。

### 扫描算法（`scan_longterm`）

对每个 root 依次：

1. root 不存在或不是目录 → 加入 `unavailable`，跳过。
2. root 下有 `INDEX_FILENAME` → 若 `index_file` 仍为 `None`，记为它。
3. 遍历 root 的**直接子目录**（不递归进子目录再当类目）：
   - 每个直接子目录 = 一个**类目**，类目名 = 子目录名
   - 计数 = 该子目录下**递归**的文件数（含更深层子目录里的文件）
   - 跳过 `.` 开头的隐藏目录
4. root 直接放着的文件（不在任何子目录里）→ **不计入类目**（它们只能靠索引被发现）

**确定性**：`categories` 按 key 升序。

### 默认扫描根

```python
roots = [os.path.join(get_agent_dir(identity), 'longterm')]
if workspace:
    roots.insert(0, workspace)      # 工作区优先
```

### 渲染格式（逐字）

两块，中间一个空行。

**第一块 · 人设**

```
[开机] 我是{name}｜{style}｜边界:{boundary}
```

- 分隔符是**全角竖线 `｜`**
- `name` ← `read_self(identity)['name']`；缺失时用 `identity`
- `style` ← `mutable['persona_style']`；缺失时整段省略（连 `｜` 一起）
- `boundary` ← `mutable['boundary']`；缺失时整段省略
- `self.md` 不存在 → 只输出 `[开机] 我是{identity}`，不报错

**第二块 · 长期内容**（三种情形）

情形 1 —— 所有 root 都不可用：

```
长期内容  不可用（{第一个 unavailable 的路径} 不存在）
```

情形 2 —— 可用 root 存在但一个子目录都没有：

```
长期内容  无
```

情形 3 —— 有类目：

```
长期内容  {cat1} {n1} · {cat2} {n2} · ... {catk} {nk}
          → {index_file 绝对路径}
```

- 类目间用 ` · `（空格 + 中点 + 空格），按名字升序
- 第二行缩进 **10 个半角空格**
- `index_file` 为 `None` 时，第二行整行省略

### 不设上限

**不裁剪，不降级，类目有几类列几类。**

理由：字数上限是外部规则，管得住输出、管不住判断。挤是真实信号——清单变长，
智能体自己会看到，自己会想合并。**把取舍交还给它。**

代价意识由两句话承载，写在 `SKILL.md` 与 `self.md` 里（见 Issue #12），**不写在代码里**。

唯一允许的兜底：清单长度超过 **2000 字**时，在末尾追加一行提醒（不裁剪内容）：

```
（这份清单已占约 {n} 字。token 很贵——考虑合并或退休几项。）
```

这是**镜子，不是闸门**。

### CLI

```
python boot.py --identity NAME [--workspace PATH]
```

| 情况 | 退出码 |
|---|---|
| 正常 | 0，stdout 打印清单 |
| 缺 `--identity` | 2，stderr 给 Usage |
| 未知参数 | 2，stderr `Unknown option: {arg}` |

### 只读保证

不得创建文件、写 `recall.db`、写 `retrieval_ledger.jsonl`、改任何 `mtime`。

---

## 测试

新建 `skills/recall/tests/test_boot.py`。照抄 `tests/test_session_start.py` 的 fixture：

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
| 1 | `test_manifest_contains_identity_and_category` | 有 self.md + `longterm/tools/` 2 文件 → 含 name 与 `tools 2` |
| 2 | `test_zero_file_category_shown` | 类目目录存在但为空 → 输出 `类目 0`，不消失 |
| 3 | `test_index_file_path_shown` | 有 `LONGTERM.md` → 含其绝对路径 |
| 4 | `test_missing_longterm_reports_unavailable` | 无 longterm 目录 → 含「不可用」与路径 |
| 5 | `test_empty_longterm_says_none` | 目录存在但无子目录 → 含「无」 |
| 6 | `test_missing_self_degrades` | 无 self.md → 不抛异常，含 `[开机] 我是{identity}` |
| 7 | `test_nested_subdir_counts_as_one_category` | `kb/S1/x.md` → 类目 `kb` 计数 1，不出现类目 `S1` |
| 8 | `test_categories_sorted` | 建 `z/`、`a/` → 输出里 `a` 在 `z` 前 |
| 9 | `test_no_truncation_with_many_categories` | 建 20 个类目 → **20 个全在输出里**，一个不少 |
| 10 | `test_long_output_appends_hint` | 清单 >2000 字 → 末尾含「token 很贵」，且**内容未被裁剪** |
| 11 | `test_deterministic` | 连跑两次，输出逐字节相同 |
| 12 | `test_readonly_no_mtime_change` | 跑前后 longterm 下所有文件 mtime 一致 |
| 13 | `test_cli_requires_identity` | 无参数 → 返回 2 |
| 14 | `test_cli_prints_manifest` | 正常 → stdout 含 `[开机]` |
| 15 | `test_workspace_root_priority` | `--workspace` 下有 LONGTERM.md → index_file 指向它 |

### 跑法

```bash
cd D:\Project\globalSkills-library\MidNight\skills\recall
python -m pytest tests/test_boot.py -q
python -m pytest tests -q
```

**G1 基线：343 passed / 6 skipped。** 完成后应为 **358 passed / 6 skipped**（+15）。

---

## 实现思路（给执行方）

### 代码怎么组织

一个文件 ~150 行写完。顺序建议：

1. **先写 `scan_longterm`**——纯函数（入路径列表，出 dict），不碰 self.md，最好测
2. 再写两个私有渲染函数 `_render_identity(identity)` / `_render_longterm(scan)`，各自纯
3. `compile_boot_manifest` 只做「调两个渲染 → 拼 → 判断要不要加提醒行」
4. `main` 最后写；参数解析可照 `recall.py` 的 `take_value` 风格（缺值给 Usage，不裸 traceback）

### 陷阱一：类目计数别用 `os.walk(root)`

正确写法是「列直接子目录当类目，各自内部递归计数」：

```python
for name in sorted(os.listdir(root)):
    sub = os.path.join(root, name)
    if not os.path.isdir(sub) or name.startswith('.'):
        continue
    count = sum(len(files) for _, _, files in os.walk(sub))
    categories[name] = count
```

**不要** `os.walk(root)` 然后按相对路径第一段分组——root 下有散文件时会多出一个假类目，
或者把散文件错算进某个类目。测试 7 锁这个。

### 陷阱二：缩进别纠结对齐

第二行用 **10 个半角空格**。中文是双宽，视觉上永远差一点——**别去调**。
测试断言的是字面串 `'          → '`，不是视觉居中对齐。

### 陷阱三：2000 字提醒不能改内容

提醒行是**追加**，不是裁剪。写的时候别顺手 `text[:2000]`——那是另一种错。

```python
if len(text) > HINT_THRESHOLD:
    text += f'\n（这份清单已占约 {len(text)} 字。token 和上下文都很宝贵——考虑合并或退休几项。）'
```

### 测试怎么造数据

不用建真目录树跑 CLI。tmp 里就行：

```python
longterm = os.path.join(get_agent_dir(agent), 'longterm')
os.makedirs(os.path.join(longterm, 'tools'))
open(os.path.join(longterm, 'tools', 'a.py'), 'w').close()   # 空文件够用
```

扫描只数文件，不读内容。

### 调试先看哪一步

输出不对，**先单独调 `scan_longterm([root])` 打印 dict**——九成问题在这（类目少了 / 计数错）。
渲染层很薄，通常不会错。

---

## 验收标准

- [ ] 新增 `skills/recall/scripts/boot.py`，接口与规格逐条一致
- [ ] 渲染格式逐字符符合三种情形（全角 `｜`、` · `、10 空格缩进）
- [ ] **不裁剪、不降级**：20 个类目全部输出
- [ ] 超 2000 字时**只追加提醒行，不改内容**
- [ ] 扫描根：`<agent_dir>/longterm/` + `--workspace`（工作区优先）
- [ ] 三种失败/空态文案与规格一致
- [ ] `self.md` 缺失时降级不崩
- [ ] **只读**：不建文件、不写库、不改 mtime
- [ ] 现有 `prep.py` / `recall.py` / `session_start.py` 行为逐位不变
- [ ] 15 个新测试全绿；全量 **358 passed / 6 skipped**

## 票（垂直切片，按序实现）

- [ ] **票1：扫描 + 渲染** —— `scan_longterm` + `compile_boot_manifest`，覆盖测试 1–8、11、15 ｜ Blocked by: 无
- [ ] **票2：CLI + 只读 + 超长提示** —— `main()` + 2000 字提醒行，覆盖测试 9、10、12–14 ｜ Blocked by: 票1

每张票 = 一个 commit，message 带 `(#9)`。

## 范围外（本轮不做）

- **不做能力扫描**（技能库清单）——Issue #10 用一句指路替代
- **不做同伴扫描**——同上
- **不做自动注入**：只交付命令 + 文档纪律，不碰 harness 的 session-start hook
- **不做长期内容的写入/编辑/退休**——本轮只让它们「被看见」
- **不动 `~/.midnight/recall/*/` 下任何数据**：只读
- 不建 `longterm/` 目录本身
- **不设字数上限、不做裁剪**（见「不设上限」）

## 对抗式自检

- 类目名超长（30 字）× 20 类 → 输出会很长，提醒行触发了吗
- 类目名含中文/空格 → 输出格式会不会崩
- 空类目目录 → 显示 `0`，还是被过滤掉
- `LONGTERM.md` 存在但指向的目录已删 → 照常扫，索引只做路径展示
- Windows 路径反斜杠 → 输出照 `os.path` 原样
- self.md frontmatter 坏掉 → `read_self` 返回什么，崩不崩
- 同一秒跑两次 → 确定性

## 真相影响

- **PROJECT.md**：模块地图加 `boot.py`；"核心业务流程"加第 6 条「开机」；
  "关键数据结构"说明长期内容是目录不是表
- **CONTEXT.md**：新增 **长期内容（long-term content）**（四特征 + 与记忆的区分）、
  **开机清单（boot manifest）**、**三级加载**
- **ADR**：`docs/adr/0004-long-term-content-as-files.md`
