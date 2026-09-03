"""Recall — vector similarity search for midnight-recall memory store.

CLI: python recall.py --query "..." [--k 10] [--db PATH] [--key KEY]
"""
import os
import sys
import sqlite3
import struct
from typing import Optional

_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _SCRIPTS_DIR)                      # 让 from embedding 可用
sys.path.insert(0, os.path.dirname(_SCRIPTS_DIR))     # 让 from scripts.xxx 可用
from embedding import load_embedding_client  # noqa: E402
from scripts.config import (  # noqa: E402
    get_db_path, list_agents, DEFAULT_AGENT, ensure_agent,
)

# 词面锚定阈值：非 default agent 需与查询共享 ≥ 该数量的汉字才算"可信候选"，
# 防止泛化/情绪化查询（无领域词）被 embedding 相似度误导而路由到某个私人 agent。
ROUTE_ANCHOR_MIN_SHARED = 2


def _agent_chars(agent: dict) -> set:
    """Agent 的领域字符集：description + keywords 去空格后的字符集合。"""
    text = agent.get('description') or ''
    text += ' ' + ' '.join(agent.get('keywords') or [])
    return {c for c in text if not c.isspace()}


def _deserialize_vector(blob: bytes) -> Optional[list[float]]:
    """Deserialize BLOB back to float list."""
    if blob is None:
        return None
    return list(struct.unpack(f'{len(blob) // 4}f', blob))


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def recall(query: str, db_path: str, embedding_client, k: int = 10) -> list[dict]:
    """Vector similarity search. Returns list of {chunk_id, content, date, score, file_path, importance}."""
    # Ensure schema exists (open+close so Windows doesn't hold the file lock)
    from scripts.schema import init_db
    _init = init_db(db_path)
    _init.close()

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        count = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        if count == 0:
            return []

        query_vec = embedding_client.embed([query])[0]

        rows = conn.execute("""
            SELECT c.id, c.content, c.file_id, COALESCE(f.diary_date, f.created_at) AS date,
                   f.file_path, c.importance, c.access_count
            FROM chunks c
            JOIN files f ON c.file_id = f.id
        """).fetchall()

        vec_rows = conn.execute("SELECT id, vector FROM chunks WHERE vector IS NOT NULL").fetchall()
        vec_map = {row['id']: _deserialize_vector(row['vector']) for row in vec_rows}

        scored = []
        for row in rows:
            vec = vec_map.get(row['id'])
            if vec is None:
                continue
            score = cosine_similarity(query_vec, vec)
            scored.append({
                'chunk_id': row['id'],
                'content': row['content'],
                'date': row['date'][:10] if row['date'] else '',
                'file_path': row['file_path'],
                'score': score,
                'importance': row['importance'] or 'medium',
                'access_count': row['access_count'] or 0,
            })

        # Importance boost: high=1.5x, medium=1.0x, low=0.5x
        boost = {'high': 1.5, 'medium': 1.0, 'low': 0.5}
        for r in scored:
            r['score'] *= boost.get(r['importance'], 1.0)

        scored.sort(key=lambda x: x['score'], reverse=True)
        return scored[:k]
    finally:
        conn.close()


def recall_by_identity(query: str, embedding_client, identity: str,
                       k: int = 10, tag_weight: float = 0.3,
                       time_ratio: float = 0.2, truncate: float = 1.0) -> list[dict]:
    """Identity-preferred recall: 上层会话显式声明了「我是谁」就查谁的记忆区。

    与 auto_recall 的关键差异：auto_recall 靠"查询文本 vs agent 描述"的语义相似度
    去 *猜* 该查哪个库；本函数把身份当作确定性事实——身份指向的 agent 就是目标库，
    不做任何猜库、不跨区。query 只在目标 agent 的库内做向量+标签脉冲召回。

    隔离墙由此保持：青岚会话传 identity=qinglan 就永远查 qinglan 区，
    mira 会话传 identity=mira 就永远查 mira 区，auto 的语义猜库不会再戳破分区。
    """
    if not identity:
        return []
    db_path = get_db_path(identity)
    if not os.path.exists(db_path):
        return []
    results = recall_associative(query, db_path, embedding_client,
                                 k=k, tag_weight=tag_weight,
                                 time_ratio=time_ratio, truncate=truncate)
    return results


