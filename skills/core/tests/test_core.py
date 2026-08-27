"""Tests for midnight-core: cross-session timeline.

Tests append, timeline, format, and adversarial edge cases.
"""
import os
import tempfile
import sqlite3
import pytest
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from scripts.schema import init_db
from scripts.append import append
from scripts.timeline import get_timeline, format_timeline


@pytest.fixture
def db_path():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        yield os.path.join(tmpdir, 'core.db')


def test_init_db_creates_table(db_path):
    """init_db 应创建 messages 表"""
    conn = init_db(db_path)
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()]
    conn.close()
    assert 'messages' in tables


def test_append_message(db_path):
    """append 应写入消息并返回 id"""
    result = append("session1", "web", "user", "你好", db_path=db_path)
    assert result['status'] == 'appended'
    assert result['id'] is not None


def test_append_duplicate(db_path):
    """5 分钟内相同内容应去重"""
    r1 = append("session1", "web", "user", "你好", db_path=db_path)
    assert r1['status'] == 'appended'
    r2 = append("session1", "web", "user", "你好", db_path=db_path)
    assert r2['status'] == 'duplicate'


def test_append_different_session_same_content(db_path):
    """不同会话相同内容不应去重"""
    r1 = append("session1", "web", "user", "你好", db_path=db_path)
    assert r1['status'] == 'appended'
    r2 = append("session2", "mobile", "user", "你好", db_path=db_path)
    assert r2['status'] == 'appended'


def test_append_assistant_role(db_path):
    """支持 assistant 角色"""
    r = append("session1", "web", "assistant", "我明白了", db_path=db_path)
    assert r['status'] == 'appended'


def test_append_invalid_role(db_path):
    """非法角色应报错"""
    with pytest.raises(sqlite3.IntegrityError):
        append("session1", "web", "robot", "你好", db_path=db_path)


def test_get_timeline_empty(db_path):
    """空库返回空列表"""
    msgs = get_timeline(session_id="s1", db_path=db_path)
    assert msgs == []


def test_get_timeline_excludes_own_session(db_path):
    """get_timeline 排除当前会话"""
    append("s1", "web", "user", "s1消息", db_path=db_path)
    append("s2", "mobile", "user", "s2消息", db_path=db_path)
    msgs = get_timeline(session_id="s1", db_path=db_path)
    assert len(msgs) == 1
    assert msgs[0]['session_id'] == 's2'


def test_get_timeline_all_sessions(db_path):
    """不指定 session 时返回所有会话"""
    append("s1", "web", "user", "m1", db_path=db_path)
    append("s2", "mobile", "user", "m2", db_path=db_path)
    msgs = get_timeline(session_id=None, db_path=db_path)
    assert len(msgs) == 2


def test_get_timeline_limit(db_path):
    """limit 参数限制返回数量"""
    for i in range(20):
        append(f"s{i}", "web", "user", f"msg{i}", db_path=db_path)
    msgs = get_timeline(limit=5, db_path=db_path)
    assert len(msgs) <= 5


def test_format_timeline_empty(db_path):
    """空时间线输出友好提示"""
    text = format_timeline([])
    assert "无其他会话记录" in text


def test_format_timeline_single(db_path):
    """单条消息格式化"""
    msgs = [{'id': 1, 'session_id': 's1', 'source': 'web', 'role': 'user',
             'content': '你好', 'created_at': '2026-08-20 14:30:00'}]
    text = format_timeline(msgs)
    assert 'web' in text
    assert '你好' in text


def test_format_timeline_grouped_by_source(db_path):
    """不同来源的消息分组显示"""
    msgs = [
        {'id': 1, 'session_id': 's1', 'source': 'web', 'role': 'user',
         'content': 'a', 'created_at': '2026-08-20 14:30:00'},
        {'id': 2, 'session_id': 's2', 'source': 'mobile', 'role': 'user',
         'content': 'b', 'created_at': '2026-08-20 14:31:00'},
    ]
    text = format_timeline(msgs)
    assert 'web' in text
    assert 'mobile' in text


def test_format_timeline_long_content_truncated():
    """超长内容截断"""
    msgs = [{'id': 1, 'session_id': 's1', 'source': 'web', 'role': 'user',
             'content': 'A' * 300, 'created_at': '2026-08-20 14:30:00'}]
    text = format_timeline(msgs)
    assert '…' in text


# ---- Adversarial tests ----

def test_append_empty_content(db_path):
    """空内容应该能写入（SQLite 允许空字符串）"""
    r = append("s1", "web", "user", "", db_path=db_path)
    assert r['status'] == 'appended'


def test_append_huge_content(db_path):
    """超大内容应能写入"""
    r = append("s1", "web", "user", "X" * 100000, db_path=db_path)
    assert r['status'] == 'appended'


def test_timeline_missing_db():
    """不存在的数据库应返回空列表"""
    msgs = get_timeline(db_path="/nonexistent/core.db")
    assert msgs == []


def test_append_special_chars(db_path):
    """特殊字符应正确处理"""
    r = append("s1", "web", "user", "你好！@#$%^&*()_+{}:\"<>?", db_path=db_path)
    assert r['status'] == 'appended'


def test_append_and_timeline_integration(db_path):
    """写入后读取应一致"""
    append("s1", "web", "user", "测试消息", db_path=db_path)
    msgs = get_timeline(db_path=db_path)
    assert len(msgs) == 1
    assert msgs[0]['content'] == '测试消息'
    assert msgs[0]['source'] == 'web'


def test_multiple_sources_timeline(db_path):
    """多来源多会话时间线"""
    for source, session, content in [
        ("web", "s1", "web消息1"),
        ("web", "s1", "web消息2"),
        ("mobile", "s2", "手机消息1"),
        ("mobile", "s2", "手机消息2"),
    ]:
        append(session, source, "user", content, db_path=db_path)

    msgs = get_timeline(session_id="s1", db_path=db_path)
    assert len(msgs) == 2
    assert all(m['session_id'] == 's2' for m in msgs)


def test_timeline_sort_order(db_path):
    """时间线按时间倒序"""
    append("s1", "web", "user", "最早", db_path=db_path)
    import time
    time.sleep(0.01)
    append("s2", "mobile", "user", "最晚", db_path=db_path)
    msgs = get_timeline(db_path=db_path)
    # 最晚的应排在前面
    assert msgs[0]['content'] == '最晚'