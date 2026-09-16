"""Regression tests for root-level orphan data (maintenance.py).

多智能体物理隔离要求每个 agent 有自己的 recall.db 与 dailynote/。
早期单库时代的根级 recall.db / 根级 dailynote/ 不属于任何 agent，
需要能被 detect_orphans 发现、被 migrate_orphans 归并进指定 agent。
"""
import os
import tempfile
import pytest

from scripts.schema import init_db
from scripts.embedding import FakeEmbeddingClient
from scripts.config import (
    DEFAULT_AGENT, get_agent_dir, get_db_path, get_dailynote_path,
)
from scripts.maintenance import detect_orphans, migrate_orphans
import scripts.config as cfg


@pytest.fixture
def embed():
    return FakeEmbeddingClient(dimension=4)


def _set_base(tmpdir):
    old = cfg.BASE_DIR
    cfg.BASE_DIR = tmpdir
    return old


def _write_md(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)


def _make_root_db(base):
    """Create a valid (empty, schema-initialized) recall.db at the base root."""
    init_db(os.path.join(base, 'recall.db')).close()


def test_detect_orphans_finds_root_data_only():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        old = _set_base(tmpdir)
        try:
            _make_root_db(tmpdir)
            _write_md(os.path.join(tmpdir, 'dailynote', '2026-08-01.md'), '---\n---\n根级旧日记')
            _write_md(os.path.join(tmpdir, 'loose.md'), '---\n---\n根级散落日记')

            # 正常 agent 子目录（自带 recall.db + dailynote）不是孤儿
            nova_dir = get_agent_dir('Nova')
            os.makedirs(os.path.join(nova_dir, 'dailynote'), exist_ok=True)
            init_db(get_db_path('Nova')).close()
            _write_md(os.path.join(nova_dir, 'dailynote', 'c.md'), '---\n---\nNova日记')

            o = detect_orphans(base_dir=tmpdir)
            assert o['recall_db'] == os.path.join(tmpdir, 'recall.db')
            assert o['dailynote_files'] == ['2026-08-01.md']
            assert o['loose_files'] == ['loose.md']
        finally:
            cfg.BASE_DIR = old


def test_detect_orphans_clean_base():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        old = _set_base(tmpdir)
        try:
            nova_dir = get_agent_dir('Nova')
            os.makedirs(os.path.join(nova_dir, 'dailynote'), exist_ok=True)
            init_db(get_db_path('Nova')).close()
            o = detect_orphans(base_dir=tmpdir)
            assert o == {'recall_db': None, 'dailynote_files': [], 'loose_files': []}
        finally:
            cfg.BASE_DIR = old


def test_migrate_root_data_into_agent(embed):
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        old = _set_base(tmpdir)
        try:
            _make_root_db(tmpdir)
            _write_md(os.path.join(tmpdir, 'dailynote', '2026-08-01.md'),
                      '---\ntags: [考试]\n---\n根级考试日记')
            _write_md(os.path.join(tmpdir, 'loose.md'), '---\n---\n根级散落')

            res = migrate_orphans(DEFAULT_AGENT, tmpdir)
            assert res['moved_diaries'] == 2
            assert res['db_action'] == 'moved'
            assert res['ingested'] >= 2

            daily = get_dailynote_path(DEFAULT_AGENT)
            assert os.path.exists(os.path.join(daily, '2026-08-01.md'))
            assert os.path.exists(os.path.join(daily, 'loose.md'))
            assert os.path.exists(get_db_path(DEFAULT_AGENT))
            # 根级已清空
            assert not os.path.exists(os.path.join(tmpdir, 'recall.db'))
            assert not os.path.exists(os.path.join(tmpdir, 'dailynote', '2026-08-01.md'))
        finally:
            cfg.BASE_DIR = old


def test_migrate_backs_up_root_db_when_agent_has_one(embed):
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        old = _set_base(tmpdir)
        try:
            # agent default 已存在库
            init_db(get_db_path(DEFAULT_AGENT)).close()
            _make_root_db(tmpdir)

            res = migrate_orphans(DEFAULT_AGENT, tmpdir)
            assert res['db_action'] == 'backed_up'
            assert os.path.exists(os.path.join(tmpdir, 'recall.db.root.bak'))
            # 已有 agent 库不受影响
            assert os.path.exists(get_db_path(DEFAULT_AGENT))
        finally:
            cfg.BASE_DIR = old


def test_migrate_name_collision_uses_root_suffix(embed):
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        old = _set_base(tmpdir)
        try:
            _write_md(os.path.join(tmpdir, 'dailynote', '2026-08-01.md'), '---\n---\n根级')
            _write_md(os.path.join(get_dailynote_path(DEFAULT_AGENT), '2026-08-01.md'),
                      '---\n---\n已有')

            res = migrate_orphans(DEFAULT_AGENT, tmpdir)
            assert res['moved_diaries'] == 1
            assert os.path.exists(os.path.join(get_dailynote_path(DEFAULT_AGENT), '2026-08-01.md'))
            assert os.path.exists(os.path.join(get_dailynote_path(DEFAULT_AGENT), '2026-08-01.md.root'))
        finally:
            cfg.BASE_DIR = old
