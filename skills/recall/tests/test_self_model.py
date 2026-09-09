"""Tests for T1: self anchor generation (self.md).

Behavioral checks:
- ensure_self creates self.md on first run (anchor_tags + mutable present).
- ensure_self is idempotent: existing anchors are never overwritten.
- read_self parses self.md back into a dict.
- update_self(mutable_only=True) writes only the mutable layer; immutable
  keys (name / anchor_tags / description) are rejected and stay unchanged.
"""
import json
import os
import tempfile

import pytest

import scripts.config as cfg
from scripts.self_model import ensure_self, read_self, update_self, get_self_path


@pytest.fixture
def basedir():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        old_base = cfg.BASE_DIR
        cfg.BASE_DIR = tmp
        yield tmp
        cfg.BASE_DIR = old_base


@pytest.fixture
def agent(basedir):
    return 'mira'


def test_get_self_path_under_agent_dir(agent, basedir):
    """self.md 应位于该 agent 的数据目录下"""
    path = get_self_path(agent)
    assert path == os.path.join(basedir, 'mira', 'self.md')


def test_ensure_self_creates_file(agent):
    """首次 ensure_self 自动生成 self.md，含 anchor_tags 与 mutable 块"""
    data = ensure_self(agent)
    assert os.path.exists(get_self_path(agent))
    assert 'name' in data
    assert isinstance(data['anchor_tags'], list) and data['anchor_tags']
    assert isinstance(data['mutable'], dict)
    assert data['description'].strip()


def test_ensure_self_idempotent_preserves_anchor(agent):
    """已有 self.md 时 ensure_self 幂等，不覆盖既有锚"""
    ensure_self(agent)
    path = get_self_path(agent)
    # 用户手动自定义了锚标签
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content.replace('anchor_tags: [midnight]', 'anchor_tags: [mira, assistant]'))

    data = ensure_self(agent)
    assert 'mira' in data['anchor_tags'] and 'assistant' in data['anchor_tags']


def test_read_self_parses(agent):
    """read_self 能解析 self.md 回 dict"""
    ensure_self(agent)
    data = read_self(agent)
    assert data['name']
    assert isinstance(data['anchor_tags'], list)
    assert isinstance(data['mutable'], dict)
    assert data['description']


def test_update_mutable_only_applies_mutable(agent):
    """mutable_only=True 时，可动层字段可写入"""
    ensure_self(agent)
    result = update_self(agent, {'persona_style': '冷静工程师', 'position': 'AI 助理'})
    assert result['updated'] is True
    assert result['rejected'] == []
    data = read_self(agent)
    assert data['mutable']['persona_style'] == '冷静工程师'
    assert data['mutable']['position'] == 'AI 助理'


def test_update_mutable_only_rejects_immutable(agent):
    """mutable_only=True 时，改定海锚字段被拒绝，值不变"""
    ensure_self(agent)
    original = read_self(agent)
    result = update_self(agent, {'name': 'evil', 'anchor_tags': ['hacked']})
    assert result['updated'] is False
    assert set(result['rejected']) == {'name', 'anchor_tags'}
    data = read_self(agent)
    assert data['name'] == original['name']
    assert data['anchor_tags'] == original['anchor_tags']


def test_ensure_self_serializes_read_only(agent, basedir):
    """新 self.md 应在 frontmatter 显式声明 read_only，且读回含定海锚字段"""
    ensure_self(agent)
    path = get_self_path(agent)
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    assert 'read_only:' in content
    data = read_self(agent)
    for key in ('name', 'anchor_tags', 'description'):
        assert key in data['read_only']


def test_backcompat_existing_self_without_read_only(agent):
    """无 read_only 字段的旧 self.md 读回时默认保护定海锚（不破坏既有数据）"""
    ensure_self(agent)
    path = get_self_path(agent)
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    # 手动删掉 read_only 行，模拟旧版自建 self.md
    content = '\n'.join(
        line for line in content.splitlines() if not line.startswith('read_only:')
    )
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    data = read_self(agent)
    assert 'name' in data['read_only']      # 仍默认保护
    assert 'description' in data['read_only']

    # 旧文件上改定海锚依然被拒
    result = update_self(agent, {'name': 'evil'})
    assert 'name' in result['rejected']


def test_update_respects_file_read_only_override(agent):
    """文件级 read_only 追加字段后，该字段被当成可动层的保护字段拒绝写入"""
    ensure_self(agent)
    path = get_self_path(agent)
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    # 按行定位 read_only 行，整行重写，把自建的 'position' 也声明为只读
    lines = content.splitlines()
    out = []
    replaced = False
    for line in lines:
        if line.startswith('read_only:') and not replaced:
            out.append('read_only: [anchor_tags, description, name, position]')
            replaced = True
        else:
            out.append(line)
    assert replaced, 'should have found read_only line'
    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(out))

    data = read_self(agent)
    assert 'position' in data['read_only']

    # position 已被声明只读 → mutable_only 下拒绝写入；其余可动层字段仍可写
    result = update_self(agent, {'position': 'hacked', 'persona_style': '可改'})
    assert result['updated'] is True          # persona_style 被应用
    assert 'position' in result['rejected']    # position 被拒
    assert 'persona_style' not in result['rejected']
    data = read_self(agent)
    assert 'position' not in data['mutable']   # 原值未被写进可动层
