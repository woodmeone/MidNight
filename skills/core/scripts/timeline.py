"""Cross-session timeline — get recent messages from other sessions.

CLI: python timeline.py [--session NAME] [--limit 10] [--hours 24]
"""
import os
import sys
import sqlite3

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from schema import DEFAULT_DB_PATH


def get_timeline(session_id: str = None, limit: int = 10, hours: int = 24,
                 db_path: str = DEFAULT_DB_PATH) -> list[dict]:
    """Get recent messages from sessions OTHER than session_id, grouped by source.

    Returns list of dicts: {id, session_id, source, role, content, created_at}
    """
    if not os.path.exists(db_path):
        return []

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        if session_id:
            rows = conn.execute(
                """SELECT id, session_id, source, role, content, created_at
                   FROM messages
                   WHERE session_id != ?
                   AND datetime(created_at) > datetime('now', ?)
                   ORDER BY created_at DESC
                   LIMIT ?""",
                (session_id, f'-{hours} hours', limit)
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT id, session_id, source, role, content, created_at
                   FROM messages
                   WHERE datetime(created_at) > datetime('now', ?)
                   ORDER BY created_at DESC
                   LIMIT ?""",
                (f'-{hours} hours', limit)
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def format_timeline(messages: list[dict]) -> str:
    """Format timeline messages as a context-injectable text block with source markers."""
    if not messages:
        return "[跨端通知] 近24小时无其他会话记录。"

    # Group by source
    from collections import OrderedDict
    groups = OrderedDict()
    for m in messages:
        source = m['source'] or 'unknown'
        if source not in groups:
            groups[source] = []
        groups[source].append(m)

    lines = ["[跨端通知] 以下是来自其他会话的最近消息：\n"]
    for source, msgs in groups.items():
        source_label = f"来自 [{source}]"
        for m in reversed(msgs):  # chronological within group
            time_str = m['created_at'][:16] if m['created_at'] else ''
            role_icon = '🧑' if m['role'] == 'user' else '🤖'
            content = m['content'][:150]
            if len(m['content']) > 150:
                content += '…'
            lines.append(f"  {source_label} · {time_str} {role_icon} {content}")
    return "\n".join(lines)


def main(argv=None) -> int:
    """CLI: python timeline.py [--session NAME] [--limit 10] [--hours 24]"""
    argv = argv if argv is not None else sys.argv[1:]

    session_id = os.environ.get('MIDNIGHT_SESSION_ID')
    limit = 10
    hours = 24

    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == '--session' and i + 1 < len(argv):
            session_id = argv[i + 1]
            i += 2
        elif arg == '--limit' and i + 1 < len(argv):
            limit = int(argv[i + 1])
            i += 2
        elif arg == '--hours' and i + 1 < len(argv):
            hours = int(argv[i + 1])
            i += 2
        else:
            print(f"Unknown: {arg}", file=sys.stderr)
            return 2

    messages = get_timeline(session_id=session_id, limit=limit, hours=hours)
    output = format_timeline(messages)
    print(output)
    return 0


if __name__ == '__main__':
    sys.exit(main())