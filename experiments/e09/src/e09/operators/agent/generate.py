"""Generate：产出新内容，如最终回答、草稿、点子与方案（docs/designs/v2/operators.md §4.4）。

允许没有引用的段落，返回有引用的段落比例。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ...artifact.write import Output, Problems
from ...model.refs import cited, paragraphs
from ..base import agent_operator, schema
from ._common import (
    check_keys,
    is_text,
)

PURPOSES = ("answer", "draft", "idea", "plan", "other")


def generate(params: Mapping[str, Any], payload: Mapping[str, Any], problems: Problems) -> Output:
    """新内容：回答、草稿、点子、方案。允许没有引用的段落，返回有引用的段落比例。"""
    check_keys(params, "params", {"purpose"}, {"purpose"}, problems)
    check_keys(payload, "payload", {"text"}, {"text"}, problems)
    purpose, text = params.get("purpose"), payload.get("text")
    if purpose not in PURPOSES:
        problems.add("schema", "params.purpose", f"one of {list(PURPOSES)}")
    if not is_text(text):
        problems.add("schema", "payload.text", "a non-empty string")
        return Output("Generate", "")
    blocks = paragraphs(text)
    stats = {"cited_paragraphs": f"{sum(1 for b in blocks if cited(b))}/{len(blocks)}"}
    refs = [("payload.text", r) for r in cited(text)]
    title = f"Generate ({purpose})" if purpose in PURPOSES else "Generate"
    return Output(title, text.strip(), refs=refs, stats=stats)


GENERATE = agent_operator(
    name="Generate",
    label="Generate",
    description=(
        "Produce new content: a final answer, a draft, an idea or a plan. Numbers, comparisons and judgments "
        "should cite the artifacts they come from."
    ),
    params=schema({"purpose": {"enum": list(PURPOSES)}}, ["purpose"]),
    payload=schema({"text": {"type": "string", "description": "Markdown; cite inputs as [ref]."}}, ["text"]),
    validate=generate,
)


__all__ = ["GENERATE"]
