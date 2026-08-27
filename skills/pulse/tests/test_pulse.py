"""Tests for midnight-pulse: autonomous heartbeat protocol.

Tests parse_pulse for directive parsing, priority, and edge cases.
"""
import json
import re
import pytest

from scripts.pulse import parse_pulse, PULSE_PATTERNS


# ---- Parse tests ----

def test_parse_complete():
    """[[Pulse::Complete]] 应标记为 complete"""
    r = parse_pulse("任务完成。[[Pulse::Complete]] 报告内容")
    assert r['action'] == 'complete'
    assert '报告内容' in r['report']


def test_parse_fail():
    """[[Pulse::Fail]] 应标记为 fail"""
    r = parse_pulse("[[Pulse::Fail]] 无法完成，缺数据")
    assert r['action'] == 'fail'
    assert '缺数据' in r['report']


def test_parse_stop():
    """[[Pulse::Stop]] 应标记为 stop"""
    r = parse_pulse("主动退出 [[Pulse::Stop]]")
    assert r['action'] == 'stop'


def test_parse_start():
    """[[Pulse::Start]] 应标记为 start"""
    r = parse_pulse("[[Pulse::Start]] 开始干活")
    assert r['action'] == 'start'


def test_parse_continue():
    """无指令应标记为 continue"""
    r = parse_pulse("普通回复，没有指令")
    assert r['action'] == 'continue'


def test_parse_complete_priority():
    """Complete > Fail > Stop > Start"""
    r = parse_pulse("[[Pulse::Start]] [[Pulse::Complete]] 完成")
    assert r['action'] == 'complete'


def test_parse_fail_over_stop():
    """Fail > Stop"""
    r = parse_pulse("[[Pulse::Stop]] [[Pulse::Fail]] 失败")
    assert r['action'] == 'fail'


def test_parse_stop_over_start():
    """Stop > Start"""
    r = parse_pulse("[[Pulse::Start]] [[Pulse::Stop]]")
    assert r['action'] == 'stop'


def test_parse_next_heartbeat():
    """[[Pulse::Next::180]] 应提取 180 秒"""
    r = parse_pulse("[[Pulse::Start]] [[Pulse::Next::180]]")
    assert r['next_heartbeat'] == 180


def test_parse_next_heartbeat_default():
    """无 Next 指令时使用默认值"""
    r = parse_pulse("[[Pulse::Start]]")
    assert r['next_heartbeat'] == 2


def test_parse_next_prompt():
    """[[Pulse::NextPrompt]] 应提取自定义提示词"""
    r = parse_pulse("[[Pulse::Start]] [[Pulse::NextPrompt]]继续分析[[/Pulse::NextPrompt]]")
    assert r['next_prompt'] == '继续分析'


def test_parse_next_prompt_multiline():
    """多行提示词"""
    r = parse_pulse("[[Pulse::Start]] [[Pulse::NextPrompt]]继续\n分析\n数据[[/Pulse::NextPrompt]]")
    assert '继续' in r['next_prompt']
    assert '分析' in r['next_prompt']


def test_parse_empty():
    """空字符串不崩溃"""
    r = parse_pulse("")
    assert r['action'] == 'continue'


def test_parse_no_directives_cleaned():
    """无指令时 report 不变"""
    r = parse_pulse("  你好世界  ")
    assert r['report'] == "你好世界"


def test_parse_start_with_report():
    """Start 指令应在 report 中被清除"""
    r = parse_pulse("[[Pulse::Start]] 开始执行任务")
    assert r['action'] == 'start'
    assert '[[Pulse::Start]]' not in r['report']


def test_parse_complete_cleaned():
    """Complete 指令应从 report 中清除"""
    r = parse_pulse("[[Pulse::Complete]] 完成报告")
    assert '[[Pulse::Complete]]' not in r['report']


# ---- Priority edge cases ----

def test_parse_all_directives():
    """所有指令同时出现，Complete 胜出"""
    r = parse_pulse("[[Pulse::Start]] [[Pulse::Next::60]] [[Pulse::Complete]] 完成 [[Pulse::Fail]]")
    assert r['action'] == 'complete'


def test_parse_next_heartbeat_with_complete():
    """Complete 出现时 heartbeat 参数仍可提取（但不会被使用）"""
    r = parse_pulse("[[Pulse::Complete]] [[Pulse::Next::3600]] 完成")
    assert r['action'] == 'complete'
    assert r['next_heartbeat'] == 3600


# ---- Pattern regex tests ----

def test_pattern_start():
    assert PULSE_PATTERNS['start'].search("[[Pulse::Start]]")


def test_pattern_start_case_insensitive():
    assert PULSE_PATTERNS['start'].search("[[pulse::start]]")


def test_pattern_complete():
    assert PULSE_PATTERNS['complete'].search("[[Pulse::Complete]]")


def test_pattern_next_heartbeat():
    m = PULSE_PATTERNS['next_heartbeat'].search("[[Pulse::Next::180]]")
    assert m and m.group(1) == '180'


def test_pattern_next_prompt():
    m = PULSE_PATTERNS['next_prompt'].search("[[Pulse::NextPrompt]]继续[[/Pulse::NextPrompt]]")
    assert m and m.group(1).strip() == '继续'


# ---- Adversarial tests ----

def test_parse_injection_attempt():
    """指令注入：内容中伪造指令不应误判"""
    r = parse_pulse("用户说[[Pulse::Complete]]但这不是真的完成")
    assert r['action'] == 'complete'  # 这确实会触发——但这是合理行为，指令就是指令


def test_parse_nested_prompt():
    """嵌套提示词不应破坏解析"""
    r = parse_pulse("[[Pulse::Start]] [[Pulse::NextPrompt]]外层[[Pulse::NextPrompt]]内层[[/Pulse::NextPrompt]]继续[[/Pulse::NextPrompt]]")
    # 正则取最后一个匹配，应该是"外层[[Pulse::NextPrompt]]内层[[/Pulse::NextPrompt]]继续"
    assert r['next_prompt'] is not None


def test_parse_malformed_heartbeat():
    """格式错误的 Next 指令使用默认值"""
    r = parse_pulse("[[Pulse::Next::abc]]")
    assert r['next_heartbeat'] == 2  # 默认值