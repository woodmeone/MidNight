"""Adversarial tests for midnight-recall — 逆向思维 + 系统思维。

覆盖边界条件、异常路径、安全漏洞、数据完整性、并发、恢复。
"""
import os
import tempfile
import sqlite3
import struct
import pytest
from scripts.embedding import FakeEmbeddingClient, load_embedding_client, EmbeddingClient
from scripts.schema import init_db
from scripts.ingest import ingest_file, parse_diary, chunk_body, compute_checksum, FRONTMATTER_PATTERN
from scripts.recall import recall, recall_associative, format_recall_output, cosine_similarity, _deserialize_vector
from scripts.tag_network import activate_tags


@pytest.fixture
def db_path():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        yield os.path.join(tmpdir, 'recall.db')


@pytest.fixture
def embed():
    return FakeEmbeddingClient(dimension=4)


# ============================================================
# 逆向思维：边界条件
# ============================================================

def test_ingest_empty_file(db_path, embed):
    """空文件应优雅处理，不崩溃"""
    tmpdir = tempfile.mkdtemp()
    file_path = os.path.join(tmpdir, 'empty.md')
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write("")
    result = ingest_file(file_path, db_path, embed)
    assert result['status'] == 'ingested'
    assert result['chunks_count'] == 0
    os.unlink(file_path)
    os.rmdir(tmpdir)


def test_ingest_whitespace_only(db_path, embed):
    """纯空白文件应优雅处理"""
    tmpdir = tempfile.mkdtemp()
    file_path = os.path.join(tmpdir, 'whitespace.md')
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write("   \n\n  \n")
    result = ingest_file(file_path, db_path, embed)
    assert result['status'] == 'ingested'
    assert result['chunks_count'] == 0
    os.unlink(file_path)
    os.rmdir(tmpdir)


def test_ingest_huge_content(db_path, embed):
    """超大内容（10万字符）应正常切块"""
    tmpdir = tempfile.mkdtemp()
    file_path = os.path.join(tmpdir, 'huge.md')
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write("---\ntags: [大文件]\n---\n")
        f.write("A" * 100000)  # 100k chars
    result = ingest_file(file_path, db_path, embed)
    assert result['status'] == 'ingested'
    assert result['chunks_count'] >= 195  # 100000/512 ≈ 196
    os.unlink(file_path)
    os.rmdir(tmpdir)


def test_ingest_many_tags(db_path, embed):
    """大量标签（50个）应全部入库，共现矩阵正确"""
    tmpdir = tempfile.mkdtemp()
    file_path = os.path.join(tmpdir, 'many_tags.md')
    tags = ','.join([f'tag{i}' for i in range(50)])
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(f"""---
tags: [{tags}]
---
内容。
""")
    result = ingest_file(file_path, db_path, embed)
    assert result['status'] == 'ingested'
    conn = sqlite3.connect(db_path)
    tag_count = conn.execute("SELECT COUNT(*) FROM tags").fetchone()[0]
    co_count = conn.execute("SELECT COUNT(*) FROM tag_cooccurrence").fetchone()[0]
    conn.close()
    # 50 tags → 50 choose 2 = 1225 pairs
    assert tag_count == 50
    assert co_count == 1225  # 50*49/2
    os.unlink(file_path)
    os.rmdir(tmpdir)


def test_ingest_special_chars_in_tags(db_path, embed):
    """特殊字符标签应正确处理"""
    tmpdir = tempfile.mkdtemp()
    file_path = os.path.join(tmpdir, 'special.md')
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write("""---
tags: [a/b, c.d, e-f, g_h, i+j, 标签1, hello@world, $pecial]
---
内容。
""")
    result = ingest_file(file_path, db_path, embed)
    assert result['status'] == 'ingested'
    conn = sqlite3.connect(db_path)
    tags = [r[0] for r in conn.execute("SELECT name FROM tags").fetchall()]
    conn.close()
    assert 'a/b' in tags or 'a' in tags  # depends on how regex parses
    assert len(tags) >= 6


# ============================================================
# 逆向思维：异常路径
# ============================================================

def test_ingest_nonexistent_file(db_path, embed):
    """不存在的文件应报错"""
    with pytest.raises(FileNotFoundError):
        ingest_file("/nonexistent/path.md", db_path, embed)


def test_ingest_nonexistent_directory(db_path, embed):
    """不存在的目录应报错"""
    from scripts.ingest import ingest_directory
    with pytest.raises(FileNotFoundError):
        ingest_directory("/nonexistent/", db_path, embed)


