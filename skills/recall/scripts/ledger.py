"""检索留痕（retrieval ledger）——把"这一轮走了哪条检索通道"落成事实。

第一性：SKILL.md 里写"默认走联想通道"是**承诺**，留痕把它变成**可核查的事实**。
没有留痕时，"我走了联想"只能靠 Agent 自述；有留痕时，人可以直接看
`--audit` 反查这一轮到底查了没有、查了什么、命中几条。

三条硬性质（测试锁定）：
1. **旁路**：留痕是检索的旁路，写失败必须吞掉并返回 False——磁盘满、只读挂载、
   路径非法时，检索结果照常返回（记忆比日志重要）。
2. **隔离**：一 agent 一文件（`<agent_dir>/retrieval_ledger.jsonl`），
   A 的留痕 B 看不见，与 recall.db / dailynote 的物理隔离口径一致。
3. **纯净**：只由 CLI 入口调用，库函数（`recall_associative` / `prep_for_reply`）
   不许碰磁盘——否则单测会往真实 `~/.midnight` 里写垃圾。
"""
import json
import os
from datetime import datetime

from scripts.config import DEFAULT_AGENT, get_agent_dir

# 留痕文件名：jsonl（一行一条），追加成本 O(1)，人可 `Get-Content | Select -Last N`。
LEDGER_FILENAME = 'retrieval_ledger.jsonl'

# `--audit` 默认回看条数。
DEFAULT_AUDIT_LIMIT = 20

# 单条留痕里最多记多少个 chunk id：留痕用于**证明查过**，不用于复现召回全集。
MAX_CHUNK_IDS = 50


def ledger_path(agent: str = None) -> str:
    """该 agent 的留痕文件路径（与 recall.db 同目录）。"""
    return os.path.join(get_agent_dir(agent), LEDGER_FILENAME)


def _chunk_ids(results) -> list:
    """从召回结果里抽 chunk_id 去重保序（容忍缺字段/非 dict 元素）。"""
    ids = []
    for r in results or []:
        try:
            cid = r.get('chunk_id')
        except AttributeError:
            continue
        if isinstance(cid, int) and cid not in ids:
            ids.append(cid)
            if len(ids) >= MAX_CHUNK_IDS:
                break
    return ids


def append_entry(channel: str, query: str, results=None, agent: str = None,
                 extra: dict = None, now: datetime = None) -> bool:
    """追加一行留痕。**永不抛异常**：成功 True，任何失败 False。"""
    try:
        entry = {
            'ts': (now or datetime.now()).isoformat(timespec='seconds'),
            'agent': agent or os.environ.get('MIDNIGHT_AGENT') or DEFAULT_AGENT,
            'channel': str(channel),
            'query': '' if query is None else str(query),
            'hits': len(results or []),
            'chunk_ids': _chunk_ids(results),
            'extra': dict(extra or {}),
        }
        path = ledger_path(agent)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(entry, ensure_ascii=False) + '\n')
        return True
    except Exception:      # noqa: BLE001 — 旁路必须吞掉一切
        return False


def read_entries(agent: str = None, limit: int = DEFAULT_AUDIT_LIMIT) -> list[dict]:
    """读取留痕，返回**最后** limit 条（时间正序）。

    坏行（半行 JSON、被手改坏的行）跳过不抛——留痕是观测数据，不能因为一行坏了
    就让整个审计失败。`limit=None` 表示全部。
    """
    path = ledger_path(agent)
    if not os.path.exists(path):
        return []
    entries = []
    try:
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except (ValueError, TypeError):
                    continue
                if isinstance(obj, dict):
                    entries.append(obj)
    except OSError:
        return []
    if limit is not None and limit > 0:
        entries = entries[-limit:]
    return entries


def format_entries(entries: list[dict], agent: str = None) -> str:
    """把留痕格式化成一行人可读的审计文本。"""
    if not entries:
        return "[检索留痕] 暂无记录。"
    who = agent or os.environ.get('MIDNIGHT_AGENT') or DEFAULT_AGENT
    lines = [f"[检索留痕] agent={who} 最近 {len(entries)} 条："]
    for e in entries:
        ids = ','.join(str(i) for i in (e.get('chunk_ids') or []))
        lines.append(
            f"{e.get('ts', '?')}  channel={e.get('channel', '?')}  "
            f"hits={e.get('hits', 0)}  query={e.get('query', '')!r}"
            + (f"  ids={ids}" if ids else "")
        )
    return "\n".join(lines)
