"""并发追加对抗测试：多线程同时写同一份 ledger，不能丢行、不能撕裂。

为什么值得测：留痕的用途是**当证据**（反查"这一轮到底走没走算法"）。
一份会丢行的日志不能当证据——它会把"查了"记成"没查"，正好毁掉它存在的理由。
Windows 上 `O_APPEND` 不是真原子（CPython 用 seek-to-end 模拟），所以这里锁的是
进程内互斥；跨进程追加走 OS 层，本测试不覆盖（见"未覆盖的风险"）。
"""
import json
import os
import sys
import tempfile
import threading

SCRIPTS = os.path.join(os.path.dirname(__file__), '..', 'scripts')
sys.path.insert(0, os.path.abspath(os.path.dirname(SCRIPTS)))

import scripts.config as cfg  # noqa: E402
from scripts.config import ensure_agent  # noqa: E402
from scripts.ledger import append_entry, ledger_path, read_entries  # noqa: E402


def test_concurrent_appends_do_not_tear():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        old = cfg.BASE_DIR
        cfg.BASE_DIR = tmp
        try:
            ensure_agent('cc')
            path = ledger_path('cc')

            def _worker(n):
                for i in range(10):
                    append_entry('associative', f'q{n}-{i}',
                                 results=[{'chunk_id': n}], agent='cc')

            threads = [threading.Thread(target=_worker, args=(n,)) for n in range(8)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            lines = [l for l in open(path, encoding='utf-8').read().splitlines() if l.strip()]
            assert len(lines) == 80, f'丢行：{len(lines)}/80'
            for line in lines:
                json.loads(line)          # 每一行都必须是完整 JSON，不能撕裂
            assert len(read_entries('cc', limit=None)) == 80
        finally:
            cfg.BASE_DIR = old


def test_concurrent_appends_across_agents_do_not_interfere():
    """不同 agent 并发写各自 ledger，互不串号。"""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        old = cfg.BASE_DIR
        cfg.BASE_DIR = tmp
        try:
            names = [f'a{i}' for i in range(4)]
            for n in names:
                ensure_agent(n)

            def _worker(name):
                for i in range(15):
                    append_entry('timeline', f'{name}-{i}',
                                 results=[{'chunk_id': i}], agent=name)

            threads = [threading.Thread(target=_worker, args=(n,)) for n in names]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            for n in names:
                entries = read_entries(n, limit=None)
                assert len(entries) == 15
                assert all(e['query'].startswith(f'{n}-') for e in entries)
        finally:
            cfg.BASE_DIR = old
