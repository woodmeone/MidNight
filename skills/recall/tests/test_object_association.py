"""T2: 对象规约（对象 = anchor tag）集成测试。

V2 口径（2026-09-02 定稿）：单 agent 单库；对象 = anchor tag。关于对象 X 的日记，
frontmatter tags 带对象名（如 `阿散`），不建独立库/子目录。

本测试证明"对象作为一等节点可被联想召回"：query 不含对象名（阿散），
仍通过话题 tag（马拉松/紧张）的共现边召回阿散对象日记，且不与另一个对象（乙）混淆。

用 SemanticFakeEmbeddingClient：字符重叠决定相似度，种子感应确定性。
"""
import os
import tempfile

import pytest

from scripts.embedding import SemanticFakeEmbeddingClient
from scripts.schema import init_db
from scripts.ingest import ingest_file
from scripts.recall import recall_associative


@pytest.fixture
def embed():
    return SemanticFakeEmbeddingClient()


@pytest.fixture
def object_db(embed):
    """唯一库：阿散（马拉松/紧张/雅思）与 乙（旅行/美食）两本对象记忆同库共存。"""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        db_path = os.path.join(tmpdir, 'recall.db')
        init_db(db_path)
        entries = [
            ("阿散 马拉松 紧张", "阿散说下月要跑马拉松，赛前有点紧张，还和雅思考试撞期。"),
            ("阿散 雅思", "阿散备考雅思，听力错题常因为紧张走神。"),
            ("乙 旅行 美食", "乙计划去京都旅行，想尝当地美食。"),
        ]
        for idx, (tags, content) in enumerate(entries):
            fp = os.path.join(tmpdir, f'd{idx}.md')
            with open(fp, 'w', encoding='utf-8') as f:
                f.write(f"---\nmaid: mira\ncreated: 2026-08-15T10:00:00\n"
                        f"tags: [{tags}]\n---\n{content}\n")
            ingest_file(fp, db_path, embed)
            os.unlink(fp)
        yield db_path


def test_object_recalled_via_topic_without_name(object_db, embed):
    """query 不含对象名「阿散」，查「跑马拉松 紧张」联想召回阿散对象日记"""
    results = recall_associative("跑马拉松 紧张", object_db, embed,
                                 k=5, tag_weight=0.5, decay=0.5, max_depth=2)
    assert results, "应有关联召回结果"
    contents = [r['content'] for r in results]
    assert any('马拉松' in c for c in contents), "话题标签应把阿散对象日记带出来"


def test_object_ranked_above_unrelated_person(object_db, embed):
    """软隔离：查阿散主题时，乙的日记不排在阿散前面"""
    results = recall_associative("跑马拉松 紧张", object_db, embed,
                                 k=5, tag_weight=0.5, decay=0.5, max_depth=2)
    ashan_idx = next((i for i, r in enumerate(results) if '马拉松' in r['content']), None)
    yi_idx = next((i for i, r in enumerate(results) if '京都' in r['content']), None)
    assert ashan_idx is not None, "阿散对象日记应被召回"
    assert ashan_idx < len(results)
    if yi_idx is not None:
        assert ashan_idx < yi_idx, "阿散主题不应被无关对象（乙）的内容排到前面"


def test_object_second_topic_recalls(object_db, embed):
    """换一个话题标签（雅思）同样能召回阿散对象日记"""
    results = recall_associative("雅思 紧张", object_db, embed,
                                 k=5, tag_weight=0.5, decay=0.5, max_depth=2)
    contents = [r['content'] for r in results]
    assert any('雅思' in c for c in contents), "另一话题标签也应带出阿散对象日记"
