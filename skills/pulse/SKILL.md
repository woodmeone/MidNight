---
name: pulse
description: "自主心跳——让 AI 自己定闹钟续命、干完活自己醒来继续。当需要长时间任务、多轮分析、自主监控时触发。"
---

# midnight-pulse

让 AI 拥有"自主心跳"——不是"你问一句它答一句"，而是它自己安排时间、自己醒来继续干活。

## 核心能力

1. **自主续命**：AI 输出 `[[Pulse::Start]]` 启动心跳，干完活输出 `[[Pulse::Complete]]` 自动结束
2. **弹性调度**：`[[Pulse::Next::秒数]]` 自定义下次心跳间隔（默认 2 秒），`[[Pulse::NextPrompt]]...[[/Pulse::NextPrompt]]` 自定义下一轮提示词
3. **安全防护**：最大轮数（15 轮）、超时（5 分钟）、Complete > Fail > Stop > Start 优先级
4. **VCP 兼容**：协议设计受 VCP Flowlock 启发，但简化了语法（`[[Pulse::]]` 而非 `[[Flowlock::]]`）

## 协议

AI 在回复中嵌入以下指令：

| 指令 | 含义 | 优先级 |
|---|---|---|
| `[[Pulse::Start]]` | 启动心跳模式 | 最低 |
| `[[Pulse::Next::180]]` | 下次心跳间隔 180 秒 | — |
| `[[Pulse::NextPrompt]]...[[/Pulse::NextPrompt]]` | 自定义下一轮提示词 | — |
| `[[Pulse::Complete]]` | 任务完成，附报告 | 最高 |
| `[[Pulse::Fail]]` | 任务失败，附原因 | 高 |
| `[[Pulse::Stop]]` | 主动退出心跳 | 中 |

## 触发条件

| 触发词/情境 | 操作 |
|---|---|
| 用户说"帮我处理一下"、"分析一下"、"整理一下" | 启动心跳协议 |
| 需要多步推理、长时间运行的任务 | 在回复中嵌入 `[[Pulse::Start]]` |
| 任务完成 | 输出 `[[Pulse::Complete]]` + 报告 |
| 任务卡住 | 输出 `[[Pulse::Fail]]` + 原因 |

## 使用示例

### 启动心跳

```bash
python pulse.py \
  --api-url "https://api.deepseek.com" \
  --api-key "sk-..." \
  --model "deepseek-v4-flash" \
  --system "你是一个文件分析助手" \
  --prompt "请分析当前目录下所有 Python 文件，给出代码质量报告。每分析完一个文件说继续。" \
  --rounds 15 \
  --timeout 300
```

### AI 回复示例

```
好的，开始分析。[[Pulse::Start]]

分析文件1: main.py — 代码质量良好，复杂度低。
[[Pulse::Next::5]]
[[Pulse::NextPrompt]]继续分析下一个文件[[/Pulse::NextPrompt]]

---

分析文件2: utils.py — 有一些重复代码，建议重构。
[[Pulse::Next::5]]
[[Pulse::NextPrompt]]继续分析下一个文件[[/Pulse::NextPrompt]]

---

所有文件分析完毕。总结：3个文件，2个需要改进。
[[Pulse::Complete]] 分析完成，共检查3个文件，2个需要重构。
```

## 文件结构

```
skills/pulse/
├── SKILL.md
├── scripts/
│   └── pulse.py          # 心跳循环引擎
├── tests/
│   └── test_pulse.py     # 26 个测试
```