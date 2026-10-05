"""引用的三种写法（docs/designs/v2/operators.md §2.1）与正文中的方括号引用。

- 对象引用：节点 id，如 ``exp_0012``、``art_0003``；
- 来源引用：``<材料 id 或带材料的节点 id>::<章节>::<start>:<end>``，与 graph-doc 的 ``source_refs`` 相同；
- 记录引用：``<artifact id>#<key>``，指 Artifact 数据块中的一条记录。

正文中的引用写在方括号里，如 ``[exp_0012]``、``[art_0003#dlinear-etth1-96]``；一对方括号里可以用逗号或分号
隔开多个引用。方括号里不全是引用时（如普通的方括号文字）不当作引用；Markdown 链接 ``[文字](地址)`` 也不算。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from ..utils.schema import LOCATOR

RefKind = Literal["object", "source", "record"]

NODE_ID = re.compile(r"[a-z]+_[0-9a-f]{4,}")  # 模型节点、Artifact 与 Material 的 id
RECORD = re.compile(r"(?P<art>art_\d{4,})#(?P<key>[A-Za-z0-9_.~-]+)")
RECORD_KEY = re.compile(r"[A-Za-z0-9_.-]+")  # 记录键与 Check、Filter 的项键；~ 留给 Check 的成对键
_BRACKET = re.compile(r"\[([^\[\]\n]+)\](?!\()")
_SEPARATOR = re.compile(r"\s*[,;]\s+(?=[a-z]+_[0-9a-f]{4,})")


@dataclass(frozen=True, slots=True)
class Ref:
    """``head`` 是对象 id、Artifact id（记录引用）或来源引用开头的材料 / 节点 id。"""

    text: str
    kind: RefKind
    head: str
    key: str | None = None  # 记录键
    locator: str | None = None  # 来源引用 :: 之后的部分


def parse_ref(text: str) -> Ref | None:
    """解析一个引用；不是三种写法之一时返回 ``None``。"""
    text = text.strip()
    if match := RECORD.fullmatch(text):
        return Ref(text, "record", match["art"], key=match["key"])
    head, sep, locator = text.partition("::")
    if sep:
        if NODE_ID.fullmatch(head) and LOCATOR.fullmatch(locator):
            return Ref(text, "source", head, locator=locator)
        return None
    if NODE_ID.fullmatch(text):
        return Ref(text, "object", text)
    return None


def cited(text: str) -> list[str]:
    """正文中方括号里的引用，按出现顺序，不去重。"""
    out: list[str] = []
    for match in _BRACKET.finditer(text):
        parts = _SEPARATOR.split(match[1].strip())
        if parts and all(parse_ref(p) is not None for p in parts):
            out += [p.strip() for p in parts]
    return out


def paragraphs(text: str) -> list[str]:
    """以空行分隔的段落；只有标题行的段落不计。"""
    blocks = [b.strip() for b in re.split(r"\n\s*\n", text)]
    return [b for b in blocks if b and not all(line.lstrip().startswith("#") for line in b.splitlines())]


__all__ = ["NODE_ID", "RECORD", "RECORD_KEY", "Ref", "RefKind", "cited", "paragraphs", "parse_ref"]
