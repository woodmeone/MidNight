# 01 — 开机清单生成器（boot manifest）

Spec: `../spec.md` ｜ Blocked by: 无 ｜ 分支: `feat/self-index`

## 用户故事

作为**刚醒来的智能体**，我想要会话第一条就看到「我是谁 + 我的资产目录长什么样」，
以便不必每轮重复摸索自己，也不用等别人提醒才想起手里有家伙。

## 背景 / 为什么要变

现在新会话开头跑的是 `prep.py`——按 query 召回，不是开机清单。
`session_start.py` 里有 `compile_identity_summary()`，但它只编译 self.md 的字段，没有任何流程调用它，
也不含资产。结果是：**零件有，没装上。**

开编（kaibian）的实证：它已经建出 `kb/ refs/ tools/ snippets/ templates/ checklists/` + `ASSETS.md`，
但日记写着「是用户提醒才想到存可执行资产」——因为干活时看不见这些目录。

## 验收标准

- [ ] 新增 `skills/recall/scripts/boot.py`，对外一个函数 + 一个 CLI：
      `compile_boot_manifest(identity, workspace=None, budget=120) -> str`
- [ ] 输出含两块：**人设摘要**（name / 风格 / 边界）+ **资产**（类目计数或条目名 + 索引路径）
- [ ] **硬预算 ≤120 字**；超预算按序砍（条目名 → 类目 → 人设补充项），**绝不截断半句**
- [ ] **条目 vs 类目切换**：资产条目总数 ≤5 直出条目名；>5 按子目录给「类目 + 计数」
- [ ] 资产根候选：`<agent_dir>/assets/`；若 `--workspace` 下存在 `ASSETS.md` 则一并纳入
- [ ] **资产目录不存在** → 明说「资产目录不可用（路径 X）」，禁止静默给空或给「无」
- [ ] **self.md 不存在** → 人设段降级为 `我是 <identity>`，不崩
- [ ] **只读**：跑完任何文件 `mtime` 不变；不建表、不写库、不写 jsonl
- [ ] 现有 `prep.py` / `recall.py` / `session_start.py` 行为**逐位不变**（boot.py 是独立新入口）
- [ ] 全量测试与 G1 基线一致（**343 passed / 6 skipped**，2026-11-14 实测于 `feat/self-index` @ `develop`）

## 票（垂直切片，按序实现）

- [ ] 票1：扫描 + 渲染 —— 扫 self.md 与资产根，输出两块文本（先不限预算）｜ Blocked by: 无
- [ ] 票2：预算裁剪 —— 120 字硬上限，按序降级，不截半句 ｜ Blocked by: 票1
- [ ] 票3：CLI + 失败态 —— `--identity/--workspace/--budget`，三种失败态各给人话 ｜ Blocked by: 票2

## 范围外（本轮不做）

- **不做能力扫描**（技能库清单）——Issue 02 用一句指路替代
- **不做同伴扫描**（`list_agents()`）——同上
- **不做自动注入**：本轮只交付命令 + 文档纪律，不碰 harness 的 session-start hook
- **不动 `~/.midnight/recall/*/` 下任何数据**：只读
- 不做开机清单的持久化/缓存（每次现扫）

## 对抗式自检（写测试时问自己）

- 资产目录存在但全空 → 输出什么？不许是空串
- 资产 5 条边界、6 条边界 → 切换点是否精确
- 类目名超长（30 字）→ 预算怎么处理
- self.md 的 frontmatter 坏掉 → 崩不崩
- `--budget 10` → 还剩什么，还是空
- 同一秒跑两次 → 输出是否确定性一致

## 真相影响

- **PROJECT.md**：模块地图加 `boot.py`；"核心业务流程"加第 6 条「开机」；"关键数据结构"说明资产是目录不是表
- **CONTEXT.md**：新增术语 **开机清单（boot manifest）**、**资产（asset）**、**三级加载**
- **ADR**：`docs/adr/0004-boot-manifest-and-assets-as-files.md`——记录「为什么资产不进库、能力/同伴不进清单」六个被否决方案（三条件全中：难逆转、有真实取舍、后来者会问为什么）
