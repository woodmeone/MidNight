# -*- coding: utf-8 -*-
"""票2：确定性通道（时间轴 / 字面命中）。

存在理由（第一性）：联想召回是**相关性排序**，答不了"最新一条是哪天 / 记到哪天 /
有没有提过某词"。没有正解时，AI 只能去翻 `dailynote/*.md`——那不是纪律问题，
是能力缺口。这两条通道把这类问题变成库内一次查询，于是"不读 md"才成为理性选择。

对抗重点：
- 通道必须**不依赖 md**：把 dailynote 整个删掉，结果必须一字不变；
- 通道必须**不越隔离墙**：A 的时间轴里绝不能出现 B 的日记；
- 通道必须**不静默**：没声明身份就直接拒绝，不许落到 env/default 库。
"""
import os
import shutil
import tempfile

import pytest

import scripts.config as cfg
from scripts.config import ensure_agent, get_agent_dir, get_dailynote_path
from scripts.embedding import SemanticFakeEmbeddingClient
from scripts.ingest import ingest_file
from scripts.ledger import read_entries
from scripts.recall import (
    format_recall_output, literal_recall, main as recall_main, timeline_recall,
)

OLD_HEADER = '[回忆] 以下是相关记忆（来源于你的日记，按相关度排序）：'


@pytest.fixture
def base(monkeypatch):
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        monkeypatch.setattr(cfg, 'BASE_DIR', tmp)
        yield tmp


def _diary(agent, name, created, body, tags='教学'):
    d = get_dailynote_path(agent)
    os.makedirs(d, exist_ok=True)
    fp = os.path.join(d, f'{name}.md')
    with open(fp, 'w', encoding='utf-8') as f:
        f.write(f"---\nmaid: {agent}\ncreated: {created}T10:00:00\ntags: [{tags}]\n---\n{body}\n")
    return fp


def _seed(agent, db=None):
    """probe 区：09-01（两块）、09-10（带 % 号）、09-17、09-22；other 区：09-30。"""
    ensure_agent(agent)
    db = db or os.path.join(get_agent_dir(agent), 'recall.db')
    embed = SemanticFakeEmbeddingClient()
    rows = [
        ('d1', '2026-09-01', '九月一日第一段。开学第一天。\n\n九月一日第二段。学生自我介绍。'),
        ('d2', '2026-09-10', '命中率 50% 算达标。'),
        ('d3', '2026-09-17', '备课模块：先备人再备课。'),
        ('d4', '2026-09-22', '头发事件：方案降级为中立不追究。'),
    ]
    for name, created, body in rows:
        fp = _diary(agent, name, created, body)
        ingest_file(fp, db, embed)
        os.unlink(fp)
    return db


def _seed_other():
    ensure_agent('other')
    db = os.path.join(get_agent_dir('other'), 'recall.db')
    fp = _diary('other', 'o1', '2026-09-30', '别人的秘密：中立不追究，Python 课。')
    ingest_file(fp, db, SemanticFakeEmbeddingClient())
    os.unlink(fp)
    return db


# ============================================================
# 1. 时间轴：倒序 + file 级去重 + 块序拼接
# ============================================================

def test_timeline_newest_first(base):
    db = _seed('probe')
    got = timeline_recall(db, k=2)
    assert [r['date'] for r in got] == ['2026-09-22', '2026-09-17']


def test_timeline_dedupes_by_file_and_keeps_chunk_order(base):
    db = _seed('probe')
    got = timeline_recall(db, k=10)
    assert [r['date'] for r in got] == ['2026-09-22', '2026-09-17', '2026-09-10', '2026-09-01']
    first = got[-1]
    assert '九月一日第一段' in first['content']
    assert '九月一日第二段' in first['content']
    assert first['content'].index('第一段') < first['content'].index('第二段')


# ============================================================
# 2. 日期区间（闭区间）
# ============================================================

def test_timeline_since_is_inclusive(base):
    db = _seed('probe')
    got = timeline_recall(db, k=10, since='2026-09-17')
    assert [r['date'] for r in got] == ['2026-09-22', '2026-09-17']


def test_timeline_until_is_inclusive(base):
    db = _seed('probe')
    got = timeline_recall(db, k=10, until='2026-09-10')
    assert [r['date'] for r in got] == ['2026-09-10', '2026-09-01']


# ============================================================
# 3. 字面命中（含通配符必须被转义）
# ============================================================

def test_literal_hits_substring(base):
    db = _seed('probe')
    got = literal_recall(db, '中立不追究', k=10)
    assert [r['date'] for r in got] == ['2026-09-22']


def test_literal_escapes_percent_wildcard(base):
    """`%` 必须按字面匹配——否则 LIKE 会退化成"全部命中"，比 grep 还糟。"""
    db = _seed('probe')
    got = literal_recall(db, '%', k=10)
    assert [r['date'] for r in got] == ['2026-09-10']


def test_literal_empty_when_no_match(base):
    db = _seed('probe')
    assert literal_recall(db, '完全不存在的词', k=10) == []


def test_literal_escapes_underscore_wildcard(base):
    """`_` 是 LIKE 的单字符通配符：不转义的话，查一个下划线会命中所有日记。"""
    db = _seed('probe')
    assert literal_recall(db, '_', k=10) == []


def test_timeline_zero_returns_empty(base):
    db = _seed('probe')
    assert timeline_recall(db, k=0) == []


def test_since_without_channel_is_rejected(base, capsys):
    rc = recall_main(['--since', '2026-09-01', '--identity', 'probe'])
    assert rc == 2
    assert '--timeline' in capsys.readouterr().err