def auto_recall(query: str, embedding_client, k: int = 10,
                tag_weight: float = 0.3, time_ratio: float = 0.2,
                truncate: float = 1.0) -> dict:
    """Auto-route query to the best matching agent, then recall.

    Routing is anchored: a non-default agent must share ≥ ROUTE_ANCHOR_MIN_SHARED
    characters with the query (description + optional keywords) to be a trusted
    candidate. Generic / emotional queries without domain words therefore fall
    back to the `default` agent (the user's own memory) instead of a random
    niche agent — preventing cross-DB leakage of unrelated private memory.

    Returns {name, description, score, ambiguous, results}
    """
    agents = list_agents()
    if not agents:
        return {'name': None, 'description': None, 'score': 0,
                'ambiguous': True, 'results': []}

    query_vec = embedding_client.embed([query])[0]
    q_chars = {c for c in query if not c.isspace()}

    # Score each agent's description+keywords against the query + lexical anchor
    scored = []
    for agent in agents:
        route_text = agent['description']
        if agent.get('keywords'):
            route_text += ' ' + ' '.join(agent['keywords'])
        desc_vec = embedding_client.embed([route_text])[0]
        score = cosine_similarity(query_vec, desc_vec)
        anchor = len(q_chars & _agent_chars(agent))
        scored.append({**agent, 'score': score, 'anchor': anchor})

    # 可信候选：default 恒为兜底；非 default 需有词面锚定
    trusted = [a for a in scored
               if a['name'] == DEFAULT_AGENT or a['anchor'] >= ROUTE_ANCHOR_MIN_SHARED]
    if not trusted:
        # 无 default 也无锚定 agent → 不猜，返回空 + ambiguous
        return {'name': None, 'description': None, 'score': 0,
                'ambiguous': True, 'results': []}

    best = max(trusted, key=lambda a: (a['score'], a['anchor']))
    # ambiguous = 本次靠 default 兜底（没有任何非 default agent 被词面锚定）
    ambiguous = best['name'] == DEFAULT_AGENT and not any(
        a['name'] != DEFAULT_AGENT and a['anchor'] >= ROUTE_ANCHOR_MIN_SHARED
        for a in scored)

    # Run recall on the best agent's database
    db_path = get_db_path(best['name'])
    if not os.path.exists(db_path):
        return {**best, 'ambiguous': ambiguous, 'results': []}

    results = recall_associative(query, db_path, embedding_client,
                                 k=k, tag_weight=tag_weight,
                                 time_ratio=time_ratio, truncate=truncate)
    return {**best, 'ambiguous': ambiguous, 'results': results}


def format_recall_output(results: list[dict], max_chars: int = None) -> str:
    """Format recall results as a context-injectable text block.

    默认**保留完整 chunk，不硬截断**（语义优先：截断会在句子中间拦腰切断，破坏信息）。
    只当调用方显式传 `max_chars` 时才按字符截断（向后兼容的历史兜底）；
    上下文体积控制应走 `fit_to_budget` 的按预算收条，而不是靠截断单条。
    """
    if not results:
        return "[回忆] 暂无相关记忆。"

    lines = ["[回忆] 以下是相关记忆（来源于你的日记，按相关度排序）：\n"]
    for r in results:
        date_part = f"（{r['date']}）" if r['date'] else ""
        content = r['content']
        if max_chars is not None and len(content) > max_chars:
            content = content[:max_chars] + "…"
        lines.append(f"{date_part}{content}")
    return "\n\n".join(lines)


def dedupe_results(results: list[dict]) -> list[dict]:
    """注入前全局去重（对齐 VCP ResultDeduplicator 的硬去重）。

    只去"真冗余"，不去"有关联的不同记忆"：
      - 同一 chunk_id 只留一次（联想/标签命中会重复带出同一 chunk）；
      - 规范化正文（去掉空白）相同视为重复，保留相关度更高的那条；
      - 不同正文绝不删除——避免漏掉有效信息。
    顺序保持召回相关度降序。
    """
    if not results:
        return results
    seen_ids = set()
    seen_norm = set()
    out = []
    for r in results:
        cid = r.get('chunk_id')
        norm = ''.join((r.get('content') or '').split())
        if cid is not None and cid in seen_ids:
            continue
        if norm in seen_norm:
            continue
        if cid is not None:
            seen_ids.add(cid)
        seen_norm.add(norm)
        out.append(r)
    return out


