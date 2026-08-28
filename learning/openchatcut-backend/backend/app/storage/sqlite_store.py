"""SQLite KV 文档库（对齐原版 server/storage/sqlite-store.ts 的最小实现）。

原版是 node:sqlite 的 key-value JSON 文档库（非关系型），核心一张 kv(k,v) 表，
value 是 JSON 字符串。这里用 sqlite3 stdlib 等价实现，作为 persist.py 的存储后端。
"""
from __future__ import annotations

import json
import sqlite3


class SqliteStore:
    def __init__(self, path: str):
        self._conn = sqlite3.connect(path)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=FULL")
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT NOT NULL)"
        )
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS storage_migration_state ("
            " singleton INTEGER PRIMARY KEY CHECK (singleton = 1),"
            " state TEXT NOT NULL CHECK (state = 'complete'),"
            " receipt TEXT NOT NULL)"
        )
        self._conn.commit()

    def get(self, k: str) -> str | None:
        row = self._conn.execute("SELECT v FROM kv WHERE k = ?", (k,)).fetchone()
        return row[0] if row else None

    def put(self, k: str, v: str) -> None:
        self._conn.execute(
            "INSERT INTO kv (k, v) VALUES (?, ?) "
            "ON CONFLICT(k) DO UPDATE SET v = excluded.v",
            (k, v),
        )
        self._conn.commit()

    def delete(self, k: str) -> None:
        self._conn.execute("DELETE FROM kv WHERE k = ?", (k,))
        self._conn.commit()

    def has_migration_receipt(self) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM storage_migration_state WHERE singleton = 1"
        ).fetchone()
        return row is not None

    def set_migration_receipt(self, receipt: dict) -> None:
        self._conn.execute(
            "INSERT INTO storage_migration_state (singleton, state, receipt) "
            "VALUES (1, 'complete', ?)",
            (json.dumps(receipt, ensure_ascii=False),),
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()
