"""Tests for boot.py — 开机清单（Issue #9）.

契约（见 .scratch/self-index/issues/01-boot-manifest.md）：
- 两块：人设摘要 + 长期内容索引，中间一个空行
- 不设字数上限，不裁剪；超 2000 字只在末尾追加提醒行
- 三种情形：不可用 / 无 / 有类目
- 只读：不建文件、不写库、不改 mtime
"""
import os
import tempfile

import pytest

import scripts.config as cfg
from scripts.boot import compile_boot_manifest, scan_longterm, main
from scripts.config import get_agent_dir
from scripts.self_model import ensure_self


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


def _longterm(agent):
    return os.path.join(get_agent_dir(agent), 'longterm')


def _mkfile(path, content=''):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)


def _self(agent, name='kaibian', style='第一性原理、克制', boundary='不收噪音'):
    ensure_self(agent, defaults={
        'name': name,
        'anchor_tags': ['midnight'],
        'mutable': {'persona_style': style, 'boundary': boundary},
        'description': f'{name} 的身份锚。',
    })


# ============================================================
# 票1：扫描 + 渲染
# ============================================================

def test_manifest_contains_identity_and_category(agent):
    """有 self.md + longterm/tools/ 2 个文件 → 含 name 与 `tools 2`"""
    _self(agent)
    _mkfile(os.path.join(_longterm(agent), 'tools', 'a.py'))
    _mkfile(os.path.join(_longterm(agent), 'tools', 'b.py'))

    out = compile_boot_manifest(agent)

    assert 'kaibian' in out
    assert 'tools 2' in out


def test_zero_file_category_shown(agent):
    """类目目录存在但为空 → 输出 `类目 0`，不消失"""
    _self(agent)
    os.makedirs(os.path.join(_longterm(agent), 'empty_cat'))

    out = compile_boot_manifest(agent)

    assert 'empty_cat 0' in out


def test_index_file_path_shown(agent):
    """有 LONGTERM.md → 含其绝对路径"""
    _self(agent)
    _mkfile(os.path.join(_longterm(agent), 'tools', 'a.py'))
    index = os.path.join(_longterm(agent), 'LONGTERM.md')
    _mkfile(index, '# 索引\n')

    out = compile_boot_manifest(agent)

    assert index in out


def test_missing_longterm_reports_unavailable(agent):
    """无 longterm 目录 → 含「不可用」与路径"""
    _self(agent)
    # 不建 longterm 目录

    out = compile_boot_manifest(agent)

    assert '不可用' in out
    assert 'longterm' in out


def test_empty_longterm_says_none(agent):
    """目录存在但无子目录 → 含「无」"""
    _self(agent)
    os.makedirs(_longterm(agent))

    out = compile_boot_manifest(agent)

    assert '无' in out
    assert '不可用' not in out


def test_missing_self_degrades(agent):
    """无 self.md → 不抛异常，含 `[开机] 我是{identity}`"""
    assert not os.path.exists(
        os.path.join(get_agent_dir(agent), 'self.md'))

    out = compile_boot_manifest(agent)

    assert f'[开机] 我是{agent}' in out


def test_nested_subdir_counts_as_one_category(agent):
    """kb/S1/x.md → 类目 `kb` 计数 1，不出现类目 `S1`"""
    _self(agent)
    _mkfile(os.path.join(_longterm(agent), 'kb', 'S1', 'x.md'))

    out = compile_boot_manifest(agent)

    assert 'kb 1' in out
    assert 'S1' not in out


def test_categories_sorted(agent):
    """建 z/、a/ → 输出里 a 在 z 前"""
    _self(agent)
    _mkfile(os.path.join(_longterm(agent), 'z', 'f.md'))
    _mkfile(os.path.join(_longterm(agent), 'a', 'f.md'))

    out = compile_boot_manifest(agent)

    assert out.index('a 1') < out.index('z 1')


def test_deterministic(agent):
    """连跑两次，输出逐字节相同"""
    _self(agent)
    _mkfile(os.path.join(_longterm(agent), 'tools', 'a.py'))
    _mkfile(os.path.join(_longterm(agent), 'kb', 'b.md'))

    assert compile_boot_manifest(agent) == compile_boot_manifest(agent)


def test_workspace_root_priority(agent, tmp_path):
    """--workspace 下有 LONGTERM.md → index_file 指向它而非 agent 目录"""
    _self(agent)
    _mkfile(os.path.join(_longterm(agent), 'LONGTERM.md'), 'agent\n')

    ws = str(tmp_path / 'workspace')
    ws_index = os.path.join(ws, 'LONGTERM.md')
    _mkfile(ws_index, 'workspace\n')
    _mkfile(os.path.join(ws, 'tools', 'a.py'))

    out = compile_boot_manifest(agent, workspace=ws)

    assert ws_index in out
    assert os.path.join(_longterm(agent), 'LONGTERM.md') not in out