def fit_to_budget(results: list[dict], budget_chars: int = None) -> list[dict]:
    """预算收敛：在有限上下文预算内按相关度取「完整」条目。

    - 该召回多少召回多少（recall_associative 内部不动，召回充足）；
    - 注入前按预算从高到低收条，预算内每条保留完整正文，**绝不拦腰截断**；
    - 对抗兜底：若最相关的一条单就超过预算，仍注入那一条（宁有一条完整，不返回空）。

    这使 token 有硬上限（不会随召回量爆掉），同时又不损语义。
    """
    if not results or budget_chars is None or budget_chars <= 0:
        return results
    fitted = []
    used = 0
    for r in results:
        length = len(r.get('content') or '')
        if not fitted:              # 至少注入相关度最高的一条（单条超预算也完整保留）
            fitted.append(r)
            used = length
            continue
        if used + length > budget_chars:
            break                   # 预算用尽即停，不再硬塞
        fitted.append(r)
        used += length
    return fitted


def _time_score(date_str: str) -> float:
    """Recency score: 7d→1.0, 30d→0.5, 90d→0.2, older→0.05."""
    if not date_str:
        return 0.0
    from datetime import datetime
    try:
        diary_date = datetime.strptime(date_str, '%Y-%m-%d')
        days_ago = (datetime.now() - diary_date).days
        if days_ago <= 7:
            return 1.0
        if days_ago <= 30:
            return 0.5
        if days_ago <= 90:
            return 0.2
        return 0.05
    except ValueError:
        return 0.0


def recall_associative(query: str, db_path: str, embedding_client,
                       k: int = 10, tag_weight: float = 0.3,
                       decay: float = 0.5, max_depth: int = 2,
                       threshold: float = 0.1, time_ratio: float = 0.0,
                       truncate: float = 1.0) -> list[dict]:
    """Associative recall: combine vector KNN results with tag pulse propagation
    and optional time weighting, truncation, and importance boosting.
    """
    from tag_network import activate_tags

    fetch_k = max(k, int(k / max(truncate, 0.01))) if truncate < 1.0 else k
    final_k = max(1, int(k * truncate)) if truncate < 1.0 else k
    vector_results = recall(query, db_path, embedding_client, k=fetch_k)
    if not vector_results:
        return []

    query_vec = embedding_client.embed([query])[0]
    activated = activate_tags(query_vec, db_path, embedding_client,
                              decay=decay, max_depth=max_depth, threshold=threshold)

    # 3. Combine scores
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        for r in vector_results:
            r['time_score'] = _time_score(r.get('date'))

        if not activated:
            # No tag boost, just vector + time
            for r in vector_results:
                r['score'] = r['score'] + time_ratio * r['time_score']
            vector_results.sort(key=lambda x: x['score'], reverse=True)
            return vector_results[:final_k]

        strength_map = {tid: s for tid, s in activated}
        seen = {r['chunk_id'] for r in vector_results}

        boosted = []
        for r in vector_results:
            tag_rows = conn.execute("""
                SELECT ct.tag_id FROM chunk_tags ct
                WHERE ct.chunk_id = ?
            """, (r['chunk_id'],)).fetchall()
            tag_strength = sum(strength_map.get(t['tag_id'], 0.0) for t in tag_rows)
            boosted.append({
                **r,
                'tag_strength': tag_strength,
                'score': r['score'] + tag_weight * tag_strength + time_ratio * r['time_score'],
            })

        # Deep association: chunks that carry an activated tag but fell outside the
        # vector top-k can still surface (e.g. 压力 → 紧张 → 雅思, lexically disjoint
        # from the query). Only pulled when tag boosting is active, and bounded.
        if tag_weight > 0:
            extra = []
            for tid, s in activated:
                if s <= 0:
                    continue
                for row in conn.execute(
                        "SELECT chunk_id FROM chunk_tags WHERE tag_id = ?", (tid,)).fetchall():
                    cid = row['chunk_id']
                    if cid in seen:
                        continue
                    seen.add(cid)
                    meta = conn.execute("""
                        SELECT c.id, c.content, c.file_id,
                               COALESCE(f.diary_date, f.created_at) AS date,
                               f.file_path, c.importance, c.access_count
                        FROM chunks c JOIN files f ON c.file_id = f.id
                        WHERE c.id = ?
                    """, (cid,)).fetchone()
                    if not meta:
                        continue
                    trows = conn.execute(
                        "SELECT tag_id FROM chunk_tags WHERE chunk_id = ?", (cid,)).fetchall()
                    tag_strength = sum(strength_map.get(t['tag_id'], 0.0) for t in trows)
                    if tag_strength <= 0:
                        continue
                    date_str = meta['date'][:10] if meta['date'] else ''
                    ts = _time_score(date_str)
                    extra.append({
                        'chunk_id': meta['id'],
                        'content': meta['content'],
                        'date': date_str,
                        'file_path': meta['file_path'],
                        'score': tag_weight * tag_strength + time_ratio * ts,
                        'importance': meta['importance'] or 'medium',
                        'access_count': meta['access_count'] or 0,
                        'tag_strength': tag_strength,
                        'time_score': ts,
                    })
            boosted.extend(extra)

        boosted.sort(key=lambda x: x['score'], reverse=True)
        return boosted[:final_k]
    finally:
        conn.close()


