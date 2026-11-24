"""tools/skill_injection_doctor.py 的行为测试。

写测试时对抗自己：什么输入会让它算错？
- 空 dump / 只有一条 / 三条都开
- preset 层与 host 层混在一起，能不能分清
- `disabled: true` 有没有被误算成启用
- 会话日志只有一轮 / 一轮里同名 skill 出现三次
- 没有 zstd 包时会不会崩（应报错跳过，不静默）
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))       # tools/tests
TOOL = os.path.join(os.path.dirname(HERE), 'skill_injection_doctor.py')


def _load():
    spec = importlib.util.spec_from_file_location('skill_injection_doctor', TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


doctor = _load()


# ------------------------------------------------------------- dump 解析侧

HOST_ONLY = """\
- id: agent-preset-registry
  name: '@deepseek-ai/dsh-agent-preset-registry'
  config:
    default: standard
    selectedDefault: standard
- id: skill-filesystem
  name: '@deepseek-ai/dsh-skill-filesystem'
- id: tool-skill
  name: '@deepseek-ai/dsh-tool-skill'
- id: preset-standard
  name: '@deepseek-ai/dsh-agent-preset'
  config:
    id: standard
    plugins:
      - id: tool-bash
        name: '@deepseek-ai/dsh-tool-bash'
"""

DOUBLE_MOUNTED = """\
- id: agent-preset-registry
  name: '@deepseek-ai/dsh-agent-preset-registry'
  config:
    default: standard
    selectedDefault: standard
- id: skill-filesystem
  name: '@deepseek-ai/dsh-skill-filesystem'
  disabled: false
- id: tool-skill
  name: '@deepseek-ai/dsh-tool-skill'
  disabled: false
- id: preset-standard
  name: '@deepseek-ai/dsh-agent-preset'
  config:
    id: standard
    plugins:
      - id: tool-bash
        name: '@deepseek-ai/dsh-tool-bash'
      - id: skill-filesystem
        name: '@deepseek-ai/dsh-skill-filesystem'
      - id: tool-skill
        name: '@deepseek-ai/dsh-tool-skill'
- id: preset-ptc
  name: '@deepseek-ai/dsh-agent-preset'
  config:
    id: ptc
    plugins:
      - id: tool-skill
        name: '@deepseek-ai/dsh-tool-skill'
"""

HOST_DISABLED = """\
- id: agent-preset-registry
  config:
    selectedDefault: standard
- id: tool-skill
  name: '@deepseek-ai/dsh-tool-skill'
  disabled: true
- id: preset-standard
  name: '@deepseek-ai/dsh-agent-preset'
  config:
    id: standard
    plugins:
      - id: tool-skill
        name: '@deepseek-ai/dsh-tool-skill'
