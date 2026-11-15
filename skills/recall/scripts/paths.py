"""可迁移路径（Issue #11）——库里不存盘符与用户名。

问题：`files.file_path` 原本存绝对路径（`C:\\Users\\WoodMe\\...`），
换机器 / 换用户名全断。ADR-0002 说「库是单文件，跟着 agent 走」——库能走，
路径不走。

解法：**兼容而不是强制迁移**。

- 新数据存相对 agent 目录的路径（正斜杠）
- 老数据仍是绝对路径，读取侧 `isabs` 判定后原样返回
- 两种共存，零迁移也能跑；迁移只是把老库也变成可搬的

还原基准取 `dirname(abspath(db_path))`——它天然就是 agent 目录，
不需要额外知道 agent 名（`recall(db_path)` 本来也拿不到）。
"""
import os


def stored_path(file_path: str, db_path: str) -> str:
    """入库时该存什么：能相对就相对（正斜杠），否则退回绝对路径。

    统一存正斜杠：Windows 反斜杠进 JSON / 跨平台时易出转义问题，
    正斜杠两边都能被 `os.path.join` 处理。
    """
    abs_path = os.path.abspath(file_path)
    base = os.path.dirname(os.path.abspath(db_path))
    try:
        rel = os.path.relpath(abs_path, base)
    except ValueError:
        # Windows 跨盘：没有公共前缀，只能退回绝对路径
        return abs_path
    if rel.startswith('..'):
        # 在 agent 目录之外——搬走时它跟着走不了，老实存绝对
        return abs_path
    return rel.replace('\\', '/')


def resolve_file_path(db_path: str, stored: str) -> str:
    """读取时该用什么：相对路径按 db 所在目录还原，绝对路径原样返回。

    **必须先 abspath 再 dirname**：`recall.py` 支持 `--db recall.db` 这种
    裸文件名，直接 `dirname('recall.db')` 会得到空串。
    """
    if not stored:
        return stored
    if os.path.isabs(stored):
        return stored
    base = os.path.dirname(os.path.abspath(db_path))
    return os.path.normpath(os.path.join(base, stored))


def resolve_from_conn(conn, stored: str) -> str:
    """同 `resolve_file_path`，但库路径从已打开的连接取。

    给 `expand_tag_candidates` 这类"只有 conn、没有 db_path"的函数用——
    否则同一个召回结果里，向量命中的路径是绝对、标签扩增的路径是相对，
    下游拿到两种格式必然出错。
    """
    if not stored or os.path.isabs(stored):
        return stored
    try:
        row = conn.execute('PRAGMA database_list').fetchone()
        db_path = row[2] if row else ''
    except Exception:      # noqa: BLE001 — 取不到就原样返回，不阻断召回
        return stored
    if not db_path:
        return stored
    return resolve_file_path(db_path, stored)
