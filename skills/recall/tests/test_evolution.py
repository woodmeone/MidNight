"""Tests for T6: 自进化（/evolution 覆写可动层 + 定海锚只读 + 久不用衰减）。

Behavioral checks (OPTIMIZATION-SPEC §5「self 演化」):
- 调整可动层后定海锚未变；改定海锚字段被拒且写入演化日志。
- 无 self 时 --apply 自动先建 self 再应用。
- 演化历史可读（多次追加）。
- 久不用衰减：新鲜边不动、过期边降权、过期弱边删除（tag_edges 与 cooccurrence）。
"""
import os
import sqlite3
import tempfile

import pytest

import scripts.config as cfg
from scripts.self_model import ensure_self, read_self, get_self_path
from scripts.schema import init_db
from scripts.evolution import (
    apply_evolution, read_evolution_log, decay_stale_edges,
    get_evolution_log_path,
)


@pytest.fixture
def basedir():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        old_base = cfg.BASE_DIR
        cfg.BASE_DIR = tmp
        yield tmp
        cfg.BASE_DIR = old_base


@pytest.fixture
def agent(basedir):
    return 'mira'


def test_apply_evolution_updates_mutable_and_logs(agent):
    """可动层 patch 生效，且演化被记录进 evolution.log"""
    ensure_self(agent)
    result = apply_evolution(
        agent,
        feedback='用户纠正：Windows 用 py 别用 python',
        patch={'position': 'Windows 工程师', 'preferences': {'cmd': 'py'}},
        source='user',
    )
    assert set(result['applied']) == {'position', 'preferences'}
    assert result['rejected'] == []
    data = read_self(agent)
    assert data['mutable']['position'] == 'Windows 工程师'
    assert data['mutable']['preferences'] == {'cmd': 'py'}

    log = read_evolution_log(agent)
    assert len(log) == 1
    assert log[0]['source'] == 'user'
    assert 'py' in log[0]['feedback']
    assert log[0]['applied'] == ['position', 'preferences']


def test_apply_evolution_rejects_immutable(agent):
    """改定海锚字段被拒绝，值不变，且拒绝被记录"""
    ensure_self(agent)
    original = read_self(agent)
    result = apply_evolution(agent, feedback='mirror 自省',
                             patch={'name': 'evil', 'anchor_tags': ['hacked']},
                             source='mirror')
    assert result['updated'] is False
    assert set(result['rejected']) == {'name', 'anchor_tags'}
    data = read_self(agent)
    assert data['name'] == original['name']
    assert data['anchor_tags'] == original['anchor_tags']

    log = read_evolution_log(agent)
    assert log[0]['rejected'] == ['name', 'anchor_tags']
    assert log[0]['source'] == 'mirror'


def test_apply_evolution_without_self_creates_self(agent):
    """无 self 时 --apply 自动先建 self（幂等）再应用"""
    assert not os.path.exists(get_self_path(agent))
    result = apply_evolution(agent, patch={'persona_style': '冷静'}, source='research')
    assert result['applied'] == ['persona_style']
    assert os.path.exists(get_self_path(agent))
    assert read_self(agent)['mutable']['persona_style'] == '冷静'


def test_evolution_log_append_history(agent):
    """多次演化按时间追加，历史可完整读取"""
    ensure_self(agent)
    apply_evolution(agent, patch={'persona_style': 'A'}, source='user')
    apply_evolution(agent, patch={'persona_style': 'B'}, source='mirror')
    log = read_evolution_log(agent)
    assert len(log) == 2
    assert [e['source'] for e in log] == ['user', 'mirror']
    assert log[-1]['patch'] == {'persona_style': 'B'}


def test_decay_fresh_stays_old_fades(agent):
    """久不用衰减：新鲜边不动，过期边降权，过期弱边删除"""
    db = cfg.get_db_path(agent)
    init_db(db)
    conn = sqlite3.connect(db)
    # tags 1..4
    for name in ('a', 'b', 'c', 'd'):
        conn.execute("INSERT INTO tags (name) VALUES (?)", (name,))
    # 新鲜边 a->b：today, weight 1.0 → 不变
    conn.execute(
        "INSERT INTO tag_edges (tag_from_id, tag_to_id, weight, updated_at) "
        "VALUES (1, 2, 1.0, datetime('now'))")
    # 过期边 b->a：200 天前, weight 1.0 → 0.5
    conn.execute(
        "INSERT INTO tag_edges (tag_from_id, tag_to_id, weight, updated_at) "
        "VALUES (2, 1, 1.0, datetime('now', '-200 days'))")
    # 过期弱边 c->d：200 天前, weight 0.08 → 0.04 → 删除（floor 0.05）
    conn.execute(
        "INSERT INTO tag_edges (tag_from_id, tag_to_id, weight, updated_at) "
        "VALUES (3, 4, 0.08, datetime('now', '-200 days'))")
    conn.commit()

    result = decay_stale_edges(db, stale_days=90, factor=0.5, floor=0.05)
    rows = {f"{r[0]}-{r[1]}": r[2]
            for r in conn.execute("SELECT tag_from_id, tag_to_id, weight FROM tag_edges").fetchall()}
    conn.close()

    assert rows['1-2'] == 1.0, "新鲜边不应被衰减"
    assert rows['2-1'] == pytest.approx(0.5), "过期边应降权"
    assert '3-4' not in rows, "过期弱边应被删除"
    assert result['decayed'] >= 2
    assert result['removed'] == 1


def test_decay_stale_cooccurrence_too(agent):
    """共现矩阵同样衰减，保证召回一致性"""
    db = cfg.get_db_path(agent)
    init_db(db)
    conn = sqlite3.connect(db)
    for name in ('a', 'b'):
        conn.execute("INSERT INTO tags (name) VALUES (?)", (name,))
    conn.execute(
        "INSERT INTO tag_cooccurrence (tag1_id, tag2_id, weight, updated_at) "
        "VALUES (1, 2, 1.0, datetime('now', '-200 days'))")
    conn.commit()

    decay_stale_edges(db, stale_days=90, factor=0.5, floor=0.05)
    w = conn.execute("SELECT weight FROM tag_cooccurrence").fetchone()[0]
    conn.close()
    assert w == pytest.approx(0.5)


def test_evolution_log_path_under_agent_dir(agent):
    """演化日志位于该 agent 的数据目录下"""
    assert get_evolution_log_path(agent) == os.path.join(cfg.get_agent_dir(agent), 'evolution.log')


def test_build_patch_set_parsing():
    """--set 解析：平铺键、点号嵌套、JSON 数组值；--patch 基础保留、--set 覆盖"""
    from scripts.evolution import _build_patch
    patch = _build_patch(
        ['position=Windows 工程师', 'preferences.cmd=py', 'capabilities=[记忆,联想,执行]'],
        {'persona_style': '冷静'},
    )
    assert patch['persona_style'] == '冷静'
    assert patch['position'] == 'Windows 工程师'
    assert patch['preferences'] == {'cmd': 'py'}
    assert patch['capabilities'] == ['记忆', '联想', '执行']
