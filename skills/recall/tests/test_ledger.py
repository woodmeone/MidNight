# -*- coding: utf-8 -*-
"""票1：检索留痕底座（retrieval_ledger.jsonl）。

第一性：留痕不是日志洁癖，是把"这一轮走没走算法"从**自述**变成**事实**。
所以它必须满足三条硬性质：
1. 旁路——写失败绝不拖累检索（只读盘/磁盘满下检索照常返回）；
2. 隔离——按 agent 分文件，A 的留痕 B 看不见；
3. 纯净——只写 CLI 入口，库函数（recall_associative / prep_for_reply）不许碰磁盘。
"""
import json
import os

import pytest

import scripts.config as cfg
from scripts.config import ensure_agent, get_agent_dir
from scripts.embedding import SemanticFakeEmbeddingClient
from scripts.ingest import ingest_file
from scripts.ledger import append_entry, ledger_path, read_entries
from scripts.recall import recall_associative, main as recall_main
from scripts.prep import prep_for_reply


@pytest.fixture
def base(monkeypatch):
    import tempfile
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        monkeypatch.setattr(cfg, 'BASE_DIR', tmp)
        cfg.ensure_agent('probe')
        yield tmp


def _seed(agent, content, embed):
    fp = os.path.join(get_agent_dir(agent), 'seed.md')
    with open(fp, 'w', encoding='utf-8') as f:
        f.write(f"---\nmaid: {agent}\ncreated: 2026-09-22T10:00:00\n"
                f"tags: [教学]\n---\n{content}\n")
    ingest_file(fp, os.path.join(get_agent_dir(agent), 'recall.db'), embed)
    os.unlink(fp)


# ============================================================
# 1. 写入契约
# ============================================================

def test_append_writes_one_jsonl_line_with_contract_fields(base):
    ok = append_entry('associative', '当老师 教师 教学',
                      results=[{'chunk_id': 12}, {'chunk_id': 15}], agent='probe',
                      extra={'k': 10})
    assert ok is True
    path = ledger_path('probe')
    assert path.endswith('retrieval_ledger.jsonl')
    assert os.path.dirname(path) == get_agent_dir('probe')

    lines = [l for l in open(path, encoding='utf-8').read().splitlines() if l.strip()]
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry['channel'] == 'associative'
    assert entry['agent'] == 'probe'
    assert entry['query'] == '当老师 教师 教学'
    assert entry['hits'] == 2
    assert entry['chunk_ids'] == [12, 15]
    assert entry['extra'] == {'k': 10}
    assert entry['ts']  # ISO 时间戳，格式交给 append 决定，只要求非空


def test_append_is_additive_not_overwriting(base):
    append_entry('timeline', 'q1', results=[{'chunk_id': 1}], agent='probe')
    append_entry('literal', 'q2', results=[], agent='probe')
    entries = read_entries('probe')
    assert [e['channel'] for e in entries] == ['timeline', 'literal']


# ============================================================
# 2. 读取契约（坏行容忍、缺失容忍、limit 取最近）
# ============================================================

def test_read_entries_returns_tail_with_limit(base):
    for i in range(5):
        append_entry('associative', f'q{i}', results=[{'chunk_id': i}], agent='probe')
    tail = read_entries('probe', limit=2)
    assert [e['query'] for e in tail] == ['q3', 'q4']


def test_read_entries_skips_corrupt_lines(base):
    append_entry('associative', 'good', results=[], agent='probe')
    path = ledger_path('probe')
    with open(path, 'a', encoding='utf-8') as f:
        f.write('{not json at all\n')
        f.write('\n')
    append_entry('literal', 'also good', results=[], agent='probe')
    entries = read_entries('probe')
    assert [e['query'] for e in entries] == ['good', 'also good']


def test_read_entries_missing_file_returns_empty(base):
    assert read_entries('probe') == []


# ============================================================
# 3. 隔离：A 的留痕 B 看不见
# ============================================================

def test_ledger_is_per_agent(base):
    cfg.ensure_agent('other')
    append_entry('associative', 'A 的秘密', results=[], agent='probe')
    assert read_entries('other') == []
    assert ledger_path('probe') != ledger_path('other')


# ============================================================
# 4. 旁路性质：写失败必须吞掉
# ============================================================

