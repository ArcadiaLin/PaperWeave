"""各 Agent 算子的参数、内容与正文（docs/designs/v2/operators.md §4.2–4.7）。

每个算子是一个函数 ``(params, payload, problems) -> Output``：按该算子的 schema 检查 ``params`` 与 ``payload``，
把问题记入 ``problems``，并给出默认标题、文档正文、数据块，以及 ``params`` 与 ``payload`` 中出现的引用（由共同
校验核对它们都属于 ``inputs``）。这里只看调用本身；引用是否在库中由 :mod:`e09.use.write` 核对。

判断的取值：``T`` 在声明的条件与依据下成立，``F`` 有依据判断不成立，``U`` 依据不足、相互冲突或条件含义不明。
``T`` 与 ``F`` 必须给出 ``basis``，``U`` 必须给出 ``reason``。
"""

from __future__ import annotations

import itertools
import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from ..utils.refs import RECORD_KEY, cited, paragraphs

VALUES = ("T", "F", "U")
PURPOSES = ("answer", "draft", "idea", "plan", "other")
FIELD_TYPES = ("string", "number", "integer", "boolean", "ref")
_FIELD_NAME = re.compile(r"[a-z][a-z0-9_]*")
_ENUM = re.compile(r"enum\[(?P<values>[^\]]*)\]")


class Problems:
    """调用中的错误：``{rule, where, msg}``，与 Commit 阻塞项的形状相同。"""

    def __init__(self) -> None:
        self.items: list[dict[str, str]] = []

    def add(self, rule: str, where: str, msg: str) -> None:
        self.items.append({"rule": rule, "where": where, "msg": msg})

    def __bool__(self) -> bool:
        return bool(self.items)


@dataclass
class Output:
    title: str
    body: str
    data: Any = None  # 正文末尾的数据块；只有 Extract、Check、Filter 有
    refs: list[tuple[str, str]] = field(default_factory=list)  # (位置, 引用)：必须属于 inputs
    roles: dict[str, list[str]] = field(default_factory=dict)  # 引用 → 它在参数中的角色（USED.role）
    stats: dict[str, Any] = field(default_factory=dict)


Operator = Callable[[Mapping[str, Any], Mapping[str, Any], Problems], Output]


# ── Extract ───────────────────────────────────────────────────────────


def extract(params: Mapping[str, Any], payload: Mapping[str, Any], problems: Problems) -> Output:
    """读原文后取成的结构化记录。记录键由 ``schema.key`` 中字段的值拼成，在本次产物中唯一。"""
    out = Output("", "")
    _only(params, "params", {"schema"}, {"schema"}, problems)
    _only(payload, "payload", {"rows"}, {"rows", "note"}, problems)
    schema = params.get("schema")
    if not isinstance(schema, Mapping):
        problems.add("schema", "params.schema", "{fields: {name: type}, required: [...], key: [...]}")
        return out
    _only(schema, "params.schema", {"fields", "key"}, {"fields", "required", "key"}, problems)
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
    if note is not None and not _text(note):
        problems.add("schema", "payload.note", "a non-empty string")
    if not rows and not _text(note):
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
        if not _text(source):
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
            if not _typed(value, type_):
                problems.add("schema", f"{at}.{name}", f"not a {_type_name(type_)}: {value!r}")
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
        [r["key"], *(_cell(r.get(n), fields[n]) for n in names), f"[{r['source']}]" if r["source"] else "—"]
        for r in records
    ]
    body = table(["key", *names, "source"], cells) if records else "No records."
    if _text(note):
        body += f"\n\n**Note:** {note.strip()}"
    data: dict[str, Any] = {
        "schema": {"fields": dict(schema.get("fields") or {}), "required": required, "key": key},
        "rows": records,
    }
    if _text(note):
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
            problems.add("schema", at, "field names are lower_snake_case; key and source are reserved")
            continue
        parsed = _parse_type(type_)
        if parsed is None:
            problems.add("schema", at, f"one of {list(FIELD_TYPES)} or enum[a, b, ...]")
            continue
        fields[name] = parsed
    return fields


def _parse_type(value: Any) -> Any:
    if value in FIELD_TYPES:
        return value
    match = _ENUM.fullmatch(value) if isinstance(value, str) else None
    if match is None:
        return None
    options = tuple(v.strip() for v in match["values"].split(",") if v.strip())
    return options or None


