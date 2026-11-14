# 03 — 记忆库可迁移（路径相对化）

Issue: #11 ｜ Spec: `../spec.md` ｜ Blocked by: 无 ｜ 分支: `feat/self-index`

> **本文件自包含**。执行方不需要看任何对话历史。
> 所有路径相对仓库根 `D:\Project\globalSkills-library\MidNight`。
> **本 Issue 是整个 feature 里唯一碰到既有数据的**，风险控制要求见「非破坏铁律」。

---

## 用户故事

作为**用户 YG**，我想要打包一个智能体就能搬走、解压就能用，
以便迁移不丢记忆、不丢人设，换台机器换用户名的路径下也读得到日记源。

---

## 背景 / 为什么要变

实测 `~/.midnight/recall/*/recall.db`：

```
C:\Users\WoodMe\.midnight\recall\seagull\dailynote\2026-11-14_173000.md
C:\Users\WoodMe\.midnight\recall\qinglan\dailynote\2026-08-27_220734.md
```

`files.file_path` 存的是**绝对路径，带用户名**。ADR-0002 说「库是单文件，跟着 agent 走」——
库能走，路径不走。换机器 / 换用户名，`file_path` 全断。

这是**迁移的硬阻塞**，也是本 feature 里唯一需要碰既有数据的改动。

---

## 设计：兼容而不是强制迁移

`recall(db_path)` 和 `timeline_recall(db_path)` 只拿到 `db_path`，不知道 agent 名。
所以还原基准取 `os.path.dirname(os.path.abspath(db_path))`——它天然就是 agent 目录。

- **新库**：存 `dailynote/x.md`，读时拼回 `<db 所在目录>/dailynote/x.md`
- **老库**：存绝对路径，`os.path.isabs()` 判定后原样返回

**两种共存，零迁移也能跑。** 迁移只是把老库也变成可搬的，不是前置条件。

---

## 实现规格

### 改动一：新建 `skills/recall/scripts/paths.py`

两个纯函数，无副作用，便于单测。

```python
import os

def stored_path(file_path: str, db_path: str) -> str:
    """入库时该存什么：能相对就相对（正斜杠），否则退回绝对路径。

    规则：
    1. 求 file_path 绝对路径与 base = dirname(abspath(db_path)) 的相对路径
    2. 相对路径以 '..' 开头（在 agent 目录之外）→ 返回绝对路径
    3. os.path.relpath 抛 ValueError（Windows 跨盘）→ 返回绝对路径
    4. 其余 → 返回相对路径，并把 '\\' 统一替换成 '/'
    """
```

```python
def resolve_file_path(db_path: str, stored: str) -> str:
    """读取时该用什么：相对路径按 db 所在目录还原，绝对路径原样返回。

    规则：
    1. stored 为空（None/''）→ 原样返回
    2. os.path.isabs(stored) → 原样返回（老数据）
    3. 否则 → normpath(join(dirname(abspath(db_path)), stored))
    """
```

**为什么统一存正斜杠**：Windows 反斜杠进 JSON / 跨平台时易出转义问题，正斜杠两边都能 `os.path.join` 处理。

### 改动二：`skills/recall/scripts/ingest.py`

#### 2.1 写：改存相对路径

`ingest_file(file_path, db_path, embedding_client, conn=None)` 内：

```python
abs_path = os.path.abspath(file_path)        # ← 保留，仅用于回退
stored = stored_path(file_path, db_path)     # ← 新增
```

把两处 `abs_path` 换成 `stored`：

- `SELECT id, checksum FROM files WHERE file_path = ?` → 参数用 `stored`
- `INSERT INTO files (file_path, ...) VALUES (?, ...)` → 参数用 `stored`

#### 2.2 兼容：老库绝对路径必须能匹配上（**关键，漏了会插重复行**）

老库里存的是绝对路径。若只用 `stored` 查，会查不到 → 当成新文件 → **同一篇日记插两次**。

所以查询要两次：

