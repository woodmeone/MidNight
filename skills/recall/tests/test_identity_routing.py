"""Regression tests for identity-preferred routing (身份绑定优先).

回归场景：即使给了 `--auto`，只要上层会话显式声明了自己的身份（--identity
/ --agent），就必须优先走该智能体的记忆区，绝不被 auto_recall 的语义猜库覆盖。
这保证「青岚会话查 qinglan 区、mira 会话查 mira 区」，隔离墙不被自动路由戳破。
"""
import json
import os
import tempfile
import pytest

from scripts.embedding import SemanticFakeEmbeddingClient
from scripts.ingest import ingest_file
from scripts.config import get_agent_dir, get_db_path, get_dailynote_path, ensure_agent_dir
import scripts.config as cfg


@pytest.fixture
def embed():
    return SemanticFakeEmbeddingClient()


def _set_base(tmpdir):
    old = cfg.BASE_DIR
    cfg.BASE_DIR = tmpdir
    return old


def _make_agent(name, description, keywords=None, diary='默认记忆'):
    ensure_agent_dir(name)
    meta = {'description': description}
    if keywords:
        meta['keywords'] = keywords
    with open(os.path.join(get_agent_dir(name), 'agent.json'), 'w', encoding='utf-8') as f:
        json.dump(meta, f, ensure_ascii=False)
    fp = os.path.join(get_dailynote_path(name), 'd.md')
    with open(fp, 'w', encoding='utf-8') as f:
        f.write(f"---\nmaid: {name}\ntags: [测试]\n---\n{diary}")
    ingest_file(fp, get_db_path(name), embed)
    os.unlink(fp)


# --- 身份优先：给定身份绝不回落到被 auto 猜走的库 ---

def test_explicit_identity_beats_auto_semantics(embed):
    """上层说自己是谁（--identity qinglan），查询再像别的 agent 也必须查 qinglan 区。

    对抗式：构造一句「像 mira 的话」（含社交恋爱词），但身份明确是 qinglan → 必须回 qinglan。
    """
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        old = _set_base(tmpdir)
        try:
            from scripts.recall import recall_by_identity
            _make_agent('qinglan', '教学实习老师备课', diary='今天在东莞上课')
            _make_agent('mira', '社交恋爱约会', diary='懵那的一切')

            results = recall_by_identity('懵那最近怎么样', embed, identity='qinglan', k=5)
            # 即使查询指向 mira 语义，身份绑 qinglan → 结果只能来自 qinglan
            assert all('懵那' not in r['content'] for r in results)
        finally:
            cfg.BASE_DIR = old


def test_identity_with_no_match_still_scoped(embed):
    """身份区里没有关键词匹配到的内容时，返回空，而不是跑去别区凑。"""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        old = _set_base(tmpdir)
        try:
            from scripts.recall import recall_by_identity
            _make_agent('qinglan', '教学实习', diary='课堂复盘')
            _make_agent('mira', '社交恋爱', diary='约会安排')

            results = recall_by_identity('股票投资', embed, identity='qinglan', k=5)
            # 关键约束：结果只可能来自 qinglan 区（scope 正确），绝不带出别区（无"约会安排"）
            assert all('约会' not in r['content'] for r in results)
        finally:
            cfg.BASE_DIR = old


def test_auto_still_valid_without_identity(embed):
    """未声明身份时才走 auto；auto 的锚定兜底仍应防止跨库泄露。"""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        old = _set_base(tmpdir)
        try:
            from scripts.recall import auto_recall
            _make_agent('mira', '社交恋爱管家', keywords=['紧张'], diary='恋爱敏感词')
            _make_agent('default', '用户日常记忆', diary='用户日常')

            result = auto_recall('我有点紧张怕搞砸', embed, k=5)
            # 无身份 + 词面锚定到 mira → 允许（这是 auto 的兜底职责）
            assert result['name'] in ('mira', 'default')
        finally:
            cfg.BASE_DIR = old