def test_append_failure_is_swallowed(base, monkeypatch):
    # 让 ledger 路径落在一个"已存在的文件"下面 → open() 必然失败
    blocker = os.path.join(get_agent_dir('probe'), 'blocker')
    with open(blocker, 'w', encoding='utf-8') as f:
        f.write('x')
    monkeypatch.setattr('scripts.ledger.ledger_path',
                        lambda agent=None: os.path.join(blocker, 'retrieval_ledger.jsonl'))
    assert append_entry('associative', 'q', results=[], agent='probe') is False


def test_retrieval_survives_ledger_failure(base, monkeypatch):
    import scripts.recall as rc
    _seed('probe', '带教老师刘晓平，专业课权威', SemanticFakeEmbeddingClient())

    def _boom(*a, **k):
        raise OSError('disk full')

    monkeypatch.setattr(rc, 'ledger_append', _boom)
    assert recall_main(['--query', '刘晓平', '--identity', 'probe']) == 0


# ============================================================
# 5. 纯净：库函数不写盘
# ============================================================

def test_library_functions_do_not_write_ledger(base):
    embed = SemanticFakeEmbeddingClient()
    _seed('probe', '备课模块 学情分析', embed)
    db = os.path.join(get_agent_dir('probe'), 'recall.db')

    recall_associative('备课', db, embed, k=3)
    prep_for_reply('还记得吗', db_path=db, embedding_client=embed, force=True)

    assert not os.path.exists(ledger_path('probe'))


# ============================================================
# 6. CLI 接线 + --audit
# ============================================================

def test_cli_associative_writes_ledger(base, capsys):
    embed = SemanticFakeEmbeddingClient()
    _seed('probe', '带教老师刘晓平，专业课权威', embed)

    rc = recall_main(['--query', '刘晓平', '--identity', 'probe'])
    assert rc == 0

    entries = read_entries('probe')
    assert len(entries) == 1
    entry = entries[0]
    assert entry['channel'] == 'associative'
    assert entry['agent'] == 'probe'
    assert entry['query'] == '刘晓平'
    assert entry['hits'] >= 1
    assert all(isinstance(i, int) for i in entry['chunk_ids'])


def test_cli_audit_prints_ledger(base, capsys):
    append_entry('associative', '当老师 教师', results=[{'chunk_id': 3}], agent='probe')
    rc = recall_main(['--audit', '5', '--identity', 'probe'])
    assert rc == 0
    out = capsys.readouterr().out
    assert 'associative' in out
    assert '当老师 教师' in out


def test_cli_audit_without_ledger_does_not_crash(base, capsys):
    rc = recall_main(['--audit', '--identity', 'probe'])
    assert rc == 0
    out = capsys.readouterr().out
    assert '暂无' in out


# ============================================================
# 7. prep.py 也必须留痕（它是 SKILL.md 推荐的默认入口）
# ============================================================

def test_cli_prep_writes_ledger(base, capsys):
    import scripts.prep as prep_mod
    embed = SemanticFakeEmbeddingClient()
    _seed('probe', '带教老师刘晓平，专业课权威', embed)

    rc = prep_mod.main(['--message', '还记得刘晓平吗', '--identity', 'probe',
                        '--force', '--k', '3'])
    assert rc == 0

    entries = read_entries('probe')
    assert len(entries) == 1
    assert entries[0]['channel'] == 'associative'
    assert entries[0]['agent'] == 'probe'
    assert entries[0]['extra']['entry'] == 'prep'


def test_cli_prep_gated_out_does_not_write_ledger(base, capsys):
    """门控挡下的短寒暄不是一次检索，不该污染审计。"""
    import scripts.prep as prep_mod
    _seed('probe', '随便一条记忆', SemanticFakeEmbeddingClient())

    rc = prep_mod.main(['--message', '嗯', '--identity', 'probe'])
    assert rc == 0
    assert read_entries('probe') == []


def test_prep_ledger_failure_does_not_break_recall(base, monkeypatch, capsys):
    import scripts.prep as prep_mod
    embed = SemanticFakeEmbeddingClient()
    _seed('probe', '带教老师刘晓平，专业课权威', embed)

    def _boom(*a, **k):
        raise OSError('disk full')

    monkeypatch.setattr(prep_mod, 'ledger_append', _boom)
    assert prep_mod.main(['--message', '还记得刘晓平吗', '--identity', 'probe',
                          '--force']) == 0
    assert '刘晓平' in capsys.readouterr().out
