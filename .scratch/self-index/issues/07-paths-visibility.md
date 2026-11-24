# 07 — paths 要被显示出来（#10 的缺陷）

Issue: #16 ｜ Spec: `../spec.md` ｜ Blocked by: #10 ｜ 分支: `feat/self-index`

> 本文件自包含。**这是 #10 的缺陷**：`paths` 字段写进去了，但没有任何入口
> 把它送到智能体眼前。写了等于没写。

---

## 缺陷

`#10` 给 `self.md` 加了 `paths`（「先查技能库 / 有事问同伴」），
但 `boot.py` 的人设段只渲染三样：

```python
parts = [f'[开机] 我是{name}']
if style:    parts.append(style)
if boundary: parts.append(f'边界:{boundary}')
```

**没有 `paths`。** `session_start.py` 那边当初也明确取消了（理由：`self.md` 是它的家）。
结果是：

```
[开机] 我是开编｜第一性原理、复用优先、克制｜边界:只动自己的记忆区…
```

`paths` 里那两句「先查技能库」「有事问同伴」，**开机清单一个字都没有**。
智能体得主动去 `read self.md` 才看得到——而它开机时并不知道有这东西可读。

### 为什么这是缺陷

`#10` 的设计前提是「存在性写一句指路就永久有效」。但指路必须**先被看见**才有效。
看不见的指路，等于没写。

实测 12 个 agent，`paths` 全部被填了（智能体很认真），但没有任何一个能在开机清单里看到它。

---

## 用户故事

作为**一个刚醒来的智能体**，我想要开机就看到「不会的活去哪查、有事找谁」，
以便遇到墙的时候想起来还有这两条路，而不是自己从零造。

---

## 实现规格

### 改动一：`boot.py` 人设段带上 paths 的极短形式

`_render_identity` 增加一段，放在边界之后：

```python
paths = mutable.get('paths')
if paths:
    parts.append('路径:先查技能库·有事问同伴')
```

- **固定短串**，不动态截取 `paths` 内容
- 理由：动态截取容易产出半句（`paths` 现在是长句，里面还带绝对路径）；
  固定串只承担「提醒存在」的职责，具体内容去 `self.md` 读
- 全角间隔号 `·`，无空格。约 14 字

渲染后：

```
[开机] 我是开编｜第一性原理、复用优先、克制｜路径:先查技能库·有事问同伴
```

### 改动二：`paths` 缺失时不显示

老 `self.md` 没有 `paths`（`ensure_self` 幂等不动它）→ 这一段整段省略，
不留空 `｜`，不报错。这是 `#10` 定下的语义，保持。

### 改动三：可选 —— `--show-paths` 展开

```bash
python boot.py --identity X --show-paths
```

输出 `paths` 的完整内容（每行一条），供调试 / 体检用。**不进开机清单**——
那会占掉本就不多的上下文。

### 改动四：SKILL.md 说明「占位 vs 内容」

在「长期内容的维护」附近补一句：

```markdown
开机清单里的 `路径:先查技能库·有事问同伴` 是**占位提醒**，不是全文。
具体去哪、问谁，读你的 `self.md`。那两句是你自己写的，只有你读得懂细节。
```

---

## 测试

`test_boot.py` 扩写：

| # | 测试名 | 断言 |
|---|---|---|
| 45 | `test_identity_shows_paths_hint` | self.md 有 paths → 含 `路径:先查技能库·有事问同伴` |
| 46 | `test_identity_omits_paths_when_absent` | 无 paths → 不含 `路径:`，且不留空 `｜` |
| 47 | `test_paths_hint_is_fixed_string` | 无论 paths 内容多长，输出里都是那句固定串（不截取） |
| 48 | `test_show_paths_prints_full_content` | `--show-paths` 输出含 paths 原文 |
| 49 | `test_show_paths_absent` | 无 paths → 明确说「未设置」，退 0 |

---

## 验收标准

- [ ] `boot.py` 人设段在 `paths` 存在时带 `路径:先查技能库·有事问同伴`
- [ ] 固定串，不随 `paths` 内容变化
- [ ] `paths` 缺失时整段省略，不留空分隔符
- [ ] `--show-paths` 能展开全文
- [ ] 开机清单总长仍在合理范围（比现在多约 14 字）
- [ ] `SKILL.md` 说明「占位提醒 vs 全文」
- [ ] 5 条新测试全绿；全量失败 0

## 票（垂直切片）

- [ ] 票1：人设段带固定串 ｜ Blocked by: 无
- [ ] 票2：`--show-paths` 展开 ｜ Blocked by: 票1
- [ ] 票3：SKILL.md 说明 ｜ Blocked by: 无

## 范围外（本轮不做）

- 不把 `paths` 全文塞进开机清单（占上下文，且内容会变长）
- 不改 `session_start.py`（当初已明确取消，`self.md` 是它的家）
- 不动态摘要 `paths` 内容（同「不拦腰硬截」纪律）

## 真相影响

- **CONTEXT.md**：`开机清单` 术语补一句「人设段含 paths 的固定占位串」
- **PROJECT.md**：「核心业务流程·开机」补 `paths` 占位说明