```python
row = conn.execute(
    "SELECT id, checksum FROM files WHERE file_path = ?", (stored,)).fetchone()
if not row and stored != abs_path:
    row = conn.execute(
        "SELECT id, checksum FROM files WHERE file_path = ?", (abs_path,)).fetchone()
```

**匹配到老行时，不做任何 UPDATE 去「顺手改成相对」**——那是迁移的活，不是 ingest 的活。
只更新 `checksum` 和 `updated_at`（现有行为）。

### 改动三：`skills/recall/scripts/recall.py`

三个返回 `file_path` 的地方，读出后还原：

| 函数 | 改法 |
|---|---|
| `recall()` | `'file_path': row['file_path']` → `'file_path': resolve_file_path(db_path, row['file_path'])` |
| `timeline_recall()` | `'file_path': f['file_path']` → `resolve_file_path(db_path, f['file_path'])` |
| `literal_recall()` | `'file_path': r['file_path']` → `resolve_file_path(db_path, r['file_path'])` |

同时补 import：

```python
from scripts.paths import resolve_file_path
```

**不改任何 SQL、不改任何排序、不改任何返回字段名。**

### 改动四：`skills/recall/scripts/maintenance.py`

新增 `--relativize-paths` 动作。

```
python maintenance.py --relativize-paths [--agent X] [--dry-run]
```

**`--dry-run` 是默认行为**（不传也 dry-run；只有显式 `--apply` 才写盘）。

参数：

| 参数 | 含义 |
|---|---|
| `--relativize-paths` | 选中该动作 |
| `--agent X` | 目标 agent，缺省取 `MIDNIGHT_AGENT` 或 `default` |
| `--dry-run` | 默认；只打印，零写入 |
| `--apply` | 真执行（与 `--dry-run` 互斥，同时给则退出码 2） |

输出（stdout，JSON）：

```json
{
  "status": "ok",
  "agent": "seagull",
  "db": "<abs>",
  "dry_run": true,
  "would_change": 2,
  "total": 2,
  "samples": [["C:\\...\\dailynote\\a.md", "dailynote/a.md"]]
}
```

`--apply` 时额外带 `"backup": "<abs 备份路径>"`。

#### 非破坏铁律（本 Issue 最高优先级）

1. **只 `UPDATE files SET file_path = ?`**。绝不 `DELETE`、`DROP`、`TRUNCATE`，绝不碰 `chunks` 表任何列。
2. **`--apply` 前必须备份**：`shutil.copy2(db_path, db_path + '.bak-YYYYMMDDHHMMSS')`。
   备份失败 → 中止，退出码 1，不写任何一行。
3. **只处理 `os.path.isabs(file_path)` 为真的行**（已经是相对的不动）。
4. **算不出相对路径的行跳过**（跨盘 / 在 agent 目录外），计入 `skipped`，不算失败。
5. **幂等**：连跑两次 `--apply`，第二次 `would_change` 必须为 0。

### 改动五：`skills/recall/SKILL.md`

「多智能体物理隔离与孤儿数据」一节末尾补：

```markdown
## 搬迁（路径相对化）

`files.file_path` 存相对 agent 目录的路径（正斜杠），读时按库所在目录还原——
所以整个 `<agent>/` 目录可以直接复制/打包到另一台机器。

老库若存的仍是绝对路径，读侧兼容（`isabs` 判定原样返回），**不迁移也能用**。
想把老库也变成可搬的：

```bash
python maintenance.py --relativize-paths --agent X            # 预览，零写入
python maintenance.py --relativize-paths --agent X --apply    # 真执行，先自动备份
```
```

---

## 测试

新建 `skills/recall/tests/test_relocatable_paths.py`。

fixture 复用现有模式：

```python
@pytest.fixture
def basedir():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        old_base = cfg.BASE_DIR
        cfg.BASE_DIR = tmp
        yield tmp
        cfg.BASE_DIR = old_base
```

入库用现成的 `FakeEmbeddingClient`（`scripts/embedding.py`，无需模型）。

### 必须有的用例

