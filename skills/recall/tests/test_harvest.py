"""Tests for the pull-based harvest: Trae session_memory jsonl → recall diaries.

拉取式沉淀：Trae IDE 落盘的会话摘要（intent/actions/outcome/learned）
转换成遵守日记协议的 md 文件并入库。手写日记是主动渠道，本渠道只做补充。

测试纪律：对抗式输入（畸形行/缺字段/幂等重跑）在票2 扩充，
本文件先锁票1 的端到端最小可用。
"""
import json
import os

import pytest

from scripts.embedding import FakeEmbeddingClient
from scripts.schema import init_db
from scripts.recall import recall_associative
from scripts import harvest


def _rec(mid="m1", t="2026-09-08 16:51:17", **kw):
    """构造一条 Trae session_memory 记录（默认值可覆盖）。"""
    base = {
        "intent": "将bge-m3模型放置到指定路径",
        "actions": ["完成模型内置落位", "确认历史记忆完好"],
        "outcome": "模型已成功落位到 skills-library/recall/models/bge-m3/",
        "learned": [
            "模型路径为D:\\Project\\TeacherPipeLine\\skills-library\\recall\\models\\bge-m3\\",
            "模型包含model.onnx、model.onnx_data和tokenizer.json文件",
        ],
        "message_summary_time": t,
        "message_id": mid,
        "compact_summary_meta": {"trigger": "auto", "mode": "async"},
    }
    base.update(kw)
    return base


def _trae_tree(tmp_path, records, project="projA", date="20260908"):
    """在 tmp 里搭一棵假的 Trae 记忆树：<root>/projects/<project>/<date>/session_memory_x.jsonl"""
    d = tmp_path / "projects" / project / date
    d.mkdir(parents=True)
    fp = d / "session_memory_abc.jsonl"
    fp.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in records),
                  encoding="utf-8")
    return tmp_path


class TestParseRecord:
    def test_valid_record(self):
        rec = harvest.parse_trae_record(json.dumps(_rec(), ensure_ascii=False))
        assert rec is not None
        assert rec["message_id"] == "m1"

    def test_malformed_line_returns_none(self):
        assert harvest.parse_trae_record("{not json") is None

    def test_missing_required_field_returns_none(self):
        bad = _rec()
        del bad["message_id"]
        assert harvest.parse_trae_record(json.dumps(bad, ensure_ascii=False)) is None

    def test_empty_learned_and_outcome_returns_none(self):
        """精华缺失（learned 与 outcome 都空）→ 低价值，不采。"""
        rec = _rec(learned=[], outcome="")
        assert harvest.parse_trae_record(json.dumps(rec, ensure_ascii=False)) is None


class TestRecordToDiary:
    def test_frontmatter_has_protocol_fields(self):
        name, content = harvest.record_to_diary(harvest.parse_trae_record(
            json.dumps(_rec(), ensure_ascii=False)), agent="qinglan")
        assert name.endswith(".md")
        assert content.startswith("---\n")
        assert "maid: qinglan" in content
        # created 取真：来自 message_summary_time，转 ISO
        assert "created: 2026-09-08T16:51:17" in content
        assert "tags: [" in content

    def test_tags_only_in_frontmatter(self):
        """正文不得出现 Tag: 行（入库只解析 frontmatter tags）。"""
        _, content = harvest.record_to_diary(harvest.parse_trae_record(
            json.dumps(_rec(), ensure_ascii=False)), agent="qinglan")
        body = content.split("---", 2)[2]
        assert "Tag:" not in body

    def test_tags_extract_anchor_terms(self):
        """技术锚点（bge-m3 / onnx）应进标签，供联想网络连线。"""
        _, content = harvest.record_to_diary(harvest.parse_trae_record(
            json.dumps(_rec(), ensure_ascii=False)), agent="qinglan")
        fm_tags = content.split("tags: [")[1].split("]")[0]
        low = fm_tags.lower()
        assert "bge-m3" in low
        assert len([t for t in fm_tags.split(",") if t.strip()]) <= 6

    def test_body_contains_essence_and_source(self):
        _, content = harvest.record_to_diary(harvest.parse_trae_record(
            json.dumps(_rec(), ensure_ascii=False)), agent="qinglan")
        assert "tokenizer.json" in content          # learned 精华进了正文
        assert "m1" in content                       # 出处 message_id 可溯源

    def test_filename_is_deterministic(self):
        rec = harvest.parse_trae_record(json.dumps(_rec(), ensure_ascii=False))
        n1, _ = harvest.record_to_diary(rec, agent="qinglan")
        n2, _ = harvest.record_to_diary(rec, agent="qinglan")
        assert n1 == n2  # 幂等重跑的前提：同记录同文件名


