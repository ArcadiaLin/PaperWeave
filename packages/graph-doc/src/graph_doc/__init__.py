"""graph_doc：graph-doc（读写同形的 YAML 子图）的解析与求差。见 README。"""

from .document import VERSIONS, DocEdge, DocNode, Document, from_data, is_temp, load, parse
from .errors import DocError, GraphDocError

__all__ = [
    "VERSIONS",
    "DocEdge",
    "DocError",
    "DocNode",
    "Document",
    "GraphDocError",
    "from_data",
    "is_temp",
    "load",
    "parse",
]