| # | 测试名 | 断言 |
|---|---|---|
| 1 | `test_stored_path_relative` | agent 目录内文件 → 返回正斜杠相对路径，不含盘符与用户名 |
| 2 | `test_stored_path_outside_falls_back_absolute` | 文件在 agent 目录外 → 返回绝对路径 |
| 3 | `test_stored_path_cross_drive_falls_back` | mock `os.path.relpath` 抛 `ValueError` → 返回绝对路径 |
| 4 | `test_resolve_relative` | 相对路径 → 拼成 `<db 目录>/...` 绝对路径 |
| 5 | `test_resolve_absolute_passthrough` | 绝对路径 → 原样返回（老数据） |
| 6 | `test_resolve_empty` | `None` / `''` → 原样返回，不抛 |
| 7 | `test_ingest_stores_relative` | 入库后查库，`file_path` 是相对路径 |
| 8 | `test_ingest_matches_legacy_absolute_no_duplicate` | **手写一行老绝对路径 → 再 ingest 同一文件 → `files` 行数不变** |
| 9 | `test_timeline_returns_resolved_path` | 新库 `--timeline` 返回的 `file_path` 是存在的绝对路径 |
| 10 | `test_literal_returns_resolved_path` | 同上，`--literal` 路径 |
| 11 | `test_relativize_dry_run_no_write` | `--dry-run` 后库文件 checksum 不变 |
| 12 | `test_relativize_apply_creates_backup` | `--apply` 后存在 `.bak-*` 文件 |
| 13 | `test_relativize_apply_updates_rows` | `--apply` 后所有 `file_path` 非 `isabs` |
| 14 | `test_relativize_idempotent` | 连跑两次 `--apply`，第二次 `would_change == 0` |
| 15 | `test_relativize_skips_outside_paths` | 一条 agent 目录外的绝对路径 → 被跳过，仍为绝对 |
| 16 | `test_relocate_agent_dir_still_readable` | **把整个 agent 目录复制到新路径 → 对副本跑 `--timeline`，内容与原文一致** |
| 17 | `test_chunks_content_untouched` | 迁移前后 `chunks.content` 全表哈希一致 |

第 8、16、17 是**验收的核心三条**，缺一不算完成。

### 跑法

```bash
cd D:\Project\globalSkills-library\MidNight\skills\recall
python -m pytest tests/test_relocatable_paths.py -q
python -m pytest tests -q
```

**基线不是固定数字。** 开工前先跑一次全量（`python -m pytest tests -q`），
把当时的 `passed / skipped` 记下来当基线；本 Issue 完成后应为「基线 + 17」，**失败数必须为 0**。

（2026-11-14 在 `feat/self-index` 上的实测是 343 passed / 6 skipped，这只是参考。）

---

## 实现思路（给执行方）

### 顺序：先兼容，再迁移

最容易的错是先写迁移脚本。**先写 `paths.py` 两个纯函数 + ingest 改造**，跑通「新老共存」，
再写迁移。兼容是刚需，迁移是锦上添花。

### 陷阱一：重复插入（本 Issue 最贵的错）

ingest 靠 checksum 查重，幂等。改成存相对路径后，若只用相对路径查老库（存的是绝对），
查不到 → 当新文件 → **同一篇日记插两次**。

**先写测试 8 让它红，再改代码。** 手工构造：

```python
# 手动插一行老格式
conn.execute("INSERT INTO files (file_path, diary_name, checksum, diary_date) VALUES (?,?,?,?)",
             (os.path.abspath(fp), 'default', 'x', '2026-11-14'))
# 再正常 ingest 同一个文件
ingest_file(fp, db_path, client)
# 断言 files 只有 1 行
```

### 陷阱二：`db_path` 可能是裸相对路径

`recall.py` 支持 `--db recall.db`。这时：

```python
os.path.dirname('recall.db')              # → ''    ✗ 错
os.path.dirname(os.path.abspath('recall.db'))   # → 当前工作目录  ✓ 对
```

`resolve_file_path` 里**必须先 `abspath` 再 `dirname`**。

### 陷阱三：备份撞名

