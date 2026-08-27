"""Append a message to the cross-session timeline.

CLI: python append.py --session "work" --source "web" --role user --content "消息内容"
"""
import hashlib
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from schema import init_db, DEFAULT_DB_PATH


def append(session_id: str, source: str, role: str, content: str,
           db_path: str = DEFAULT_DB_PATH) -> dict:
    """Append a message to the timeline. Returns {id, created_at}."""
    conn = init_db(db_path)
    try:
        checksum = hashlib.sha256(content.encode('utf-8')).hexdigest()
        # Check for duplicate (same content in same session within 5 minutes)
        existing = conn.execute(
            """SELECT id FROM messages
               WHERE session_id = ? AND checksum = ?
               AND datetime(created_at) > datetime('now', '-5 minutes')""",
            (session_id, checksum)
        ).fetchone()
        if existing:
            return {'id': existing[0], 'status': 'duplicate', 'created_at': None}

        cur = conn.execute(
            "INSERT INTO messages (session_id, source, role, content, checksum) VALUES (?, ?, ?, ?, ?)",
            (session_id, source, role, content, checksum)
        )
        conn.commit()
        row = conn.execute("SELECT created_at FROM messages WHERE id = ?", (cur.lastrowid,)).fetchone()
        return {'id': cur.lastrowid, 'status': 'appended', 'created_at': row[0]}
    finally:
        conn.close()


def main(argv=None) -> int:
    """CLI: python append.py --session NAME --source NAME --role user --content TEXT"""
    argv = argv if argv is not None else sys.argv[1:]

    session_id = os.environ.get('MIDNIGHT_SESSION_ID', 'default')
    source = os.environ.get('MIDNIGHT_SOURCE', 'unknown')
    role = 'user'
    content = ''

    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == '--session' and i + 1 < len(argv):
            session_id = argv[i + 1]
            i += 2
        elif arg == '--source' and i + 1 < len(argv):
            source = argv[i + 1]
            i += 2
        elif arg == '--role' and i + 1 < len(argv):
            role = argv[i + 1]
            i += 2
        elif arg == '--content' and i + 1 < len(argv):
            content = argv[i + 1]
            i += 2
        else:
            print(f"Unknown: {arg}", file=sys.stderr)
            return 2

    if not content:
        print("Usage: append.py --content TEXT [--session NAME] [--source NAME] [--role user|assistant]", file=sys.stderr)
        return 1

    result = append(session_id, source, role, content)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())