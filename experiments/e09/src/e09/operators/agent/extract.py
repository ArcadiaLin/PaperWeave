"""Extract：读原文后，把需要的具体信息取成结构化记录（docs/designs/v2/operators.md §4.2）。

记录键由 ``schema.key`` 中字段的值依次转成小写、非字母数字换成 ``-`` 后用 ``-`` 连接，在本次产物中唯一。
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from ...artifact.write import Output, Problems
from ..base import agent_operator, schema
from ._common import (
    FIELD_TYPES,
    cell_text,
    check_keys,
    is_text,
    is_typed,
    parse_type,
    table,
    type_name,
)

_FIELD_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_]*")


def extract(params: Mapping[str, Any], payload: Mapping[str, Any], problems: Problems) -> Output:
    """读原文后取成的结构化记录。记录键由 ``schema.key`` 中字段的值拼成，在本次产物中唯一。"""
    out = Output("", "")
    check_keys(params, "params", {"schema"}, {"schema"}, problems)
    check_keys(payload, "payload", {"rows"}, {"rows", "note"}, problems)
    schema = params.get("schema")
    if not isinstance(schema, Mapping):
        problems.add("schema", "params.schema", "{fields: {name: type}, required: [...], key: [...]}")
        return out
    check_keys(schema, "params.schema", {"fields", "key"}, {"fields", "required", "key"}, problems)
    fields = _fields(schema.get("fields"), problems)
    required = _subset(schema.get("required", []), fields, "params.schema.required", problems)
    key = _subset(schema.get("key"), fields, "params.schema.key", problems)
    if not key:
        problems.add("schema", "params.schema.key", "name at least one field; record keys are built from them")

    rows = payload.get("rows")
    if not isinstance(rows, list):
        problems.add("schema", "payload.rows", "a list of records")
        rows = []
    note = payload.get("note")
    if note is not None and not is_text(note):
        problems.add("schema", "payload.note", "a non-empty string")
    if not rows and not is_text(note):
        problems.add("schema", "payload.note", "an empty result needs a note: what was read and why nothing was found")

    records: list[dict[str, Any]] = []
    seen: dict[str, int] = {}
    for i, row in enumerate(rows):
        at = f"payload.rows[{i}]"
        if not isinstance(row, Mapping):
            problems.add("schema", at, "a record is a mapping of fields and source")
            continue
        if unknown := sorted(set(row) - set(fields) - {"source"}):
            problems.add("schema", at, f"fields not in the schema: {unknown}")
        source = row.get("source")
        if not is_text(source):
            problems.add("schema", f"{at}.source", "the reference this record was read from")
        else:
            out.refs.append((f"{at}.source", source))
        record: dict[str, Any] = {}
        for name, type_ in fields.items():
            value = row.get(name)
            if value is None or value == "":
                if name in required or name in key:
                    problems.add("schema", f"{at}.{name}", "required")
                continue
            if not is_typed(value, type_):
                problems.add("schema", f"{at}.{name}", f"not a {type_name(type_)}: {value!r}")
                continue
            if type_ == "ref":
                out.refs.append((f"{at}.{name}", value))
            record[name] = value
        if key and all(name in record for name in key):
            record_key = "-".join(_slug(str(record[name])) for name in key)
            if not record_key.strip("-"):
                problems.add("schema", at, "the key fields give an empty record key")
            elif record_key in seen:
                problems.add("schema", at, f"key {record_key!r} repeats payload.rows[{seen[record_key]}]")
            else:
                seen[record_key] = i
            records.append({"key": record_key, **record, "source": source})

    names = list(fields)
    cells = [
        [r["key"], *(cell_text(r.get(n), fields[n]) for n in names), f"[{r['source']}]" if r["source"] else "—"]
        for r in records
    ]
    body = table(["key", *names, "source"], cells) if records else "No records."
    if is_text(note):
        body += f"\n\n**Note:** {note.strip()}"
    data: dict[str, Any] = {
        "schema": {"fields": dict(schema.get("fields") or {}), "required": required, "key": key},
        "rows": records,
    }
    if is_text(note):
        data["note"] = note.strip()
    out.title = "Extract: " + ", ".join(names)
    out.body, out.data = body, data
    return out


def _fields(value: Any, problems: Problems) -> dict[str, Any]:
    if not isinstance(value, Mapping) or not value:
        problems.add("schema", "params.schema.fields", "a non-empty mapping of field name to type")
        return {}
    fields: dict[str, Any] = {}
    for name, type_ in value.items():
        at = f"params.schema.fields.{name}"
        if not isinstance(name, str) or not _FIELD_NAME.fullmatch(name) or name in ("key", "source"):
            problems.add(
                "schema",
                at,
                "field names are letters, digits and _, starting with a letter; key and source are reserved",
            )
            continue
        parsed = parse_type(type_)
        if parsed is None:
            problems.add("schema", at, f"one of {list(FIELD_TYPES)} or enum[a, b, ...]")
            continue
        fields[name] = parsed
    return fields


def _subset(value: Any, fields: Mapping[str, Any], at: str, problems: Problems) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(v in fields for v in value):
        problems.add("schema", at, f"a list of fields from {list(fields)}")
        return []
    return list(dict.fromkeys(value))


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9._]+", "-", value.lower()).strip("-")


EXTRACT = agent_operator(
    name="Extract",
    params=schema(
        {
            "schema": schema(
                {
                    "fields": {
                        "type": "object",
                    },
                    "required": {"type": "array", "items": {"type": "string"}},
                    "key": {"type": "array", "items": {"type": "string"}},
                },
                ["fields", "key"],
            )
        },
        ["schema"],
    ),
    payload=schema(
        {
            "rows": {"type": "array", "items": {"type": "object"}},
            "note": {"type": "string"},
        },
        ["rows"],
    ),
    validate=extract,
)


__all__ = ["EXTRACT"]
