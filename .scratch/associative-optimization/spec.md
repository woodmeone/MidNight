# 联想算法优化 规格（+ 分解后的 tickets）

> 权威母档：`docs/associative-optimization-spec.md`。本文件是 to-tickets 执行切片。
> 分支：`feature/optimize-associative-algorithm`。日期：2026-09-08。

## 关键约束（贯穿全部票）
- **AI 只判关键词，代码只做召回，AI 只收数据**；召回参数（k/budget/threshold）锁死为代码安全默认。
- 不建 VCP 决策层伪判定（EPA/残差金字塔/PSR 不做算法）。
- 记忆正文**永不删除**，只降权（P2）。
- `recall_associative` 对外签名不变，改动锁在引擎层（recall.py + tag_network.py + schema）。

## Ticket 清单（blocking 关系）

| 票 | 内容 | Blocked by | 对应 Spec |
|---|---|---|---|
| T0 | 更新 ADR-0001：开放借鉴（借思想自由、借代码落 License 声明） | 无 | P0.5 / §4.1 |
| T1 | tag-first 前置门控：tag 从"事后抬分"改为"事前约束候选" | 无 | P0 / §4.1 铁律2 |
| T2 | 深联想质量门槛 + 条数硬上限 | T1 | P1 |
| T3 | 记忆保鲜：弱关联/久未用条目自动降权（不删除） | T1 | P2 |
| T4 | 召回性能：倒排/FTS 索引 + 结果缓存 | T1 | P3 |

> 建议严格执行顺序：T0 → T1 → T2 → T3 → T4。每票独立 /tdd + /code-review，`recall_associative` 接口不变，基线 157 测试全绿。