# Midnight Skills

> 给 AI 装上持久记忆和生命——记得你、会办事、不用催、懂选择。

一组原子化 Reasonix skill，把 AI 的核心缺陷（无记忆、无联想、无跨端身份、无自主行动）逐一补齐。设计受 VCP 的 TagMemo 记忆算法启发，**代码全部原创实现**，采用 CC BY-NC-SA 4.0 许可（非商业使用）。

## 四个 skill

| Skill | 解决的问题 | 核心能力 |
|---|---|---|
| **recall** | AI 没有长期记忆，答完就忘 | 自动写日记 + 联想式召回（共现矩阵 + 脉冲传播） |
| **core** | 跨端/跨会话不认得你 | 统一事实时间线，多会话共享上下文 |
| **pulse** | AI 只能被动回复 | 自主心跳，AI 自己定闹钟循环工作 |
| **compass** | 不管什么题都用同一个模型 | 语义路由，按问题难度自动选模型 |

## 亮点

- **联想式记忆**：不靠关键词命中——你今天说"压力大"，三个月前聊的"考试"会自动浮上来（共现矩阵 + 脉冲传播）
- **物理隔离**：每个智能体独立数据库（`~/.midnight/recall/<agent>/`），数据不串
- **语义自动路由**：AI 自己判断该用哪个记忆区（`--auto` 参数）
- **完全自包含**：Python + SQLite，零外部服务，任何环境可跑
- **92 个测试**全部通过，含对抗式测试（SQL 注入、边界、数据完整性）

## 快速开始

```bash
# 1. 安装依赖
pip install requests

# 2. 复制 skill 到 Reasonix 全局技能库
cp -r skills/* %APPDATA%/reasonix/skills/

# 3. 体验端到端演示
cd skills/recall && python demo.py
```

## 使用

```bash
# 写日记入库（Nova 智能体）
python ingest.py --agent Nova

# 联想召回
python recall.py --query "焦虑" --agent Nova

# 语义自动路由（AI 自己判断用哪个记忆区）
python recall.py --query "帮我看看这段代码" --auto
```

详见各 skill 的 `SKILL.md`。

## 测试

```bash
cd skills/recall && python -m pytest tests/ -q
# 92 passed
```

## 项目结构

```
midnight-skills/
├── skills/
│   ├── recall/      # 记忆（核心）
│   ├── core/        # 跨端统一
│   ├── pulse/       # 自主心跳
│   └── compass/     # 语义路由
├── docs/            # 架构决策 + 开发记录
├── CONTEXT.md       # 领域词汇表
└── AGENTS.md        # Agent 配置
```

## 许可证

CC BY-NC-SA 4.0（非商业使用，详见 LICENSE）