def _typed(value: Any, type_: Any) -> bool:
    if isinstance(type_, tuple):
        return value in type_
    if type_ == "number":
        return isinstance(value, int | float) and not isinstance(value, bool)
    if type_ == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if type_ == "boolean":
        return isinstance(value, bool)
    return isinstance(value, str)  # string、ref


def _type_name(type_: Any) -> str:
    return f"enum{list(type_)}" if isinstance(type_, tuple) else type_


def _cell(value: Any, type_: Any) -> str:
    if value is None:
        return "—"
    if type_ == "ref":
        return f"[{value}]"
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9._]+", "-", value.lower()).strip("-")


# ── Summarize、Generate ───────────────────────────────────────────────


def summarize(params: Mapping[str, Any], payload: Mapping[str, Any], problems: Problems) -> Output:
    """忠实压缩输入：每个段落至少有一处引用。"""
    _only(params, "params", {"focus"}, {"focus"}, problems)
    _only(payload, "payload", {"text"}, {"text"}, problems)
    focus, text = params.get("focus"), payload.get("text")
    if not _text(focus):
        problems.add("schema", "params.focus", "a non-empty string")
    if not _text(text):
        problems.add("schema", "payload.text", "a non-empty string")
        return Output("Summary", "")
    for n, paragraph in enumerate(paragraphs(text), start=1):
        if not cited(paragraph):
            problems.add("citation", "payload.text", f"paragraph {n} has no reference: {_head(paragraph)}")
    refs = [("payload.text", r) for r in cited(text)]
    return Output(f"Summary: {focus}" if _text(focus) else "Summary", text.strip(), refs=refs)


def generate(params: Mapping[str, Any], payload: Mapping[str, Any], problems: Problems) -> Output:
    """新内容：回答、草稿、点子、方案。允许没有引用的段落，返回有引用的段落比例。"""
    _only(params, "params", {"purpose"}, {"purpose"}, problems)
    _only(payload, "payload", {"text"}, {"text"}, problems)
    purpose, text = params.get("purpose"), payload.get("text")
    if purpose not in PURPOSES:
        problems.add("schema", "params.purpose", f"one of {list(PURPOSES)}")
    if not _text(text):
        problems.add("schema", "payload.text", "a non-empty string")
        return Output("Generate", "")
    blocks = paragraphs(text)
    stats = {"cited_paragraphs": f"{sum(1 for b in blocks if cited(b))}/{len(blocks)}"}
    refs = [("payload.text", r) for r in cited(text)]
    title = f"Generate ({purpose})" if purpose in PURPOSES else "Generate"
    return Output(title, text.strip(), refs=refs, stats=stats)


# ── Check、Verify、Filter ─────────────────────────────────────────────


