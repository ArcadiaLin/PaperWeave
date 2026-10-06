"""Artifact 文档的格式（docs/designs/v2/operators.md §5.3）：头部与正文，需要被其他算子读取的产物在正文末尾附数据块。

写入（e09.artifact.write）与读取（e09.artifact.stale 计算过期）共用。

    ---
    title: …
    nodes_used: [<inputs 中的引用>]
    abs: …
    ---
    <正文>

    ```yaml
    <数据块>
    ```

文档存放在材料根目录下的 ``artifacts/<标题>.md``（:func:`file_name`），标题重复时依次加 `` (1)``、`` (2)``；写入后
不再改动。Material 的 id 由内容哈希给出（``material_<sha256 前 12 位>``），与文件名无关；头部不含 Artifact 的 id，
所以内容相同的文档只存一份。
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import yaml

from ..yamlfmt import dump

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
    def material_id(self) -> str:
        """与论文材料相同的 id 规则（e09.commit.translate）。"""
        return f"material_{self.sha256[:12]}"


_UNSAFE = re.compile(r'[\x00-\x1f\x7f<>:"/\\|?*]')  # 控制字符与 Linux、Windows 文件名中不能用的字符
NAME_BYTES = 200  # 文件名（不含序号与扩展名）的最大字节数；文件系统的上限是 255


def file_name(title: str, n: int = 0) -> str:
    """标题对应的文件名：不能用的字符换成空格，连续空白并成一个，去掉首尾的空白与点，按 UTF-8 截到
    :data:`NAME_BYTES` 字节；``n`` 大于 0 时加 `` (n)``。"""
    stem = " ".join(_UNSAFE.sub(" ", title).split()).strip(" .")  # 不以点开头：不成为隐藏文件
    stem = stem.encode("utf-8")[:NAME_BYTES].decode("utf-8", "ignore").rstrip(" .") or "artifact"
    return f"{stem} ({n}).md" if n else f"{stem}.md"


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
    if op == "MatrixConstruct":
        return [f"{c['row']}~{c['col']}" for c in data.get("cells") or [] if isinstance(c, Mapping)]
    return []


__all__ = ["DIRECTORY", "NAME_BYTES", "Document", "compose", "data_of", "file_name", "header_of", "record_keys"]
