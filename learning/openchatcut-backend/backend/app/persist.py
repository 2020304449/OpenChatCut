"""run 持久化：ProjectDoc 的 JSON 文件快照（B5，零新依赖）。"""
from __future__ import annotations

import dataclasses
import json
import os
import types
from dataclasses import is_dataclass
from typing import Any, Union, get_args, get_origin, get_type_hints

from .domain.timeline import ProjectDoc, project_to_dict


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


def default_path() -> str:
    base = os.environ.get("OPENCHATCUT_DATA_DIR", "data")
    return os.path.join(base, "project.json")


def save_project(doc: ProjectDoc, path: str | None = None) -> None:
    p = path or default_path()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(project_to_dict(doc), f, ensure_ascii=False, indent=2)


def load_project(path: str | None = None) -> ProjectDoc | None:
    p = path or default_path()
    if not os.path.exists(p):
        return None
    with open(p, "r", encoding="utf-8") as f:
        data = json.load(f)
    return project_from_dict(data)
