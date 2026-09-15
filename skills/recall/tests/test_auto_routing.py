"""Tests for semantic auto-routing (语义自动路由)."""
import os
import json
import tempfile
import pytest

from scripts.embedding import FakeEmbeddingClient
from scripts.schema import init_db
from scripts.ingest import ingest_file
from scripts.recall import auto_recall
from scripts.config import list_agents, get_db_path, get_dailynote_path, ensure_agent_dir
import scripts.config as cfg


@pytest.fixture
def embed():
    return FakeEmbeddingClient(dimension=64)  # higher dim for better discrimination


def _set_base(tmpdir):
    old = cfg.BASE_DIR
    cfg.BASE_DIR = tmpdir
    return old


def test_list_agents_with_description():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        old = _set_base(tmpdir)
        try:
            ensure_agent_dir('助手')
            d = cfg.get_agent_dir('助手')
            with open(os.path.join(d, 'agent.json'), 'w', encoding='utf-8') as f:
                json.dump({'description': '帮助学习'}, f)
            agents = list_agents()
            assert len(agents) >= 1
            assert any('帮助' in a['description'] for a in agents)
        finally:
            cfg.BASE_DIR = old


def test_list_agents_fallback_to_name():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        old = _set_base(tmpdir)
        try:
            ensure_agent_dir('Nova')
            init_db(get_db_path('Nova'))
            agents = list_agents()
            nova = [a for a in agents if a['name'] == 'Nova']
            assert len(nova) == 1
            assert nova[0]['description'] == 'Nova'
        finally:
            cfg.BASE_DIR = old


def test_auto_recall_selects_best_agent():
    """auto_recall 应选语义+词面锚定都命中的 agent（而非无锚定的高相似噪声）。"""
    from scripts.embedding import SemanticFakeEmbeddingClient
    embed = SemanticFakeEmbeddingClient()
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        old = _set_base(tmpdir)
        try:
            ensure_agent_dir('default')
            d = cfg.get_agent_dir('default')
            with open(os.path.join(d, 'agent.json'), 'w', encoding='utf-8') as f:
                json.dump({'description': '用户日常记忆与心情记录'}, f)

            ensure_agent_dir('助教')
            d = cfg.get_agent_dir('助教')
            with open(os.path.join(d, 'agent.json'), 'w', encoding='utf-8') as f:
                json.dump({'description': '辅导学习编程帮助做题解答问题',
                           'keywords': ['代码', '编程']}, f)
            fp = os.path.join(get_dailynote_path('助教'), 'd.md')
            with open(fp, 'w', encoding='utf-8') as f:
                f.write("---\nmaid: t\ntags: [编程]\n---\nPython学习笔记")
            ingest_file(fp, get_db_path('助教'), embed)
            os.unlink(fp)

            ensure_agent_dir('导购')
            d = cfg.get_agent_dir('导购')
            with open(os.path.join(d, 'agent.json'), 'w', encoding='utf-8') as f:
                json.dump({'description': '推荐商品介绍促销活动购物折扣'}, f)
            fp = os.path.join(get_dailynote_path('导购'), 'd.md')
            with open(fp, 'w', encoding='utf-8') as f:
                f.write("---\nmaid: t\ntags: [购物]\n---\n商品推荐")
            ingest_file(fp, get_db_path('导购'), embed)
            os.unlink(fp)

            result = auto_recall("帮我看看这段Python代码怎么写", embed, k=5)
            # 助教有 代码 锚定且语义命中 → 应选中；导购无锚定不被信任
            assert result['name'] == '助教'
            assert result['score'] > 0
            assert result['ambiguous'] is False
        finally:
            cfg.BASE_DIR = old


def test_auto_recall_no_agents(embed):
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        old = _set_base(tmpdir)
        try:
            result = auto_recall("测试", embed, k=5)
            assert result['name'] is None
            assert result['results'] == []
        finally:
            cfg.BASE_DIR = old


def test_auto_recall_empty_db(embed):
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        old = _set_base(tmpdir)
        try:
            ensure_agent_dir('测试Agent')
            d = cfg.get_agent_dir('测试Agent')
            with open(os.path.join(d, 'agent.json'), 'w', encoding='utf-8') as f:
                json.dump({'description': '测试用agent'}, f)
            result = auto_recall("测试", embed, k=5)
            assert result['name'] == '测试Agent'
            assert result['results'] == []
        finally:
            cfg.BASE_DIR = old


def test_auto_recall_returns_agent_info(embed):
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        old = _set_base(tmpdir)
        try:
            ensure_agent_dir('Nova')
            d = cfg.get_agent_dir('Nova')
            with open(os.path.join(d, 'agent.json'), 'w', encoding='utf-8') as f:
                json.dump({'description': '辅导学习编程帮助做题'}, f)
            result = auto_recall("学习", embed, k=5)
            assert 'name' in result
            assert 'description' in result
            assert 'score' in result
            assert result['score'] > 0
        finally:
            cfg.BASE_DIR = old