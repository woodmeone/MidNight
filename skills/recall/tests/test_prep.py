"""票4：prep_for_reply 可移植核心 + 薄 CLI。

验收口径（.scratch/t4-prep-core.md）：
- 门控：触发词命中必召回；纯寒暄短消息不召回；可注入时钟做确定性测试
- query=None 用原话；显式 query 优先（AI 定语义的 A 左接口）
- 编排：门控→取 query→联想召回→去重→MMR→预算→格式化文本；输出文本块+结构化结果
- 核心不依赖 SKILL.md 提示词逻辑、不 import 运行时/框架代码
"""
import os
import tempfile

import pytest

from scripts.embedding import EmbeddingClient
from scripts.schema import init_db
from scripts.ingest import ingest_file
from scripts.prep import prep_for_reply, should_recall


def _v(*xs):
    n = sum(x * x for x in xs) ** 0.5
    return [x / n for x in xs]


class _Dim3Client(EmbeddingClient):
    """固定文本→确定向量；其余文本给正交基。"""

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


CLIENT = _Dim3Client({
    "我压力好大": _v(1, 0, 0),
    "焦虑": _v(0.9, 0.1, 0),
    "跑步": _v(0, 1, 0),
    "跑步 解压": _v(0, 1, 0),
    "番职大 金融科技": _v(0, 0, 1),
})


@pytest.fixture
def prep_db():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        db_path = os.path.join(tmpdir, 'recall.db')
        init_db(db_path)
        entries = [
            ("焦虑", "那段时间特别焦虑，睡眠很差"),
            ("跑步", "开始跑步之后状态好了很多"),
            ("番职大 金融科技", "纠结了很久要不要报番职大的金融科技志愿"),
        ]
        for idx, (tags, content) in enumerate(entries):
            fp = os.path.join(tempfile.mkdtemp(), f'd{idx}.md')
            with open(fp, 'w', encoding='utf-8') as f:
                f.write(f"---\nmaid: mira\ncreated: 2026-08-15T10:00:00\n"
                        f"tags: [{tags}]\n---\n{content}\n")
            ingest_file(fp, db_path, CLIENT)
            os.unlink(fp)
        yield db_path


# ============================================================
# 门控（确定性：注入时钟，不读真实时间）
# ============================================================

def test_gate_trigger_words_force_recall():
    assert should_recall("还记得吗") is True
    assert should_recall("帮我回忆一下") is True
    assert should_recall("我上次说过什么") is True


def test_gate_greeting_and_short_skip():
    assert should_recall("你好") is False
    assert should_recall("Hi") is False
    assert should_recall("嗯嗯") is False
    assert should_recall("") is False
    assert should_recall("   ") is False


def test_gate_substantive_message_passes():
    assert should_recall("我最近压力好大，晚上总是睡不好") is True


def test_gate_cooldown_uses_injected_clock():
    """冷却期内不召回；冷却结束恢复召回。时钟显式注入，测试确定。"""
    msg = "我们继续聊聊项目排期的事情"
    assert should_recall(msg, now=100.0, last_recall_ts=50.0,
                         cooldown_seconds=100.0) is False
    assert should_recall(msg, now=200.0, last_recall_ts=50.0,
                         cooldown_seconds=100.0) is True


def test_gate_trigger_beats_cooldown():
    """触发词命中必召回——冷却也拦不住。"""
    assert should_recall("还记得吗", now=10.0, last_recall_ts=0.0,
                         cooldown_seconds=9999.0) is True


# ============================================================
# prep_for_reply 编排
# ============================================================

def test_prep_gated_returns_empty(prep_db):
    out = prep_for_reply("你好", db_path=prep_db, embedding_client=CLIENT)
    assert out['recalled'] is False
    assert out['text'] == ""
    assert out['results'] == []


def test_prep_force_bypasses_gate(prep_db):
    out = prep_for_reply("你好", db_path=prep_db, embedding_client=CLIENT,
                         force=True, query="我压力好大")
    assert out['recalled'] is True
    assert "[回忆]" in out['text']


def test_prep_end_to_end_injects_full_memories(prep_db):
    out = prep_for_reply("我压力好大", db_path=prep_db, embedding_client=CLIENT)
    assert out['recalled'] is True
    assert "[回忆]" in out['text']
    assert "焦虑" in out['text']
    # 结构化结果供未来 hook 直接消费
    assert all('chunk_id' in r and 'content' in r for r in out['results'])
    # 完整注入：正文不拦腰截断
    for r in out['results']:
        assert r['content'] in out['text']


def test_prep_explicit_query_wins_over_user_msg(prep_db):
    """A 左接口：AI 判断的语义（query）优先于用户原话。"""
    out = prep_for_reply("我们随便聊点别的什么好呢", db_path=prep_db,
                         embedding_client=CLIENT, query="跑步 解压")
    assert out['recalled'] is True
    assert "跑步" in out['text']


def test_prep_budget_keeps_top1_whole(prep_db):
    """预算极小：至少完整注入最相关一条，绝不返回空、绝不截半句。"""
    out = prep_for_reply("我压力好大", db_path=prep_db,
                         embedding_client=CLIENT, budget_chars=1)
    assert out['recalled'] is True
    assert len(out['results']) >= 1
    top = out['results'][0]
    assert top['content'] in out['text']


def test_prep_mmr_passthrough_diversifies(prep_db):
    """透传票3：开 MMR 不崩、仍返回合法结构。"""
    out = prep_for_reply("我压力好大", db_path=prep_db,
                         embedding_client=CLIENT, mmr_lambda=0.5)
    assert out['recalled'] is True
    assert isinstance(out['results'], list)


def test_prep_multi_scale_passthrough(prep_db):
    out = prep_for_reply("我压力好大", db_path=prep_db,
                         embedding_client=CLIENT, multi_scale=True)
    assert out['recalled'] is True


def test_prep_empty_db_is_safe(prep_db):
    """空库不崩：召回为空时输出「暂无相关记忆」。"""
    empty = os.path.join(os.path.dirname(prep_db), 'empty.db')
    init_db(empty)
    out = prep_for_reply("我压力好大", db_path=empty, embedding_client=CLIENT)
    assert out['recalled'] is True
    assert "暂无相关记忆" in out['text']


# ============================================================
# 薄 CLI
# ============================================================

def test_prep_cli_smoke(prep_db, capsys):
    from scripts import prep
    rc = prep.main(['--db', prep_db, '--message', '我压力好大'])
    assert rc == 0
    printed = capsys.readouterr().out
    assert "[回忆]" in printed


def test_prep_cli_gated_exits_clean(prep_db, capsys):
    from scripts import prep
    rc = prep.main(['--db', prep_db, '--message', '你好'])
    assert rc == 0
    assert capsys.readouterr().out.strip() == ""