class TestHarvestEndToEnd:
    def test_dry_run_writes_nothing(self, tmp_path):
        root = _trae_tree(tmp_path, [_rec()])
        out = harvest.harvest_trae(root=str(root), agent="qinglan",
                                  dry_run=True, state_path=str(tmp_path / "state.json"))
        assert out["candidates"] == 1
        assert out["written"] == 0
        assert not (tmp_path / "state.json").exists()

    def test_write_then_recall_hits(self, tmp_path, monkeypatch):
        """端到端最小可用：假 Trae 树 → 生成日记 → ingest → 联想召回命中。"""
        root = _trae_tree(tmp_path, [_rec()])
        diary_dir = tmp_path / "diary"
        db_path = str(tmp_path / "recall.db")
        init_db(db_path)
        client = FakeEmbeddingClient(dimension=16)
        out = harvest.harvest_trae(
            root=str(root), agent="qinglan", dry_run=False,
            state_path=str(tmp_path / "state.json"),
            diary_dir=str(diary_dir), db_path=db_path, client=client)
        assert out["written"] == 1
        assert out["ingested"] == 1
        hits = recall_associative("bge-m3 模型 落位", db_path, client, k=5)
        assert any("bge-m3" in h["content"] for h in hits)

    def test_rerun_is_idempotent(self, tmp_path):
        """水位线：重跑同一棵树，written=0，不产生重复日记。"""
        root = _trae_tree(tmp_path, [_rec()])
        diary_dir = tmp_path / "diary"
        db_path = str(tmp_path / "recall.db")
        init_db(db_path)
        client = FakeEmbeddingClient(dimension=16)
        kw = dict(agent="qinglan", dry_run=False,
                  state_path=str(tmp_path / "state.json"),
                  diary_dir=str(diary_dir), db_path=db_path, client=client)
        harvest.harvest_trae(root=str(root), **kw)
        out2 = harvest.harvest_trae(root=str(root), **kw)
        assert out2["written"] == 0
        assert len([f for f in os.listdir(diary_dir) if f.endswith(".md")]) == 1

    def test_new_record_appended_only(self, tmp_path):
        """增量：树里新增一条记录，第二次跑只写新的一条。"""
        root = _trae_tree(tmp_path, [_rec(mid="m1")])
        diary_dir = tmp_path / "diary"
        db_path = str(tmp_path / "recall.db")
        init_db(db_path)
        client = FakeEmbeddingClient(dimension=16)
        kw = dict(agent="qinglan", dry_run=False,
                  state_path=str(tmp_path / "state.json"),
                  diary_dir=str(diary_dir), db_path=db_path, client=client)
        harvest.harvest_trae(root=str(root), **kw)
        fp = next((tmp_path / "projects" / "projA" / "20260908").glob("*.jsonl"))
        with open(fp, "a", encoding="utf-8") as f:
            f.write("\n" + json.dumps(_rec(mid="m2"), ensure_ascii=False))
        out2 = harvest.harvest_trae(root=str(root), **kw)
        assert out2["written"] == 1
