"""票2：harvest 对抗式健壮性测试。

思路：逆向想"什么输入能让转换内核崩、写错位置、或污染记忆库"——
文件名注入、类型错乱、状态损坏、超长文本、空目录。
每条对抗测试先假设实现是错的，跑不绿就修实现。
"""
import json
import os

from scripts.embedding import FakeEmbeddingClient
from scripts.schema import init_db
from scripts.recall import recall_associative
from scripts import harvest

from test_harvest import _rec, _trae_tree  # noqa: E402  复用票1 fixture 助手


class TestAdversarialParsing:
    def test_learned_wrong_types_survives(self):
        """learned 是字符串/含非字符串项 → 不崩，能过滤。"""
        rec = harvest.parse_trae_record(json.dumps(
            _rec(learned="纯字符串不是列表"), ensure_ascii=False))
        assert rec is not None and rec['learned'] == []
        rec2 = harvest.parse_trae_record(json.dumps(
            _rec(learned=[None, 123, "有效经验一条"]), ensure_ascii=False))
        assert rec2['learned'] == ["有效经验一条"]

    def test_actions_none_yields_empty(self):
        rec = harvest.parse_trae_record(json.dumps(
            _rec(actions=None), ensure_ascii=False))
        assert rec['actions'] == []

    def test_weird_timestamp_passes_through(self):
        """时间格式异常不崩，原样进 created（取真原则：不臆造修正）。"""
        rec = harvest.parse_trae_record(json.dumps(
            _rec(t="2026-09-08"), ensure_ascii=False))
        name, content = harvest.record_to_diary(rec, agent="qinglan")
        assert "created: 2026-09-08" in content

    def test_blank_line_in_jsonl_skipped(self):
        assert harvest.parse_trae_record("   ") is None
        assert harvest.parse_trae_record("") is None
        assert harvest.parse_trae_record("[1,2,3]") is None  # JSON 但不是 dict


class TestAdversarialFilesystem:
    def test_message_id_with_path_separators_is_sanitized(self):
        """文件名注入对抗：message_id 含 ../ \\ / → 产物必须落在 diary_dir 内。"""
        rec = harvest.parse_trae_record(json.dumps(
            _rec(mid="../../evil\\id"), ensure_ascii=False))
        name, _ = harvest.record_to_diary(rec, agent="qinglan")
        assert "/" not in name and "\\" not in name
        assert ".." not in name
        assert name.endswith(".md")

    def test_duplicate_message_id_written_once(self, tmp_path):
        """同一 message_id 出现两次 → 水位线只采第一条。"""
        root = _trae_tree(tmp_path, [_rec(mid="dup1"), _rec(mid="dup1", outcome="第二条")])
        diary_dir = tmp_path / "diary"
        db_path = str(tmp_path / "recall.db")
        init_db(db_path)
        harvest.harvest_trae(root=str(root), agent="qinglan", dry_run=False,
                             state_path=str(tmp_path / "state.json"),
                             diary_dir=str(diary_dir), db_path=db_path,
                             client=FakeEmbeddingClient(dimension=16))
        assert len([f for f in os.listdir(diary_dir) if f.endswith(".md")]) == 1

    def test_corrupt_state_falls_back_to_ingest_idempotency(self, tmp_path):
        """state.json 损坏 → 水位线清空，但确定性文件名 + ingest checksum
        双保险：日记不重复、库不重复。"""
        root = _trae_tree(tmp_path, [_rec()])
        diary_dir = tmp_path / "diary"
        db_path = str(tmp_path / "recall.db")
        init_db(db_path)
        client = FakeEmbeddingClient(dimension=16)
        kw = dict(agent="qinglan", dry_run=False,
                  state_path=str(tmp_path / "state.json"),
                  diary_dir=str(diary_dir), db_path=db_path, client=client)
        harvest.harvest_trae(root=str(root), **kw)
        (tmp_path / "state.json").write_text("{corrupt", encoding="utf-8")
        out = harvest.harvest_trae(root=str(root), **kw)
        assert out["written"] == 1  # 重新生成同名文件（覆盖，非新文件）
        files = [f for f in os.listdir(diary_dir) if f.endswith(".md")]
        assert len(files) == 1
        # 库里不产生重复 chunk
        import sqlite3
        conn = sqlite3.connect(db_path)
        assert conn.execute("SELECT COUNT(*) FROM files").fetchone()[0] == 1
        conn.close()

    def test_nonexistent_root_yields_zero(self, tmp_path):
        out = harvest.harvest_trae(root=str(tmp_path / "nope"), agent="qinglan",
                                   dry_run=True, state_path=str(tmp_path / "s.json"))
        assert out["candidates"] == 0


class TestAdversarialContent:
    def test_oversized_learned_truncated(self):
        """超长 learned → 日记正文有上限，不把库撑爆。"""
        rec = harvest.parse_trae_record(json.dumps(
            _rec(learned=["长" * 5000] * 5), ensure_ascii=False))
        _, content = harvest.record_to_diary(rec, agent="qinglan")
        assert len(content) <= harvest.MAX_DIARY_CHARS

    def test_no_tags_still_valid_frontmatter(self):
        """全空白/无锚点文本 → tags 允许为空但 frontmatter 结构不破。"""
        rec = harvest.parse_trae_record(json.dumps(
            _rec(intent="。", outcome="。", learned=["。"]), ensure_ascii=False))
        _, content = harvest.record_to_diary(rec, agent="qinglan")
        assert content.startswith("---\n")
        assert "tags: [" in content


class TestScopeControl:
    def test_project_filter_limits_scope(self, tmp_path):
        """作用域控制：--project 子串过滤，跨项目记忆不混入。"""
        _trae_tree(tmp_path, [_rec(mid="in1")], project="projA-TeacherPipeLine")
        _trae_tree(tmp_path, [_rec(mid="out1")], project="projB-OtherRepo")
        recs = list(harvest.iter_trae_records(str(tmp_path), project_filter="TeacherPipeLine"))
        assert [r["message_id"] for r in recs] == ["in1"]

    def test_harvested_diary_is_low_importance(self):
        """补充渠道定位：拉取日记 importance=low，召回天然让位手写。"""
        rec = harvest.parse_trae_record(json.dumps(_rec(), ensure_ascii=False))
        _, content = harvest.record_to_diary(rec, agent="qinglan")
        assert "importance: low" in content


class TestRecallQuality:
    def test_harvested_diary_recallable_by_topic(self, tmp_path):
        """召回验证：拉取入库的日记，能被同话题的自然语言查询召回。"""
        root = _trae_tree(tmp_path, [
            _rec(mid="r1", intent="修复 B 站字幕轮询 412 风控崩溃",
                 outcome="给 _run 加退避重试容错",
                 learned=["BcutASR 轮询遇瞬时 412 会 raise_for_status 崩掉整段，需退避重试"]),
            _rec(mid="r2", intent="无关内容：烘焙蛋糕配方",
                 outcome="成功", learned=["面粉过筛两次更松软"]),
        ])
        diary_dir = tmp_path / "diary"
        db_path = str(tmp_path / "recall.db")
        init_db(db_path)
        client = FakeEmbeddingClient(dimension=16)
        harvest.harvest_trae(root=str(root), agent="qinglan", dry_run=False,
                             state_path=str(tmp_path / "state.json"),
                             diary_dir=str(diary_dir), db_path=db_path, client=client)
        hits = recall_associative("412 风控 重试", db_path, client, k=5)
        assert hits
        top = hits[0]["content"]
        assert "412" in top or "重试" in top
