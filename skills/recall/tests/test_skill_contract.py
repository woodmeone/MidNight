# -*- coding: utf-8 -*-
"""票3：文档契约测试——规则被"写进 SKILL.md"这件事本身必须可回归。

为什么值得给文档写测试：本轮的核心资产不是代码，是**规则**。规则写在 prompt 里、
靠 Agent 自觉遵守，一旦哪天被人"顺手简化"掉（比如把"md 永不作为检索目标"删成
"尽量用算法"），能力还在、约束没了，坏行为会静默回来。

所以这里断言的是**不可删的句子**，而不是措辞优美。
"""
import os

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
SKILL = os.path.join(REPO_ROOT, 'skills', 'recall', 'SKILL.md')
PROJECT = os.path.join(REPO_ROOT, 'PROJECT.md')
CONTEXT = os.path.join(REPO_ROOT, 'CONTEXT.md')
ADR2 = os.path.join(REPO_ROOT, 'docs', 'adr', '0002-md-is-source-not-index.md')


def _read(path):
    with open(path, encoding='utf-8') as f:
        return f.read()


@pytest.fixture(scope='module')
def skill():
    return _read(SKILL)


# ============================================================
# 1. 通道铁律：三条通道 + md 不是索引 + 例外条件
# ============================================================

def test_skill_declares_three_channels(skill):
    assert '检索通道铁律' in skill
    assert '联想通道' in skill
    assert '确定性通道' in skill
    assert '--timeline' in skill
    assert '--literal' in skill


def test_skill_forbids_md_as_retrieval_target(skill):
    # 这句是整条铁律的核心：源 ≠ 索引
    assert '永远不是检索目标' in skill
    assert 'recall.db' in skill


def test_skill_states_the_explicit_authorization_exception(skill):
    # 例外口子必须写成"用户明确说"，不能留成"视情况自行判断"
    assert '仅当用户明确说' in skill
    assert '读原文' in skill and '看文件' in skill


def test_skill_has_self_check_trigger(skill):
    """发现自己要 grep/read dailynote 时必须停手改道——这是防止规则被遗忘的钩子。"""
    assert '自检触发点' in skill
    assert '停手' in skill


def test_no_line_teaches_reading_md_as_a_default_path(skill):
    """任何提到 grep 的行，必须同时是"禁止/例外/停手"，不能是"先 grep 一下"。"""
    allowed = ('停手', '仅当', '不要', '禁止', '不读', '别', '禁止跨')
    for line in skill.splitlines():
        if 'grep' in line:
            assert any(w in line for w in allowed), f'可疑的 grep 指引：{line!r}'


# ============================================================
# 2. 查询派生协议
# ============================================================

def test_skill_has_query_derivation_protocol(skill):
    assert '查询派生协议' in skill
    assert '2–5 个名词性线索' in skill
    assert 'anchor' in skill
    assert '--multi-scale' in skill
    assert '不要把用户原话直接当 query' in skill


# ============================================================
# 3. 留痕可核查
# ============================================================

def test_skill_documents_ledger_and_audit(skill):
    assert 'retrieval_ledger.jsonl' in skill
    assert '--audit' in skill
    assert '不要试图绕过它' in skill


def test_skill_says_prep_is_covered_by_ledger(skill):
    """默认入口 prep.py 必须也在留痕范围内——否则"每次检索都留痕"是假话。"""
    assert 'prep.py' in skill
    for line in skill.splitlines():
        if 'retrieval_ledger.jsonl' in line:
            assert 'prep.py' in line, f'留痕声明漏了默认入口：{line!r}'


def test_skill_requires_identity_for_deterministic_channels(skill):
    assert '必须显式带 `--identity/--agent`' in skill or '必须显式带 --identity/--agent' in skill


# ============================================================
# 4. 真相回写（PROJECT / CONTEXT / ADR）
# ============================================================

def test_project_truth_updated():
    project = _read(PROJECT)
    assert 'ledger.py' in project
    assert 'retrieval_ledger.jsonl' in project
    assert '--timeline' in project
    assert 'ADR-0002' in project
    assert '检索只走库' in project


def test_context_terms_added():
    context = _read(CONTEXT)
    for term in ('检索通道', '联想通道', '确定性通道', '检索留痕', 'md 源文件'):
        assert f'**{term}**' in context


def test_adr_0002_exists_and_has_three_parts():
    assert os.path.exists(ADR2)
    adr = _read(ADR2)
    for part in ('## 背景', '## 决定', '## 后果'):
        assert part in adr
    assert '不是索引' in adr or '不作检索索引' in adr
