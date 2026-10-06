"""Verify：一条主张在给定证据下是否成立，以及成立的范围（docs/designs/v2/operators.md §4.6）。

没有找到支持不等于反驳，应为 ``U``。``claim`` 为引用时，其 ``USED`` 边的 ``role`` 含 ``claim``。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ...artifact.write import Output, Problems
from ..base import agent_operator, schema
from ._common import (
    JUDGMENT,
    check_keys,
    is_text,
    judgment_shape,
    verdict_of,
)


def verify(params: Mapping[str, Any], payload: Mapping[str, Any], problems: Problems) -> Output:
    """一条主张在给定证据下是否成立，以及成立的范围。没有找到支持不等于反驳，应为 ``U``。"""
    out = Output("", "")
    check_keys(params, "params", {"claim"}, {"claim"}, problems)
    claim = params.get("claim")
    if is_text(claim):
        out.refs.append(("params.claim", claim))
        out.roles.setdefault(claim, []).append("claim")
        stated = f"[{claim}]"
    elif isinstance(claim, Mapping) and set(claim) == {"text"} and is_text(claim["text"]):
        stated = claim["text"].strip()
    else:
        problems.add("schema", "params.claim", "a reference or {text}")
        stated = "—"
    verdict = None
    if judgment_shape(payload, "payload", {"conditions"}, problems, required=frozenset()):
        verdict = verdict_of(payload, "payload", out, problems)
    conditions = payload.get("conditions")
    if conditions is not None and not is_text(conditions):
        problems.add("schema", "payload.conditions", "a non-empty string")
    lines = [f"**Claim:** {stated}", f"**Value:** {payload.get('value', '—')}"]
    if is_text(conditions):
        lines.append(f"**Conditions:** {conditions.strip()}")
    if verdict and verdict.get("basis"):
        lines.append("**Basis:** " + ", ".join(f"[{r}]" for r in verdict["basis"]))
    if verdict and verdict.get("reason"):
        lines.append(f"**Reason:** {verdict['reason']}")
    out.title = f"Verify {stated}" if len(stated) <= 80 else f"Verify {stated[:77]}..."
    out.body = "\n\n".join(lines)
    return out


VERIFY = agent_operator(
    name="Verify",
    label="Verify",
    description=(
        "Judge whether a claim holds under the given evidence (T supported, F refuted, U insufficient) and state "
        "the conditions under which it holds. Finding no support is U, not F."
    ),
    params=schema({"claim": {"description": "A reference or {text}"}}, ["claim"]),
    payload=schema(
        {**JUDGMENT["properties"], "conditions": {"type": "string"}},
        ["value"],
    ),
    validate=verify,
)


__all__ = ["VERIFY"]