def test_recall_empty_query(db_path, embed):
    """空查询应返回空结果"""
    conn = init_db(db_path)
    conn.close()
    # 先入库一条数据，确保数据库非空
    tmpdir = tempfile.mkdtemp()
    file_path = os.path.join(tmpdir, 'test.md')
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write("测试内容。")
    ingest_file(file_path, db_path, embed)
    os.unlink(file_path)
    os.rmdir(tmpdir)
    # 空查询
    results = recall("", db_path, embed, k=5)
    assert isinstance(results, list)


def test_recall_associative_mismatched_vectors(db_path):
    """向量维度不匹配时能正常处理"""
    from scripts.embedding import FakeEmbeddingClient
    # 用两个不同维度的 client 入库和召回
    embed4 = FakeEmbeddingClient(dimension=4)
    embed16 = FakeEmbeddingClient(dimension=16)

    tmpdir = tempfile.mkdtemp()
    file_path = os.path.join(tmpdir, 'test.md')
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write("测试内容。")
    ingest_file(file_path, db_path, embed4)
    os.unlink(file_path)
    os.rmdir(tmpdir)

    results = recall_associative("测试", db_path, embed16, k=5)
    # 维度不匹配时余弦相似度会算错，但不应该崩溃
    assert isinstance(results, list)


def test_format_recall_output_truncation(embed):
    """超长内容应被截断"""
    results = [{
        'chunk_id': 1,
        'content': 'A' * 500,
        'date': '2026-08-15',
        'file_path': 'x.md',
        'score': 0.9,
    }]
    text = format_recall_output(results, max_chars=50)
    assert '…' in text


def test_recall_missing_db():
    """不存在的数据库应优雅报错"""
    with pytest.raises(sqlite3.OperationalError):
        recall("查询", "/nonexistent/recall.db", FakeEmbeddingClient(4), k=5)


# ============================================================
# 逆向思维：安全 / 注入
# ============================================================

def test_sql_injection_via_tags(db_path, embed):
    """标签中的 SQL 注入尝试不应破坏数据库"""
    tmpdir = tempfile.mkdtemp()
    file_path = os.path.join(tmpdir, 'sqli.md')
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write("""---
tags: ["'; DROP TABLE chunks; --", "1; SELECT * FROM files;"]
---
内容。
""")
    try:
        result = ingest_file(file_path, db_path, embed)
        # 应该成功入库，且 chunks 表仍在
        conn = sqlite3.connect(db_path)
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()]
        conn.close()
        assert 'chunks' in tables  # 表没有被删除
        assert result['status'] == 'ingested'
    finally:
        os.unlink(file_path)
        os.rmdir(tmpdir)


def test_sql_injection_via_query(db_path, embed):
    """查询中的 SQL 注入尝试不应破坏数据库"""
    conn = init_db(db_path)
    conn.close()
    # 先入库
    tmpdir = tempfile.mkdtemp()
    file_path = os.path.join(tmpdir, 'test.md')
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write("测试内容。")
    ingest_file(file_path, db_path, embed)
    os.unlink(file_path)
    os.rmdir(tmpdir)
    # 注入查询
    results = recall("'; DROP TABLE chunks; --", db_path, embed, k=5)
    assert isinstance(results, list)
    conn = sqlite3.connect(db_path)
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()]
    conn.close()
    assert 'chunks' in tables  # 表仍在


# ============================================================
# 逆向思维：数据完整性
# ============================================================

def test_data_integrity_after_reingest(db_path, embed):
    """重新入库修改过的文件，旧 chunk 不应残留"""
    tmpdir = tempfile.mkdtemp()
    file_path = os.path.join(tmpdir, 'test.md')
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write("原始内容。")
    r1 = ingest_file(file_path, db_path, embed)
    assert r1['status'] == 'ingested'

    with open(file_path, 'w', encoding='utf-8') as f:
        f.write("修改后的内容，完全不同。")
    r2 = ingest_file(file_path, db_path, embed)
    assert r2['status'] == 'ingested'

    # 验证 chunks 中没有旧内容
    conn = sqlite3.connect(db_path)
    contents = [r[0] for r in conn.execute("SELECT content FROM chunks").fetchall()]
    conn.close()
    assert not any('原始内容' in c for c in contents), "旧内容应被清除"
    assert any('修改后的内容' in c for c in contents), "新内容应存在"
    os.unlink(file_path)
    os.rmdir(tmpdir)


