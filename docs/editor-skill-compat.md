# Midnight Skills 编辑器 skill 适配指南

> 目标：让 recall / core / pulse / compass 四个 skill 适配 Claude Code、Cursor、Trae、CodeBuddy 等编码编辑器的 Agent skill 机制。
> 核心结论：**Anthropic Agent Skills 已成为事实标准**，我们的 SKILL.md 格式完全兼容，多数编辑器直接复制即可。
> 适配状态：2026-08-27

---

## 一、核心结论（先看这个）

**我们的 SKILL.md 格式 = Anthropic Agent Skills 标准格式，完全兼容，无需转换。**

Anthropic 官方模板（primary source: github.com/anthropics/skills 仓库 `template/SKILL.md`）：

```yaml
---
name: template-skill
description: Replace with description of the skill and when Claude should use it.
---
```

我们的 4 个 SKILL.md 正是这个格式（`name` + `description` frontmatter + 正文指令 + `scripts/` 目录）。

| 编辑器 | 支持 Agent Skills？ | 需要转换吗？ |
|---|---|---|
| **Claude Code** | ✅ 原生 | 否，直接复制 |
| **Claude Desktop / Claude 应用** | ✅ 原生 | 否，直接复制 |
| **Cursor** | ✅ 支持（Agent Skills） | 否，复制到 `.cursor/skills/` |
| **Trae** | ✅ 支持（Agent Skills） | 否，复制到 `.trae/skills/` |
| **CodeBuddy** | ✅ 支持（Agent Skills） | 否，复制到 skills 目录 |

---

## 二、Claude Code

### 机制

Claude Code 使用 **Agent Skills**：一个 skill 是一个目录，包含 `SKILL.md`（frontmatter 定义 name/description + markdown 指令）和可选的支持文件。

### 安装位置

```
# 全局（所有项目可用）
~/.claude/skills/<skill-name>/SKILL.md

# 项目级（仅当前项目）
<project>/.claude/skills/<skill-name>/SKILL.md
```

### 安装命令

```bash
# 全局安装（把 4 个 skill 复制到 ~/.claude/skills/）
mkdir -p ~/.claude/skills
cp -r skills/recall ~/.claude/skills/
cp -r skills/core ~/.claude/skills/
cp -r skills/pulse ~/.claude/skills/
cp -r skills/compass ~/.claude/skills/
```

### 验证

在 Claude Code 中 `/` 应该能看到 `recall`、`core`、`pulse`、`compass` 四个命令。

---

## 三、Cursor

### 机制

Cursor 支持两种相关机制：
- **Rules**（`.cursor/rules/*.mdc`）— 旧式规则文件，带 frontmatter（globs/description）
- **Agent Skills**（`.cursor/skills/`）— 与 Anthropic Agent Skills 同格式，支持 SKILL.md

Agent Skills 是我们的目标格式，直接复制。

### 安装位置

```
.cursor/skills/<skill-name>/SKILL.md
```

### 安装命令

```bash
# 项目级（在项目根目录）
mkdir -p .cursor/skills
cp -r skills/recall .cursor/skills/
cp -r skills/core .cursor/skills/
cp -r skills/pulse .cursor/skills/
cp -r skills/compass .cursor/skills/
```

> 注意：Cursor 的 Agent Skills 主要在 Agent 模式下被触发。若想兼容 Rules 机制（`.mdc`），可用脚本转换（见下文"兼容 .mdc 的说明"）。

---

## 四、Trae（字节跳动）

### 机制

Trae 支持 **Agent Skills**（与 Anthropic 同格式），可通过 `/skills` 目录加载。

### 安装位置

```
# 项目级
<project>/.trae/skills/<skill-name>/SKILL.md
```

### 安装命令

```bash
mkdir -p .trae/skills
cp -r skills/recall .trae/skills/
cp -r skills/core .trae/skills/
cp -r skills/pulse .trae/skills/
cp -r skills/compass .trae/skills/
```

---

## 五、CodeBuddy（腾讯）

### 机制

CodeBuddy 支持 Agent Skills（与 Anthropic 同格式）。安装位置通常在项目的 `.codebuddy/` 或用户目录的 skills 目录。

### 安装位置

```
<project>/.codebuddy/skills/<skill-name>/SKILL.md
```

### 安装命令

```bash
mkdir -p .codebuddy/skills
cp -r skills/recall .codebuddy/skills/
cp -r skills/core .codebuddy/skills/
cp -r skills/pulse .codebuddy/skills/
cp -r skills/compass .codebuddy/skills/
```

---

## 六、一键安装脚本

`install/install-skills.sh` 提供一键安装到指定编辑器。

```bash
# 安装到 Claude Code 全局
bash install/install-skills.sh claude

# 安装到当前项目的 Cursor
bash install/install-skills.sh cursor .

# 安装到 Trae
bash install/install-skills.sh trae .

# 安装到 CodeBuddy
bash install/install-skills.sh codebuddy .
```

---

## 七、兼容 Rules（.mdc）的说明

Cursor 的 Rules（`.mdc`）是另一种机制，与 Agent Skills 不同：

```markdown
---
description: 规则描述
globs: **/*.ts
---
规则内容
```

我们的 skill **不需要**转换为 `.mdc`——Agent Skills 是更现代、功能更完整的机制，且各家编辑器都已支持。`.mdc` 主要用于"始终生效的项目规则"，而 Agent Skills 用于"按需触发的能力"，两者定位不同。

---

## 八、验证清单

安装后逐项验证：

1. **触发**：在编辑器里输入 `recall` 或"帮我回忆"，确认 skill 被加载
2. **脚本可执行**：确认 `scripts/` 下的 Python 脚本有执行权限且 `python` 可用
3. **路径**：确认 skill 里的路径假设（如 `~/.midnight/recall/`）在你环境中有效
4. **多 agent 隔离**：测试 `--agent Nova` 和 `--agent Coco` 各自独立

---

## 九、依赖说明

各 skill 的 `scripts/` 需要：
- Python 3.8+
- `requests`（embedding / pulse 用到）
- 数据库用 SQLite（Python 内置）

安装：
```bash
pip install requests
```

---

*主要参考：github.com/anthropics/skills（Anthropic 官方 skills 仓库）、各家编辑器官方文档。*