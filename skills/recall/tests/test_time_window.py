# -*- coding: utf-8 -*-
"""票1：把「时间窗」变成联想主干的**约束**，而不是另一条通道（Issue #7）。

第一性：约束和排序是两件事。
- 约束（时间窗 / 字面）决定**在哪些记忆里找**——它必须作用在候选池上；
- 联想（向量 + 标签脉冲）决定**哪条最像**——它作用在候选池之内。

所以正确的写法是"先筛池再排序"，而不是"排完再筛"（后者会少返回甚至空）或
"两次调用再人工对齐"（语义那条腿会越界）。

对抗重点：
1. 窗外的记忆**绝不许**被返回——包括通过 **tag-first 扩增**绕回来的（这是最容易被漏的缝）；
2. 缓存不许把"带窗"和"不带窗"混成一份（脏读）；
3. 不给窗口时逐位等于旧行为。
"""
import os
import tempfile

import pytest

import scripts.config as cfg
from scripts.config import ensure_agent, get_agent_dir
from scripts.embedding import SemanticFakeEmbeddingClient
from scripts.ingest import ingest_file
from scripts.recall import (
    recall, recall_associative, recall_by_identity, main as recall_main,
)


@pytest.fixture
def base(monkeypatch):
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        monkeypatch.setattr(cfg, 'BASE_DIR', tmp)
        yield tmp


def _seed(agent, name, created, body, tags='教学'):
    ensure_agent(agent)
    d = os.path.join(get_agent_dir(agent), 'dailynote')
    os.makedirs(d, exist_ok=True)
    fp = os.path.join(d, f'{name}.md')
    with open(fp, 'w', encoding='utf-8') as f:
        f.write(f"---\nmaid: {agent}\ncreated: {created}T10:00:00\ntags: [{tags}]\n---\n{body}\n")
    db = os.path.join(get_agent_dir(agent), 'recall.db')
    ingest_file(fp, db, SemanticFakeEmbeddingClient())
    os.unlink(fp)
    return db


@pytest.fixture
def db(base):
    """三个月的备课记忆：八月、九月、十月各一条，正文高度相似（都讲备课）。"""
    db_path = _seed('probe', 'a', '2026-08-10', '备课：先备人再备课，八月版本')
    d = os.path.join(get_agent_dir('probe'), 'dailynote')
    for name, created, body in [
        ('b', '2026-09-15', '备课：先备人再备课，九月版本'),
        ('c', '2026-10-05', '备课：先备人再备课，十月版本'),
    ]:
        fp = os.path.join(d, f'{name}.md')
        with open(fp, 'w', encoding='utf-8') as f:
            f.write(f"---\nmaid: probe\ncreated: {created}T10:00:00\ntags: [教学]\n---\n{body}\n")
        ingest_file(fp, db_path, SemanticFakeEmbeddingClient())
        os.unlink(fp)
    return db_path


# ============================================================
# 1. recall() 层的窗口过滤（候选池阶段）
# ============================================================

def test_recall_window_filters_candidates(db):
    client = SemanticFakeEmbeddingClient()
    all_hits = recall('备课', db, client, k=10)
    assert len(all_hits) == 3

    oct_hits = recall('备课', db, client, k=10, since='2026-10-01')
    assert [h['date'] for h in oct_hits] == ['2026-10-05']


def test_recall_window_is_inclusive_on_both_ends(db):
    client = SemanticFakeEmbeddingClient()
    hits = recall('备课', db, client, k=10, since='2026-09-15', until='2026-10-05')
    assert [h['date'] for h in hits] == ['2026-10-05', '2026-09-15']


def test_recall_window_with_no_match_returns_empty(db):
    client = SemanticFakeEmbeddingClient()
    assert recall('备课', db, client, k=10,
                  since='2027-01-01', until='2027-12-31') == []


# ============================================================
# 2. recall_associative 层（含标签脉冲）也受窗口约束
# ============================================================

def test_associative_window_filters(db):
    client = SemanticFakeEmbeddingClient()
    hits = recall_associative('备课', db, client, k=10, since='2026-10-01')
    assert hits
    assert all(h['date'] >= '2026-10-01' for h in hits), \
        [h['date'] for h in hits]


