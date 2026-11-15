"""Tests for 记忆库可迁移 · 路径相对化（Issue #11）.

契约（见 .scratch/self-index/issues/03-*.md）：
- ingest 新数据存相对路径（正斜杠），老绝对路径仍能匹配（**不插重复行**）
- 读取侧 isabs 判定：老的绝对原样返回，新的按 db 所在目录还原
- 迁移只 UPDATE files.file_path，chunks 一个字节不动
- --dry-run 默认，--apply 前自动备份

第 8、16、17 是核心三条。
"""
import hashlib
import os
import sqlite3
import tempfile

import pytest

import scripts.config as cfg
from scripts.config import get_agent_dir, get_db_path
from scripts.embedding import FakeEmbeddingClient
from scripts.ingest import ingest_file
from scripts.maintenance import main as maint_main
from scripts.paths import resolve_file_path, stored_path
from scripts.recall import literal_recall, timeline_recall
from scripts.schema import init_db


@pytest.fixture
def basedir():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        old_base = cfg.BASE_DIR
        cfg.BASE_DIR = tmp
        yield tmp
        cfg.BASE_DIR = old_base


@pytest.fixture
def agent(basedir):
    return 'seagull'


@pytest.fixture
def client():
    return FakeEmbeddingClient(dimension=64)


def _diary(agent, name='2026-11-14_120000.md', body='今天记一条。', tags='测试'):
    d = os.path.join(get_agent_dir(agent), 'dailynote')
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, name)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(f'---\nmaid: {agent}\ncreated: 2026-11-14T12:00:00\n'
                f'tags: [{tags}]\n---\n{body}\n')
    return path


def _rows(agent, col='file_path'):
    conn = sqlite3.connect(get_db_path(agent))
    try:
        return [r[0] for r in conn.execute(f'SELECT {col} FROM files').fetchall()]
    finally:
        conn.close()


def _chunks_digest(agent):
    conn = sqlite3.connect(get_db_path(agent))
    try:
        rows = conn.execute('SELECT id, content FROM chunks ORDER BY id').fetchall()
    finally:
        conn.close()
    h = hashlib.sha256()
    for cid, content in rows:
        h.update(f'{cid}:{content}'.encode('utf-8'))
    return h.hexdigest()


def _db_checksum(agent):
    with open(get_db_path(agent), 'rb') as f:
        return hashlib.sha256(f.read()).hexdigest()


# ============================================================
# 票1：paths.py + ingest 写相对 + 读取兼容
# ============================================================

def test_stored_path_relative(agent):
    """agent 目录内文件 → 正斜杠相对路径，不含盘符与用户名"""
    path = _diary(agent)
    db = get_db_path(agent)

    result = stored_path(path, db)

    assert not os.path.isabs(result)
    assert '\\' not in result
    assert result.startswith('dailynote/')


def test_stored_path_outside_falls_back_absolute(agent, tmp_path):
    """agent 目录外的文件 → 绝对路径"""
    outside = tmp_path / 'outside.md'
    outside.write_text('x', encoding='utf-8')

    result = stored_path(str(outside), get_db_path(agent))

    assert os.path.isabs(result)


def test_stored_path_cross_drive_falls_back(agent, monkeypatch):
    """relpath 抛 ValueError（跨盘）→ 绝对路径，不崩"""
    path = _diary(agent)

    def boom(*a, **k):
        raise ValueError('cross drive')

    monkeypatch.setattr(os.path, 'relpath', boom)

    result = stored_path(path, get_db_path(agent))

    assert os.path.isabs(result)


def test_resolve_relative(agent):
    """相对路径 → 拼成 <db 目录>/... 绝对路径"""
    db = get_db_path(agent)

    result = resolve_file_path(db, 'dailynote/a.md')

    assert os.path.isabs(result)
    assert result.endswith(os.path.join('dailynote', 'a.md'))


def test_resolve_absolute_passthrough(agent):
    """绝对路径 → 原样返回（老数据）"""
    abs_path = os.path.join(get_agent_dir(agent), 'dailynote', 'a.md')

    assert resolve_file_path(get_db_path(agent), abs_path) == abs_path


def test_resolve_empty(agent):
    """None / '' → 原样返回，不抛"""
    db = get_db_path(agent)

    assert resolve_file_path(db, None) is None
    assert resolve_file_path(db, '') == ''


def test_ingest_stores_relative(agent, client):
    """入库后查库，file_path 是相对路径"""
    path = _diary(agent)
    init_db(get_db_path(agent)).close()

    ingest_file(path, get_db_path(agent), client)

    stored = _rows(agent)
    assert len(stored) == 1
    assert not os.path.isabs(stored[0])
    assert stored[0].startswith('dailynote/')
    assert '\\' not in stored[0]


def test_ingest_matches_legacy_absolute_no_duplicate(agent, client):
    """**核心**：老库存绝对路径 → 再 ingest 同一文件，files 仍只有 1 行

    这是本 Issue 最贵的错：只用相对路径查老库会查不到，当成新文件插第二次。
    """
    path = _diary(agent)
    db = get_db_path(agent)
    conn = init_db(db)
    conn.execute(
        'INSERT INTO files (file_path, diary_name, checksum, diary_date) '
        'VALUES (?, ?, ?, ?)',
        (os.path.abspath(path), agent, 'legacy-checksum', '2026-11-14'))
    conn.commit()
    conn.close()

    ingest_file(path, db, client)

    assert len(_rows(agent)) == 1, '老绝对路径没匹配上，插出了重复行'


