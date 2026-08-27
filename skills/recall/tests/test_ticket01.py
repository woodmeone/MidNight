"""Tests for ticket 01: storage layer and minimal ingest pipeline.

Tests the core logic (ingest_file, init_db, embedding client abstraction)
at the highest seam — function calls, not CLI invocations.
"""
import os
import tempfile
import sqlite3
import pytest
from datetime import datetime

# ---- 测试夹具 ----

@pytest.fixture
def db_path():
    """临时数据库路径（使用目录确保 Windows 上可清理）"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield os.path.join(tmpdir, 'recall.db')

@pytest.fixture
def diary_dir():
    """临时日记目录"""
    with tempfile.TemporaryDirectory() as d:
        yield d

@pytest.fixture
def fake_embed():
    """可注入的假 embedding 客户端（确定性伪向量，不依赖外网）"""
    from scripts.embedding import FakeEmbeddingClient
    return FakeEmbeddingClient(dimension=4)  # 小维度加速测试

# 我们需要先导入实现，但测试先写再实现
# 所以这里先写测试描述，等实现存在后再取消注释跑
# 但现在按 TDD 先写 red 测试

def test_init_db_creates_tables(db_path):
    """init_db 应创建全部 5 张表"""
    from scripts.schema import init_db
    conn = init_db(db_path)
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    tables = [row[0] for row in cursor.fetchall()]
    assert 'chunk_tags' in tables
    assert 'chunks' in tables
    assert 'files' in tables
    assert 'tag_cooccurrence' in tables
    assert 'tags' in tables
    conn.close()

def test_init_db_idempotent(db_path):
    """init_db 可重复调用，不报错"""
    from scripts.schema import init_db
    conn1 = init_db(db_path)
    conn1.close()
    conn2 = init_db(db_path)
    conn2.close()

def test_fake_embedding_returns_deterministic_vectors():
    """FakeEmbeddingClient 对同一文本返回相同向量"""
    from scripts.embedding import FakeEmbeddingClient
    client = FakeEmbeddingClient(dimension=4)
    v1 = client.embed(["hello world"])
    v2 = client.embed(["hello world"])
    assert v1 == v2

def test_fake_embedding_dimension():
    """FakeEmbeddingClient 返回指定维度"""
    from scripts.embedding import FakeEmbeddingClient
    client = FakeEmbeddingClient(dimension=16)
    vec = client.embed(["test"])[0]
    assert len(vec) == 16

def test_ingest_parses_diary_file(db_path, fake_embed):
    """ingest_file 解析标准日记并写入数据库"""
    from scripts.ingest import ingest_file
    from scripts.schema import init_db
    import tempfile

    # 写一份标准日记文件
    diary_content = """---
maid: Nova
created: 2026-08-20T14:30:00
tags: [考试, 压力, 面试]
---
今天阿漂说下周要面试，有点紧张。他准备了三天，但觉得不够充分。
"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, encoding='utf-8') as f:
        f.write(diary_content)
        file_path = f.name
    
    try:
        result = ingest_file(file_path, db_path, fake_embed)
        assert result['status'] == 'ingested', f"ingest failed: {result}"
        assert result['file_id'] is not None
        assert result['chunks_count'] >= 1

        # 验证数据库记录
        conn = sqlite3.connect(db_path)
        files = conn.execute("SELECT * FROM files").fetchall()
        assert len(files) == 1
        chunks = conn.execute("SELECT * FROM chunks").fetchall()
        assert len(chunks) >= 1
        # 验证标签
        tags = conn.execute("SELECT name FROM tags").fetchall()
        tag_names = [t[0] for t in tags]
        assert '考试' in tag_names
        assert '压力' in tag_names
        assert '面试' in tag_names
        conn.close()
    finally:
        os.unlink(file_path)

def test_ingest_idempotent(db_path, fake_embed):
    """同一文件重复 ingest 跳过（checksum 去重）"""
    from scripts.ingest import ingest_file
    from scripts.schema import init_db
    import tempfile

    diary_content = """---
maid: Nova
created: 2026-08-20T14:30:00
tags: [测试]
---
重复测试内容。
"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, encoding='utf-8') as f:
        f.write(diary_content)
        file_path = f.name
    
    try:
        r1 = ingest_file(file_path, db_path, fake_embed)
        assert r1['status'] == 'ingested'
        r2 = ingest_file(file_path, db_path, fake_embed)
        assert r2['status'] == 'skipped', f"second ingest should be skipped: {r2}"
        
        conn = sqlite3.connect(db_path)
        count = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
        assert count == 1, f"should be 1 file, got {count}"
        conn.close()
    finally:
        os.unlink(file_path)

def test_ingest_modified_file_reingested(db_path, fake_embed):
    """文件内容修改后应重新入库"""
    from scripts.ingest import ingest_file
    from scripts.schema import init_db
    import tempfile

    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, encoding='utf-8') as f:
        f.write("""---
maid: Nova
created: 2026-08-20
tags: [v1]
---
版本一内容。
""")
        file_path = f.name
    
    try:
        r1 = ingest_file(file_path, db_path, fake_embed)
        assert r1['status'] == 'ingested'
        
        # 修改文件
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write("""---
maid: Nova
created: 2026-08-21
tags: [v2]
---
版本二内容，修改了。
""")
        
        r2 = ingest_file(file_path, db_path, fake_embed)
        assert r2['status'] == 'ingested', f"modified file should be re-ingested: {r2}"
        
        conn = sqlite3.connect(db_path)
        # 修改后 file_id 可以不变，但 chunks 应更新
        chunks = conn.execute("SELECT content FROM chunks").fetchall()
        contents = [c[0] for c in chunks]
        assert any('版本二' in c for c in contents), "new content should be in db"
        conn.close()
    finally:
        os.unlink(file_path)

def test_ingest_no_frontmatter(db_path, fake_embed):
    """无 frontmatter 的纯文本文件也能入库（自动生成 maid/date/tags）"""
    from scripts.ingest import ingest_file
    from scripts.schema import init_db
    import tempfile

    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, encoding='utf-8') as f:
        f.write("这是一段纯文本日记，没有 frontmatter。")
        file_path = f.name
    
    try:
        result = ingest_file(file_path, db_path, fake_embed)
        assert result['status'] == 'ingested'
        conn = sqlite3.connect(db_path)
        files = conn.execute("SELECT * FROM files").fetchall()
        assert len(files) == 1
        conn.close()
    finally:
        os.unlink(file_path)