def test_until_includes_whole_day_when_date_has_time_part(base):
    """旧库/手工改写的行可能是全时间戳，--until 必须仍能包住当天。

    对抗场景：`'2026-09-22 10:00:00' > '2026-09-22'` 为真——不把日期截到 10 位
    就会把当天的记忆误排除（边界最容易被"看起来对"的字符串比较坑到）。
    """
    import sqlite3
    db = _seed('probe')
    conn = sqlite3.connect(db)
    try:
        conn.execute("UPDATE files SET diary_date = '2026-09-22 10:00:00' "
                     "WHERE diary_date = '2026-09-22'")
        conn.commit()
    finally:
        conn.close()
    got = timeline_recall(db, k=10, until='2026-09-22')
    assert [r['date'] for r in got] == ['2026-09-22', '2026-09-17', '2026-09-10', '2026-09-01']


def test_bad_date_format_is_rejected_not_silently_empty(base, capsys):
    """未补零的日期不会报错、只会静默返回"没记忆"——必须当参数错误拒绝。"""
    _seed('probe')
    for argv in (['--timeline', '3', '--since', '2026-9-1', '--identity', 'probe'],
                 ['--timeline', '3', '--until', '2026/09/22', '--identity', 'probe'],
                 ['--literal', 'x', '--since', 'yesterday', '--identity', 'probe']):
        assert recall_main(argv) == 2
    err = capsys.readouterr().err
    assert 'YYYY-MM-DD' in err


def test_inverted_range_is_rejected(base, capsys):
    _seed('probe')
    rc = recall_main(['--timeline', '3', '--since', '2026-09-22',
                      '--until', '2026-09-01', '--identity', 'probe'])
    assert rc == 2
    assert '区间为空' in capsys.readouterr().err


def test_literal_ascii_case_insensitive(base):
    db = _seed('probe')
    got = literal_recall(db, 'python', k=10)
    assert len(got) == 0        # 别人的 Python，不可见
    _seed_other()
    assert [r['date'] for r in literal_recall(db, 'python', k=10)] == []


# ============================================================
# 4. 隔离：A 的通道里绝不出现 B
# ============================================================

def test_timeline_never_crosses_agents(base):
    db = _seed('probe')
    _seed_other()
    assert all('别人的秘密' not in r['content'] for r in timeline_recall(db, k=10))
    assert all('别人的秘密' not in r['content'] for r in literal_recall(db, '中立不追究', k=10))


def test_other_agent_own_timeline_works(base):
    db = _seed('probe')
    other_db = _seed_other()
    assert [r['date'] for r in timeline_recall(other_db, k=10)] == ['2026-09-30']


# ============================================================
# 5. 对抗：把 md 源文件删干净，通道必须一字不变
# ============================================================

def test_channels_survive_dailynote_removal(base):
    db = _seed('probe')
    before_t = [(r['date'], r['content']) for r in timeline_recall(db, k=10)]
    before_l = [(r['date'], r['content']) for r in literal_recall(db, '中立不追究', k=10)]

    shutil.rmtree(get_dailynote_path('probe'))

    assert [(r['date'], r['content']) for r in timeline_recall(db, k=10)] == before_t
    assert [(r['date'], r['content']) for r in literal_recall(db, '中立不追究', k=10)] == before_l


def test_cli_channels_survive_dailynote_removal(base, capsys):
    _seed('probe')
    shutil.rmtree(get_dailynote_path('probe'))
    assert recall_main(['--timeline', '1', '--identity', 'probe']) == 0
    assert '中立不追究' in capsys.readouterr().out


# ============================================================
# 6. 身份强制：没声明身份就拒绝，不落任何库
# ============================================================

def test_timeline_requires_explicit_identity(base, capsys):
    rc = recall_main(['--timeline', '3'])
    assert rc == 2
    assert os.listdir(base) == []
    assert 'identity' in capsys.readouterr().err.lower()


def test_literal_requires_explicit_identity(base, capsys):
    rc = recall_main(['--literal', '中立不追究'])
    assert rc == 2
    assert os.listdir(base) == []


# ============================================================
# 7. 空库、CLI 输出头、默认行为不变
# ============================================================

def test_empty_db_says_nothing_found(base, capsys):
    ensure_agent('probe')
    assert recall_main(['--timeline', '3', '--identity', 'probe']) == 0
    assert '暂无相关记忆' in capsys.readouterr().out


def test_cli_timeline_writes_ledger_with_channel(base, capsys):
    _seed('probe')
    assert recall_main(['--timeline', '2', '--identity', 'probe']) == 0
    entry = read_entries('probe')[-1]
    assert entry['channel'] == 'timeline'
    assert entry['hits'] == 2


def test_cli_literal_writes_ledger_with_channel(base, capsys):
    _seed('probe')
    assert recall_main(['--literal', '中立不追究', '--identity', 'probe']) == 0
    assert read_entries('probe')[-1]['channel'] == 'literal'


def test_default_format_output_is_byte_identical():
    """不给 header 时，输出必须与改动前逐字节一致（默认行为不可漂移）。"""
    results = [{'chunk_id': 1, 'content': '正文', 'date': '2026-09-22',
                'score': 1.0, 'file_path': 'p', 'importance': 'medium'}]
    expected = OLD_HEADER + '\n\n\n（2026-09-22）正文'
    assert format_recall_output(results) == expected
    assert format_recall_output(results, header=None) == expected
    assert format_recall_output([{'chunk_id': 1, 'content': 'x', 'date': None,
                                  'score': 0.0, 'file_path': 'p',
                                  'importance': 'medium'}]) == OLD_HEADER + '\n\n\nx'