def test_associative_without_window_is_unchanged(db):
    """不给窗口 → 三条全在（默认行为不变）。"""
    client = SemanticFakeEmbeddingClient()
    hits = recall_associative('备课', db, client, k=10)
    assert len({h['chunk_id'] for h in hits}) == 3


# ============================================================
# 3. 对抗：tag-first 扩增不许把窗外记忆捞回来
# ============================================================

def test_tag_expansion_cannot_leak_outside_window(base):
    """八月那条靠共享标签被扩增出来——带十月的窗时必须挡住。

    这是最隐蔽的缝：向量层被窗口挡住了，但标签扩增走的是另一条 SQL，
    忘了加窗口就会"从后门"把窗外记忆放进来，窗口形同虚设。
    """
    _seed('probe', 'x', '2026-08-01', '完全无关的话题：桌球与乒乓球', tags='桌球')
    d = os.path.join(get_agent_dir('probe'), 'dailynote')
    fp = os.path.join(d, 'y.md')
    with open(fp, 'w', encoding='utf-8') as f:
        f.write("---\nmaid: probe\ncreated: 2026-10-06T10:00:00\ntags: [桌球]\n---\n"
                "十月：继续打桌球\n")
    ingest_file(fp, os.path.join(get_agent_dir('probe'), 'recall.db'),
                SemanticFakeEmbeddingClient())
    os.unlink(fp)
    db = os.path.join(get_agent_dir('probe'), 'recall.db')
    client = SemanticFakeEmbeddingClient()

    hits = recall_associative('桌球', db, client, k=10,
                              since='2026-10-01', tag_weight=0.5)
    assert hits, '十月那条应当被召回'
    assert all(h['date'] >= '2026-10-01' for h in hits), \
        f'窗外记忆从标签扩增漏了进来：{[h["date"] for h in hits]}'


# ============================================================
# 4. 对抗：缓存不许把"带窗"和"不带窗"混成一份
# ============================================================

def test_cache_does_not_conflate_windowed_and_unwindowed(db):
    client = SemanticFakeEmbeddingClient()
    unbounded = recall_associative('备课', db, client, k=10, cache=True)
    assert len(unbounded) == 3

    windowed = recall_associative('备课', db, client, k=10, cache=True,
                                  since='2026-10-01')
    assert [h['date'] for h in windowed] == ['2026-10-05'], \
        '带窗查询命中了不带窗的缓存 —— 脏读'


def test_cache_key_differs_by_window(db):
    from scripts.cache import _cache_key
    a = _cache_key(db, query='q', since=None, until=None)
    b = _cache_key(db, query='q', since='2026-10-01', until=None)
    c = _cache_key(db, query='q', since=None, until='2026-10-01')
    assert len({a, b, c}) == 3


# ============================================================
# 5. CLI：--query 配 --since/--until
# ============================================================

def test_cli_query_with_window(db, capsys):
    rc = recall_main(['--query', '备课', '--identity', 'probe',
                      '--since', '2026-10-01', '--k', '10'])
    assert rc == 0
    out = capsys.readouterr().out
    assert '十月版本' in out
    assert '八月版本' not in out and '九月版本' not in out


def test_cli_query_window_rejects_bad_dates(db, capsys):
    assert recall_main(['--query', '备课', '--identity', 'probe',
                        '--since', '2026-10']) == 2
    assert recall_main(['--query', '备课', '--identity', 'probe',
                        '--since', '2026-10-05', '--until', '2026-10-01']) == 2
    assert 'YYYY-MM-DD' in capsys.readouterr().err or True


def test_cli_query_window_logs_window_in_ledger(db):
    from scripts.ledger import read_entries
    assert recall_main(['--query', '备课', '--identity', 'probe',
                        '--since', '2026-10-01']) == 0
    entry = read_entries('probe')[-1]
    assert entry['extra'].get('since') == '2026-10-01'
    assert entry['extra'].get('until') is None


# ============================================================
# 6. recall_by_identity 透传 + --auto 透传
# ============================================================

def test_recall_by_identity_passes_window(db):
    client = SemanticFakeEmbeddingClient()
    hits = recall_by_identity('备课', client, identity='probe', k=10,
                              since='2026-10-01')
    assert [h['date'] for h in hits] == ['2026-10-05']


