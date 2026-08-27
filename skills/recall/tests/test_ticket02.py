"""Tests for ticket 02: vector KNN recall (recall.py core logic).

Tests the recall function at the function-call seam, not the CLI.
"""
import os
import tempfile
import sqlite3
import pytest

from scripts.embedding import FakeEmbeddingClient
from scripts.schema import init_db
from scripts.ingest import ingest_file
from scripts.recall import recall, format_recall_output, cosine_similarity


@pytest.fixture
def db_path():
    """临时数据库路径"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield os.path.join(tmpdir, 'recall.db')


@pytest.fixture
def embed():
    """4 维假 embedding（加速测试）"""
    return FakeEmbeddingClient(dimension=4)


@pytest.fixture
def seeded_db(db_path, embed):
    """预填 3 条不同主题的日记"""
    conn = init_db(db_path)
    conn.close()

    topics = [
        ("考试压力", "下周要参加数学考试，感觉压力很大，准备还不够充分。"),
        ("旅行计划", "计划下个月去日本旅行，正在研究京都的景点和美食。"),
        ("编程学习", "最近在学习 Python 的高级特性，装饰器和生成器真有意思。"),
    ]
    for i, (tag, content) in enumerate(topics):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, encoding='utf-8') as f:
            f.write(f"""---
maid: Nova
created: 2026-08-{10 + i:02d}T10:00:00
tags: [{tag}]
---
{content}
""")
            file_path = f.name
        ingest_file(file_path, db_path, embed)
        os.unlink(file_path)

    return db_path


# ---- Unit tests ----

def test_cosine_similarity_identical():
    """相同向量余弦相似度为 1.0"""
    v = [1.0, 0.0, 0.0, 0.0]
    assert cosine_similarity(v, v) == pytest.approx(1.0, rel=1e-6)


def test_cosine_similarity_orthogonal():
    """正交向量余弦相似度为 0.0"""
    a = [1.0, 0.0, 0.0, 0.0]
    b = [0.0, 1.0, 0.0, 0.0]
    assert cosine_similarity(a, b) == pytest.approx(0.0, abs=1e-6)


def test_cosine_similarity_zero_vector():
    """零向量余弦相似度为 0.0"""
    a = [0.0, 0.0, 0.0, 0.0]
    b = [1.0, 0.0, 0.0, 0.0]
    assert cosine_similarity(a, b) == 0.0


# ---- Integration tests ----

def test_recall_empty_db(embed):
    """空库返回空列表"""
    with tempfile.TemporaryDirectory() as tmpdir:
        db = os.path.join(tmpdir, 'empty.db')
        conn = init_db(db)
        conn.close()
        results = recall("什么内容都没有", db, embed, k=5)
        assert results == []


def test_recall_returns_top_k(seeded_db, embed):
    """recall 返回 Top-K 条结果"""
    results = recall("考试", seeded_db, embed, k=2)
    assert len(results) <= 2
    assert len(results) > 0


def test_recall_most_relevant_first(seeded_db, embed):
    """查询结果按相似度降序排列"""
    results = recall("考试 压力 焦虑", seeded_db, embed, k=3)
    assert len(results) == 3
    # 第一条应该最相关（考试压力）
    assert results[0]['score'] >= results[1]['score']
    assert results[1]['score'] >= results[2]['score']


def test_recall_matches_topic(seeded_db, embed):
    """查询"考试"应优先召回考试相关日记"""
    results = recall("考试", seeded_db, embed, k=3)
    top = results[0]['content']
    assert '考试' in top or '压力' in top


def test_recall_all_k(seeded_db, embed):
    """k=10 时返回全部 3 条"""
    results = recall("随便", seeded_db, embed, k=10)
    # 我们只有 3 条日记
    assert len(results) == 3


def test_recall_k_1(seeded_db, embed):
    """k=1 只返回 1 条"""
    results = recall("考试", seeded_db, embed, k=1)
    assert len(results) == 1


# ---- Format tests ----

def test_format_empty():
    """空结果输出友好提示"""
    text = format_recall_output([])
    assert "暂无相关记忆" in text


def test_format_non_empty():
    """非空结果包含日期和内容"""
    results = [{'chunk_id': 1, 'content': '今天考试', 'date': '2026-08-15', 'file_path': 'x.md', 'score': 0.9}]
    text = format_recall_output(results)
    assert '2026-08-15' in text
    assert '今天考试' in text