"""Regression tests for auto_recall routing fallback (泛化查询不跨库泄露).

回归场景：`--query "我有点紧张，怕搞砸" --auto` 被路由到 mira（社交恋爱管家）而非 default，
返回不相关的私密记忆。修复：非 default agent 需与查询有词面锚定
（description + keywords 共享字符 ≥ ROUTE_ANCHOR_MIN_SHARED）才算可信候选；
泛化/情绪化查询（无领域词）回落到 default，并标记 ambiguous。
"""
import json
import os
import tempfile
import pytest

from scripts.embedding import SemanticFakeEmbeddingClient
from scripts.ingest import ingest_file
from scripts.recall import auto_recall, ROUTE_ANCHOR_MIN_SHARED
from scripts.config import get_agent_dir, get_db_path, get_dailynote_path, ensure_agent_dir
import scripts.config as cfg


@pytest.fixture
def embed():
    # 语义伪向量：query 与描述共享字符/二元组时余弦才高，跨话题 ≈ 0
    return SemanticFakeEmbeddingClient()


def _set_base(tmpdir):
    old = cfg.BASE_DIR
    cfg.BASE_DIR = tmpdir
    return old


def _make_agent(name, description, keywords=None, diary=None):
    ensure_agent_dir(name)
    meta = {'description': description}
    if keywords:
        meta['keywords'] = keywords
    with open(os.path.join(get_agent_dir(name), 'agent.json'), 'w', encoding='utf-8') as f:
        json.dump(meta, f, ensure_ascii=False)
    if diary:
        fp = os.path.join(get_dailynote_path(name), 'd.md')
        with open(fp, 'w', encoding='utf-8') as f:
            f.write(f"---\nmaid: {name}\ntags: [测试]\n---\n{diary}")
        ingest_file(fp, get_db_path(name), embed)
        os.unlink(fp)


def test_generic_query_falls_back_to_default(embed):
    """无领域词的泛化查询：即使私人 agent 描述向量相似度可能偏高也不该被截胡。"""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        old = _set_base(tmpdir)
        try:
            _make_agent('mira', '社交恋爱管家情感陪伴', diary='恋爱约会安排')
            _make_agent('default', '用户日常记忆与心情记录', diary='用户自己的日常')

            result = auto_recall('我有点紧张怕搞砸', embed, k=5)
            assert result['name'] == 'default'
            assert result['ambiguous'] is True
            # 绝不带出 mira 的私密记忆
            assert all('恋爱' not in r['content'] for r in result['results'])
        finally:
            cfg.BASE_DIR = old


def test_lexical_anchor_routes_to_agent(embed):
    """查询含领域词且词面锚定达标 → 路由到对应 agent，ambiguous=False。"""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        old = _set_base(tmpdir)
        try:
            _make_agent('mira', '社交恋爱管家情感陪伴', keywords=['紧张', '压力'],
                        diary='用户紧张时的恋爱建议')
            _make_agent('default', '用户日常记忆与心情记录', diary='用户的日常')

            result = auto_recall('我有点紧张怕搞砸', embed, k=5)
            assert result['name'] == 'mira'
            assert result['ambiguous'] is False
            assert len(result['results']) > 0
        finally:
            cfg.BASE_DIR = old


def test_keywords_alone_can_anchor(embed):
    """描述无共享词、仅 keywords 提供锚定也能路由（领域词独立于描述）。"""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        old = _set_base(tmpdir)
        try:
            _make_agent('mira', '社交恋爱管家', keywords=['紧张'], diary='紧张时怎么办')
            _make_agent('default', '用户日常', diary='用户日常')

            result = auto_recall('我有点紧张', embed, k=5)
            assert result['name'] == 'mira'
            assert result['ambiguous'] is False
        finally:
            cfg.BASE_DIR = old


def test_single_char_overlap_not_enough(embed):
    """共享字符不足阈值（< ROUTE_ANCHOR_MIN_SHARED）→ 不锚定 → 回退 default。"""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        old = _set_base(tmpdir)
        try:
            _make_agent('mira', '紧衣缩食小管家', diary='理财日记')
            _make_agent('default', '用户日常记忆', diary='用户日常')

            result = auto_recall('我有点紧张怕搞砸', embed, k=5)
            assert result['name'] == 'default'
            assert result['ambiguous'] is True
        finally:
            cfg.BASE_DIR = old


def test_anchor_threshold_matches_constant():
    assert ROUTE_ANCHOR_MIN_SHARED == 2


def test_list_agents_exposes_keywords():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        old = _set_base(tmpdir)
        try:
            _make_agent('mira', '社交恋爱管家', keywords=['紧张', '压力'])
            from scripts.config import list_agents
            mira = [a for a in list_agents() if a['name'] == 'mira'][0]
            assert mira['keywords'] == ['紧张', '压力']
        finally:
            cfg.BASE_DIR = old
