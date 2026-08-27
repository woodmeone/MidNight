"""Adversarial tests for new features: physical isolation, importance, agent paths.

逆向思维：边界条件、异常路径、安全。
"""
import os
import tempfile
import sqlite3
import pytest

from scripts.embedding import FakeEmbeddingClient
from scripts.schema import init_db
from scripts.ingest import ingest_file, parse_diary
from scripts.recall import recall, recall_associative
from scripts.config import get_db_path, get_dailynote_path, ensure_agent_dir, BASE_DIR
import scripts.config as cfg


@pytest.fixture
def embed():
    return FakeEmbeddingClient(dimension=4)


# ---- Importance parsing ----

def test_parse_diary_importance_high():
    """importance: high 应正确解析"""
    r = parse_diary("---\nimportance: high\n---\n内容")
    assert r['importance'] == 'high'


def test_parse_diary_importance_low():
    """importance: low 应正确解析"""
    r = parse_diary("---\nimportance: low\n---\n内容")
    assert r['importance'] == 'low'


def test_parse_diary_importance_default():
    """无 importance 字段使用默认 medium"""
    r = parse_diary("---\ntags: [a]\n---\n内容")
    assert r['importance'] == 'medium'


def test_parse_diary_importance_invalid():
    """非法 importance 值回退到 medium"""
    r = parse_diary("---\nimportance: ultra\n---\n内容")
    assert r['importance'] == 'medium'


# ---- Physical isolation ----

def test_agent_paths_are_unique():
    """不同智能体的路径完全不同"""
    assert get_db_path('Nova') != get_db_path('Coco')
    assert get_dailynote_path('Nova') != get_dailynote_path('Coco')


def test_agent_path_contains_name():
    """路径中包含智能体名"""
    assert 'Nova' in get_db_path('Nova')
    assert 'Coco' in get_dailynote_path('Coco')


def test_agent_default_is_default():
    """默认智能体名为 'default'"""
    path = get_db_path()
    assert 'default' in path


def test_ensure_agent_dir_creates(embed):
    """ensure_agent_dir 创建目录"""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        old_base = cfg.BASE_DIR
        cfg.BASE_DIR = tmpdir
        try:
            path = ensure_agent_dir('TestAgent')
            assert os.path.exists(path)
            assert os.path.exists(os.path.join(path, 'dailynote'))
        finally:
            cfg.BASE_DIR = old_base


def test_ingest_to_agent_default_to_other(embed):
    """写入 agent A 的数据不应出现在 agent B 的数据库"""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        old_base = cfg.BASE_DIR
        cfg.BASE_DIR = tmpdir
        try:
            ensure_agent_dir('AgentA')
            file_path = os.path.join(get_dailynote_path('AgentA'), 'test.md')
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write("---\nmaid: A\ntags: [测试]\n---\nAgentA数据")
            r = ingest_file(file_path, get_db_path('AgentA'), embed)
            assert r['status'] == 'ingested'
            os.unlink(file_path)

            # AgentB 的数据库应无数据
            init_db(get_db_path('AgentB'))
            conn = sqlite3.connect(get_db_path('AgentB'))
            count = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
            conn.close()
            assert count == 0
        finally:
            cfg.BASE_DIR = old_base


def test_ingest_agent_with_special_chars(embed):
    """智能体名含特殊字符时路径仍正确"""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        old_base = cfg.BASE_DIR
        cfg.BASE_DIR = tmpdir
        try:
            path = ensure_agent_dir('Test-Agent_123')
            assert os.path.exists(path)
            db = get_db_path('Test-Agent_123')
            assert 'Test-Agent_123' in db
        finally:
            cfg.BASE_DIR = old_base


# ---- Importance in recall results ----

def test_importance_in_recall_result(embed):
    """召回结果中包含 importance 字段"""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        old_base = cfg.BASE_DIR
        cfg.BASE_DIR = tmpdir
        try:
            ensure_agent_dir('default')
            file_path = os.path.join(get_dailynote_path('default'), 'test.md')
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write("---\nimportance: high\ntags: [测试]\n---\n重要内容")
            ingest_file(file_path, get_db_path('default'), embed)
            os.unlink(file_path)

            results = recall("内容", get_db_path('default'), embed, k=5)
            assert len(results) > 0
            assert 'importance' in results[0]
            assert results[0]['importance'] == 'high'
        finally:
            cfg.BASE_DIR = old_base


def test_importance_high_outranks_low(embed):
    """相同相似度下 high 比 low 排名高"""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        old_base = cfg.BASE_DIR
        cfg.BASE_DIR = tmpdir
        try:
            ensure_agent_dir('default')
            for imp, tag in [('high', 'A'), ('low', 'B')]:
                file_path = os.path.join(get_dailynote_path('default'), f'{tag}.md')
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(f"---\nimportance: {imp}\ntags: [{tag}]\n---\n相同内容{tag}")
                ingest_file(file_path, get_db_path('default'), embed)
                os.unlink(file_path)

            results = recall("内容", get_db_path('default'), embed, k=5)
            # With fake embedding, "相同内容A" and "相同内容B" should have similar vectors
            # Importance boost should push high above low
            high_idx = next(i for i, r in enumerate(results) if r['importance'] == 'high')
            low_idx = next(i for i, r in enumerate(results) if r['importance'] == 'low')
            assert high_idx < low_idx, "high 应排在 low 前面"
        finally:
            cfg.BASE_DIR = old_base


# ---- Agent env var ----

def test_agent_env_var_override(embed, monkeypatch):
    """环境变量 MIDNIGHT_AGENT 应覆盖默认 agent"""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        old_base = cfg.BASE_DIR
        cfg.BASE_DIR = tmpdir
        try:
            # Set env var
            monkeypatch.setenv('MIDNIGHT_AGENT', 'EnvAgent')
            path = get_db_path()
            assert 'EnvAgent' in path
        finally:
            cfg.BASE_DIR = old_base
            monkeypatch.delenv('MIDNIGHT_AGENT', raising=False)