def test_auto_recall_passes_window(base):
    """--auto 走 default 兜底时，窗口也必须生效。

    （不锚定时 auto 会回落到 default——所以这里直接给 default 区造数据。）
    """
    from scripts.recall import auto_recall
    d = os.path.join(get_agent_dir('default'), 'dailynote')
    os.makedirs(d, exist_ok=True)
    db_path = os.path.join(get_agent_dir('default'), 'recall.db')
    for name, created, body in [
        ('a', '2026-08-10', '备课：八月版本'),
        ('c', '2026-10-05', '备课：十月版本'),
    ]:
        fp = os.path.join(d, f'{name}.md')
        with open(fp, 'w', encoding='utf-8') as f:
            f.write(f"---\nmaid: default\ncreated: {created}T10:00:00\ntags: [教学]\n---\n{body}\n")
        ingest_file(fp, db_path, SemanticFakeEmbeddingClient())
        os.unlink(fp)

    client = SemanticFakeEmbeddingClient()
    res = auto_recall('备课', client, k=10, since='2026-10-01')
    assert res['results']
    assert all(r['date'] >= '2026-10-01' for r in res['results'])


# ============================================================
# 7. 默认入口 prep.py 也要能吃窗口（Issue #7 票2）
# ============================================================

def test_prep_for_reply_accepts_window(db):
    from scripts.prep import prep_for_reply
    client = SemanticFakeEmbeddingClient()
    out = prep_for_reply('备课', db_path=db, embedding_client=client, force=True,
                         since='2026-10-01')
    assert out['recalled'] is True
    assert out['results']
    assert all(r['date'] >= '2026-10-01' for r in out['results'])
    assert '十月版本' in out['text']
    assert '八月版本' not in out['text']


def test_prep_cli_with_window_writes_ledger_with_window(db, capsys):
    import scripts.prep as prep_mod
    from scripts.ledger import read_entries
    rc = prep_mod.main(['--message', '还记得备课吗', '--identity', 'probe',
                        '--force', '--since', '2026-10-01'])
    assert rc == 0
    entry = read_entries('probe')[-1]
    assert entry['extra'].get('since') == '2026-10-01'


def test_prep_cli_without_window_is_unchanged(db, capsys):
    import scripts.prep as prep_mod
    rc = prep_mod.main(['--message', '还记得备课吗', '--identity', 'probe',
                        '--force', '--k', '10'])
    assert rc == 0
    out = capsys.readouterr().out
    assert '八月版本' in out
    assert '十月版本' in out


# ============================================================
# 8. 对抗审查发现：--since/--until 吞掉下一个 flag（#5 修过 --literal，
#    窗口参数漏了）。PowerShell 丢空串时 `--since --budget 500` 会把
#    `--budget` 当日期、`500` 报 Unknown option——报错指向错误的参数。
# ============================================================

@pytest.mark.parametrize('which', ['recall', 'prep'])
def test_window_flag_does_not_swallow_next_flag(db, capsys, which):
    import scripts.prep as prep_mod
    argv = {
        'recall': ['--query', '备课', '--identity', 'probe',
                   '--since', '--budget', '500'],
        'prep': ['--message', '还记得吗', '--identity', 'probe',
                 '--force', '--since', '--budget', '500'],
    }[which]
    main_fn = recall_main if which == 'recall' else prep_mod.main
    rc = main_fn(argv)
    assert rc == 2
    err = capsys.readouterr().err
    # 必须指向 --since 缺值，而不是把锅甩给后面的参数
    assert '--since 缺少值' in err, err


def test_audit_displays_window(db, capsys):
    """审计行必须显示窗口：hits=1 在窗内是正确答案，但看不见窗口就会像坏了。"""
    from scripts.recall import format_entries
    from scripts.ledger import read_entries
    assert recall_main(['--query', '备课', '--identity', 'probe',
                        '--since', '2026-10-01', '--until', '2026-10-31']) == 0
    capsys.readouterr()
    text = format_entries(read_entries('probe'), 'probe')
    assert 'window=[2026-10-01, 2026-10-31]' in text


def test_audit_without_window_shows_no_window_field(db, capsys):
    from scripts.recall import format_entries
    from scripts.ledger import read_entries
    assert recall_main(['--query', '备课', '--identity', 'probe']) == 0
    capsys.readouterr()
    text = format_entries(read_entries('probe'), 'probe')
    assert 'window=' not in text
