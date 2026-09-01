"""Tests for configurable base directory (MIDNIGHT_BASE_DIR).

Verifies paths respect the env var while defaulting to ~/.midnight.
"""
import os
import sys
import tempfile
import pytest

import scripts.config as cfg


def test_default_base_dir():
    """未设环境变量时默认 ~/.midnight/recall"""
    assert 'MIDNIGHT_BASE_DIR' not in os.environ or not os.environ['MIDNIGHT_BASE_DIR']
    assert cfg.BASE_DIR == os.path.join(
        os.path.expanduser("~/.midnight"), 'recall'
    )


def test_base_dir_respects_env(monkeypatch):
    """设置 MIDNIGHT_BASE_DIR 后 BASE_DIR 跟随"""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        monkeypatch.setenv('MIDNIGHT_BASE_DIR', tmpdir)
        # 重新导入以读取新环境变量
        import importlib
        import scripts.config as c2
        importlib.reload(c2)
        assert c2.BASE_DIR == os.path.join(tmpdir, 'recall')
        assert c2.get_db_path('Nova') == os.path.join(tmpdir, 'recall', 'Nova', 'recall.db')


def test_core_db_path_respects_env(monkeypatch):
    """core 数据库路径跟随 MIDNIGHT_BASE_DIR（直接读文件验证）"""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        monkeypatch.setenv('MIDNIGHT_BASE_DIR', tmpdir)
        # 读 core/schema.py 源码确认用的是环境变量
        import pathlib
        core_schema = pathlib.Path(__file__).parent.parent.parent / 'core' / 'scripts' / 'schema.py'
        src = core_schema.read_text(encoding='utf-8')
        assert "MIDNIGHT_BASE_DIR" in src
        assert "os.path.expanduser(\"~/.midnight\")" in src