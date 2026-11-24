# 05 — 长期内容路径相对化（修 #9 的绝对路径缺陷）

Issue: #14 ｜ Spec: `../spec.md` ｜ Blocked by: #9 ｜ 分支: `feat/self-index`

> 本文件自包含。这是 **#9 的缺陷修正**：#9 的实现让 `boot.py` 输出绝对路径，
> 智能体照着模仿，就会把自己的长期内容索引写成 `D:\Project\...` —— 搬机器即断。

---

## 缺陷报告

### 现象

`boot.py --workspace <ws>` 实际输出：

```
长期内容  tools 2 · kb 12
          → D:\Project\_tmp_ws_test\LONGTERM.md
```

### 为什么是错的

1. **它是最好的老师，教的却是坏习惯。** 智能体看到 `→ D:\Project\...`，写自己的
   `LONGTERM.md` 时就会照抄绝对路径。索引里一旦全是绝对路径，工作区换个盘就全断。
2. **`#11` 只管住了数据库**（`files.file_path`），管不到长期内容——后者是纯文件系统，没有库。
3. **测试把错误锁死了**：`test_index_file_path_shown` 断言 `index in out`（绝对路径），
   `test_workspace_root_priority` 同样。任何人想改成相对，测试先红。

### 关键区分

| | 存不存 | 搬机器会不会断 |
|---|---|---|
| 开机清单**显示**的路径 | 不存（每次现算） | **不会**——下次 boot.py 重新算 |
| 索引文件**里面写的**路径 | **存**（智能体自己写） | **会**——这才是真问题 |

所以修的是两件事：**① 展示改成相对（示范正确做法）② 教 + 抓索引里的绝对路径**。

---

## 用户故事

作为**一个要把智能体搬到另一台机器的用户**，我想要整个工作区原样搬走后长期内容还能用，
以便不用手工改每一条索引里的路径。

---

## 实现规格

### 改动一：`boot.py` 渲染改为「相对路径 + 根」

`scan_longterm` 的返回值不变（`categories` / `index_file` / `unavailable`），
但 `index_file` 语义改为**相对它所在根**的路径，并新增 `root`（该根绝对路径）。

```python
def scan_longterm(roots: list) -> dict:
    """返回 {
      'categories': {类目名: 文件数},
      'index_file': 'LONGTERM.md',        # ← 相对 root，不是绝对
      'root': '<该索引文件所在根的绝对路径>',  # ← 定位用，每次现算
      'unavailable': [...],
    }
    """
```

渲染：

```
长期内容  {cat1} {n1} · {cat2} {n2}
          → {index_file}（根 {root}）
```

- `index_file` 为 `None` 时第二行整行省略（同现状）
- 括号里那句是**定位信息**，不是让智能体抄进索引的范例——SKILL.md 会讲清

### 改动二：`boot.py --check` 扫索引里的绝对路径

```
python boot.py --identity X [--workspace Y] --check
```

扫描 `LONGTERM.md`（若存在），逐行找出「看起来像路径且是绝对路径」的引用：

- Windows 盘符：`[A-Za-z]:[\\/]`
- POSIX 根：行内 `` `...` `` 或 markdown 链接里以 `/` 开头
- `file://` 协议

输出：

```
[路径检查] LONGTERM.md 发现 2 处绝对路径（搬机器会断）：
  第 12 行  D:\Project\AIZY\tools\a.py
  第 15 行  C:\Users\WoodMe\...

改成相对路径（相对索引文件所在目录），例如：tools/a.py
```

- 干净时输出：`[路径检查] LONGTERM.md 未发现绝对路径。`
- `LONGTERM.md` 不存在：`[路径检查] 未找到索引文件，跳过。`，退出码 0
- 发现问题时**退出码仍为 0**（这是检查，不是断言失败）；要进 CI 时用 `--check --strict` → 发现问题退 1

### 改动三：`SKILL.md` 写死一条纪律

在「## 长期内容的维护」下新增一小节：

```markdown
### 索引里写相对路径

`LONGTERM.md` 里的每一条，都写**相对于索引文件所在目录**的路径：

- ✅ `tools/preflight.py`
- ❌ `D:\Project\AIZY\tools\preflight.py`

理由：整个工作区可能被搬到另一台机器、另一个盘。绝对路径一搬就断，
相对路径跟着目录走，永远有效。这条跟你写代码时"不硬编码绝对路径"是同一个道理。

写完自查：`python boot.py --identity <名字> --workspace <工作区> --check`
```

### 改动四：修测试（把锁死的绝对路径断言改掉）

`test_boot.py`：

- `test_index_file_path_shown` → 重命名 `test_index_file_is_relative`，
  断言输出含 `LONGTERM.md` 且**不含** `os.path.abspath(index)`，含 `根 `
- `test_workspace_root_priority` → 断言 `根 {ws}` 出现，index 是 `LONGTERM.md` 而非绝对

新增：

| # | 测试名 | 断言 |
|---|---|---|
| 16 | `test_index_relative_not_absolute` | 输出里 `→ ` 后是 `LONGTERM.md`，全文不含盘符形式的索引路径 |
| 17 | `test_root_shown` | 输出含 `根 {workspace 绝对路径}` |
| 18 | `test_check_finds_absolute` | 索引里写 `D:\x\a.py` → `--check` 报告它 |
| 19 | `test_check_clean_index` | 全是相对路径 → 报告「未发现」 |
| 20 | `test_check_missing_index` | 无索引文件 → 「跳过」，退出码 0 |
| 21 | `test_check_strict_exit_code` | `--check --strict` + 有问题 → 退出码 1 |

---

## 验收标准

- [ ] `boot.py` 输出的索引路径是**相对**的，绝对路径只在「根」那句里出现一次
- [ ] `--check` 能抓 Windows 盘符 / POSIX 绝对 / `file://` 三种
- [ ] `--check` 干净时明确说「未发现」，不沉默
- [ ] `--strict` 有问题时退 1；不加时退 0
- [ ] `SKILL.md` 有「索引里写相对路径」小节，含正反例与自查命令
- [ ] **旧的「绝对路径」断言全部改掉**，不允许再有人把绝对路径锁回来
- [ ] 全量测试与基线一致，失败 0

## 票（垂直切片）

- [ ] 票1：`scan_longterm` 返回相对 `index_file` + `root`，渲染改「相对+根」｜ Blocked by: 无
- [ ] 票2：`--check` / `--strict` 扫描器 ｜ Blocked by: 票1
- [ ] 票3：SKILL.md 纪律 + 修旧断言 + 新增 6 条测试 ｜ Blocked by: 票1

## 范围外（本轮不做）

- 不改 `#11` 的 `files.file_path` 逻辑（那块已经相对了）
- 不自动改写智能体已写的索引（发现是检查，不是修复——改不改由它自己决定）
- 不校验相对路径是否**真实存在**（那是另一个检查，避免和「迁移中临时缺失」混淆）
- 不做多根同名类目的分开展示（当前会合并计数，已知限制，另议）

## 真相影响

- **CONTEXT.md**：`相对路径（relocatable path）` 术语扩写——不只 `files.file_path`，
  长期内容索引同样口径，基准是**索引文件所在目录**
- **PROJECT.md**：约束「路径相对化」补一句「长期内容索引同样适用」
- **ADR-0005**：加一节「为什么这条也管长期内容」
