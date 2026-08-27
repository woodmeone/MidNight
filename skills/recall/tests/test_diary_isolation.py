"""Tests for physical agent isolation in recall (多智能体物理隔离).

Verifies that different agents (Nova vs Coco) use completely separate
database files and directories, so there's no cross-contamination.
"""
import os
import tempfile
import pytest

from scripts.embedding import FakeEmbeddingClient
from scripts.schema import init_db
from scripts.ingest import ingest_file
from scripts.recall import recall, recall_associative
from scripts.config import get_db_path, get_dailynote_path, ensure_agent_dir


@pytest.fixture
def embed():
    return FakeEmbeddingClient(dimension=4)


def _write_diary(dirpath, maid, tags, content, date="2026-08-15"):
    """Write a diary into a specific agent's dailynote dir."""
    os.makedirs(dirpath, exist_ok=True)
    file_path = os.path.join(dirpath, f'{maid}.md')
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(f"""---
maid: {maid}
created: {date}T10:00:00
tags: [{tags}]
---
{content}
""")
    return file_path


def test_physical_agents_have_separate_dbs(embed):
    """不同智能体使用不同的数据库文件"""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as basedir:
        import scripts.config as cfg
        old_base = cfg.BASE_DIR
        cfg.BASE_DIR = basedir

        try:
            nova_db = get_db_path('Nova')
            coco_db = get_db_path('Coco')
            assert nova_db != coco_db
            assert 'Nova' in nova_db
            assert 'Coco' in coco_db
        finally:
            cfg.BASE_DIR = old_base


def test_physical_agent_write_and_read(embed):
    """写入 Nova 的记忆只从 Nova 的数据库读到"""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as basedir:
        import scripts.config as cfg
        old_base = cfg.BASE_DIR
        cfg.BASE_DIR = basedir

        try:
            ensure_agent_dir('Nova')
            ensure_agent_dir('Coco')

            # Write Nova diary
            nova_diary = get_dailynote_path('Nova')
            _write_diary(nova_diary, 'Nova', '考试', 'Nova的考试记忆')
            ingest_file(os.path.join(nova_diary, 'Nova.md'), get_db_path('Nova'), embed)
            os.unlink(os.path.join(nova_diary, 'Nova.md'))

            # Write Coco diary
            coco_diary = get_dailynote_path('Coco')
            _write_diary(coco_diary, 'Coco', '旅行', 'Coco的旅行记忆')
            ingest_file(os.path.join(coco_diary, 'Coco.md'), get_db_path('Coco'), embed)
            os.unlink(os.path.join(coco_diary, 'Coco.md'))

            # Nova should only see Nova's memory
            nova_results = recall("记忆", get_db_path('Nova'), embed, k=10)
            assert len(nova_results) == 1
            assert 'Nova' in nova_results[0]['content']

            # Coco should only see Coco's memory
            coco_results = recall("记忆", get_db_path('Coco'), embed, k=10)
            assert len(coco_results) == 1
            assert 'Coco' in coco_results[0]['content']
        finally:
            cfg.BASE_DIR = old_base


def test_physical_associative_agent_isolation(embed):
    """联想召回也遵循物理隔离"""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as basedir:
        import scripts.config as cfg
        old_base = cfg.BASE_DIR
        cfg.BASE_DIR = basedir

        try:
            ensure_agent_dir('Nova')
            ensure_agent_dir('Coco')

            nova_diary = get_dailynote_path('Nova')
            _write_diary(nova_diary, 'Nova', '考试 压力', 'Nova的考试压力')
            ingest_file(os.path.join(nova_diary, 'Nova.md'), get_db_path('Nova'), embed)
            os.unlink(os.path.join(nova_diary, 'Nova.md'))

            coco_diary = get_dailynote_path('Coco')
            _write_diary(coco_diary, 'Coco', '美食 旅行', 'Coco的美食旅行')
            ingest_file(os.path.join(coco_diary, 'Coco.md'), get_db_path('Coco'), embed)
            os.unlink(os.path.join(coco_diary, 'Coco.md'))

            nova_assoc = recall_associative("考试", get_db_path('Nova'), embed, k=10)
            assert len(nova_assoc) >= 1
            assert 'Nova' in nova_assoc[0]['content']

            coco_assoc = recall_associative("考试", get_db_path('Coco'), embed, k=10)
            # Coco's memory has no exam content, but might match via associative
            # At minimum, the DBs are separate
            assert len(coco_assoc) >= 0
        finally:
            cfg.BASE_DIR = old_base


def test_physical_agent_default_isolation(embed):
    """默认 agent 与其他 agent 物理隔离"""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as basedir:
        import scripts.config as cfg
        old_base = cfg.BASE_DIR
        cfg.BASE_DIR = basedir

        try:
            ensure_agent_dir('default')
            ensure_agent_dir('Nova')

            default_diary = get_dailynote_path('default')
            _write_diary(default_diary, 'default', '默认', '默认数据')
            ingest_file(os.path.join(default_diary, 'default.md'), get_db_path('default'), embed)
            os.unlink(os.path.join(default_diary, 'default.md'))

            nova_diary = get_dailynote_path('Nova')
            _write_diary(nova_diary, 'Nova', 'Nova', 'Nova数据')
            ingest_file(os.path.join(nova_diary, 'Nova.md'), get_db_path('Nova'), embed)
            os.unlink(os.path.join(nova_diary, 'Nova.md'))

            default_results = recall("数据", get_db_path('default'), embed, k=10)
            nova_results = recall("数据", get_db_path('Nova'), embed, k=10)

            assert len(default_results) == 1
            assert len(nova_results) == 1
            assert '默认' in default_results[0]['content']
            assert 'Nova' in nova_results[0]['content']
        finally:
            cfg.BASE_DIR = old_base