"""


def test_parses_host_layer_as_not_a_preset():
    records = doctor.parse_dump_config(HOST_ONLY)
    host = [r for r in records if r['preset'] is None]
    assert len(host) == 2, '顶层应检出 skill-filesystem + tool-skill 两条'
    assert all(r['layer'] == 'host' for r in host)


def test_preset_layer_is_attributed_to_its_preset():
    records = doctor.parse_dump_config(DOUBLE_MOUNTED)
    standard = [r for r in records if r['preset'] == 'standard']
    ptc = [r for r in records if r['preset'] == 'ptc']
    assert len(standard) == 2
    assert len(ptc) == 1
    assert all(r['layer'].startswith('preset:') for r in standard + ptc)


def test_active_preset_read_from_registry():
    assert doctor.active_preset(DOUBLE_MOUNTED) == 'standard'


def test_active_preset_absent_is_none():
    assert doctor.active_preset('- id: tool-skill\n  name: x\n') is None


def test_disabled_true_is_parsed_not_assumed_false():
    records = doctor.parse_dump_config(HOST_DISABLED)
    host_injector = [r for r in records
                     if r['id'] == doctor.INJECTOR and r['preset'] is None]
    assert len(host_injector) == 1
    assert host_injector[0]['disabled'] is True


@pytest.mark.parametrize('text,expected_code', [
    (HOST_ONLY, 0),          # host 有、预设没有 —— 只一份
    (DOUBLE_MOUNTED, 1),     # host + standard 同时开 —— 两份
    (HOST_DISABLED, 0),      # host 关了，只剩预设
])
def test_report_config_red_or_green(text, expected_code):
    assert doctor.report_config(text) == expected_code


def test_only_active_preset_counts_towards_duplication():
    """ptc 也挂了 tool-skill，但当前活跃的是 standard —— 不能算成三份。

    这条是回归测试：第一版把三个预设计入同时生效，报告"被塞 4 份"，
    与日志实测的 2 份对不上。
    """
    records = doctor.parse_dump_config(DOUBLE_MOUNTED)
    active = doctor.active_preset(DOUBLE_MOUNTED)

    def effective(r):
        return r['preset'] is None or r['preset'] == active

    live = [r for r in records
            if r['id'] == doctor.INJECTOR and not r['disabled'] and effective(r)]
    assert len(live) == 2, f'应算 2 处（host + standard），实际 {len(live)}'
    assert 'ptc' not in ' '.join(r['layer'] for r in live)


def test_no_target_plugin_returns_error_code():
    assert doctor.report_config('- id: tool-bash\n  name: x\n') == 2


# ---------------------------------------------------------- 会话日志侧

def _session(events, path):
    with open(path, 'w', encoding='utf-8') as f:
        for event in events:
            f.write(json.dumps(event, ensure_ascii=False) + '\n')
    return str(path)


def _turn_start():
    return {'type': 'turn/start'}


def _invoke(name, text='body'):
    return {'type': 'user/message',
            'data': {'source': {'kind': 'skill-invocation', 'name': name},
                     'content': [{'type': 'text', 'text': text}]}}


def _other(kind='time-context'):
    return {'type': 'user/message', 'data': {'source': {'kind': kind}}}


def test_single_injection_is_not_reported(tmp_path):
    path = _session([_turn_start(), _invoke('recall')], tmp_path / 'a.jsonl')
    assert doctor.scan_session_file(path) == []


def test_duplicate_injection_in_one_turn_is_reported(tmp_path):
    path = _session([_turn_start(), _invoke('recall'), _invoke('recall')],
                    tmp_path / 'a.jsonl')
    hits = doctor.scan_session_file(path)
    assert len(hits) == 1
    assert hits[0]['name'] == 'recall'
    assert hits[0]['count'] == 2


def test_triple_injection_is_reported_as_three(tmp_path):
    path = _session([_turn_start()] + [_invoke('recall')] * 3, tmp_path / 'a.jsonl')
    assert doctor.scan_session_file(path)[0]['count'] == 3


def test_injection_in_separate_turns_is_not_duplication(tmp_path):
    """两轮各注入一次，是正确的 —— 不能判成重复。"""
    path = _session([_turn_start(), _invoke('recall'),
                     _turn_start(), _invoke('recall')], tmp_path / 'a.jsonl')
    assert doctor.scan_session_file(path) == []


def test_different_skills_same_turn_is_not_duplication(tmp_path):
    path = _session([_turn_start(), _invoke('recall'), _invoke('ask-matt')],
                    tmp_path / 'a.jsonl')
    assert doctor.scan_session_file(path) == []


def test_time_context_noise_is_ignored(tmp_path):
    path = _session([_turn_start(), _other(), _other(), _invoke('recall')],
                    tmp_path / 'a.jsonl')
    assert doctor.scan_session_file(path) == []


def test_malformed_json_line_is_skipped(tmp_path):
    path = tmp_path / 'a.jsonl'
    path.write_text('{not json}\n', encoding='utf-8')
    assert doctor.scan_session_file(str(path)) == []


def test_digest_is_stable_for_identical_payloads(tmp_path):
    path = _session([_turn_start(), _invoke('recall', 'SAME'), _invoke('recall', 'SAME')],
                    tmp_path / 'a.jsonl')
    assert len(doctor.scan_session_file(path)[0]['digest']) == 10


def test_missing_sessions_root_returns_error():
    assert doctor.report_sessions(os.path.join(os.sep, 'no-such-dir-xyz')) == 2
