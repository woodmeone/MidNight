---
name: compass
description: "语义路由——按问题难度自动选模型，主模型挂了自动切换。当需要决定用哪个模型处理当前任务时触发。"
---

# midnight-compass

让 AI 自动判断当前任务应该用什么模型——日常闲聊用轻量级模型，复杂推理用重量级模型，主模型挂了自动降级。

## 核心能力

1. **语义路由**：按问题内容自动匹配最合适的模型——聊天、写代码、深度推理、创意写作各自走不同的模型
2. **容灾切换**：主模型超时/报错时自动降级到备用模型
3. **可配置路由表**：通过 JSON 配置文件自定义路由规则和备选模型

## 触发条件

| 触发词/情境 | 操作 |
|---|---|
| 开启新对话 | 调用 `route.py` 判断当前话题类型 |
| 用户提出复杂问题 | 调用 `route.py` 选择最佳模型 |
| 主模型回复失败 | 使用路由结果中的 `fallback_models` |

## 路由表

默认配置（`~/.midnight/compass/config.json`）：

| 路由 | 匹配场景 | 模型 |
|---|---|---|
| `daily_chat` | 日常聊天、闲聊、寒暄 | flash |
| `research_and_coding` | 信息调研、代码编写、调试 | pro |
| `deep_reasoning` | 复杂推理、形式逻辑、哲学思辨 | pro |
| `creative_writing` | 创意写作、文案、故事 | flash |
| `memory_operation` | 记忆操作、日记、检索 | flash |

## 使用示例

```bash
# 路由一条查询
python route.py --query "帮我分析这段代码的复杂度"

# 使用指定 preset
python route.py --query "写一首诗" --preset default
```

## 文件结构

```
skills/compass/
├── SKILL.md
├── scripts/
│   ├── route.py          # 路由引擎
│   └── embedding.py      # embedding 客户端（共享）
└── tests/
    └── test_compass.py   # 16 个测试
```