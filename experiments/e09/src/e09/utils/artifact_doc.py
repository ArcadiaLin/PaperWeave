"""Artifact 文档的格式（docs/designs/v2/operators.md §5.3）：头部与正文，需要被其他算子读取的产物在正文末尾附数据块。

写入（e09.use）与读取（e09.read 计算过期）共用。

    ---
    title: …
    nodes_used: [<inputs 中的引用>]
    abs: …
    ---
    <正文>

    ```yaml
    <数据块>
    ```

文档按内容寻址存放在材料根目录下的 ``artifacts/<sha256 前 12 位>.md``，写入后不再改动；头部不含 Artifact 的 id，
所以内容相同的文档只存一份。
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import yaml

from .yamlfmt import dump

DIRECTORY = "artifacts"
_HEADER = re.compile(r"\A---\n(?P<header>.*?)\n---\n", re.DOTALL)
_FENCE = "```yaml\n"


@dataclass(frozen=True, slots=True)
class Document:
    text: str

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()

    @property
    def path(self) -> str:
        """相对于材料根目录的路径。"""
        return f"{DIRECTORY}/{self.sha256[:12]}.md"

    @property
    def material_id(self) -> str:
        """与论文材料相同的 id 规则（e09.write.translate）。"""
        return f"material_{self.sha256[:12]}"


def compose(title: str, nodes_used: list[str], abs_: str, body: str, data: Any = None) -> Document:
    header = dump({"title": title, "nodes_used": nodes_used, "abs": abs_})
    text = f"---\n{header}---\n\n{body.strip()}\n"
    if data is not None:
        text += f"\n```yaml\n{dump(data)}```\n"
    return Document(text)


def header_of(text: str) -> dict[str, Any]:
    """文档头部；没有头部时为空。"""
    match = _HEADER.match(text)
    header = yaml.safe_load(match["header"]) if match else None
    return header if isinstance(header, dict) else {}


def data_of(text: str) -> Any:
    """正文末尾的数据块；没有时为 ``None``。"""
    start = text.rfind(_FENCE)
    end = text.find("```", start + len(_FENCE)) if start >= 0 else -1
    return yaml.safe_load(text[start + len(_FENCE) : end]) if end >= 0 else None


def record_keys(op: str, data: Any) -> list[str]:
    """Artifact 数据块中可用 ``<artifact>#<key>`` 引用的记录键。"""
    if not isinstance(data, Mapping):
        return []
    if op == "Extract":
        return [r["key"] for r in data.get("rows") or [] if isinstance(r, Mapping) and "key" in r]
    if op == "Check":
        return ["~".join(p) for p in data.get("pairs") or [] if isinstance(p, list)]
    if op == "Filter":
        return list(data.get("items") or {})
    return []


__all__ = ["DIRECTORY", "Document", "compose", "data_of", "header_of", "record_keys"]