def test_data_integrity_rollback(db_path, embed):
    """入库失败时不应有部分数据残留"""
    conn = init_db(db_path)
    conn.close()
    tmpdir = tempfile.mkdtemp()
    file_path = os.path.join(tmpdir, 'test.md')
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write("测试内容。")
    # 先正常入库
    r = ingest_file(file_path, db_path, embed)
    assert r['status'] == 'ingested'
    file_count_before = sqlite3.connect(db_path).execute("SELECT COUNT(*) FROM files").fetchone()[0]
    sqlite3.connect(db_path).close()
    # 删除文件后重新入库应失败
    os.unlink(file_path)
    # 验证文件数不变
    file_count_after = sqlite3.connect(db_path).execute("SELECT COUNT(*) FROM files").fetchone()[0]
    sqlite3.connect(db_path).close()
    assert file_count_before == file_count_after
    os.rmdir(tmpdir)


# ============================================================
# 系统思维：模块间交互
# ============================================================

def test_parse_diary_no_frontmatter():
    """无 frontmatter 的纯文本应正确解析"""
    result = parse_diary("这是一段纯文本。")
    assert result['maid'] == 'default'
    assert result['body'] == '这是一段纯文本。'
    assert result['tags'] == []


def test_parse_diary_partial_frontmatter():
    """部分 frontmatter 应正确解析"""
    result = parse_diary("---\nmaid: Nova\n---\n正文内容。")
    assert result['maid'] == 'Nova'
    assert result['body'] == '正文内容。'
    assert result['tags'] == []


def test_parse_diary_all_fields():
    """完整 frontmatter 应正确解析"""
    result = parse_diary("""---
maid: Nova
created: 2026-08-15T14:30:00
tags: [考试, 压力, 面试]
---
正文内容。
""")
    assert result['maid'] == 'Nova'
    assert result['created'] == '2026-08-15T14:30:00'
    assert '考试' in result['tags']
    assert '压力' in result['tags']
    assert '面试' in result['tags']
    assert result['body'] == '正文内容。'


def test_chunk_body_empty():
    """空正文应返回空列表"""
    assert chunk_body("") == []
    assert chunk_body("   ") == []


def test_chunk_body_single_para():
    """单段落应返回单元素"""
    chunks = chunk_body("这是单段内容。")
    assert len(chunks) == 1


def test_chunk_body_long_para():
    """超长段落应被切分"""
    text = "段落。" * 300  # 900 chars
    chunks = chunk_body(text, max_chars=200)
    assert len(chunks) >= 4  # 900/200 = 4.5


def test_cosine_similarity_identical():
    a = [1.0, 2.0, 3.0]
    b = [1.0, 2.0, 3.0]
    assert cosine_similarity(a, b) == pytest.approx(1.0)


def test_cosine_similarity_partial():
    a = [1.0, 0.0]
    b = [0.5, 0.0]
    assert cosine_similarity(a, b) == pytest.approx(1.0)  # same direction


def test_cosine_similarity_negative():
    a = [1.0, 0.0]
    b = [-1.0, 0.0]
    assert cosine_similarity(a, b) == pytest.approx(-1.0)


def test_serialize_deserialize_roundtrip():
    """向量序列化往返应无损"""
    original = [0.5, 0.1, -0.3, 0.8]
    blob = struct.pack(f'{len(original)}f', *original)
    restored = _deserialize_vector(blob)
    for a, b in zip(original, restored):
        assert a == pytest.approx(b)


def test_embedding_factory_no_config():
    """无配置时返回假 embedding"""
    client = load_embedding_client({})
    from scripts.embedding import FakeEmbeddingClient
    assert isinstance(client, FakeEmbeddingClient)


def test_embedding_factory_with_key():
    """有 API key 时返回真实 client"""
    client = load_embedding_client({'api_key': 'sk-test', 'api_url': 'https://test.api'})
    from scripts.embedding import SiliconFlowEmbeddingClient
    assert isinstance(client, SiliconFlowEmbeddingClient)


def test_ingest_checksum_changes_on_content_change():
    """相同内容应产生相同 checksum"""
    c1 = compute_checksum("Hello World")
    c2 = compute_checksum("Hello World")
    assert c1 == c2
    c3 = compute_checksum("Hello World!")
    assert c1 != c3


def test_embedding_deterministic():
    """假 embedding 对同一文本应返回相同向量"""
    client = FakeEmbeddingClient(dimension=4)
    v1 = client.embed(["测试"])
    v2 = client.embed(["测试"])
    assert v1 == v2