def test_scan_longterm_returns_structure(agent):
    """scan_longterm 返回 categories / index_file / unavailable"""
    _self(agent)
    _mkfile(os.path.join(_longterm(agent), 'tools', 'a.py'))

    scan = scan_longterm([_longterm(agent)])

    assert scan['categories'] == {'tools': 1}
    assert scan['unavailable'] == []


def test_scan_longterm_reports_unavailable(basedir):
    """不存在的 root 进 unavailable，不进 categories"""
    missing = os.path.join(basedir, 'nope')

    scan = scan_longterm([missing])

    assert scan['unavailable'] == [missing]
    assert scan['categories'] == {}


def test_loose_files_not_counted_as_category(agent):
    """root 直接放的文件不计入类目（只能靠索引被发现）"""
    _self(agent)
    _mkfile(os.path.join(_longterm(agent), 'loose.md'))
    _mkfile(os.path.join(_longterm(agent), 'tools', 'a.py'))

    scan = scan_longterm([_longterm(agent)])

    assert scan['categories'] == {'tools': 1}


def test_hidden_dirs_skipped(agent):
    """`.` 开头的隐藏目录不当类目"""
    _self(agent)
    _mkfile(os.path.join(_longterm(agent), '.git', 'x'))
    _mkfile(os.path.join(_longterm(agent), 'tools', 'a.py'))

    scan = scan_longterm([_longterm(agent)])

    assert scan['categories'] == {'tools': 1}


# ============================================================
# 票2：CLI + 只读 + 超长提示
# ============================================================

def test_no_truncation_with_many_categories(agent):
    """建 20 个类目 → 20 个全在输出里，一个不少（不裁剪是硬要求）"""
    _self(agent)
    for i in range(20):
        _mkfile(os.path.join(_longterm(agent), f'cat{i:02d}', 'f.md'))

    out = compile_boot_manifest(agent)

    for i in range(20):
        assert f'cat{i:02d} 1' in out


def test_long_output_appends_hint(agent):
    """清单 >2000 字 → 末尾含提醒，且内容未被裁剪"""
    _self(agent)
    # 造足够多的类目让输出超阈值
    for i in range(120):
        _mkfile(os.path.join(_longterm(agent), f'category_with_a_long_name_{i:03d}', 'f.md'))

    out = compile_boot_manifest(agent)

    assert 'token 和上下文都很宝贵' in out
    # 内容未被裁剪：第一个和最后一个类目都还在
    assert 'category_with_a_long_name_000 1' in out
    assert 'category_with_a_long_name_119 1' in out


def test_readonly_no_mtime_change(agent):
    """跑前后 longterm 下所有文件 mtime 完全一致"""
    _self(agent)
    _mkfile(os.path.join(_longterm(agent), 'tools', 'a.py'))
    _mkfile(os.path.join(_longterm(agent), 'tools', 'b.py'))
    _mkfile(os.path.join(_longterm(agent), 'LONGTERM.md'), '# x\n')

    before = {
        p: os.stat(p).st_mtime_ns
        for p in [
            os.path.join(_longterm(agent), 'tools', 'a.py'),
            os.path.join(_longterm(agent), 'tools', 'b.py'),
            os.path.join(_longterm(agent), 'LONGTERM.md'),
        ]
    }

    compile_boot_manifest(agent)

    after = {p: os.stat(p).st_mtime_ns for p in before}
    assert before == after


def test_cli_requires_identity():
    """无参数 → 返回 2"""
    assert main([]) == 2


def test_cli_prints_manifest(agent, capsys):
    """正常调用 → stdout 含 `[开机]`，退出码 0"""
    _self(agent)
    _mkfile(os.path.join(_longterm(agent), 'tools', 'a.py'))

    rc = main(['--identity', agent])
    out = capsys.readouterr().out

    assert rc == 0
    assert '[开机]' in out


def test_identity_omits_missing_style_and_boundary(agent):
    """style / boundary 缺失时整段省略，不留空 `｜`"""
    ensure_self(agent, defaults={
        'name': 'kaibian',
        'anchor_tags': ['midnight'],
        'mutable': {},
        'description': 'x',
    })
    os.makedirs(_longterm(agent))

    out = compile_boot_manifest(agent)
    first = out.splitlines()[0]

    assert first == '[开机] 我是kaibian'
    assert '｜' not in first
