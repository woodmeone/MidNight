# 05 — SKILL.md + 配置 + 端到端验证

**What to build:** 把 midnight-recall 包装成完整的 Reasonix skill：`SKILL.md` 定义 AI 何时写日记、日记格式怎么写、如何触发召回、召回参数怎么调；`config.toml` 首次运行自动生成；端到端 demo 脚本（`demo.py`）演示完整流程（写日记 → ingest → recall → 输出）。这是 skill 的"用户界面"。

**Blocked by:** 04 — time truncation

**Status:** ready-for-agent

- [ ] `SKILL.md` 包含：YAML frontmatter（name/description/triggers）、写日记协议（文件格式、存放路径）、召回调用说明（recall.py 参数）、路由表（按场景推荐不同参数组合）
- [ ] 触发条件：用户说"记住"、"还记得吗"、"帮我回忆"、"我上次说"等
- [ ] `config.toml` 首次运行自动生成（含默认 embedding 和 recall 参数）
- [ ] `demo.py`：写测试日记 → ingest → recall 验证一步到位
- [ ] 测试 `test_end_to_end.py`：完整流程走通（写 → 入库 → 召回 → 断言命中）