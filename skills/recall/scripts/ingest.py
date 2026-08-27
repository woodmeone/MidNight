"""Ingest diary files into the midnight-recall memory store.

Core logic: parse diary file (YAML frontmatter + body), chunk it,
embed each chunk, write into SQLite. Idempotent via checksum.
Supports importance (low/medium/high) for hot/cold knowledge.
"""
import hashlib
import json
import os
import re
import sqlite3
import sys
from datetime import datetime
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from schema import init_db  # noqa: E402
from scripts.config import get_db_path, get_dailynote_path, ensure_agent_dir  # noqa: E402

MAX_CHUNK_CHARS = 512

FRONTMATTER_PATTERN = re.compile(r'^---\s*\n(.*?)\n---\s*\n?(.*)$', re.DOTALL)


def parse_diary(content: str) -> dict:
    """Parse diary content into {maid, created, tags[], body, importance}."""
    result = {
        'maid': 'default',
        'created': datetime.now().isoformat(timespec='seconds'),
        'tags': [],
        'body': content.strip(),
        'importance': 'medium',
    }
    m = FRONTMATTER_PATTERN.match(content)
    if not m:
        return result

    frontmatter_text, body = m.group(1), m.group(2)
    result['body'] = body.strip()

    for line in frontmatter_text.splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if ':' not in line:
            continue
        key, _, value = line.partition(':')
        key = key.strip().lower()
        value = value.strip()
        if key == 'maid':
            result['maid'] = value
        elif key == 'created':
            result['created'] = value
        elif key == 'importance':
            if value.lower() in ('high', 'medium', 'low'):
                result['importance'] = value.lower()
        elif key == 'tags':
            tags = re.findall(r'[\u4e00-\u9fff\w-]+', value)
            result['tags'] = tags
    return result


def compute_checksum(content: str) -> str:
    """SHA-256 checksum of file content."""
    return hashlib.sha256(content.encode('utf-8')).hexdigest()


def chunk_body(body: str, max_chars: int = MAX_CHUNK_CHARS) -> list[str]:
    """Split body into chunks by paragraph, capping length."""
    if not body.strip():
        return []
    paragraphs = [p.strip() for p in re.split(r'\n\s*\n', body) if p.strip()]
    if not paragraphs:
        paragraphs = [body.strip()]

    chunks = []
    for para in paragraphs:
        if len(para) <= max_chars:
            chunks.append(para)
        else:
            # Hard split long paragraph
            for i in range(0, len(para), max_chars):
                chunks.append(para[i:i + max_chars])
    return chunks


def _serialize_vector(vec: list[float]) -> bytes:
    """Serialize float list to bytes for BLOB storage."""
    import struct
    return struct.pack(f'{len(vec)}f', *vec)


def _deserialize_vector(blob) -> Optional[list[float]]:
    """Deserialize BLOB back to float list."""
    import struct
    if blob is None:
        return None
    return list(struct.unpack(f'{len(blob) // 4}f', blob))