```python
shutil.copy2(db_path, db_path + '.bak-' + datetime.now().strftime('%Y%m%d%H%M%S'))
```

同一秒跑两次会撞同名文件。**复制前先检查目标是否存在**，存在就加序号。

### 测试 16（搬迁往返）怎么写

```python
# 建库 → 入库若干日记 → shutil.copytree 整个 agent 目录到新路径
# 对新路径的 recall.db 调 timeline_recall
# 断言返回内容与原文一致
```

这条最接近真实场景。它绿了，基本就敢交付。

### 别碰 chunk

迁移只 `UPDATE files.file_path`。测试 17（`chunks.content` 全表哈希不变）写完，
心里就有底了——它绿的，说明你没误伤正文。

---

## 验收标准

- [ ] `scripts/paths.py` 两个纯函数，行为与规格逐条一致
- [ ] `ingest.py` 新数据存相对路径；**老绝对路径能匹配上，不插重复行**
- [ ] `recall.py` 三处返回的 `file_path` 已还原；SQL 与排序零改动
- [ ] `maintenance.py --relativize-paths` 可用，`--dry-run` 默认，`--apply` 前自动备份
- [ ] **只 `UPDATE files.file_path`**，`chunks` 表一个字节没动
- [ ] 17 个新测试全绿，其中 8 / 16 / 17 为核心验收
- [ ] 全量测试失败数为 0
- [ ] 对现存 12 个 agent 库跑 `--relativize-paths`（**dry-run**）不报错、不写盘

## 票（垂直切片，按序实现）

- [ ] **票1：paths.py + ingest 写相对 + 读取兼容** —— 覆盖测试 1–8 ｜ Blocked by: 无
- [ ] **票2：读取侧还原** —— `recall.py` 三处，覆盖测试 9、10 ｜ Blocked by: 票1
- [ ] **票3：迁移命令** —— `--relativize-paths`，覆盖测试 11–15 ｜ Blocked by: 票1
- [ ] **票4：搬迁往返验收** —— 覆盖测试 16、17 ｜ Blocked by: 票2、票3

每张票 = 一个 commit，message 带 `(#11)`。

## 范围外（本轮不做）

- **不做打包脚本**（`bundle.py` / tar）：路径相对化完成后再单开 Issue
- **不迁移长期内容**（长期内容本来就存相对工作区的路径，且不进库）
- 不改 `chunks` / `files` 以外的任何表
- **不动 `dailynote/*.md` 一个字节**
- **不对真实 `~/.midnight` 库跑 `--apply`**——本 Issue 只交付能力与测试，
  真库迁移由用户在验收后自行执行

## 对抗式自检（写测试时问自己）

- 老库混合新老格式（迁移一半失败）→ 读取侧能不能同时处理
- `db_path` 以裸相对路径传入（`recall.db`）→ `dirname` 得空串，还原会不会变成相对当前目录
- Windows 反斜杠 vs 正斜杠 → 存正斜杠，读时 `os.path.join` 能不能正常拼
- 迁移中途断电 → 备份能不能恢复；备份文件名带时间戳，能不能重复跑
- `diary_date` 为 NULL 的老行 → 迁移 SQL 会不会把它一起改坏
- 迁移后再跑一次 → 幂等不重复改
- 同一文件被 ingest 两次（一次老绝对、一次新相对）→ 表里会不会两行
- 中文文件名 → 相对路径编码不变形

## 真相影响

- **PROJECT.md**：「关键数据结构」补一句 `files.file_path` 存**相对 agent 目录的路径（正斜杠）**；
  「必须遵守的约束」补一条「路径相对化：库里不存盘符与用户名」
- **CONTEXT.md**：新增术语 **相对路径（relocatable path）**——`files.file_path` 的存储口径，
  相对 agent 目录、正斜杠；读时按库所在目录还原，老绝对路径兼容
- **ADR**：`docs/adr/0005-relocatable-store-paths.md`——记录「为什么兼容而不是强制迁移」
  （取舍：多一层 `isabs` 分支 vs 要求所有库先迁移才能用）
