"""End-to-end test for midnight-recall.

Verifies the complete pipeline: write diary → ingest → recall → format output.
"""
import os
import tempfile
import pytest

from scripts.embedding import FakeEmbeddingClient
from scripts.schema import init_db
from scripts.ingest import ingest_file
from scripts.recall import recall_associative, format_recall_output


@pytest.fixture
def env():
    """Create a complete recall environment (db + diary dir + client)."""
    tmpdir_obj = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
    tmpdir = tmpdir_obj.name
    db_path = os.path.join(tmpdir, 'recall.db')
    diary_dir = os.path.join(tmpdir, 'dailynote')
    os.makedirs(diary_dir, exist_ok=True)
    client = FakeEmbeddingClient(dimension=16)
    init_db(db_path)
    yield {
        'tmpdir': tmpdir,
        'db_path': db_path,
        'diary_dir': diary_dir,
        'client': client,
    }
    tmpdir_obj.cleanup()


def _write_diary(diary_dir, filename, tags, content, date="2026-08-15"):
    """Helper to write a diary file."""
    file_path = os.path.join(diary_dir, filename)
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(f"""---
maid: Nova
created: {date}T10:00:00
tags: [{tags}]
---
{content}
""")
    return file_path


def test_end_to_end_basic(env):
    """端到端基本流程：写日记 → 入库 → 召回 → 输出"""
    # 1. Write diary
    file_path = _write_diary(env['diary_dir'], 'test.md',
                             "考试 压力", "用户说下周要考试，压力很大，睡不着。")
    # 2. Ingest
    result = ingest_file(file_path, env['db_path'], env['client'])
    assert result['status'] == 'ingested'
    # 3. Recall
    results = recall_associative("考试", env['db_path'], env['client'],
                                 k=5, tag_weight=0.3, time_ratio=0.2)
    assert len(results) >= 1
    # 4. Format
    text = format_recall_output(results)
    assert len(text) > 10
    # 5. Cleanup
    os.unlink(file_path)


def test_end_to_end_associative(env):
    """端到端联想验证：写"考试"日记，查"焦虑"应联想召回"""
    # 1. Write diary with "考试"
    _write_diary(env['diary_dir'], 'exam.md',
                 "考试 压力 焦虑", "用户说下周要数学考试，压力很大，准备了三天。")
    ingest_file(os.path.join(env['diary_dir'], 'exam.md'), env['db_path'], env['client'])
    os.unlink(os.path.join(env['diary_dir'], 'exam.md'))

    # 2. Write unrelated diary
    _write_diary(env['diary_dir'], 'travel.md',
                 "旅行 京都", "用户计划去京都旅行。")
    ingest_file(os.path.join(env['diary_dir'], 'travel.md'), env['db_path'], env['client'])
    os.unlink(os.path.join(env['diary_dir'], 'travel.md'))

    # 3. Query with "焦虑" (should find exam content via tag co-occurrence)
    results = recall_associative("焦虑", env['db_path'], env['client'],
                                 k=5, tag_weight=0.5, time_ratio=0.1)
    contents = [r['content'] for r in results]
    assert any('考试' in c or '数学' in c for c in contents), \
        "联想应该将「焦虑」与「考试」关联起来"


def test_end_to_end_multiple_ingest(env):
    """多次入库后召回结果正确"""
    for i in range(3):
        _write_diary(env['diary_dir'], f'diary_{i}.md',
                     f"测试 第{i}条", f"这是第{i}条测试日记内容。")
        ingest_file(os.path.join(env['diary_dir'], f'diary_{i}.md'),
                    env['db_path'], env['client'])
        os.unlink(os.path.join(env['diary_dir'], f'diary_{i}.md'))

    results = recall_associative("测试", env['db_path'], env['client'],
                                 k=5, tag_weight=0, time_ratio=0)
    assert len(results) == 3