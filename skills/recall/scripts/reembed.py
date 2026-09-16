"""NON-DESTRUCTIVE re-embedding for midnight-recall memory stores.

Upgrades existing (hash-pseudo) vectors to real semantic vectors **in place**
after wiring up a local ONNX / cloud embedding backend.

Safety contract (do NOT weaken):
  - Never deletes or re-creates any table, row, or the database.
  - Only UPDATEs the `vector` column of `chunks` and `tags`.
  - `content`, `tags`, `chunk_tags`, `tag_edges`, `tag_cooccurrence`,
    `files`, `importance`, `access_count` are all left untouched.
  - Idempotent: safe to re-run.

CLI:
  python reembed.py --agent qinglan                       # re-embed one agent
  python reembed.py --all                                 # re-embed every registered agent
  python reembed.py --db /path/to/recall.db               # arbitrary db
  # backend: set env MIDNIGHT_EMBEDDING=local + MIDNIGHT_MODEL_DIR=<dir>,
  #          or pass --backend local --model-dir <dir> / --key <key>
"""
import argparse
import os
import sqlite3
import struct
import sys

_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _SCRIPTS_DIR)
sys.path.insert(0, os.path.dirname(_SCRIPTS_DIR))   # 让 from scripts.xxx 可用

from embedding import load_embedding_client  # noqa: E402
from scripts.config import get_db_path, list_agents, DEFAULT_AGENT  # noqa: E402

_BATCH = 64


def _serialize_vector(vec) -> bytes:
    return struct.pack(f'{len(vec)}f', *vec)


def reembed_db(db_path: str, client) -> dict:
    """Re-embed chunks.vector and tags.vector in place. Returns counts."""
    if not os.path.exists(db_path):
        return {'chunks': 0, 'tags': 0, 'error': 'db not found'}

    conn = sqlite3.connect(db_path)
    conn.execute('PRAGMA journal_mode=WAL')
    try:
        # Count before touching anything.
        n_chunks = conn.execute('SELECT COUNT(*) FROM chunks').fetchone()[0]
        n_tags = conn.execute('SELECT COUNT(*) FROM tags').fetchone()[0]

        # chunks
        rows = conn.execute('SELECT id, content FROM chunks').fetchall()
        for i in range(0, len(rows), _BATCH):
            group = rows[i:i + _BATCH]
            texts = [ (r[1] or '') for r in group ]
            vecs = client.embed(texts)
            for (cid, _), vec in zip(group, vecs):
                conn.execute('UPDATE chunks SET vector = ? WHERE id = ?',
                             (_serialize_vector(vec), cid))

        # tags
        trows = conn.execute('SELECT id, name FROM tags').fetchall()
        for i in range(0, len(trows), _BATCH):
            group = trows[i:i + _BATCH]
            vecs = client.embed([(r[1] or '') for r in group])
            for (tid, _), vec in zip(group, vecs):
                conn.execute('UPDATE tags SET vector = ? WHERE id = ?',
                             (_serialize_vector(vec), tid))

        conn.commit()
        return {'chunks': n_chunks, 'tags': n_tags}
    finally:
        conn.close()


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description='Non-destructive vector re-embedding.')
    p.add_argument('--agent', default=os.environ.get('MIDNIGHT_AGENT') or DEFAULT_AGENT,
                   help='agent to re-embed (default: default)')
    p.add_argument('--all', action='store_true', help='re-embed all registered agents')
    p.add_argument('--db', help='explicit db path (overrides --agent)')
    p.add_argument('--backend', help='local|onnx|api|fake (default: env MIDNIGHT_EMBEDDING)')
    p.add_argument('--model-dir', help='dir with model.onnx + tokenizer.json (for local)')
    p.add_argument('--key', default=os.environ.get('SILICONFLOW_API_KEY', ''),
                   help='SiliconFlow API key (for api backend)')
    args = p.parse_args(argv)

    config = {}
    if args.backend:
        config['backend'] = args.backend
    if args.model_dir:
        config['model_dir'] = args.model_dir
    if args.key:
        config['api_key'] = args.key
    config.setdefault('dimension', 1024)

    client = load_embedding_client(config)

    if args.db:
        db_paths = [args.db]
    elif args.all:
        agents = list_agents()
        db_paths = [get_db_path(a['name']) for a in agents]
        if not db_paths:
            print('No registered agents found; nothing to do.')
            return 0
    else:
        db_paths = [get_db_path(args.agent)]

    # Back up nothing yet; we only UPDATE the vector column (non-destructive).
    for db_path in db_paths:
        res = reembed_db(db_path, client)
        if 'error' in res:
            print(f'[skip] {db_path}: {res["error"]}')
            continue
        print(f'[done] {db_path}: '
              f're-embedded {res["chunks"]} chunks + {res["tags"]} tags')
    return 0


if __name__ == '__main__':
    sys.exit(main())