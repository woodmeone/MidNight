"""Iter-2 联想效果增强：A 检索回馈强化 / B 激活标签向量再扩散 / C 多跳深度衰减。

全部为**默认关闭**的新能力：默认路径（expand_neighbors=False、depth_decay=1.0、
feedback 独立调用）与既有行为逐位一致，不破坏任何现有记忆/接口。
空白题先写（red），再看实现（green）。
"""
import os
import tempfile
import sqlite3

from scripts.schema import init_db
from scripts.embedding import SemanticFakeEmbeddingClient
from scripts.ingest import ingest_file
from scripts.recall import feedback_reward
from scripts.tag_network import activate_tags, tags_for_activated


class _ExactSemanticFake(SemanticFakeEmbeddingClient):
    """无哈希碰撞的精确 token 袋嵌入：不相交文本的余弦精确≈0。"""
    FEATURE_DIM = 200000


def _p(path, content):
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)


def _write_0301(db, embed, entries):
    """entries: list of (tags_str, body) → 写独立日记文件并 ingest。"""
    for i, (tags, body) in enumerate(entries):
        fp = os.path.join(tempfile.mkdtemp(), f'd{i}.md')
        _p(fp, f"---\nmaid: qinglan\ncreated: 2026-08-{1 + i % 28:02d}T10:00:00\n"
               f"tags: [{tags}]\n---\n{body}\n")
        ingest_file(fp, db, embed)
        os.unlink(fp)


def _tag_id(conn, name):
    return conn.execute("SELECT id FROM tags WHERE name = ?", (name,)).fetchone()[0]


def _edge_w(conn, src, dst):
    r = conn.execute("SELECT weight FROM tag_edges WHERE tag_from_id=? AND tag_to_id=?",
                     (src, dst)).fetchone()
    return r[0] if r else None


# ============================================================
# A · 检索回馈强化：命中 → 相关边 +Δ / access 记一笔，不新建边、不影响冷门边
# ============================================================

def test_feedback_rewars_hit_edges_access_and_spares_cold_ones():
    """命中升学 chunk 后：升学相关边增强、命中 chunk access 记录；未使用边不变、资产不新增。"""
    embed = SemanticFakeEmbeddingClient()
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        db = os.path.join(td, 'recall.db')
        init_db(db)
        _write_0301(db, embed, [
            ("张娜 升学", "番职大金融科技专业，计应对口，属冲档。"),
            ("张娜 英语", "张娜英语阅读策略，读带动单词。"),
        ])
        conn = sqlite3.connect(db)
        shengxue_cid = conn.execute(
            "SELECT c.id FROM chunks c WHERE c.content LIKE '%番职大%'").fetchone()[0]
        yingyu_cid = conn.execute(
            "SELECT c.id FROM chunks c WHERE c.content LIKE '%阅读策略%'").fetchone()[0]

        w_zs_sx_before = _edge_w(conn, _tag_id(conn, '张娜'), _tag_id(conn, '升学'))
        w_zs_yy_before = _edge_w(conn, _tag_id(conn, '张娜'), _tag_id(conn, '英语'))
        acc_before = conn.execute(
            "SELECT access_count FROM chunks WHERE id=?", (shengxue_cid,)).fetchone()[0]
        n_edges_before = conn.execute("SELECT COUNT(*) FROM tag_edges").fetchone()[0]
        conn.close()

        r = feedback_reward(db, [shengxue_cid], delta=0.1)

        conn = sqlite3.connect(db)
        # 命中 chunk：access 记一笔
        assert conn.execute("SELECT access_count FROM chunks WHERE id=?",
                            (shengxue_cid,)).fetchone()[0] > acc_before
        # 升学相关边（张娜→升学）被增强
        w_zs_sx_after = _edge_w(conn, _tag_id(conn, '张娜'), _tag_id(conn, '升学'))
        assert w_zs_sx_after > w_zs_sx_before, "命中路径上的边应被强化"
        # 未使用边（张娜→英语）不动
        w_zs_yy_after = _edge_w(conn, _tag_id(conn, '张娜'), _tag_id(conn, '英语'))
        assert w_zs_yy_after == w_zs_yy_before, "未命中的边不应被回馈"
        conn.close()
        assert r['edges_rewarded'] > 0 and r['chunks_touched'] == 1 and r['access'] == 1
        assert not r['edges_created'], "回馈只强化已有边，绝不新建"


def test_feedback_never_creates_new_edges_or_rows():
    """对抗：回馈后 tag_edges / tag_cooccurrence 的行数不变（只 UPDATE，不 INSERT）。"""
    embed = SemanticFakeEmbeddingClient()
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        db = os.path.join(td, 'recall.db')
        init_db(db)
        _write_0301(db, embed, [("张娜 升学", "番职大金融科技专业。")])
        conn = sqlite3.connect(db)
        cid = conn.execute("SELECT id FROM chunks LIMIT 1").fetchone()[0]
        e_before = conn.execute("SELECT COUNT(*) FROM tag_edges").fetchone()[0]
        c_before = conn.execute("SELECT COUNT(*) FROM tag_cooccurrence").fetchone()[0]
        conn.close()

        feedback_reward(db, [cid], delta=100.0, reward_cap=1e6)

        conn = sqlite3.connect(db)
        assert conn.execute("SELECT COUNT(*) FROM tag_edges").fetchone()[0] == e_before
        assert conn.execute("SELECT COUNT(*) FROM tag_cooccurrence").fetchone()[0] == c_before
        conn.close()


