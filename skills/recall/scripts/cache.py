"""结果缓存（T4）：同一 (query, 参数, db) 在记忆未变时，短时高频直接命中。

- 代数失效：`cache_generation` 存于 meta 表，每次真实 ingest 递增。缓存条目
  携带写入时的代数；命中时若代数 != 当前代数即失效（记忆已变），避免脏读。
- 时间窗：TTL 内才命中；超窗视为过期重算（兜底，防长会话内陈旧印象霸屏）。
- 语义：缓存的是 `recall_associative` 的**最终注入列表**，读路径完全不变；
  只在 CLI/高频调用方显式开启（`cache=True`），引擎默认路径不动。
"""
import hashlib
import json
import os
import sqlite3
from datetime import datetime

_GENERATION_KEY = 'cache_generation'

# 默认缓存时间窗（秒）内单进程高频同查询直接命中。
CACHE_TTL_SECONDS = 300


def get_generation(conn: sqlite3.Connection) -> int:
    """当前缓存代数（0 表示从未 ingest）。"""
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (_GENERATION_KEY,)).fetchone()
    return int(row[0]) if row else 0


def bump_generation(conn: sqlite3.Connection) -> None:
    """真实 ingest 后使缓存整体失效：代数 +1，清空旧缓存条目。"""
    next_gen = get_generation(conn) + 1
    conn.execute(
        "INSERT INTO meta (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (_GENERATION_KEY, str(next_gen)))
    conn.execute("DELETE FROM recall_cache")


def _cache_key(db_path: str, **params) -> str:
    """查询参数 → 缓存键指纹。db_path 参与，避免跨库串扰。"""
    payload = json.dumps({'db': os.path.abspath(db_path), **params},
                         sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


def cache_get(db_path: str, key: str, ttl_seconds: int = CACHE_TTL_SECONDS):
    """命中且代数一致且未超窗 → 返回反序列化列表；否则 None。"""
    if not os.path.exists(db_path):
        return None
    conn = sqlite3.connect(db_path)
    try:
        current = get_generation(conn)
        row = conn.execute(
            "SELECT generation, result, ts FROM recall_cache WHERE key = ?",
            (key,)).fetchone()
        if not row:
            return None
        gen, result_json, ts = row
        if gen != current:
            return None
        try:
            written = datetime.fromisoformat(ts)
            age = (datetime.now() - written).total_seconds()
        except (ValueError, TypeError):
            return None
        if age > ttl_seconds:
            return None
        return json.loads(result_json)
    finally:
        conn.close()


def cache_set(db_path: str, key: str, results: list) -> None:
    """写入本代缓存。失败静默（缓存是优化，绝不让缓存错误影响召回）。"""
    try:
        conn = sqlite3.connect(db_path)
        try:
            gen = get_generation(conn)
            now = datetime.now().isoformat(timespec='seconds')
            conn.execute(
                "INSERT INTO recall_cache (key, generation, result, ts) "
                "VALUES (?, ?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET generation = excluded.generation, "
                "result = excluded.result, ts = excluded.ts",
                (key, gen, json.dumps(results, ensure_ascii=False), now))
            conn.commit()
        finally:
            conn.close()
    except Exception:
        pass