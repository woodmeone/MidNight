# -*- coding: utf-8 -*-
"""对抗探针（手工运行，非纳入 CI）：把最容易崩的输入一次性打穿。

这些用例如果进 CI 会拖慢全量（每个都建临时库），所以单独放一个文件，
需要时手动跑：python tests/probe_adversarial.py
"""
import os
import sqlite3
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'scripts')))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import scripts.config as cfg  # noqa: E402
from scripts.config import ensure_agent, get_agent_dir  # noqa: E402
from scripts.embedding import SemanticFakeEmbeddingClient  # noqa: E402
from scripts.ingest import ingest_file  # noqa: E402
from scripts.recall import literal_recall, timeline_recall  # noqa: E402

FAILED = []


def check(name, fn):
    try:
        fn()
        print(f'  PASS  {name}')
    except Exception as exc:                      # noqa: BLE001
        FAILED.append((name, exc))
        print(f'  FAIL  {name}: {type(exc).__name__}: {exc}')


def check_raises(name, fn, exc_type, needle):
    """断言"该炸的时候炸得清楚"——静默失败比崩溃更危险。"""
    try:
        fn()
    except exc_type as exc:
        if needle in str(exc):
            print(f'  PASS  {name}（清晰报错：{exc}）')
        else:
            FAILED.append((name, exc))
            print(f'  FAIL  {name}: 报错信息里没有 {needle!r}，实际 {exc!r}')
    except Exception as exc:                      # noqa: BLE001
        FAILED.append((name, exc))
        print(f'  FAIL  {name}: 抛错类型不对 {type(exc).__name__}: {exc}')
    else:
        FAILED.append((name, AssertionError('本应报错却成功了')))
        print(f'  FAIL  {name}: 本应报错却成功了')