def test_feedback_cap_prevents_unbounded_explosion():
    """对抗：重复回馈被 reward_cap 封顶，单条边不会无界膨胀（对应 VCP「破坏」痛点）。"""
    embed = SemanticFakeEmbeddingClient()
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        db = os.path.join(td, 'recall.db')
        init_db(db)
        _write_0301(db, embed, [("张娜 升学", "番职大金融科技专业。"), ("张娜 英语", "阅读带单词。")])
        conn = sqlite3.connect(db)
        cid = conn.execute("SELECT id FROM chunks WHERE content LIKE '%番职大%'").fetchone()[0]
        conn.close()

        for _ in range(50):
            feedback_reward(db, [cid], delta=1.0, reward_cap=2.0)

        conn = sqlite3.connect(db)
        w = _edge_w(conn, _tag_id(conn, '张娜'), _tag_id(conn, '升学'))
        conn.close()
        assert w <= 2.0 + 1e-6, "奖励应被 cap 封顶，不随次数无限增长"


# ============================================================
# B · 激活标签向量再扩散：词面不同但向量相近的旁支标签，可被 soft 激活
# ============================================================

def test_neighbor_expansion_drags_similar_tag_in_only_when_enabled():
    """「与某激活种子向量近、但既不贴近查询、也无直达边」的旁支，仅开启邻居扩散才被捕获。

    构造：query『甲迅』激活『甲迅』(core)，『迅步』与它共享"迅"故为 ghost 种子；
    『步语』与『迅步』共享"步"(sim≈1/3)，但与 query『甲迅』无共享字(sim≈0)、亦无直达边。
    → 默认路径绝不会看到『步语』；开启邻居扩散后经『迅步』soft 激活。
    """
    embed = _ExactSemanticFake()
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        db = os.path.join(td, 'recall.db')
        init_db(db)
        # 分开单文件 → 互相无 tag_edge（杜绝直达边污染）
        _write_0301(db, embed, [
            ("甲迅", "起点路线。"),
            ("迅步", "相邻的记忆。"),
            ("步语", "隔着一步的旁支。"),
        ])
        conn = sqlite3.connect(db)
        nid = _tag_id(conn, '步语')
        conn.close()

        qv = embed.embed(["甲迅"])[0]
        default_activated = activate_tags(qv, db, embed, max_depth=2, threshold=0.01)
        assert not any(tid == nid for tid, _ in default_activated), \
            "默认绝不能因向量相近就乱带入旁支（且无直达边）"

        expanded = activate_tags(qv, db, embed, max_depth=2, threshold=0.01,
                                 expand_neighbors=True, neighbor_cap=2)
        assert any(tid == nid for tid, _ in expanded), "开启邻居扩散后应 soft 激活相似旁支"


# ============================================================
# C · 多跳深度衰减：depth_decay<1 时二跳被额外削弱，1 跳不受影响
# ============================================================

def test_depth_decay_weakens_second_hop_only():
    """A→B→C 两跳（B、C 与查询无共享字 → 纯边/D 链可达，非 ghost 种子）：
    depth_decay<1 只削弱 C（第 2 跳），B（第 1 跳）逐位不变。"""
    embed = _ExactSemanticFake()
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        db = os.path.join(td, 'recall.db')
        init_db(db)
        # 甲卡→乙鞠（file1），乙鞠→丙翼（file2）→ 甲卡到丙翼恰为 2 跳；
        # 乙鞠/丙翼 与查询『甲卡』无共享字 → 不成为 ghost 种子，仅靠边到达。
        _write_0301(db, embed, [
            ("甲卡 乙鞠", "第一段。"),
            ("乙鞠 丙翼", "第二段。"),
        ])
        qv = embed.embed(["甲卡"])[0]

        act_default = {t[0]: t[1] for t in activate_tags(
            qv, db, embed, max_depth=2, threshold=0.01)}
        act_shallow = {t[0]: t[1] for t in activate_tags(
            qv, db, embed, max_depth=2, threshold=0.01, depth_decay=0.5)}

        conn = sqlite3.connect(db)
        b, c = _tag_id(conn, '乙鞠'), _tag_id(conn, '丙翼')
        conn.close()

        assert b in act_default and c in act_default, "两跳默认都应可达"
        # B 第 1 跳：depth_decay^(1-1)=1 → 逐位不受影响
        assert abs(act_shallow.get(b, 0) - act_default.get(b, 0)) < 1e-9
        # C 第 2 跳：被 depth_decay 额外削弱
        assert act_shallow.get(c, 0) < act_default.get(c, 0), "二跳应被额外削弱"
        assert act_default.get(c, 0) < abs(act_default.get(b, 0)), "1 跳仍应强于 2 跳"