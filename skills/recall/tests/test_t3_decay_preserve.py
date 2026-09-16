"""T3 · 记忆保鲜：弱关联/久未用条目自动降权（不删除正文）。

验收口径（.scratch/associative-optimization/issues/T3-decay-preserve.md）：
- 久未用关联权重自动淡出：同一起点 tag 下，被衰减的旧边目标在召回排序中
  **显著下沉**；但没有被删除——仍被激活、仍能被召回。
- 正文永久保留：手动按 file_path 仍可完整取回原 chunk（chunks 表绝不因衰减改动）。
- 非破坏铁律：衰减/钳制后关联边数量不变（不 DELETE）。
"""
import os
import tempfile
import sqlite3
import struct

from scripts.schema import init_db
from scripts.embedding import SemanticFakeEmbeddingClient
from scripts.ingest import ingest_file
from scripts.evolution import decay_stale_edges
from scripts.tag_network import activate_tags, tags_for_activated

import pytest


@pytest.fixture
def embed():
    return SemanticFakeEmbeddingClient()


class _ExactSemanticFake(SemanticFakeEmbeddingClient):
    """无哈希碰撞的精确 token 袋嵌入：不相交文本的余弦相似度精确≈0。

    用于排除 SemanticFake(256 维) 的哈希碰撞对激活强度的影响，使
    "衰减前两目标持平、衰减后旧链下沉"的序关系可被精确断言。
    """
    FEATURE_DIM = 200000


def _pack(vec):
    return struct.pack(f'{len(vec)}f', *vec)


def _write(db_path, embed, tags, content, idx):
    """Ingest one diary so chunk + tag vectors are created by the real pipeline."""
    fd, path = tempfile.mkstemp(suffix='.md')
    os.close(fd)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(f"---\nmaid: qinglan\ncreated: 2026-08-{1 + idx % 28:02d}T10:00:00\n"
                f"tags: [{tags}]\n---\n{content}\n")
    ingest_file(path, db_path, embed)
    os.unlink(path)


def test_decay_sinks_stale_target_but_keeps_it_activated():
    """同一起点 tag，旧边目标在衰减后激活强度显著低于新鲜边目标，但仍在激活集合。"""
    embed = _ExactSemanticFake()
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        db = os.path.join(tmpdir, 'recall.db')
        init_db(db)
        conn = sqlite3.connect(db)
        try:
            # 种子“起源”被查询激活为 core；两个目标词面与查询完全无重叠，只经边脉冲可达。
            for name in ('起源', '甲乙', '丙丁'):
                conn.execute("INSERT INTO tags (name, vector) VALUES (?, ?)",
                             (name, _pack(embed.embed([name])[0])))
            ids = {}
            for row in conn.execute("SELECT id, name FROM tags").fetchall():
                ids[row[1]] = row[0]
            conn.execute(  # 新鲜边：丙丁(now)
                "INSERT INTO tag_edges (tag_from_id, tag_to_id, weight, updated_at) "
                "VALUES (?, ?, 1.0, datetime('now'))", (ids['起源'], ids['丙丁']))
            conn.execute(  # 久未用弱边：甲乙(-300 天)
                "INSERT INTO tag_edges (tag_from_id, tag_to_id, weight, updated_at) "
                "VALUES (?, ?, 1.0, datetime('now', '-300 days'))", (ids['起源'], ids['甲乙']))
            conn.commit()

            qv = embed.embed(["起源"])[0]
            before = {t['name']: t['strength']
                      for t in tags_for_activated(activate_tags(
                          qv, db, embed, max_depth=1, threshold=0.0), db)}

            # 非破坏衰减：旧边 weight 1.0 → 0.5，新边保持 1.0
            r = decay_stale_edges(db, stale_days=90, factor=0.5, floor=0.05)
            assert r['decayed'] == 1

            after = {t['name']: t['strength']
                     for t in tags_for_activated(activate_tags(
                         qv, db, embed, max_depth=1, threshold=0.0), db)}

            # 衰减发生前同权边 → 两目标激活应基本持平（精确嵌入下）
            assert abs(before['甲乙'] - before['丙丁']) < 1e-6
            # 衰减后：甲乙（旧）显著下沉、弱于丙丁（新）……
            assert after['丙丁'] > after['甲乙'], "久未用旧边目标应显著沉底"
            # ……但未被删除：仍被激活、仍可被召回。
            assert '甲乙' in after and after['甲乙'] > 0, "旧边目标应保留、仍激活"
        finally:
            conn.close()


def test_decay_preserves_body_retrievable_by_file(embed):
    """衰减后正文完整可查：按 file_path 可翻到原文 chunk（chunks 表不受影响）。"""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        db = os.path.join(tmpdir, 'recall.db')
        init_db(db)
        _write(db, embed, "班风 早读", "这周早读整体还行，个别走神。", 1)
        _write(db, embed, "班风 迟到", "连续三天有学生迟到，需要盯。", 2)

        conn = sqlite3.connect(db)
        # 把“班风→迟到”这条关联改成久未用弱边，其余不动
        conn.execute(
            "UPDATE tag_edges SET weight = 0.01, updated_at = datetime('now', '-300 days') "
            "WHERE tag_to_id = (SELECT id FROM tags WHERE name = '迟到')")
        conn.commit()
        conn.close()

        decay_stale_edges(db, stale_days=90, factor=0.5, floor=0.05)

        conn = sqlite3.connect(db)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT c.content FROM chunks c JOIN files f ON c.file_id = f.id "
            "WHERE c.content LIKE '%迟到%'").fetchone()
        edge_count = conn.execute("SELECT COUNT(*) FROM tag_edges").fetchone()[0]
        conn.close()
        # 正文仍在、完整、可手动翻到；关联边也未因弱化被删除。
        assert row is not None and '连续三天有学生迟到' in row['content']
        assert edge_count == 4, "关联边数量应保持不变（非破坏）"