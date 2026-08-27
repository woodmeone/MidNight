# Midnight Skills — ROADMAP

> 进度追踪文件。每次开工前看"当前状态"，收工后更新"已完成"。

## 当前状态（2026-08-20）

**阶段：Phase 1-4 全部完成（4 个 skill 已实现 + 部署到全局）**

- ✅ Phase 1: midnight-recall（记忆）— 40 功能测试 + 29 对抗式测试
- ✅ Phase 2: midnight-core（跨端统一）— 21 测试
- ✅ Phase 3: midnight-pulse（自主心跳）— 26 测试
- ✅ Phase 4: midnight-compass（语义路由）— 16 测试
- ✅ 全部部署到全局技能库（`%APPDATA%\reasonix\skills\`）
- ⬜ **下一步：用户实际试用 → 反馈 → 迭代 → 开源发布**

## 已确认决策速查

| 主题 | 决策 |
|---|---|
| 范围 | 记忆 + 跨端 + 心跳 + 路由（4 个原子 skill） |
| 命名 | `midnight-recall` / `midnight-core` / `midnight-pulse` / `midnight-compass` |
| 解耦 | 完全自包含，不依赖 VCP 进程/服务器 |
| 语言 | Python（sqlite3 标准库 + requests） |
| 存储 | SQLite 单文件库 |
| embedding | 双后端：默认 SiliconFlow bge-m3，留本地接口 |
| 写日记 | Agent 直接写文件到 `~/.midnight/recall/dailynote/` + `ingest.py` 自动入库 |
| 法律红线 | 不复制 VCP 代码，不引用 VCP 品牌（详见 ADR-0001） |
| 实施顺序 | recall → core → pulse → compass |

## 实施路线图

### Phase 1: midnight-recall（记忆，核心）

- [x] **1.1** SKILL.md 骨架：触发条件、工作流、路由表
- [x] **1.2** `scripts/ingest.py`：读取 `dailynote/` 新文件 → 切块 → 调 embedding API → 写入 SQLite（chunks 表）
- [x] **1.3** `scripts/recall.py`：查询向量化 → 最近邻检索 → 共现矩阵联想扩增 → 输出上下文片段
- [x] **1.4** `scripts/tag_network.py`：从日记中提取标签 → 构建共现矩阵（脉冲传播的底座）
- [x] **1.5** 端到端验证：人工制造测试日记 → 入库 → 检索 → 验证联想命中
- [x] **1.6** 复制进全局技能库试运行

### Phase 2: midnight-core（跨端）

- [ ] **2.1** SKILL.md 骨架：统一事实时间线的概念与协议
- [ ] **2.2** `scripts/append.py`：向时间线追加带时间戳/来源的消息
- [ ] **2.3** `scripts/merge.py`：按时间线合并跨端历史，去重（模糊 diff）
- [ ] **2.4** 与 recall 共享 SQLite 库，验证跨会话记忆互通

### Phase 3: midnight-pulse（心跳）

- [ ] **3.1** SKILL.md 骨架：心跳协议 `[[Pulse::Start/Next/Complete/Fail/Stop]]`
- [ ] **3.2** `scripts/pulse.py`：定时器循环 + 下一轮提示词注入
- [ ] **3.3** 防失控：最大轮数、总超时、取消机制
- [ ] **3.4** 端到端验证：长任务自动续命直到 Complete

### Phase 4: midnight-compass（路由）

- [ ] **4.1** SKILL.md 骨架：模型路由表概念
- [ ] **4.2** `scripts/route.py`：向量相似度匹配 → 选出模型 + 备选降级链
- [ ] **4.3** 集成：验证按问题难度选模型、主模型挂掉切备选

### 收尾

- [ ] **5.1** 四个 skill 全部装进全局技能库
- [ ] **5.2** 用户实际试用 → 反馈 → 迭代
- [ ] **5.3** 开源发布（MIT 许可证文件、README、许可证声明）

## 项目文件索引

| 文件 | 职责 |
|---|---|
| `CONTEXT.md` | 领域词汇表 + 决策记录（改术语/决策时更新） |
| `docs/adr/*.md` | 架构决策记录（新决策产生时追加） |
| `ROADMAP.md` | 进度追踪 + 下一步计划（本文件） |