"""T3: A 联想深化 (VCP TagMemo §A1–A5) — 方向边 / log压缩 / 枢纽校正 / 预算守恒 / Core-Ghost 预感应。

验收口径（OPTIMIZATION-SPEC §5）：
- 深联想回归: 「压力大 怕考砸」应经 log压缩+枢纽校正 深联想 雅思（而非被高频枢纽词「考试」吞）。
- 接口 recall_associative 不变；旧测试全绿。

用 SemanticFakeEmbeddingClient：字符重叠决定相似度，种子感应确定性。
"""
import os
import tempfile
import sqlite3

import pytest

from scripts.embedding import SemanticFakeEmbeddingClient, FakeEmbeddingClient
from scripts.schema import init_db
from scripts.ingest import ingest_file
from scripts.recall import recall_associative
from scripts.tag_network import (
    activate_tags, tags_for_activated,
    _compressed_weight, _hub_scale,
)


@pytest.fixture
def embed():
    return SemanticFakeEmbeddingClient()


class _ExactSemanticFake(SemanticFakeEmbeddingClient):
    """无哈希碰撞的精确 token 袋嵌入。

    FEATURE_DIM 极大 → 不同 token 几乎不会碰撞到同一维度，
    不相交文本的余弦相似度精确≈0。用于构造确定性的 core/ghost 带
    与「深链 chunk 对向量完全不可见」的场景。
    """
    FEATURE_DIM = 200000


def _write(db_path, embed, entries):
    """Write each (tags, content) into a unique file and ingest it."""
    for idx, (tags, content) in enumerate(entries):
        fp = os.path.join(tempfile.mkdtemp(), f'd{idx}.md')
        with open(fp, 'w', encoding='utf-8') as f:
            f.write(f"---\nmaid: mira\ncreated: 2026-08-15T10:00:00\n"
                    f"tags: [{tags}]\n---\n{content}\n")
        ingest_file(fp, db_path, embed)
        os.unlink(fp)


@pytest.fixture
def deep_db(embed):
    """「考试」是高濒枢纽词；深链 压力→紧张→雅思 存在。

    雅思 chunk 内容刻意不含 query 词（压/力/大/怕/考/砸），保证纯向量排不到它。
    """
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        db_path = os.path.join(tmpdir, 'recall.db')
        init_db(db_path)
        entries = [
            ("考试 压力 焦虑", "下周要数学考试，压力很大，晚上睡不着。"),
            ("考试 压力 天气", "考试周下雨，压力大。"),
            ("考试 压力 工作", "白天上班累，晚上还要备考，压力大。"),
            ("考试 压力 吃饭", "压力大的时候没胃口，但考试前还是得吃饭。"),
            ("考试 压力 通勤", "考试那几天通勤要一小时，压力大。"),
            ("考试 购物", "考试前买了新文具。"),
            ("考试 音乐", "复习考试时喜欢听轻音乐。"),
            ("考试 电影", "考完试想去看电影。"),
            ("考试 健身", "备考期间坚持健身。"),
            ("考试 阅读", "备考间隙会读点书。"),
            ("考试 写作", "备考也在练写作。"),
            ("压力 紧张 烦躁", "最近压力大，晚上烦躁，静不下来。"),
            ("紧张 雅思 听力", "雅思口试时容易紧张，答错就慌神。"),
        ]
        _write(db_path, embed, entries)
        yield db_path


@pytest.fixture
def expansion_db():
    """深链 chunk 词面上与 query 无重叠，向量排名沉底，靠候选扩增被召回。

    用无碰撞嵌入：雅思 chunk 对 query 相似度精确为 0，落在所有向量候选之后。
    前面 5 条高相似填充 chunk 占满向量 top-k；10 条无关噪声；深链 chunk 放最后。
    """
    embed = _ExactSemanticFake()
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        db_path = os.path.join(tmpdir, 'recall.db')
        init_db(db_path)
        entries = [
            ("考试 压力 焦虑", "下周要考试，压力很大。"),
            ("压力 紧张 烦躁", "压力大，晚上烦躁，静不下来。"),
            ("压力 冥想", "压力大的时候就深呼吸。"),
            ("考试 冲刺", "考前冲刺复习，压力很大。"),
            ("失眠 压力", "压力一大就失眠。"),
            *[(f"主题{i} 细节{i}", f"无关内容第{i}条，与查询毫无关系。") for i in range(10)],
            ("紧张 雅思", "雅思口试时容易紧张，答错就慌神。"),
        ]
        _write(db_path, embed, entries)
        yield db_path, embed


# ============================================================
# A1 有序双向边
# ============================================================

def test_ordered_edges_forward_stronger(deep_db):
    """同文件 tag 按出现序建方向边：顺流(前→后) > 逆流(后→前)。"""
    conn = sqlite3.connect(deep_db)
    fwd = conn.execute("""
        SELECT e.weight FROM tag_edges e
        JOIN tags a ON e.tag_from_id = a.id
        JOIN tags b ON e.tag_to_id = b.id
        WHERE a.name = '考试' AND b.name = '压力'
    """).fetchone()
    rev = conn.execute("""
        SELECT e.weight FROM tag_edges e
        JOIN tags a ON e.tag_from_id = a.id
        JOIN tags b ON e.tag_to_id = b.id
        WHERE a.name = '压力' AND b.name = '考试'
    """).fetchone()
    conn.close()
    assert fwd and rev, "方向边应双向写入"
    assert rev[0] > 0
    assert fwd[0] > rev[0], "顺流应强于逆流"
    # 方向阻尼 guard：逆流占比受限（1.0 / 0.4 = 2.5 倍以内）
    assert fwd[0] / rev[0] < 2.6


