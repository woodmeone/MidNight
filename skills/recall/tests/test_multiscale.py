"""票2：多尺度线索提取（残差金字塔落地）。

验收口径（.scratch/t2-multiscale.md）：
- multi_scale 默认关闭，关闭时逐位等于旧行为
- 开启时多粒度种子合并激活：藏在句子角落的细线索标签可被独立激活
- 激活总数有界、结果确定性

用脚本化嵌入客户端构造确定性场景：整句向量对目标标签只有弱相似（落入
ghost 带），而某个子粒度短语向量与目标标签向量完全一致 → 多粒度合并后
该标签以 core 满强度激活。
"""
import hashlib
import os
import tempfile

import pytest

from scripts.embedding import EmbeddingClient, SemanticFakeEmbeddingClient
from scripts.schema import init_db
from scripts.ingest import ingest_file
from scripts.recall import recall_associative
from scripts.tag_network import activate_tags, multi_scale_queries


class _ScriptedClient(EmbeddingClient):
    """按文本→向量的精确映射返回向量；未登记的文本给确定性正交基向量。

    用于构造"整句弱命中 / 子粒度强命中"的确定性种子感应场景。
    """

    def __init__(self, mapping, dim=16):
        super().__init__(dimension=dim)
        self.mapping = dict(mapping)
        self.dim = dim

    def embed(self, texts):
        out = []
        for t in texts:
            if t in self.mapping:
                out.append(list(self.mapping[t]))
                continue
            h = hashlib.sha256(str(t).encode('utf-8')).digest()
            v = [0.0] * self.dim
            v[h[0] % self.dim] = 1.0
            out.append(v)
        return out


def _basis(i, dim=16):
    v = [0.0] * dim
    v[i] = 1.0
    return v


E1 = _basis(0)   # 考试
E2 = _basis(1)   # 番职大
# 整句查询：与 考试 强相似(0.9)，与 番职大 弱相似(0.1→ghost 带)
Q_FULL = [0.9, 0.1] + [0.0] * 14
# 子粒度短语：与 番职大 完全一致
Q_SEG = list(E2)


def _write(db_path, embed, entries):
    for idx, (tags, content) in enumerate(entries):
        fp = os.path.join(tempfile.mkdtemp(), f'd{idx}.md')
        with open(fp, 'w', encoding='utf-8') as f:
            f.write(f"---\nmaid: mira\ncreated: 2026-08-15T10:00:00\n"
                    f"tags: [{tags}]\n---\n{content}\n")
        ingest_file(fp, db_path, embed)
        os.unlink(fp)


@pytest.fixture
def scripted_db():
    """考试 chunk 整句强命中；番职大 chunk 整句弱命中、子粒度满命中。"""
    client = _ScriptedClient({
        "考试成绩出来了压力好大，纠结了很久要不要报番职大的金融科技志愿": Q_FULL,
        # 实际拆分的第二粒度（逗号切分的尾段），映射为 番职大 的满相似向量
        "纠结了很久要不要报番职大的金融科技志愿": Q_SEG,
        "考试": E1,
        "番职大": E2,
        "压力": _basis(2),   # 与查询正交，不干扰感应
        "志愿": _basis(3),
        "考试成绩压力大": E1,
        "番职大金融科技志愿": E2,
    })
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        db_path = os.path.join(tmpdir, 'recall.db')
        init_db(db_path)
        _write(db_path, client, [
            ("考试 压力", "考试成绩压力大"),
            ("番职大 志愿", "番职大金融科技志愿"),
        ])
        yield db_path, client


# ============================================================
# 纯函数：query 分解
# ============================================================

def test_decompose_full_text_first():
    scales = multi_scale_queries("压力大 怕考砸")
    assert scales[0] == "压力大 怕考砸"
    assert "压力大" in scales and "怕考砸" in scales


def test_decompose_punctuation_split():
    scales = multi_scale_queries("考试完了，想去旅行；还有面试。")
    assert "考试完了" in scales
    assert "想去旅行" in scales
    assert "还有面试" in scales


def test_decompose_dedup_and_bounded():
    long_q = " ".join([f"片段{i}" for i in range(30)])
    scales = multi_scale_queries(long_q)
    assert len(scales) == len(set(scales)), "不应有重复粒度"
    assert len(scales) <= 8, "粒度总数有界"
    assert scales[0] == long_q


def test_decompose_empty_and_single():
    assert multi_scale_queries("") == []
    assert multi_scale_queries("  ") == []
    assert multi_scale_queries("单一片段") == ["单一片段"]