def main():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        old = cfg.BASE_DIR
        cfg.BASE_DIR = tmp
        try:
            ensure_agent('p')
            db = os.path.join(get_agent_dir('p'), 'recall.db')
            d = os.path.join(get_agent_dir('p'), 'dailynote')
            os.makedirs(d, exist_ok=True)
            fp = os.path.join(d, 'x.md')
            with open(fp, 'w', encoding='utf-8') as f:
                f.write("---\nmaid: p\ncreated: 2026-09-22T10:00:00\ntags: [t]\n---\n"
                        "含百分号 50% 和 下划线 a_b 和 单引号 it's 和反斜杠 C:\\x\n")
            ingest_file(fp, db, SemanticFakeEmbeddingClient())

            print('SQL / LIKE 注入面：')
            for probe in ("a' OR 1=1 --", "%' OR '1'='1", "it's", "C:\\x",
                          "50%", "a_b", "'", "\\", "%"):
                check(f'literal {probe!r}',
                      lambda p=probe: literal_recall(db, p, k=10))

            print('日期边界：')
            check('since == until',
                  lambda: timeline_recall(db, k=5, since='2026-09-22', until='2026-09-22'))
            check('since 极早', lambda: timeline_recall(db, k=5, since='1900-01-01'))
            check('until 极晚', lambda: timeline_recall(db, k=5, until='2999-12-31'))
            check('空串日期（当作无过滤）', lambda: timeline_recall(db, k=5, since='', until=''))

            print('规模与异常输入：')
            check('k 极大', lambda: timeline_recall(db, k=10 ** 6))
            check('k=0', lambda: timeline_recall(db, k=0))
            check('k 负数', lambda: timeline_recall(db, k=-5))
            check_raises('literal 超长 → 明确报错而不是 LIKE 崩溃',
                         lambda: literal_recall(db, 'x' * 100000, k=5),
                         ValueError, '最多 200 字')
            check('literal 空', lambda: literal_recall(db, '', k=5))
            check('literal 纯空白', lambda: literal_recall(db, '   \t\n', k=5))

            print('库异常：')
            check('库文件不存在（应自动建空库）',
                  lambda: timeline_recall(os.path.join(tmp, 'newdir', 'none.db'), k=3))

            # 坏库：不是 sqlite 文件
            bad = os.path.join(tmp, 'bad.db')
            with open(bad, 'wb') as f:
                f.write(b'not a database at all' * 10)
            check_raises('坏库文件 → 说人话的报错',
                         lambda: timeline_recall(bad, k=3),
                         ValueError, '记忆库不可用')

            # 孤儿 chunk：file 行缺失（FK 默认开启，用关闭 FK 的连接模拟历史脏数据）
            orph = os.path.join(tmp, 'orphan.db')
            from scripts.schema import init_db
            c = init_db(orph)
            c.execute("PRAGMA foreign_keys=OFF")
            c.execute("INSERT INTO chunks (file_id, chunk_index, content) VALUES (999, 0, '孤儿')")
            c.commit()
            c.close()
            check('孤儿 chunk（file 不存在）', lambda: timeline_recall(orph, k=3))
            check('孤儿 chunk 字面', lambda: literal_recall(orph, '孤儿', k=3))

            print('时间窗约束（Issue #7）：')
            from scripts.recall import recall_associative
            cli = SemanticFakeEmbeddingClient()
            # 补三条跨月"备课"记忆：窗口探针要能观察到"确实收窄"
            for name, created, body in [
                ('w1', '2026-08-10', '备课：八月版本'),
                ('w2', '2026-09-15', '备课：九月版本'),
                ('w3', '2026-10-05', '备课：十月版本'),
            ]:
                fp2 = os.path.join(d, f'{name}.md')
                with open(fp2, 'w', encoding='utf-8') as f:
                    f.write(f"---\nmaid: p\ncreated: {created}T10:00:00\n"
                            f"tags: [教学]\n---\n{body}\n")
                ingest_file(fp2, db, cli)
                os.unlink(fp2)

            check('窗口 起点=终点',
                  lambda: recall_associative('备课', db, cli, k=10,
                                             since='2026-09-15', until='2026-09-15'))
            check('窗口 只有 since',
                  lambda: recall_associative('备课', db, cli, k=10, since='2026-09-15'))
            check('窗口 只有 until',
                  lambda: recall_associative('备课', db, cli, k=10, until='2026-09-15'))
            check('窗口 空串（等价不设窗）',
                  lambda: recall_associative('备课', db, cli, k=10, since='', until=''))
            check('窗口 极早~极晚',
                  lambda: recall_associative('备课', db, cli, k=10,
                                             since='1900-01-01', until='2999-12-31'))
            check('窗口 + prefilter',
                  lambda: recall_associative('备课', db, cli, k=10, prefilter=True,
                                             since='2026-09-15'))
            check('窗口 + multi_scale',
                  lambda: recall_associative('备课', db, cli, k=10, multi_scale=True,
                                             since='2026-09-15'))
            check('窗口 + MMR',
                  lambda: recall_associative('备课', db, cli, k=10, mmr_lambda=0.5,
                                             since='2026-09-15'))
            check('窗口 + cache（连跑两次不脏读）',
                  lambda: [recall_associative('备课', db, cli, k=10, cache=True,
                                              since='2026-09-15') for _ in range(2)])

            # 窗口必须真的收窄且选对内容——"没过滤"和"过滤坏了"都要抓到
            unbounded = recall_associative('备课', db, cli, k=10)
            windowed = recall_associative('备课', db, cli, k=10, since='2026-10-01')
            if len(windowed) > len(unbounded):
                raise AssertionError(
                    f'窗口反而变宽了：{len(windowed)} > {len(unbounded)}')
            dates = {r['date'] for r in windowed}
            if not all(dt >= '2026-10-01' for dt in dates):
                raise AssertionError(f'窗外记忆混进来了：{sorted(dates)}')
            print(f'  PASS  窗口确实收窄（不设窗 {len(unbounded)} 条 ≥ 设窗 '
                  f'{len(windowed)} 条，且全部 >= 2026-10-01）')
        finally:
            cfg.BASE_DIR = old

    print()
    if FAILED:
        print(f'{len(FAILED)} 个探针失败')
        for name, exc in FAILED:
            print(f'  - {name}: {type(exc).__name__}: {exc}')
        return 1
    print('全部探针通过')
    return 0


if __name__ == '__main__':
    sys.exit(main())
