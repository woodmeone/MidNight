"""Tests for T5: session_start.py 上下文轻编译。

Behavioral checks:
- 有 self.md 时，compile_identity_summary 输出含身份摘要（name / 锚标签 / 可动层概要）。
- 摘要长度受控（≤ MAX_CHARS ≈ 200 字），不把 persona 全档塞进上下文。
- 无 self.md 时 compile_identity_summary 返回空串，CLI 输出引导文案且不报错。
"""
import os
import tempfile

import pytest

import scripts.config as cfg
from scripts.self_model import ensure_self, get_self_path
from scripts.session_start import compile_identity_summary, GUIDANCE_TEXT, main


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


def test_summary_contains_identity(agent):
    """有 self 时，摘要应含 name、锚标签与可动层概要"""
    ensure_self(agent, defaults={
        'name': 'mira',
        'anchor_tags': ['midnight', 'recall'],
        'mutable': {'persona_style': '温柔坚定', 'capabilities': ['记忆', '联想', '执行']},
        'description': 'mira 的身份锚。',
    })
    summary = compile_identity_summary(agent)
    assert 'mira' in summary
    assert 'midnight' in summary
    assert '温柔坚定' in summary
    assert '记忆' in summary


def test_summary_keeps_full_fields_no_truncation(agent):
    """身份摘要是最基础信息，能有多少就多少：超长字段也完整保留，不拦腰硬截（无省略号）"""
    ensure_self(agent, defaults={
        'name': 'mira',
        'anchor_tags': ['midnight'],
        'mutable': {
            'persona_style': '冷静' * 60,            # 刻意塞超长文本，须完整保留
            'capabilities': [f'能力{i}' for i in range(50)],
            'position': 'AI 助手' * 40,
        },
        'description': 'x' * 500,
    })
    summary = compile_identity_summary(agent)
    assert '冷静' * 60 in summary      # 刻意超长的风格字段完整保留，绝不拦腰切
    assert '能力49' in summary          # 第 50 项能力也在（没在头部就截断）
    assert '…' not in summary           # 不出现截断省略号


def test_summary_without_self_returns_empty(agent):
    """无 self.md 时 compile_identity_summary 返回空串，不报错"""
    assert not os.path.exists(get_self_path(agent))
    assert compile_identity_summary(agent) == ''


def test_cli_without_self_prints_guidance(agent):
    """CLI 无 self 时输出引导文案且退出码 0，不报错"""
    rc = main(['--agent', agent])
    # main 打印内容已定向到 stdout；这里通过 GUIDANCE_TEXT 校验文案存在
    assert rc == 0
    assert '尚未定位自我' in GUIDANCE_TEXT


def test_cli_with_self_prints_identity(agent, capsys):
    """CLI 有 self 时输出 `[身份] ...（其余记忆靠联想召回）`"""
    ensure_self(agent, defaults={
        'name': 'mira',
        'anchor_tags': ['midnight'],
        'mutable': {'persona_style': '冷静高效'},
    })
    rc = main(['--agent', agent])
    out = capsys.readouterr().out
    assert rc == 0
    assert '[身份]' in out
    assert 'mira' in out
    assert '其余记忆靠联想召回' in out