# ============================================================
# A2 累计证据压缩 / A3 入流枢纽校正（纯函数）
# ============================================================

def test_log_compression_sublinear():
    """边权 e=log(1+λ·W) 亚线性：证据翻倍/百倍不翻倍权重，防高频垄断。"""
    e1 = _compressed_weight(1.0)
    e2 = _compressed_weight(2.0)
    e100 = _compressed_weight(100.0)
    assert _compressed_weight(0.0) == 0.0
    assert e2 > e1
    assert e2 < 2 * e1, "2倍证据不应有2倍权重"
    assert e100 < 100 * e1, "100倍证据远低于100倍权重"


def test_hub_correction_shrinks_high_inflow():
    """入流枢纽校正：目标节点全图入流越大，边增益越被幂律缩降。"""
    assert _hub_scale(0.0) == 1.0
    assert _hub_scale(0.5) > _hub_scale(5.0) > _hub_scale(50.0)
    assert 0.0 < _hub_scale(1e6) < 0.05


# ============================================================
# A4 预算守恒传播
# ============================================================

def test_budget_conservation_bounds_energy(deep_db, embed):
    """预算守恒：传播总激活强度随深度有界，不无限累。"""
    query_vec = embed.embed(["压力"])[0]
    d2 = activate_tags(query_vec, deep_db, embed, decay=0.5, max_depth=2, threshold=0.0)
    d4 = activate_tags(query_vec, deep_db, embed, decay=0.5, max_depth=4, threshold=0.0)
    s2 = sum(s for _, s in d2)
    s4 = sum(s for _, s in d4)
    assert s2 > 0 and s4 > 0
    assert s4 < s2 * 2.5, "更深传播不应显著放大总能量（每跳至多 decay）"


# ============================================================
# A5 Core/Ghost 预感应
# ============================================================

def test_core_ghost_pre_sensing_band():
    """Core/Ghost 分层：强相似=core(1.0)，弱相似=ghost(0.3)，无关不激活。

    用无碰撞嵌入精确构造：query 长、含 1 个共享 token 的弱候选落入 ghost 带。
    """
    embed = _ExactSemanticFake()
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        db = os.path.join(tmpdir, 'r.db')
        init_db(db)
        _write(db, embed, [
            ("考试", "考试内容。"),
            ("测试今天天气", "测试内容。"),
            ("无关内容", "完全无关内容。"),
        ])
        query_vec = embed.embed(["考试压力焦虑失眠音乐"])[0]
        activated = activate_tags(query_vec, db, embed, max_depth=0, threshold=0.0)
    names = {t['name']: t['strength'] for t in tags_for_activated(activated, db)}
    assert names.get('考试') == 1.0, "强相似 tag 应为 core 满强度"
    assert names.get('测试今天天气') == 0.3, "弱相似 tag 应为 ghost 强度"
    assert '无关内容' not in names, "相似度为 0 的无关 tag 不应被激活"


# ============================================================
# 深联想回归：hub 不吞深链
# ============================================================

def test_hub_does_not_swallow_ielts(deep_db, embed):
    """引擎层：「压力大 怕考砸」深联想激活雅思，且不被枢纽「考试」吞没。"""
    query_vec = embed.embed(["压力大 怕考砸"])[0]
    activated = activate_tags(query_vec, deep_db, embed,
                              decay=0.9, max_depth=3, threshold=0.03)
    smap = {t['name']: t['strength'] for t in tags_for_activated(activated, deep_db)}
    assert '考试' in smap, "枢纽考试应被激活"
    assert '紧张' in smap, "中间节点紧张应被激活"
    assert '雅思' in smap, "深链雅思应被激活"
    assert smap['雅思'] > 0.05 * smap['考试'], "雅思激活不应被高频词吞到可忽略"


def test_deep_association_surfaces_ielts(deep_db, embed):
    """端到端：recall_associative 召回含雅思的日记（词面上与 query 无重叠）。"""
    results = recall_associative("压力大 怕考砸", deep_db, embed,
                                 k=20, tag_weight=1.0, decay=0.9,
                                 max_depth=3, threshold=0.03, time_ratio=0)
    assert results
    contents = [r['content'] for r in results]
    assert any('雅思' in c for c in contents), "深联想应带出雅思内容"


def test_pure_vector_misses_deep_association(deep_db, embed):
    """对照：纯向量（无联想）在合理 k 内召回不到雅思。"""
    shallow = recall_associative("压力大 怕考砸", deep_db, embed, k=10, tag_weight=0)
    shallow_contents = [r['content'] for r in shallow]
    assert not any('雅思' in c for c in shallow_contents), "纯向量不应跨词面联想出雅思"


def test_candidate_expansion_rescues_deep_chunk(expansion_db):
    """候选扩增：深链 chunk 落在向量 top-k 之外，仍能被联想扩增召回。"""
    db_path, embed = expansion_db
    results = recall_associative("压力大 怕考砸", db_path, embed,
                                 k=8, tag_weight=1.0, decay=0.9,
                                 max_depth=3, threshold=0.03, time_ratio=0)
    contents = [r['content'] for r in results]
    assert any('雅思' in c for c in contents), "深链 chunk 应经候选扩增进入 top-k"
    # 且不被无关噪声（无激活 tag）挤出
    assert any('雅思' in c for c in contents[:6]), "深链 chunk 应排在噪声之上"


def test_candidate_expansion_differential(expansion_db):
    """对照：同一 k 下纯向量召回不到深链 chunk。"""
    db_path, embed = expansion_db
    shallow = recall_associative("压力大 怕考砸", db_path, embed, k=8, tag_weight=0)
    shallow_contents = [r['content'] for r in shallow]
    assert not any('雅思' in c for c in shallow_contents), "纯向量在top-k内不应含深链chunk"
