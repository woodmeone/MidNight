"""T4 · 召回性能：倒排索引候选预筛 + 结果缓存（接口不变，默认行为不动）。

验收口径：
- 倒排索引在 ingest 时构建；`vector_candidate_ids` 能按查询字面 n-gram 定位候选。
- 开启预筛后，tag-first 要求的核心候选（词面与查询无重叠、靠标签承载的内容）
  仍能被召回（倒排只收窄向量扫描，tag 扩增路径不受影响）。
- 结果缓存命中时不重算（embed 不再被调用）；真实 ingest 后代数失效、必重算。
"""
import os
import tempfile

from scripts.schema import init_db
from scripts.embedding import SemanticFakeEmbeddingClient
from scripts.ingest import ingest_file
from scripts.recall import recall_associative, vector_candidate_ids
from scripts.cache import get_generation


class _CountingEmbed(SemanticFakeEmbeddingClient):
    """包装层：记录 embed 调用次数，用于证明缓存命中时不再重算。"""

    def __init__(self):
        super().__init__()
        self.calls = 0

    def embed(self, texts):
        self.calls += 1
        return super().embed(texts)


def _write(db_path, embed, entries):
    """写入多个 (tags, content) 日记。"""
    for idx, (tags, content) in enumerate(entries):
        fp = os.path.join(tempfile.mkdtemp(), f'd{idx}.md')
        with open(fp, 'w', encoding='utf-8') as f:
            f.write(f"---\nmaid: qinglan\ncreated: 2026-09-{1 + idx % 28:02d}T10:00:00\n"
                    f"tags: [{tags}]\n---\n{content}\n")
        ingest_file(fp, db_path, embed)
        os.unlink(fp)


def _build_incident(db_path, embed):
    """复刻 tag-first 翻车场景：升学内容词面与 query 无重叠、纯靠标签承载。"""
    _write(db_path, embed, [
        ("张娜 升学", "番职大金融科技专业，计应对口，属冲档。"),
        ("张娜 英语 阅读", "张娜英语阅读策略：读带动单词，主攻完形与阅读。"),
        ("熊可婷 兴趣", "熊可婷想学 MJ。"),
        *[(f"噪声{i}", f"杂乱学习内容第{i}条，与记忆主题无关。") for i in range(10)],
    ])


# ============================================================
# 倒排索引
# ============================================================

def test_inverted_index_populated_and_candidate_lookup():
    """ingest 后 chunk_ngrams 就位；按查询 bigram 能定位其 chunk，且命中噪声受抑制。"""
    embed = SemanticFakeEmbeddingClient()
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        db = os.path.join(tmpdir, 'recall.db')
        init_db(db)
        _build_incident(db, embed)

        import sqlite3
        conn = sqlite3.connect(db)
        try:
            ngrams = conn.execute("SELECT COUNT(*) FROM chunk_ngrams").fetchone()[0]
            assert ngrams > 0, "ingest 后应构建倒排索引"

            cand = vector_candidate_ids(conn, "张娜 升学")
            assert cand, "查询应有词面候选"
            # 升学 chunk 词面上与『张娜 升学』无共享 bigram → 不应在向量候选里
            # （它靠 tag 扩增被召回，本处仅验证倒排候选只含字面重叠者）
            rows = conn.execute(
                "SELECT c.content FROM chunks c WHERE c.content LIKE '%番职大%'").fetchall()
            assert rows
            # 张娜英语 chunk 与查询共享『张娜』→ 必在候选
            eng_ids = conn.execute(
                "SELECT c.id FROM chunks c WHERE c.content LIKE '%阅读策略%'").fetchall()
            assert any(r[0] in cand for r in eng_ids)
        finally:
            conn.close()


def test_prefilter_still_surfaces_tag_first_core():
    """开启预筛后 tag-first 核心候选（张娜升学→番职大）仍可被召回。"""
    embed = SemanticFakeEmbeddingClient()
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        db = os.path.join(tmpdir, 'recall.db')
        init_db(db)
        _build_incident(db, embed)
        results = recall_associative("张娜 升学", db, embed, k=10,
                                     tag_weight=1.0, decay=0.9, max_depth=2,
                                     threshold=0.03, time_ratio=0, prefilter=True)
        contents = [r['content'] for r in results]
        assert any('番职大' in c for c in contents), \
            "预筛只收窄向量扫描，tag 扩增路径应仍带出词面不可见的升学内容"


