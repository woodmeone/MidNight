# 06 — 路径可移植性三级判据 + 全库路径体检

Issue: #15 ｜ Spec: `../spec.md` ｜ Blocked by: #14 ｜ 分支: `feat/self-index`

> 本文件自包含。**这是 #14 的扩展**：#14 只管 `LONGTERM.md`，
> 实测发现真正的重灾区是 `self.md`——30 处绝对路径里 20 处在它里面。

---

## 实测盘点（2026-11-15，12 个 agent）

```
=== 按「文件 × 类型」汇总 ===
  LONGTERM.md    EXTERNAL(保留绝对)     5
  LONGTERM.md    HOME(应写 ~/)        3
  LONGTERM.md    INSIDE(必须相对)       1
  agent.json     EXTERNAL(保留绝对)     1
  self.md        EXTERNAL(保留绝对)     4
  self.md        HOME(应写 ~/)        9
  self.md        INSIDE(必须相对)       7
  --- 合计 30 处 ---
```

### 为什么会这样

`#10` 给 `self.md` 加了 `paths` 字段（「先查技能库 / 有事问同伴」），
智能体照着填，很自然就写成了自己机器上的绝对路径：

```json
"paths": [
  "我的长期内容在 C:\\Users\\WoodMe\\.midnight\\recall\\kaibian\\longterm\\ ，总索引 LONGTERM.md",
  "遇到不会的活，先查技能库 C:\\Users\\WoodMe\\.dsh\\skills\\（唯一真源是 ~/.agents/skills）"
]
```

**同一句话里，前半句是绝对路径，后半句已经写了 `~/.agents/skills`。**
写 `~` 的那半句是可移植的，写 `C:\Users\...` 的那半句不是——说明它其实知道
「相对写法存在」，只是没人告诉它该用哪个。

### 三档，不是两档

`#14` 只分了「root 内 / root 外」。实测发现中间还有一档：**用户目录内**。

| 档 | 例子 | 迁移后果 | 该写成 |
|---|---|---|---|
| `INSIDE` | `C:\Users\WoodMe\.midnight\recall\kaka\longterm\` | 必断（跟着 agent 目录走） | `longterm/` |
| `HOME` | `C:\Users\WoodMe\.dsh\skills` | 换用户名就断 | `~/.dsh/skills` |
| `EXTERNAL` | `D:\Project\AIRPCreate` | 换机器后需重指，但当前只能绝对 | 保留绝对 |

`~` 这一档是这次新发现的：`C:\Users\WoodMe\.dsh\skills` 和 `~/.dsh/skills`
指的是同一个地方，但**只有一个能搬**。

---

## 用户故事

作为**要把整套智能体搬到另一台机器的人**，我想要所有「用来定位的路径」都写成
跟着目录走的形式，以便搬完之后不用手工改 30 处引用。

---

## 实现规格

### 改动一：`boot.py --check` 扩展到三处载体

现在只查 `LONGTERM.md`。改为查：

| 载体 | 查什么 |
|---|---|
| `self.md` | frontmatter 的 `mutable`（JSON 里的路径要**解转义**再判） |
| `agent.json` | 整个 JSON 的字符串值 |
| `<root>/LONGTERM.md` | 全文 |

新增三级判定，替换现在的 `inside`/`outside`：

```python
def classify_path(path: str, agent_dir: str) -> str:
    """返回 'inside' | 'home' | 'external'。"""
```

- `inside`：落在 `agent_dir` 之内（含 `longterm/`）
- `home`：落在 `~` 之内但不在 `agent_dir` 之内
- `external`：都不在

### 改动二：输出分级 + 建议重写

```
[路径体检] @kaibian
  ✗ 2 处该修（指向自己却写绝对，搬机器必断）
    self.md    第 0 项  C:\Users\WoodMe\.midnight\recall\kaibian\longterm\
               → longterm/
  ⚠ 2 处可改进（在用户目录下，写 ~/ 就能搬）
    self.md    第 1 项  C:\Users\WoodMe\.dsh\skills\
               → ~/.dsh/skills/
  ℹ 2 处外部真源（当前只能绝对，迁移后重指）
    self.md    第 3 项  D:\Project\AIDevelopSOP

共 30 处：该修 8 · 可改进 12 · 外部 10
```

- `--check` 默认只报，退出码 0
- `--check --strict`：有 `inside` 或 `home` → 退 1（两者都该修）
- `--check --all`：扫全部 agent，不只当前 identity

### 改动三：`SKILL.md` 写死三级纪律

在「索引里写相对路径」那节扩写：

```markdown
### 三种路径，三种写法