def check(params: Mapping[str, Any], payload: Mapping[str, Any], problems: Problems) -> Output:
    """成对的项在声明的维度上是否一致或可比；每个 (对, 维度) 恰有一条判断。记录键为 ``<k1>~<k2>``。"""
    out = Output("", "")
    _only(params, "params", {"items", "pairs", "dimensions"}, {"items", "pairs", "dimensions"}, problems)
    _only(payload, "payload", {"judgments"}, {"judgments"}, problems)
    items = _items(params.get("items"), 2, out, problems)
    pairs = _pairs(params.get("pairs"), items, problems)
    dimensions = _dimensions(params.get("dimensions"), problems)

    cells: dict[tuple[tuple[str, str], str], dict[str, Any]] = {}
    attempted: set[tuple[tuple[str, str], str]] = set()  # 给了判断但不合格的单元已另行报告，不再报缺少
    for i, judgment in enumerate(_list(payload.get("judgments"), "payload.judgments", problems)):
        at = f"payload.judgments[{i}]"
        if not _judgment_shape(judgment, at, {"pair", "dimension"}, problems):
            continue
        pair = _pair_of(judgment.get("pair"), pairs)
        dimension = judgment.get("dimension")
        if pair is None:
            problems.add("judgment", f"{at}.pair", f"not a declared pair: {judgment.get('pair')!r}")
        if dimension not in dimensions:
            problems.add("judgment", f"{at}.dimension", f"not a declared dimension: {dimension!r}")
        verdict = _verdict(judgment, at, out, problems)
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
    body += ["**Dimensions**", _bullets(f"`{d}`: {q}" for d, q in dimensions.items())]
    body += ["**Items**", _bullets(f"`{k}`: [{ref}]" for k, ref in items.items())]
    flagged = [c for c in (cells.get((p, d)) for p in pairs for d in dimensions) if c and c["value"] != "T"]
    body.append("## F and U")
    body.append(
        _bullets(f"`{'~'.join(c['pair'])}` · `{c['dimension']}` = {c['value']}{_why(c)}" for c in flagged)
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


def verify(params: Mapping[str, Any], payload: Mapping[str, Any], problems: Problems) -> Output:
    """一条主张在给定证据下是否成立，以及成立的范围。没有找到支持不等于反驳，应为 ``U``。"""
    out = Output("", "")
    _only(params, "params", {"claim"}, {"claim"}, problems)
    claim = params.get("claim")
    if _text(claim):
        out.refs.append(("params.claim", claim))
        out.roles.setdefault(claim, []).append("claim")
        stated = f"[{claim}]"
    elif isinstance(claim, Mapping) and set(claim) == {"text"} and _text(claim["text"]):
        stated = claim["text"].strip()
    else:
        problems.add("schema", "params.claim", "a reference or {text}")
        stated = "—"
    verdict = None
    if _judgment_shape(payload, "payload", {"conditions"}, problems, required=frozenset()):
        verdict = _verdict(payload, "payload", out, problems)
    conditions = payload.get("conditions")
    if conditions is not None and not _text(conditions):
        problems.add("schema", "payload.conditions", "a non-empty string")
    lines = [f"**Claim:** {stated}", f"**Value:** {payload.get('value', '—')}"]
    if _text(conditions):
        lines.append(f"**Conditions:** {conditions.strip()}")
    if verdict and verdict.get("basis"):
        lines.append("**Basis:** " + ", ".join(f"[{r}]" for r in verdict["basis"]))
    if verdict and verdict.get("reason"):
        lines.append(f"**Reason:** {verdict['reason']}")
    out.title = f"Verify {stated}" if len(stated) <= 80 else f"Verify {stated[:77]}..."
    out.body = "\n\n".join(lines)
    return out


def filter_(params: Mapping[str, Any], payload: Mapping[str, Any], problems: Problems) -> Output:
    """逐项判断是否满足条件；每项恰有一条判断，``U`` 不当作 ``F`` 丢弃。记录键为项键。"""
    out = Output("", "")
    _only(params, "params", {"items", "condition"}, {"items", "condition"}, problems)
    _only(payload, "payload", {"judgments"}, {"judgments"}, problems)
    items = _items(params.get("items"), 1, out, problems)
    condition = params.get("condition")
    if not (isinstance(condition, Mapping) and set(condition) == {"id", "text"} and _key(condition["id"])):
        problems.add("schema", "params.condition", "{id, text}; the id is a short key")
        condition = {"id": "condition", "text": ""}
    elif not _text(condition["text"]):
        problems.add("schema", "params.condition.text", "a non-empty string")

    judged: dict[str, dict[str, Any]] = {}
    attempted: set[str] = set()
    for i, judgment in enumerate(_list(payload.get("judgments"), "payload.judgments", problems)):
        at = f"payload.judgments[{i}]"
        if not _judgment_shape(judgment, at, {"key"}, problems):
            continue
        key = judgment.get("key")
        if key not in items:
            problems.add("judgment", f"{at}.key", f"not a declared item: {key!r}")
        verdict = _verdict(judgment, at, out, problems)
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
        lines = (f"`{j['key']}` [{items[j['key']]}]{_why(j)}" for j in group)
        body += [f"## {value} ({len(group)})", _bullets(lines) if group else "None."]
    out.title = f"Filter: {condition['id']}"
    out.body = "\n\n".join(body)
    out.data = {"items": items, "condition": dict(condition), "judgments": ordered}
    return out


def _items(value: Any, minimum: int, out: Output, problems: Problems) -> dict[str, str]:
    if not isinstance(value, Mapping) or len(value) < minimum:
        problems.add("schema", "params.items", f"a mapping of at least {minimum} item key(s) to references")
        return {}
    items: dict[str, str] = {}
    for key, ref in value.items():
        at = f"params.items.{key}"
        if not _key(key):
            problems.add("schema", at, "item keys use letters, digits, _ . and -")
        elif not _text(ref):
            problems.add("schema", at, "a reference")
        else:
            items[key] = ref
            out.refs.append((at, ref))
            out.roles.setdefault(ref, []).append(key)
    return items


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
        if not (isinstance(dim, Mapping) and set(dim) == {"id", "question"} and _key(dim["id"])):
            problems.add("schema", at, "{id, question}; the id is a short key")
        elif not _text(dim["question"]):
            problems.add("schema", f"{at}.question", "a non-empty string")
        elif dim["id"] in dimensions:
            problems.add("schema", f"{at}.id", f"repeats {dim['id']}")
        else:
            dimensions[dim["id"]] = dim["question"].strip()
    return dimensions


def _judgment_shape(
    value: Any,
    at: str,
    extra: set[str],
    problems: Problems,
    required: frozenset[str] | None = None,
) -> bool:
    if not isinstance(value, Mapping):
        problems.add("schema", at, "a judgment {value, basis?, reason?}")
        return False
    allowed = {"value", "basis", "reason", *extra}
    _only(value, at, {"value", *(extra if required is None else required)}, allowed, problems)
    return True


def _verdict(judgment: Mapping[str, Any], at: str, out: Output, problems: Problems) -> dict[str, Any] | None:
    """``T`` 与 ``F`` 必须有 ``basis``，``U`` 必须有 ``reason``；``basis`` 中的引用必须属于 inputs。"""
    value, basis, reason = judgment.get("value"), judgment.get("basis"), judgment.get("reason")
    if value not in VALUES:
        problems.add("judgment", f"{at}.value", "T, F or U; an interrupted or malformed run is an error, not U")
        return None
    basis = [basis] if isinstance(basis, str) else basis
    if basis is not None and (not isinstance(basis, list) or not all(_text(b) for b in basis)):
        problems.add("judgment", f"{at}.basis", "a reference or a list of references")
        return None
    if reason is not None and not _text(reason):
        problems.add("judgment", f"{at}.reason", "a non-empty string")
        return None
    if value in ("T", "F") and not basis:
        problems.add("judgment", f"{at}.basis", f"{value} needs the references it rests on")
        return None
    if value == "U" and not reason:
        problems.add("judgment", f"{at}.reason", "U needs a reason: insufficient, conflicting or unclear evidence")
        return None
    out.refs += [(f"{at}.basis", b) for b in basis or []]
    verdict: dict[str, Any] = {"value": value}
    if basis:
        verdict["basis"] = list(basis)
    if reason:
        verdict["reason"] = reason.strip()
    return verdict


# ── 公共 ──────────────────────────────────────────────────────────────


def _only(value: Any, at: str, required: set[str], allowed: set[str], problems: Problems) -> None:
    if not isinstance(value, Mapping):
        problems.add("schema", at, f"a mapping with {sorted(allowed)}")
        return
    if unknown := sorted(set(value) - allowed):
        problems.add("schema", at, f"unknown keys {unknown}; allowed {sorted(allowed)}")
    for key in sorted(required - set(value)):
        problems.add("schema", f"{at}.{key}", "required")


def _subset(value: Any, fields: Mapping[str, Any], at: str, problems: Problems) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(v in fields for v in value):
        problems.add("schema", at, f"a list of fields from {list(fields)}")
        return []
    return list(dict.fromkeys(value))


def _list(value: Any, at: str, problems: Problems) -> list[Any]:
    if not isinstance(value, list):
        problems.add("schema", at, "a list")
        return []
    return value


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _key(value: Any) -> bool:
    return isinstance(value, str) and bool(RECORD_KEY.fullmatch(value))


def _head(text: str) -> str:
    line = " ".join(text.split())
    return repr(line if len(line) <= 60 else line[:57] + "...")


def _why(judgment: Mapping[str, Any]) -> str:
    parts = []
    if judgment.get("basis"):
        parts.append("basis " + ", ".join(f"[{r}]" for r in judgment["basis"]))
    if judgment.get("reason"):
        parts.append(judgment["reason"])
    return " — " + "; ".join(parts) if parts else ""


def _bullets(lines: Iterable[str]) -> str:
    return "\n".join(f"- {line}" for line in lines)


def table(columns: list[str], rows: list[list[str]]) -> str:
    """Markdown 表格；单元格中的 ``|`` 与换行会转义。"""

    def cell(value: str) -> str:
        return value.replace("|", "\\|").replace("\n", " ")

    lines = ["| " + " | ".join(cell(c) for c in columns) + " |", "|" + "---|" * len(columns)]
    lines += ["| " + " | ".join(cell(c) for c in row) + " |" for row in rows]
    return "\n".join(lines)


OPERATORS: dict[str, Operator] = {
    "Extract": extract,
    "Summarize": summarize,
    "Generate": generate,
    "Check": check,
    "Verify": verify,
    "Filter": filter_,
}


__all__ = ["OPERATORS", "VALUES", "Operator", "Output", "Problems"]
