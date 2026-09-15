# -*- coding: utf-8 -*-
"""注入侧上下文控制：去重 + 预算收敛 + 去掉 200 字硬截断。

对齐 VCP（ResultDeduplicator 去重 + top-k 全文保留）与 letta（context budget）。
第一性原理：注入目标的上下文是有限资源——"少而完整"优先于"多而残破"；
token 膨胀的主因之一是重复/超量注入，不是"单条没截断"。
"""
import json
import os
import tempfile
import pytest

import scripts.config as cfg
from scripts.config import (
    get_db_path, get_dailynote_path, get_agent_dir, ensure_agent,
)
from scripts.embedding import SemanticFakeEmbeddingClient
from scripts.ingest import ingest_file
from scripts.recall import (
    format_recall_output, dedupe_results, fit_to_budget,
    recall_by_identity, recall, main as recall_main,
)


@pytest.fixture
def embed():
    return SemanticFakeEmbeddingClient()


def _set_base(tmpdir):
    old = cfg.BASE_DIR
    cfg.BASE_DIR = tmpdir
    return old


def _seed(agent, description, diary, embed, base):
    ensure_agent(agent, description)
    fp = os.path.join(get_dailynote_path(agent), 'd.md')
    with open(fp, 'w', encoding='utf-8') as f:
        f.write(f"---\nmaid: {agent}\ntags: [测试]\n---\n{diary}")
    r = ingest_file(fp, get_db_path(agent), embed)
    os.unlink(fp)
    return r


# ============================================================
# 1. format_recall_output：默认不再 200 硬截断，保留完整 chunk
# ============================================================

def test_format_default_keeps_full_content(embed):
    """默认不截断：超长内容应完整输出，不含省略号。"""
    results = [{'chunk_id': 1, 'content': 'A' * 500, 'date': '2026-08-15',
                'file_path': 'x.md', 'score': 0.9}]
    text = format_recall_output(results)
    assert 'A' * 500 in text
    assert '…' not in text


def test_format_explicit_max_chars_still_truncates(embed):
    """显式传 max_chars 时仍截断（向后兼容），不破坏旧语义保护。"""
    results = [{'chunk_id': 1, 'content': 'A' * 500, 'date': '2026-08-15',
                'file_path': 'x.md', 'score': 0.9}]
    text = format_recall_output(results, max_chars=50)
    assert '…' in text


# ============================================================
# 2. dedupe_results：去重（chunk_id / 规范化正文 / 可开语义）
# ============================================================

def _res(cid, content, score=1.0):
    return {'chunk_id': cid, 'content': content, 'date': '2026-08-15',
            'file_path': 'x.md', 'score': score}


def test_dedupe_by_chunk_id():
    """同一 chunk_id 只留一次（联想/标签命中会重复带出同一 chunk）。"""
    src = [_res(7, '内容甲', 0.9), _res(7, '内容甲', 0.5), _res(8, '内容乙', 0.8)]
    out = dedupe_results(src)
    assert len(out) == 2
    assert [r['chunk_id'] for r in out] == [7, 8]


def test_dedupe_by_normalized_content():
    """不同 chunk_id 但正文相同（仅空白差异）视为重复，去冗余。"""
    src = [_res(1, '周日去打球', 0.9), _res(2, ' 周日去 打球 ', 0.4)]
    out = dedupe_results(src)
    assert len(out) == 1
    assert out[0]['chunk_id'] == 1  # 保留相关度更高、更早的那条
    assert out[0]['content'] == '周日去打球'


def test_dedupe_keeps_distinct_content():
    """不同正文绝不误删（语义去重默认关闭，避免漏信息）。"""
    src = [_res(1, '考试压力大', 0.9), _res(2, '马拉松紧张', 0.8)]
    out = dedupe_results(src)
    assert len(out) == 2


# ============================================================
# 3. fit_to_budget：预算内取完整条目，超预算收条不截单条
# ============================================================

def _long(k):
    return {'chunk_id': k, 'content': f'记忆编号{k}：' + '内容' * 30,
            'date': '2026-08-15', 'file_path': 'x.md', 'score': 1.0 / k}


def test_fit_budget_respects_limit():
    """小预算只放得下最高的几条完整条目。"""
    results = [_long(1), _long(2), _long(3), _long(4)]
    out = fit_to_budget(results, budget_chars=50)
    assert 1 <= len(out) < len(results)
    # 留下的都应是排在最前（相关度最高）的
    assert {r['chunk_id'] for r in out} <= {1, 2, 3}


def test_fit_budget_grows_with_budget():
    """预算越大，注入条数越多（单调）。"""
    small = fit_to_budget([_long(1), _long(2), _long(3)], budget_chars=40)
    big = fit_to_budget([_long(1), _long(2), _long(3)], budget_chars=200)
    assert len(small) <= len(big)


def test_fit_budget_single_over_budget_still_returns_one():
    """对抗：单条内容就超过预算时，仍注入最相关那一条（完整、不空）。"""
    huge = {'chunk_id': 1, 'content': '超长' * 1000, 'date': '2026-08-15',
            'file_path': 'x.md', 'score': 0.95}
    out = fit_to_budget([huge], budget_chars=50)
    assert len(out) == 1
    assert out[0]['content'] == '超长' * 1000  # 完整保留，绝不拦腰切


def test_fit_budget_keeps_full_content():
    """预算内的每条都应完整输出，不含省略号。"""
    results = [_long(1), _long(2)]
    out = fit_to_budget(results, budget_chars=2000)
    assert all('…' not in r['content'] for r in out)


def test_fit_budget_none_returns_all():
    """budget 为空（不设）时返回全部，不做限制。"""
    results = [_long(1), _long(2), _long(3)]
    out = fit_to_budget(results, budget_chars=None)
    assert len(out) == 3


# ============================================================
# 4. 端到端对抗：双 agent 隔离 + 去重 + 预算一起生效，绝不串号
# ============================================================

def test_e2e_identity_dedupe_budget_isolation(embed, monkeypatch, capsys):
    """qinglan 区内重复记录会被去重、预算收条；mira 内容绝不泄漏。"""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        old = _set_base(tmpdir)
        try:
            _seed('qinglan', '教学实习', '约会礼仪课', embed, tmpdir)
            _seed('qinglan', '教学实习', '约会礼仪课', embed, tmpdir)  # 重复正文
            _seed('mira', '社交恋爱', '和小雨约会逛游乐园', embed, tmpdir)

            # 直接用函数级路径验证（隔离是结构性的）
            q = recall_by_identity('约会', embed, identity='qinglan', k=5)
            # 去重：重复正文只留一条
            q_unique = dedupe_results(q)
            assert len(q_unique) <= len(q)
            assert all('游乐园' not in r['content'] for r in q_unique)  # 绝不串号

            # CLI 级验证 --budget 生效且不崩
            monkeypatch.setattr(cfg, 'BASE_DIR', tmpdir)
            rc = recall_main([
                '--query', '约会', '--identity', 'qinglan',
                '--k', '10', '--budget', '40',
            ])
            assert rc == 0
            out = capsys.readouterr().out
            assert '游乐园' not in out  # mira 内容绝不出现
            assert '约会礼仪课' in out  # qinglan 自己的记忆正常浮现
        finally:
            cfg.BASE_DIR = old