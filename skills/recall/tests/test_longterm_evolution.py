"""Tests for 长期内容的自我维护（Issue #12）.

契约（见 .scratch/self-index/issues/04-*.md）：
- SKILL.md 有「## 长期内容的维护」：一句话问 + token 提醒 + 三个触发点 + 边界表
- **不含**准入判据 / 反例清单 / 90 天算法——那些是替它判断
- DEFAULT_EVOLUTION 常量；add_evolution 幂等；--add-evolution CLI
- session_start 摘要带「长期内容可自维护」

第 8、9 是一对：一条锁住该有的，一条锁住不该有的。
"""
import json
import os
import tempfile

import pytest

import scripts.config as cfg
from scripts.config import get_self_path
from scripts.evolution import apply_evolution
from scripts.self_model import (
    DEFAULT_EVOLUTION,
    DEFAULT_PATHS,
    DEFAULT_TEMPLATE,
    add_evolution,
    ensure_self,
    main,
    read_self,
)
from scripts.session_start import compile_identity_summary

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
SKILL = os.path.join(REPO_ROOT, 'skills', 'recall', 'SKILL.md')


@pytest.fixture
def basedir():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        old_base = cfg.BASE_DIR
        cfg.BASE_DIR = tmp
        yield tmp
        cfg.BASE_DIR = old_base


@pytest.fixture
def agent(basedir):
    return 'kaibian'


def _write_self(agent, mutable):
    path = get_self_path(agent)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write('---\n')
        f.write('name: kaibian\n')
        f.write('anchor_tags: [midnight]\n')
        f.write(f'mutable: {json.dumps(mutable, ensure_ascii=False)}\n')
        f.write('---\n')
        f.write('我是开编。\n')


# ============================================================
# self.md 演化字段
# ============================================================

def test_default_template_has_evolution():
    """DEFAULT_EVOLUTION 非空，含「收尾」与「下次用」"""
    evo = DEFAULT_TEMPLATE['mutable'].get('evolution')
    assert evo == DEFAULT_EVOLUTION
    assert '收尾' in evo
    assert '下次用' in evo


def test_paths_length_still_two():
    """#10 不回归：paths 仍是 2 项，没被 evolution 挤进去"""
    assert len(DEFAULT_TEMPLATE['mutable']['paths']) == 2
    assert DEFAULT_TEMPLATE['mutable']['paths'] == DEFAULT_PATHS


def test_add_evolution_fills_missing(agent):
    """老 self.md 无 evolution → added=True，文件里出现那句"""
    _write_self(agent, {'persona_style': '冷静'})

    result = add_evolution(agent)

    assert result['added'] is True
    assert read_self(agent)['mutable']['evolution'] == DEFAULT_EVOLUTION


def test_add_evolution_noop_when_present(agent):
    """已有自定义 evolution → added=False，文件逐字节不变"""
    _write_self(agent, {'persona_style': '冷静', 'evolution': '我自己写的'})
    before = open(get_self_path(agent), 'rb').read()

    result = add_evolution(agent)

    assert result['added'] is False
    assert open(get_self_path(agent), 'rb').read() == before


def test_add_evolution_creates_when_absent(agent):
    """无 self.md → 建出带 evolution 的 self.md"""
    assert not os.path.exists(get_self_path(agent))

    result = add_evolution(agent)

    assert result['added'] is True
    assert read_self(agent)['mutable']['evolution'] == DEFAULT_EVOLUTION


def test_summary_contains_evolution_hint(agent):
    """摘要含「长期内容可自维护」"""
    ensure_self(agent)

    summary = compile_identity_summary(agent)

    assert '长期内容可自维护' in summary


def test_summary_without_evolution_omits_hint(agent):
    """无该字段 → 摘要不含该串，不报错"""
    _write_self(agent, {'persona_style': '冷静'})

    summary = compile_identity_summary(agent)

    assert '长期内容可自维护' not in summary


# ============================================================
# 契约：该有的 vs 不该有的
# ============================================================

def test_contract_skill_md_has_evolution_section():
    """章节四块齐全，且含那几句不可省的硬话"""
    text = open(SKILL, encoding='utf-8').read()
    assert '## 长期内容的维护' in text
    assert '是我想要长期留下来的' in text     # 唯一的准入：一句问话
    assert '别先问「这个够不够格」——想留就留' in text
    assert 'token 和上下文很宝贵' in text
    assert '收尾那一刻' in text
    assert '要人点头' in text
    assert '身份不能漂' in text


def test_contract_skill_md_has_no_entry_bar():
    """反面：维护章节里不许有准入判据 / 反例清单 / 90 天算法——那是替它判断

    只查「## 长期内容的维护」这一节。全文别处的「90 天」是 `--decay`
    （记忆关联的久不用衰减），那是另一件事，不该被这条断言误伤。
    """
    text = open(SKILL, encoding='utf-8').read()
    start = text.index('## 长期内容的维护')
    # 到下一个同级标题为止
    rest = text[start + len('## 长期内容的维护'):]
    nxt = rest.find('\n## ')
    section = rest if nxt == -1 else rest[:nxt]

    for banned in ('准入', '判据表', '反例清单', '90 天'):
        assert banned not in section, f'维护章节不该出现「{banned}」——那是替它判断'


def test_evolution_can_be_patched_by_evolution_engine(agent):
    """evolution 是可动层，允许演化（但留痕在 evolution.log）"""
    ensure_self(agent)

    result = apply_evolution(agent, feedback='测试', patch={'evolution': '改过一句'})

    assert 'evolution' not in result['rejected']
    assert read_self(agent)['mutable']['evolution'] == '改过一句'


def test_cli_add_evolution_json(agent, capsys):
    """--add-evolution 输出 JSON，退出码 0"""
    _write_self(agent, {'persona_style': '冷静'})

    rc = main(['--add-evolution', '--agent', agent])
    payload = json.loads(capsys.readouterr().out)

    assert rc == 0
    assert payload['status'] == 'ok'
    assert payload['added'] is True
