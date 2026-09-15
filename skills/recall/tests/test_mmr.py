"""票3：MMR 多样性重排（Ω 门控"信噪比"落地）。

验收口径（.scratch/t3-mmr.md）：
- 纯函数：输入候选+查询向量+λ，输出重排列表
- 近重复候选被压后、互补候选被前提；λ=1 退化为纯相关排序
- 空输入/单条输入安全
- 默认关闭（mmr_lambda=None），关闭时行为逐位等于旧实现
"""
import os
import tempfile

import pytest

from scripts.embedding import EmbeddingClient
from scripts.schema import init_db
from scripts.ingest import ingest_file
from scripts.recall import recall_associative, mmr_rerank


def _v(*xs):
    n = sum(x * x for x in xs) ** 0.5
    return [x / n for x in xs]


# ============================================================
# 纯函数行为
# ============================================================

def test_mmr_empty_and_single():
    assert mmr_rerank([], _v(1, 0), {}, 0.5) == []
    one = [{'chunk_id': 1, 'score': 0.9}]
    assert mmr_rerank(one, _v(1, 0), {1: _v(1, 0)}, 0.5) == one


def test_mmr_lambda_one_is_pure_relevance():
    """λ=1 → 退化为纯相关度降序（等价旧排序）。"""
    cands = [
        {'chunk_id': 1, 'score': 0.5},
        {'chunk_id': 2, 'score': 0.9},
        {'chunk_id': 3, 'score': 0.7},
    ]
    vecs = {1: _v(1, 0), 2: _v(0.9, 0.1), 3: _v(0.8, 0.2)}
    out = mmr_rerank(cands, _v(1, 0), vecs, lambda_mult=1.0)
    assert [c['chunk_id'] for c in out] == [2, 3, 1]


def test_mmr_pushes_near_duplicates_down():
    """对抗核心：2 与 3 几乎同向量（近重复）、都与查询高相关；
    4 相关度略低但方向互补。λ 适中时 4 应挤进第 2 位，压掉冗余的 3。"""
    q = _v(1, 0, 0)
    cands = [
        {'chunk_id': 2, 'score': 0.95},
        {'chunk_id': 3, 'score': 0.90},
        {'chunk_id': 4, 'score': 0.70},
    ]
    vecs = {
        2: _v(0.95, 0.05, 0.0),
        3: _v(0.94, 0.06, 0.0),   # 与 2 近重复
        4: _v(0.70, 0.0, 0.70),   # 互补方向
    }
    out = mmr_rerank(cands, q, vecs, lambda_mult=0.5)
    order = [c['chunk_id'] for c in out]
    assert order[0] == 2
    assert order[1] == 4, "互补候选应挤掉近重复"
    assert order[2] == 3


def test_mmr_deterministic():
    cands = [{'chunk_id': i, 'score': 1.0 - i * 0.1} for i in range(5)]
    vecs = {i: _v(1.0 - i * 0.1, i * 0.1) for i in range(5)}
    q = _v(1, 0)
    a = mmr_rerank(cands, q, vecs, lambda_mult=0.6)
    b = mmr_rerank(cands, q, vecs, lambda_mult=0.6)
    assert [c['chunk_id'] for c in a] == [c['chunk_id'] for c in b]


def test_mmr_k_truncates():
    cands = [{'chunk_id': i, 'score': 1.0 - i * 0.1} for i in range(5)]
    vecs = {i: _v(1.0 - i * 0.1, i * 0.1) for i in range(5)}
    out = mmr_rerank(cands, _v(1, 0), vecs, lambda_mult=0.5, k=2)
    assert len(out) == 2


def test_mmr_missing_vector_falls_back_to_score():
    """候选缺向量 → 按已有 score 参与排序，不崩。"""
    cands = [{'chunk_id': 1, 'score': 0.9}, {'chunk_id': 2, 'score': 0.5}]
    out = mmr_rerank(cands, _v(1, 0), {1: _v(1, 0)}, lambda_mult=0.5)
    assert [c['chunk_id'] for c in out] == [1, 2]


# ============================================================
# 端到端：recall_associative(mmr_lambda)
# ============================================================

class _Dim3Client(EmbeddingClient):
    """把固定文本映射到确定向量；其余文本给正交基（相似度 0）。"""

    def __init__(self, mapping):
        super().__init__(dimension=3)
        self.mapping = mapping

    def embed(self, texts):
        out = []
        for i, t in enumerate(texts):
            if t in self.mapping:
                out.append(list(self.mapping[t]))
                continue
            v = [0.0, 0.0, 0.0]
            v[i % 3] = 1.0
            out.append(v)
        return out


Q = "压力大 怕考砸"


@pytest.fixture
def mmr_db():
    """两条近重复（焦虑A/焦虑B 向量几乎相同）+ 一条互补（运动，方向不同）。"""
    client = _Dim3Client({
        Q: _v(1, 0, 0),
        "焦虑A": _v(0.95, 0.05, 0.0),
        "焦虑B": _v(0.94, 0.06, 0.0),
        "运动": _v(0.75, 0.0, 0.65),
        "压力 焦虑": _v(1, 0, 0),
        "跑步 解压": _v(0, 1, 0),
    })
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        db_path = os.path.join(tmpdir, 'recall.db')
        init_db(db_path)
        entries = [
            ("压力 焦虑", "焦虑A"),
            ("压力 焦虑", "焦虑B"),
            ("跑步 解压", "运动"),
        ]
        for idx, (tags, content) in enumerate(entries):
            fp = os.path.join(tempfile.mkdtemp(), f'd{idx}.md')
            with open(fp, 'w', encoding='utf-8') as f:
                f.write(f"---\nmaid: mira\ncreated: 2026-08-15T10:00:00\n"
                        f"tags: [{tags}]\n---\n{content}\n")
            ingest_file(fp, db_path, client)
            os.unlink(fp)
        yield db_path, client


def test_recall_mmr_default_off_bitwise(mmr_db):
    """默认关闭：与不传参数的旧调用逐位一致。"""
    db_path, client = mmr_db
    old = recall_associative(Q, db_path, client, k=3, tag_weight=1.0,
                             threshold=0.0, time_ratio=0)
    explicit_off = recall_associative(Q, db_path, client, k=3, tag_weight=1.0,
                                      threshold=0.0, time_ratio=0,
                                      mmr_lambda=None)
    assert old == explicit_off


def test_recall_mmr_promotes_complementary(mmr_db):
    """开启后：k=2 时互补的「运动」应挤掉近重复的第二条焦虑。"""
    db_path, client = mmr_db
    plain = recall_associative(Q, db_path, client, k=2, tag_weight=1.0,
                               threshold=0.0, time_ratio=0)
    plain_contents = [r['content'] for r in plain]
    assert '运动' not in plain_contents, "前提：纯相关排序里运动被两条焦虑挤出 top-2"

    reranked = recall_associative(Q, db_path, client, k=2, tag_weight=1.0,
                                  threshold=0.0, time_ratio=0, mmr_lambda=0.5)
    contents = [r['content'] for r in reranked]
    assert '运动' in contents, "MMR 应把互补候选带进 top-2"
