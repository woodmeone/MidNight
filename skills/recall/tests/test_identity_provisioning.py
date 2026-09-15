"""Regression tests for identity-based auto-provisioning (身份即建区).

要点：声明身份（--identity/--agent/--register）即自动开户——建目录 + 建 agent.json，
让 list_agents() 立刻可见；幂等不覆盖已有描述；default 区不生成身份文件。
"""
import json
import os
import tempfile
import pytest

import scripts.config as cfg
from scripts.config import (
    ensure_agent_dir, ensure_agent, list_agents, get_agent_dir,
    DEFAULT_AGENT,
)


def _set_base(tmpdir):
    old = cfg.BASE_DIR
    cfg.BASE_DIR = tmpdir
    return old


def test_register_creates_visible_agent():
    """声明身份 → 建目录 + agent.json，list_agents 立刻能看到，无需先写日记。"""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        old = _set_base(tmpdir)
        try:
            ensure_agent('nova', '美食探索与食谱记录管家')
            assert os.path.isdir(os.path.join(get_agent_dir('nova'), 'dailynote'))
            meta_path = os.path.join(get_agent_dir('nova'), 'agent.json')
            assert os.path.exists(meta_path)
            data = json.load(open(meta_path, encoding='utf-8'))
            assert data['name'] == 'nova'
            assert data['description'] == '美食探索与食谱记录管家'

            names = [a['name'] for a in list_agents()]
            assert 'nova' in names
            nova = [a for a in list_agents() if a['name'] == 'nova'][0]
            assert nova['description'] == '美食探索与食谱记录管家'
        finally:
            cfg.BASE_DIR = old


def test_register_without_description_defaults_to_name():
    """只给名字不给描述 → description 以名字兜底，仍可见。"""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        old = _set_base(tmpdir)
        try:
            ensure_agent('solo')
            meta_path = os.path.join(get_agent_dir('solo'), 'agent.json')
            data = json.load(open(meta_path, encoding='utf-8'))
            assert data['description'] == 'solo'
            assert 'solo' in [a['name'] for a in list_agents()]
        finally:
            cfg.BASE_DIR = old


def test_register_is_idempotent_keeps_description():
    """重复开户不覆盖已有描述。"""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        old = _set_base(tmpdir)
        try:
            ensure_agent('mira', '社交恋爱管家')
            ensure_agent('mira', '别覆盖我')
            data = json.load(open(os.path.join(get_agent_dir('mira'), 'agent.json'), encoding='utf-8'))
            assert data['description'] == '社交恋爱管家'
        finally:
            cfg.BASE_DIR = old


def test_default_agent_has_no_identity_file():
    """default 是兜底槽位，开户时不生成 agent.json（不冒充具名 AI）。"""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        old = _set_base(tmpdir)
        try:
            ensure_agent(DEFAULT_AGENT, '不要给我建身份')
            meta_path = os.path.join(get_agent_dir(DEFAULT_AGENT), 'agent.json')
            assert not os.path.exists(meta_path)
        finally:
            cfg.BASE_DIR = old


def test_register_fills_missing_description_but_keeps_keywords():
    """已有 agent.json 但缺 description → 补上；已有 keywords 保留。"""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        old = _set_base(tmpdir)
        try:
            d = get_agent_dir('kpop')
            os.makedirs(os.path.join(d, 'dailynote'), exist_ok=True)
            with open(os.path.join(d, 'agent.json'), 'w', encoding='utf-8') as f:
                json.dump({'name': 'kpop', 'keywords': ['编舞', '舞台']}, f, ensure_ascii=False)

            ensure_agent('kpop', '追星舞台记录')
            data = json.load(open(os.path.join(d, 'agent.json'), encoding='utf-8'))
            assert data['description'] == '追星舞台记录'
            assert data['keywords'] == ['编舞', '舞台']
        finally:
            cfg.BASE_DIR = old