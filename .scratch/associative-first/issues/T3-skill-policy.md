# T3 — 规则层与真相回写

Issue: #5 ｜ Spec: `../spec.md` ｜ Blocked by: 票2

## 目标

把"默认走联想、md 不作索引"从**代码能力**升成**规则与真相**：SKILL.md 有铁律与查询派生协议，CONTEXT/PROJECT 有新术语与模块，ADR 记下不可逆取舍，并用契约测试防规则被后面的人悄悄删掉。

## 落点

- `skills/recall/SKILL.md`：新增「检索通道铁律」「查询派生协议」两节；触发条件表补"时间轴/字面问题"一行
- `PROJECT.md`：模块地图（`recall/scripts` 核心入口 + 内部文件表加 `ledger.py`）、核心业务流程 2 补通道选择、当前支持功能加一行
- `CONTEXT.md`：术语表新增 检索通道 / 联想通道 / 确定性通道 / 检索留痕 / md 源文件
- `docs/adr/0002-md-is-source-not-index.md`：新 ADR（三段式）
- `tests/test_skill_contract.py`：文档契约测试

## 验收

- [ ] SKILL.md 明确：默认=联想；`--timeline/--literal` 仅用于结构性时间/字面问题；md **永不作为检索目标**；只有用户显式说"读原文/看文件"才允许，且必须在回复里声明授权通道
- [ ] SKILL.md 有查询派生协议（2–5 个名词性线索 + 对象 anchor + `--multi-scale`），并给出"自检触发点"（发现自己要 grep dailynote → 停，改跑 timeline/literal）
- [ ] CONTEXT.md 五个术语有定义；PROJECT.md 三处回写一致
- [ ] ADR-0002 满足三条件（难以逆转 / 真实取舍 / 后来者会问）
- [ ] 契约测试：断言 SKILL.md 含通道名与例外条件；断言 SKILL.md 不再把"读 md"写成检索路径
- [ ] 全量测试仍 265 passed 起步、无回归