def main(argv=None) -> int:
    """CLI: python recall.py --query '...' [--auto] [--k N] [--agent NAME] [--db PATH] [--key KEY]"""
    argv = argv if argv is not None else sys.argv[1:]

    query = None
    k = 10
    agent = os.environ.get('MIDNIGHT_AGENT')
    auto = False
    register = None
    budget = None
    db_path = None
    api_key = os.environ.get('SILICONFLOW_API_KEY', '')

    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == '--query' and i + 1 < len(argv):
            query = argv[i + 1]
            i += 2
        elif arg == '--k' and i + 1 < len(argv):
            k = int(argv[i + 1])
            i += 2
        elif arg == '--auto':
            auto = True
            i += 1
        elif arg in ('--agent', '--identity') and i + 1 < len(argv):
            agent = argv[i + 1]
            i += 2
        elif arg == '--register' and i + 1 < len(argv):
            register = argv[i + 1]
            i += 2
        elif arg == '--budget' and i + 1 < len(argv):
            budget = int(argv[i + 1])
            i += 2
        elif arg == '--db' and i + 1 < len(argv):
            db_path = argv[i + 1]
            i += 2
        elif arg == '--key' and i + 1 < len(argv):
            api_key = argv[i + 1]
            i += 2
        else:
            print(f"Unknown option: {arg}", file=sys.stderr)
            return 2

    # --register：只开户、立身份，不召回（无需 query 也可用）
    if register:
        if not agent:
            print("Usage: --register '<描述>' 需要配合 --identity <名字>", file=sys.stderr)
            return 1
        ensure_agent(agent, description=register)
        print(f"[开户] 已为智能体「{agent}」建立记忆区并登记身份。")
        return 0

    if not query:
        print("Usage: recall.py --query '...' [--auto] [--k N] [--agent NAME] [--db PATH] [--key KEY] [--budget N]", file=sys.stderr)
        return 1

    config = {'api_key': api_key, 'dimension': 1024}
    client = load_embedding_client(config)

    # 身份优先：上层显式声明了 --agent/--identity 就查该智能体区，--auto 不得覆盖。
    # （身份是确定事实，auto 猜库只在身份缺失时才兜底，避免戳破记忆隔离墙。）
    if agent:
        # 声明身份即开户：即使该区还没写过日记，也已立身份、在 list_agents 中可见
        ensure_agent(agent)
        results = recall_by_identity(query, client, identity=agent, k=k)
        results = dedupe_results(fit_to_budget(results, budget))
        output = format_recall_output(results)
        print(output)
        return 0

    if auto:
        result = auto_recall(query, client, k=k)
        if result['name']:
            print(f"[自动路由] → 匹配到智能体「{result['name']}」({result['description']}, 相似度={result['score']:.3f})\n")
        results = dedupe_results(fit_to_budget(result['results'], budget))
        output = format_recall_output(results)
        print(output)
        return 0

    db_path = db_path or get_db_path(agent)
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    results = recall(query, db_path, client, k=k)
    results = dedupe_results(fit_to_budget(results, budget))
    output = format_recall_output(results)
    print(output)
    return 0


if __name__ == '__main__':
    sys.exit(main())