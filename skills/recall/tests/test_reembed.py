"""Non-destructive re-embedding tests.

Proves reembed_db only rewrites the `vector` column of chunks/tags and leaves
every other memory field (content, tags, links, co-occurrence, edges, files,
importance, access_count) byte-for-byte untouched.
"""
import sqlite3
import tempfile
import os

from scripts.ingest import ingest_file
from scripts.embedding import FakeEmbeddingClient
from scripts.reembed import reembed_db

DIARY = """---
maid: Nova
created: 2026-08-20T14:30:00
tags: [考试, 压力]
---
今天聊到下周要面试，有点紧张。准备了三天，但觉得不够充分。
"""
OTHER = """---
maid: Nova
created: 2026-08-21T10:00:00
tags: [面试]
---
昨天一起复习了考试资料，感觉状态不错。
"""


class _FixedVecClient:
    """Embed that returns a deterministic non-hash vector, to prove rewriting."""
    def __init__(self, dims=4):
        self.dims = dims

    def embed(self, texts):
        return [[0.5] * self.dims for _ in texts]


OTHER_TABLES = ('chunks', 'tags', 'chunk_tags', 'tag_edges', 'tag_cooccurrence', 'files')


def _table_rows(db, table):
    conn = sqlite3.connect(db)
    cols = [r[1] for r in conn.execute(f'PRAGMA table_info({table})').fetchall()
            if r[1] != 'vector']  # exclude mutable vector; memory fields only
    sel = ', '.join(f'"{c}"' for c in cols)
    rows = conn.execute(f'SELECT {sel} FROM {table}').fetchall()
    conn.close()
    return cols, rows


def _vector_blobs(db, table):
    conn = sqlite3.connect(db)
    blobs = conn.execute(f'SELECT rowid, vector FROM {table} WHERE vector IS NOT NULL').fetchall()
    conn.close()
    return blobs


def test_reembed_is_non_destructive(tmp_path):
    db_path = os.path.join(str(tmp_path), 'recall.db')

    with tempfile.NamedTemporaryFile('w', suffix='.md', delete=False, encoding='utf-8') as f:
        f.write(DIARY); p1 = f.name
    with tempfile.NamedTemporaryFile('w', suffix='.md', delete=False, encoding='utf-8') as f:
        f.write(OTHER); p2 = f.name
    try:
        emb = FakeEmbeddingClient(dimension=4)
        r1 = ingest_file(p1, db_path, emb)
        r2 = ingest_file(p2, db_path, emb)
        assert r1['status'] == 'ingested' and r2['status'] == 'ingested'

        before = {t: _table_rows(db_path, t) for t in OTHER_TABLES}
        vec_before_chunks = _vector_blobs(db_path, 'chunks')
        vec_before_tags = _vector_blobs(db_path, 'tags')
        assert vec_before_chunks, 'expected some chunk vectors'

        res = reembed_db(db_path, _FixedVecClient(4))
        assert res['chunks'] == len(before['chunks'][1])
        assert res['tags'] == len(before['tags'][1])

        after = {t: _table_rows(db_path, t) for t in OTHER_TABLES}

        # Memory fields (rows in every table) unchanged.
        for t in OTHER_TABLES:
            assert after[t] == before[t], f'{t} was mutated by reembed'

        # Vectors actually rewritten: blob bytes differ for every chunk/tag.
        vec_after_chunks = {rid: b for rid, b in _vector_blobs(db_path, 'chunks')}
        for rid, b in vec_before_chunks:
            assert vec_after_chunks.get(rid) != b, f'chunk {rid} vector not rewritten'
        vec_after_tags = {rid: b for rid, b in _vector_blobs(db_path, 'tags')}
        for rid, b in vec_before_tags:
            assert vec_after_tags.get(rid) != b, f'tag {rid} vector not rewritten'
    finally:
        os.unlink(p1); os.unlink(p2)