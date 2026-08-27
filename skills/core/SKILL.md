---
name: core
description: "跨端统一时间线——让不同会话/不同端的 AI 共享同一份记忆时间线。当用户切换会话、跨端聊天或需要了解其他会话上下文时触发。"
---

# midnight-core

让 AI 在不同会话、不同设备之间拥有**统一的事实时间线**。你在电脑上聊的事，手机上打开时 AI 自动知道——因为"是同一个自己"。

## 核心能力

1. **跨会话记录**：关键消息自动写入时间线，带来源标记（"来自工作会话"、"来自手机端"）
2. **跨端补充**：新会话开始时，自动拉取其他会话/端的最近消息，补充当前上下文
3. **来源标记**：补充的内容带上 `[来自 XX]` 标记，AI 知道"这是从哪知道的"
4. **就近去重**：5 分钟内同一会话的相同内容不重复写入

## 触发条件

| 触发词/情境 | 操作 |
|---|---|
| 新会话开始 | 调用 `timeline.py` 获取其他会话的最近消息 |
| 用户切换话题/设备 | 调用 `append.py` 记录当前关键消息 |
| 用户说"刚才在另一个会话提到" | 调用 `timeline.py` 获取相关会话记录 |
| 对话产生重要结论 | 调用 `append.py` 记录到时间线 |

## 协议

### 写入时间线

```bash
# 记录用户消息
python append.py --session "工作会话" --source "电脑端" --role user --content "帮我看看这个方案的可行性"

# 记录 AI 回复
python append.py --session "工作会话" --source "电脑端" --role assistant --content "好的，我来分析一下……"
```

### 读取时间线

```bash
# 获取其他会话最近 10 条消息
python timeline.py --session "当前会话名" --limit 10 --hours 24

# 获取所有会话最近 1 小时的消息
python timeline.py --hours 1
```

### 输出格式

```
[跨端通知] 以下是来自其他会话的最近消息：

  来自 [电脑端] · 2026-08-20 14:30 🧑 用户: 帮我看看这个方案的可行性
  来自 [电脑端] · 2026-08-20 14:31 🤖 Nova: 好的，我来分析一下……
  来自 [手机端] · 2026-08-20 10:00 🧑 用户: 记得提醒我晚上买牛奶
```

## 与 midnight-recall 的关系

- `midnight-recall` 存的是**摘要日记**（处理过的、打了标签的、可联想检索的长期记忆）
- `midnight-core` 存的是**原始消息**（未处理的、按时间线排列的、跨会话共享的短期上下文）
- **两者互补**：recall 管"还记得吗"，core 管"刚才在另一个窗口说了什么"

## 文件结构

```
skills/core/
├── SKILL.md
├── scripts/
│   ├── schema.py          # SQLite 初始化
│   ├── append.py           # 追加消息到时间线
│   └── timeline.py         # 读取跨会话时间线
├── tests/
└── demo.py
```

## 存储

- 数据库：`~/.midnight/core/core.db`
- 表：`messages`（id, session_id, source, role, content, checksum, created_at）