def test_decompose_deterministic():
    q = "压力大 怕考砸 焦虑失眠"
    assert multi_scale_queries(q) == multi_scale_queries(q)


# ============================================================
# activate_tags：query_vecs 合并感应
# ============================================================

def test_activate_tags_multi_vecs_promotes_buried_tag(scripted_db):
    """核心对抗：整句向量下 番职大 只是 ghost(0.3)；并入子粒度向量后升为 core(1.0)。"""
    db_path, client = scripted_db
    q_vec = client.embed([
        "考试成绩出来了压力好大，纠结了很久要不要报番职大的金融科技志愿"])[0]
    seg_vec = client.embed(["纠结了很久要不要报番职大的金融科技志愿"])[0]

    single = dict(activate_tags(q_vec, db_path, client, max_depth=0,
                                threshold=0.0, query_vecs=[q_vec]))
    multi = dict(activate_tags(q_vec, db_path, client, max_depth=0,
                               threshold=0.0, query_vecs=[q_vec, seg_vec]))

    # 找 番职大 标签 id：名字解析用 tags 表
    import sqlite3
    conn = sqlite3.connect(db_path)
    tid = conn.execute("SELECT id FROM tags WHERE name='番职大'").fetchone()[0]
    eid = conn.execute("SELECT id FROM tags WHERE name='考试'").fetchone()[0]
    conn.close()

    assert single.get(tid) == pytest.approx(0.3), "整句感应应落入 ghost 带"
    assert multi.get(tid) == pytest.approx(1.0), "子粒度并入后应升为 core 满强度"
    assert multi.get(eid) == pytest.approx(single.get(eid)), "既有 core 不受损"


def test_activate_tags_none_vecs_equals_single(scripted_db):
    """query_vecs=None 与 query_vecs=[query_vec] 逐位一致（向后兼容）。"""
    db_path, client = scripted_db
    q_vec = client.embed([
        "考试成绩出来了压力好大，纠结了很久要不要报番职大的金融科技志愿"])[0]
    a = activate_tags(q_vec, db_path, client, max_depth=0, threshold=0.0)
    b = activate_tags(q_vec, db_path, client, max_depth=0, threshold=0.0,
                      query_vecs=[q_vec])
    assert dict(a) == dict(b)


# ============================================================
# 端到端：recall_associative(multi_scale)
# ============================================================

def test_recall_multi_scale_boosts_buried_chunk(scripted_db):
    """开启后，角落细线索 chunk 的召回得分显著高于单尺度。"""
    db_path, client = scripted_db
    q = "考试成绩出来了压力好大，纠结了很久要不要报番职大的金融科技志愿"
    single = recall_associative(q, db_path, client, k=5, tag_weight=1.0,
                                max_depth=0, threshold=0.0, time_ratio=0)
    multi = recall_associative(q, db_path, client, k=5, tag_weight=1.0,
                               max_depth=0, threshold=0.0, time_ratio=0,
                               multi_scale=True)
    s_map = {r['content']: r for r in single}
    m_map = {r['content']: r for r in multi}
    assert "番职大金融科技志愿" in s_map and "番职大金融科技志愿" in m_map
    assert m_map["番职大金融科技志愿"]['score'] > \
        s_map["番职大金融科技志愿"]['score'] * 1.5, "core 提升应显著抬升得分"


def test_recall_multi_scale_default_off_bitwise(scripted_db):
    """默认关闭：与不传参数的旧调用逐位一致。"""
    db_path, client = scripted_db
    q = "考试成绩出来了压力好大，纠结了很久要不要报番职大的金融科技志愿"
    old = recall_associative(q, db_path, client, k=5, tag_weight=1.0,
                             max_depth=0, threshold=0.0, time_ratio=0)
    explicit_off = recall_associative(q, db_path, client, k=5, tag_weight=1.0,
                                      max_depth=0, threshold=0.0, time_ratio=0,
                                      multi_scale=False)
    assert old == explicit_off


def test_recall_multi_scale_bounded_activation(scripted_db):
    """激活总数有界：多尺度不得让激活标签数爆量（core+ghost 上限不变）。"""
    db_path, client = scripted_db
    q = "考试成绩出来了压力好大，纠结了很久要不要报番职大的金融科技志愿"
    single = recall_associative(q, db_path, client, k=5, tag_weight=1.0,
                                threshold=0.0, time_ratio=0)
    multi = recall_associative(q, db_path, client, k=5, tag_weight=1.0,
                               threshold=0.0, time_ratio=0, multi_scale=True)
    assert len(multi) == len(single) <= 5, "k 截断不因多尺度改变"
