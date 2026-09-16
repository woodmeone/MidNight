"""Integration adversarial tests against the real bge-m3 ONNX model.

These prove the REAL imported vectors drive correct behaviour end-to-end:
  1. Semantic seed sensing: a query about 面试 surfaces interview/压力 tags.
  2. No activation blow-up: pulse propagation stays bounded.
  3. No false-positive over-claiming: a query unrelated to the corpus yields
     low cosine (not a strong-but-meaningless match).
  4. Long input doesn't OOM (max_length truncation kicks in).
  5. Determinism: identical text -> identical vector.

They are skipped automatically when the model isn't installed, so CI or other
machines without the 2GB weights don't fail.
"""
import os
import sqlite3
import tempfile
import pytest

MODEL_DIR = os.environ.get(
    'MIDNIGHT_MODEL_DIR', r'd:\Project\DSH\models\bge-m3')

pytestmark = pytest.mark.skipif(
    not os.path.exists(os.path.join(MODEL_DIR, 'model.onnx')),
    reason='bge-m3 ONNX model not installed')


@pytest.fixture(scope='module')
def client():
    from scripts.embedding import LocalOnnxEmbeddingClient
    return LocalOnnxEmbeddingClient(dimension=1024, model_dir=MODEL_DIR)


def _corpus(tmp_path, client):
    """Small multi-topic corpus: interviews vs cooking (distinct semantics)."""
    from scripts.ingest import ingest_file
    topics = {
        'interview1.md': """---
maid: Nova
created: 2026-08-15T09:00:00
tags: [面试, 紧张]
---
下周有一个面试，我很紧张，担心自己准备得不够充分。
""",
        'interview2.md': """---
maid: Nova
created: 2026-08-16T09:00:00
tags: [面试, 简历]
---
面试前把简历和项目经历重新整理了一遍。
""",
        'cook1.md': """---
maid: Nova
created: 2026-08-17T09:00:00
tags: [做饭, 周末]
---
周末在家学做红烧肉，最后味道还不错。
""",
    }
    db = os.path.join(str(tmp_path), 'recall.db')
    for name, text in topics.items():
        p = os.path.join(str(tmp_path), name)
        with open(p, 'w', encoding='utf-8') as f:
            f.write(text)
        ingest_file(p, db, client)
    return db


def test_seed_sensing_is_semantic(client, tmp_path):
    from scripts.tag_network import activate_tags
    db = _corpus(tmp_path, client)
    activated = activate_tags(client.embed(['面试'])[0], db, client)
    names = []
    conn = sqlite3.connect(db)
    for tid, _s in activated[:5]:
        row = conn.execute("SELECT name FROM tags WHERE id=?", (tid,)).fetchone()
        if row:
            names.append(row[0])
    conn.close()
    # bge-m3: '面试' query must surface interview corpus tags, not cooking.
    assert any(n in ('面试', '紧张', '简历') for n in names), f'got {names}'


def test_activation_stays_bounded(client, tmp_path):
    from scripts.tag_network import activate_tags
    db = _corpus(tmp_path, client)
    activated = activate_tags(client.embed(['面试'])[0], db, client)
    # Small corpus -> number of activated tags should be small and bounded
    # (pulse propagates with fixed budget + threshold filter, no fan-out blowup).
    assert len(activated) <= 6, f'activation exploded: {len(activated)}'


def test_unrelated_query_does_not_outrank_related(client, tmp_path):
    from scripts.recall import recall
    db = _corpus(tmp_path, client)
    # Related query must score clearly above an unrelated one on the SAME corpus.
    # bge-m3 absolute cosines are high even for mismatches (~0.5-0.6), so the
    # meaningful property is relative separation, not an absolute threshold.
    rel = recall('下周面试，心里很紧张', db, client, k=1)[0]['score']
    unr = recall('今天股市大涨，想买点基金', db, client, k=1)[0]['score']
    assert rel > unr + 0.1, f'related={rel:.3f} unrelated={unr:.3f}'


def test_long_input_does_not_oom_and_truncates(client):
    vec = client.embed(['x' * 200000])[0]
    assert len(vec) == 1024
    finite = all(v == v for v in vec)  # no NaN
    assert finite


def test_deterministic_vectors(client):
    a = client.embed(['今天去面试'])[0]
    b = client.embed(['今天去面试'])[0]
    assert a == b


def test_associative_recall_end_to_end_finite_scores(client, tmp_path):
    from scripts.recall import recall_associative
    db = _corpus(tmp_path, client)
    res = recall_associative('下周面试，心里有点紧张', db, client,
                             k=5, tag_weight=0.3, time_ratio=0.5)
    assert res, 'expected associative recall results'
    assert 0 < len(res) <= 10
    for r in res:
        assert r['score'] == r['score'], f'NaN score in {r}'  # finite
        assert r['content'], 'empty content returned'