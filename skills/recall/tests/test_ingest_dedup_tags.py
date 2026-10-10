"""对抗式回归：重复标签不得让 ingest 崩。

2026-10-09 harvest 回填炸出的既有 bug：日记 tags 含重复项时，
共现矩阵插入 (t1, t2) 出现 t1==t2，触发 CHECK(tag1_id < tag2_id)，
整篇入库失败。手写日记写重复标签同样会崩，与 harvest 无关。
"""
import os

from scripts.embedding import FakeEmbeddingClient
from scripts.schema import init_db
from scripts.ingest import ingest_file


def test_duplicate_tags_do_not_crash_ingest(tmp_path):
    db = str(tmp_path / "r.db")
    init_db(db)
    fp = tmp_path / "d.md"
    fp.write_text(
        "---\nmaid: t\ncreated: 2026-09-09T10:00:00\n"
        "tags: [md, AgentThought, md, 设计]\n---\n正文内容一条。\n",
        encoding="utf-8")
    r = ingest_file(str(fp), db, FakeEmbeddingClient(dimension=16))
    assert r["status"] == "ingested"


def test_duplicate_tags_cooccurrence_pairs_valid(tmp_path):
    """去重后共现边必须满足 tag1_id < tag2_id（schema CHECK 的语义）。"""
    import sqlite3
    db = str(tmp_path / "r.db")
    init_db(db)
    fp = tmp_path / "d.md"
    fp.write_text(
        "---\nmaid: t\ncreated: 2026-09-09T10:00:00\n"
        "tags: [a1tag, b2tag, a1tag]\n---\n正文。\n",
        encoding="utf-8")
    ingest_file(str(fp), db, FakeEmbeddingClient(dimension=16))
    conn = sqlite3.connect(db)
    rows = conn.execute("SELECT tag1_id, tag2_id FROM tag_cooccurrence").fetchall()
    assert rows, "共现边应存在"
    assert all(t1 < t2 for t1, t2 in rows)
    conn.close()
