# midnight-recall

> 让 AI 拥有长期记忆——自动写日记、联想式召回。
> 设计受 VCP(VCPToolBox) 的 TagMemo 记忆算法启发，但代码全部原创实现（详见 `docs/adr/0001-original-implementation.md`）。

## 它能做什么

- **自动写日记**：Agent 把重要对话写成日记文件，`ingest.py` 自动入库
- **联想式召回**：不靠关键词命中——标签共现网络 + 脉冲传播，你今天说"压力大"，昨天聊的"考试"自动浮上来
- **时间感知**：最近的记忆权重更高，新会话开头不空白
- **完全自包含**：Python + SQLite，零数据库服务，任何环境可跑

## 安装

```bash
pip install requests  # 唯一外部依赖（默认可离线用假 embedding）
```

把 `skills/recall/` 目录复制到 Reasonix 全局技能库：

```bash
# Windows
cp -r skills/recall %APPDATA%/reasonix/skills/recall
```

## 使用

### 写日记（Agent 操作）

用 `write_file` 写 `~/.midnight/recall/dailynote/YYYY-MM-DD_HHMMSS.md`：

```yaml
---
maid: Nova
created: 2026-08-20T14:30:00
tags: [考试, 压力, 面试]
---
今天讨论了面试，有点紧张，准备了三天。
```

### 入库

```bash
python ingest.py ~/.midnight/recall/dailynote/
```

### 召回

```bash
python recall.py --query "焦虑" --k 10 --tag-weight 0.5 --time-ratio 0.3
```

### 端到端演示

```bash
python demo.py
```

## embedding 配置

默认使用确定性假 embedding（离线可用，仅用于验证链路）。
生产使用可配置 SiliconFlow BAAI/bge-m3 或其他 OpenAI 兼容 embedding API：

```bash
export SILICONFLOW_API_KEY="sk-xxx"   # 设置后自动切换真实 embedding
export MIDNIGHT_DB_PATH="~/.midnight/recall/recall.db"
export MIDNIGHT_DAILYNOTE_PATH="~/.midnight/recall/dailynote/"
```

## 验证

```bash
python -m pytest tests/   # 40 个测试
```

## 许可证

CC BY-NC-SA 4.0（非商业使用，详见根目录 LICENSE）