def ingest_file(file_path: str, db_path: str, embedding_client, conn: Optional[sqlite3.Connection] = None) -> dict:
    """Ingest a single diary file. Idempotent via checksum.

    Returns {"status": "ingested"|"skipped", "file_id": int|None, "chunks_count": int}
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    checksum = compute_checksum(content)
    abs_path = os.path.abspath(file_path)

    own_conn = conn is None
    if own_conn:
        conn = init_db(db_path)

    try:
        # Check existing file record
        row = conn.execute(
            "SELECT id, checksum FROM files WHERE file_path = ?", (abs_path,)
        ).fetchone()
        if row and row[1] == checksum:
            return {'status': 'skipped', 'file_id': row[0], 'chunks_count': 0}

        parsed = parse_diary(content)

        # Create or update file record
        if row:
            file_id = row[0]
            conn.execute(
                "UPDATE files SET checksum = ?, updated_at = datetime('now') WHERE id = ?",
                (checksum, file_id)
            )
            # Delete old chunks (and their tag links)
            conn.execute("DELETE FROM chunk_tags WHERE chunk_id IN (SELECT id FROM chunks WHERE file_id = ?)", (file_id,))
            conn.execute("DELETE FROM chunks WHERE file_id = ?", (file_id,))
        else:
            # Extract just the date part from created for diary_date
            diary_date = parsed['created'][:10] if parsed['created'] else None
            cur = conn.execute(
                "INSERT INTO files (file_path, diary_name, checksum, diary_date) VALUES (?, ?, ?, ?)",
                (abs_path, parsed['maid'], checksum, diary_date)
            )
            file_id = cur.lastrowid

        # Chunk and embed
        chunks = chunk_body(parsed['body'])
        vectors = []
        if chunks:
            vectors = embedding_client.embed(chunks) if hasattr(embedding_client, 'embed') else []
            if len(vectors) != len(chunks):
                # Safety: embed returned different count, pad or truncate
                vectors = vectors[:len(chunks)] if vectors else []
                if len(vectors) < len(chunks):
                    import struct
                    empty_vec = [0.0] * (len(vectors[0]) if vectors else 4)
                    vectors.extend([empty_vec] * (len(chunks) - len(vectors)))

        # Insert chunks
        chunk_ids = []
        for idx, (chunk_text, vec) in enumerate(zip(chunks, vectors)):
            cur = conn.execute(
                "INSERT INTO chunks (file_id, chunk_index, content, vector, importance) VALUES (?, ?, ?, ?, ?)",
                (file_id, idx, chunk_text, _serialize_vector(vec), parsed['importance'])
            )
            chunk_ids.append(cur.lastrowid)

        # Insert tags (upsert) and link to all chunks of this file
        tag_ids = []
        for tag_name in parsed['tags']:
            if not tag_name:
                continue
            # Upsert tag
            existing = conn.execute("SELECT id FROM tags WHERE name = ?", (tag_name,)).fetchone()
            if existing:
                tag_id = existing[0]
            else:
                # Embed tag name for associative search
                tag_vec = embedding_client.embed([tag_name])[0] if hasattr(embedding_client, 'embed') else []
                cur = conn.execute(
                    "INSERT INTO tags (name, vector) VALUES (?, ?)",
                    (tag_name, _serialize_vector(tag_vec) if tag_vec else None)
                )
                tag_id = cur.lastrowid
            tag_ids.append(tag_id)
            for position, chunk_id in enumerate(chunk_ids):
                conn.execute(
                    "INSERT OR IGNORE INTO chunk_tags (chunk_id, tag_id, position) VALUES (?, ?, ?)",
                    (chunk_id, tag_id, position)
                )

        # Update co-occurrence matrix: all tag pairs in the same file get weight +1
        for i in range(len(tag_ids)):
            for j in range(i + 1, len(tag_ids)):
                t1, t2 = sorted((tag_ids[i], tag_ids[j]))
                conn.execute(
                    """INSERT INTO tag_cooccurrence (tag1_id, tag2_id, weight, updated_at)
                       VALUES (?, ?, 1.0, datetime('now'))
                       ON CONFLICT(tag1_id, tag2_id) DO UPDATE SET
                         weight = weight + 1,
                         updated_at = datetime('now')""",
                    (t1, t2)
                )

        conn.commit()
        return {
            'status': 'ingested',
            'file_id': file_id,
            'chunks_count': len(chunk_ids),
            'tags': [parsed['tags']],
        }
    finally:
        if own_conn:
            conn.close()


def ingest_directory(diary_dir: str, db_path: str, embedding_client) -> dict:
    """Ingest all .md files in a directory. Returns summary."""
    results = {'ingested': 0, 'skipped': 0, 'files': []}
    conn = init_db(db_path)
    try:
        for filename in sorted(os.listdir(diary_dir)):
            if not filename.endswith('.md') and not filename.endswith('.txt'):
                continue
            file_path = os.path.join(diary_dir, filename)
            if not os.path.isfile(file_path):
                continue
            r = ingest_file(file_path, db_path, embedding_client, conn=conn)
            results['files'].append({'path': file_path, 'status': r['status']})
            results[r['status']] += 1
    finally:
        conn.close()
    return results


def main(argv=None) -> int:
    """CLI: python ingest.py [file_or_dir] [--agent NAME] [--db PATH] [--diary PATH] [--key KEY]"""
    argv = argv if argv is not None else sys.argv[1:]

    target = None
    agent = os.environ.get('MIDNIGHT_AGENT')
    db_path = None
    diary_dir = None
    api_key = os.environ.get('SILICONFLOW_API_KEY', '')

    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == '--agent' and i + 1 < len(argv):
            agent = argv[i + 1]
            i += 2
        elif arg == '--db' and i + 1 < len(argv):
            db_path = argv[i + 1]
            i += 2
        elif arg == '--diary' and i + 1 < len(argv):
            diary_dir = argv[i + 1]
            i += 2
        elif arg == '--key' and i + 1 < len(argv):
            api_key = argv[i + 1]
            i += 2
        elif arg.startswith('-'):
            print(f"Unknown option: {arg}", file=sys.stderr)
            return 2
        else:
            target = arg
            i += 1

    # Resolve paths from agent if not explicitly set
    db_path = db_path or get_db_path(agent)
    diary_dir = diary_dir or get_dailynote_path(agent)
    ensure_agent_dir(agent)

    from embedding import load_embedding_client
    config = {'api_key': api_key, 'dimension': 1024}
    client = load_embedding_client(config)

    if target:
        if os.path.isdir(target):
            results = ingest_directory(target, db_path, client)
        else:
            r = ingest_file(target, db_path, client)
            results = {'ingested': 1 if r['status'] == 'ingested' else 0,
                       'skipped': 1 if r['status'] == 'skipped' else 0,
                       'files': [r]}
    else:
        # default: ingest whole diary dir
        if not os.path.isdir(diary_dir):
            print(f"Diary dir not found: {diary_dir}", file=sys.stderr)
            return 1
        results = ingest_directory(diary_dir, db_path, client)

    print(json_dumps(results))
    return 0


def json_dumps(obj) -> str:
    import json
    return json.dumps(obj, ensure_ascii=False, indent=2)


if __name__ == '__main__':
    sys.exit(main())