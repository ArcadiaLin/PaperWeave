"""Check：成对的项在声明的维度上是否一致或可比（docs/designs/v2/operators.md §4.5）。

每个 (对, 维度) 恰有一条判断，对不计顺序。记录键为 ``<k1>~<k2>``。
"""

from __future__ import annotations

import itertools
from collections.abc import Iterable, Mapping
from typing import Any

from ...artifact.write import Output, Problems
from ..base import agent_operator, schema
from ._common import (
    JUDGMENT,
    as_list,
    bullets,
    check_keys,
    is_key,
    is_text,
    items_of,
    judgment_shape,
    table,
    verdict_of,
    why,
)


def check(params: Mapping[str, Any], payload: Mapping[str, Any], problems: Problems) -> Output:
    """成对的项在声明的维度上是否一致或可比；每个 (对, 维度) 恰有一条判断。记录键为 ``<k1>~<k2>``。"""
    out = Output("", "")
    check_keys(params, "params", {"items", "pairs", "dimensions"}, {"items", "pairs", "dimensions"}, problems)
    check_keys(payload, "payload", {"judgments"}, {"judgments"}, problems)
    items = items_of(params.get("items"), 2, out, problems)
    pairs = _pairs(params.get("pairs"), items, problems)
    dimensions = _dimensions(params.get("dimensions"), problems)

    cells: dict[tuple[tuple[str, str], str], dict[str, Any]] = {}
    attempted: set[tuple[tuple[str, str], str]] = set()  # 给了判断但不合格的单元已另行报告，不再报缺少
    for i, judgment in enumerate(as_list(payload.get("judgments"), "payload.judgments", problems)):
        at = f"payload.judgments[{i}]"
        if not judgment_shape(judgment, at, {"pair", "dimension"}, problems):
            continue
        pair = _pair_of(judgment.get("pair"), pairs)
        dimension = judgment.get("dimension")
        if pair is None:
            problems.add("judgment", f"{at}.pair", f"not a declared pair: {judgment.get('pair')!r}")
        if dimension not in dimensions:
            problems.add("judgment", f"{at}.dimension", f"not a declared dimension: {dimension!r}")
        verdict = verdict_of(judgment, at, out, problems)
        if pair is not None and dimension in dimensions:
            attempted.add((pair, dimension))
        if pair is None or dimension not in dimensions or verdict is None:
            continue
        if (pair, dimension) in cells:
            problems.add("judgment", at, f"a second judgment for {'~'.join(pair)} on {dimension}")
            continue
        cells[(pair, dimension)] = {"pair": list(pair), "dimension": dimension, **verdict}
    if absent := [f"{'~'.join(p)}/{d}" for p in pairs for d in dimensions if (p, d) not in attempted]:
        problems.add("judgment", "payload.judgments", f"missing judgments: {', '.join(absent)}")

    rows = [[f"{a} ~ {b}", *(cells.get(((a, b), d), {}).get("value", "—") for d in dimensions)] for a, b in pairs]
    body = [table(["pair", *dimensions], rows)]
    body += ["**Dimensions**", bullets(f"`{d}`: {q}" for d, q in dimensions.items())]
    body += ["**Items**", bullets(f"`{k}`: [{ref}]" for k, ref in items.items())]
    flagged = [c for c in (cells.get((p, d)) for p in pairs for d in dimensions) if c and c["value"] != "T"]
    body.append("## F and U")
    body.append(
        bullets(f"`{'~'.join(c['pair'])}` · `{c['dimension']}` = {c['value']}{why(c)}" for c in flagged)
        if flagged
        else "None: every judgment is T."
    )
    ordered = [cells[(p, d)] for p in pairs for d in dimensions if (p, d) in cells]
    out.title = f"Check {', '.join(dimensions)} across {len(items)} items"
    out.body = "\n\n".join(body)
    out.data = {
        "items": items,
        "pairs": [list(p) for p in pairs],
        "dimensions": [{"id": d, "question": q} for d, q in dimensions.items()],
        "judgments": ordered,
    }
    return out


def _pairs(value: Any, items: Mapping[str, str], problems: Problems) -> list[tuple[str, str]]:
    if value == "all_pairs":
        return list(itertools.combinations(items, 2))
    if not isinstance(value, list) or not value:
        problems.add("schema", "params.pairs", "all_pairs or a non-empty list of [k1, k2]")
        return []
    pairs: list[tuple[str, str]] = []
    for i, pair in enumerate(value):
        at = f"params.pairs[{i}]"
        if not (isinstance(pair, list) and len(pair) == 2 and all(k in items for k in pair) and pair[0] != pair[1]):
            problems.add("schema", at, "two different item keys")
        elif _pair_of(pair, pairs) is not None:
            problems.add("schema", at, f"repeats {pair}")
        else:
            pairs.append((pair[0], pair[1]))
    return pairs


def _pair_of(value: Any, pairs: Iterable[tuple[str, str]]) -> tuple[str, str] | None:
    """声明中与 ``value`` 相同的对（不计顺序）。"""
    if not isinstance(value, list | tuple) or len(value) != 2:
        return None
    return next((p for p in pairs if set(p) == set(value)), None)


def _dimensions(value: Any, problems: Problems) -> dict[str, str]:
    if not isinstance(value, list) or not value:
        problems.add("schema", "params.dimensions", "a non-empty list of {id, question}")
        return {}
    dimensions: dict[str, str] = {}
    for i, dim in enumerate(value):
        at = f"params.dimensions[{i}]"
        if not (isinstance(dim, Mapping) and set(dim) == {"id", "question"} and is_key(dim["id"])):
            problems.add("schema", at, "{id, question}; the id is a short key")
        elif not is_text(dim["question"]):
            problems.add("schema", f"{at}.question", "a non-empty string")
        elif dim["id"] in dimensions:
            problems.add("schema", f"{at}.id", f"repeats {dim['id']}")
        else:
            dimensions[dim["id"]] = dim["question"].strip()
    return dimensions


CHECK = agent_operator(
    name="Check",
    label="Check",
    description=(
        "Judge whether pairs of items agree or are comparable on declared dimensions (split, horizon, metric, ...). "
        "Give exactly one T/F/U judgment per pair and dimension."
    ),
    params=schema(
        {
            "items": {"type": "object", "description": "item key -> reference; at least two"},
            "pairs": {"description": "all_pairs or a list of [k1, k2]"},
            "dimensions": {
                "type": "array",
                "items": schema({"id": {"type": "string"}, "question": {"type": "string"}}),
            },
        },
        ["items", "pairs", "dimensions"],
    ),
    payload=schema(
        {
            "judgments": {
                "type": "array",
                "items": {**JUDGMENT, "description": "{pair, dimension, value, basis, reason}"},
            }
        },
        ["judgments"],
    ),
    validate=check,
)


__all__ = ["CHECK"]
