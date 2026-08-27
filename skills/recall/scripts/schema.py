"""SQLite schema for midnight-recall memory storage.

Five tables: files, chunks, tags, chunk_tags, tag_cooccurrence.
Plus: metadata table for cold/hot knowledge tracking.
"""
import sqlite3
import os

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path TEXT UNIQUE NOT NULL,
    diary_name TEXT NOT NULL DEFAULT 'default',
    checksum TEXT NOT NULL,
    diary_date TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER NOT NULL REFERENCES files(id),
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    vector BLOB,
    importance TEXT DEFAULT 'medium',
    access_count INTEGER DEFAULT 0,
    last_accessed TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(file_id, chunk_index)
);

CREATE TABLE IF NOT EXISTS tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    vector BLOB,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS chunk_tags (
    chunk_id INTEGER NOT NULL REFERENCES chunks(id),
    tag_id INTEGER NOT NULL REFERENCES tags(id),
    position INTEGER DEFAULT 0,
    PRIMARY KEY (chunk_id, tag_id)
);

CREATE TABLE IF NOT EXISTS tag_cooccurrence (
    tag1_id INTEGER NOT NULL REFERENCES tags(id),
    tag2_id INTEGER NOT NULL REFERENCES tags(id),
    weight REAL NOT NULL DEFAULT 1.0,
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (tag1_id, tag2_id),
    CHECK (tag1_id < tag2_id)
);

CREATE INDEX IF NOT EXISTS idx_chunks_file_id ON chunks(file_id);
CREATE INDEX IF NOT EXISTS idx_tags_name ON tags(name);
CREATE INDEX IF NOT EXISTS idx_tag_cooccurrence_weight ON tag_cooccurrence(weight DESC);
CREATE INDEX IF NOT EXISTS idx_chunks_importance ON chunks(importance);
CREATE INDEX IF NOT EXISTS idx_chunks_access ON chunks(access_count DESC);
"""


def init_db(db_path: str) -> sqlite3.Connection:
    """Initialize database: create tables if not exists. Returns connection."""
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    return conn