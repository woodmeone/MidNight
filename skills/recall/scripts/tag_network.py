"""Tag network — co-occurrence matrix and pulse propagation for midnight-recall.

This is the associative memory engine: when a query activates certain tags,
the pulse spreads along the co-occurrence network so that *associated* content
surfaces without the user mentioning the exact keyword.

Algorithm (simplified from the associative-memory design, original implementation):
- Activate tags whose vector/similarity matches the query.
- BFS spread: each hop decays pulse strength by `decay`.
- Any tag receiving strength >= `threshold` joins the activated set.
- Return activated tags with their cumulative strength.
"""
import os
import sys
import sqlite3

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scripts.config import get_db_path  # noqa: E402


def activate_tags(query_vec, db_path: str, embedding_client,
                  decay: float = 0.5, max_depth: int = 2, threshold: float = 0.1,
                  initial_hits: int = 5) -> list[tuple[int, float]]:
    """Pulse-propagate activation from seed tags to their co-occurrence neighbours.

    Returns list of (tag_id, cumulative_strength) sorted desc, including seed tags.
    """
    conn = sqlite3.connect(db_path)
    try:
        # 1. Find seed tags: tags whose vector is most similar to query
        rows = conn.execute("SELECT id, name, vector FROM tags WHERE vector IS NOT NULL").fetchall()
        if not rows:
            return []

        seed_scores = []
        for row in rows:
            vec = _deserialize(row['vector']) if isinstance(row, sqlite3.Row) else _deserialize(row[2])
            score = _cosine(query_vec, vec) if vec else 0.0
            seed_scores.append((row['id'] if isinstance(row, sqlite3.Row) else row[0], score))
        seed_scores.sort(key=lambda x: x[1], reverse=True)
        seed_tags = [tid for tid, s in seed_scores[:initial_hits] if s > 0]

        if not seed_tags:
            return []

        # 2. BFS pulse propagation
        strength = {tid: 1.0 for tid in seed_tags}
        current_frontier = list(seed_tags)
        for depth in range(1, max_depth + 1):
            next_frontier = []
            for tid in current_frontier:
                edges = conn.execute(
                    "SELECT tag1_id, tag2_id, weight FROM tag_cooccurrence WHERE tag1_id = ? OR tag2_id = ?",
                    (tid, tid)
                ).fetchall()
                for e in edges:
                    t1, t2, w = e[0], e[1], e[2] if not isinstance(e, sqlite3.Row) else (e['tag1_id'], e['tag2_id'], e['weight'])
                    neighbor = t2 if t1 == tid else t1
                    pulsed = strength.get(tid, 0.0) * decay * min(w, 5.0) / 5.0
                    if neighbor not in strength or pulsed > strength[neighbor]:
                        strength[neighbor] = pulsed
                        next_frontier.append(neighbor)
            # prune below threshold
            current_frontier = [t for t in set(next_frontier) if strength.get(t, 0.0) >= threshold]
            if not current_frontier:
                break

        # 3. Filter threshold, sort by strength
        result = [(tid, s) for tid, s in strength.items() if s >= threshold and s > 0]
        result.sort(key=lambda x: x[1], reverse=True)
        return result
    finally:
        conn.close()


def tags_for_activated(activated: list[tuple[int, float]], db_path: str) -> list[dict]:
    """Resolve activated tag ids to {id, name, strength}."""
    if not activated:
        return []
    conn = sqlite3.connect(db_path)
    try:
        result = []
        for tid, strength in activated:
            row = conn.execute("SELECT id, name FROM tags WHERE id = ?", (tid,)).fetchone()
            if row:
                result.append({'id': row[0], 'name': row[1], 'strength': strength})
        return result
    finally:
        conn.close()


def _deserialize(blob) -> list[float]:
    import struct
    if blob is None:
        return []
    return list(struct.unpack(f'{len(blob) // 4}f', blob))


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)