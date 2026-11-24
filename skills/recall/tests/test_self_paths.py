"""Tests for self.md 路径指路（Issue #10）.

契约（见 .scratch/self-index/issues/02-*.md）：
- DEFAULT_PATHS 两句：先查技能库 / 有事问同伴
- ensure_self 语义不变：已有 self.md **不被改写**（自我认知只能自愿补）
- add_paths 幂等：已有非空 paths 则不动
- paths 是可动层，evolution 能改

关键：本条最容易被"顺手帮它补齐字段"破坏，测试 3 专门锁这个。
"""
import json
import os
import tempfile

import pytest

import scripts.config as cfg
from scripts.config import get_agent_dir, get_self_path
from scripts.evolution import apply_evolution
from scripts.self_model import (
    DEFAULT_PATHS,
    DEFAULT_TEMPLATE,
    add_paths,
    ensure_self,
    main,
    read_self,
)


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


def _write_self(agent, mutable):
    """直接写一份 self.md（模拟老用户的既有文件）。"""
    path = get_self_path(agent)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write('---\n')
        f.write('name: mira\n')
        f.write('anchor_tags: [midnight]\n')
        f.write(f'mutable: {json.dumps(mutable, ensure_ascii=False)}\n')
        f.write('---\n')
        f.write('我是 mira。\n')


def test_default_template_has_paths():
    """DEFAULT_TEMPLATE 的 paths 是那两句，各含关键词"""
    paths = DEFAULT_TEMPLATE['mutable'].get('paths')
    assert paths, 'paths 必须是非空的'
    assert len(paths) == 2
    joined = ' '.join(paths)
    assert '技能库' in joined
    assert '同伴' in joined


def test_init_writes_paths(agent):
    """新 agent 调 ensure_self → 写出的 self.md 里 mutable.paths 是那两句"""
    ensure_self(agent)

    data = read_self(agent)
    assert data['mutable']['paths'] == DEFAULT_PATHS


def test_init_does_not_touch_existing_self(agent):
    """已有 self.md（无 paths）→ ensure_self 后文件内容逐字节不变

    这是本 Issue 最重要的一条：顺手给老用户补字段 = 第三方动它的自我认知。
    """
    _write_self(agent, {'persona_style': '温柔坚定'})
    before = open(get_self_path(agent), 'rb').read()

    ensure_self(agent)

    after = open(get_self_path(agent), 'rb').read()
    assert before == after, 'ensure_self 不得改写既有的 self.md'


def test_add_paths_fills_missing(agent):
    """已有 self.md 无 paths → add_paths 返回 added=True，文件里出现那两句"""
    _write_self(agent, {'persona_style': '温柔坚定'})

    result = add_paths(agent)

    assert result['added'] is True
    assert read_self(agent)['mutable']['paths'] == DEFAULT_PATHS


def test_add_paths_noop_when_present(agent):
    """已有自定义 paths → added=False，文件内容不变"""
    custom = ['我自己写的路径说明']
    _write_self(agent, {'persona_style': '温柔坚定', 'paths': custom})
    before = open(get_self_path(agent), 'rb').read()

    result = add_paths(agent)

    assert result['added'] is False
    assert open(get_self_path(agent), 'rb').read() == before
    assert read_self(agent)['mutable']['paths'] == custom


def test_add_paths_creates_when_absent(agent):
    """无 self.md → add_paths 建出带 paths 的 self.md"""
    assert not os.path.exists(get_self_path(agent))

    result = add_paths(agent)

    assert result['added'] is True
    assert os.path.exists(get_self_path(agent))
    assert read_self(agent)['mutable']['paths'] == DEFAULT_PATHS


def test_cli_add_paths_json_output(agent, capsys):
    """main(['--add-paths','--agent',a]) → 退出码 0，输出可 json.loads"""
    _write_self(agent, {'persona_style': '冷静'})

    rc = main(['--add-paths', '--agent', agent])
    out = capsys.readouterr().out

    assert rc == 0
    payload = json.loads(out)
    assert payload['status'] == 'ok'
    assert payload['added'] is True


def test_evolution_can_still_patch_paths(agent):
    """paths 是可动层 → evolution.update_self 能改它（不被 protected）"""
    ensure_self(agent)

    result = apply_evolution(agent, feedback='测试', patch={'paths': ['自定义一句']})

    assert 'paths' not in result['rejected']
    assert read_self(agent)['mutable']['paths'] == ['自定义一句']


def test_evolution_rejects_immutable(agent):
    """定海锚仍不可改（现有行为不回归）"""
    ensure_self(agent)

    result = apply_evolution(agent, feedback='测试', patch={'name': 'hacked'})

    assert 'name' in result['rejected']
    assert read_self(agent)['name'] == 'midnight-agent'


def test_paths_type_string_or_list(agent):
    """paths 写成字符串也要能被 add_paths 判成「已有」"""
    _write_self(agent, {'persona_style': '冷静', 'paths': '一句字符串路径'})

    result = add_paths(agent)

    assert result['added'] is False
    assert read_self(agent)['mutable']['paths'] == '一句字符串路径'


def test_paths_empty_list_counts_as_missing(agent):
    """paths 是空列表 → 视为缺失（falsy）"""
    _write_self(agent, {'persona_style': '冷静', 'paths': []})

    result = add_paths(agent)

    assert result['added'] is True


def test_broken_mutable_does_not_crash(agent):
    """mutable 是坏 JSON → 不崩，add_paths 照常补"""
    path = get_self_path(agent)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write('---\nname: mira\nmutable: {broken json\n---\n正文\n')

    result = add_paths(agent)

    assert result['added'] is True
    assert read_self(agent)['mutable']['paths'] == DEFAULT_PATHS