| 指向哪里 | 写成什么 | 例子 |
|---|---|---|
| **自己的目录**（记忆区、longterm、日记） | 相对那个目录的基准 | `longterm/LONGTERM.md` |
| **用户目录下**（技能库、桌面、其他 home 内的东西） | `~/` 开头 | `~/.dsh/skills` |
| **别的盘 / 别人的项目** | 保留绝对路径，标注「外部真源」 | `D:\Project\Other` |

判据一句话：**这段路径跟着谁搬家？**

- 跟着 agent 目录 → 写相对（`longterm/`）
- 跟着用户账户 → 写 `~`（换机器还是同一个家目录）
- 跟着另一个项目 → 只能绝对，但要说清它不是本区内容

**同一个 `self.md` 里两种写法并存，是最典型的错**：
`...longterm\\ ，总索引…` 和 `~/.agents/skills` 出现在同一段——写 `~` 的那句能搬，
写 `C:\Users` 的那句不能。
```

### 改动四：老数据只报告，不自动改

**不主动改写任何 `self.md` / `agent.json` / `LONGTERM.md`。**

理由同 #14：这些是智能体自己的认知载体，改不改由它决定。工具只做两件事：
1. 体检报告 + 建议写法
2. `--strict` 供 CI 拦住新增的坏路径

**给智能体的迁移动作**（写进 SKILL.md）：看到体检报告后，自己 `--add-paths` 或手改。

---

## 测试

`test_boot.py` 扩写（现有 32 条）：

| # | 测试名 | 断言 |
|---|---|---|
| 33 | `test_classify_inside` | agent 目录内的路径 → `inside` |
| 34 | `test_classify_home` | `~/.dsh/skills` 与 `C:\Users\X\.dsh` 都 → `home` |
| 35 | `test_classify_external` | `D:\Other` → `external` |
| 36 | `test_check_scans_self_md` | self.md 的 mutable 里有绝对路径 → 报出 |
| 37 | `test_check_scans_agent_json` | agent.json 里有 → 报出 |
| 38 | `test_check_decodes_json_escapes` | `C:\\Users\\...`（JSON 双反斜杠）能正确识别成一条 |
| 39 | `test_report_shows_rewrite_suggestion` | 输出含 `→ longterm/` 这类建议 |
| 40 | `test_strict_fails_on_inside` | 有 inside → 退 1 |
| 41 | `test_strict_fails_on_home` | 有 home → 退 1 |
| 42 | `test_strict_passes_on_external` | 只有 external → 退 0 |
| 43 | `test_check_all_agents` | `--all` 扫多个 agent，各自标题分开 |
| 44 | `test_check_readonly` | 跑完 self.md / agent.json mtime 不变 |

---

## 验收标准

- [ ] `boot.py --check` 覆盖三处载体：`self.md` / `agent.json` / `LONGTERM.md`
- [ ] 三级判定 `inside` / `home` / `external`，`home` 包含 `~/` 与 `C:\Users\...` 两种写法
- [ ] JSON 转义（`C:\\Users\\...`）能正确解码成一个路径
- [ ] 报告给出 `原值 → 建议值`
- [ ] `--strict` 在 `inside` 或 `home` 时退 1；只 `external` 时退 0
- [ ] `--all` 全 agent 体检，按 agent 分组
- [ ] **只读**：不写任何 self.md / agent.json / LONGTERM.md
- [ ] `SKILL.md` 有「三种路径，三种写法」及其判据（跟着谁搬家）
- [ ] 12 条新测试全绿；全量失败 0

## 票（垂直切片）

- [ ] 票1：`classify_path` 三级判定（含 `~` 归一）｜ Blocked by: 无
- [ ] 票2：三处载体扫描 + JSON 解转义 ｜ Blocked by: 票1
- [ ] 票3：分级报告 + 建议重写 + `--strict` / `--all` ｜ Blocked by: 票2
- [ ] 票4：SKILL.md 三级纪律 ｜ Blocked by: 无

## 范围外（本轮不做）

- **不自动改写**任何存量 self.md / agent.json / LONGTERM.md
- 不扫 `dailynote/*.md`——记忆正文里出现绝对路径是**正常**的（记的是当时的事），
  它不需要被解析，不该进体检
- 不扫 `retrieval_ledger.jsonl`——里面的 `query` 是用户问的话，不是配置
- 不动 `evolution.log`——它是历史审计记录，改了就失真
- 不处理 Windows 大小写 / 短路径名（`PROGRA~1`）这类边界
- 不做跨 agent 路径改写（别的 agent 的 self.md 只能它自己改）

## 真相影响

- **CONTEXT.md**：`相对路径` 术语改为**三级**（inside / home / external）；
  新增 **外部真源**（已有，扩写为三档之一）
- **PROJECT.md**：「路径相对化」约束改为三级判据表述
- **ADR-0005**：补一节「为什么是三档不是两档」——`~` 这一档的发现过程