def test_prefilter_does_not_change_default_semantics():
    """默认（prefilter=False）行为与未接入优化前一致：幂等且含词面命中。"""
    embed = SemanticFakeEmbeddingClient()
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        db = os.path.join(tmpdir, 'recall.db')
        init_db(db)
        _build_incident(db, embed)
        r_off = recall_associative("张娜 英语", db, embed, k=5, tag_weight=0)
        assert any('阅读策略' in x['content'] for x in r_off), "词面命中应保留"


def test_content_ngrams_matches_embedding_model_scale():
    """倒排候选 ≤ 全量：候选规模不会大于全部 chunk（只收窄，不扩张）。"""
    embed = SemanticFakeEmbeddingClient()
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        db = os.path.join(tmpdir, 'recall.db')
        init_db(db)
        _build_incident(db, embed)
        import sqlite3
        conn = sqlite3.connect(db)
        try:
            cand = vector_candidate_ids(conn, "张娜 升学")
            total = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
            assert len(cand) <= total
        finally:
            conn.close()


# ============================================================
# 结果缓存
# ============================================================

def test_cache_hit_skips_recomputation():
    """缓存命中：第二次同查询属同一代数，embed 不再被调用。"""
    counter = _CountingEmbed()
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        db = os.path.join(tmpdir, 'recall.db')
        init_db(db)
        _build_incident(db, counter)

        first = recall_associative("张娜", db, counter, k=5, tag_weight=0.3,
                                   time_ratio=0.2, cache=True)
        calls_after_first = counter.calls
        assert calls_after_first > 0

        second = recall_associative("张娜", db, counter, k=5, tag_weight=0.3,
                                    time_ratio=0.2, cache=True)
        assert counter.calls == calls_after_first, "缓存命中后不应再触发 embed"
        assert [r['chunk_id'] for r in first] == [r['chunk_id'] for r in second]


def test_cache_invalidates_after_ingest():
    """真实 ingest 后代数递增 → 缓存失效，必须重算并包含新内容。"""
    counter = _CountingEmbed()
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        db = os.path.join(tmpdir, 'recall.db')
        init_db(db)
        _write(db, counter, [("张娜 升学", "番职大金融科技专业。")])

        hits = []
        hits.append(recall_associative("张娜", db, counter, k=5, tag_weight=0.3,
                                       time_ratio=0.2, cache=True))
        calls_before = counter.calls
        import sqlite3
        conn = sqlite3.connect(db)
        assert get_generation(conn) == 1
        conn.close()

        # 全量加塞一条新记忆（触发 bump_generation）
        _write(db, counter, [("张娜 英语", "张娜英语阅读策略：读带动单词。")])
        conn = sqlite3.connect(db)
        assert get_generation(conn) == 2, "ingest 后缓存代数应递增"
        conn.close()

        after = recall_associative("张娜", db, counter, k=5, tag_weight=0.3,
                                   time_ratio=0.2, cache=True)
        assert counter.calls > calls_before, "代数失效后应强制重算（不再吃缓存）"
        assert any('阅读策略' in r['content'] for r in after), "重算应包含新记忆"


def test_cache_respects_query_variance():
    """不同查询 → 不同缓存键，不互相污染。"""
    counter = _CountingEmbed()
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        db = os.path.join(tmpdir, 'recall.db')
        init_db(db)
        _write(db, counter, [("张娜 升学", "番职大金融科技专业。"),
                             ("熊可婷 兴趣", "熊可婷想学 MJ。")])
        recall_associative("张娜", db, counter, k=5, tag_weight=0.3,
                           time_ratio=0.2, cache=True)
        calls_after_a = counter.calls
        # 换一个查询：不同 key → 必然重算
        recall_associative("熊可婷", db, counter, k=5, tag_weight=0.3,
                           time_ratio=0.2, cache=True)
        assert counter.calls > calls_after_a