# ============================================================
# 票2：读取侧还原
# ============================================================

def test_timeline_returns_resolved_path(agent, client):
    """--timeline 返回的 file_path 是存在的绝对路径"""
    path = _diary(agent)
    init_db(get_db_path(agent)).close()
    ingest_file(path, get_db_path(agent), client)

    results = timeline_recall(get_db_path(agent), k=5)

    assert len(results) == 1
    assert os.path.isabs(results[0]['file_path'])
    assert os.path.exists(results[0]['file_path'])


def test_literal_returns_resolved_path(agent, client):
    """--literal 返回的 file_path 也是绝对路径"""
    path = _diary(agent, body='这里有个独特词：雪鸮')
    init_db(get_db_path(agent)).close()
    ingest_file(path, get_db_path(agent), client)

    results = literal_recall(get_db_path(agent), '雪鸮')

    assert len(results) == 1
    assert os.path.isabs(results[0]['file_path'])


# ============================================================
# 票3：迁移命令
# ============================================================

def _legacy_db(agent, n=2):
    """造一个「老库」：file_path 全是绝对路径。"""
    db = get_db_path(agent)
    conn = init_db(db)
    for i in range(n):
        p = os.path.join(get_agent_dir(agent), 'dailynote', f'd{i}.md')
        conn.execute(
            'INSERT INTO files (file_path, diary_name, checksum, diary_date) '
            'VALUES (?, ?, ?, ?)', (p, agent, f'c{i}', '2026-11-14'))
    conn.commit()
    conn.close()
    return db


def test_relativize_dry_run_no_write(agent):
    """--dry-run 后库 checksum 不变"""
    _legacy_db(agent)
    before = _db_checksum(agent)

    rc = maint_main(['--relativize-paths', '--agent', agent])

    assert rc == 0
    assert _db_checksum(agent) == before


def test_relativize_apply_creates_backup(agent):
    """--apply 后存在 .bak-* 备份"""
    _legacy_db(agent)

    rc = maint_main(['--relativize-paths', '--agent', agent, '--apply'])

    assert rc == 0
    d = os.path.dirname(get_db_path(agent))
    backups = [f for f in os.listdir(d) if '.bak-' in f]
    assert backups, '没有生成备份'


def test_relativize_apply_updates_rows(agent):
    """--apply 后所有 file_path 非 isabs"""
    _legacy_db(agent)

    maint_main(['--relativize-paths', '--agent', agent, '--apply'])

    for fp in _rows(agent):
        assert not os.path.isabs(fp), f'仍是绝对路径：{fp}'


def test_relativize_idempotent(agent):
    """连跑两次 --apply，第二次 would_change == 0"""
    _legacy_db(agent)

    maint_main(['--relativize-paths', '--agent', agent, '--apply'])
    before = _rows(agent)

    maint_main(['--relativize-paths', '--agent', agent, '--apply'])

    assert _rows(agent) == before


def test_relativize_skips_outside_paths(agent, tmp_path):
    """agent 目录外的绝对路径 → 跳过，仍为绝对"""
    db = init_db(get_db_path(agent))
    outside = str(tmp_path / 'elsewhere.md')
    db.execute('INSERT INTO files (file_path, diary_name, checksum, diary_date) '
               'VALUES (?, ?, ?, ?)', (outside, agent, 'c1', '2026-11-14'))
    db.commit()
    db.close()

    maint_main(['--relativize-paths', '--agent', agent, '--apply'])

    assert outside in _rows(agent)


# ============================================================
# 票4：搬迁往返验收（核心）
# ============================================================

def test_relocate_agent_dir_still_readable(agent, client, basedir):
    """**核心**：整个 agent 目录复制到新路径 → 对副本跑 timeline，内容一致"""
    import shutil

    path = _diary(agent, body='搬迁测试：这段正文必须还在。', tags='搬迁')
    init_db(get_db_path(agent)).close()
    ingest_file(path, get_db_path(agent), client)

    original = timeline_recall(get_db_path(agent), k=5)
    assert original

    # 复制整个 agent 目录到 base 下另一个名字
    src = get_agent_dir(agent)
    dst = os.path.join(basedir, 'moved_agent')
    shutil.copytree(src, dst)

    moved_db = os.path.join(dst, 'recall.db')
    moved = timeline_recall(moved_db, k=5)

    assert len(moved) == len(original)
    assert moved[0]['content'] == original[0]['content']
    assert '搬迁测试' in moved[0]['content']
    # 副本里还原出的路径必须真的指向副本内的文件
    assert os.path.exists(moved[0]['file_path'])
    assert os.path.abspath(dst) in os.path.abspath(moved[0]['file_path'])


def test_chunks_content_untouched(agent, client):
    """**核心**：迁移前后 chunks.content 全表哈希一致"""
    _legacy_db(agent)
    db = get_db_path(agent)
    conn = sqlite3.connect(db)
    conn.execute('INSERT INTO chunks (file_id, chunk_index, content, importance) '
                 'VALUES (1, 0, ?, ?)', ('正文不许动', 'high'))
    conn.commit()
    conn.close()

    before = _chunks_digest(agent)
    maint_main(['--relativize-paths', '--agent', agent, '--apply'])

    assert _chunks_digest(agent) == before
