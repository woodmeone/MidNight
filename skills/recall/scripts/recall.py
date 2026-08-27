"""Recall — vector similarity search for midnight-recall memory store.

CLI: python recall.py --query "..." [--k 10] [--db PATH] [--key KEY]
"""
import os
import sys
import sqlite3
import struct
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from embedding import load_embedding_client  # noqa: E402
from scripts.config import get_db_path, list_agents  # noqa: E402


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


def auto_recall(query: str, embedding_client, k: int = 10,
                tag_weight: float = 0.3, time_ratio: float = 0.2,
                truncate: float = 1.0) -> dict:
    """Auto-route query to the best matching agent, then recall.

    Scans all agents, semantically matches query to each agent's description,
    picks the best match, and runs recall_associative on that agent's database.

    Returns {agent, description, score, results}
    """
    agents = list_agents()
    if not agents:
        return {'name': None, 'description': None, 'score': 0, 'results': []}

    query_vec = embedding_client.embed([query])[0]

    # Score each agent's description against the query
    scored = []
    for agent in agents:
        desc_vec = embedding_client.embed([agent['description']])[0]
        score = cosine_similarity(query_vec, desc_vec)
        scored.append({**agent, 'score': score})

    scored.sort(key=lambda x: x['score'], reverse=True)
    best = scored[0]

    # Run recall on the best agent's database
    db_path = get_db_path(best['name'])
    if not os.path.exists(db_path):
        return {**best, 'results': []}

    results = recall_associative(query, db_path, embedding_client,
                                 k=k, tag_weight=tag_weight,
                                 time_ratio=time_ratio, truncate=truncate)
    return {**best, 'results': results}


def format_recall_output(results: list[dict], max_chars: int = 200) -> str:
    """Format recall results as a context-injectable text block."""
    if not results:
        return "[回忆] 暂无相关记忆。"

    lines = ["[回忆] 以下是相关记忆（来源于你的日记，按相关度排序）：\n"]
    for r in results:
        date_part = f"（{r['date']}）" if r['date'] else ""
        content = r['content']
        if len(content) > max_chars:
            content = content[:max_chars] + "…"
        lines.append(f"{date_part}{content}")
    return "\n\n".join(lines)


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

    # 3. Compute time scores
    from datetime import datetime, timedelta
    now = datetime.now()
    for r in vector_results:
        r['time_score'] = 0.0
        if r.get('date'):
            try:
                diary_date = datetime.strptime(r['date'], '%Y-%m-%d')
                days_ago = (now - diary_date).days
                if days_ago <= 7:
                    r['time_score'] = 1.0
                elif days_ago <= 30:
                    r['time_score'] = 0.5
                elif days_ago <= 90:
                    r['time_score'] = 0.2
                else:
                    r['time_score'] = 0.05
            except ValueError:
                pass

    # 4. Combine scores
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        if not activated:
            # No tag boost, just vector + time
            for r in vector_results:
                r['score'] = r['score'] + time_ratio * r['time_score']
            vector_results.sort(key=lambda x: x['score'], reverse=True)
            return vector_results[:final_k]

        activated_ids = [tid for tid, _ in activated]
        strength_map = {tid: s for tid, s in activated}

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
        elif arg == '--agent' and i + 1 < len(argv):
            agent = argv[i + 1]
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

    if not query:
        print("Usage: recall.py --query '...' [--auto] [--k N] [--agent NAME] [--db PATH] [--key KEY]", file=sys.stderr)
        return 1

    config = {'api_key': api_key, 'dimension': 1024}
    client = load_embedding_client(config)

    if auto:
        result = auto_recall(query, client, k=k)
        if result['name']:
            print(f"[自动路由] → 匹配到智能体「{result['name']}」({result['description']}, 相似度={result['score']:.3f})\n")
        output = format_recall_output(result['results'])
        print(output)
        return 0

    db_path = db_path or get_db_path(agent)
    results = recall(query, db_path, client, k=k)
    output = format_recall_output(results)
    print(output)
    return 0


if __name__ == '__main__':
    sys.exit(main())