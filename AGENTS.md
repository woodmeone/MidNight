# AGENTS.md — Midnight Skills

Midnight Skills 是一组受 VCP(设计思想) 启发但完全原创的原子化 Reasonix skill。
目标：给 AI 装上持久记忆和生命——记得你、会办事、不用催、懂选择。

## 关键限制（违反即项目失败）

1. **不复制 VCP 代码**（ADR-0001）：`scripts/` 全部原创实现，不摘抄 VCPToolBox 的任何函数。
2. **不引用 VCP 品牌**：命名、README、文档中不得出现 "VCP" 作为品牌前缀。
3. **完全自包含**：不依赖 VCPToolBox 进程或服务器，任何环境可跑。

## 项目结构

```
midnight-skills/
├── CONTEXT.md              # 领域词汇表 + 决策记录（术语/决策变更时更新）
├── ROADMAP.md              # 进度追踪（Phase 1-4）
├── AGENTS.md               # 本文件
├── docs/
│   ├── adr/                # 架构决策记录
│   └── agents/             # 工程 skill 配置（issue tracker / triage / domain）
└── skills/                 # 原子 skill（每个一个目录）
    ├── recall/             # midnight-recall（记忆）
    ├── core/               # midnight-core（跨端）
    ├── pulse/              # midnight-pulse（心跳）
    └── compass/            # midnight-compass（路由）
```

## Agent skills

### Issue tracker

Issues and specs live as markdown files in `.scratch/`. See `docs/agents/issue-tracker.md`.

### Triage labels

The five canonical triage roles with default label names. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context repo — one `CONTEXT.md` + `docs/adr/` at the root. See `docs/agents/domain.md`.

## 工程流程约定

- 走 mattpocock/skills 主流程：grill-with-docs → to-spec → to-tickets → implement(带 tdd) → code-review
- 实现顺序：recall → core → pulse → compass