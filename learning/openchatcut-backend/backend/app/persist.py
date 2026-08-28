"""持久化：ProjectDoc 的 SQLite KV 文档库（对齐原版 sqlite-store）。

迁移：首启若无 SQLite 且存在旧 JSON 快照（data/project.json），导入并写 receipt；
之后走 SQLite。receipt 缺失时回退 JSON 读取，保持向后兼容。
"""
from __future__ import annotations

import dataclasses
import json
import os
import types
from dataclasses import is_dataclass
from typing import Any, Union, get_args, get_origin, get_type_hints

from .domain.timeline import ProjectDoc, project_to_dict
from .storage.sqlite_store import SqliteStore

PROJECT_KEY = "project:default"


def _coerce(tp, value):
    """按字段类型注解递归反序列化 JSON 值。"""
    if value is None:
        return None
    origin = get_origin(tp)
    if origin is tuple:
        args = get_args(tp)
        elem_tp = args[0] if args else Any
        return tuple(_coerce(elem_tp, v) for v in value)
    if origin is list:
        args = get_args(tp)
        elem_tp = args[0] if args else Any
        return [_coerce(elem_tp, v) for v in value]
    if origin is dict:
        args = get_args(tp)
        val_tp = args[1] if len(args) > 1 else Any
        return {k: _coerce(val_tp, v) for k, v in value.items()}
    if origin is Union or origin is types.UnionType:
        non_none = [a for a in get_args(tp) if a is not type(None)]
        if non_none:
            return _coerce(non_none[0], value)
        return value
    if is_dataclass(tp):
        return _construct(tp, value)
    return value


def _construct(cls, value):
    if value is None:
        return None
    hints = get_type_hints(cls)
    kwargs = {}
    for f in dataclasses.fields(cls):
        if f.name in value:
            kwargs[f.name] = _coerce(hints.get(f.name, Any), value[f.name])
    return cls(**kwargs)


def project_from_dict(data: dict) -> ProjectDoc:
    return _construct(ProjectDoc, data)


def data_dir() -> str:
    return os.environ.get("OPENCHATCUT_DATA_DIR", "data")


def default_path() -> str:
    """SQLite DB 文件路径（默认存储位置）。"""
    return os.path.join(data_dir(), "project-store.sqlite3")


def legacy_json_path() -> str:
    """旧版 JSON 快照路径（迁移源）。"""
    return os.path.join(data_dir(), "project.json")


def _load_json(path: str) -> ProjectDoc | None:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return project_from_dict(data)
    except (json.JSONDecodeError, FileNotFoundError, OSError):
        return None


def _mark_migrated(db_path: str, legacy: str) -> None:
    store = SqliteStore(db_path)
    try:
        store.set_migration_receipt({"source": legacy, "phase": 1})
    finally:
        store.close()


def save_project(doc: ProjectDoc, path: str | None = None) -> None:
    """写 ProjectDoc 到 SQLite（path 为 DB 文件路径，默认 data/project-store.sqlite3）。"""
    db_path = path or default_path()
    parent = os.path.dirname(db_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    store = SqliteStore(db_path)
    try:
        store.put(PROJECT_KEY, json.dumps(project_to_dict(doc), ensure_ascii=False))
    finally:
        store.close()


def load_project(path: str | None = None) -> ProjectDoc | None:
    """从 SQLite 读 ProjectDoc；默认路径下 DB 缺失时从旧 JSON 迁移。"""
    db_path = path or default_path()
    if not os.path.exists(db_path):
        # 迁移只在默认路径场景触发（显式 path 只读该 DB，不存在即 None）
        if path is None:
            legacy = legacy_json_path()
            if os.path.exists(legacy):
                doc = _load_json(legacy)
                if doc is not None:
                    save_project(doc, db_path)
                    _mark_migrated(db_path, legacy)
                    return doc
        return None
    store = SqliteStore(db_path)
    try:
        raw = store.get(PROJECT_KEY)
    finally:
        store.close()
    if raw is None:
        return None
    return project_from_dict(json.loads(raw))
