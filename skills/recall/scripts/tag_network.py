"""Tag network — ordered directed edges and budget-conserving pulse propagation.

This is the associative memory engine (V2, aligned with VCP TagMemo V9.1):
when a query activates certain tags, the pulse spreads along *directed*,
*log-compressed*, *hub-corrected* edges so that associated content surfaces
without the user mentioning the exact keyword — and without high-frequency
hub words (e.g. "考试") monopolising the spread.

Design (locked in docs/OPTIMIZATION-SPEC.md §A):
1. Ordered bidirectional edges: tags in the same file get directed edges
   (顺流 forward = earlier→later, 逆流 reverse = later→earlier). Weight is
   accumulated raw evidence W (see ingest.py), contribution =
   order potential · exp(-position distance / λ) · direction damping.
2. Cumulative evidence compression: effective edge weight e = log(1 + λ·W).
   Keeps high-frequency tags from dominating linearly.
3. In-flow hub correction: the gain of an edge *into* a node is power-law
   scaled down by that node's total in-flow — generic hub words are suppressed.
4. Budget-conserving propagation: each node's total out-flow is capped at
   strength·decay, split among neighbours by effective edge share. Pulse
   energy only decays per hop, never multiplies without bound.
5. Core/Ghost tag pre-sensing: the query is embedded and compared against
   *all* tags (not one seed); top candidates become Core tags (full strength),
   a few weak-but-positive ones become Ghost tags (small strength) so deep
   associations can join if reinforced.

The `recall_associative` interface in recall.py is unchanged.
"""
import math
import os
import sys
import sqlite3

_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _SCRIPTS_DIR)                      # 让 from config 可用
sys.path.insert(0, os.path.dirname(_SCRIPTS_DIR))     # 让 from scripts.xxx 可用
from scripts.config import get_db_path  # noqa: E402

# --- VCP TagMemo association constants ---
DISTANCE_LAMBDA = 3.0        # position-distance decay length in a file's tag list
FORWARD_DAMP = 1.0           # 顺流 direction damping
REVERSE_DAMP = 0.4           # 逆流 direction damping
MAX_REVERSE_RATIO = 0.6      # guard: reverse/forward damping ratio ceiling
LOG_LAMBDA = 1.0             # cumulative evidence log compression: e = log(1 + λ·W)
HUB_K = 0.05                 # hub correction gain
HUB_POWER = 1.0              # hub correction power-law exponent
GHOST_STRENGTH = 0.3         # ghost tag pre-sensed activation
GHOST_BUDGET = 5             # how many ghost candidates to pre-sense
CORE_RATIO = 0.25            # core seed must be ≥ this fraction of best-match similarity
GHOST_RATIO = 0.05           # ghost candidate must be ≥ this fraction of best-match similarity


def _edge_contribution(pos_a: int, pos_b: int) -> float:
    """Per-file forward edge contribution: order potential × distance decay.

    Tags listed earlier in a file's frontmatter are treated as more salient
    (order potential = 1/(1 + min position)); far-apart tags decay with the
    position distance. This is the geometric part of the weight; the caller
    multiplies in direction damping.
    """
    distance = abs(pos_a - pos_b)
    if distance == 0:
        return 0.0
    potential = 1.0 / (1 + min(pos_a, pos_b))
    return potential * math.exp(-distance / DISTANCE_LAMBDA)


def _compressed_weight(raw: float) -> float:
    """Cumulative evidence compression: e = log(1 + λ·W)."""
    return math.log1p(LOG_LAMBDA * max(raw, 0.0))


def _hub_scale(hub_inflow: float) -> float:
    """In-flow hub correction: power-law shrink of edge gain into a hub node."""
    return (1.0 + HUB_K * (hub_inflow ** HUB_POWER)) ** -1.0


def activate_tags(query_vec, db_path: str, embedding_client,
                  decay: float = 0.5, max_depth: int = 2, threshold: float = 0.1,
                  initial_hits: int = 5) -> list[tuple[int, float]]:
    """Pulse-propagate activation from pre-sensed seed tags along directed edges.

    Returns list of (tag_id, cumulative_strength) sorted desc, including
    core/ghost seeds and every tag reached above `threshold`.
    """
    conn = sqlite3.connect(db_path)
    try:
        # 1. Pre-sense Core + Ghost tags by embedding similarity (not one seed).
        rows = conn.execute("SELECT id, name, vector FROM tags WHERE vector IS NOT NULL").fetchall()
        if not rows:
            return []

        seed_scores = []
        for row in rows:
            vec = _deserialize(row[2])
            score = _cosine(query_vec, vec) if vec else 0.0
            seed_scores.append((row[0], score))
        seed_scores.sort(key=lambda x: x[1], reverse=True)
        top_score = seed_scores[0][1] if seed_scores else 0.0
        if top_score <= 0:
            return []

        # Core = meaningfully similar tags (relative to best match), not just >0,
        # so embedding-hash collision noise can't become full-strength seeds.
        core_floor = top_score * CORE_RATIO
        ghost_floor = top_score * GHOST_RATIO
        core = [tid for tid, s in seed_scores if s >= core_floor][:initial_hits]
        ghosts = [
            tid for tid, s in seed_scores
            if ghost_floor <= s < core_floor
        ][:GHOST_BUDGET]

        if not core:
            return []

        # 2. Pre-compute hub in-flow (raw evidence) for hub correction.
        hub_inflow: dict[int, float] = {}
        for from_id, to_id, w in conn.execute(
            "SELECT tag_from_id, tag_to_id, weight FROM tag_edges"
        ).fetchall():
            hub_inflow[to_id] = hub_inflow.get(to_id, 0.0) + w

        def _out_edges(tid: int) -> list[tuple[int, float]]:
            """Effective outgoing edges: log-compressed and hub-corrected."""
            out = []
            for to_id, w in conn.execute(
                "SELECT tag_to_id, weight FROM tag_edges WHERE tag_from_id = ?",
                (tid,)
            ).fetchall():
                if to_id == tid:
                    continue
                eff = _compressed_weight(w) * _hub_scale(hub_inflow.get(to_id, 0.0))
                if eff > 0:
                    out.append((to_id, eff))
            return out

        # 3. Budget-conserving pulse propagation.
        strength: dict[int, float] = {}
        for tid in core:
            strength[tid] = strength.get(tid, 0.0) + 1.0
        for tid in ghosts:
            strength[tid] = strength.get(tid, 0.0) + GHOST_STRENGTH
        frontier = [(tid, strength[tid]) for tid in core + ghosts]

        for _depth in range(1, max_depth + 1):
            received: dict[int, float] = {}
            for tid, s in frontier:
                edges = _out_edges(tid)
                total_w = sum(w for _, w in edges)
                if total_w <= 0 or s <= 0:
                    continue
                budget = s * decay  # fixed outflow budget: no unbounded fan-out
                for to_id, eff in edges:
                    pulse = budget * eff / total_w
                    if pulse > 0:
                        received[to_id] = received.get(to_id, 0.0) + pulse
            frontier = []
            for to_id, pulse in received.items():
                strength[to_id] = strength.get(to_id, 0.0) + pulse
                if strength[to_id] >= threshold:
                    frontier.append((to_id, strength[to_id]))
            if not frontier:
                break

        # 4. Filter threshold, sort by strength.
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
