"""Filter：对一组对象逐项判断是否满足一个条件（docs/designs/v2/operators.md §4.7）。

每项恰有一条判断，``U`` 不当作 ``F`` 丢弃。记录键为项键。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ...artifact.write import Output, Problems
from ..base import agent_operator, schema
from ._common import (
    JUDGMENT,
    VALUES,
    as_list,
    bullets,
    check_keys,
    is_key,
    is_text,
    items_of,
    judgment_shape,
    verdict_of,
    why,
)


def filter_(params: Mapping[str, Any], payload: Mapping[str, Any], problems: Problems) -> Output:
    """逐项判断是否满足条件；每项恰有一条判断，``U`` 不当作 ``F`` 丢弃。记录键为项键。"""
    out = Output("", "")
    check_keys(params, "params", {"items", "condition"}, {"items", "condition"}, problems)
    check_keys(payload, "payload", {"judgments"}, {"judgments"}, problems)
    items = items_of(params.get("items"), 1, out, problems)
    condition = params.get("condition")
    if not (isinstance(condition, Mapping) and set(condition) == {"id", "text"} and is_key(condition["id"])):
        problems.add("schema", "params.condition", "{id, text}; the id is a short key")
        condition = {"id": "condition", "text": ""}
    elif not is_text(condition["text"]):
        problems.add("schema", "params.condition.text", "a non-empty string")

    judged: dict[str, dict[str, Any]] = {}
    attempted: set[str] = set()
    for i, judgment in enumerate(as_list(payload.get("judgments"), "payload.judgments", problems)):
        at = f"payload.judgments[{i}]"
        if not judgment_shape(judgment, at, {"key"}, problems):
            continue
        key = judgment.get("key")
        if key not in items:
            problems.add("judgment", f"{at}.key", f"not a declared item: {key!r}")
        verdict = verdict_of(judgment, at, out, problems)
        if key in items:
            attempted.add(key)
        if key not in items or verdict is None:
            continue
        if key in judged:
            problems.add("judgment", at, f"a second judgment for {key}")
            continue
        judged[key] = {"key": key, **verdict}
    if absent := [k for k in items if k not in attempted]:
        problems.add("judgment", "payload.judgments", f"missing judgments: {', '.join(absent)}")

    ordered = [judged[k] for k in items if k in judged]
    body = [f"**Condition** `{condition['id']}`: {condition['text']}"]
    for value in VALUES:
        group = [j for j in ordered if j["value"] == value]
        lines = (f"`{j['key']}` [{items[j['key']]}]{why(j)}" for j in group)
        body += [f"## {value} ({len(group)})", bullets(lines) if group else "None."]
    out.title = f"Filter: {condition['id']}"
    out.body = "\n\n".join(body)
    out.data = {"items": items, "condition": dict(condition), "judgments": ordered}
    return out


FILTER = agent_operator(
    name="Filter",
    params=schema(
        {
            "items": {"type": "object"},
            "condition": schema({"id": {"type": "string"}, "text": {"type": "string"}}, ["id", "text"]),
        },
        ["items", "condition"],
    ),
    payload=schema(
        {"judgments": {"type": "array", "items": {**JUDGMENT}}},
        ["judgments"],
    ),
    validate=filter_,
)


__all__ = ["FILTER"]
