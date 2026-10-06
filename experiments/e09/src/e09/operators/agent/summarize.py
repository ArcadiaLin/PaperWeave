"""Summarize：忠实压缩与重组输入中已有的内容，每个段落至少有一处引用（docs/designs/v2/operators.md §4.3）。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ...artifact.write import Output, Problems
from ...model.refs import cited, paragraphs
from ..base import agent_operator, schema
from ._common import (
    check_keys,
    head,
    is_text,
)


def summarize(params: Mapping[str, Any], payload: Mapping[str, Any], problems: Problems) -> Output:
    """忠实压缩输入：每个段落至少有一处引用。"""
    check_keys(params, "params", {"focus"}, {"focus"}, problems)
    check_keys(payload, "payload", {"text"}, {"text"}, problems)
    focus, text = params.get("focus"), payload.get("text")
    if not is_text(focus):
        problems.add("schema", "params.focus", "a non-empty string")
    if not is_text(text):
        problems.add("schema", "payload.text", "a non-empty string")
        return Output("Summary", "")
    for n, paragraph in enumerate(paragraphs(text), start=1):
        if not cited(paragraph):
            problems.add("citation", "payload.text", f"paragraph {n} has no reference: {head(paragraph)}")
    refs = [("payload.text", r) for r in cited(text)]
    return Output(f"Summary: {focus}" if is_text(focus) else "Summary", text.strip(), refs=refs)


SUMMARIZE = agent_operator(
    name="Summarize",
    label="Summarize",
    description=(
        "Compress and reorganize what the inputs already say. Every paragraph must cite at least one input in "
        "square brackets; use Generate when inference or new content is needed."
    ),
    params=schema({"focus": {"type": "string"}}, ["focus"]),
    payload=schema({"text": {"type": "string", "description": "Markdown; cite inputs as [ref]."}}, ["text"]),
    validate=summarize,
)


__all__ = ["SUMMARIZE"]
