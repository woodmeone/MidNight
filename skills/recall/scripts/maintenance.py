"""Maintenance utilities for midnight-recall — orphan-data detection & migration.

多智能体物理隔离要求每个 agent 有自己的 recall.db 与 dailynote/。早期单库时代的
数据会残留在 `BASE_DIR` 根层（根级 `recall.db`、根级 `dailynote/`、根级散落 *.md），
它们不属于任何 agent，`list_agents()` 也看不到——"漂"在系统外，没人维护。

本脚本负责检测与迁移这类孤儿数据，把根级日记并入指定 agent（默认 default）并
重新入库；根级旧 recall.db 在目标 agent 无库时迁入，有库时备份保留（绝不删除）。

CLI:
    python maintenance.py --scan                     # 只报告，不修改
    python maintenance.py --migrate [--agent X]      # 迁移根级孤儿数据到 agent
"""
import os
import shutil
import sys

_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _SCRIPTS_DIR)                      # 让 from scripts.config 可用
sys.path.insert(0, os.path.dirname(_SCRIPTS_DIR))     # 让 from scripts.xxx 可用
from scripts.config import (  # noqa: E402
    BASE_DIR, DEFAULT_AGENT, get_agent_dir, get_db_path, get_dailynote_path,
    ensure_agent_dir,
)

ROOT_DB_NAME = 'recall.db'
ROOT_DAILYNOTE_NAME = 'dailynote'
ROOT_DB_BACKUP_SUFFIX = '.root.bak'


def detect_orphans(base_dir: str = None) -> dict:
    """Detect root-level data that belongs to no agent.

    Returns {'recall_db': path|None, 'dailynote_files': [names], 'loose_files': [names]}.
    """
    base = base_dir or BASE_DIR
    orphans = {'recall_db': None, 'dailynote_files': [], 'loose_files': []}
    if not os.path.isdir(base):
        return orphans

    root_db = os.path.join(base, ROOT_DB_NAME)
    if os.path.isfile(root_db):
        orphans['recall_db'] = root_db

    root_daily = os.path.join(base, ROOT_DAILYNOTE_NAME)
    if os.path.isdir(root_daily):
        orphans['dailynote_files'] = sorted(
            f for f in os.listdir(root_daily) if f.endswith('.md'))

    for f in sorted(os.listdir(base)):
        fp = os.path.join(base, f)
        if os.path.isfile(fp) and f != ROOT_DB_NAME and f.endswith('.md'):
            orphans['loose_files'].append(f)
    return orphans


def migrate_orphans(agent: str = None, base_dir: str = None) -> dict:
    """Migrate root-level orphan data into `agent` (default: default).

    - Root dailynote/*.md and root loose *.md → moved into <agent>/dailynote/.
    - Root recall.db → moved to <agent>/recall.db if the agent has none;
      otherwise renamed to recall.db.root.bak (preserved, never overwritten).
    - After moving, the agent's dailynote is ingested so the content is indexed.
    Returns {'moved_diaries': n, 'db_action': 'moved'|'backed_up'|'none',
             'ingested': n}.
    """
    agent = agent or os.environ.get('MIDNIGHT_AGENT') or DEFAULT_AGENT
    base = base_dir or BASE_DIR
    result = {'moved_diaries': 0, 'db_action': 'none', 'ingested': 0}
    if not os.path.isdir(base):
        return result

    ensure_agent_dir(agent)
    agent_daily = get_dailynote_path(agent)

    # 1) 根级 dailynote 与散落 *.md → agent/dailynote
    moved = []
    for name in (detect_orphans(base)['dailynote_files']
                 + detect_orphans(base)['loose_files']):
        src = os.path.join(base, ROOT_DAILYNOTE_NAME, name) if os.path.exists(
            os.path.join(base, ROOT_DAILYNOTE_NAME, name)) else os.path.join(base, name)
        dst = os.path.join(agent_daily, name)
        if os.path.exists(dst):
            dst = os.path.join(agent_daily, f'{name}.root')
        shutil.move(src, dst)
        moved.append(os.path.basename(dst))
    result['moved_diaries'] = len(moved)

    # 2) 根级 recall.db → agent db 或备份
    root_db = os.path.join(base, ROOT_DB_NAME)
    agent_db = get_db_path(agent)
    if os.path.isfile(root_db):
        if not os.path.exists(agent_db):
            shutil.move(root_db, agent_db)
            result['db_action'] = 'moved'
        else:
            shutil.move(root_db, root_db + ROOT_DB_BACKUP_SUFFIX)
            result['db_action'] = 'backed_up'

    # 3) 重新入库 agent 的 dailynote（把迁入内容索引进 agent db）
    if moved:
        from scripts.schema import init_db
        from scripts.ingest import ingest_directory
        from embedding import load_embedding_client
        db = get_db_path(agent)
        _init = init_db(db)
        _init.close()
        client = load_embedding_client({})
        res = ingest_directory(agent_daily, db, client)
        result['ingested'] = res.get('ingested', 0)

    return result


def main(argv=None) -> int:
    """CLI: maintenance.py --scan | --migrate [--agent X]"""
    argv = argv if argv is not None else sys.argv[1:]
    agent = os.environ.get('MIDNIGHT_AGENT')
    action = None

    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == '--scan':
            action = 'scan'
        elif arg == '--migrate':
            action = 'migrate'
        elif arg == '--agent' and i + 1 < len(argv):
            agent = argv[i + 1]
            i += 1
        else:
            print(f"Unknown option: {arg}", file=sys.stderr)
            return 2
        i += 1

    if action == 'scan':
        o = detect_orphans()
        print(f"根级孤儿数据扫描（{BASE_DIR}）:")
        if o['recall_db']:
            print(f"  recall.db : {o['recall_db']}")
        if o['dailynote_files']:
            print(f"  dailynote/{len(o['dailynote_files'])} 篇日记")
        if o['loose_files']:
            print(f"  根级散落 *.md : {o['loose_files']}")
        if not (o['recall_db'] or o['dailynote_files'] or o['loose_files']):
            print("  无孤儿数据。")
        return 0

    if action == 'migrate':
        result = migrate_orphans(agent)
        import json
        print(json.dumps({'status': 'ok', **result}, ensure_ascii=False))
        return 0

    print("Usage: maintenance.py --scan | --migrate [--agent X]", file=sys.stderr)
    return 1


if __name__ == '__main__':
    sys.exit(main())
