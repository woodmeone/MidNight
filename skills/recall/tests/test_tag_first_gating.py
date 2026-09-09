"""T1+T2: tag-first 前置门控 + 候选扩增有界。

验收口径（docs/associative-optimization-spec.md §5.1 P-1 / P-3 / P-6）：
- 核心标签(chunk 语义靠标签承载、词面与 query 无重叠)内容必须能被召回 —— tag-first 保证。
- 候选扩增必须有界：高频枢纽标签不能把候选池撑爆（有界、确定性、保最强）。
- 接口 recall_associative 不变；旧测试全绿。
"""
import os
import tempfile
import sqlite3

import pytest

from scripts.embedding import SemanticFakeEmbeddingClient
from scripts.schema import init_db
from scripts.ingest import ingest_file
from scripts.recall import recall_associative, expand_tag_candidates, _time_score
from scripts.tag_network import activate_tags


@pytest.fixture
def embed():
    return SemanticFakeEmbeddingClient()


def _write(db_path, embed, entries):
    for idx, (tags, content) in enumerate(entries):
        fp = os.path.join(tempfile.mkdtemp(), f'd{idx}.md')
        with open(fp, 'w', encoding='utf-8') as f:
            f.write(f"---\nmaid: qinglan\ncreated: 2026-09-{1+idx%28:02d}T10:00:00\n"
                    f"tags: [{tags}]\n---\n{content}\n")
        ingest_file(fp, db_path, embed)
        os.unlink(fp)


@pytest.fixture
def incident_db(embed):
    """复刻真实翻车场景：升学内容词面与 query 无重叠，纯靠标签承载。

    英语内容含「张娜」字面（自然向量命中）；10 条噪声各含「学」字，
    确保在 tag_weight=0 时把 score=0 的升学 chunk 确定性挤出 top-k。
    """
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        db_path = os.path.join(tmpdir, 'recall.db')
        init_db(db_path)
        _write(db_path, embed, [
            ("张娜 升学", "番职大金融科技专业，计应对口，属冲档。"),
            ("张娜 英语 阅读", "张娜英语阅读策略：读带动单词，主攻完形与阅读。"),
            ("熊可婷 兴趣", "熊可婷想学 MJ。"),
            ("郭子峰 课堂", "郭子峰 top1。"),
            *[(f"噪声{i}", f"杂乱学习内容第{i}条，与记忆主题无关。") for i in range(10)],
        ])
        yield db_path


@pytest.fixture
def hub_db(embed):
    """枢纽标签「考试」挂在 30 个 chunk 上；其中一条额外带高激活标签「核心」，应被保留。"""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        db_path = os.path.join(tmpdir, 'recall.db')
        init_db(db_path)
        entries = [("考试", f"考试相关细节第{i}条，与主题无关。") for i in range(30)]
        entries[0] = ("考试 核心", "核心事件的深度记忆，携带高优先级内容。")
        _write(db_path, embed, entries)
        yield db_path, embed


# ============================================================
# T1 · 核心标签保证命中（tag-first 门控）
# ============================================================

def test_core_tagged_content_surfaces_when_vector_misses(incident_db, embed):
    """张娜升学 → 必须带出符职大金融科技（词面对 query 不可见，纯靠标签）。"""
    results = recall_associative("张娜 升学", incident_db, embed,
                                 k=10, tag_weight=1.0, decay=0.9,
                                 max_depth=2, threshold=0.03, time_ratio=0)
    contents = [r['content'] for r in results]
    assert any('番职大' in c for c in contents), "核心标签(张娜/升学)应保证召回升学内容"


def test_person_topic_direction_hits_target(incident_db, embed):
    """「人+事」方向：张娜英语 → 命中英语策略内容。"""
    results = recall_associative("张娜 英语", incident_db, embed,
                                 k=10, tag_weight=1.0, decay=0.9,
                                 max_depth=2, threshold=0.03, time_ratio=0)
    contents = [r['content'] for r in results]
    assert any('英语阅读策略' in c for c in contents), "「张娜英语」应命中英语策略"


# ============================================================
# T2 · 候选扩增有界 + 确定 + 保最强
# ============================================================

def test_tag_candidate_expansion_is_bounded(embed):
    """候选扩增硬上界：高频枢纽标签不得撑爆候选池。"""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        db_path = os.path.join(tmpdir, 'recall.db')
        init_db(db_path)
        _write(db_path, embed, [("考试", f"细节第{i}条。") for i in range(30)])
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            qv = embed.embed(["考试"])[0]
            activated = activate_tags(qv, db_path, embed, max_depth=0, threshold=0.0)
            assert len(activated) > 0
            strength_map = {tid: s for tid, s in activated}
            extras = expand_tag_candidates(conn, activated, strength_map, set(),
                                           tag_weight=1.0, time_ratio=0.0,
                                           time_score_fn=_time_score, cap=5)
            assert len(extras) <= 5, "候选扩增必须受 max_extra 硬上界约束"
        finally:
            conn.close()


def test_tag_candidate_expansion_keeps_strongest(hub_db):
    """确定性 + 保最强：高激活标签携带的 chunk 必须保留，普通洪泛被截。"""
    db_path, embed = hub_db
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        qv = embed.embed(["考试 核心"])[0]
        activated = activate_tags(qv, db_path, embed, max_depth=0, threshold=0.0)
        strength_map = {tid: s for tid, s in activated}
        extras = expand_tag_candidates(conn, activated, strength_map, set(),
                                       tag_weight=1.0, time_ratio=0.0,
                                       time_score_fn=_time_score, cap=5)
        contents = {e['content'] for e in extras}
        assert any('核心事件' in c for c in contents), "高价值(双标签)chunk 应被保留"
    finally:
        conn.close()


# ============================================================
# 回归护栏
# ============================================================

def test_no_expansion_when_tag_weight_zero(incident_db, embed):
    """tag_weight=0 → 不走标签扩增，词面不可见内容应缺失。"""
    results = recall_associative("张娜 升学", incident_db, embed, k=10, tag_weight=0)
    contents = [r['content'] for r in results]
    assert not any('番职大' in c for c in contents), "tag_weight=0 时应退化为纯向量召回"


def test_interface_and_output_shape_unchanged(incident_db, embed):
    """接口返回结构不变：每条含 chunk_id/score/content。"""
    results = recall_associative("张娜", incident_db, embed, k=10, tag_weight=0.5,
                                 time_ratio=0.2)
    assert isinstance(results, list)
    for r in results:
        assert 'chunk_id' in r and 'score' in r and 'content' in r